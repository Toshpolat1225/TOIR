# 08 — Test results (read-only scenarios)

> Audit 2026-11-22. Only SELECT queries in `BEGIN READ ONLY` transactions and code reading. No production-changing test was run. No browser/API test was run (no credentials).

| # | Scenario | Result | Evidence |
|---|---|---|---|
| 1 | One wagon in two open trains at once | PASS (0 found) | worker B s-queries; `membership_conflicts` = 0 now. No DB constraint prevents it (SOS-07). |
| 2 | Vanished train gets closed (`is_open=false`, `end_time`) | FAIL | 116 trains total, 116 open (my query v1); 79 are ghosts with 0 members (SOS-01). |
| 3 | GTK membership sync is fresh | PASS at check time | `gtk_sync_runs` last 2026-11-22 08:29:23, trains `last_synced` 2026-11-22 08:29. But a ~38 h gap 11-20 → 11-22 existed (SOS-03). |
| 4 | Wagon mileage ledger is fresh | FAIL | ledger 2871 rows, max `created` 2026-11-16 09:21:04 (my query v1); engine flag off in deployed stack (MOD-01 / INT-1). |
| 5 | Mileage is consistent across pages | FAIL | wagon assets mileage sum ≈ 36,084 km vs about 748,196 km in the other mileage view (worker A, PRB). |
| 6 | Locomotive mileage plausible | PASS (weak) | 68 of 86 loco/diesel assets > 0, max 1505 (v1). Correctness against Wialon not independently re-derived. |
| 7 | Scales ingest is running | FAIL | last scale `updated_at` 2026-11-20 15:28 (MOD-02). 96.6 % of scale trains are `no_gtk_train` (INT-6). |
| 8 | Maintenance has live content | FAIL | `maintenance_plan` 0, `asset_maintenance_baseline` 0, `work_orders` 0, `employees` 0, intervals 9 (exact `count(*)`). |
| 9 | Asset directory spine | PASS (count) | `fixed_assets` 1075; but identity stores drift (INT-3, MOD-04), inv_number not unique (INT-4). |
| 10 | Master sees only own section | NOT TESTED live | Code read: 11 re-implementations, all reviewed ones filter in the query / 404 (MOD-18); GPS wagons filters in Python (SEC-8). |
| 11 | Page rendering / buttons / filters of 8 pages | NOT TESTED | No credentials. |
| 12 | API endpoint responses | NOT TESTED | Authentication required. |
| 13 | Backend unit tests / `npm run test:unit` / build | NOT TESTED | Not run in this audit (read-only, avoid load on live PC). |
| 14 | Backup restore | NOT TESTED | Dumps exist; restore not attempted (SEC-4). |
| 15 | Map ↔ GPS verdict consistency | NOT TESTED live | Code shows 3 position rules (SOS-10); no runtime comparison. |
