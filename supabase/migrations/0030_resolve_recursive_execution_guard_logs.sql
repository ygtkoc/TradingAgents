-- Prevent execution guard audit rows from recursively blocking future trades.
--
-- The execution engine now excludes security_guard_blocked_execution rows from
-- the unresolved critical-event count. Mark historical rows resolved too, so
-- accounts that were caught in the recursive block loop unlock after migration.

update public.security_logs
set
  resolved = true,
  resolved_at = coalesce(resolved_at, now()),
  metadata = coalesce(metadata, '{}'::jsonb)
    || jsonb_build_object(
      'auto_resolved_by_migration', '0030_resolve_recursive_execution_guard_logs',
      'auto_resolve_reason', 'guard audit row is not an underlying security incident'
    )
where event_type = 'security_guard_blocked_execution'
  and severity = 'critical'
  and resolved = false;
