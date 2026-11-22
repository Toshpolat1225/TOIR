# 04 — SOSTAV (train formation) audit

> READ-ONLY audit, 2026-11-22. Nothing was changed in code, config, DB or containers. Every finding is labelled VERIFIED (code line / SQL result seen) or UNVERIFIED / POTENTIAL RISK. Browser/API behaviour of the pages was NOT tested (no credentials; creating an account would write to the live DB).
> Source: worker B (sostav)

# B. SOSTAV (train formation) audit — TOIR

Auditor: read-only. All SQL was run through the BRIEF pattern (BEGIN READ ONLY, statement_timeout 8 s), against the DB reachable by `docker compose exec postgres` on this PC (snapshot time of queries: 2026-11-22 ~08:20 UTC). Browser/API verification of pages was NOT possible (no credentials, rule 5): everything about pages is code + SQL evidence. Whether the `docker compose` DB equals the live server DB at 192.168.28.104 is UNVERIFIED.

Paths below are relative to `C:\Users\okmkh\OneDrive\Documents\GitHub\TOIR`; `B/` = `backend/app/`.

---------------------------------------------------------------------
## 1. Formation logic

### 1.1 What forms a sostav
Only GTK defines a sostav. Wialon has no notion of train or wagon.

| Table | Meaning | Key | Evidence |
|---|---|---|---|
| `gtk_trains` | one row per GTK train object, mirror (upsert) | `gtk_id` (int PK), `number` (text, indexed non-unique), `title`, `begin_time`, `end_time`, `is_open` | B/models/gtk.py:71-83 |
| `gtk_train_members` | membership interval of a locomotive or carriage in a train | `id` bigserial; `train_gtk_id, kind('locomotive'/'carriage'), object_gtk_id, is_main, ord, gtk_begin_time, observed_from, observed_to` | B/models/gtk.py:86-112 |
| `gtk_membership_observations` | audit of 'opened'/'closed' per membership with `snapshot_id` -> `gtk_raw_snapshots` | | B/models/gtk.py:115-135 |
| `gtk_locomotives`, `gtk_carriages` | mirrors of GTK vehicles (own ids; `gtk_carriages` also has `lat, lon, is_loaded, state_duration_s`) | `gtk_id` | B/models/gtk.py:20-68 |
| `gps_wagon_segments` | derived: (carriage, train, day-piece) -> loco -> km candidates | UNIQUE(carriage_gtk_id, train_gtk_id, period_from) | B/models/gtk_gps.py:116-120 |
| `asset_source_links` | `(source, external_id) <-> fixed_assets.id`, `status` active/ended | partial UNIQUE (source, external_id) where active AND (asset_id, source) where active | B/models/asset_source_links.py:20-34 |

Pipeline (B/services/gtk.py `sync_gtk`, :149-255): `GtkClient` fetch snapshot -> `norm_train` (B/integrations/gtk_client.py:162-199: `is_open = end_time is None`, locos/carriages sorted by `order`) -> save raw payload (`gtk_raw_snapshots`) -> `repository.upsert_mirror` (B/repositories/gtk.py:629-675, ON CONFLICT gtk_id update number/title/begin/end/is_open + `last_synced_at`) -> `repository.sync_memberships` (B/repositories/gtk.py:678-749) -> `position_history.safe_record_gtk` -> (loop wrapper) `run_wagon_mileage`. A snapshot whose carriages or trains count dropped by more than 50% versus the last successful run is stored as `suspicious` and NOT applied (B/services/gtk.py:60-67, 175-203). Detection of one wagon appearing in several trains = `snapshot_transition_evidence` (B/services/gtk_membership.py:6-58), classification `HELD`, written into `gtk_sync_runs.quality` only (no UI-blocking, no constraint).

