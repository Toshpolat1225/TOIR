-- ═══════════════════════════════════════════════════════════════════
-- ТАБЛИЦЫ: departments (участки с цветом), nomenclature (номенклатура)
-- Выполнить в Supabase SQL Editor
-- ═══════════════════════════════════════════════════════════════════

-- Участки/депо с цветовым акцентом для UI
CREATE TABLE IF NOT EXISTS public.departments (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name       text NOT NULL UNIQUE,
  color      text NOT NULL DEFAULT '#3b82f6',
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.departments ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "departments_all" ON public.departments;
DROP POLICY IF EXISTS "departments_insert" ON public.departments;
DROP POLICY IF EXISTS "departments_select_anon" ON public.departments;
DROP POLICY IF EXISTS "departments_insert_anon" ON public.departments;
CREATE POLICY "departments_all" ON public.departments
  FOR ALL USING (true) WITH CHECK (true);
-- Для приложения (anon/authenticated): SELECT нужен после INSERT ... .select("id")
CREATE POLICY "departments_select_anon" ON public.departments FOR SELECT TO anon USING (true);
CREATE POLICY "departments_select_auth" ON public.departments FOR SELECT TO authenticated USING (true);
CREATE POLICY "departments_insert_anon" ON public.departments FOR INSERT TO anon WITH CHECK (true);
CREATE POLICY "departments_insert_auth" ON public.departments FOR INSERT TO authenticated WITH CHECK (true);

-- Номенклатура запчастей по участкам
CREATE TABLE IF NOT EXISTS public.nomenclature (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  department_id uuid NOT NULL REFERENCES public.departments(id) ON DELETE CASCADE,
  name          text NOT NULL,
  code          text NOT NULL DEFAULT '',
  unit          text NOT NULL DEFAULT 'шт.',
  extra         jsonb NOT NULL DEFAULT '{}',
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (department_id, name)
);

ALTER TABLE public.nomenclature ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "nomenclature_all" ON public.nomenclature;
DROP POLICY IF EXISTS "nomenclature_insert" ON public.nomenclature;
DROP POLICY IF EXISTS "nomenclature_select_anon" ON public.nomenclature;
DROP POLICY IF EXISTS "nomenclature_insert_anon" ON public.nomenclature;
CREATE POLICY "nomenclature_all" ON public.nomenclature
  FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "nomenclature_select_anon" ON public.nomenclature FOR SELECT TO anon USING (true);
CREATE POLICY "nomenclature_select_auth" ON public.nomenclature FOR SELECT TO authenticated USING (true);
CREATE POLICY "nomenclature_insert_anon" ON public.nomenclature FOR INSERT TO anon WITH CHECK (true);
CREATE POLICY "nomenclature_insert_auth" ON public.nomenclature FOR INSERT TO authenticated WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_nomenclature_department ON public.nomenclature (department_id);
CREATE INDEX IF NOT EXISTS idx_nomenclature_name ON public.nomenclature (name);

-- Синхронизация с sections: при необходимости можно заполнить sections из departments
-- INSERT INTO sections (name) SELECT name FROM departments ON CONFLICT (name) DO NOTHING;
