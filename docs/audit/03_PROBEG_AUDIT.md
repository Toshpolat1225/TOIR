# 03 — PROBEG (mileage) audit

> READ-ONLY audit, 2026-11-22. Nothing was changed in code, config, DB or containers. Every finding is labelled VERIFIED (code line / SQL result seen) or UNVERIFIED / POTENTIAL RISK. Browser/API behaviour of the pages was NOT tested (no credentials; creating an account would write to the live DB).
> Source: worker A (probeg)

# A_probeg — PROBEG (mileage) end-to-end audit (read-only)

Date of audit: 2026-11-22 (DB clock ~08:24 UTC). Issue prefix: PRB-. Method: code reading (`path:line`) + SELECT-only SQL on the live DB (read-only tx, 8 s limit, indexed/narrow queries). Browser/API verification of pages was NOT possible (no credentials, no UI login); page behaviour below is derived from frontend code + the DB fields each page reads.

Paths are relative to `backend/app/` unless they start with `app/` (frontend) or `lib/`.

---------------------------------------------------------------------

## 1. SOURCES AND UNITS

### 1.1 Real schema actually used (checked in `information_schema.columns`)
Assets table is `fixed_assets` (NOT `assets`). Mileage related columns:

| Table | Mileage columns / unit | Role |
|---|---|---|
| `fixed_assets` | `mileage numeric` (km, 2 dp, "TOIR scale" = growth since tracking began, NOT the real odometer) | the ONE number maintenance, assets list, scales, work-orders read |
| `wialon_units` | `cnm numeric` (km, absolute Wialon counter, integer resolution), `cneh` (hours), `last_message_at`, `suspect_absolute` | raw live Wialon snapshot; shown on /dashboard/os/wialon |
| `wialon_odometer_readings` | `odometer_km numeric` (km), `reading_at` (= Wialon last-message time, UTC), `received_at`, `accepted`, `calculation_eligible`, `classification` CONFIRMED/HELD, `rejection_reason`, `resolution_km`=1, `measurement_key`, `payload_hash` | per-message odometer samples (change-only: new row only when unit+message-time+odometer is new) |
| `wialon_counter_state` | `baseline_cnm`, `last_cnm`, `last_cnm_at`, `baseline_cneh`, `last_cneh`, `engine_hours`, `last_status`, `last_reason`, `suspect_absolute` | gate state per asset (87 rows) |
| `wialon_rejected_readings` | counter, value, previous_value, reason | audit of gate rejections (13 667 rows) |
| `mileage_history` | `mileage numeric`(TOIR scale), `source` in (wialon, manual, gtk), `recorded_at` | cumulative TOIR mileage log; only written on a positive Wialon delta (loco) |
| `asset_meter_daily` | `km` (= fixed_assets.mileage snapshot), `hours` | hourly job snapshot, pace history |
| `gtk_gps_units` / `gtk_gps_days` / `gtk_gps_runs` | `distance_m integer` (METRES, GTK server-computed daily figure), `points`, `is_final`, `events jsonb` | GTK own GPS feed |
| `asset_position_history` | lat/lon, `source` in (wialon, gtk_gps) | thinned tracks (>=100 m move or 20-min heartbeat) |
| `gps_day_assessment` | `wialon_m`, `gtk_m`, `fused_m`, `odo_m`, `unknown_gap_m` (all integer METRES), `verdict`, `cause`, `confidence`, `odo_agrees`, `is_final` | per-locomotive-day comparison (page /dashboard/gps) |
| `gps_wagon_segments` | `km_odometer`, `km_wialon`, `km_gtk`, `km_fused`, `selected_km` (km, 3 dp), `basis`, `confidence`, `coverage` | wagon km derived from the locomotive's tracks |
| `wagon_mileage_opening_balances` | `mileage_km`, `effective_at`, `status` pending/approved/superseded | manual wagon opening mileage (maker/checker) |
| `wagon_mileage_ledger` | `distance_km` (2 dp), `classification` CONFIRMED/ESTIMATED/HELD, `status` active/superseded, `idempotency_key` UNIQUE | wagon km ledger -> projected into `fixed_assets.mileage` |
| `gtk_wagon_mileage_log` / `gtk_locomotive_mileage_checkpoints` | legacy (201 / 76 rows) | legacy; checkpoint table is only reset on relink (`services/assets.py:454-462`), never read for a value |
| `asset_maintenance_baseline` | `km numeric` (TOIR scale), `done_at`, `hours`, `source` | last-service mileage — 0 rows in DB |
| `maintenance_plan` | `trigger_mileage`, `completed_km` | 0 rows in DB |