### 1.2 Sostav identifier
- Technical identity = `gtk_trains.gtk_id` (a new id for each formation; ids 3014..3282 for the last 2 months).
- Human "number" = `gtk_trains.number`, equal to the main locomotive's `garage_number` (quality check B/integrations/gtk_client.py:303-325). VERIFIED by SQL: 37 of 37 current trains have `number = gtk_locomotives.garage_number` of the main loco (query s11).
- **The number is NOT unique over time**: 116 train rows share only 44 distinct numbers (e.g. `258`: gtk_id 3191, 3232, 3233, 3268, 3279; `117`: 5 ids; `421`: 5 ids). Among the 37 currently-live trains there are no duplicate numbers. There is no unique index on `number` (B/models/gtk.py:74). VERIFIED (queries s3, s4).
- Consumers that resolve by number: scales (`scale_trains.loco_number` -> GTK garage number, B/services/scales_matching.py:1-8, `gtk_garage` method), assistant (`B/services/assistant/entities.py:209`, `handlers/gps.py:335` — pick `ORDER BY is_open DESC, gtk_id/begin_time DESC LIMIT 1`; because `is_open` is true for all rows, only the newest id wins), `gps_wagons` filter `train` (B/services/gps_wagons.py:180: matches number string OR gtk_id string).

### 1.3 Start / end of a sostav (is_open and timestamps)
- GTK start = `gtk_trains.begin_time`; TOIR observation start = `gtk_train_members.observed_from` (time of the sync run that first saw it, B/repositories/gtk.py:729-737 `observed_from=observed_at`), end = `observed_to` (time of the first sync run that no longer saw it, :712-713). `gtk_begin_time` is copied but is not used to bound intervals.
- Latency begin->observed for locomotive memberships opened after 2026-11-05: n=80, p50 0.1 h, p90 16.0 h, max 37.7 h (query s21) — the max is caused by the sync outage (see SOS-03).
- **`gtk_trains.is_open` is never turned to false.** The GTK feed apparently lists only open trains (no train row ever got `end_time`: `count(end_time NOT NULL)=0` of 116), and `upsert_mirror` only touches trains that are in the snapshot. A train that vanished from GTK keeps `is_open=true` with an old `last_synced_at` while its members are correctly closed. VERIFIED: 116 rows, 116 `is_open`, 37 synced <1 h ago, 79 stale (`last_synced_at` between 2026-11-04 09:50 and 2026-11-20 17:35) each with 0 open members (queries s1, s2, s3).
- Closing members: when a train disappears, each member gets `observed_to = observed_at` (B/repositories/gtk.py:709-722). History is kept (rows are never deleted/overwritten, intervals are appended; `ord`/`is_main` of an open member ARE overwritten in place, :723-725, so ord history is lost).

### 1.4 Adding / removing wagons, history
- Key of a membership in sync = `(train_gtk_id, kind, object_gtk_id)`. A wagon moved from train A to B = A-member closed + B-member opened (same run). History table keeps all. 437 carriages have been in >1 train over history; 1173 closed carriage intervals, lifetime 0.00 .. 16.2 days. VERIFIED (s21).
- Flapping evidence: 15 closed carriage memberships lived <15 min, 41 <1 h; 5 (train, carriage) pairs were re-added to the same train (s22). Indicates occasional GTK feed jitter (a partial list closes and re-opens members); only guard is the 50% count rule.
- Total history: 1767 member rows, observation starts 2026-11-04 (earlier membership is unknown; 68 members have `observed_from` = 2026-11-04 = baseline load).

### 1.5 One wagon in several OPEN trains
- Schema: the only uniqueness is `uq_gtk_train_members_open` on `(train_gtk_id, kind, object_gtk_id) WHERE observed_to IS NULL` (B/models/gtk.py:96-103). It does NOT stop one carriage being open in two different trains. A DB-level constraint for that does not exist. VERIFIED (code).
- Real data: 0 carriages and 0 locomotives in >1 open train; 0 historical overlapping intervals of one carriage in two trains (queries s9, s21). Detection exists only post-hoc in `gtk_sync_runs.quality.membership_conflicts` and as flag `two_trains` on /dashboard/gps/wagons (B/services/gps_wagons.py:141-142). Also `gps_wagons` silently picks the open membership with newest `observed_from` (:130).

