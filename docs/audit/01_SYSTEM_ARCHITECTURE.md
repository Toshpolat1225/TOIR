# 01 — System architecture

> READ-ONLY audit, 2026-11-22. Nothing was changed in code, config, DB or containers. Every finding is labelled VERIFIED (code line / SQL result seen) or UNVERIFIED / POTENTIAL RISK. Browser/API behaviour of the pages was NOT tested (no credentials; creating an account would write to the live DB).
> Source: worker C (architecture + modules)

## A. SYSTEM ARCHITECTURE MAP

### A1. Frontend
- Next.js 15 App Router, pages in `app/dashboard/**`, one shared client `lib/api.ts` (2637 lines, `request<T>()` at `lib/api.ts:275`, 401 -> token refresh + single retry at :316-333). No React-Query/SWR, no client-side response cache: every page owns `useState` + `useEffect` + `api.<resource>.<method>()`. Pure view helpers in `lib/*-view.ts` (gps-view, map-view, scales-view, maintenance-view).
- Refresh mechanisms actually present (grep `setInterval|useAutoRefresh|useRealtime`, VERIFIED):
  | Page | Mechanism |
  |---|---|
  | `/dashboard/gps` | `useAutoRefresh` 60 s, skipped when tab hidden, aborts previous request (`gps/_components/ui.tsx:141-163`, `gps/page.tsx:94`), pause button |
  | `/dashboard/gps/wagons` | same hook, 60 s (`gps/wagons/page.tsx:76`) |
  | `/dashboard/map` | raw `setInterval` 60 s (`map/page.tsx:21,64-66`), NOT paused in hidden tab, no abort |
  | `/dashboard/os/gtk`, `/os/wialon`, `/scales`, `/maintenance` | none (manual reload / button "Обновить"); no realtime |
  | `/dashboard/directories/assets` | WebSocket `useRealtime` (`page.tsx:1672`) |
- WebSocket (`lib/use-realtime.ts`, backend `app/realtime.py` + `routers/realtime.py`): PostgreSQL `LISTEN/NOTIFY` channel `toir_changes` (trigger function in `postgres/schema.sql:964-985`, scoped in alembic `0004_realtime_scopes.py`) -> in-memory `asyncio.Queue` -> per-client filter. `ALLOWED_TABLES = {work_orders, fixed_assets, users}` (`realtime.py:16`). So GPS/Map/Scales/GTK/Wialon/Maintenance data is NEVER pushed.
- Map libs: Leaflet+OSM tiles (`map/_components/OsmAssetMap.tsx:121`, `TrackMap.tsx:41`), Google Maps only if `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` is set (`map/page.tsx:20,95`).

### A2. Backend (FastAPI, `backend/app`)
- Layers: `routers/` -> `services/` -> `repositories/` -> `models/`+`schemas/`. Some services run raw SQL (`gps_overview`/`repositories/gps.py` `_DAY_SQL`, `repositories/unified_assets.py` text SQL, `scales*`).
- Global HTTP middleware (`main.py:~165-250`): redacts Wialon query token, writes fallback audit row for every un-audited POST/PUT/PATCH/DELETE (except `/scales/ingest`, assistant), localises some JSON responses.
- Routers: auth, users, permissions, references, nomenclature, assets, asset_conflicts, asset_links, wialon, wialon_pull, gtk, mileage, work_orders, maintenance, asset_map, gps, assistant, scales, localization, realtime, analytics, dashboard, ml, tmc_documents, audit_logs, health.
- Integrations (`backend/app/integrations`): `wialon_client.py` (JSON API `/wialon/ajax.html`, token auth, pull), `gtk_client.py` (logs in to the GTK web site with CSRF cookie and PARSES an HTML page that carries Python-literal blobs: `REQUIRED_BLOCKS=("locomotives","carriages","trains","carriageStates")`, hard-coded `TZ=UTC+5` at `gtk_client.py:~15`), `gtk_gps_client.py` (GTK JSON plugins `core_vehicles_plugin`, `core_tracks_plugin`, GET only), `gtk_adapter.py`/`base.py` (SourceObject protocol). Scales: NOT a backend integration: external Windows collector `scripts/scales_collector/collector.py` (reads two `Bridge_Scale.mdb` read-only) pushes `POST /api/v1/scales/ingest` (Bearer `SCALES_INGEST_TOKEN`, `routers/scales.py:26-48`). Wialon also has a legacy push endpoint `POST|GET /api/v1/wialon/input` (`routers/wialon.py:263-270`, own ingest token). 1C: NONE (see MOD-16).