### 1.2 How mileage enters the system
| Source | Entry point | Unit | Stored as | Used for TOIR `fixed_assets.mileage`? |
|---|---|---|---|---|
| Wialon pull (live, every `WIALON_SYNC_INTERVAL_MINUTES`, default 2) | `services/wialon.py:106 sync_wialon_assets` -> `integrations/wialon_client.py:155 _mileage` (key `cnm`) -> `wialon_ingestion.py:76 ingest_wialon_reading` | km (cnm truncated to whole km by Wialon API; `wialon_quality.py:5-6`) | `wialon_units.cnm`, `wialon_odometer_readings.odometer_km`, state in `wialon_counter_state` | YES, only the gated DELTA, only for asset types `locomotive`,`diesel` (`services/assets.py:511,636-647`) |
| Wialon push `/wialon/input` | `routers/wialon.py:228` | km | readings only | NO: `source_time_verified=False` -> always HELD (`wialon_ingestion.py:153-154`); `mileage=None` passed to `receive_wialon_update` (`routers/wialon.py:250`) |
| GTK GPS daily track | `services/gtk_gps.py:173 sync_gtk_gps` (every `GTK_GPS_SYNC_INTERVAL_MINUTES`, live ~10 min) | METRES (`gtk_gps_days.distance_m`) | `gtk_gps_days`, points in `asset_position_history` source gtk_gps | NO. GTK never writes `fixed_assets.mileage` for locomotives (checked: no code path; only comparison/analytics) |
| GTK train membership + Wialon odometer of the locomotive -> wagon ledger | `services/wagon_mileage_run.py:501 run_wagon_mileage` | km | `wagon_mileage_ledger` -> `fixed_assets.mileage` of wagons (`wagon_mileage_run.py:854-862`) | YES for wagons, but the engine is OFF (see PRB-02) |
| Wagon GPS segments (loco tracks x GTK membership) | `services/wagon_gps.py:133 compute_segments` (after each GTK GPS cycle, back 3 days) | km | `gps_wagon_segments` | NO (docstring `wagon_gps.py:6-7`; only as HELD-period fallback if `WAGON_MILEAGE_TRACK_FALLBACK`) |
| Manual | `services/assets.py:514 set_fixed_asset_mileage` always raises 422; `FixedAssetUpdate` excludes `mileage` (`lib/api.ts:1173`) | - | - | NO manual path for locomotives at all. Wagons: opening balance workflow only (`services/mileage_opening.py:28`, maker/checker) |
| Passport / 1C | `asset_inventory_import`, `asset_passport_import`: no mileage handling (grep empty); `core/asset_field_policy.py:24` `mileage -> source wialon` | - | - | NO |
| Maintenance baselines (last-service km) | `services/maintenance_lifecycle.py:700 import_baselines`, `:416 set_baseline` | km TOIR scale OR `odometer_km` converted | `asset_maintenance_baseline` | n/a (0 rows) |
| Wialon asset creation | `services/wialon_units.py:221` `mileage = unit.cnm` (ABSOLUTE counter seeded into TOIR mileage) | km | `fixed_assets.mileage` | one-off seed; existing assets are small (loco max 1300) so they were reset elsewhere (not found in code, UNVERIFIED how) |

### 1.3 TOIR scale vs real odometer
- TOIR mileage = sum of gated Wialon deltas since tracking began (code comment `wialon_quality.py:3-6`: "TOIR mileage is kept by counter GROWTH, not the absolute cnm"). Offset = `wialon_units.cnm - fixed_assets.mileage` is computed on demand (`maintenance_lifecycle.py:384-398 _odometer_offset`) only to convert a passport `odometer_km` baseline into TOIR scale (`resolve_baseline_km` :401-413).
- VERIFIED example (SQL): loco 37070: TOIR 861, Wialon cnm 190902, offset 190041. Loco 37073: TOIR 1012 vs cnm 181152.
- Counter cleanliness: `suspect_absolute` if cnm > 1 000 000 or cnm/cneh > 100 (`wialon_quality.py:103-108`); 7 of 179 units flagged.

