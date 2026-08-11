-- ═══════════════════════════════════════════════════════
-- Таблица profiles (роли пользователей)
-- Выполнить в Supabase SQL Editor
-- ═══════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS public.profiles (
  id          uuid references auth.users on delete cascade primary key,
  full_name   text not null default '',
  email       text not null default '',
  role        text not null default 'master' check (role in ('admin', 'operator', 'master')),
  section     text not null default '',
  created_at  timestamptz not null default now()
);

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

-- Простые открытые политики (внутренняя система)
CREATE POLICY "profiles_all" ON public.profiles
  FOR ALL USING (true) WITH CHECK (true);

-- ───────────────────────────────────────────
-- Триггер: автосоздание профиля при регистрации
-- ───────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  INSERT INTO public.profiles (id, full_name, email, role, section)
  VALUES (
    NEW.id,
    COALESCE(NEW.raw_user_meta_data->>'full_name', split_part(NEW.email, '@', 1)),
    COALESCE(NEW.email, ''),
    COALESCE(NEW.raw_user_meta_data->>'role', 'master'),
    COALESCE(NEW.raw_user_meta_data->>'section', '')
  )
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE PROCEDURE public.handle_new_user();
