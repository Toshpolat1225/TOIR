# TOIR — AI WORKLOG

Append-only. After every AI session add 3-5 lines. Do not read this file unless asked.

Format:
`YYYY-MM-DD | tool/model | task | changed files | tested? (command -> result) | next step`

2026-10-16 | Claude chat | created AGENTS.md, rewrote docs/HANDOFF.md, added DECISIONS.md and this log | docs only, no code | n/a | switch to local Ollama assistant (Continue); first test task must be tiny
2026-10-16 | Copilot SDK | P-T8 cleanup: removed obsolete client, route, SQL, and archive copies; standardized npm metadata | frontend, backend scripts, docs | validation pending | run tsc/build, Python syntax checks, and source scan
2026-10-16 | Copilot SDK | P-T8 validation | npm build + tsc passed after refreshing generated route types; Python syntax checks passed; source scan empty | PostgreSQL and browser NOT TESTED | next: implement P-T9 ML worker
2026-10-16 | Codex | Added API-based demo seed/remove script | backend/scripts/seed_demo.py, docs/HANDOFF.md, docs/AI_WORKLOG.md | Python AST syntax check only; script/API/server NOT TESTED | user review, then run against intended API if desired
2026-10-16 | Codex | Investigated Maintenance fetch and TMC 404; added read-only TMC list API and UI error states | backend TMC router/service/repository/schema, main.py, lib/api.ts, Maintenance/TMC pages, docs | tsc + Python syntax passed; build/API/CORS NOT TESTED | inspect browser request URL/CORS and deploy backend change
2026-10-16 | Codex | Started 3-locale localization: cookie/provider, Accept-Language, normalized business translations, localized response fields, admin editor, locale-aware report CSV | frontend, backend localization, 0006 migration, schema, localization inventory/docs | tsc --noEmit passed; build passed with 2 Hook warnings; Python AST syntax passed for 15 files | migration/API/UI E2E NOT TESTED
2026-10-16 | Codex | Added localization E2E and locale parsing unit tests; did not execute them | backend/scripts/e2e_localization.py, backend/tests/test_localization.py | NOT TESTED by instruction/workflow | finish remaining hardcoded strings and resource filters
2026-10-16 | Codex | Full localization remains incomplete: page text and some API sorting/filter/export/error paths still use Russian or canonical values | docs/LOCALIZATION_INVENTORY.md, docs/HANDOFF.md | Browser, migration, database, server NOT TESTED | continue remaining pages and authorized runtime verification
2026-10-16 | Codex | Extended translated data labels to dashboard summaries and analytics/report output; expanded E2E fallback checks | backend analytics/dashboard localization path, lib/api.ts, dashboard UI, E2E script | tsc --noEmit and build exit 0; Python AST syntax passed for 18 files | full page localization, migration, API E2E and browser remain NOT TESTED
2026-10-16 | Codex | Added manageable fixed-asset type/status catalogs and admin page | backend routers/services/repositories/schemas, migration 0007, postgres schema, lib/api.ts, OS/admin UI | Python AST syntax passed for 12 files; tsc exit 0; build exit 0 with 2 existing Hook warnings | migration, API E2E, browser and production behavior NOT TESTED
Status codes keep their existing meaning through an explicit behavior group; active catalog values are checked for new asset writes.
Used catalog entries return a conflict on delete and display their fixed-asset usage count.
Next: inspect/run the new API E2E and migration only against the intended test environment.
2026-10-18 | Codex | Mapped current organization schema, foreign keys, section CRUD and master scope for Stage 3 | docs/HANDOFF.md, docs/AI_WORKLOG.md | Repository/schema read only; no database connection or code test | Await approval of additive sections hierarchy plan
Existing section IDs feed users, employees, assets, work orders, TMC documents, maintenance logs, translations and readiness snapshots; live values were not inspected.
Proposed mapping preserves each old section ID and leaves existing parent IDs NULL; no parent is inferred from the static seed pairs.
Next: after approval, implement migration dry-run/mapping and backend hierarchy rules before updating consumers.
2026-10-18 | Codex | Organized work-order detail, added server-side filters and scoped TMC document lookup | work-orders/TMC backend layers, lib/api.ts, work-orders UI, e2e_workorders.py, docs | Python AST (7 files), tsc, build passed; build has 2 Hook warnings; E2E NOT TESTED | Run E2E on intended test API and verify detail flow in browser
Detail shows existing repair rows and planned quantities separately from linked warehouse-document quantities and prices.
No dedicated tasks, returned quantities, work-order audit trail, or TMC write API were present; no migration was added.
Server, database, API E2E and browser/theme/locales were not tested.
2026-10-18 | Codex | Added OS dashboard facet counts and interactive filters | backend assets layers, lib/api.ts, app/dashboard/os/page.tsx, backend/scripts/e2e_asset_dashboard.py, docs | Python AST (5 files) passed; tsc passed; build passed with 2 existing work-orders Hook warnings; API E2E not run | Run E2E against test API and review browser themes/mobile
Cards use persisted asset type/status/status behavior and current section IDs; asset active/inactive is not represented as an asset field.
Stats and list share query dimensions; master section scope is forced server-side.
No migration, server, database, browser, theme, mobile, or interaction test was run.
2026-10-18 | Codex | Added database-backed granular RBAC, protected admin role, and permission editor | backend/app permission model/service/router, migration 0008, lib/api.ts/auth-context.tsx, dashboard permission UI, e2e_permissions.py, docs | Python AST 88 files passed; tsc exit 0; build exit 0 with 2 React Hook warnings; E2E and migration NOT RUN | Review permission matrix and run migration/E2E only on intended test environment
2026-10-18 | Codex | Added user active/inactive controls and refresh-token revocation | User service/router/RBAC, Alembic 0009, admin users page, E2E script | Python AST 6 files, tsc and build passed; build had 2 existing Hook warnings | Migration, API and E2E NOT TESTED
2026-10-18 | Codex | Active-status permission and self/last-admin guards | backend/app/core/permissions.py, backend/app/services/users.py, backend/app/routers/users.py | Static source reviewed; runtime NOT TESTED | Verify against test API after migration
2026-10-18 | Codex | Added user-status E2E coverage and updated handoff/decision notes | backend/scripts/e2e_user_status.py, docs/HANDOFF.md, docs/DECISIONS.md | Script syntax checked; E2E NOT RUN | Apply Alembic 0009 and run E2E on intended test API
2026-10-18 | Codex | Added work-order opening mileage to reports and CSV, with mileage filters | backend/app work-order, analytics, asset layers; lib/api.ts; reports page; e2e_workorders.py | Python AST, tsc and build passed; build had 2 React Hook warnings; E2E NOT RUN | Run E2E on intended test API and review report in browser
Snapshot uses existing mileage_at_creation; historical NULLs are not backfilled, and no migration was needed.
Server derives snapshot on create, locks asset row, and rejects later asset reassignment; unknown default zero remains NULL without history evidence.
Production server/database, API, E2E, CSV runtime and browser behavior are NOT TESTED; source and exact sample timestamp are unavailable in schema.
2026-10-18 | Codex | Added server-side filters for employee, user, work-type and TMC lists; paged employee/user/TMC views and debounced searches | backend references/users/TMC layers, lib/api.ts, list pages, E2E scripts, docs | AST 12 files, tsc exit 0, build exit 0 with 2 React Hook warnings; E2E NOT RUN | Run E2E against intended test API and review browser/mobile filters
Existing OS/work-order/report/nomenclature filters were audited; common indexes exist, but substring search index plans were not evaluated.
No schema or migration changed; URL filter persistence and several reference-list search controls remain for follow-up.

