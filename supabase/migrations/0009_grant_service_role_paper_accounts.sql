-- Migration 0009 — Grant service_role access to paper trading tables
--
-- The Python backend workers authenticate with SUPABASE_SERVICE_ROLE_KEY and
-- query public.paper_accounts on startup. Migration 0007 created the tables
-- and RLS policies, but did not grant table privileges to the Postgres
-- service_role role. That causes PostgREST /rest/v1 requests signed with a
-- valid service_role JWT to fail with:
--   code 42501 / permission denied for table paper_accounts
--
-- This migration grants the backend role the explicit table privileges it
-- needs. RLS remains enabled; service_role bypasses RLS by design.

begin;

grant usage on schema public to service_role;

grant select, insert, update, delete
    on table public.paper_accounts
    to service_role;

grant select, insert, update, delete
    on table public.paper_account_events
    to service_role;

commit;