### 1.4 Initial / final reading logic (Wialon gate) — `services/wialon_quality.py`
- First reading (no state): `Verdict.BASELINE`, delta 0, baseline saved (:114-116). Mileage not changed.
- Same or older message time: UNCHANGED (:117-118).
- `dc = cnm - last_cnm`: `dc < -1` REJECTED ("cnm kamaydi"); `-1 <= dc <= 0` UNCHANGED (rounding); `dc > 150 km/h * dt_hours + 10 km` REJECTED ("cnm sakradi"); else ACCEPTED with delta dc (:119-127). State is NOT advanced on REJECTED.
- STALE: if message time older than 24 h vs `now` (:154-156) nothing is accepted.
- Same message time but different odometer: `ingest` locks rows and marks "same_time_different_odometer" conflict unless it is a benign growth (`is_counter_advance` :78-100); a conflict blocks the asset counter until an operator rebaselines (`wialon_ingestion.py:216-228,250-256`).

### 1.5 Which source wins and when
| Question | Logic | Where |
|---|---|---|
| Locomotive TOIR mileage | Wialon gated delta only | `services/assets.py:636-647` |
| Locomotive daily distance (GPS page) | fused track: Wialon track is the timeline, GTK points fill Wialon holes > 25 min; if a unit has NO Wialon track at all use GTK `distance_m` + bridge | `gps_analytics.py:106-123 fuse`; `gps_assessment.py:158` |
| GTK vs Wialon verdict per day | ratio = gtk_m / wialon_m: 0.85-1.15 match; 0.60-0.85 or 1.15-1.60 minor_diff; below 0.60 gtk_gap; above 1.60 wialon_gap; both < 1000 m idle | `gps_compare.py:139-168` (IDLE_M=1000, thresholds :20-22) |
| Cause classification | not_collected, idle/no_data, ok, day_open, gtk_dead, gtk_no_day, both_gaps, gtk_gaps (>=2 h silence), wialon_gaps, gtk_sparse (<40 % points), method | `gps_analytics.py:154-179` |
| Odometer "third source" | `odo_m` = interpolated odometer delta over the local day; `odo_agrees` if within 15 % of the Wialon track; raises confidence only | `gps_analytics.py:126-150,270-295`; `gps_assessment.py:159-162` |
| Wagon km candidates A odometer / B Wialon track / C GTK track / D fused | `select_candidate`: D if coverage >= 0.9 (high if another agrees within 10 %); else A vs B if both exist; else first present of fused > wialon > odometer > gtk, low confidence | `gps_analytics.py:366-379` |
| Wagon TOIR km | ledger projection = approved opening + sum(active, eligible ledger rows with `period_from >= effective_at`) | `wagon_mileage_run.py:799-824` |

---------------------------------------------------------------------

## 2. ALGORITHMS (formula, location, limits, defects)

