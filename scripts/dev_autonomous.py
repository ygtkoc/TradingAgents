#!/usr/bin/env python
"""
Single-command boot for the entire autonomous paper-trading stack.

Spawns four subprocesses (all `python -m src.main`):

  1. autonomous       — market data + signal seeder + demo-bot bootstrap + /health
  2. agent-engine     — agent pipeline → trade_decisions
  3. execution-engine — paper executor → trades
  4. position-engine  — lifecycle (P&L, SL/TP, trailing, reconciliation)

Behaviour:

  • Each child's stdout/stderr is line-prefixed with [name] and forwarded.
  • If a child exits non-zero (and we are not shutting down), it is restarted
    with an exponential-backoff cap of 30 s. After 10 consecutive crashes
    the supervisor gives up on that child, but leaves the rest running.
  • Ctrl-C / SIGTERM sends SIGTERM to every child, then SIGKILL after 10 s
    if any haven't exited.
  • Process-level supervision only — within each subprocess, the autonomous
    package's `Supervisor` handles in-process task supervision.

This script does NOT start live execution. The execution and position
engines respect their own `ENABLE_LIVE_*` env gates which default to false.

Usage:
    python scripts/dev_autonomous.py

Or just specific workers:
    python scripts/dev_autonomous.py autonomous agent-engine
"""
from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (name, working_dir, module) — each subprocess runs as `python -m <module>`
WORKERS: list[tuple[str, Path, str]] = [
    ("autonomous",        ROOT / "autonomous",        "src.main"),
    ("agent-engine",      ROOT / "agent-engine",      "src.main"),
    ("execution-engine",  ROOT / "execution-engine",  "src.main"),
    ("position-engine",   ROOT / "position-engine",   "src.main"),
]

MAX_RESTART_ATTEMPTS = 10
BACKOFF_INITIAL_S    = 1.0
BACKOFF_MAX_S        = 30.0
TERMINATE_TIMEOUT_S  = 10.0

# asyncio's StreamReader defaults to a 64 KB line limit; a Python traceback
# or a structlog JSON line with embedded payloads can exceed that and crash
# `readline()` with `LimitOverrunError`/`ValueError`. Pump it to 16 MB so
# realistic log lines never trip it, and additionally fall back to
# chunk-truncation if the limit is *still* exceeded.
STREAM_BUFFER_LIMIT     = 16 * 1024 * 1024   # 16 MB
LONG_LINE_TRUNCATE_AT   = 64 * 1024          # 64 KB displayed maximum


# ── ANSI helpers ─────────────────────────────────────────────────────────────

_COLOURS = ["\033[36m", "\033[33m", "\033[35m", "\033[32m", "\033[34m", "\033[31m"]
_RESET   = "\033[0m"
_USE_COLOUR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _prefix(name: str, idx: int) -> str:
    if _USE_COLOUR:
        return f"{_COLOURS[idx % len(_COLOURS)]}[{name:<16}]{_RESET}"
    return f"[{name:<16}]"


# ── Subprocess management ───────────────────────────────────────────────────

