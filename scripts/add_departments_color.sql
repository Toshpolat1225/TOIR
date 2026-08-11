-- Добавить колонку color в departments, если её ещё нет (выполнить в Supabase SQL Editor)
ALTER TABLE public.departments
  ADD COLUMN IF NOT EXISTS color text NOT NULL DEFAULT '#3b82f6';