| # | Algorithm | Formula / rule | Location | Limits / defects |
|---|---|---|---|---|
| A1 | Wialon delta | `delta = cnm_new - last_cnm` if `-1 <= ...`, accepted iff `0 < delta <= 150*dt_h + 10` | `wialon_quality.py:111-127` | cnm is whole km (±1 km quantisation; parked units can show +1 km/h drift, PRB-06). Rejection leaves state unchanged -> repeated rejection until the allowance grows (hours: PRB-12). |
| A2 | First reading | BASELINE, delta 0 | `wialon_quality.py:114` | The km driven before first contact is unknown; no manual starting mileage exists for locomotives (no UI/API). |
| A3 | Duplicate readings | `measurement_key = sha256(unit|reading_at|odometer)`, UNIQUE; `payload_hash` UNIQUE; `ON CONFLICT DO NOTHING` | `wialon_ingestion.py:62-73,156-178` | Idempotent (re-pull of same message time is UNCHANGED). A re-pull can flip an existing row's `classification` (`:287-290`). |
| A4 | Decreasing counter | `dc < -1` rejected; `-1..0` ignored | `wialon_quality.py:120-123` | Also in analytics: `odometer_delta` returns None when end < start (`gps_analytics.py:293`). |
| A5 | Counter reset / jump | `dc > 150 km/h * dt + 10` rejected ("cnm sakradi"); 176 such rows in `wialon_rejected_readings` | `wialon_quality.py:124-126` | After a Wialon outage the allowance grows with dt, so a real catch-up is accepted in one step (booked on the later day, PRB-09). |
| A6 | Max/min bounds | `suspect_absolute`: cnm > 1e6 or cnm/cneh > 100 | `wialon_quality.py:103-108` | info only; asset creation is refused for such units (`wialon_units.py:203-212`). |
| A7 | Bad GPS coordinates | `valid_fix`: |lat|<=90, |lon|<=180, not (0,0); thinning: store when moved >=100 m or 20 min passed | `position_history.py:49-71` | No HDOP/satellite/accuracy filter; analytics drops hops > 120 km/h (`TELEPORT_KMH`) and treats > 60 min silence as a "bridge" (straight line) (`gps_analytics.py:17-18,53-70`). Track length = polyline of thinned points (chord), systematically below the odometer (code says median 0.973). |
| A8 | Signal loss | `coverage_and_gaps` (gap > 60 min), `GAP_LONG_H=2`; GTK "dead" if >= 90 % of >= 3 active days have no points | `gps_analytics.py:73-89,154-179`; `gps_assessment.py:117-120` | OK. |
| A9 | Ordering | readings ordered by `reading_at`; same-time ties resolved by lock + conflict rule | `wialon_ingestion.py:141-149,188-228` | Per-unit advisory lock. Lookup `source_unit_id=? AND reading_at=?` has no matching index (PRB-10). |
| A10 | Date rollover / timezone | GTK/GPS days use FIXED offset `GTK_UTC_OFFSET_HOURS` (default 5 = Asia/Tashkent, no DST) (`gps_assessment.py:74-80`, `gtk_gps.py:48-62`; segments split at local midnight `wagon_gps.py:75-85`). Maintenance pace/snapshots use UTC dates: `date.today()` in a UTC container (VERIFIED: container `date` = UTC, `TZ` empty; DB timezone = UTC), `func.date(recorded_at)` | `maintenance_lifecycle.py:671,622`; `maintenance_obligations.py:100-139` | Two different "day" definitions (local vs UTC) between GPS pages and maintenance pace (PRB-09). |
| A11 | Historical recalculation | `gps_day_assessment`: upsert; today always recomputed, past days until `is_final` (`gps_assessment.py:252-266`); CLI `assess_range` for backfill. GTK day fetched until final = local midnight + 45 min (`gtk_gps.py:35,61-75`). TOIR mileage: no recalculation of old Wialon readings (HELD rows stay HELD, PRB-05). Wagon ledger: new run supersedes overlapping rows (`wagon_mileage_run.py:662-691`). | | Final days never re-fetched (PRB-13). |
| A12 | Idempotency of re-ingest | readings: unique keys; ledger: `idempotency_key` UNIQUE + invariant check (negative, overlap, duplicates) `wagon_mileage_run.py:587-637`; gps rows: upsert on PK | | Good design. |
| A13 | Wagon km (ledger) | per (wagon, GTK membership period): main locomotive chosen, `km = sum over eligible odometer sample brackets of (sample_km * overlap_s / bracket_s)`; bracket gap > `WAGON_MILEAGE_MAX_BRACKET_GAP_MIN` (240) with distance>0 => HELD `odometer_sample_gap_exceeded`; classification ESTIMATED unless exact 2-minute brackets | `wagon_mileage.py:144-290`; `wagon_mileage_run.py:219-283` | Every wagon in the train gets the FULL locomotive distance (by design). 506 active ledger rows: 505 ESTIMATED, 1 CONFIRMED (SQL). |
| A14 | HELD reasons | 18 codes in `wagon_mileage_reasons.py` (e.g. approved_opening_balance_missing, odometer_sample_gap_exceeded, reading_not_calculation_eligible, locomotive_handoff_time_unknown, missing_odometer_sample_bracket) | `wagon_mileage_reasons.py:3-82` | run summaries in DB show 363x `odometer_sample_gap_exceeded`, 252x `reading_not_calculation_eligible` in early runs (2026-11-16 07:44/08:05); last run HELD 0. |
| A15 | Track fallback | for HELD periods use `select_candidate` of the loco tracks (`wagon_gps.py:103-130`), only if `WAGON_MILEAGE_TRACK_FALLBACK` | | docs/HANDOFF.md:1377 says it was enabled 2026-11-18 but the engine is not running, so no effect. |
| A16 | Locomotive mileage in maintenance | `used = fixed_assets.mileage - baseline_km`; provisional baseline (no row) = `floor(mileage/interval)*interval` ("grid") | `maintenance_obligations.py:479-500` | With 0 baselines every obligation is "provisional" (PRB-04). |
| A17 | Pace | per asset: day buckets of max(`mileage_history.mileage`) per UTC date + `asset_meter_daily` snapshots; `daily_deltas` forward-fills idle days; quantiles p25/p50/p75; shrink to type group: `w = n/(n+7)`; wagons: ledger partial-day rates | `maintenance_obligations.py:100-248`; `maintenance_engine.py:51-186` | Mixed bases (UTC), catch-up booked on later day. |
| A18 | Overdue state | `used > limit+tol` -> over_tolerance; `used >= limit` -> over_limit; today >= date_p75 - lead_days -> due_soon; else forecast | `maintenance_engine.py:288-317` | Formula verified by reading; see section 4. |

