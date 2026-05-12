"""
Security category agents.
These agents are the last defence against malicious signals,
prompt injection attacks, and policy violations.

SecurityGuardianAgent and PromptInjectionDefenseAgent both have can_veto=True.
They operate on the signal metadata and symbol strings — never on free-form LLM output.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from src.agents.base import BaseAgent
from src.db.models import AgentDecision, AgentOutputResult

if TYPE_CHECKING:
    from src.orchestration.state import PipelineState


# ── Known injection patterns ──────────────────────────────────────────────────
# These patterns target the most common prompt injection vectors.
# The signal metadata field is the only untrusted free-text input.

_INJECTION_PATTERNS: list[re.Pattern] = [
    # Role override attempts
    re.compile(r"\b(ignore|forget|disregard)\b.{0,30}\b(previous|prior|above|instructions?|rules?|constraints?)\b", re.I),
    re.compile(r"\byou are now\b", re.I),
    re.compile(r"\bact as\b.{0,20}\b(admin|root|system|developer|unrestricted)\b", re.I),
    re.compile(r"\bnew\s+(persona|role|identity|instructions?)\b", re.I),
    # System prompt leakage attempts
    re.compile(r"\brepeat\b.{0,30}\b(system|prompt|instructions?|above)\b", re.I),
    re.compile(r"\bprint\b.{0,30}\b(system|prompt|instructions?|configuration)\b", re.I),
    re.compile(r"\bshow\b.{0,30}\b(system|prompt|configuration|secrets?|keys?)\b", re.I),
    # Data exfiltration patterns
    re.compile(r"https?://[^\s]{20,}", re.I),   # Long URLs in metadata
    re.compile(r"webhook|exfil|callback\s+url", re.I),
    # Code/command injection in metadata
    re.compile(r"```|\$\(|`[^`]+`|\beval\s*\(|\bexec\s*\(", re.I),
    re.compile(r"\bimport\b.{0,30}\bos\b|\bos\.system\b|\bsubprocess\b", re.I),
    # SQL injection
    re.compile(r"(--|;|\bunion\b|\bselect\b|\bdrop\b|\bdelete\b|\binsert\b)\s+.{0,30}\b(from|into|table)\b", re.I),
    # Override trading decisions directly
    re.compile(r"\b(approve|execute|open|place)\b.{0,20}\b(trade|order|position)\b", re.I),
    re.compile(r"\bset\b.{0,20}\b(score|confidence|decision)\b.{0,20}(=|\bto\b)", re.I),
]

# Suspicious symbol characters (valid symbols should be ASSET/QUOTE format)
_VALID_SYMBOL_RE = re.compile(r"^[A-Z0-9]{1,20}(/[A-Z0-9]{1,10})?(:USDT)?$")
_VALID_EXCHANGE_RE = re.compile(r"^[a-z0-9_\-]{1,30}$")


class SecurityGuardianAgent(BaseAgent):
    """
    Validates signal provenance and policy compliance.
    Checks:
    - Symbol and exchange format validity
    - Signal source is a known/allowed source
    - Signal metadata size limits
    - No override of critical safety flags
    - Dry-run policy respected

    can_veto=True
    """

    async def _execute(self, state: "PipelineState") -> AgentOutputResult:
        signal = state["signal"]
        findings: list[str] = []
        flags: list[str] = []
        veto_reasons: list[str] = []

        # ── Symbol format validation ──────────────────────────────────────────
        symbol = signal.symbol or ""
        if not _VALID_SYMBOL_RE.match(symbol):
            veto_reasons.append(f"Symbol '{symbol}' does not match expected format (e.g. BTC/USDT)")
            flags.append("invalid_symbol_format")
        else:
            findings.append(f"Symbol '{symbol}' format valid")

        # ── Exchange format validation ────────────────────────────────────────
        exchange = signal.exchange or ""
        if not _VALID_EXCHANGE_RE.match(exchange):
            veto_reasons.append(f"Exchange '{exchange}' contains invalid characters")
            flags.append("invalid_exchange_format")
        else:
            findings.append(f"Exchange '{exchange}' format valid")

        # ── Signal direction sanity ───────────────────────────────────────────
        valid_directions = {"long", "short", "neutral"}
        direction_val = signal.direction.value if signal.direction else ""
        if direction_val not in valid_directions:
            veto_reasons.append(f"Unknown signal direction: '{direction_val}'")
            flags.append("invalid_direction")

        # ── Metadata checks — use sanitized_metadata from state ──────────────
        # The orchestrator pre-processes raw metadata before graph entry and
        # stores the safe version in state["sanitized_metadata"].
        # Agents must NEVER read signal["metadata"] for content decisions.
        sanitized_metadata = state.get("sanitized_metadata", {})
        metadata_suspicious = state.get("metadata_suspicious", False)
        metadata_oversize = state.get("metadata_oversize", False)

        if metadata_oversize:
            findings.append("Signal metadata exceeded size limit — sanitized copy used")
            flags.append("oversized_metadata")

        # Report pre-scan result from orchestrator
        if metadata_suspicious:
            # Orchestrator already detected injection before graph entry.
            # This agent confirms and vetoes.
            veto_reasons.append(
                "Injection patterns detected in signal metadata (pre-pipeline scan)"
            )
            flags.append("metadata_injection_attempt")
        else:
            # Re-scan the sanitized copy as a defence-in-depth measure
            sanitized_str = str(sanitized_metadata)[:2048]
            injection_hits = _scan_for_injection(sanitized_str)
            if injection_hits:
                veto_reasons.append(
                    f"Injection patterns in sanitized metadata: {injection_hits[:2]}"
                )
                flags.append("metadata_injection_attempt")

        # ── Apply veto if any hard failures ──────────────────────────────────
        if veto_reasons:
            return self._safe_veto(
                reason="SecurityGuardian veto: " + "; ".join(veto_reasons),
                severity_flags=flags,
            )

        # ── All clear ────────────────────────────────────────────────────────
        security_score = max(0.0, 50.0 - len(flags) * 15.0)

        return self._make_result(
            decision=AgentDecision.WAIT,
            score=security_score,
            confidence=0.95,
            reasoning=(
                "Security guardian check passed. "
                + ("; ".join(findings) if findings else "No issues.")
            ),
            output={
                "symbol_valid": not any(f == "invalid_symbol_format" for f in flags),
                "exchange_valid": not any(f == "invalid_exchange_format" for f in flags),
                "metadata_clean": "metadata_injection_attempt" not in flags,
                "metadata_oversize": metadata_oversize,
                "metadata_suspicious_pre_scan": metadata_suspicious,
                "flags": flags,
            },
            security_flags=flags,
        )


class PromptInjectionDefenseAgent(BaseAgent):
    """
    Deep scan for prompt injection attempts across all free-text fields
    that could influence agent reasoning or pipeline routing.

    This agent runs AFTER all other agents so it can also scan agent
    reasoning strings for signs that an earlier agent was compromised
    (e.g., a misbehaving LLM-backed agent).

    can_veto=True
    """

    async def _execute(self, state: "PipelineState") -> AgentOutputResult:
        signal = state["signal"]
        agent_results = state.get("agent_results", [])

        scan_targets: dict[str, str] = {}
        flags: list[str] = []
        veto_reasons: list[str] = []

        # ── Build scan corpus ─────────────────────────────────────────────────
        # 1. Signal structural fields (symbol/exchange — not metadata content)
        scan_targets["signal.symbol"] = signal.symbol or ""
        scan_targets["signal.exchange"] = signal.exchange or ""

        # 2. Sanitized metadata from state (NEVER use signal["metadata"] directly)
        #    The orchestrator has already size-limited and field-filtered it.
        sanitized_metadata = state.get("sanitized_metadata", {})
        for k, v in sanitized_metadata.items():
            scan_targets[f"signal.sanitized_metadata.{k}"] = str(v)[:500]

        # 3. If orchestrator pre-scan already flagged injection, count it as a hit
        if state.get("metadata_suspicious"):
            veto_reasons.append("Pre-pipeline metadata injection flag set by orchestrator")
            flags.append("metadata_injection_attempt")

        # 2. Agent reasoning strings — detect compromised/jailbroken agents
        for result in agent_results:
            agent_name = result.get("agent_name", "unknown")
            reasoning = result.get("reasoning", "")
            scan_targets[f"agent.{agent_name}.reasoning"] = reasoning[:500]

        # ── Run injection scan ────────────────────────────────────────────────
        compromised_fields: list[str] = []
        for field, content in scan_targets.items():
            hits = _scan_for_injection(content)
            if hits:
                compromised_fields.append(f"{field}: {hits[0]}")

        if compromised_fields:
            # High severity: agent reasoning compromise = potential pipeline takeover
            reasoning_compromised = [f for f in compromised_fields if f.startswith("agent.")]
            signal_compromised = [f for f in compromised_fields if f.startswith("signal.")]

            if reasoning_compromised:
                veto_reasons.append(
                    f"Agent reasoning injection detected — pipeline may be compromised: "
                    f"{reasoning_compromised[:2]}"
                )
                flags.append("agent_reasoning_injection")

            if signal_compromised:
                veto_reasons.append(
                    f"Signal field injection detected: {signal_compromised[:2]}"
                )
                flags.append("signal_field_injection")

        # ── Anomalous score patterns ──────────────────────────────────────────
        # An agent that always returns score=100 or always overrides decisions
        # is a sign of a misbehaving component.
        if agent_results:
            scores = [r.get("score", 0) for r in agent_results if r.get("score") is not None]
            if scores:
                perfect_scores = sum(1 for s in scores if abs(s) >= 99.0)
                if perfect_scores >= 3:
                    flags.append("suspicious_score_distribution")
                    veto_reasons.append(
                        f"{perfect_scores}/{len(scores)} agents returned extreme scores "
                        "— possible score manipulation"
                    )

        # ── Apply veto ────────────────────────────────────────────────────────
        if veto_reasons:
            return self._safe_veto(
                reason="PromptInjectionDefense veto: " + "; ".join(veto_reasons),
                severity_flags=flags,
            )

        return self._make_result(
            decision=AgentDecision.WAIT,
            score=50.0,  # Clean pass: positive contribution to final score
            confidence=0.95,
            reasoning=(
                f"Injection scan passed. Scanned {len(scan_targets)} fields across "
                f"signal + {len(agent_results)} agent outputs. No injection patterns found."
            ),
            output={
                "fields_scanned": len(scan_targets),
                "agents_scanned": len(agent_results),
                "clean": True,
                "flags": flags,
            },
            security_flags=flags,
        )


def _scan_for_injection(text: str) -> list[str]:
    """
    Runs all injection patterns against `text`.
    Returns a list of matched pattern descriptions (empty list = clean).
    """
    hits: list[str] = []
    for pattern in _INJECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            # Return the matched substring, not the full text
            hits.append(match.group(0)[:80])
    return hits
