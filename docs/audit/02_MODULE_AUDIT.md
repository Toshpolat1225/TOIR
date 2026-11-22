# 02 — Module audit (8 modules)

> READ-ONLY audit, 2026-11-22. Nothing was changed in code, config, DB or containers. Every finding is labelled VERIFIED (code line / SQL result seen) or UNVERIFIED / POTENTIAL RISK. Browser/API behaviour of the pages was NOT tested (no credentials; creating an account would write to the live DB).
> Source: worker C

## B. MODULE-BY-MODULE

Legend: perm = `require_permission` code. Role defaults from `core/permissions.py:61-63` and live `role_permissions`.
Live users: only 3 (admin x2, management x1; SELECT). No `master` or `operator` user exists on the live DB.

### B1. GPS Wialon<->GTK `/dashboard/gps`
- Files: `app/dashboard/gps/page.tsx` (451 l.), `_components/{GpsMap,GpsDrawer,HealthPanel,OverviewFilters,parts,ui,useUrlState}.tsx`, `lib/gps-view.ts`, `lib/gps-analytics.ts`; asset detail `gps/[assetId]`.
- API: `api.gps.overview(params, limit 50/500, facets=true, bbox)`, `api.gps.health({days:30,limit:8})`, `api.assetMap.assets()`, `api.gps.exportOverview` -> `GET /gps/overview`, `/gps/health`, `/map/assets`, `/gps/overview/export`, `/gps/assets/{id}`.
- Backend: `routers/gps.py` (perm `analytics.view`, `gps.py:19`) -> `services/gps_overview.py` (`get_overview`, `get_health`, `get_asset_detail`, `matches`, `facets_of`, `sort_rows`), `gps_compare.py` (pure verdicts), `gps_assessment.py` (day verdicts), `gps_analytics.py`; repo `repositories/gps.py` (`list_loco_positions`, `_DAY_SQL`, `feed_health`).
- Tables read: `fixed_assets`, `asset_source_links`, `wialon_units`, `gtk_gps_units`, `gtk_gps_days`, `gtk_gps_runs`, `asset_position_history`, `gps_day_assessment`, `sections`, `asset_models`. Written by the page: none.
- Backend vs frontend: verdicts, ratios, distances, facets computed on backend; frontend only colours/labels (`positionColor`, `POSITION_LABEL`) and recomputes marker lists. Filtering/sorting/search are SERVER-side but done in Python over all locomotive rows (87) with a whitelist-style sort (`sort_rows`); URL-synced filters (`useUrlState`).
- Refresh: 60 s polling + pause button; "обновлено HH:MM:SS" shown (`page.tsx:225`); feed health panel shows `gtk_units_synced_at` (stale >45 min) and `wialon_units_synced_at` (stale >15 min) (`page.tsx:407-408`).
- Staleness risk: low (60 s). Each refresh = up to 4 requests (overview x1-2, map, health) and the unified map call failure is swallowed (`.catch(() => null)` `page.tsx:~80-81`) -> MOD-11.
- Hard-coded: PAGE_SIZE, FRESH_MIN=30 (`lib/gps-view.ts:86`, mirrors backend `gps_compare.FRESH`), thresholds mirrored on the frontend.
- Scoping: `_scope(user)` (`gps_overview.py:77`) master -> own section, section filter overridden (`:309`); detail of foreign section -> 404.
- Errors: red message `Не удалось загрузить сравнение GPS`; partial failures hidden (above).

### B2. Карта `/dashboard/map`
- Files: `map/page.tsx` (317), `_components/{GoogleAssetMap,OsmAssetMap,TrackMap}.tsx`, `map/history`, `map/unplaced`; `lib/map-view.ts`, `lib/map-history.ts`, `lib/map-icons.ts`.
- API: `api.assetMap.assets()` -> `GET /map/assets` (no params sent by the page), `api.assetMap.trains()` -> `GET /map/trains`; sub-pages `/map/unplaced`, `/map/history`.
- Backend: `routers/asset_map.py` (perm `analytics.view`), `services/asset_map.py` (`get_asset_map`, `build_points`, `_loco_gps_point`, `classify_unplaced`, `find_gtk_candidate`), `services/train_formation.py` (`live_trains`), `services/asset_history.py`, repo `repositories/asset_map.py` (`list_asset_positions`, `list_train_positions`, `online_since`).
- Tables read: `fixed_assets`, `asset_source_links`, `wialon_units`, `gtk_carriages`, `gtk_gps_units`, `gtk_trains`, `gtk_train_members`, `asset_position_history`, `sections`, `asset_models`.
- Position priority (VERIFIED `services/asset_map.py:build_points`): (1) locomotive with a GTK GPS unit: newer of Wialon vs GTK GPS via `gps_compare.position_check`, other kept as `alt_*`; (2) own Wialon fix; (3) wagon: position of the locomotive of its open GTK train (`source="train"`); (4) carriage's own GTK coordinate (`source="gtk"`); else unplaced with reason (`no_link`/`no_position`). Filter `decommissioned_at IS NULL` (`repositories/asset_map.py:110`).
- Computed on frontend: filtering (q/type/source/section/online/moving/verdict) client-side over all points (`map/page.tsx:70-85`), `fleetStats`, `buildTrains`.
- Refresh: 60 s interval even in a hidden tab, no AbortController (MOD-12); `loadedAt` shown (`page.tsx:119`). `trains` call error swallowed (`.catch(() => null)`, :50).
- Hard-coded: online window 15 min (server), `MOVING_KMH`, map centre lat 41.3/lon 64.5, `DEMO_MAP_ID` for Google.
- Scoping: `_master_section_scope` (`asset_map.py:26`); loco of another section is not named in a train (`loco_visible`).

