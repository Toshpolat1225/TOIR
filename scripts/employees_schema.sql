-- Таблица работников (справочник)
CREATE TABLE IF NOT EXISTS public.employees (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tab_number  text NOT NULL,
  full_name   text NOT NULL,
  position    text NOT NULL DEFAULT '',
  section_id  uuid REFERENCES public.sections(id) ON DELETE SET NULL,
  location_id uuid REFERENCES public.sections(id) ON DELETE SET NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tab_number)
);

-- Индексы
CREATE INDEX IF NOT EXISTS idx_employees_section ON public.employees(section_id);
CREATE INDEX IF NOT EXISTS idx_employees_location ON public.employees(location_id);
CREATE INDEX IF NOT EXISTS idx_employees_tab_number ON public.employees(tab_number);

-- RLS
ALTER TABLE public.employees ENABLE ROW LEVEL SECURITY;

-- Политики для SELECT
DROP POLICY IF EXISTS employees_select_anon ON public.employees;
CREATE POLICY employees_select_anon ON public.employees FOR SELECT TO anon USING (true);

DROP POLICY IF EXISTS employees_select_auth ON public.employees;
CREATE POLICY employees_select_auth ON public.employees FOR SELECT TO authenticated USING (true);

-- Политики для INSERT
DROP POLICY IF EXISTS employees_insert_anon ON public.employees;
CREATE POLICY employees_insert_anon ON public.employees FOR INSERT TO anon WITH CHECK (true);

DROP POLICY IF EXISTS employees_insert_auth ON public.employees;
CREATE POLICY employees_insert_auth ON public.employees FOR INSERT TO authenticated WITH CHECK (true);

-- Политики для UPDATE
DROP POLICY IF EXISTS employees_update_anon ON public.employees;
CREATE POLICY employees_update_anon ON public.employees FOR UPDATE TO anon USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS employees_update_auth ON public.employees;
CREATE POLICY employees_update_auth ON public.employees FOR UPDATE TO authenticated USING (true) WITH CHECK (true);

-- Политики для DELETE
DROP POLICY IF EXISTS employees_delete_anon ON public.employees;
CREATE POLICY employees_delete_anon ON public.employees FOR DELETE TO anon USING (true);

DROP POLICY IF EXISTS employees_delete_auth ON public.employees;
CREATE POLICY employees_delete_auth ON public.employees FOR DELETE TO authenticated USING (true);
