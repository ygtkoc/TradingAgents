-- Per-source Telegram message template matching.
--
-- Users can paste an example signal from a selected group/topic. The listener
-- uses it as a format fingerprint before creating trade signals.

ALTER TABLE public.telegram_signal_sources
  ADD COLUMN IF NOT EXISTS signal_template text,
  ADD COLUMN IF NOT EXISTS template_similarity_threshold numeric(4,3) NOT NULL DEFAULT 0.650
    CHECK (template_similarity_threshold BETWEEN 0 AND 1);

COMMENT ON COLUMN public.telegram_signal_sources.signal_template IS
  'Optional example Telegram signal text used to accept only similar incoming messages for this source.';

COMMENT ON COLUMN public.telegram_signal_sources.template_similarity_threshold IS
  'Minimum 0..1 similarity score required when signal_template is set.';