### B3. Данные GTK `/dashboard/os/gtk`
- Files: `os/gtk/page.tsx` (660). API: `api.gtk.{status,locomotives,carriages,trains,train,link,unlink,createCarriageAssets}` -> `/gtk/status`, `/gtk/locomotives`, `/gtk/carriages`, `/gtk/trains`, `/gtk/trains/{id}`, `/gtk/links`, `/gtk/carriages/create-assets`; `POST /gtk/sync`, `/gtk/match-report` exist.
- Backend: `routers/gtk.py` (perm `gtk.view` for reads; `gtk.manage`; `asset_links.manage` for link writes), `services/gtk.py`, `gtk_matching.py`, `asset_matching.py`, `asset_links.py`; repo `repositories/gtk.py` (753 l.).
- Tables: reads `gtk_*`; writes `asset_source_links` (+ mirror columns `fixed_assets.gtk_id`), `fixed_assets` (create from carriage, `gtk.py:728-833`).
- Quality panel is computed backend-side (`gtk_sync_runs.quality`). "Нет связи с GTK" if last run older than 30 min (`gtk/page.tsx:~104`, frontend threshold).
- Refresh: manual button only. Last run time shown. Auto-sync stopped notice shown (`status.auto_sync_stopped`).
- Scoping: `gtk.view` false for master (live `role_permissions`), so master has no access at all (consistent with the rule, not with "own section only").
- Filters: server-side with query params (`sort_by` whitelist in repository).

### B4. Данные Wialon `/dashboard/os/wialon`
- Files: `os/wialon/page.tsx` (264). API: `api.wialon.{listUnits,getUnit,suggestions,createAsset}`, `api.fixedAssets.update` -> `/wialon/units`, `/wialon/units/{id}`, suggestions, `POST` create asset.
- Backend: `routers/wialon.py` (perm `assets.view`, `assets.create`, `asset_links.manage`; `_master_section` :51), `services/wialon_units.py`, `repositories/wialon_units.py`, `wialon_health.py`, `wialon_counter_release.py`.
- Tables read: `wialon_units`, `wialon_counter_state`, `wialon_rejected_readings`, `asset_source_links`, `fixed_assets`.
- Frontend rule: "Нет связи" if `last_message_at` older than 24 h else `is_online` (15 min server) (`wialon/page.tsx:14-17`) -> a third staleness definition (MOD-08).
- Refresh: none (no polling). Last message per unit is shown per row (`page.tsx:162,251`). No page-level "synced at".
- Filters: `linked`, `online`, `suspect`, `search`, `page` server-side.

### B5. Вагоны (по составу) `/dashboard/gps/wagons`
- Files: `gps/wagons/page.tsx` (244), `[key]/page.tsx` (167), `_components/WagonParts.tsx`; API `api.gps.wagons` x2 (page of 50 + a 500-row "wide" set for the map) -> `GET /gps/wagons`, `/gps/wagons/{key}`.
- Backend: `routers/gps.py` (perm `analytics.view`), `services/gps_wagons.py` (`list_wagons`, `wagon_detail`, `explain`, flags `two_trains/stale_membership/loco_silent/no_loco/no_history`, `STALE_MEMBERSHIP_DAYS=3`), `wagon_gps.py` (segments, 4 distance candidates), `gps_analytics.select_candidate`, `train_formation.py`, `gtk_membership.py`.
- Tables: `gtk_carriages`, `gtk_train_members`, `gtk_trains`, `gps_wagon_segments`, `asset_source_links`, `fixed_assets`, `asset_position_history`, `gtk_gps_units`, `wialon_units`. Writes: by background analytics `gps_wagon_segments` (every GTK GPS cycle, `back_days=3`).
- Position of a wagon = position of its locomotive (a wagon has no GPS). km is derived not stored in ledger (`wagon_gps.py` docstring: "Nothing here writes into the wagon mileage ledger"). Mileage/sostav details: see other auditors (probeg, sostav).
- Master: only carriages linked to an asset of own section (`gps_wagons.py:99`); foreign -> 404.
- Refresh 60 s (`useAutoRefresh(..., false)`); `loadedAt` state exists. Map of wagons limited to the first 500 rows (`wagons/page.tsx:~62`) -> POTENTIAL RISK if total wagons >500 (688 carriages exist).

