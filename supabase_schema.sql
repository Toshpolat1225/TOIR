-- ═══════════════════════════════════════════
-- ТАБЛИЦА: work_orders (Наряд-заказы)
-- ═══════════════════════════════════════════
create table if not exists work_orders (
  id           text primary key,
  unit_type    text not null default 'locomotive',
  unit         text not null default '',
  depot        text not null default '',
  section      text not null default '',
  equipment    text not null default '',
  work_type    text not null default '',
  repair_kind  text not null default '',
  status       text not null default 'pending',
  priority     text not null default 'normal',
  tech         text not null default '',
  chief        text not null default '',
  description  text not null default '',
  note         text not null default '',
  created      text not null default '',
  closed       text not null default '—',
  repair_items jsonb not null default '[]',
  date_start   text not null default '',
  date_end     text not null default '',
  created_at   timestamptz not null default now()
);

alter table work_orders enable row level security;
create policy "public read"  on work_orders for select using (true);
create policy "public insert" on work_orders for insert with check (true);
create policy "public update" on work_orders for update using (true);
create policy "public delete" on work_orders for delete using (true);

-- ═══════════════════════════════════════════
-- ТАБЛИЦА: fixed_assets (Основные средства)
-- ═══════════════════════════════════════════
create table if not exists fixed_assets (
  id           text primary key,
  name         text not null default '',
  asset_type   text not null default 'locomotive',
  series       text not null default '',
  depot        text not null default '',
  status       text not null default 'operational',
  comm_date    text not null default '',
  year_built   text not null default '',
  mileage      text not null default '0',
  last_maint   text not null default '—',
  next_maint   text not null default '—',
  inv_number   text not null default '',
  initial_cost text not null default '',
  owner        text not null default '',
  created_at   timestamptz not null default now()
);

alter table fixed_assets enable row level security;
create policy "public read"   on fixed_assets for select using (true);
create policy "public insert" on fixed_assets for insert with check (true);
create policy "public update" on fixed_assets for update using (true);
create policy "public delete" on fixed_assets for delete using (true);

-- ═══════════════════════════════════════════
-- ТАБЛИЦА: tmc_documents (ТМЦ документы)
-- ═══════════════════════════════════════════
create table if not exists tmc_documents (
  id            text primary key,
  doc_no        text not null default '',
  date          text not null default '',
  work_order_id text not null default '',
  loco          text not null default '',
  work_type     text not null default '',
  depot         text not null default '',
  warehouse     text not null default '',
  issued_by     text not null default '',
  accepted_by   text not null default '',
  chief         text not null default '',
  status        text not null default 'draft',
  items         jsonb not null default '[]',
  created_at    timestamptz not null default now()
);

alter table tmc_documents enable row level security;
create policy "public read"   on tmc_documents for select using (true);
create policy "public insert" on tmc_documents for insert with check (true);
create policy "public update" on tmc_documents for update using (true);
create policy "public delete" on tmc_documents for delete using (true);
