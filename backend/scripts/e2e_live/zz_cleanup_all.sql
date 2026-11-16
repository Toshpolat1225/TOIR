-- FINAL CLEANUP of the live end-to-end run. One transaction: either everything ZZTEST disappears or nothing changes.
-- Only rows that are provably the run's own are touched: names / numbers / e-mails starting with ZZTEST, and the
-- audit rows written by or about those objects. Prints how many rows each step removed.
\set ON_ERROR_STOP on
begin;
create temp table zz_users        on commit drop as select id from users where email like 'zztest-%@example.test' or ad_username like 'zztest.%';
create temp table zz_sections     on commit drop as select id from sections where name like 'ZZTEST-%';
create temp table zz_departments  on commit drop as select id from departments where name ilike 'zztest-%';
create temp table zz_employees    on commit drop as select id from employees where tab_number like 'ZZTEST-%';
create temp table zz_intervals    on commit drop as select id from maintenance_intervals where code like 'ZZTEST-%';
create temp table zz_assets       on commit drop as select id from fixed_assets where inv_number like 'ZZTEST-%';
create temp table zz_orders       on commit drop as select id from work_orders where fixed_asset_id in (select id from zz_assets) or description like 'ZZTEST%' or executor_id in (select id from zz_employees);
create temp table zz_plans        on commit drop as select id from maintenance_plan where asset_id in (select id from zz_assets) or interval_id in (select id from zz_intervals);
create temp table zz_disruptions  on commit drop as select id from maintenance_disruption where note like 'ZZTEST%' or asset_id in (select id from zz_assets) or section_id in (select id from zz_sections) or created_by in (select id from zz_users);
create temp table zz_openings     on commit drop as select id from wagon_mileage_opening_balances where asset_id in (select id from zz_assets);
create temp table zz_work_types   on commit drop as select id from work_types where code like 'ZZT%' and name like 'ZZTEST%';
create temp table zz_nomenclature on commit drop as select id from nomenclature where name like 'ZZTEST%';
create temp table zz_norms        on commit drop as select id from nomenclature_norms where nomenclature_id in (select id from zz_nomenclature) or work_type_id in (select id from zz_work_types);
create temp table zz_all_ids      on commit drop as
  select id::text as id from zz_users union all select id::text from zz_sections union all select id::text from zz_departments
  union all select id::text from zz_employees union all select id::text from zz_intervals union all select id::text from zz_assets
  union all select id::text from zz_orders union all select id::text from zz_plans union all select id::text from zz_disruptions
  union all select id::text from zz_openings union all select id::text from zz_work_types union all select id::text from zz_nomenclature
  union all select id::text from zz_norms;

\echo '--- audit rows written by or about ZZTEST objects'
with d as (delete from audit_logs where actor_user_id in (select id from zz_users) or object_id in (select id from zz_all_ids)
              or actor_name ilike '%zztest%' or object_label ilike '%zztest%'
              or details::text ilike '%zztest%' or new_values::text ilike '%zztest%' or old_values::text ilike '%zztest%'
           returning 1) select 'audit_logs' t, count(*) from d;
with d as (delete from permission_audit where actor_user_id in (select id from zz_users) returning 1) select 'permission_audit' t, count(*) from d;

\echo '--- maintenance data'
with d as (delete from maintenance_decision where plan_id in (select id from zz_plans) returning 1) select 'maintenance_decision' t, count(*) from d;
with d as (delete from maintenance_plan where id in (select id from zz_plans) returning 1) select 'maintenance_plan' t, count(*) from d;
with d as (delete from asset_maintenance_baseline where asset_id in (select id from zz_assets) or interval_id in (select id from zz_intervals) returning 1) select 'asset_maintenance_baseline' t, count(*) from d;
with d as (delete from asset_meter_daily where asset_id in (select id from zz_assets) returning 1) select 'asset_meter_daily' t, count(*) from d;
with d as (delete from maintenance_disruption where id in (select id from zz_disruptions) returning 1) select 'maintenance_disruption' t, count(*) from d;

\echo '--- work orders and everything that hangs off them (found through the foreign keys)'
do $$
declare r record; n bigint; total bigint := 0;
begin
  for r in select c.conrelid::regclass::text as tbl, a.attname as col
           from pg_constraint c join pg_attribute a on a.attrelid = c.conrelid and a.attnum = c.conkey[1]
           where c.contype = 'f' and c.confrelid = 'work_orders'::regclass and array_length(c.conkey, 1) = 1 loop
    execute format('delete from %s where %I in (select id from zz_orders)', r.tbl, r.col);
    get diagnostics n = row_count; total := total + n;
  end loop;
  raise notice 'work-order dependants removed: %', total;
end $$;
with d as (delete from work_orders where id in (select id from zz_orders) returning 1) select 'work_orders' t, count(*) from d;

\echo '--- reference data'
with d as (delete from nomenclature_norms where id in (select id from zz_norms) returning 1) select 'nomenclature_norms' t, count(*) from d;
with d as (delete from nomenclature where id in (select id from zz_nomenclature) returning 1) select 'nomenclature' t, count(*) from d;
with d as (delete from work_types where id in (select id from zz_work_types) returning 1) select 'work_types' t, count(*) from d;
with d as (delete from maintenance_intervals where id in (select id from zz_intervals) returning 1) select 'maintenance_intervals' t, count(*) from d;
with d as (delete from employees where id in (select id from zz_employees) returning 1) select 'employees' t, count(*) from d;

\echo '--- assets'
with d as (delete from wagon_mileage_ledger where wagon_asset_id in (select id from zz_assets) returning 1) select 'wagon_mileage_ledger' t, count(*) from d;
with d as (delete from wagon_mileage_opening_balances where id in (select id from zz_openings) returning 1) select 'wagon_mileage_opening_balances' t, count(*) from d;
with d as (delete from asset_source_links where asset_id in (select id from zz_assets) returning 1) select 'asset_source_links' t, count(*) from d;
with d as (delete from mileage_history where asset_id in (select id from zz_assets) returning 1) select 'mileage_history' t, count(*) from d;
with d as (delete from asset_field_changes where asset_id in (select id from zz_assets) returning 1) select 'asset_field_changes' t, count(*) from d;
with d as (delete from fixed_assets where id in (select id from zz_assets) returning 1) select 'fixed_assets' t, count(*) from d;

\echo '--- identities'
with d as (delete from refresh_tokens where user_id in (select id from zz_users) returning 1) select 'refresh_tokens' t, count(*) from d;
with d as (delete from users where id in (select id from zz_users) returning 1) select 'users' t, count(*) from d;
with d as (delete from sections where id in (select id from zz_sections) returning 1) select 'sections' t, count(*) from d;
with d as (delete from departments where id in (select id from zz_departments) returning 1) select 'departments' t, count(*) from d;
commit;