### B6. Весовая `/dashboard/scales`
- Files: `scales/page.tsx` (258), `_components/{Overview,WagonLedger,cards,viz}.tsx`, sub-routes `scales/{loco,train,wagon}`; `lib/scales-view.ts`, `scales-insights.ts`.
- API: `api.scales.{status,trains,unmatched,corrections,createCorrection,endCorrection,rematch,overview,wagonTotals,wagonTrips,exportWagonTrips}` -> `/scales/status|trains|unmatched|corrections|rematch|overview|wagons|wagon-trips[/export.csv]|trains/{id}|wagon-card|loco-card/{id}`; ingest `POST /scales/ingest` (collector only).
- Backend: `routers/scales.py` (perm `scales.view` / `scales.manage`, ingest token), `services/scales.py` (`ingest`, `_context`, `rematch`, `get_status`), `scales_matching.py`, `scales_trips.py`, `scales_insights.py`.
- Tables: reads/writes `scale_posts`, `scale_trains`, `scale_weighings`, `scale_train_carriages`, `scale_cargo`, `scale_corrections`; reads `gtk_locomotives` (garage_number), `gtk_train_members`, `asset_source_links`, `fixed_assets`.
- Linking (VERIFIED `services/scales.py:176-215`): loco number typed on the scale (normalised upper-case/no spaces, then zero-stripped variants `scales_matching.py:23-37`) -> `GtkLocomotive.garage_number` -> `gtk_id` -> active gtk link -> `fixed_assets` (NOT via `fixed_assets.inv_number`); wagons: GTK train membership by time overlap (tolerance `scales_gtk_tolerance_min`=15) -> carriage -> link. `source='vesavoy'` in `asset_source_links` is allowed by CHECK but unused.
- Computed on backend (`rematch` recomputes all derived values from raw rows + corrections). Frontend only presents.
- Refresh: none. Staleness shown per post: `silent_hours`, `health` (warn >=6 h, alert >=24 h), collector `ok/stale/never` (>10 min stale) (`services/scales.py:409-460`). LIVE: last weighing 2026-11-20 15:39, i.e. ~41 h silent -> MOD-02.
- Master: `scales.view=false` for master (alembic `0034_scales.py:153`), no row scoping exists in services (not needed while denied; becomes a gap if the permission is ever granted).
- Filters/sort: server-side (`TRAIN_SORT` whitelist).

### B7. ТО и ремонты `/dashboard/maintenance`
- Files: `maintenance/page.tsx` (3001 lines in one file) + `_components/{EquipmentBadge,LiveOverview,LivePlanCard,PlanDialogs,RescheduleDialog}.tsx`; `lib/maintenance-view.ts`.
- API (21 calls): `maintenanceSchedule.get`, `maintenancePlans.{list,update,block,unblock,waive,createFromForecast,decisions}`, `maintenanceLive.{kpis,disruptions,createDisruption,closeDisruption,saveBaseline}`, `maintenanceSettings.{get,update}`, `workOrders.create`, `workTypes.list`, `sections.list`, `employees.list`, `fixedAssets.mileageHistory` -> `/maintenance-schedule`, `/maintenance-plan*`, `/maintenance-disruptions`, `/maintenance-baselines`, `/maintenance-kpis`, `/maintenance-settings`, `/maintenance-health`.
- Backend: `routers/maintenance.py`; reads use `AuthenticatedUser = Depends(get_current_user)` (`:35`) i.e. NO `maintenance.view` permission check; writes `maintenance.update` + role admin/operator; `services/maintenance.py` (`_master_section_scope` :48, `get_schedule`, `list_plans`, `reconcile_asset_plans`), `maintenance_engine.py` (pure planner), `maintenance_obligations.py`, `maintenance_lifecycle.py`; repo `repositories/maintenance.py`.
- Tables: `maintenance_intervals`, `maintenance_plan`, `asset_maintenance_baseline`, `maintenance_decision`, `maintenance_disruption`, `maintenance_settings`, `asset_meter_daily`, `maintenance_log`, `work_orders`, `fixed_assets` (mileage), `mileage_history`, `wagon_mileage_ledger`, `wagon_mileage_opening_balances`, `wialon_units`, `asset_source_links`.
- Link to assets: plan FK `asset_id` (CASCADE); current meter = `fixed_assets.mileage` / `MileageHistory.max` (locomotives via Wialon delta; wagons via the ledger projection), pace from `asset_meter_daily`/ledger.
- Backend/frontend split: engine state is server-side, BUT the frontend recomputes progress %, recommendation text and pace fallback (`lib/maintenance-view.ts:71-137`, thresholds `NEAR_THRESHOLD_PCT=90`, `PLAN_AHEAD_PCT=70` hard-coded) -> two implementations (MOD-19).
- Refresh: none on the page (no timer, no realtime); the background job re-plans hourly; UI state is only as fresh as the last manual load. `localStorage` used only for view prefs (try/catch).
- LIVE DATA: `maintenance_plan=0`, `asset_maintenance_baseline=0`, `maintenance_decision=0`, `maintenance_settings=0`, `maintenance_intervals=9`. The module is wired but holds no plan data (MOD-03).
- Master: service-level scope per query; foreign section -> hidden.

