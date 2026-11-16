\pset format aligned
\echo '=== 1. assets: structure ==='
select asset_type, count(*) total,
  count(*) filter (where section_id is null) no_section,
  count(*) filter (where model_id is null) no_model,
  count(*) filter (where status <> 'operational') not_operational,
  count(*) filter (where inv_number ilike 'zztest%') zztest
from fixed_assets group by 1 order by 2 desc;
\echo '--- duplicate inventory numbers ignoring leading zeros/case/spaces'
select ltrim(upper(replace(inv_number,' ','')),'0') norm, count(*) n, string_agg(inv_number, ', ') from fixed_assets group by 1 having count(*) > 1 order by 2 desc limit 8;
\echo '--- mileage outliers'
select count(*) filter (where mileage < 0) negative, count(*) filter (where mileage > 3000000) over_3m_km, max(mileage) max_mileage from fixed_assets;
\echo '--- wagons: mileage without an approved opening (must be 0) / approved opening but zero mileage'
select count(*) filter (where a.mileage > 0 and not exists (select 1 from wagon_mileage_opening_balances o where o.asset_id=a.id and o.status='approved')) mileage_without_opening,
       count(*) filter (where a.mileage = 0 and exists (select 1 from wagon_mileage_opening_balances o where o.asset_id=a.id and o.status='approved')) opening_but_zero
from fixed_assets a where asset_type='wagon' and inv_number not ilike 'zztest%';
\echo '=== 2. mileage_history anomalies (locomotives/diesels, last 30 days) ==='
with s as (select asset_id, mileage, recorded_at, lag(mileage) over (partition by asset_id order by recorded_at) prev from mileage_history where recorded_at > now() - interval '30 days')
select count(*) filter (where mileage < prev) decreases, count(*) filter (where mileage - prev > 200) jumps_over_200km,
       count(*) filter (where mileage - prev > 1000) jumps_over_1000km, max(mileage - prev) biggest_jump from s;
\echo '=== 3. Wialon / GTK ==='
select count(*) units, count(*) filter (where last_message_at < now() - interval '24 hours') silent_24h, count(*) filter (where last_message_at is null) never_seen, count(*) filter (where suspect_absolute) suspect from wialon_units;
select (select count(*) from wialon_units u where not exists (select 1 from asset_source_links l where l.source='wialon' and l.external_id=u.unit_id and l.status='active')) wialon_units_not_linked,
       (select count(*) from asset_source_links where status='active') active_links,
       (select count(*) from asset_conflicts where status='pending') pending_conflicts;
select status, count(*) from wialon_counter_state group by 1;
select left(coalesce(reason, 'n/a'), 50) reason, count(*) from wialon_rejected_readings group by 1 order by 2 desc limit 5;
\echo '=== 4. maintenance model ==='
select status, count(*) from maintenance_plan group by 1 order by 2 desc;
select i.code, count(*) plans from maintenance_plan p join maintenance_intervals i on i.id=p.interval_id where p.status in ('scheduled','blocked','in_progress') group by 1 order by 2 desc;
select 'real (non-test) open plans' k, count(*) from maintenance_plan p join maintenance_intervals i on i.id=p.interval_id where i.code <> 'test' and p.status in ('scheduled','blocked','in_progress');
select 'baselines (real last-service data)' k, count(*) from asset_maintenance_baseline where source <> 'provisional';
select 'plans with trigger not on the interval grid (stale)' k, count(*) from maintenance_plan p join maintenance_intervals i on i.id=p.interval_id where p.status='scheduled' and p.trigger_mileage is not null and i.interval_km is not null and (p.trigger_mileage % i.interval_km) <> 0;
select 'overdue open plans (scheduled_date in the past)' k, count(*) from maintenance_plan where status='scheduled' and scheduled_date < current_date;
select 'work orders ever created' k, count(*) from work_orders;
\echo '=== 5. people and reference data ==='
select role, is_active, auth_source, count(*) from users where email not like 'zztest-%' and coalesce(ad_username,'') not like 'zztest.%' group by 1,2,3 order by 1,2;
select 'employees', count(*) filter (where full_name ilike 'demo%') demo, count(*) total from employees where tab_number not like 'ZZTEST%';
select name from sections where name not like 'ZZTEST%' order by name;
select 'users that never logged in', count(*) from users where last_login_at is null and email not like 'zztest-%';
select 'demo-like names in users', count(*) from users where full_name ilike '%demo%' or email ilike '%demo%' or email ilike '%example%' and email not like 'zztest-%';
\echo '=== 6. audit_logs: where the volume comes from (last 24 h) ==='
select module, action, actor_type, count(*) from audit_logs where created_at > now() - interval '24 hours' group by 1,2,3 order by 4 desc limit 8;
select route, count(*) from audit_logs where created_at > now() - interval '24 hours' group by 1 order by 2 desc limit 6;
select 'oldest audit row' k, min(created_at)::text from audit_logs;
\echo '=== 7. housekeeping: expired/unused rows that are never purged ==='
select 'refresh_tokens total / expired / revoked' k, count(*) total, count(*) filter (where expires_at < now()) expired, count(*) filter (where revoked_at is not null) revoked from refresh_tokens;
select 'login_attempts rows / older than 1 day' k, count(*), count(*) filter (where failed_at < now() - interval '1 day') from login_attempts;
select 'wialon_raw_receipts older than 7 days' k, count(*) from wialon_raw_receipts where received_at < now() - interval '7 days';
