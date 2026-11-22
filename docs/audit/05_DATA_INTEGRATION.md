# 05 — Data integration and integrity

> READ-ONLY audit, 2026-11-22. Nothing was changed in code, config, DB or containers. Every finding is labelled VERIFIED (code line / SQL result seen) or UNVERIFIED / POTENTIAL RISK. Browser/API behaviour of the pages was NOT tested (no credentials; creating an account would write to the live DB).
> Source: workers C and D

## C. SINGLE SOURCE OF TRUTH

### C1. Asset identity
- Canonical identity: `fixed_assets.id` (UUID). External identity: `asset_source_links (source, external_id, status)` with two partial UNIQUE indexes (one active link per asset+source and per source+external id) -> duplicate active links are impossible at DB level (VERIFIED indexes). Live: 0 duplicates; 0 orphan links (asset missing); 0 Wialon links without a `wialon_units` row; all 663 active GTK links resolve to exactly one of `gtk_carriages` (587) / `gtk_locomotives` (76); 0 GTK ids exist in both tables.
- Second, parallel identity store: legacy columns `fixed_assets.wialon_id` / `gtk_id` (UNIQUE). `asset_links._MIRROR_FIELDS` (`asset_links.py:16`) keeps them in sync on link/unlink, and ingestion (`find_wialon_asset` -> `asset_links_service.find_asset`; `repositories/wialon_counters.get_asset_by_wialon_id` joins links) correctly uses links. But LIVE DRIFT exists: wialon_id column set on 100 assets vs 87 active Wialon links (13 rows: 11 wagons + 2 platforms with `wialon_id` such as "3", "2", "257" and NO link); gtk_id column set on 707 assets vs 663 active GTK links (44 wagons with `gtk_id` set, carriage row exists in `gtk_carriages`, no active or ended link; all 44 rows have the same `updated_at` 2026-11-09 14:12:17 -> one bulk write that bypassed the link service). Those wagons are "no_link" for map/GPS/scales/ТО but the Справочник API still returns a `gtk_id`. (MOD-04)
- Kind of external id is not stored: GTK locomotive and carriage ids are separate spaces and the code disambiguates by asset type (`asset_map.py:_train_for`, `scales.py:200`, `repositories/asset_map.py:104-108`). Live collisions: 0, no constraint prevents one (MOD-17).
- Coverage (live): 1075 assets = wagon 835, tank_car 129, platform 24, locomotive 51, diesel 35, special_self_propelled 1; status all `operational`; `decommissioned_at` null for all (no archived assets exist). Active links: wialon 87 (all 87 locomotives of all three loco types; 0 wagons), gtk 663 (587 wagons + 76 locos). Assets with NO active link at all: 401 (tank_car 129, platform 24, wagon 248). Locomotives without GTK link: 11 (diesel 10 + special_self_propelled 1). Unlinked source objects: `wialon_units` 92 of 179, `gtk_carriages` 101 of 688, `gtk_locomotives` 1 of 77, `gtk_gps_units` 164 of 242. All 756 links are `link_method='manual'` (6 ended).
- Duplicates: 15 inventory numbers shared by 30 assets (types diesel/tank_car/wagon) — deliberate (DECISIONS #31); each pair has different `serial_number`; none of the pairs has any link. Any code that matches by `inv_number` alone is ambiguous for these 15: `asset_map.find_gtk_candidate` matches carriages by inventory/registration (`asset_map.py:181-225`).
- Link quality: of 663 active GTK links, GTK `inventory_number` equals the asset `inv_number` (leading zeros ignored) for 574/587 wagons and 62/76 locomotives; 27 differ (e.g. loco 38956 vs GTK 38957, wagon 38922 vs 38992, 37815 vs 37915): probably typos in GTK, but nothing in the UI flags them since `inv_number` is `manual_only` (MOD-07).

### C2. Passport vs GTK/Wialon: who overwrites whom (VERIFIED `core/asset_field_policy.py`, `services/asset_field_changes.py:propose_field`)
- `inv_number`, `asset_type`, `org_unit_id`: owner `toir`, `manual_only` (no source may write).
- `number`, `model_id`: owner `gtk`, `auto_fill_if_empty` — GTK fills only when empty; if different it creates a `conflict` row in `asset_field_changes`; `_same_number` ignores leading zeros (`asset_field_changes.py:35`). Proposals are applied only for `asset.asset_type == "wagon"` (tank_car/platform rejected silently, :~100) (MOD-06). Live: 287 rows, all field `number`, kind `conflict`: 286 rejected, 1 pending; 0 `applied`/`auto_fill`.
- `accounting_inv_number`, `commissioned_at`, `serial_number`, `year_built`: owner `onec`, `suggest_only`, but no 1C integration exists; live `accounting_inv_number` is NULL for 1075/1075 assets (VERIFIED), `serial_number`/`model_id`/`section_id`/`commissioned_at`/`year_built` filled for 1075/1075 (from the JSON passport import, DECISIONS #31).
- `mileage`, `online`, `speed`: owner `wialon`, no proposals; written directly by the pull: `wialon_online`/`wialon_speed`/`wialon_last_sync` for any linked asset, `mileage` ONLY by gated delta and ONLY for `locomotive`,`diesel` (`services/assets.py:511,636-640`); wagon mileage only by the wagon ledger projection.
- Conflict flow = `asset_field_changes` (+ `asset_conflicts` router); the GTK pull creates proposals in a separate session after the snapshot (`gtk.py:138-146`); failures are logged and swallowed.

### C3. Duplicated algorithms (VERIFIED by grep)
1. Number normalisation: 5 different implementations — `asset_map._norm` (strip, lstrip "0", lower) `asset_map.py:181`; `scales_matching.normalize_loco_number`+`loco_keys` (upper, no spaces, exact then zero-stripped) `:23-37`; `asset_matching.normalize_token` (NFKC, casefold, Latin->Cyrillic map, alnum only) `:56`; `asset_passport.normalize_token`; `asset_field_changes._same_number` (int compare). Same plate can match in one module and not in another.
2. "Online/fresh" thresholds: 15 min in `repositories/asset_map.py:21`, `services/wialon.py:23`, `services/train_formation.py:35`, hard-coded again in `repositories/unified_assets.py:168`; 30 min `gps_compare.FRESH`; GPS page UI 15/45 min (`gps/page.tsx:407-408`); GTK page 30 min; Wialon page 24 h; scales 6/24 h + collector 10 min. (MOD-08)
3. Locomotive type set: `LOCOMOTIVE_TYPES` x3 (`repositories/asset_map.py:20`, `services/assistant/types.py:15`, `wialon_counter_release.py:47` WITHOUT special_self_propelled), `LOCOMOTIVE_MILEAGE_TYPES` (`assets.py:511`), literal sets in `assets.py:499`, `gtk.py:388`, `asset_matching.py:130`, `gtk_matching.py:51`, frontend `lib/maintenance-view.ts:242`. (MOD-14)
4. Master-section scoping helper copied in routers/assets, mileage, references, wialon, services asset_history, asset_map, gps_overview, maintenance, tmc_documents, train_formation, analytics (11 definitions). (MOD-18)
5. ТО recommendation/progress/pace: backend `maintenance_engine` + frontend `maintenance-view.ts` (`progressPct`, `recommend`, `paceOf`). (MOD-19)
6. Timezone: `gtk_client.TZ=UTC+5` constant, `settings.gtk_utc_offset_hours`, `settings.scales_utc_offset_hours`, and `date.today()` in `maintenance_lifecycle.run_cycle` (`:671`, container-local). (MOD-09)
7. GPS position verdict is computed by ONE function (`gps_compare.position_check`) used by both Map (`asset_map._loco_gps_point`) and GPS page (`gps_overview`), good: the two pages agree by construction for locomotives with a GTK unit.

### C4. Scales <-> wagons <-> assets
Chain: scale row (loco number by hand) -> GTK locomotive by `garage_number` -> GTK train membership overlapping the weighing time -> carriages -> `asset_source_links(gtk)` -> `fixed_assets`. Live: 55 533 trains; `loco_asset_id` set on 54 881; `match_status`: `no_gtk_train` 53 623, `ok` 1 258, `no_loco` 652; ALL 1 258 `ok` are in 2026-11 (GTK composition history only exists since TOIR began mirroring it; older trains cannot match, `scales.py:396` docstring). `scale_train_carriages` 16 321 rows all with `asset_id` set, 512 distinct wagon assets. So the wagon-level scale data covers ~2 weeks only; the locomotive-level data covers the whole history.

### C5. ТО <-> assets
`maintenance_plan.asset_id` FK; meters come from `fixed_assets.mileage` (loco via Wialon delta; wagon via ledger). Wagon ledger is not refreshed automatically (MOD-01) so wagon ТО would rest on a 6-day-old meter if baselines existed. With 0 baselines/plans there is currently no live ТО state at all (MOD-03).

---------------------------------------------------------------------------------------------------

## E. LIVE IDENTITY-INTEGRITY SQL (all SELECT, read-only tx; results quoted above in C1)
Key results: assets 1075 (see types in C1); links 756 (gtk 669 = 663 active + 6 ended, wialon 87 active); assets without any active link 401; without Wialon link 988 (wagon 835, tank_car 129, platform 24) — expected as Wialon is locomotives-only; without GTK link 412 (wagon 248, tank_car 129, platform 24, diesel 10, special_self_propelled 1); duplicate active links 0 (enforced by partial unique indexes); orphan links 0; mirror drift wialon 13, gtk 44; duplicate inventory numbers 15 groups/30 assets; `inv_number` NULL/blank 0; provisional inventory 0; unlinked gtk_carriages 101; decommissioned 0.

---------------------------------------------------------------------------------------------------

## Data integrity (worker D)

## 1. DATA INTEGRITY (live SQL)

### 1.1 Row counts (exact `count(*)` where small; `pg_class.reltuples` otherwise)
Planner statistics are stale/never collected for several tables (reltuples = -1, or wrong): e.g. reltuples said `users`=22, `asset_maintenance_baseline`=7, `maintenance_decision`=20, `maintenance_intervals`=12; real `count(*)` = 3, 0, 0, 9. `work_orders`, `mileage_calculation_runs`, `scale_corrections` show -1 (never analyzed).

| table | rows | note |
|---|---|---|
| asset_position_history | ~1,944,703 (630 MB) | since 2026-09-26; ~26.5k rows/24 h; retention 180 d exists |
| wialon_odometer_readings | ~535,954 (476 MB) | earliest observed_at 2021-08-15 |
| wialon_raw_receipts | ~789,894 (340 MB) | earliest 2026-11-10, all `transport='pull'`; NO retention code |
| scale_weighings | ~599,731 (223 MB) | |
| gtk_raw_snapshots | 2,441 (103 MB, ~41 kB payload/row) | 2026-11-09..2026-11-22; NO retention |
| scale_trains | 55,533 | 2024-12-31..2026-11-20 |
| fixed_assets | 1,075 (all status `operational`) | wagon 835, tank_car 129, locomotive 51, diesel 35, platform 24, special_self_propelled 1 |
| asset_source_links | 756 | gtk active 663 / gtk ended 6 / wialon active 87 |
| wialon_units | 179 | |
| gtk_locomotives 77 / gtk_carriages 688 / gtk_trains 116 / gtk_train_members 1,767 (carriage 1,651 [478 open], locomotive 116 [37 open]) | | |
| gtk_gps_units 242 / gtk_gps_days 3,774 (76 distinct gtk_id, 2026-09-18..11-22) | | |
| gps_day_assessment | 2,736 (76 assets, 2026-10-18..11-22) | |
| gps_wagon_segments | 10,161 (2026-11-04..11-22) | |
| wagon_mileage_ledger | 2,871 rows; created 2026-11-15 16:32 .. 2026-11-16 09:21 only | active: CONFIRMED 1, ESTIMATED 506 (35,700 km), HELD 3; superseded 2,361 |
| wagon_mileage_opening_balances | 589, all `approved`, all wagons | |
| mileage_calculation_runs | 7, all `completed`, 2026-11-15 16:32 .. 2026-11-16 09:20 | |
| asset_field_changes (conflicts) | 287: rejected 286, pending 1, accepted 0 | there is NO `asset_conflicts` table; conflicts are computed from `asset_field_changes` + `wialon_counter_state` |
| maintenance_intervals 9 (8 real + inactive `test` 90 km/10 d) | asset_maintenance_baseline 0, maintenance_schedule 0, maintenance_plan 0, maintenance_decision 0, maintenance_settings 0 | module is empty on live |
| work_orders 0, work_order_items 0, employees 0, work_types 16, sections 8 | | |
| users 3 (admin/ad/active 2; management/ad/active 1) | | all AD accounts; no local users; master/operator users: 0 |
| role_permissions 4 roles x 43 permissions | | |
| scale_corrections 0, scale_cargo 7, scale_posts 2 | | |

All 138 datetime columns in `public` are `timestamp with time zone`; zero `timestamp without time zone` (VERIFIED, information_schema). DB `timezone` = UTC.

### 1.2 Constraint / index inventory (assumptions in code vs live)
- Natural-key uniques present: `fixed_assets.wialon_id`, `fixed_assets.gtk_id` (uq_fixed_assets_gtk_id), partial unique `accounting_inv_number`, `asset_source_links` partial uniques (asset_id,source WHERE active) and (source,external_id WHERE active), `gtk_train_members` open-membership partial unique (train_gtk_id,kind,object_gtk_id WHERE observed_to IS NULL), `scale_trains (post_id,src_id)`, `scale_weighings (train_id,src_id)`, `wagon_mileage_ledger.idempotency_key`, `gps_wagon_segments (carriage_gtk_id,train_gtk_id,period_from)`, `work_orders.number`, `maintenance_intervals.code`.
- NOT unique: `fixed_assets.inv_number` (plain btree `ix_fixed_assets_inv_number`), `gtk_carriages.reg_number`, `gtk_trains.number`.
- No FK between `fixed_assets.gtk_id` / `asset_source_links.external_id` and `gtk_*` (types differ: `fixed_assets.gtk_id` and `external_id` are varchar, `gtk_*.gtk_id` integer; `wialon_units.unit_id` varchar). `gtk_train_members.train_gtk_id/object_gtk_id` have no FK either. Orphan checks below show 0 orphans today, but nothing enforces it.
- 3 CHECK constraints on `fixed_assets` are `NOT VALID` (never validated): `ck_fixed_assets_year_built_min`, `ck_fixed_assets_commissioned_at_year_built`, `ck_fixed_assets_decommissioned_at_commissioned_at`. No current row violates them (3 queries returned 0).
- `asset_maintenance_baseline`: pk (asset_id, interval_id); 4 FKs.
- Redundant index: `ix_asset_position_history_asset_at (asset_id, at)` is a prefix of unique `uq_asset_position_history_point (asset_id, at, source)`.

### 1.3 Duplicates / orphans / NULLs (exact queries run, results)
```
-- duplicate inventory numbers
select count(*) from (select inv_number from fixed_assets group by 1 having count(*)>1) x;      -> 15  (sample 38128, 38129, 38130, 38572..: both rows tank_car)
-- duplicate wagon serials
select count(*) from (select serial_number from fixed_assets where asset_type in ('wagon','tank_car','platform') group by 1 having count(*)>1) x; -> 14
-- inv_number format: length 5 for all 1075 rows, no leading zero, all digits
-- GTK carriages with duplicate reg_number
select count(*) from (select reg_number from gtk_carriages group by 1 having count(*)>1) d;      -> 57 groups (114 rows)
   rows of those groups that are linked to an asset (fixed_assets.gtk_id = gtk_id::text) -> 58 of 114
   gtk_carriages total 688, linked 631 => the 57 unlinked carriages are GTK-side duplicates of linked ones
-- GTK train number duplicates: 38 numbers repeat (117, 258, 421 appear 5 times) -> numbers are reused, not an identity
-- active gtk link without GTK row: 0 ; active wialon link without wialon_units row: 0
-- fixed_assets.gtk_id without gtk row: 0
-- fixed_assets.wialon_id without wialon_units row: 4
-- fixed_assets.gtk_id set but NO active gtk link: 44 (all wagons, none have an 'ended' link)
-- fixed_assets.wialon_id set but NO active wialon link: 13 (platform 2, wagon 11; 7 of the wagons' units exist)
-- active link vs fixed_assets column mismatch (gtk / wialon): 0 / 0
-- wialon_units not referenced by any fixed_assets.wialon_id: 83 of 179
-- gtk_train_members orphan train / orphan object: 0 / 0; carriage in >1 open train: 0
-- gps_wagon_segments orphan carriage / train: 0 / 0; gtk_gps_days without unit: 0
-- wo orphan asset 0; wo.section_id vs asset.section_id mismatch 0 (work_orders is empty anyway)
-- fixed_assets NULLs: model_id 0, commissioned_at 0, year_built 0, section_id 0 (of 1075); accounting_inv_number NULL for all 1075
```
Leading-zero inventory (task item): GTK `reg_number` is 8 chars zero-padded for 390 of 688 carriages (all 390 start with `0`; lengths 3/4/5/8). `fixed_assets.serial_number` has no leading zeros (lengths 1-5 and 8 for 157 rows, none start with `0`). For 587 linked wagons: exact equality 296, equal only after `ltrim('0')` 290, different 1. So matching depends on stripping zeros in code; 14 serial duplicates may collide after normalisation.

Units (task item "mixed units"): distance is km in `wagon_mileage_ledger.distance_km` / `wialon_odometer_readings.odometer_km` / `mileage_history.mileage` (numeric), but metres (integer) in `gps_day_assessment.wialon_m/gtk_m/fused_m/diff_m` and in the GPS API; tonnes in scales (`net_t`). Names carry the unit, no conversion bugs were looked for in this audit (UNVERIFIED).

### 1.4 Ledger / mileage checks
```
-- active ledger rows overlapping for same wagon: 1 pair
   (02e4db06.. HELD 0.00 km, train 3130, 2026-11-15 16:27 -> 2026-11-16 05:16) vs (851c33da.. ESTIMATED 61.00 km, train 3246, 16:27 -> 09:17), different run_id
-- superseded rows with no successor row pointing at them: 465 (HELD superseded 1,542; supersedes_id set on 1,386 superseded + 510 active)
-- approved openings (589) with NO active ledger row for the wagon: 105
-- approved openings per asset > 1: 0
-- mileage_history sources: wialon 14,732, gtk 201 (max recorded_at 2026-11-22 08:22)
```
Ledger/engine last ran 2026-11-16 09:20 (runs table) while GTK sync is live until today (see INT-1).

### 1.5 Time coverage / history retention (data gaps, VERIFIED)
```
select received_at::date, count(*) from wialon_raw_receipts where received_at>=now()-interval '13 days' group by 1;
11-10 15,222 | 11-11 111,151 | 11-12 124,962 | 11-13 124,785 | 11-14 7,965 | 11-15 31,683 | 11-16 121,931 | 11-17 125,719 | 11-18 124,254 | 11-19 49,560 | 11-20 77,526 | 11-21 (NO ROWS) | 11-22 3,717 (so far)
gtk_sync_runs per day: 11-15 75, 11-16 284, 11-17 295, 11-18 288, 11-19 116, 11-20 178 ok +1 error, 11-21 0, 11-22 9
gtk_gps_runs per day: 11-17 41, 11-18 144, 11-19 57, 11-20 88, 11-21 0, 11-22 4
scale_trains per started_at day: 11-16 65, 11-17 92, 11-18 70, 11-19 102, 11-20 55, then nothing for 11-21/11-22
```
Retention code exists only for `audit_logs` (365 d) and `asset_position_history` (180 d) (`services/audit_log.py:462 run_audit_retention`, config.py:23-24). No delete/purge found for `wialon_raw_receipts`, `gtk_raw_snapshots`, `wialon_odometer_readings`, `wialon_rejected_readings`, `scale_weighings` (grep of Delete/purge/retention). Expired `refresh_tokens`: 1,027 of 1,550 rows past expiry, 1,541 revoked, never purged.
Wialon readings with `asset_id IS NULL` in the last 2 days: 15,946 of 31,575 (50.5%) (unlinked units still produce readings).

### 1.6 Other live data observations
- Live data still contains maintenance interval `test` (inactive) -> test residue (Low).
- `wialon_settings`: `token` column empty (token is read from env, not DB) (VERIFIED: `token is not null and length>0` = false); `auto_sync_enabled`=true, interval 5 min, last status `ok: found=87, updated=87, not_found=90`.
- No ZZTEST residue (sections/users/audit labels = 0).
- employees = 0 while `WorkOrderCreate.executor_id` is a required UUID (`schemas/work_orders.py:45`) -> with the current live data no work order can be created through the API until an employee exists (INT-9).

---------------------------------------------------------------------------------------------------