### A3. Background jobs (every loop found; VERIFIED in code)
| Job | Where | Interval | Writes | Enabled by |
|---|---|---|---|---|
| DB event listener + dispatcher (websocket) | `realtime.py:91,133`, started `main.py` lifespan | continuous (reconnect 30 s) | none (memory) | always |
| Audit retention | `services/audit_log.py:462-473` | 24 h | DELETE audit_logs (365 d), position history (180 d), gtk_gps_runs (90 d), assistant_queries (180 d), assistant_pending (7 d) | always |
| Wialon pull | `services/wialon.py:191-204` | `WIALON_SYNC_INTERVAL_MINUTES` default 2 | `wialon_units` upsert, `asset_position_history`, `wialon_raw_receipts`/`wialon_odometer_readings`/`wialon_counter_state`/`wialon_rejected_readings`, `fixed_assets.wialon_last_sync/speed/online`, locomotive `fixed_assets.mileage` + `mileage_history` (delta only), triggers `reconcile_asset_plans` | `settings.wialon_pull_enabled` |
| GTK pull | `services/gtk.py:977-989` | `GTK_SYNC_INTERVAL_MINUTES` (compose default 10; live runs are ~5 min apart: 08:13, 08:18) | `gtk_raw_snapshots`, `gtk_locomotives`, `gtk_carriages`, `gtk_trains`, `gtk_train_members`, `gtk_membership_observations`, `gtk_sync_runs`, passport proposals (`number`, `model_id` via `asset_field_changes`), then `run_wagon_mileage` ONLY IF `wagon_mileage_engine_enabled` | `gtk_pull_enabled` (= sync_enabled AND credentials) and not `auto_sync_stopped()` (in-memory flag, lost on restart) |
| GTK GPS pull + analytics | `services/gtk_gps.py:240-251`, `_analytics_cycle` :222 | `GTK_GPS_SYNC_INTERVAL_MINUTES` (10; observed runs 08:05, 08:15) | `gtk_gps_units`, `gtk_gps_days`, `gtk_gps_runs`, `asset_position_history`(gtk_gps), then `gps_day_assessment`, `gps_wagon_segments` | `gtk_gps_pull_enabled` |
| Maintenance cycle ("Tirik reja") | `services/maintenance_lifecycle.py:680-695` | `MAINTENANCE_JOB_INTERVAL_MINUTES` default 60, first run after 90 s | `asset_meter_daily` snapshots, health repair, `maintenance_plan` create/reconcile (advisory lock) | `maintenance_job_enabled` default True (config.py:92; not in compose so default) |
| Backup | compose service `backup`, `scripts/backup_loop.sh` | daily 21:00 UTC | `./backups/auto-*.dump` | always |
| Whisper | compose service `whisper` | on demand | none | optional |
| Scales collector | external Windows task (`scripts/scales_collector/install_task.ps1`) | 60 s (DECISIONS #51) | via `/scales/ingest`: `scale_posts`, `scale_trains`, `scale_weighings`; then `rematch` derives `scale_train_carriages`, `loco_asset_id` | user's PC |
No scheduler writes anything related to 1C. Wagon mileage engine is NOT scheduled in the live container: `WAGON_MILEAGE_ENGINE_ENABLED` is not forwarded by `docker-compose.yml` (only `WAGON_MILEAGE_TRACK_FALLBACK` is) and the default is False (`core/config.py:60`) -> MOD-01.

### A4. Database (live: `information_schema`/`pg_constraint`/`pg_indexes`)
Relevant tables with live row estimates (pg_class.reltuples; exact counts where noted): `fixed_assets` 1075 (exact), `asset_source_links` 756 (exact: 669 gtk, 87 wialon), `asset_field_changes` 287, `wialon_units` 179, `gtk_locomotives` 77, `gtk_carriages` 688, `gtk_trains` 116, `gtk_train_members` 1767, `gtk_gps_units` 242, `gtk_gps_days` 3622, `asset_position_history` 1.94 M (630 MB), `wialon_odometer_readings` 536 k (476 MB), `wialon_raw_receipts` 790 k, `gps_day_assessment` 2736, `gps_wagon_segments` 10161, `scale_trains` 55 533, `scale_weighings` 599 731, `scale_train_carriages` 15 943, `maintenance_intervals` 9 (exact), `maintenance_plan` 0 (exact), `asset_maintenance_baseline` 0 (exact), `maintenance_decision` 0 (exact), `maintenance_settings` 0 (exact), `wagon_mileage_ledger` 2871.
Key constraints (VERIFIED):
- `fixed_assets`: PK id; UNIQUE `wialon_id`, UNIQUE `gtk_id` (legacy mirror columns), UNIQUE partial `accounting_inv_number`; NO unique on `inv_number` (index only, DECISIONS #31); FK `section_id` (SET NULL), `model_id`, `status`->`fixed_asset_statuses.code`, `asset_type`->`fixed_asset_types.code`; no "archived" column: archive state = `decommissioned_at` (0 assets decommissioned) or status `out_of_service`.
- `asset_source_links`: PK id; FK asset_id ON DELETE CASCADE; CHECK source IN (wialon,gtk,vesavoy,onec), status IN (active,ended), link_method IN (manual,migrated,import); UNIQUE partial `(asset_id, source) WHERE active` and UNIQUE partial `(source, external_id) WHERE active`. `external_id` is text with no kind (locomotive vs carriage).
- `gtk_locomotives`/`gtk_carriages`/`gtk_trains`/`gtk_gps_units`: PK `gtk_id` (separate id spaces; no FK from links to them).
- `gtk_train_members`: UNIQUE partial `(train_gtk_id, kind, object_gtk_id) WHERE observed_to IS NULL`.
- `scale_trains`: UNIQUE `(post_id, src_id)`, CHECK match_status IN (pending, ok, no_loco, no_gtk_train, excluded), FK `loco_asset_id` SET NULL; `scale_train_carriages`: PK `(train_id, carriage_gtk_id)`, FK `asset_id` SET NULL; `scale_weighings`: UNIQUE `(train_id, src_id)`.
- `maintenance_plan`: UNIQUE `(asset_id, interval_id, trigger_mileage)`, CHECK status set, FK asset CASCADE, interval RESTRICT; `asset_maintenance_baseline`: PK `(asset_id, interval_id)`.
- `gps_wagon_segments`: UNIQUE `(carriage_gtk_id, train_gtk_id, period_from)`; FK wagon/loco asset SET NULL.
- `wialon_units`: PK `unit_id`, CHECK lat/lon range.
There are NO foreign keys between `asset_source_links.external_id` and the GTK/Wialon mirror tables (orphan protection is by code only).
Real-time/caches: no server-side caches/TTLs found in the modules audited (each request recomputes from tables; GPS overview filters/sorts in Python after loading all locomotives, `services/gps_overview.py:162-270`); `maintenance_obligations.reset_pace_book()` is an in-process pace cache reset per cycle (`maintenance_lifecycle.py:673`). Staleness is therefore bounded only by the pull intervals above.

---------------------------------------------------------------------------------------------------

## Verdict of the architecture worker

## F. VERDICT: is TOIR one integrated system?

**Answer: (b) integrated with gaps.** It is built on one identity spine and shared services, not eight silos, but several links are broken, partial or missing, and a few modules are effectively idle or stale.

Proof of REAL links (VERIFIED):
1. One asset identity: all 8 modules key on `fixed_assets.id`, and every external join goes through `asset_source_links` (Map `repositories/asset_map.py:80-108`, GPS `repositories/gps.py:38-48`, Scales `services/scales.py:176-199`, ТО `maintenance_obligations` imports `AssetSourceLink`, Wialon pull `find_wialon_asset` -> `asset_links_service`). DB-level uniqueness of active links; 0 orphans, 0 duplicates.
2. Map and GPS share the position verdict function (`gps_compare.position_check`) and the same links.
3. Wagons derive position/km from locomotive + GTK membership; Map draws the same trains (`train_formation`); Scales reuses GTK membership history and links.
4. Wialon pull -> `fixed_assets.mileage` -> `reconcile_asset_plans` (ТО) is a live in-process chain; Wialon, GTK and GTK-GPS data are fresh within seconds/minutes on the live DB.
5. Справочник is the only editor of links and passport fields and receives realtime events.

Proof of BROKEN / MISSING links:
1. Wagon mileage chain is not scheduled in the deployed container (MOD-01) so ledger -> ТО/Справочник for wagons is stale (6 days).
2. Scales collector silent ~41 h (MOD-02) and wagon-level scale linkage only covers ~2 weeks (1 258 of 55 533 trains `ok`).
3. ТО has no data (0 plans, 0 baselines) — the Wialon -> ТО chain exists in code but nothing is produced (MOD-03).
4. Two identity stores drift (MOD-04): 44 wagons and 13 assets carry an id in the legacy column but no link.
5. 401 assets (248 wagons, 129 tank cars, 24 platforms) have no source link at all; 153 of them (tank_car/platform) are structurally excluded from GTK matching/passport proposals (MOD-06).
6. 1C: no integration, `accounting_inv_number` empty for all assets (MOD-16). Vesovoy is not represented in `asset_source_links` (CHECK allows it, unused).
7. Staleness/online/timezone rules are re-implemented per module (MOD-08, MOD-09), so the same unit can look "online" on one page and "stale" on another.
8. No cross-module push: realtime covers only work_orders/fixed_assets/users (MOD-13).

---------------------------------------------------------------------------------------------------
