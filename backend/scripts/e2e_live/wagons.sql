\echo '--- 1. wagons: the gate vs the projection'
select
  count(*)                                                        as wagons,
  count(*) filter (where a.mileage > 0)                           as with_mileage,
  count(*) filter (where exists (select 1 from wagon_mileage_opening_balances o where o.asset_id=a.id and o.status='approved')) as approved_opening,
  count(*) filter (where exists (select 1 from wagon_mileage_ledger l where l.wagon_asset_id=a.id and l.status='active' and l.calculation_eligible and l.classification in ('CONFIRMED','ESTIMATED'))) as eligible_ledger,
  count(*) filter (where exists (select 1 from wagon_mileage_ledger l where l.wagon_asset_id=a.id and l.status='active' and l.calculation_eligible and l.classification='CONFIRMED')) as passes_current_gate
from fixed_assets a where a.asset_type='wagon';

\echo '--- 2. wagons with mileage: sum / percentiles'
select count(*) n, round(sum(mileage)) total_km,
  round(percentile_cont(0.5) within group (order by mileage)::numeric,1) p50,
  round(percentile_cont(0.9) within group (order by mileage)::numeric,1) p90,
  max(mileage) mx
from fixed_assets where asset_type='wagon' and mileage>0;

\echo '--- 3. pace from the ledger: wagon-days with km in the last 30 days'
with seg as (
  select l.wagon_asset_id w, date(l.period_from) d, sum(l.distance_km) km
  from wagon_mileage_ledger l
  where l.status='active' and l.calculation_eligible and l.classification in ('CONFIRMED','ESTIMATED')
    and l.period_from > now() - interval '30 days'
  group by 1,2),
per as (select w, count(*) days_with_km, sum(km) total_km, max(km) best_day from seg group by 1)
select count(*) wagons_with_ledger_motion,
  round(percentile_cont(0.5) within group (order by total_km)::numeric,1) median_total_km,
  round(max(total_km),1) max_total_km,
  round(percentile_cont(0.5) within group (order by days_with_km)::numeric,1) median_days_with_km
from per;

\echo '--- 4. ledger time span'
select min(period_from) first_period, max(period_to) last_period, count(*) rows_all,
       count(*) filter (where status='active' and calculation_eligible) active_eligible
from wagon_mileage_ledger;

\echo '--- 5. wagon mileage_history / snapshots (the planner pace source)'
select count(distinct h.asset_id) wagons_with_history, count(*) rows
from mileage_history h join fixed_assets a on a.id=h.asset_id where a.asset_type='wagon';
select count(*) wagon_snapshots from asset_meter_daily s join fixed_assets a on a.id=s.asset_id where a.asset_type='wagon';

\echo '--- 6. how far are wagons from the next 90 km multiple (test interval), by mileage mod 90'
select width_bucket((90 - (mileage % 90))::numeric, 0, 90, 9) as bucket_of_remaining_km_0_90, count(*)
from fixed_assets where asset_type='wagon' and mileage>0 group by 1 order by 1;

\echo '--- 7. railcars of other types'
select asset_type, count(*), count(*) filter (where mileage>0) with_mileage,
  count(*) filter (where exists (select 1 from asset_source_links s where s.asset_id=a.id and s.status='active' and s.source='gtk')) gtk_linked
from fixed_assets a where asset_type in ('wagon','tank_car','platform') group by 1;

\echo '--- 8. intervals and which asset types they apply to'
select code, interval_km, asset_types from maintenance_intervals order by rank nulls last, code;