---------------------------------------------------------------------

## 3. CROSS-PAGE CONSISTENCY

### 3.1 Which page reads what
| Page | Frontend | API / backend | DB fields | Recomputes or reuses? |
|---|---|---|---|---|
| /dashboard/gps (locomotives) | `app/dashboard/gps/page.tsx:72` `api.gps.overview` | `services/gps_overview.py` -> `gps_assessment.ensure_days` (stored for past days, LIVE compute for today / missing) | `gps_day_assessment` (+ live `asset_position_history`, `gtk_gps_days`, `wialon_odometer_readings`) | own computation; shows daily Wialon-track m / GTK m / fused m / odo m; NEVER shows `fixed_assets.mileage` |
| /dashboard/gps/wagons | `app/dashboard/gps/wagons/page.tsx:61` `api.gps.wagons` | `services/gps_wagons.py:110,121` | `gps_wagon_segments.selected_km` (sum over period) | its own number, independent of ledger |
| /dashboard/os/wialon | `app/dashboard/os/wialon/page.tsx:243-249` ("Пробег, км" = `unit.cnm`) | `routers/wialon.py` list units | `wialon_units.cnm` (ABSOLUTE counter) | raw Wialon value |
| /dashboard/os/gtk | `app/dashboard/os/gtk/page.tsx` (no km/mileage field at all, grep empty) | `api.gtk.*` | `gtk_locomotives`, `gtk_carriages`, trains | none; detail drawer data `recent_mileage_logs` (legacy `gtk_wagon_mileage_log`) is shown on the assets page (`app/dashboard/directories/assets/page.tsx:938-942`) |
| /dashboard/maintenance | `app/dashboard/maintenance/page.tsx:589,807,929,1192` (`item.mileage`, `item.remainingKm`) | `services/maintenance.py:756,823` | `fixed_assets.mileage`; plan `trigger_mileage`/obligation `due_km`; pace from `mileage_history`/`asset_meter_daily`/ledger | reuses the TOIR-scale value; `mileage=None` for untrusted wagons (`maintenance.py:823`) |
| /dashboard/directories/assets | `page.tsx:2433` `formatKm(a.mileage)`; wagon drawer `api.wagonMileage.summary/openings` (:599-600) | fixed-assets router, `routers/mileage.py` | `fixed_assets.mileage`; ledger + opening balances | reuses TOIR value; drawer shows ledger |
| also: /dashboard/scales (`cards.tsx:66`), work orders (`ViewEditOrderModal.tsx:253`) | | | `fixed_assets.mileage` | reuse |
| voice assistant | `services/assistant/handlers/gps.py:179` | `gps_assessment` fused | `gps_day_assessment.fused_m` | reuses fused |

