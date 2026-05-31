-- =============================================================================
-- Migration 0039 - Backfill source metadata into knowledge chunks
-- =============================================================================

BEGIN;

UPDATE public.trading_knowledge_chunks AS chunk
SET metadata = COALESCE(chunk.metadata, '{}'::jsonb)
  || jsonb_build_object(
    'source_title', source.title,
    'source_metadata', source.metadata
  )
FROM public.trading_knowledge_sources AS source
WHERE chunk.source_id = source.id
  AND (
    chunk.metadata->'source_metadata' IS NULL
    OR chunk.metadata->>'source_title' IS NULL
  );

COMMIT;