### 1.6 Locomotive <-> wagon binding, role of Wialon
- Binding is by train: wagons of an open train belong to the train's locomotive. Main loco = `kind='locomotive' AND is_main`; secondary rule `min(not is_main, ord, object_gtk_id)` in gps_wagons (B/services/gps_wagons.py:136), wagon_gps.pick_loco (B/services/wagon_gps.py:50-53) and asset_map (B/repositories/asset_map.py:189); `train_formation.live_trains` requires `is_main` strictly (B/services/train_formation.py:176-177) — i.e. a train with only non-main locos shows on the GPS/map-assets pages but is dropped from the map "trains" formation. Current data: every open train has exactly 1 loco member and it is main (queries s2, s9) so this is only POTENTIAL.
- Wialon: units are tracked for locomotives only. 835 non-decommissioned `wagon` assets: 587 with active GTK link, **0 with a Wialon link** (query s25). Wagon position is therefore always derived: (a) train_formation lays vehicles out behind the loco's Wialon fix along the last 300 stored Wialon track points, with catalogue lengths (B/services/train_formation.py:1-6, 31-37, 141-153) — a drawing, not measurement; (b) asset_map `source="train"` = loco's fix (B/repositories/asset_map.py:138-205); (c) gps_wagons = loco's best fix (`gtk` vs `wialon` by `position_check`).
- GTK's own wagon coordinates (`gtk_carriages.lat/lon`) exist but are unreliable: among 478 carriages of open trains there are only 22 distinct (lat,lon) pairs; only 5 are within 0.5 km of their loco's Wialon position, 315 within 0.5-5 km, 156 within 5-50 km, 2 beyond 50 km; 2 carriages have coordinates outside Uzbekistan (e.g. carriage 383 in train 3166 at 80.79, 30.31); `state_duration_s` of carriages of a moving loco is ~26 days (train 3166). VERIFIED (s17, s18, s19, s20). The map uses these coordinates only as the last fallback for wagons not in an open train (B/services/asset_map.py:114-118), with `position_at = gtk_synced_at` (sync time, not the time of the position), and its `_valid` check is only range based (:34-35).

### 1.7 Detection of ambiguous / wrong formation (what exists)
- Sync: 50% drop guard; `membership_conflicts` and `wagon_transfers` (ESTIMATED) in `gtk_sync_runs.quality`; GTK quality report (open trains older than STALE_DAYS, inactive carriages in open trains, number-vs-loco-garage mismatch) B/integrations/gtk_client.py:233-325.
- Read side: gps_wagons flags `two_trains, stale_membership (>3 d and <0.5 km), loco_silent, no_loco, no_history` (B/services/gps_wagons.py:29-33, 140-150); map unplaced reasons (`train_no_gps`, `gtk_carriage_missing`, ... B/services/asset_map.py:151-178).
- Scales: `count_mismatch` / `traction_inferred` flags; exact-count pairing only (B/services/scales_matching.py:181-196).

---------------------------------------------------------------------
## 2. Wagon / sostav identifiers and relations

| Identity | Where | Notes |
|---|---|---|
| asset id (UUID) | `fixed_assets.id`, `inv_number` (5-digit, e.g. 37804) | TOIR master |
| GTK carriage id | `gtk_carriages.gtk_id`, `name` (e.g. `СВ2-105 16161`), `reg_number`, `inventory_number` | link: `asset_source_links(source='gtk', external_id = carriage gtk_id::text)` |
| GTK locomotive id | `gtk_locomotives.gtk_id`, `garage_number`, `inventory_number` | same link table, same `source='gtk'` namespace |
| Wialon id | `asset_source_links(source='wialon', external_id=unit_id)` -> `wialon_units` | locomotives only |
| scales | `scale_trains.loco_number` (text, = garage number), `loco_gtk_id`, `gtk_train_id`, `scale_train_carriages(train_id, carriage_gtk_id, asset_id, ord, unit_position, net_t)` | `scale_weighings.unit_label/position`; matched by sequence order |

