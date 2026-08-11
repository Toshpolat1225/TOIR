-- ═══════════════════════════════════════════════════════════════════
-- Исправление RLS: разрешить INSERT в departments и nomenclature
-- для ролей anon и authenticated (приложение с anon key).
-- Выполнить в Supabase → SQL Editor → New query → Run
-- ═══════════════════════════════════════════════════════════════════

-- departments: SELECT нужен после INSERT ... .select("id")
DROP POLICY IF EXISTS "departments_insert" ON public.departments;
DROP POLICY IF EXISTS "departments_select_anon" ON public.departments;
DROP POLICY IF EXISTS "departments_insert_anon" ON public.departments;
DROP POLICY IF EXISTS "departments_select_auth" ON public.departments;
DROP POLICY IF EXISTS "departments_insert_auth" ON public.departments;

CREATE POLICY "departments_select_anon" ON public.departments FOR SELECT TO anon USING (true);
CREATE POLICY "departments_select_auth" ON public.departments FOR SELECT TO authenticated USING (true);
CREATE POLICY "departments_insert_anon" ON public.departments FOR INSERT TO anon WITH CHECK (true);
CREATE POLICY "departments_insert_auth" ON public.departments FOR INSERT TO authenticated WITH CHECK (true);

-- nomenclature
DROP POLICY IF EXISTS "nomenclature_insert" ON public.nomenclature;
DROP POLICY IF EXISTS "nomenclature_select_anon" ON public.nomenclature;
DROP POLICY IF EXISTS "nomenclature_insert_anon" ON public.nomenclature;
DROP POLICY IF EXISTS "nomenclature_select_auth" ON public.nomenclature;
DROP POLICY IF EXISTS "nomenclature_insert_auth" ON public.nomenclature;
DROP POLICY IF EXISTS "nomenclature_update_anon" ON public.nomenclature;
DROP POLICY IF EXISTS "nomenclature_update_auth" ON public.nomenclature;
DROP POLICY IF EXISTS "nomenclature_delete_anon" ON public.nomenclature;
DROP POLICY IF EXISTS "nomenclature_delete_auth" ON public.nomenclature;

CREATE POLICY "nomenclature_select_anon" ON public.nomenclature FOR SELECT TO anon USING (true);
CREATE POLICY "nomenclature_select_auth" ON public.nomenclature FOR SELECT TO authenticated USING (true);
CREATE POLICY "nomenclature_insert_anon" ON public.nomenclature FOR INSERT TO anon WITH CHECK (true);
CREATE POLICY "nomenclature_insert_auth" ON public.nomenclature FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "nomenclature_update_anon" ON public.nomenclature FOR UPDATE TO anon USING (true) WITH CHECK (true);
CREATE POLICY "nomenclature_update_auth" ON public.nomenclature FOR UPDATE TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "nomenclature_delete_anon" ON public.nomenclature FOR DELETE TO anon USING (true);
CREATE POLICY "nomenclature_delete_auth" ON public.nomenclature FOR DELETE TO authenticated USING (true);