So there are FOUR different notions of "mileage": (1) absolute Wialon counter (os/wialon), (2) TOIR-scale cumulative (`fixed_assets.mileage`: maintenance, assets, scales, WO), (3) per-day track/GTK/fused metres (gps), (4) wagon km from segments (gps/wagons) vs ledger (TOIR). Pages (2) and (1) are labelled identically "Пробег, км" without saying the scale.

### 3.2 Locomotives — 15 assets with both GTK and Wialon links (SQL, ordered by inv_number)
Columns: TOIR = `fixed_assets.mileage`; cnm = `wialon_units.cnm` (os/wialon page); off = cnm - TOIR; cnm growth = `last_cnm - baseline_cnm` (state); trk/gtk/fused/odo = sums of `gps_day_assessment` for local days 2026-11-15..11-21 (km); gtkdays = `sum(gtk_gps_days.distance_m)` same days; TOIR7d = `max(mileage_history)` before 11-22 minus before 11-15.

| inv | type | TOIR | cnm | cnm growth since baseline | Wialon track 7d | GTK 7d (assess / gtk_days) | fused 7d | odo 7d | TOIR 7d |
|---|---|---|---|---|---|---|---|---|---|
| 37017 | diesel | 0 | 63480 | - (stale, no state) | 0.0 | 151.0 / 151.0 | 152.2 | - | - |
| 37045 | diesel | 121 | 78538 | 128 | 15.1 | 71.2 / 71.2 | 48.3 | 28.5 | 83 |
| 37047 | diesel | 318 | 31081 | 380 | 189.1 | 240.0 / 240.0 | 211.2 | 64.0 | 247 |
| 37049 | diesel | 235 | 147467 | 363 | 98.5 | 220.8 / 220.8 | 176.9 | 167.2 | 197 |
| 37063 | diesel | 0 | 89349 | 0 | 0.0 | 352.6 / 352.6 | 354.4 | - | - |
| 37064 | diesel | 0 | 80825 | - | 0.0 | 81.4 / 81.4 | 91.3 | - | - |
| 37065 | diesel | 0 | 90712 | - | 0.0 | 0.4 / 0.4 | 0.5 | - | - |
| 37066 | diesel | 251 | 78430 | 311 | 118.1 | 132.1 / 132.1 | 128.2 | 29.0 | 184 |
| 37070 | loco | 861 | 190902 | 934 | 479.7 | 578.8 / 578.8 | 577.4 | 269.0 | 644 |
| 37073 | loco | 1012 | 181152 | 1270 | 524.2 | 716.6 / 716.6 | 724.3 | 320.0 | 678 |
| 37075 | loco | 850 | 209736 | 1039 | 495.6 | 191.7 / 191.7 | 516.6 | 308.3 | 664 |
| 37076 | loco | 823 | 195162 | 1103 | 297.4 | 196.7 / 196.7 | 297.4 | 119.6 | 497 |
| 37077 | loco | 865 | 189990 | 1139 | 313.4 | 339.5 / 339.5 | 407.5 | 178.0 | 496 |
| 37078 | loco | 949 | 175667 | 965 | 551.2 | 264.6 / 264.6 | 594.7 | 330.0 | 756 |
| 37079 | loco | 195 | 158422 | 250 | 11.0 | 0.0 / 0.0 | 11.0 | 63.0 | 120 |

Findings from the table (all VERIFIED by the SQL above):
1. Wialon-silent units (37017, 37063, 37064): GTK recorded 151 / 353 / 81 km in 7 days, TOIR mileage is 0 (PRB-01).
2. TOIR is below the counter growth for ALL 12 assets that have state (e.g. 37073: 1012 vs 1270; 37076: 823 vs 1103; 37077: 865 vs 1139) (PRB-05). Reason confirmed for 37079: `mileage_history` rows step exactly +1.00 per hour and the odometer-to-TOIR offset jumps from 158172 to 158227 (+55 km, 28 % of TOIR 195) between 2026-11-10 18:28 and 2026-11-13 12:03, a window whose readings are classified HELD with `source_time_policy_pending` (old ingest policy) and were never re-processed.
3. Four different 7-day figures for the same loco (37070: track 480, GTK 579, fused 577, odometer 269, TOIR 644). The odometer figure undercounts because odo_m is None on 3 of 6 active days (see PRB-08).
4. 37079 parked-ish: track 11 km, GTK 0, but TOIR +120 km in 7 days (counter creeps +1 km per ~1 h) (PRB-06).
5. Fleet-wide (86 Wialon-linked locos/diesels, same 7 days): sum TOIR 36 460 km, fused 33 212, Wialon track 23 560, GTK 23 594; TOIR > 1.3*fused+10 for 26 assets, < 0.7*fused-10 for 12, consistent for 48.
6. Not shown above (see section 3.4): `os/wialon` shows cnm (e.g. 190902) next to TOIR 861 for the same unit.

