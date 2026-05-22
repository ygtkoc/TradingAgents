-- Ensure backend services can manage Telegram account/session metadata.
--
-- RLS protects authenticated users, but the autonomous service uses the
-- service_role key and still needs table privileges on newly added tables.

GRANT SELECT, INSERT, UPDATE, DELETE ON public.telegram_accounts TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.telegram_signal_sources TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.telegram_signal_messages TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.telegram_chat_options TO service_role;

GRANT USAGE ON SCHEMA public TO service_role;