### B8. Справочник ОС `/dashboard/directories/assets`
- Files: `directories/assets/page.tsx` (2505 lines). API (26 distinct): `fixedAssets.{unified,stats,get,create,update,remove,links,linkSource,unlinkSource,models,mileageHistory,previewInventoryImport,applyInventoryImport,previewPassportJsonImport,applyPassportJsonImport,bulkUpdateOrgUnit}`, `gtk.fixedAssetDetail`, `wialon.{listUnits,getUnit,createAsset}`, `wagonMileage.{summary,openings,submitOpening,approveOpening}`, `fixedAssetCatalogs.list`, `sections.tree`.
- Backend: `routers/assets.py` (perms `assets.view/create/update/delete`, `asset_links.view/manage`), `services/assets.py`, `asset_links.py`, `asset_passport*.py`, `unified_assets.py` + repo `repositories/unified_assets.py` (UNION of TOIR assets + Wialon-only units + GTK-only objects; `UNIFIED_SORT_FIELDS` whitelist; GTK-only rows can only sort by name/inv_number, `:308`), `asset_field_changes.py`.
- Tables: `fixed_assets` (RW), `asset_source_links` (RW), `asset_field_changes`, `asset_models`, `sections`, `wialon_units`, `gtk_*`, `mileage_history`, `wagon_mileage_*`.
- Realtime: subscribes to `fixed_assets` events (the only one of the 8 pages). Shows `wialonLastSync` ("Актуальные данные Wialon · обновлено", `page.tsx:1022`).
- Master: `_master_section(user)` used in list/get/mileage/gtk (`routers/assets.py:82-88,100,129,175,306,327,486`); `/links` endpoints use `master_section_id=None` but are behind `asset_links.view` which master lacks.
- Client-side: only form helpers/selection; list filters/sort are server-side.
- Reads the legacy mirror columns `wialon_id`/`gtk_id` in `FixedAssetRead` (`schemas/assets.py:241-242`) while the truth is `asset_source_links` (MOD-04).

### B9. Table: module x tables (R = read, W = written by user action or job)
| Table | GPS | Map | GTK | Wialon | Wagons | Scales | ТО | Справочник |
|---|---|---|---|---|---|---|---|---|
| fixed_assets | R | R | R/W(create) | R | R | R | R (mileage), W (job) | R/W |
| asset_source_links | R | R | R/W | R | R | R | R | R/W |
| wialon_units | R | R | - | R | R | - | R | R |
| gtk_locomotives / gtk_carriages | - | R | R | - | R | R (garage no.) | - | R |
| gtk_trains / gtk_train_members | - | R | R | - | R | R | - | - |
| gtk_gps_units / gtk_gps_days | R | R | - | - | R | - | - | - |
| asset_position_history | R | R(history) | - | - | R | - | - | - |
| gps_day_assessment | R(W job) | - | - | - | - | - | - | - |
| gps_wagon_segments | - | - | - | - | R(W job) | - | - | - |
| scale_* | - | - | - | - | - | R/W | - | - |
| maintenance_* , asset_meter_daily | - | - | - | - | - | - | R/W | - |
| mileage_history, wagon_mileage_ledger | - | - | - | - | - | - | R | R |
| asset_field_changes | - | - | W (job) | - | - | - | - | R/W |
Shared services: `asset_links` (identity), `gps_compare` (GPS + Map), `gps_overview._fix/_scope` (Wagons), `train_formation` (Map + Wagons), `asset_map.LOCOMOTIVE_TYPES` (imported by GPS, wagons, assistant), `gtk_gps` (GPS + wagons analytics), `maintenance_service.reconcile_asset_plans` (called from Wialon pull). Shared data engine: Wialon pull -> `fixed_assets.mileage` -> ТО.

---------------------------------------------------------------------------------------------------