2026-10-18 | Codex | Independent acceptance audit of stages 1–10; excluded generated Next type file from standalone lint | .eslintignore, docs/HANDOFF.md, docs/AI_WORKLOG.md | tsc, lint, build and Python AST 116 files exit 0; two Hook warnings remain; backend tests/API/DB/E2E/browser NOT TESTED | Resolve master maintenance scope, admin demotion, dashboard readiness/ID mapping, and TMC API contract before acceptance

2026-10-18 | Codex | Stage 10 static integration/security audit; no application code changed | docs/HANDOFF.md, docs/AI_WORKLOG.md | tsc and build exit 0; lint exit 1; Python AST 116 files passed; API/DB/E2E/browser NOT TESTED | Fix audited maintenance master-scope and admin-role-demotion risks, then verify on authorized test API
2026-10-19 | Codex | Enforced master section scope in maintenance schedule/plans and protected admin role from demotion | backend/app/routers/maintenance.py, backend/app/services/maintenance.py, backend/app/repositories/maintenance.py, backend/app/services/work_orders.py, backend/app/services/users.py | Python AST syntax check passed for 6 files; mock tests/API/DB/E2E NOT TESTED | Have the user run mock regression tests locally and API E2E only against the intended test API
Master scope is derived from authenticated User.section_id and applied to schedule assets, orders, plans, plan updates, and linked work-order checks.
Admin demotion is blocked even with multiple admins; the last-active-admin and self-deactivation guards remain.
No schema or migration change was made.
2026-10-19 | Codex | Excluded cancelled work orders from monthly readiness and changed dashboard asset matching to IDs | backend dashboard/analytics repository, dashboard schema, lib/api.ts, app/dashboard/page.tsx, backend/tests/test_dashboard_regressions.py | Python AST 6 files passed; tsc exit 0; build exit 0 with 2 existing work-orders Hook warnings; backend tests/API/E2E NOT TESTED | Run mock dashboard regressions in a safe local test setup and verify API/UI behavior
Monthly trend keeps its existing historical closed_at logic for non-cancelled statuses; daily readiness snapshots were not edited.
Dashboard order responses now carry fixed_asset_id end-to-end, preventing duplicate display names from merging assets.
2026-10-19 | Codex | Aligned TMC document client with read-only UI/API and added contract coverage | lib/api.ts, backend/app/repositories/tmc_documents.py, backend/tests/test_tmc_documents_contract.py, docs/HANDOFF.md, docs/AI_WORKLOG.md | Python AST 6 files passed; tsc exit 0; build exit 0 with 2 existing work-orders Hook warnings; tests/API/E2E NOT TESTED | Run TMC contract tests in a safe local setup
Only TMC document list/read/print is used by UI; work-order material edits use work-order endpoints and nomenclature edits use inventory endpoints.
Removed unsupported TMC document create/update/delete client methods; no API, permission, migration, or schema was added.
Fixed missing SQLAlchemy exists import in the TMC repository search query.
2026-10-19 | Qoder | Read-only full system study and analysis: docs, repo structure, schema table list, router/model/service listings, frontend pages, git state | docs/HANDOFF.md, docs/AI_WORKLOG.md | No app code changed; `git status` clean, main in sync with origin/main at 8090d7e; no tests/builds executed | Next: user runs pending mock regression tests and E2E scripts only against the intended test API
2026-10-19 | Qoder | Full 6-section audit (secrets, auth, backend/DB, frontend, deploy, tests) via 4 parallel read-only agents + direct git/ignore checks; report written | docs/AUDIT_2026-10-19.md, docs/HANDOFF.md, docs/AI_WORKLOG.md | Static only; no code/tests/builds; tunnel /health responded ok; git history clean of secrets | P0: apply 0006-0009 before deploy, run 48 unit tests + e2e, sync schema.sql with 0008; P1: .gitignore backups/, dashboard errors, deploy.sh missing