### 3.3 Wagons — 10 wagons with the highest TOIR mileage (SQL)
| inv | TOIR mileage (assets page, maintenance) | approved opening | ledger active sum / rows | gps_wagon_segments sum (gps/wagons) range | legacy gtk_wagon_mileage_log |
|---|---|---|---|---|---|
| 37562 | 227 | 132 | 95 / 1 | 1604.5 km (2026-11-04..11-22) | 132 |
| 37687 | 217 | 129 | 88 / 1 | 1299.4 | 129 |
| 37539 | 194 | 123 | 71 / 1 | 1267.8 | 123 |
| 38498 | 101 | 0 | 101 / 1 | 1700.2 | - |
| 38506 | 101 | 0 | 101 / 1 | 1707.2 | - |
| 38653 | 101 | 0 | 101 / 1 | 1515.4 | - |
| 38444 | 101 | 0 | 101 / 1 | 1362.5 | - |
| 38495 | 101 | 0 | 101 / 1 | 1597.3 (from 11-05) | - |
| 38473 | 101 | 0 | 101 / 1 | 1316.9 | - |
| 38939 | 101 | 0 | 101 / 1 | 1707.2 | - |

Same wagon, 12-17x different numbers between the TOIR value and /dashboard/gps/wagons. Reason: the ledger engine last ran 2026-11-16 09:21 (one ledger row per wagon) while `gps_wagon_segments` is recomputed every ~10 min (latest `computed_at` 2026-11-22 08:16). Totals: 481 wagons with TOIR mileage > 0 sum 36 084 km; 518 wagons in segments sum 748 196 km. Wagon 38498 per-day segments: 11-15 132.1, 11-16 122.6, 11-17 88.6, 11-18 70.2, 11-19 89.7, 11-20 98.4, 11-21 106.6, 11-22 64.6 km (loco 180/218); several days are `single_source`/`low` with Wialon track 57.4 or 0.016 km vs GTK 100.9 / 105.9 km.
Segments table: 10 161 rows; basis fused_track/high 7 930 rows, single_source/low 1 826 rows (102 757 km), held/none 285, fused_track/medium 92, track/medium 28.
Wagon ledger status: active ESTIMATED 506 rows (35 699.9 km), active CONFIRMED 1, active HELD 3, superseded 2 361; 589 approved openings (avg 0.7 km).

### 3.4 Other discrepancies seen on pages
- /dashboard/os/wialon "Пробег, км" = `wialon_units.cnm` (absolute); same unit in assets/maintenance = TOIR scale. No label or conversion shown (PRB-15).
- `special_self_propelled` unit 80359: Wialon counter growth 755 km since baseline, TOIR mileage frozen at 88 (last `mileage_history` 2026-11-10). Cause: `LOCOMOTIVE_MILEAGE_TYPES = {locomotive, diesel}` (`services/assets.py:511`) vs `LOCOMOTIVE_TYPES = (locomotive, diesel, special_self_propelled)` (`repositories/asset_map.py:20`) (PRB-07).
- Distance verdict distribution, local days 2026-11-01..11-21 (`gps_day_assessment`, 21 days): match/ok 476 days (Wialon 38 500 km vs GTK 37 623); wialon_gap/both_gaps 277 days (Wialon 1 124 km vs GTK 16 712 — Wialon track missing); gtk_gap/gtk_gaps 181; gtk_gap/gtk_no_day 159; gtk_gap/gtk_dead 133; idle 137; no_data 73; minor_diff 111 in total. 165 `gtk_gps_days` rows since 11-01 have `distance_m = 0` although `points > 0` (frozen GTK tracker).
- Odometer third source present on only 327 of 1 045 active days (wialon_m >= 5 km): 31 %; of the days with odo, `odo_agrees` true 292, false 62.

