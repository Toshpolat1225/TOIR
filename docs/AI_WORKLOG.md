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