class WorkerSupervisor:
    def __init__(
        self,
        workers: list[tuple[str, Path, str]],
        shutdown_evt: asyncio.Event,
    ) -> None:
        self.workers      = workers
        self.shutdown_evt = shutdown_evt
        self._procs:        dict[str, asyncio.subprocess.Process] = {}
        self._giving_up_on: set[str] = set()

    async def run_all(self) -> int:
        tasks = [
            asyncio.create_task(self._run_one(name, cwd, module, idx), name=name)
            for idx, (name, cwd, module) in enumerate(self.workers)
        ]
        # Wait for shutdown OR any child to permanently fail
        shutdown_task = asyncio.create_task(self.shutdown_evt.wait(), name="__shutdown__")

        done, _ = await asyncio.wait(
            [*tasks, shutdown_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # If shutdown was requested, terminate every child cleanly.
        if self.shutdown_evt.is_set():
            await self._terminate_all()

        # Drain remaining tasks.
        for t in tasks:
            if not t.done():
                try:
                    await asyncio.wait_for(t, timeout=TERMINATE_TIMEOUT_S + 5.0)
                except asyncio.TimeoutError:
                    t.cancel()

        return 0 if not self._giving_up_on else 1

    async def _run_one(self, name: str, cwd: Path, module: str, idx: int) -> None:
        prefix  = _prefix(name, idx)
        attempts = 0
        backoff  = BACKOFF_INITIAL_S

        while not self.shutdown_evt.is_set():
            if not cwd.exists():
                _emit(prefix, f"working dir not found: {cwd} — skipping")
                return

            attempts += 1
            _emit(prefix, f"starting (attempt {attempts}): python -m {module} (cwd={cwd})")

            try:
                proc = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-u",                # unbuffered output
                    "-m", module,
                    cwd=str(cwd),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    env=os.environ.copy(),
                    # CRITICAL: bump the StreamReader limit so long log lines
                    # (e.g. tracebacks, JSON state dumps) don't crash readline().
                    limit=STREAM_BUFFER_LIMIT,
                )
            except FileNotFoundError as exc:
                _emit(prefix, f"failed to spawn: {exc}")
                return

            self._procs[name] = proc
            await self._stream_output(proc, prefix)
            rc = await proc.wait()
            self._procs.pop(name, None)

            if self.shutdown_evt.is_set():
                _emit(prefix, f"exited (rc={rc}) during shutdown")
                return

            if rc == 0:
                _emit(prefix, "exited cleanly (rc=0); not restarting")
                return

            if attempts >= MAX_RESTART_ATTEMPTS:
                _emit(prefix, f"giving up after {attempts} crashes (rc={rc})")
                self._giving_up_on.add(name)
                return

            _emit(prefix, f"crashed (rc={rc}); restart in {backoff:.1f}s")
            try:
                await asyncio.wait_for(self.shutdown_evt.wait(), timeout=backoff)
                # if we woke up here, shutdown was requested
                return
            except asyncio.TimeoutError:
                pass
            backoff = min(backoff * 2.0, BACKOFF_MAX_S)

    @staticmethod
    async def _stream_output(proc: asyncio.subprocess.Process, prefix: str) -> None:
        """Stream child stdout line-by-line, surviving any overlong line.

        The default `StreamReader.readline()` raises:
            ValueError:        "Separator is not found, and chunk exceed the limit"
                               (Python ≤3.11)
            LimitOverrunError: same condition (Python ≥3.12 / asyncio docs)

        Both leave the *partial* line still in the StreamReader buffer. We
        catch them and drain the buffer with a single bounded `read()` call,
        then truncate, emit, and continue.
        """
        assert proc.stdout is not None
        reader = proc.stdout
        try:
            while True:
                try:
                    raw = await reader.readline()
                except (asyncio.LimitOverrunError, ValueError) as exc:
                    # Drain whatever is buffered without blocking forever.
                    # `LimitOverrunError.consumed` (when present) is the byte
                    # count we know is in the buffer; otherwise read up to
                    # STREAM_BUFFER_LIMIT and let asyncio give us what it has.
                    consumed = getattr(exc, "consumed", STREAM_BUFFER_LIMIT)
                    try:
                        raw = await reader.read(consumed)
                    except Exception:
                        raw = b""
                    # consume up to (and including) the next newline so
                    # subsequent readline() calls realign on a fresh line.
                    try:
                        tail = await reader.readuntil(b"\n")
                        raw = (raw or b"") + tail
                    except (asyncio.LimitOverrunError, ValueError):
                        # Even the tail is still too long; just drop it.
                        pass
                    except asyncio.IncompleteReadError as ire:
                        raw = (raw or b"") + (ire.partial or b"")

                if not raw:
                    return  # EOF

                text = raw.decode(errors="replace").rstrip("\r\n")
                if len(text) > LONG_LINE_TRUNCATE_AT:
                    text = (
                        text[:LONG_LINE_TRUNCATE_AT]
                        + f"… [truncated {len(text) - LONG_LINE_TRUNCATE_AT} chars]"
                    )
                _emit(prefix, text)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # last-resort guard — never let stream death kill the supervisor
            _emit(prefix, f"[supervisor] stream-reader crashed; will reconnect on restart: {exc!r}")

    async def _terminate_all(self) -> None:
        if not self._procs:
            return

        # 1. Polite SIGTERM
        for name, proc in list(self._procs.items()):
            if proc.returncode is None:
                _emit(_prefix(name, 0), "terminating (SIGTERM)")
                try:
                    proc.terminate()
                except ProcessLookupError:
                    pass

        # 2. Wait
        deadline = asyncio.get_running_loop().time() + TERMINATE_TIMEOUT_S
        while self._procs:
            now = asyncio.get_running_loop().time()
            if now >= deadline:
                break
            await asyncio.sleep(0.2)
            for name, proc in list(self._procs.items()):
                if proc.returncode is not None:
                    self._procs.pop(name, None)

        # 3. Hard kill the laggards
        for name, proc in list(self._procs.items()):
            if proc.returncode is None:
                _emit(_prefix(name, 0), "force-killing (SIGKILL)")
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass


def _emit(prefix: str, line: str) -> None:
    sys.stdout.write(f"{prefix} {line}\n")
    sys.stdout.flush()


# ── Entry point ──────────────────────────────────────────────────────────────

def _select_workers(argv: list[str]) -> list[tuple[str, Path, str]]:
    if not argv:
        return WORKERS
    requested = set(argv)
    valid     = {name for name, _, _ in WORKERS}
    unknown   = requested - valid
    if unknown:
        sys.stderr.write(f"unknown workers: {', '.join(sorted(unknown))}\n")
        sys.stderr.write(f"valid:           {', '.join(sorted(valid))}\n")
        sys.exit(2)
    return [w for w in WORKERS if w[0] in requested]


async def _amain(argv: list[str]) -> int:
    workers      = _select_workers(argv)
    shutdown_evt = asyncio.Event()

    def _stop(_signum=None, _frame=None) -> None:
        if not shutdown_evt.is_set():
            sys.stdout.write("\n[supervisor] shutdown signal received\n")
            sys.stdout.flush()
            shutdown_evt.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            # Windows
            signal.signal(sig, _stop)

    sup = WorkerSupervisor(workers, shutdown_evt)

    sys.stdout.write(
        f"[supervisor] booting {len(workers)} workers: "
        f"{', '.join(name for name, _, _ in workers)}\n"
        f"[supervisor] autonomous /health → http://localhost:9090/health\n"
    )
    sys.stdout.flush()

    return await sup.run_all()


def main() -> None:
    try:
        rc = asyncio.run(_amain(sys.argv[1:]))
    except KeyboardInterrupt:
        rc = 0
    sys.exit(rc)


if __name__ == "__main__":
    main()
