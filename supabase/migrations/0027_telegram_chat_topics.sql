-- Website-driven Telegram channel/topic selection.

ALTER TABLE public.telegram_signal_sources
  ADD COLUMN IF NOT EXISTS topic_id text,
  ADD COLUMN IF NOT EXISTS topic_title text;

ALTER TABLE public.telegram_signal_sources
  DROP CONSTRAINT IF EXISTS telegram_signal_sources_user_id_bot_id_chat_id_key;

CREATE UNIQUE INDEX IF NOT EXISTS idx_telegram_sources_unique_chat_topic
  ON public.telegram_signal_sources(user_id, bot_id, chat_id, COALESCE(topic_id, ''));

CREATE TABLE IF NOT EXISTS public.telegram_chat_options (
  id                    uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id               uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  telegram_account_id   uuid REFERENCES public.telegram_accounts(id) ON DELETE CASCADE,
  chat_id               text NOT NULL,
  chat_title            text NOT NULL,
  chat_type             text NOT NULL DEFAULT 'group',
  has_topics            boolean NOT NULL DEFAULT false,
  topic_id              text,
  topic_title           text,
  metadata              jsonb NOT NULL DEFAULT '{}'::jsonb,
  discovered_at         timestamptz NOT NULL DEFAULT NOW(),
  updated_at            timestamptz NOT NULL DEFAULT NOW()
);

CREATE TRIGGER telegram_chat_options_updated_at
  BEFORE UPDATE ON public.telegram_chat_options
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE INDEX IF NOT EXISTS idx_telegram_chat_options_user_account
  ON public.telegram_chat_options(user_id, telegram_account_id, chat_title);

CREATE UNIQUE INDEX IF NOT EXISTS idx_telegram_chat_options_unique_chat_topic
  ON public.telegram_chat_options(user_id, telegram_account_id, chat_id, COALESCE(topic_id, ''));

ALTER TABLE public.telegram_chat_options ENABLE ROW LEVEL SECURITY;

CREATE POLICY "telegram_chat_options_select_own"
  ON public.telegram_chat_options FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR public.is_admin());

GRANT SELECT ON public.telegram_chat_options TO authenticated;

COMMENT ON COLUMN public.telegram_signal_sources.topic_id IS
  'Optional Telegram forum topic/thread id. Null means read the whole chat.';