---------------------------------------------------------------------

## 4. MILEAGE -> MAINTENANCE (TO)

- Value used: `fixed_assets.mileage` (TOIR scale). `services/maintenance.py:756,823`; obligations `maintenance_obligations.py:461`.
- Where last-repair mileage is stored: `asset_maintenance_baseline.km` (key asset_id+interval_id) written by `upsert_baseline` (`maintenance_lifecycle.py:108-126`) on completion (`:172`), manual set (`:416`), bulk import (`:700`). Completed plan km: `maintenance_plan.completed_km`. VERIFIED: 0 rows in `asset_maintenance_baseline`, 0 in `maintenance_plan`, 0 in `work_orders`, 0 in `maintenance_decision`.
- Propagation timing:
  * Wialon pull (2 min) -> `receive_wialon_update` -> `fixed_assets.mileage` + `mileage_history` + `reconcile_asset_plans` in a savepoint (`services/assets.py:641-657`): immediate for locomotives/diesel.
  * Hourly job `run_periodic_maintenance` (`maintenance_lifecycle.py:680-695`, `maintenance_job_interval_minutes=60`, first run 90 s after start): `snapshot_meters` (only Wialon-linked assets), health fix, `reconcile_all` (single transaction + advisory lock).
  * Wagons: `reconcile_asset_plans` only inside `run_wagon_mileage` (`wagon_mileage_run.py:860`), i.e. never, while the engine is off.
  * GTK mileage changes never propagate to TO (GTK is not a mileage input for locomotives).
  * Pace book is cached 20 min and reset by the hourly job (`maintenance_obligations.py:60,82`).
- Interval config (SQL `maintenance_intervals`): loco/diesel ТО-1 5 000 km, ТО-2 15 000, ТО-3 30 000, ТР-1 100 000, ТР-2 200 000, ТР-3 400 000, СР 800 000, КР 1 600 000 km; wagons have no active km interval (only a test interval, inactive). TOIR mileage today: loco max 1 300, diesel max 1 504 -> so every km interval is far from its limit on the TOIR scale.
- Without a baseline, `evaluate_asset` assumes the last service was at the last multiple of the interval on the TOIR scale (`maintenance_obligations.py:497-500`: `trigger = next_mileage_threshold(current_km, limit); baseline = trigger - limit`). With TOIR mileage starting near 0 this means "last ТО-1 at 0 km, due at 5 000", unrelated to the real service state of a locomotive with 150 000+ km on the counter. `confidence = low` (`maintenance_engine.py:325`) and no plan is created while state == forecast (`persist_obligations` :540).
- Concrete computation check (loco 37073, interval ТО-1): TOIR mileage 1012 (SQL) -> baseline 0, due 5000, remaining 3988 km. Pace from `mileage_history` day buckets over the window with the engine's definition (linear quantile = `percentile_cont`): n=12 observed days, p25 0.8, p50 57.5, p75 119.5 km/day (SQL). `days_to_limit_p75 = ceil(3988/119.5) = 34` (SQL result 33 before ceil rounding of the exact value). Since lead_days = 7 the window opens in about 27 days -> state `forecast`, no plan. Reproduced the formula inputs only; I could not read the engine's own output (no API access), so the final persisted markers are NOT VERIFIED. No asset can currently be overdue by km: max TOIR mileage 1 504 < 5 000.
- Manual mileage effect: none possible (manual PATCH disabled, `services/assets.py:514-524`); baseline `odometer_km` input is converted with the live offset (`resolve_baseline_km`).
- Stale handling: `ctx.is_stale` if last Wialon message older than 24 h (`maintenance_stale_hours`) -> confidence "stale", but the mileage value is still shown as if current.
- Hours meter: `hours_current` is the raw `wialon_units.cneh` (`maintenance_obligations.py:355-369`), NOT the gated `wialon_counter_state.engine_hours` (PRB-12).

---------------------------------------------------------------------
