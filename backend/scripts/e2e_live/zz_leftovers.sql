-- READ-ONLY: finds any row that still references a ZZTEST object, by walking every foreign key, plus text markers.
create temp table zz_fixed_assets as select id from fixed_assets where inv_number like 'ZZTEST-%';
create temp table zz_users        as select id from users where email like 'zztest-%@example.test';
create temp table zz_sections     as select id from sections where name like 'ZZTEST-%';
create temp table zz_employees    as select id from employees where tab_number like 'ZZTEST-%';
create temp table zz_work_orders  as select id from work_orders where fixed_asset_id in (select id from zz_fixed_assets) or description like 'ZZTEST%';
create temp table zz_maintenance_intervals as select id from maintenance_intervals where code like 'ZZTEST-%';
create temp table zz_maintenance_plan as select id from maintenance_plan where asset_id in (select id from zz_fixed_assets);
create temp table zz_maintenance_disruption as select id from maintenance_disruption where note like 'ZZTEST%';

select 'zz objects still present' as check_name,
  (select count(*) from zz_fixed_assets) as assets, (select count(*) from zz_users) as users,
  (select count(*) from zz_sections) as sections, (select count(*) from zz_employees) as employees,
  (select count(*) from zz_work_orders) as orders, (select count(*) from zz_maintenance_intervals) as intervals,
  (select count(*) from zz_maintenance_plan) as plans, (select count(*) from zz_maintenance_disruption) as disruptions;

select f.tbl, f.col, f.ref,
       (xpath('/row/n/text()', query_to_xml(format('select count(*) as n from %s where %I in (select id from zz_%s)', f.tbl, f.col, f.ref), false, true, '')))[1]::text::bigint as rows_referencing
from (
  select c.conrelid::regclass::text as tbl, a.attname as col, c.confrelid::regclass::text as ref
  from pg_constraint c join pg_attribute a on a.attrelid = c.conrelid and a.attnum = c.conkey[1]
  where c.contype = 'f' and array_length(c.conkey, 1) = 1
    and c.confrelid::regclass::text in ('fixed_assets','users','sections','employees','work_orders','maintenance_intervals','maintenance_plan','maintenance_disruption')
) f
where (xpath('/row/n/text()', query_to_xml(format('select count(*) as n from %s where %I in (select id from zz_%s)', f.tbl, f.col, f.ref), false, true, '')))[1]::text::bigint > 0
order by 4 desc;

select 'audit rows by ZZTEST users or about ZZTEST objects' as check_name,
  (select count(*) from audit_logs where actor_user_id in (select id from zz_users)
     or object_label ilike '%zztest%' or details::text ilike '%zztest%' or new_values::text ilike '%zztest%' or old_values::text ilike '%zztest%') as n;
select 'refresh tokens of ZZTEST users' as check_name, count(*) from refresh_tokens where user_id in (select id from zz_users);
select 'text markers: assets/orders/notes' as check_name,
  (select count(*) from fixed_assets where inv_number ilike '%zztest%') as assets,
  (select count(*) from work_orders where description ilike '%zztest%' or note ilike '%zztest%') as orders,
  (select count(*) from maintenance_plan where reschedule_reason ilike '%zztest%' or blocked_note ilike '%zztest%') as plans,
  (select count(*) from maintenance_decision where note ilike '%zztest%') as decisions,
  (select count(*) from asset_maintenance_baseline where note ilike '%zztest%') as baselines;
