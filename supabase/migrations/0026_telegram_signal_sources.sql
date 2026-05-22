-- Telegram signal ingestion foundation.
--
-- The listener runs server-side with service_role, records every received
-- message, parses it into a normalized payload, then inserts a regular
-- `signals` row. The agent/execution engines remain the only path to trades.

CREATE TABLE IF NOT EXISTS public.telegram_accounts (
  id                    uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id               uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  account_label         text NOT NULL,
  phone_hint            text,
  session_ciphertext    text,
  session_iv            text,
  connection_status     text NOT NULL DEFAULT 'pending'
    CHECK (connection_status IN ('pending', 'connected', 'paused', 'error', 'revoked')),
  last_error            text,
  last_connected_at     timestamptz,
  metadata              jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at            timestamptz NOT NULL DEFAULT NOW(),
  updated_at            timestamptz NOT NULL DEFAULT NOW()
);

CREATE TRIGGER telegram_accounts_updated_at
  BEFORE UPDATE ON public.telegram_accounts
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TABLE IF NOT EXISTS public.telegram_signal_sources (
  id                         uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id                    uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  bot_id                     uuid NOT NULL REFERENCES public.bots(id) ON DELETE CASCADE,
  telegram_account_id        uuid REFERENCES public.telegram_accounts(id) ON DELETE SET NULL,
  chat_id                    text NOT NULL,
  chat_title                 text,
  exchange                   text NOT NULL DEFAULT 'binance',
  enabled                    boolean NOT NULL DEFAULT true,
  execution_policy           text NOT NULL DEFAULT 'approval_required'
    CHECK (execution_policy IN ('observe', 'paper', 'approval_required', 'auto')),
  require_stop_loss          boolean NOT NULL DEFAULT true,
  max_signal_age_minutes     integer NOT NULL DEFAULT 10 CHECK (max_signal_age_minutes BETWEEN 1 AND 1440),
  min_parse_confidence       numeric(4,3) NOT NULL DEFAULT 0.700
    CHECK (min_parse_confidence BETWEEN 0 AND 1),
  max_leverage               numeric(8,2),
  default_leverage           numeric(8,2),
  symbol_allowlist           text[] NOT NULL DEFAULT '{}',
  metadata                   jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at                 timestamptz NOT NULL DEFAULT NOW(),
  updated_at                 timestamptz NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, bot_id, chat_id)
);

CREATE TRIGGER telegram_signal_sources_updated_at
  BEFORE UPDATE ON public.telegram_signal_sources
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TABLE IF NOT EXISTS public.telegram_signal_messages (
  id                    uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  source_id             uuid NOT NULL REFERENCES public.telegram_signal_sources(id) ON DELETE CASCADE,
  user_id               uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  telegram_message_id   text NOT NULL,
  raw_text              text NOT NULL,
  normalized_signal     jsonb NOT NULL DEFAULT '{}'::jsonb,
  parse_status          text NOT NULL DEFAULT 'pending'
    CHECK (parse_status IN ('pending', 'parsed', 'ignored', 'rejected', 'signal_created', 'failed')),
  parse_error           text,
  signal_id             uuid REFERENCES public.signals(id) ON DELETE SET NULL,
  received_at           timestamptz NOT NULL,
  created_at            timestamptz NOT NULL DEFAULT NOW(),
  updated_at            timestamptz NOT NULL DEFAULT NOW(),
  UNIQUE (source_id, telegram_message_id)
);

CREATE TRIGGER telegram_signal_messages_updated_at
  BEFORE UPDATE ON public.telegram_signal_messages
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE INDEX IF NOT EXISTS idx_telegram_sources_user
  ON public.telegram_signal_sources(user_id, enabled);

CREATE INDEX IF NOT EXISTS idx_telegram_sources_chat
  ON public.telegram_signal_sources(chat_id)
  WHERE enabled = true;

CREATE INDEX IF NOT EXISTS idx_telegram_messages_source_created
  ON public.telegram_signal_messages(source_id, created_at DESC);

ALTER TABLE public.telegram_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.telegram_signal_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.telegram_signal_messages ENABLE ROW LEVEL SECURITY;

CREATE POLICY "telegram_accounts_select_own"
  ON public.telegram_accounts FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR public.is_admin());

CREATE POLICY "telegram_sources_select_own"
  ON public.telegram_signal_sources FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR public.is_admin());

CREATE POLICY "telegram_messages_select_own"
  ON public.telegram_signal_messages FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR public.is_admin());

-- Source configuration does not grant trading authority by itself; the
-- server-side listener still validates bot ownership and creates only signals.
CREATE POLICY "telegram_sources_insert_own"
  ON public.telegram_signal_sources FOR INSERT TO authenticated
  WITH CHECK (
    user_id = auth.uid()
    AND EXISTS (
      SELECT 1 FROM public.bots b
      WHERE b.id = bot_id
        AND b.user_id = auth.uid()
    )
  );

CREATE POLICY "telegram_sources_update_own"
  ON public.telegram_signal_sources FOR UPDATE TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (
    user_id = auth.uid()
    AND EXISTS (
      SELECT 1 FROM public.bots b
      WHERE b.id = bot_id
        AND b.user_id = auth.uid()
    )
  );

CREATE POLICY "telegram_sources_delete_own"
  ON public.telegram_signal_sources FOR DELETE TO authenticated
  USING (user_id = auth.uid());

GRANT SELECT ON public.telegram_accounts TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.telegram_signal_sources TO authenticated;
GRANT SELECT ON public.telegram_signal_messages TO authenticated;

COMMENT ON TABLE public.telegram_signal_sources IS
  'User-selected Telegram chats that may feed normalized external signals into the agent pipeline.';

COMMENT ON TABLE public.telegram_signal_messages IS
  'Immutable-ish audit inbox for Telegram messages and parser outcomes before signal creation.';