Verified link quality (SQL):
- Active GTK links: 587 wagon, 51 locomotive, 25 diesel; 0 links pointing at ids missing from `gtk_locomotives`/`gtk_carriages`; 0 loco-type asset linked to a carriage id and vice versa (s10). 6 ended links.
- Every one of the 478 open-train carriages and all 37 open-train locomotives has an active link to an asset (s9: 0 / 0 missing). 100 of 687 active carriages (outside open trains) have no link (587 linked).
- **Link vs GTK inventory mismatch**: 12 active carriage links where GTK `inventory_number` != asset `inv_number`, all `link_method='manual'` (linked 2026-11-16 and 2026-11-11), 10 of them in open trains (s25, s26). Several look like typos/transpositions (GTK 38992 -> asset 38922; GTK 36878 -> 38678; GTK 37244 -> asset 37248 while GTK 37252 -> asset 37244). 5 duplicate-inventory groups have BOTH carriages simultaneously in open trains, e.g. GTK inv 37948: carriages 550 and 551 both in train 3275 (#102) linked to assets 37948 and 37947; inv 37252: carriages 516 (train 3265) and 517 (train 3253) (s28, s29). GTK registry has 59 duplicate-inventory groups and 57 duplicate reg_number groups among ACTIVE carriages (s27). Which mapping is right is UNVERIFIED (needs a human).
- Namespace risk: `asset_source_links` uniqueness is `(source, external_id)` with a single source value `gtk` for both GTK locomotive ids and GTK carriage ids (B/models/asset_source_links.py:26-33), and code even comments "GTK locomotive and carriage ids are different spaces" (B/services/asset_map.py:39). Today there are 0 id collisions (s10; loco ids 178-1322, carriage ids 344-1204 overlap in range), so POTENTIAL RISK only.
- Historical wagon<->train: `gps_wagon_segments` 10161 rows, max `computed_at` 2026-11-22 08:16, min `period_from` 2026-11-04; 478 `is_open` segments = exactly the 478 open carriage memberships; 0 open segments without an open membership; 0 segments with NULL `wagon_asset_id`; basis mix fused_track/high 7930, single_source/low 1826, held/none 285, fused_track/medium 92, track/medium 28 (s22). `gtk_wagon_mileage_log`: 201 rows, 0 referencing an unknown train (s24).
- Position in train: `gtk_train_members.ord`; for the 37 live trains: 0 duplicate ord, 0 gaps (min 1, max = count) (s9). Used as `order` by scales pairing (ord asc == scale position asc, B/services/scales_matching.py:181-196) and train_formation.

---------------------------------------------------------------------
## 3. Cross-page consistency of the same sostav

### 3.1 Which endpoint / service / table each page uses (VERIFIED by code)

| Page | API | Service / query | Membership predicate | Recomputes? |
|---|---|---|---|---|
| /dashboard/gps/wagons | `api.gps` wagons -> `gps_wagons.list_wagons` (B/services/gps_wagons.py:68) | all ACTIVE `gtk_carriages` LEFT JOIN active gtk link + non-decommissioned non-loco asset; ALL open members; `train` = `gtk_trains` by id; km from `gps_wagon_segments` | `observed_to IS NULL` (no `gtk_trains.is_open` check); newest `observed_from` wins | yes, per request (in memory) |
| /dashboard/map trains tab | `api.map.trains` `/map/trains` -> `train_formation.live_trains` (B/services/train_formation.py:165) | `gtk_trains.is_open` + open members; main loco only; loco GTK->asset->Wialon unit position ONLY (no GTK GPS); skip train if loco unlinked or no valid Wialon fix | `is_open AND observed_to IS NULL` | yes (drawing computed per request) |
| /dashboard/map points | `api.map.assets` -> `asset_map.build_points` + `repositories.asset_map.list_train_positions` (B/repositories/asset_map.py:138-205) | `GtkTrain.is_open` + open loco members + link to loco asset + Wialon unit and `gtk_gps_units`; `_newer_fix` picks newer of Wialon vs GTK GPS (:121-130); wagons get `carriage gtk_id -> train` | `is_open AND observed_to IS NULL` | yes |
| /dashboard/map/unplaced | `asset_map` `list_open_train_members` (:208-228) | same predicate | | yes |
| /dashboard/gps (overview) | `gps_overview` | locomotives only, no train membership | n/a | n/a |
| /dashboard/os/gtk (trains tab, default filter "open") | `api.gtk.trains` `/gtk/trains` -> `repositories.gtk.list_trains` (B/repositories/gtk.py:224-249) | filters ONLY `GtkTrain.is_open` | `gtk_trains.is_open` (does not look at members) | no (stored flag) |
| /dashboard/os/gtk train detail | `/gtk/trains/{id}` -> `get_train_detail` | members of that train, `current_only` optional | | no |
| /dashboard/os/wialon | `wialon` units | no sostav info (UNVERIFIED in frontend, not opened) | n/a | n/a |
| /dashboard/scales | `/scales/trains*` -> `scales`, `scales_matching`, `scales_insights` | own tables `scale_trains`, `scale_train_carriages`; GTK train found at matching time by main loco overlap with the weighing window, using ALL members `select(GtkTrainMember)` unbounded (B/services/scales.py:186) | time-window (history aware), not "now" | matched/stored by a job; `scale_trains.gtk_train_id` is a stored snapshot |
| /dashboard/directories/assets (asset card "GTK") | `/fixed-assets/{id}/gtk` -> `gtk.get_fixed_asset_gtk_detail` (B/services/gtk.py:374-424) | `list_current_trains_for_member` (open member join `gtk_trains`, NO `is_open` filter) | `observed_to IS NULL` | yes |
| GTK-driven mileage | `wagon_mileage_run._linked_members` (B/services/wagon_mileage_run.py:119-146), `wagon_gps.compute_segments` | all members, window overlap | | recomputed by job |

Differences that follow from the code (VERIFIED by reading, not by browsing):
1. Position of the same sostav is derived three ways: map trains tab = Wialon fix only; map points = newer of Wialon/GTK-GPS; gps/wagons = `position_check.best` verdict. For equal data they agree, but when Wialon is stale and GTK GPS is newer (or the reverse) the pages can show different coordinates/age.
2. Asset-type sets are inconsistent: `LOCOMOTIVE_TYPES=("locomotive","diesel","special_self_propelled")` (B/repositories/asset_map.py:20) is used by map/gps/formation; `get_fixed_asset_gtk_detail` accepts only `{"locomotive","diesel"}` and `"wagon"` (B/services/gtk.py:391-396); `wagon_mileage_run._linked_members` accepts only `asset_type == "locomotive"` / `"wagon"` (B/services/wagon_mileage_run.py:134-136). A diesel loco (25 linked in DB) pulling a train would be visible on map/GPS but be "no linked locomotive" for wagon mileage. Currently all 37 live main locos are `locomotive` type (s24), so POTENTIAL only; likewise non-`wagon` types (tank_car, platform) are accepted by map/formation (`wagon_kind`) but 404 in the asset GTK card and excluded from the mileage run.

### 3.2 SELECT-based comparison on real data (all 37 live trains, query results)
- Membership table: 37 live trains (last_synced 08:19), each 1 loco (main) + 12 or 13 carriages; total open carriage members 478 (12 trains with 13: carriages 13; trains 1141 #168, 1398 #164, 3249 #144 have 12) (s8, s9).
- Map trains (`live_trains` predicate): requires linked loco + Wialon fix: all 37 main locos are linked to an asset and a Wialon unit that has coordinates (s11) => expected 37 trains / 478 wagons. Position age: 36 within 0-5 min, 1 train (3274 #111, loco 37923) has Wialon `position_at` 2026-11-19 21:44 (3516 min = 2.4 days old), GTK GPS for the same loco 2026-11-13: the train is still drawn (offline). Unverifiable in UI.
- /dashboard/gps/wagons predicate (active carriages only): 477 in_train vs 478 membership rows: carriage 1204 (`2ВС-105 00013467`, `is_active=false`) is an open member of train 3261 (#074) but is dropped from /dashboard/gps/wagons because `GtkCarriage.is_active` is filtered in the base query (B/services/gps_wagons.py:95). Map trains tab shows 13 wagons for that train, gps/wagons 12. VERIFIED (s16; code :95).
- Scales for the same sostav (latest `match_status='ok'` weighing per GTK train, s23): for 27 listed live trains `carriages_total` equals the open GTK carriage count (12 or 13) and `dump_count` equals it, `traction_count` 2 (3 for #144), `declared_wagons` 14/15: consistent. Exception: train 3130 (#166) `dump_count=24`, `wagon_rows=26` with flags `count_mismatch,default_tare,overload` (a train weighed twice / extra rows); not reconciled by the scale logic.
- Scale loco vs GTK train main loco: 0 of 1258 matched scale trains have `loco_gtk_id` different from the main loco member of `gtk_train_id` (s12). All 1258 `ok` trains have `carriages_linked = carriages_total` (0 shortfalls), 23 have `carriages_total <> dump_count`.
- Unmatched scales: since 2026-11-04 (start of GTK history) 1450 weighed trains: 1258 ok, 180 `no_gtk_train` (all with a resolved loco asset: GTK knew the loco but it was in no train in the weighing window, or loco numbers such as 001/002/163 (28/27/15 weighings)), 12 `no_loco` (s13, s14). Before 2026-11-04 53443 trains cannot match GTK (no history) — all counted `no_gtk_train` (total `no_gtk_train` 53623, `no_loco` 652).

---------------------------------------------------------------------
## 4. Probable defects hunted with SQL (results)

| Check | Result | Query |
|---|---|---|
| wagon in 2 open trains | 0 | s9 |
| loco in 2 open trains | 0 | s9 |
| open members without carriage/loco mirror row | 0 / 0 | s9 |
| open members with no active asset link | 0 carriages, 0 locos (live trains) | s9 |
| open trains with 0 members | 79 of 116 (all stale ghosts) | s2 |
| open train without a loco member / without main loco / zero carriages | 79 / 79 / 79 (the same ghosts); among 37 live: 0 | s2 |
| duplicate number among live trains | 0 (but 44 numbers for 116 rows) | s3 |
| more than one main loco in a train | 0 | s2 |
| stale open trains (is_open, last_synced old) | 79 (oldest sync 2026-11-04 09:50) | s3 |
| live trains very old | begin_time 2025-08-20 (459 d, #168), 2025-10-10 (408 d, #164) — both are normal live trains with members; GTK `trains_older_than_days` quality list tracks it | s8 |
| members of closed trains still open | 0 | s9 |
| ord duplicates / gaps | 0 / 0 | s9 |
| inactive carriage in open train | 1 (carriage 1204, train 3261) | s9, s16 |
| carriage own coordinates outside Uzbekistan | 2 (both in open trains) | s20 |
| scale trains with `gtk_train_id` missing from `gtk_trains` | 0 | s12 |
| `gps_wagon_segments` open without open member | 0 | s22 |
| coordinate contradictions (carriage vs loco) | see 1.6: 5/478 within 0.5 km | s17 |

Sync freshness (VERIFIED): `gtk_sync_runs` shows runs every ~5 min today (07:43 .. 08:19, 8 runs, all `ok`, counts trains 37 / carriages 688 / locomotives 77), 2026-11-18: 288 runs (every 5 min), **2026-11-19: 116 runs (00:05-09:54 only)**, **2026-11-20: 178 ok + 1 error (10:15), last run 17:35:20**, **then no run until 2026-11-22 07:43:13** (s5, s6). The code default interval is 10 min (B/core/config.py:52, min 5); the observed 5 min means an env override (not read: `.env` is forbidden). Scales: `scale_trains` max `ingested_at` 2026-11-20 15:27:26, max `updated_at` 15:28:30 => no scale data for ~41 h at query time (s25) — collector push, cause UNVERIFIED.

---------------------------------------------------------------------
