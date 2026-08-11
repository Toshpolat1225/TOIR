-- ═══════════════════════════════════════════
-- ТАБЛИЦА: sections (Участки)
-- Скопируйте и выполните в Supabase: Dashboard → SQL Editor → New query → Run
-- ═══════════════════════════════════════════

CREATE TABLE IF NOT EXISTS public.sections (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name       text NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.sections ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "sections_all" ON public.sections;
CREATE POLICY "sections_all" ON public.sections
  FOR ALL USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_sections_name ON public.sections (name);
