-- Таблица видов работ (ТО-1, ТО-2, ТР-1 и т.д.)
CREATE TABLE IF NOT EXISTS public.work_types (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code        text NOT NULL UNIQUE,
  name        text NOT NULL,
  description text NOT NULL DEFAULT '',
  unit_type   text NOT NULL DEFAULT 'locomotive', -- locomotive или wagon
  sort_order  int NOT NULL DEFAULT 0,
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- Таблица подзадач для видов работ
CREATE TABLE IF NOT EXISTS public.work_subtasks (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  work_type_id  uuid NOT NULL REFERENCES public.work_types(id) ON DELETE CASCADE,
  name          text NOT NULL,
  description   text NOT NULL DEFAULT '',
  sort_order    int NOT NULL DEFAULT 0,
  created_at    timestamptz NOT NULL DEFAULT now()
);

-- Таблица шаблонов ТМЦ для видов работ
CREATE TABLE IF NOT EXISTS public.work_type_tmc (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  work_type_id  uuid NOT NULL REFERENCES public.work_types(id) ON DELETE CASCADE,
  name          text NOT NULL,
  inv_no        text NOT NULL DEFAULT '',
  unit          text NOT NULL DEFAULT 'шт.',
  qty           numeric NOT NULL DEFAULT 1,
  note          text NOT NULL DEFAULT '',
  sort_order    int NOT NULL DEFAULT 0,
  created_at    timestamptz NOT NULL DEFAULT now()
);

-- Индексы
CREATE INDEX IF NOT EXISTS idx_work_subtasks_work_type ON public.work_subtasks(work_type_id);
CREATE INDEX IF NOT EXISTS idx_work_type_tmc_work_type ON public.work_type_tmc(work_type_id);

-- RLS для work_types
ALTER TABLE public.work_types ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS work_types_select_anon ON public.work_types;
CREATE POLICY work_types_select_anon ON public.work_types FOR SELECT TO anon USING (true);

DROP POLICY IF EXISTS work_types_select_auth ON public.work_types;
CREATE POLICY work_types_select_auth ON public.work_types FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS work_types_insert_anon ON public.work_types;
CREATE POLICY work_types_insert_anon ON public.work_types FOR INSERT TO anon WITH CHECK (true);

DROP POLICY IF EXISTS work_types_insert_auth ON public.work_types;
CREATE POLICY work_types_insert_auth ON public.work_types FOR INSERT TO authenticated WITH CHECK (true);

DROP POLICY IF EXISTS work_types_update_anon ON public.work_types;
CREATE POLICY work_types_update_anon ON public.work_types FOR UPDATE TO anon USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS work_types_update_auth ON public.work_types;
CREATE POLICY work_types_update_auth ON public.work_types FOR UPDATE TO authenticated USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS work_types_delete_anon ON public.work_types;
CREATE POLICY work_types_delete_anon ON public.work_types FOR DELETE TO anon USING (true);

DROP POLICY IF EXISTS work_types_delete_auth ON public.work_types;
CREATE POLICY work_types_delete_auth ON public.work_types FOR DELETE TO authenticated USING (true);

-- RLS для work_subtasks
ALTER TABLE public.work_subtasks ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS work_subtasks_select_anon ON public.work_subtasks;
CREATE POLICY work_subtasks_select_anon ON public.work_subtasks FOR SELECT TO anon USING (true);

DROP POLICY IF EXISTS work_subtasks_select_auth ON public.work_subtasks;
CREATE POLICY work_subtasks_select_auth ON public.work_subtasks FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS work_subtasks_insert_anon ON public.work_subtasks;
CREATE POLICY work_subtasks_insert_anon ON public.work_subtasks FOR INSERT TO anon WITH CHECK (true);

DROP POLICY IF EXISTS work_subtasks_insert_auth ON public.work_subtasks;
CREATE POLICY work_subtasks_insert_auth ON public.work_subtasks FOR INSERT TO authenticated WITH CHECK (true);

DROP POLICY IF EXISTS work_subtasks_update_anon ON public.work_subtasks;
CREATE POLICY work_subtasks_update_anon ON public.work_subtasks FOR UPDATE TO anon USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS work_subtasks_update_auth ON public.work_subtasks;
CREATE POLICY work_subtasks_update_auth ON public.work_subtasks FOR UPDATE TO authenticated USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS work_subtasks_delete_anon ON public.work_subtasks;
CREATE POLICY work_subtasks_delete_anon ON public.work_subtasks FOR DELETE TO anon USING (true);

DROP POLICY IF EXISTS work_subtasks_delete_auth ON public.work_subtasks;
CREATE POLICY work_subtasks_delete_auth ON public.work_subtasks FOR DELETE TO authenticated USING (true);

-- RLS для work_type_tmc
ALTER TABLE public.work_type_tmc ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS work_type_tmc_select_anon ON public.work_type_tmc;
CREATE POLICY work_type_tmc_select_anon ON public.work_type_tmc FOR SELECT TO anon USING (true);

DROP POLICY IF EXISTS work_type_tmc_select_auth ON public.work_type_tmc;
CREATE POLICY work_type_tmc_select_auth ON public.work_type_tmc FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS work_type_tmc_insert_anon ON public.work_type_tmc;
CREATE POLICY work_type_tmc_insert_anon ON public.work_type_tmc FOR INSERT TO anon WITH CHECK (true);

DROP POLICY IF EXISTS work_type_tmc_insert_auth ON public.work_type_tmc;
CREATE POLICY work_type_tmc_insert_auth ON public.work_type_tmc FOR INSERT TO authenticated WITH CHECK (true);

DROP POLICY IF EXISTS work_type_tmc_update_anon ON public.work_type_tmc;
CREATE POLICY work_type_tmc_update_anon ON public.work_type_tmc FOR UPDATE TO anon USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS work_type_tmc_update_auth ON public.work_type_tmc;
CREATE POLICY work_type_tmc_update_auth ON public.work_type_tmc FOR UPDATE TO authenticated USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS work_type_tmc_delete_anon ON public.work_type_tmc;
CREATE POLICY work_type_tmc_delete_anon ON public.work_type_tmc FOR DELETE TO anon USING (true);

DROP POLICY IF EXISTS work_type_tmc_delete_auth ON public.work_type_tmc;
CREATE POLICY work_type_tmc_delete_auth ON public.work_type_tmc FOR DELETE TO authenticated USING (true);
