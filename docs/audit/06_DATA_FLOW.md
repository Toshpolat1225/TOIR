# 06 — Data flow maps

> READ-ONLY audit, 2026-11-22. Nothing was changed in code, config, DB or containers. Every finding is labelled VERIFIED (code line / SQL result seen) or UNVERIFIED / POTENTIAL RISK. Browser/API behaviour of the pages was NOT tested (no credentials; creating an account would write to the live DB).
> Source: workers C, A, B

## Cross-module

## D. DATA FLOW (GENERAL)

Notation: SOURCE -> INTEGRATION -> BACKEND -> DATABASE -> API -> FRONTEND -> OTHER MODULES.

- Transport id (asset identity): SOURCE operator (manual link UI) / GTK carriage|locomotive id / Wialon unit id -> `asset_links.link/unlink` (+mirror columns) or `gtk.save_links` -> `services/asset_links.py` -> `asset_source_links` (truth) and `fixed_assets.wialon_id|gtk_id` (mirror) -> `/fixed-assets/{id}/links`, `/fixed-assets/unified` -> Справочник, GTK, Wialon pages -> consumed by Map, GPS, Wagons, Scales, Wialon pull, GTK GPS, ТО. Break: mirror drift (44+13 rows).
- Inventory number: SOURCE passport JSON import (DECISIONS #31) / manual -> `asset_passport_import`, `assets.create/update` -> `fixed_assets.inv_number` (non-unique, 15 dup groups) -> `/fixed-assets*` -> Справочник; GTK `inventory_number` is a separate mirror column (`gtk_carriages`, `gtk_locomotives`); used by `asset_map.find_gtk_candidate`, GTK match report, assistant search; Scales does NOT use it (uses GTK garage number).
- GPS coordinates: SOURCE Wialon (pull 2 min) and GTK GPS (pull 10 min; carriage coordinate from GTK page) -> `wialon_client`/`gtk_gps_client` -> `wialon_units.lat/lon/position_at`, `gtk_gps_units.lat/lon/position_at`, `gtk_carriages.lat/lon`, `asset_position_history` (thinned track) -> `/map/assets`, `/map/trains`, `/gps/overview`, `/gps/wagons` -> Map, GPS, Wagons. Winner: Map `build_points` order = locomotive with GTK unit: NEWER fix of Wialon/GTK-GPS; else own Wialon; else wagon = its locomotive's train position; else own GTK carriage coordinate. GPS page shows BOTH fixes and the verdict, and (for the "Карта TOIR" layer) the point the Map would draw; they agree for locomotives because of the shared `position_check`. Wagons have no GPS of their own anywhere.
- Wagon state (composition, in-train, active): SOURCE GTK -> `gtk_client` HTML scrape (10 min) -> `gtk.sync_gtk` -> `gtk_carriages`, `gtk_trains`, `gtk_train_members` (+`gtk_membership_observations`), `gps_wagon_segments` -> `/gtk/*`, `/gps/wagons`, `/map/trains` -> GTK page, Wagons page, Map; Scales reads membership history. (Details: sostav auditor.)
- Scales data: SOURCE `Bridge_Scale.mdb` x2 -> Windows collector (60 s) -> `POST /scales/ingest` -> `scales.ingest` + `rematch` -> `scale_*` -> `/scales/*` -> Весовая; links to assets through GTK (C4); Assistant uses `/scales`. Not shown in Map/GPS/ТО.
- TO state: SOURCE baselines (user input, passport/1C import), intervals (`maintenance_intervals`), meters (Wialon delta, wagon ledger) -> hourly `run_cycle` + on each Wialon update `reconcile_asset_plans` -> `maintenance_plan`, `asset_meter_daily`, `maintenance_decision` -> `/maintenance-*` -> ТО page; work orders created from the page -> `work_orders` (separate module). No flow from ТО back to Map/GPS/Scales.
- Update timestamps: Wialon `wialon_units.last_synced_at`/`last_message_at`, `fixed_assets.wialon_last_sync`; GTK `*.last_synced_at`, `gtk_sync_runs.finished_at`; GTK GPS `gtk_gps_units.last_synced_at`, `gtk_gps_runs`; scales `scale_posts.last_pull_at`, `last_weighing_at`; Maintenance has NO "data as of" shown beyond engine freshness flags; displayed to the user on: GPS (`обновлено` + feed health), Map (`обновлено`), GTK (last run), Scales (per post), Справочник (`wialonLastSync`); NOT displayed on: Wialon page (per row only), Wagons page (state only), ТО page.
- Probeg (mileage): covered by the probeg auditor — Wialon odometer gate -> `fixed_assets.mileage` / wagon ledger -> ТО and Справочник; see MOD-01 for the unscheduled wagon engine.
- Sostav (train composition): covered by the sostav auditor — GTK membership -> Wagons/Map/Scales.

### Live freshness (SELECT max timestamps, now = 2026-11-22 08:20:33 UTC)
| Table/field | max | Age |
|---|---|---|
| wialon_units.last_synced_at / last_message_at / position_at | 08:20:19 / 08:20:16 / 08:20:16 | seconds |
| gtk_locomotives / carriages / trains `last_synced_at` | 08:19:16 | ~1 min |
| gtk_sync_runs last | ok, 08:18:50 -> 08:19:16 | ~1 min |
| gtk_gps_units.last_synced_at / position_at | 08:15:36 / 08:15:22 | 5 min |
| gtk_gps_runs last | success 08:15:36 | 5 min |
| gtk_gps_days max day / fetched_at | 2026-11-22 / 08:15:36 | 5 min |
| gps_day_assessment.computed_at / gps_wagon_segments.computed_at | 08:16:02 / 08:16:03 | 4 min |
| asset_position_history.at | 08:20:09 | seconds |
| wialon_odometer_readings.received_at | 08:20:19 | seconds |
| mileage_history (wialon) | 08:20:23 | seconds |
| scale_posts.last_pull_at (post 97 / 93) | 2026-11-20 15:38:14 / 15:39:20 | ~41 h |
| scale_trains.started_at / ingested_at | 2026-11-20 15:12:10 / 15:27:26 | ~41 h |
| wagon_mileage_ledger.created_at | 2026-11-16 09:21:04 | ~6 days |
| maintenance_plan / baseline | no rows | - |

---------------------------------------------------------------------------------------------------

## Probeg

## DATA FLOW (PROBEG)

```
SOURCE
  Wialon unit counters (cnm km, cneh h, last message time, lat/lon)      [pull every 2 min; push endpoint present but never counts]
  GTK get_vehicles + core_tracks (distance METRES per local day, points) [every ~10 min]
  GTK train membership (trains/carriages/locomotives)                    [every ~5 min, gtk_sync_runs]
  Manual: wagon opening balance (maker/checker); maintenance baselines (0 rows)
  Passport/1C: no mileage import
        |
INTEGRATION
  integrations/wialon_client.py (cnm -> mileage) ; integrations/gtk_gps_client.py ; gtk_client/gtk_adapter
  main.py lifespan tasks: run_periodic_wialon_sync, run_periodic_gtk_sync (+run_wagon_mileage only if WAGON_MILEAGE_ENGINE_ENABLED),
                          run_periodic_gtk_gps_sync (+gps_assessment.assess_recent + wagon_gps.compute_segments after each cycle),
                          run_periodic_maintenance (hourly)
        |
BACKEND
  wialon.py::sync_wialon_assets -> wialon_ingestion::ingest_wialon_reading -> wialon_quality::evaluate (gate)
  -> assets.py::receive_wialon_update (loco/diesel only: mileage += delta, mileage_history row, reconcile_asset_plans)
  gtk_gps.py::sync_gtk_gps -> gps_assessment (+gps_analytics, gps_compare) -> gps_day_assessment
  wagon_gps.py::compute_segments -> gps_wagon_segments (read-only for TOIR)
  wagon_mileage_run.py (OFF) -> wagon_mileage_ledger -> fixed_assets.mileage (wagons) -> maintenance reconcile
  maintenance_lifecycle.py::snapshot_meters/run_cycle -> maintenance_obligations (pace book, evaluate_asset) -> maintenance_plan
        |
DATABASE
  wialon_units, wialon_odometer_readings, wialon_counter_state, wialon_rejected_readings, wialon_raw_receipts,
  fixed_assets.mileage, mileage_history, asset_meter_daily, asset_position_history,
  gtk_gps_units, gtk_gps_days, gtk_gps_runs, gps_day_assessment, gps_wagon_segments,
  wagon_mileage_opening_balances, wagon_mileage_ledger, mileage_calculation_runs/inputs,
  asset_maintenance_baseline, maintenance_plan, maintenance_intervals
        |
API
  /api/v1/gps/overview|health|asset|wagons|wagon ; /api/v1/wialon/* units ; /api/v1/gtk/* ; /api/v1/fixed-assets (mileage, mileage-history, links)
  /api/v1/wagon-mileage/* (openings, summary) ; /api/v1/maintenance-schedule|plans|baselines|kpis|health
        |
FRONTEND (lib/api.ts)
  /dashboard/gps, /dashboard/gps/[assetId], /dashboard/gps/wagons  -> gps_day_assessment / gps_wagon_segments
  /dashboard/os/wialon -> wialon_units.cnm (absolute)
  /dashboard/os/gtk -> no mileage numbers
  /dashboard/maintenance, /dashboard/directories/assets, scales, work-orders -> fixed_assets.mileage (TOIR scale)
        |
OTHER MODULES
  maintenance (pace, due km, overdue, plans), work orders (current mileage), ML (repositories/ml.py reads mileage_history),
  voice assistant (fused_m), asset map (/dashboard/map), audit log (mileage_history is excluded from per-row audit)
```

### Freshness (SQL, 2026-11-22 ~08:18-08:24 UTC) and intervals (code/config)
| Source | Last timestamp | Interval |
|---|---|---|
| `wialon_units.last_synced_at` | 08:18:15 UTC (max `last_message_at` 08:18:13); 179 units, 87 linked | Wialon pull: `settings.wialon_sync_interval_minutes` default 2 (`core/config.py:44`); observed receive spacing 2 min. DB `wialon_settings.sync_interval_minutes=5, auto_sync_enabled=t, last_sync_status 'ok: found=87, updated=87, not_found=90'` is NOT used by the loop (`services/wialon.py:204`) |
| `wialon_odometer_readings` latest id 988870 | received 08:18:15 | same job |
| `mileage_history` | 08:18:18 (2 110 rows in last 3 days, all source wialon) | same job |
| `wialon_counter_state` | 87 rows, updated 08:18:15 | same job |
| `gtk_gps_runs` | latest success 08:15:36 -> 08:16:02 (242 units, 76 tracks, 0 failed), prior 08:05, 07:54 | `GTK_GPS_SYNC_INTERVAL_MINUTES` default 10 (ge 5) |
| `gtk_gps_days` | max day 2026-11-22, fetched 08:15:36 | same |
| `gps_day_assessment` | max day 11-22, computed 08:16:02 | after each GTK GPS cycle |
| `gps_wagon_segments` | computed 08:16:03 | after each GTK GPS cycle (back 3 days) |
| `gtk_sync_runs` (membership) | 08:13:43 ok (37 trains, 688 carriages, 77 locomotives), prior 08:08:40 | `GTK_SYNC_INTERVAL_MINUTES` default 10 (ge 5); live appears 5 |
| `asset_meter_daily` | max day 2026-11-22 (174 rows for last 2 days) | hourly job `maintenance_job_interval_minutes=60` |
| `mileage_calculation_runs` (wagon engine) | LAST RUN 2026-11-16 09:21:10; 7 runs total (first 2026-11-15 16:32) | only if `WAGON_MILEAGE_ENGINE_ENABLED` (default false) |
| `wagon_mileage_ledger` | no rows created in last 3 days | same |

---------------------------------------------------------------------

## Sostav

## DATA FLOW (SOSTAV)

SOURCE
- GTK web system (host/user from settings; page path/query): trains with `locomotive_list`, `carriage_list` (with `order`), `begin_time`/`end_time`; carriage state (`is_loaded`, `state_duration`, lat/lon); GTK GPS API (own tracks/positions of locomotives) — separate job.
- Wialon (GPS of locomotives ONLY; units, positions, odometer, tracks).
- Scale PCs (posts 93, 97): trains (`Составы`) and weighed units (`Вагоны`), collector pushes to `/scales` API (no pull).
- TOIR operators: manual links (`asset_source_links`, 12 inventory-mismatch links), scale corrections (`loco_alias`, `train_exclude`, `train_gtk`).

INTEGRATION
- `GtkClient`/`GtkSourceAdapter` (B/integrations/gtk_client.py) every `gtk_sync_interval_minutes` (default 10, observed 5 min; B/services/gtk.py:977-989 `run_periodic_gtk_sync`, started in B/main.py:64); login-failure guard stops auto-sync after 3 consecutive failures (`_auto_sync_stopped`, in-memory, B/services/gtk.py:48-50, 223-232).
- Wialon pull every `wialon_sync_interval_minutes` default 2 (B/core/config.py:44; B/services/wialon.py:191-204); live: `wialon_units` updated to 08:22 today.
- GTK GPS pull `gtk_gps_sync_interval_minutes` default 10 (min 5) (B/services/gtk_gps.py:240-251); `asset_position_history` latest gtk_gps 08:15 / wialon 08:22 (s25).
- Scales collector (external) -> API; matching job recomputes derived columns of `scale_trains`.

BACKEND
- `services/gtk.py::sync_gtk` -> `repositories/gtk.py::upsert_mirror` + `sync_memberships` (open/close intervals, observations) -> `position_history.safe_record_gtk` -> `wagon_mileage_run.run_wagon_mileage` (if `wagon_mileage_engine_enabled`) -> `wagon_gps.compute_segments` (segments, last computed 2026-11-22 08:16).
- Read-side recomputation (no stored sostav model): `train_formation.live_trains`, `asset_map` + repo, `gps_wagons.list_wagons`, `gtk.get_train_detail`, `scales_matching.find_gtk_train/carriages_in_train`.

DATABASE
- `gtk_raw_snapshots` (full payload) -> `gtk_trains` / `gtk_locomotives` / `gtk_carriages` (mirrors, upsert, never deleted) -> `gtk_train_members` (intervals, history) + `gtk_membership_observations` -> `gps_wagon_segments`, `gtk_wagon_mileage_log`, `wagon_mileage_ledger`; `asset_source_links` (identity); `scale_trains` / `scale_weighings` / `scale_train_carriages` / `scale_corrections`.

API
- `/gtk/trains`, `/gtk/trains/{id}`, `/gtk/carriages`, `/gtk/locomotives`, `/gtk/status` (routers/gtk.py); `/fixed-assets/{id}/gtk`; `/map/trains`, `/map/assets`, `/map/history`; GPS wagons list/detail (`api.gps` wagons, key = asset UUID or `gtk-<carriage id>`); `/scales/trains`, `/scales/trains/{id}`, `/scales/wagon-card`.

FRONTEND
- /dashboard/os/gtk, /dashboard/gps/wagons, /dashboard/map (+ unplaced, history), /dashboard/scales (+ train, wagon, loco), /dashboard/directories/assets (GTK card), assistant (voice/text commands via `services/assistant`).

OTHER MODULES
- Wagon mileage ledger / opening balances (`wagon_mileage_*`), maintenance planning (uses mileage), conflict view of blocked locomotives (`repositories/conflict_views.py:92-106` counts affected wagons via open members), asset history (`asset_history.py`), audit log (`gtk_train_members` is audited, `services/audit_log.py:28`).

Freshness summary (at query time 2026-11-22 ~08:22 UTC): GTK mirror 08:19 (5 min), Wialon 08:22, GTK GPS 08:15, wagon segments 08:16, scales 2026-11-20 15:28 (stale ~41 h), GTK sync outage 2026-11-20 17:35 -> 2026-11-22 07:43 (~38 h).

---------------------------------------------------------------------
