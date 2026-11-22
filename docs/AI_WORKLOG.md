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
2026-10-20 | Qoder | Added resumable API history generator and SQL date correction for full-scale visual testing | backend/scripts/seed_history.py, backend/scripts/sql/fix_history_dates.sql, docs/HANDOFF.md, docs/AI_WORKLOG.md | py_compile passed; offline plan test 9 assets/923 orders passed; API, database, SQL and browser NOT TESTED | User runs the generator through the tunnel, then the SQL date fix, then browser verification
Plan determinism uses separate content/date/status RNGs, so resuming after a day shift keeps descriptions and repairs stable.
The generator posts monthly mileage before order blocks so mileage_at_creation varies; completed orders still trigger the existing ML background analysis.
Full scale is about 118k orders and roughly 280k API calls; the smoke run is 4 assets and about 400 orders.
2026-10-21 | Copilot SDK | Implemented dynamic multi-level organization hierarchy using the existing `sections` table and stable IDs
Changed: `backend/app/`, `backend/alembic/versions/0007_section_hierarchy.py`, new `0008_safe_section_hierarchy.py`, `backend/scripts/`, hierarchy UI/API, `postgres/schema.sql`, and related docs/tests
Verified: Python syntax check passed; `npx tsc --noEmit` and `npm run build` passed (2 existing Hook warnings); `git diff --check` passed
NOT TESTED: backend unit/E2E tests, SQL preflight, Alembic migration, database behavior, browser, or server update; local FastAPI dependency missing
Next: run read-only hierarchy preflight on a non-production DB copy, then test migration and E2E there
2026-10-21 | Copilot SDK | Audited hierarchy diff and corrected search-tree filtering, master GET scope, Russian translation sync, and migration head graph
Added `0010_merge_section_hierarchy.py`; expanded hierarchy unit/E2E checks for translation CRUD, denied master writes, and archived historical FK retention; added duplicate-name rollback preflight
Verified: AST migration graph has one head and no missing parents; dry-run SQL contains no writes/DDL; `py_compile` and `git diff --check` passed
Backend unit test discovery FAIL (test not imported): `ModuleNotFoundError: fastapi`; PostgreSQL/Alembic runtime, E2E, server, and database NOT TESTED
Next: finish sequential frontend build/type validation; then run tests and migration checks only in an isolated test environment
2026-10-21 | Copilot SDK | Fixed duplicate-name ID assumptions in hierarchy consumers; clarified migration rollback risk.
Changed: backend CLI/analytics/tests, dashboard/layout/reports/TMC/OS, section context/hooks, DECISIONS, HANDOFF.
Verified: Python syntax, `git diff --check`, `npx tsc --noEmit`, and `npm run build` passed; build has 2 existing work-orders Hook warnings.
NOT TESTED: unit tests blocked by missing FastAPI; DB, migration, E2E, browser, and server. Next: test in an approved isolated environment without production access.
2026-10-21 | Copilot SDK | Diagnosed why hierarchy code is not proven visible in the browser; no deploy or DB connection.
Evidence: worktree changes are uncommitted; local built API URL is localhost:8010; production Compose uses DOMAIN URL; API/tree route wiring and one-head Alembic graph are statically confirmed.
NOT RUN: shared browser, live frontend/backend process, DB schema/data, live API/tree response, migration, and production server. No service was restarted.
Next: review/publish the changes, test migration and CRUD on an isolated DB copy, then deploy only with explicit user-controlled authorization.
2026-10-21 | Copilot SDK | Fixed SQLAlchemy JSONB typing causing translation-list 500.
Changed: backend/app/repositories/localization.py.
PASS: py_compile; PostgreSQL dialect SQL compile for all 7 translation entity types; source confirmed existing PUT/DELETE routes.
NOT RUN: database execution, authenticated API/browser test, migration, production. Next: verify on an authorized isolated PostgreSQL/API.
2026-10-21 | Copilot SDK | Isolated hierarchy verification; production not contacted.
Changed: backend ML next-point forecast and two backend unit-test harness fixes; HANDOFF verification notes.
PASS: isolated venv, 61 backend unit tests, tsc, isolated frontend build, offline Alembic SQL + PostgreSQL grammar parsing.
NOT RUN: PostgreSQL execution/schema/FKs, API E2E, browser, production deploy. Next: test against a confirmed disposable PostgreSQL database.
2026-10-21 | Copilot SDK | Implemented Wialon pull synchronization without server or database access.
Changed: backend Wialon client/config/service/repository/router/schema/tests, asset update helper, main lifespan, Compose env, requirements, `.env.example`, HANDOFF.
PASS: py_compile for changed backend files; isolated Wialon unittest suite (16 tests); `git diff --check`.
NOT RUN: PostgreSQL/migration, real Wialon API/account, API E2E, Docker, browser, server/deploy. Next: verify against an approved disposable DB and test API.
2026-10-22 | Copilot SDK | Completed W1 diagnostics and safe Wialon error reporting.
Changed: `backend/app/cli.py`, Wialon client/status service, mock tests, HANDOFF.
PASS: py_compile, 25 isolated MockTransport/unit tests, `git diff --check`; flags checked against official unit format docs.
NOT RUN: live Wialon probe, DB, E2E, Docker, browser, server/deploy. Next: wait for approval before W2.
2026-11-02 | Copilot SDK | Integrated Wialon delta/baseline quality-gate persistence and migration.
Changed: counter repository/models, Alembic revision, Wialon quality/bootstrap tests, `.gitignore`, HANDOFF.
PASS: Python 3.14 syntax check and `git diff --check`; `mileage=None` guard confirmed by source.
NOT RUN: Python 3.12 unit tests (runtime unavailable), SQLAlchemy/Alembic runtime, PostgreSQL, Wialon, E2E, server/deploy.
Next: run only the two requested unit test modules under Python 3.12, then validate on a disposable DB.
2026-11-02 | Copilot SDK | Made Wialon bootstrap scripts accessible in the backend image.
Changed: `backend/Dockerfile`, bootstrap CSV output path, HANDOFF.
Verified by source inspection: Compose Wialon env names match Settings; empty host/token normalize to None; copied script files are readable by appuser.
NOT TESTED: Docker build/container, bootstrap execution, CSV copying; no terminal commands or `.env` access.
Next: run the bootstrap dry-run in the user's container and copy the printed `/tmp` CSV path.
2026-11-02 | Copilot SDK | Added a dry-run-first importer for creating new assets from Wialon units.
Changed: new import service/script/test; updated Wialon pull test mock; HANDOFF.
PASS: backend Python 3.12.10 pytest for the new import test and all Wialon suites: 41 passed.
NOT RUN: live Wialon/API, DB/apply transaction, dry-run CSV, Docker or server; no `.env` access.
Next: review dry-run CSV and skipped/suspect rows before explicitly choosing `--apply`.
2026-11-02 | Copilot SDK | Implemented backend maintenance planning T5.
Changed: pure planner, settings/Compose, maintenance repo/service/router/schema, asset mileage path, CLI seed, targeted tests, HANDOFF.
PASS: backend Python 3.12.10 pytest for maintenance planning and all Wialon suites: 51 passed.
NOT RUN: PostgreSQL, interval seed execution, API/E2E, Docker, Wialon or server; security-scope test not run.
Next: verify API authorization and persistence in an approved disposable database.
2026-11-02 | Copilot SDK | Added idempotent `recalculate-plans` CLI with per-asset savepoints and accurate insert counts.
Changed: backend/app/cli.py, maintenance repository/service, maintenance tests, HANDOFF.
PASS: backend/.venv Python 3.12 pytest for recalculation and maintenance suites: 25 passed.
NOT RUN: PostgreSQL/CLI DB execution, Docker, or server; no `.env` access or commit.
Next: inspect results/logs when run against the approved database.
2026-11-02 | Copilot SDK | Connected maintenance dashboard filters and plan status changes to FastAPI; localized key page text.
Changed: app/dashboard/maintenance/page.tsx, lib/api.ts, lib/i18n.tsx, docs/HANDOFF.md, docs/AI_WORKLOG.md.
Attempted: npm run lint and npx tsc --noEmit; PowerShell blocked scripts; npm.cmd lacked ESLint and local TypeScript was unavailable.
NOT TESTED: frontend lint/typecheck, browser, API runtime; no frontend test files found; no `.env` access or commit.
Next: rerun lint/tsc with existing frontend dependencies available; verify dashboard in browser.
2026-11-02 | Copilot SDK | Fixed maintenance schedule TypeScript contract.
Changed: lib/api.ts adds nullable urgency matching backend MaintenanceScheduleItem; HANDOFF updated.
Verified by schema inspection: urgency, asset_id, plan_id, interval_id and work_type_id are defined in backend schema.
NOT TESTED: lint/tsc/build (terminal prohibited); backend, `.env`, and commit untouched.
Next: rerun `tsc --noEmit` when terminal use is permitted.
2026-11-02 | Copilot SDK | Reduced dashboard flicker from realtime asset/work-order event bursts.
Changed: app/dashboard/page.tsx coalesces events and avoids full-page loading during background refresh; HANDOFF updated.
Attempted: npm lint and TypeScript check; both unavailable because local eslint/typescript dependencies are missing.
NOT TESTED: browser behavior and production realtime rate; no dependencies installed, `.env` untouched, no commit.
Next: run lint/tsc with frontend dependencies available and verify a realtime event burst in browser.
2026-11-02 | Copilot SDK | Traced persistent flicker report to an outdated frontend bundle.
Evidence: user's console shows the old callback/log text; exact text is absent from current TS/JS source; HANDOFF updated.
No application code changed; production/browser was not accessed and frontend service was not rebuilt.
Next: deploy current frontend source, rebuild only TOIR frontend, hard-refresh, and check console again.
2026-11-02 | Copilot SDK | Separated Wialon snapshots from fixed assets; added unit APIs and unified view.
Changed: Wialon model/migration/repository/services/schemas/routes, unified asset query, link rebaseline, tests, DECISIONS, PROD_RUNBOOK, HANDOFF.
Tested: backend/.venv Python 3.12 pytest for Wialon and maintenance -> 72 passed, 17 subtests passed.
NOT TESTED: PostgreSQL migration, API E2E, Wialon service, Docker, browser, server; no `.env` access or commit.
Next: apply 0012 and exercise endpoints against a disposable PostgreSQL test database.
2026-11-02 | Copilot SDK | Added Wialon unit/unified-view API E2E coverage.
Changed: backend/scripts/e2e_wialon_units.py, docs/HANDOFF.md, docs/AI_WORKLOG.md.
Checked: Pylance syntax and diagnostics for the script -> no errors or diagnostics; pytest was not rerun because no test code changed.
NOT TESTED: API E2E, migration, PostgreSQL, Docker, browser, server.
Next: apply 0012 on a disposable DB, sync at least one unit, then run the E2E script.
2026-11-02 | Copilot SDK | Connected OS dashboard to unified assets and added Wialon unit page.
Changed: lib/api.ts, app/dashboard/os/page.tsx, app/dashboard/os/wialon/page.tsx, app/dashboard/layout.tsx, docs/HANDOFF.md, docs/AI_WORKLOG.md.
Checked: VS Code Problems -> no errors in changed TS/TSX; OS source scan -> no Supabase calls.
NOT TESTED: tsc/build blocked by missing local TypeScript/Next dependencies; browser/API behavior not tested; no packages installed.
Next: provide existing frontend dependencies, run allowed tsc/build, then browser-check with test API.
2026-11-04 | Copilot SDK | Added GTK as a separate read-only source with guarded snapshot sync and APIs.
Changed: backend GTK integration/model/migration/repository/service/schema/router/tests/scripts, config, permissions, main.py, docker-compose.yml, .gitignore, HANDOFF, DECISIONS.
Tested: backend/.venv pytest for GTK and existing Wialon tests -> 62 passed (pytest-asyncio deprecation warning).
NOT TESTED: live GTK network, migration/PostgreSQL, API E2E, Docker, server; no secrets inspected and no commit.
Next: apply 0013 to a disposable database, configure GTK, sync once, then run the GTK API E2E script.
2026-11-04 | Copilot SDK | Added human-confirmed GTK links and suggestion-only matching for fixed assets.
Changed: fixed-asset model/schema/service, Alembic 0014, GTK matching/repository/service/router, focused tests, GTK link E2E script, HANDOFF, DECISIONS.
Tested: backend/.venv pytest for GTK matching, links, unified assets, and existing GTK/Wialon tests -> 74 passed; Pylance syntax checks passed (pytest-asyncio deprecation warning).
NOT TESTED: Alembic/PostgreSQL, API E2E, Docker, browser, server, or live GTK; no secrets or GTK raw files inspected; no commit.
Next: apply 0014 to a disposable database and run e2e_gtk_links.py against the intended test API.
2026-11-04 | Copilot SDK | Added GTK locomotive mileage attribution to eligible linked wagons.
Changed: pure attribution service, GTK checkpoint/log models and repository/service/routes, fixed-asset GTK detail route, Alembic 0015, mileage source schema, tests, HANDOFF, DECISIONS.
Tested: backend/.venv pytest for GTK mileage, GTK, unified assets, and Wialon -> 83 passed; Pylance syntax checks passed.
NOT TESTED: Alembic/PostgreSQL, API E2E, Docker, browser, server, and live GTK; `.env`/GTK raw files not opened; Wialon implementation unchanged; no commit.
Next: apply migrations through 0015 to a disposable database and verify attribution and read endpoints with test data.
2026-11-04 | Copilot SDK | Added GTK data page and GTK detail block in fixed-asset modal | app/dashboard/os/gtk/page.tsx, app/dashboard/layout.tsx, app/dashboard/os/page.tsx, lib/api.ts, docs/HANDOFF.md
Tested: NOT TESTED; `npx.cmd tsc --noEmit` could not find TypeScript and `npm.cmd run build` could not find Next.js. The first `npx` attempt was blocked by PowerShell policy.
NOT TESTED: browser, live GTK/API, database migrations, or server; `.env.local` untouched; no Supabase calls or commit.
Next: restore the declared frontend dependencies in the local environment, then rerun the two required checks.
2026-11-04 | Copilot SDK | Offline G1-G4 GTK consistency review and corrections | GTK config/sync/models/API, migrations 0013/0016, postgres/schema.sql, GTK frontend/API types, backend/tests/test_gtk.py, HANDOFF
Tested: backend/.venv pytest for GTK, matching, attribution, unified assets, and Wialon -> 90 passed, 17 subtests passed; existing pytest-asyncio deprecation warning.
NOT TESTED: PostgreSQL migration execution/rollback, frontend tsc/build/browser, API E2E, live GTK, Docker, or server; `.env*` and GTK raw files not opened; no commit.
Next: apply migrations through 0016 to a disposable PostgreSQL database and verify upgrade/downgrade.
2026-11-04 | Copilot SDK | G6 GTK residual cleanup | OS realtime handler, useRealtime, Docker ignore files, tests, DECISIONS/HANDOFF | backend/.venv pytest -> 94 passed | frontend build and database/Docker/browser checks remain
Realtime listeners now keep the newest handler without channel churn; OS row notifications are coalesced before stats/unified refresh.
Added GTK text-hygiene, 0012–0016 offline migration-render, and Docker-ignore regression tests; Alembic logging is isolated during SQL rendering.
No commit; next verify TypeScript/build and browser request volume, then rehearse migrations on disposable PostgreSQL.
2026-11-04 | Copilot SDK | P1 canonical external asset links | migration 0017, asset link model/service/repository/API, Wialon/GTK integration, tests, postgres schema, HANDOFF/DECISIONS | backend/.venv pytest -> 102 passed; git diff --check clean
Old Wialon/GTK references were mapped to fixed_assets mirror columns and the updated runtime lookups now use active asset_source_links.
Legacy columns remain in place and are dual-written as compatibility mirrors; no existing migration was edited.
NOT TESTED: PostgreSQL migration/rollback, API E2E, full suite, real concurrency, production or deployment; no commit.
Next: rehearse migration 0017 and link-history API on a disposable PostgreSQL test database.
2026-11-04 | Copilot SDK | P2 fixed-asset passport | migration 0018, passport model/service/report, API types, E2E payloads, tests, postgres schema, docs | backend/.venv targeted pytest -> 102 passed
Preserved existing fixed-asset fields; added normalized model/number, conditional indexes, data report, and exact-name section matching.
Updated GTK/Wialon creation paths and E2E fixtures for required passport values; no migration execution or API E2E was run.
NOT TESTED: PostgreSQL backfill/upgrade/downgrade, frontend build/typecheck, browser, production, or deployment; no commit.
Next: rehearse 0018 on disposable PostgreSQL and run the fixed-asset/passport API E2E checks.
2026-11-04 | Copilot SDK | P3 source-to-passport field policy | policy, migration 0019, field-change model/service/API, GTK sync hook, tests, E2E, postgres schema, docs | backend/.venv targeted pytest -> 128 passed
Added auto-fill/suggestion/conflict/manual journal behavior, guarded accept/reject, paginated API, and migration-seeded admin/operator permission.
GTK passport proposals run in their own transaction and use only active canonical links; Wialon telemetry code was not changed.
NOT TESTED: PostgreSQL migration, GTK network sync, API E2E, frontend, production/deploy; no commit. E2E script requires disposable API with GTK configured.
Next: rehearse 0019 upgrade/downgrade and run asset-conflict E2E on disposable PostgreSQL/API.
2026-11-04 | Copilot SDK | P4 shared source-matching foundation | shared matcher, GTK compatibility, Wialon suggestions, GTK adapter, unmatched API, tests, E2E, integration contract, HANDOFF | backend/.venv pytest -> 134 passed
Matching normalization and levels now live in one source-neutral service; GTK and Wialon call it while preserving existing helper exports.
Added `/asset-links/unmatched` for GTK/Wialon mirrors without active source links, plus protocol/adapter tests and Uzbek onboarding documentation.
NOT TESTED: API E2E, live mirror query, source connections, frontend, production/deploy; no migrations or new external integrations added, no commit.
Next: run `e2e_asset_unmatched.py` against the intended test API.
2026-11-04 | Copilot SDK | P5 passport/source/conflicts UI and supporting APIs | OS modal, conflicts page, sidebar, API types, model/link schemas-router-service-repository, E2E script, HANDOFF | `npm.cmd run build` -> Next.js missing; `npx.cmd tsc --noEmit` -> TypeScript missing; NOT TESTED
Added editable passport fields with model selection and section-change confirmation; added active/history source links with manual link/unlink controls for Wialon, GTK, Весовой and 1С.
Added pending conflicts review page with confirm-before-accept/reject and admin/operator navigation; new API types leave existing `FixedAsset` and operational fields intact.
NOT TESTED: build/tsc executables unavailable, backend pytest/API/database/browser/production/deploy; no `.env.local` access and no commit.
Next: restore frontend dependencies in the approved workflow, rerun build and tsc, then verify the UI against the authorized API.
2026-11-04 | Copilot SDK | P6 offline audit continuation and bulk org-unit assignment | backend assets API/service/schema/repository, tests, E2E, docs | `.venv` pytest -> focused 18 passed; related suites 152 passed
Added atomic, audited bulk `org_unit_id` assignment; final migration-graph and PATCH checks passed. Existing source-link race-to-409 behavior was retained.
NOT TESTED: PostgreSQL migration/rehearsal, API E2E, browser, production/deploy; frontend build and tsc executables unavailable. No migrations/schema.sql changed and no commit.
Next: restore frontend dependencies, run build/tsc, then verify E2E and migration behavior on disposable test systems.
2026-11-04 | Copilot SDK | P7 permission reconciliation, bulk org-unit UI, inventory CSV import | migration 0020, assets API/schema/service/repository, unified API, OS UI, tests, E2E, docs | backend pytest -> 163 passed
0020 idempotently sets the expected role grants; added preview-only CSV/JSON validation and atomic, audited apply, plus bulk section selection and server filtering.
NOT TESTED: frontend build/tsc (Next.js/TypeScript unavailable), migration execution, live grants, E2E, browser, production/deploy. No .env/CSV opened; no commit or Supabase call.
Next: restore frontend tools, then validate migration and API scripts on a disposable environment.
2026-11-05 | Copilot SDK | P8 fixed-asset API client and passport save audit | lib/api.ts, OS page, app layout, P8 tests, HANDOFF | backend pytest -> 171 passed; build/tsc unavailable
Moved import methods from `gtk` to `fixedAssets`; preserved `org_unit_id` in legacy PATCH payload/state refresh and localized CRUD errors; removed Vercel Analytics mount.
NOT TESTED: Next.js build and tsc executables missing; API/database, browser, production/deploy. No migrations, package dependencies, CSV, env files, commit, or Supabase changed.
Next: restore frontend dependencies, run build/tsc, then verify CRUD against a disposable API/database.
2026-11-05 | Copilot SDK | Replaced reversible passport import with confirmed whole-register replacement; corrected type mapping and create-modal type selector.
Changed backend import/migration/schema/tests, API and OS UI, HANDOFF, DECISIONS, and AI_WORKLOG.
Verified: related pytest 178 passed, 17 subtests; `npx.cmd tsc --noEmit` exit 0; `npm.cmd run build` exit 0 with 3 Hook warnings.
NOT TESTED: source JSON counts/content, database counts/import, migration execution, API/browser, production/deploy; no commit.
Next: verify preview and apply only on an authorized disposable database.
2026-11-05 | Copilot SDK | Read and validated the full JSON register; guarded replacement against deleting referenced module records.
Read assets_list.json: 1,075 rows; parser accepts all rows after the user-approved 0022 duplicate-number migration. Added FK blocker checks, root-only deletion, and duplicate-before-delete test.
Full-file parser probe: 1 passed (1,075 accepted, 0 blocked; temporary probe removed). Related suites: 183 passed; `npx.cmd tsc --noEmit` and `npm.cmd run build` exited 0 (3 existing Hook warnings).
NOT TESTED: disposable PostgreSQL migration/import, database before/after counts, actual FK rows, API/browser, production/deploy; source file unmodified; no commit.
Next: apply and verify the migration/import only in an authorized disposable PostgreSQL database; do not run production import before exact database counts are verified.
2026-11-06 | Copilot SDK | P9 canonicalized fixed-asset schema and removed legacy columns at head.
Changed: revisions 0023-0024, asset ORM/repositories/services/schemas, `postgres/schema.sql`, drift tests, DEPLOY, DECISIONS, HANDOFF.
Tested: backend `.venv` requested asset/GTK/Wialon/unified/attribution plus drift suites -> 187 passed, 17 subtests passed.
NOT TESTED: PostgreSQL migration/view execution, live dump comparison, API E2E, frontend, browser, server/deployment; no secrets opened, no commit.
Next: apply migrations and compare schema only on a user-controlled disposable PostgreSQL copy.
2026-11-09 | Copilot SDK | Simplified frontend/backend localization to Russian only | app, lib, backend localization/API schemas/tests, postgres/schema.sql, migration 0025, localization docs | build, tsc, lint, Python syntax (17 files), diff check -> passed; 3 Hook warnings
Removed locale-switching UI and translation calls, retained Russian labels/API names, and added a forward migration to delete non-Russian translation rows. Preserved the pre-existing docker-compose.yml change.
NOT TESTED: migration execution, backend tests, API E2E, browser, production/deploy. No database or server was accessed.
Next: verify the migration and localization E2E on an authorized disposable database; never run it on production without explicit user action.
2026-11-09 | Copilot SDK | Moved fixed-assets register into directories | dashboard layout, directories index, fixed-assets page/loading, dashboard links, OS route redirects, HANDOFF | build, tsc, focused ESLint, diff check -> passed; 3 existing Hook warnings
Moved the page to `/dashboard/directories/assets`, added the Russian directory card gated by `assets.view`, and removed the separate sidebar entry and old page route.
NOT TESTED: browser navigation and permissions, backend/API, production/deploy.
Next: verify visible navigation for permitted and restricted roles in a browser.
2026-11-09 | Copilot SDK | Moved ОС catalogs into directories | dashboard layout, directories index, catalog page route, HANDOFF | build, tsc, focused ESLint, route search, diff check -> passed; 3 existing Hook warnings
Moved the catalog page to `/dashboard/directories/asset-catalogs`, added a permission-gated `Справочники ОС` directory card, and removed the separate sidebar entry and old route.
NOT TESTED: browser route and permissions, backend/API, production/deploy.
Next: verify the route and card with allowed and restricted users in a browser.
2026-11-09 | Copilot SDK | Moved permissions under users | dashboard layout, users page, permissions page route, HANDOFF | build, tsc, focused ESLint, route search, diff check -> passed; 3 existing Hook warnings
Moved role permissions to `/dashboard/admin/users/permissions`, added a link on the users page, removed the separate sidebar entry, and added a return link.
NOT TESTED: browser route and admin access, backend/API, production/deploy.
Next: verify the route and role restriction in a browser.
2026-11-09 | Copilot SDK | Moved data conflicts into directories | dashboard layout, directories index, conflicts page route, HANDOFF | build, tsc, focused ESLint, route search, diff check -> passed; 2 existing Hook warnings
Moved conflicts to `/dashboard/directories/conflicts`, added a card gated by `asset_conflicts.manage`, and removed the separate sidebar entry and old route.
NOT TESTED: browser route and permissions, backend/API, production/deploy.
Next: verify the route and access rules in a browser.
2026-11-09 | Copilot SDK | Restyled asset filters and section hierarchy | directories/assets/page.tsx, HANDOFF | build, tsc, focused ESLint, diff check -> passed; 2 existing Hook warnings
Redesigned filters as animated icon capsules with counts and a total header; replaced the section selector with nested buttons sourced from `/sections/tree`.
NOT TESTED: browser rendering, API filtering, live waiting-for-parts status.
Next: verify the filters and hierarchy in a browser against an authorized API.
2026-11-09 | Copilot SDK | Removed duplicate profile from header | dashboard/layout.tsx, HANDOFF | focused ESLint, build, tsc, diff check -> passed; 2 existing Hook warnings
Removed only the top-right role badge and initial avatar; kept the theme switcher and sidebar profile block.
NOT TESTED: browser desktop/mobile layout.
Next: verify header spacing and sidebar profile in a browser at desktop and mobile widths.
2026-11-09 | Copilot SDK | Added searchable Wialon/GTK source picker for fixed assets | directories/assets/page.tsx, source-asset-picker-dialog.tsx, HANDOFF | tsc, build, diff check -> passed; 2 existing work-orders Hook warnings
Picker uses authenticated APIs, paginated search, separate GTK locomotive/carriage lists, and the existing fixed-asset link API; placeholders remain disabled.
NOT TESTED: browser UI, live Wialon/GTK responses, and link/unlink API behavior.
Next: verify search, paging, binding, and placeholder controls in a browser with an authorized account.
2026-11-10 | Copilot SDK | Implemented controlled P0.3 opening, GTK/Wialon inputs, calculation guards, and mileage-source separation | backend mileage/GTK/Wialon, assets UI, maintenance/work-orders/ML, E2E and seed scripts, HANDOFF | frontend build + tsc, Python syntax + diff check passed; earlier backend selection: 117 passed, 4 subtests, not rerun after final refinements
NOT TESTED: PostgreSQL migration/integration, E2E, browser behavior, and production; ledger publish/projection remains unimplemented pending policy.
Next: resolve UNKNOWN/PENDING mileage policies, then implement the idempotent ledger publisher and confirmed projection pipeline.
2026-11-11 | Copilot SDK | Added exact-inventory GTK proposals for carriages and locomotives | GTK service/repository/schema, GTK page/API type, tests, e2e_gtk_links.py, HANDOFF | tsc, lint, build, Python syntax, diff check passed; two existing Hook warnings
Both GTK kinds now require a unique exact inventory match; confirmation rechecks locked source/asset state and rejects stale or conflicting links without replacement.
NOT TESTED: backend pytest, API E2E, PostgreSQL race behavior, browser, production, and deployment.
Next: run the GTK link E2E only against a disposable test API/database, then verify both tabs in a browser.
2026-11-11 | Copilot SDK | P0.3 C1–C3 davomiyligi: Push/Pull quality gate, 2 daqiqalik sample delta va GTK membership helper | Wialon ingestion/repository/router/services, mileage service/tests, P0 qarorlari, HANDOFF | pytest (5 fayl) -> 64 passed, 4 subtests; py_compile va git diff --check -> exit 0 | C3 DB/ledger integratsiyasini va qolgan bosqichlar scope’ini aniqlash
Migration: `rehearse` DB’da upgrade/downgrade/upgrade muvaffaqiyatli; 0027–0028 pg_dump parity `postgres/schema.sql`da, schema drift + 4 eski yo‘l testi -> 40 passed.
D10 import filtrlash va 10^9 km Push regression avvalgi backend suite tekshiruviga kiritilgan; C1 conflict raw yozuvlarni saqlaydi va yangi baseline’gacha counter’ni HELD qiladi.
NOT TESTED: browser, API E2E, frontend build/typecheck, concurrency/PostgreSQL publish integration, production/deploy. `COPILOT_P0_3_FINISH.md` repozitoriyda topilmadi; C4–C11/D/F tafsilotlarini tasdiqlab bo‘lmadi.
2026-11-12 | Copilot SDK | P0.3 C1–C11, D va F yakuniy davomiyligi | mileage backend, 0029 migration, assets UI, testlar va docs | pytest -> 317 passed, 28 subtests; PostgreSQL parallel testi -> 1 passed
0029 upgrade/downgrade/upgrade rehearsal va 0027–0028 schema parity qayd etildi; D9 projection qarori va ochiq PENDING holatlar hujjatlandi.
`npx.cmd tsc --noEmit`, lint va production build muvaffaqiyatli; lint/build’da ish-order sahifalarida 2 avvalgi React Hook ogohlantirishi qoldi.
Keyingi: PENDING siyosatlarni tasdiqlash; API E2E, browser, jonli integratsiya va ishlab chiqarish tekshiruvlari bajarilmagan.

## 2026-11-13 — Repository cleanup
Task: remove dead/duplicate/backup files from the project folder (user approved the list; `toir-local-root.crt` kept).
Changed: 36 tracked deletions + untracked junk removed (see HANDOFF). No code, schema or migration edited.
Tested: `npx tsc --noEmit` exit 0, `npm run build` exit 0. Backend tests not run.
Next: user commits; then rehearse migration 0029 on `toir_rehearse`.

## 2026-11-13 — Vagon probegi: (a)–(e), Faza 3, Faza 5
Task: lokomotiv yozuvchisini tiklash, CLI bayrog'i, yagona run, boshlang'ich taklif/tasdiq, HELD sabablari, hisobot, hujjat.
Changed: `services/{assets,wialon,wialon_ingestion,wagon_mileage_run,mileage_opening}.py`, yangi `mileage_opening_bulk.py`, `wagon_mileage_reasons.py`, `wagon_mileage_report.py`, `cli.py`, `routers|schemas/mileage.py`, testlar, `docs/WAGON_MILEAGE_{AUDIT,RUNBOOK}.md`, `.gitignore`.
Tested: pytest 340 o'tdi (pg 11), alembic up/down/up, tsc/lint/build exit 0. Faza 4 (real run) va UI bajarilmadi.
Next: foydalanuvchi backend'ni qayta quradi, so'ng Faza 4.

## 2026-11-15 — Faza 4 (mahalliy real run)
Task: boshlang'ich taklif/tasdiq, real run, invariantlar, hisobot. Superadmin rejimi (`OPENING_BALANCE_ALLOW_SELF_APPROVAL`), `include-zero`, MissingGreenlet tuzatildi, D3 nol-km, hisobot yorlig'i.
Tested: pytest 350 o'tdi; real run completed, invariantlar 0 xato, ikkinchi run farqsiz. Brauzer/UI tekshirilmagan; 2.5 boshlanmagan.
Next: foydalanuvchi backend'ni qayta quradi va run'ni takrorlaydi; 16 bloklangan lokomotivni operator hal qiladi.

## 2026-11-15 — AD (LDAPS) login
Task: domen paroli bilan kirish (instruksiya bo'yicha). Changed: ad_auth.py, auth.py, schemas/auth.py, config, compose, requirements, login page, certs, docs/AD_LOGIN.md.
Tested: pytest 375 o'tdi, tsc/build 0. Jonli domen kirishi tekshirilmagan.
Next: foydalanuvchi AD_AUTH_ENABLED=true qilib qayta quradi va t.turakulov bilan sinaydi.

## 2026-11-16: AD kirish qayta loyihalandi (auth_source)
- Migratsiya `0030_user_auth_source`: `users.auth_source` (local|ad), `ad_username` (unique), `ad_object_guid` (unique), `hashed_password` NULL bo'la oladi, CHECK `ck_users_auth_credentials`. pg_rehearse'da up/down/up, AD user bor holatda downgrade va `schema.sql` bilan `users` parity tekshirildi.
- Kirish manbasi `auth_source` bo'yicha (login shakli bo'yicha emas). AD user: domen, parol saqlanmaydi, domen ishlamasa 503 (lokal fallback olib tashlandi). Local user: domenga murojaat yo'q.
- Servis akkaunti yo'q (variant B): AD user kiritilganda domenda tekshirilmaydi; `objectGUID` birinchi muvaffaqiyatli kirishda yoziladi, keyin boshqa GUID rad etiladi.
- Yangi: `POST /users/ad` (parolsiz), `POST /users/{id}/convert-to-ad` (admin, o'zini emas), CLI `user-convert-to-ad`. `POST /users` (lokal) faqat admin roli. AD userda parol reset 409.
- Audit: kirishda `details.auth_source`; o'tkazish `action=other, details.event=convert_to_ad`.
- UI: «Выдать доступ» (AD), aварийная lokal yozuv alohida, «Вход» ustuni, tahrirda AD ma'lumoti va «Перевести на вход через домен». Hujjat: docs/AD_LOGIN.md.

## 2026-11-16: Konfliktlar (probeg va pasport raqami)
- Tashxis: 50 ta bloklangan hisoblagichning sababi bir xil (668/668 juftda keyingi qiymat kattaroq). 279 pasport to'qnashuvidan 275 tasi faqat nolli raqam farqi, 4 tasi haqiqiy.
- Kod: `is_counter_advance` (blok o'rniga benign HELD), `wialon_counter_release` servisi + CLI `wialon-counter-release` (replay, dry-run, --inv-number, audit), `propose_field` nolli raqamni teng deb biladi, CLI `asset-conflicts-clean`. Sahifa matni yangilandi.
- Haqiqiy ma'lumotda oflayn tekshiruv (faqat o'qish): 49/49 lokomotiv xavfsiz ochiladi, 15320 o'qish tiklanadi, 323 benign HELD, 360 darvoza tomonidan ushlanadi (259 eski xabar, 101 katta qadam).
- Alohida topilma (tuzatilmadi): `audit_logs` da wialon_raw_receipts 438k, fixed_assets 300k, wialon_odometer_readings 44k qator; `_OPERATIONAL_TABLES` da `wialon_counter_states` (ko'plik) yozilgan, jadval esa `wialon_counter_state`.

## 2026-11-16: ТО sahifasi — Виды работ spravochnikdan, Gantt da sanani qo'lda ko'chirish
- Frontend: "Виды работ" legendasi `work_types` spravochnikdan (sort_order bo'yicha) + faqat ma'lumotda bor kodlar (masalan `test`); bosilsa shu kod bo'yicha filtr (kod bo'yicha, "ТО-1 — ТО-1" emas). Yangi kodlar uchun barqaror palitra rangi (`paletteForCode`).
- Gantt: chiziqni sudrab sanani ko'chirish (kursor grab/grabbing, 4 px dan kam bo'lsa oddiy bosish = karta, Esc bekor qiladi, bugundan oldin va oy oxiridan keyin mumkin emas). Tasdiqlash oynasi: tizim tavsiyasi / hozirgi / yangi sana, km ta'siri (`rescheduleImpact`), chegara oshsa sabab (>=5 belgi) va tasdiq belgisi majburiy. Kartada ham "Перенос срока" (klaviatura/telefon uchun).
- Backend: migratsiya `0031_plan_manual_date` (`scheduled_date_manual`, `recommended_date`, `reschedule_reason` + 2 CHECK). `PATCH /maintenance-plan/{id}` (`scheduled_date`, `reschedule_reason`, `reset_schedule`) va `POST /maintenance-plan/from-forecast`. Avtomatik prognoz (`upsert_scheduled_plan_with_created`) qo'lda sanani endi ustiga yozmaydi, faqat `recommended_date` ni yangilaydi. Faqat `scheduled` reja ko'chiriladi; o'tgan sana va 366 kundan uzoq rad etiladi.
- Xavfsizlik: frontend faqat backend `dateManual` yuborganda sudrashni yoqadi (eski backendda sudrash o'chiq).
- Tekshirildi: backend 435 test (pg_rehearse, migratsiya up/down/up, schema.sql parity 13 ustun), frontend 43 unit test, haqiqiy Edge brauzerida 14 + 5 tekshiruv.
- Ogohlantirish: migratsiya jonli bazaga `docker compose up --build frontend` orqali (backend bog'liqligi) avtomatik qo'llandi; keyingi safar `--no-deps` ishlatish.

## 2026-11-16: «Tirik reja» modeli to'liq joriy etildi
- Task: ТО rejalashni «oxirgi ТО'dan beri» + har texnika tempi + majburiyat yo'qolmasligi modeliga o'tkazish (taklif artifact'i bo'yicha).
- Backend: `maintenance_engine` (sof hisob: temp, 3 sana, допуск, kaskad, birlashtirish, ustuvorlik), `maintenance_obligations` (yuklash/baholash/saqlash), `maintenance_lifecycle` (yakunlash+kaskad, block/unblock/waive, uzilishlar, bazalar, KPI, health, soatlik ish, CSV import, shadow report). `reconcile_asset_plans` va `get_schedule` dvigatelga o'tdi. Migratsiya `0032_tirik_reja` (4 yangi jadval, intervalga rank/moto-soat/допуск/lead, rejaga yangi holatlar). CLI: `maintenance-shadow-report`, `maintenance-health`, `maintenance-baseline-import`.
- Frontend: «Живой план» kartasi (markerlar chizig'i, ishonch, ustuvorlik sabablari, qarorlar jurnali), bloklash/o'tkazish/baza/uzilish dialoglari, KPI paneli, jadvalda «Приоритет» ustuni, «Отменить план» olib tashlandi, har texnikaning o'z tempi.
- Tested: backend 481 test (pg_rehearse), migratsiya up/down/up + schema.sql parity (yangi jadvallar), jonli baza nusxasida (213 MB zaxira) ikki marta soatlik sikl: farqsiz. Frontend tsc/eslint 0, 57 unit test, haqiqiy Edge'da stub API bilan 18/18 (admin va operator).
- Jonli: migratsiya 0032 qo'llandi (zaxira `backups/pre0032_20261116_181356.dump`), 87 aktiv / 775 majburiyat, hammasining hisob boshi taxminiy; hujjat: docs/MAINTENANCE_LIVE_PLAN.md.
- Next: foydalanuvchi oxirgi ТО sanalari/probegini CSV bilan beradi; kaskad xaritasi va допуск qiymatlarini tasdiqlaydi; audit_logs va `wialon_counter_states` imlo xatosi (kechiktirilgan).

## 2026-11-16: Vagon probegi ishonchi D9 ga moslandi
- Topilma: reja vagon km'ini faqat kamida bitta `CONFIRMED` ledger qatori bo'lsa ishonchli deb olardi (qoida 10.11, `p02`); D9 (12.11) esa `ESTIMATED` ni ham proyeksiyaga kiritadi. 835 vagondan 589 tasida tasdiqlangan boshlang'ich, 481 tasida probeg bor, filtrdan 1 tasi o'tardi.
- Kod: `mileage_repository.has_approved_projection` (+ batch `approved_projection_asset_ids`, `estimated_projection_asset_ids`) `has_confirmed_projection` o'rniga; reja, naryad (`get_known_asset_mileage`) va ML shundan foydalanadi. `ESTIMATED` km li vagon `mileageEstimated` + ishonch `low` bilan chiqadi.
- Tested: backend 485 test (3 yangi pg + 2 yangi unit), frontend tsc/eslint 0, 57 unit test.
- Hali yo'q: vagon tempi (ledger'dan) — sanasiz vagon Gantda chiqmaydi; vagon uchun haqiqiy intervallar (me'yorlar) berilmagan.

## 2026-11-16: Vagon tempi wagon ledger'dan
- Sabab: vagonlarda `mileage_history`/snapshot yo'q edi, temp 0 bo'lib sana chiqmasdi (Gantda vagonlar ko'rinmasdi).
- Kod: `maintenance_engine.partial_day_rates` (qisman kuzatilgan kunlar shkalalanadi), `maintenance_obligations._wagon_ledger_rates` (ledger qoplagan oyna, faqat eligible CONFIRMED/ESTIMATED, faqat tasdiqlangan boshlang'ichli vagonlar), vagonlar guruhi 1 kundan tuziladi.
- Tested: backend 489 test (pg bilan); jonli nusxada (zaxiradan) vagonlar sanaga ega bo'ldi.

## 2026-11-16: jonli tizimning to'liq end-to-end tekshiruvi
- Task: jonli tizimni (foydalanuvchi ruxsati bilan) rollar, API, brauzer, ma'lumot sifati va infratuzilma bo'yicha tekshirish, nuqsonlarni tuzatish, test ma'lumotlarni tozalash, hisobot.
- Natija: 257 tekshiruv; 14 nuqson tuzatilib jonli tekshirildi (`/fixed-assets` qidiruvi 500, parol siyosati, tasdiqlash temp'i, opening supersede, audit hajmi va eksport, NUL belgi, `/asset-links/unmatched` 500, eskirgan rejalar, soatlik qayta yozish, mobil siljish, rol qo'riqchisi, interval formasi, CSP/no-store). 17 ochiq masala (P0: HTTPS, avtomatik zaxira, audit tarixini tozalash).
- Tekshirilgan: backend 516 test (pg_rehearse), frontend `tsc` 0 / 57 unit, jonli ТО oqimi 91/91, haqiqiy Edge'da 15/15 regressiya. Tozalash: ZZTEST qoldig'i 0, statik jadvallar xeshi bir xil.
- Hisobot: `docs/E2E_REPORT_2026-11-16.md`; skriptlar: `backend/scripts/e2e_live/`. Tekshirilmagan: haqiqiy AD/Wialon/GTK, WebSocket, chaos.

## 2026-11-16: AI yordamchi tizimi uchun TZ (TOIR'ga aloqasiz)
- Task: foydalanuvchi yuborgan `message.txt` bo'yicha AI yordamchi tizimi to'liq texnik topshirig'ini yozish.
- Fayl: `docs/AI_ASSISTANT_TZ.md` (yangi, faqat hujjat; TOIR kodi, DB, migratsiya o'zgarmadi).
- Tested: kod emas, shuning uchun test yo'q; § havolalari qo'lda to'liq tekshirilmagan.
- Keyingi qadam: `docs/HANDOFF.md` dagi TOIR vazifasiga qaytish.

## 2026-11-16: barcha ochiq masalalarni bartaraf etish (O1–O17)
- Task: foydalanuvchi buyrug'i «barcha aniqlangan kamchilik, mantiq xatolari va noqulayliklarni bartaraf et»; tasdiqlar: audit telemetriyasini o'chirish, `test` interval/demo xodimlarni tozalash, HTTPS (HTTP ham qolsin).
- O'zgargan: backend (`auth`, `audit_log`, `references`, `maintenance*`, `schemas`, `cli`, `wialon_health`), frontend (`api-base`, `api`, `use-realtime`, jadval sahifasi, users), `docker-compose.yml`, `Caddyfile`, `.gitattributes`, `scripts/backup_loop.sh`, testlar (`test_fixall_units.py`, `test_fixall_pg.py`, `api-base.test.ts`), `e2e_live/t10_fixall_verify.py`.
- Tested: backend 553, tsc/eslint/62 unit, jonli 32/32 + Edge 14/14, ZZTEST qoldig'i 0. NOT tested: mijoz PC'larida sertifikat, Windows `curl` HTTPS, avtomatik dumpdan tiklash.
- Keyingi qadam: sertifikatni mijozlarga o'rnatish, commit, Wialon `cneh`.

## 2026-11-16: PROJECT.md yangilandi, tiklash va auditlar
- Task: foydalanuvchi to'liq ruxsat berdi; PROJECT.md ning 12 va 15-bo'limlari hozirgi holatga keltirildi.
- Tekshirildi: `auto-*.dump` ni `pg_rehearse` ga tiklash (73 jadval, `0032_tirik_reja`, fixed_assets 1075 = jonli, users 18 = jonli); `test_schema_drift` 5/5; `npm audit --omit=dev` (3 ta: next/postcss, zod, xlsx — tuzatish katta o'zgarish, bajarilmadi).
- NOT tested: GitHub Actions natijasi, haqiqiy AD paroli, mijoz PC'larida sertifikat.
- Keyingi qadam: biznes qarorlar va vagon intervallari/baseline ma'lumotlari (foydalanuvchidan).

## 2026-11-16: Karta (xarita) bo'limi
- Task: Аналитикадан keyin «Карта» bo'limi, Google xarita, Wialon va GTK dan har bir asosiy vosita qayerdaligini ko'rsatish.
- Qo'shildi: migratsiya `0033_wialon_position` (Wialon `lat/lon/position_at`), Wialon pozitsiyasini o'qish/saqlash, `GET /api/v1/map/assets` (`routers|services|repositories|schemas/asset_map.py`), `app/dashboard/map/` (Google xarita + klaster, kalitsiz zaxira variant), `lib/map-view.ts`, `lib/api.ts`, yon menyu, Dockerfile/compose/`.env.example` (`GOOGLE_MAPS_API_KEY`), testlar (`test_asset_map.py`, `map-view.test.ts`), `e2e_live/t11_map_verify.py`, `browser/b05_map.mjs`.
- Tested: backend 569, tsc/eslint 0 xato, 68 unit; migratsiya up/down/up (pg_rehearse) va jonli; jonli API 19/19, Edge 9/9; ZZTEST qoldig'i 0. NOT tested: Google kaliti bilan interaktiv xarita (kalit yo'q).
- Keyingi qadam: Google kalitini olib `.env` ga qo'yish va frontendni qayta qurish.

## 2026-11-17: Karta — OpenStreetMap zaxirasi (kalitsiz)
- Task: Google kaliti (karta) yo'q, shuning uchun Google (kalit bilan) + OpenStreetMap (kalitsiz) birga.
- Qo'shildi: `leaflet`, `leaflet.markercluster` (+tiplar), `app/dashboard/map/_components/OsmAssetMap.tsx`, `app/dashboard/map/page.tsx` (Google → OSM → eski embed), `browser/b05_map.mjs` (OSM tekshiruvlari).
- Tested: `tsc` 0 xato, `eslint` 0 xato, 68 unit, `npm run build` OK; frontend jonli qayta qurildi (healthy); Edge 10/10 (OSM plitkalari 9/9 yuklandi, klaster, popup, filtr, master doirasi, telefon eni); ZZTEST qoldig'i 0. NOT tested: Google kaliti bilan xarita.
- Keyingi qadam: (ixtiyoriy) Google kaliti; 401 bog'lanmagan aktivni bog'lash.

## 2026-11-17: Karta — vagonlar lokomotiv bilan (GTK sostavi)
- Task: vagonlarda GPS yo'q; sostavdagi tortuvchi lokomotiv (elektrovoz/teplovoz) joyida vagonlarni ham xaritada ko'rsatish.
- O'zgardi: `backend/app/{repositories,services,schemas,routers}/asset_map.py` (yangi manba `train`, `list_train_positions`), `lib/map-view.ts`, `lib/api.ts`, `app/dashboard/map/page.tsx`, `GoogleAssetMap.tsx`, `OsmAssetMap.tsx`, testlar (`test_asset_map.py` 21, `map-view.test.ts`), `e2e_live/t11_map_verify.py`, `browser/b05_map.mjs`.
- Tested: backend `test_asset_map.py` 21 (PG bilan); to'liq to'plam 573 o'tdi, 1 yiqildi (`test_maintenance_schedule_interval_km_pg`, sana bog'liq, mening o'zgarishimga aloqasi yo'q); tsc/eslint 0 xato; 69 unit; build OK; backend+frontend jonli qayta qurildi (healthy); jonli API 25/25, Edge 11/11; ZZTEST qoldig'i 0. Jonli natija: Wialon 87, sostav 478, GTK 91.
- Keyingi qadam: `test_maintenance_schedule_interval_km_pg` ni tuzatish (17-noyabrdan boshlab yiqiladi, sanani 16-noyabrga qo'ysak o'tadi).

## 2026-11-17: Karta — «Без координат» tafsilot sahifasi
- Task: «Без координат: 419» yozuvini bosilganda alohida sahifa: qaysi aktiv, qancha vaqt, qayerdan, nega.
- O'zgardi: `backend/app/{repositories,services,schemas,routers}/asset_map.py` (`GET /map/unplaced`, `classify_unplaced`, `find_gtk_candidate`, `build_unplaced`), `lib/map-view.ts` (tiplar, `reasonExplanation`, `sinceText`, `sourceText`, `candidateText`), `lib/api.ts`, `app/dashboard/map/page.tsx` (chip = Link), `app/dashboard/map/unplaced/page.tsx` (yangi), `GoogleAssetMap.tsx` (kalit keyin rad etilsa OSM ga o'tish), testlar (`test_asset_map.py` 29, `map-view.test.ts` 75), `e2e_live/t11_map_verify.py`, `browser/b06_unplaced.mjs`, `b05_map.mjs`.
- Tested: `test_asset_map.py` 29 (PG bilan), to'liq to'plam 581 o'tdi, 1 yiqildi (sanaga bog'liq eski `test_maintenance_schedule_interval_km_pg`); tsc/eslint 0 xato; 75 unit; build OK; backend+frontend jonli (healthy); jonli API 50/50 (t11), Edge b05 11/11 va b06 11/11; ZZTEST qoldig'i 0.
- Topildi: serverdagi `.env` dagi Google kaliti Google formatida emas (`AIza` bilan boshlanmaydi) va Google `InvalidKeyMapError` qaytaradi; xarita OSM ga o'tadi. `.env` ochilmadi.
- Keyingi qadam: to'g'ri Google Maps kalitini qo'yish (yoki `GOOGLE_MAPS_API_KEY` ni `.env` dan olib tashlash); 44 ta vagonni GTK ga bog'lash (karta ОС).

## 2026-11-17: Tozalash (keraksiz fayl va o'lik kod)
- Task: keraksiz fayllarni hujjatlash, o'lik kodni aniqlash va o'chirish.
- O'zgardi: frontend 57 ta yetib bo'lmaydigan fayl (`components/ui/*`, `theme-provider`, `lib/i18n.tsx`, `hooks/`, `styles/globals.css`), `public/` 9 rasm, `.gitkeep`; backend 14 o'lik funksiya/klass (repositories/services/schemas); `package.json` va `package-lock.json` (37 paket). Yangi: `docs/CLEANUP_2026-11-17.md`.
- Tested: tsc 0 xato, eslint 0 xato, 75 unit, `npm run build` OK (paketlardan keyin ham), backend 581 o'tdi + 1 eski sanaga bog'liq xato. NOT TESTED: Docker image qurish, jonli brauzer, joylash.
- Keyingi qadam: `docker compose build frontend` + `up -d --no-deps frontend`, so'ng Edge E2E (`b01`, `b05`, `b06`); `docs/CLEANUP_2026-11-17.md` 3-bo'limidagi nomzodlar bo'yicha qaror.

## 2026-11-17: Vesovoy (vagon tarozisi) Access bazalarini o'rganish
- Task: `Bridge_Scale 93.mdb` va `Bridge_Scale 97.mdb` tuzilmasi, bog'lanishi va mantiqini o'rganish.
- O'zgardi: `.gitignore` (`*.mdb`, `*.accdb`, `*.ldb`, `*.laccdb`), yangi `docs/VESOVOY_ANALYSIS.md`. Kod va baza o'zgarmadi.
- Tested: Access nusxalari scratchpad'da `pyodbc` (ACE 64-bit, ReadOnly) bilan o'qildi; jonli PostgreSQL faqat SELECT. Prototip bog'lash: sostavlarning 88% i lokomotiv garaj raqami + vaqt bo'yicha GTK ga topildi. NOT TESTED: haqiqiy `.ecg` fayllar, vagon darajasidagi TOIR bog'lash, 7-bo'limdagi savollar (egasi javobi).
- Keyingi qadam: egasidan `docs/VESOVOY_ANALYSIS.md` 7-bo'lim javoblari, so'ng import usuli (eksport/ETL) va ТО intervali (tonna/reys) bo'yicha reja.

## 2026-11-17: Vesovoy (tarozi) real rejim arxitekturasi
- Task: ikki tarozi (93, 97) ma'lumotini doimiy olib kelish, GTK/ОС bilan bog'lash, dinamik to'g'rilash.
- O'zgardi: yangi `backend/app/{models,schemas,routers,services}/scales*.py`, `alembic/versions/0034_scales.py`, `postgres/schema.sql`, `core/permissions.py` (`scales.*`), `core/config.py`, `main.py` (router, audit istisnosi), `cli.py` (`scales-rematch`), `services/audit_log.py`; `scripts/scales_collector/` (collector, README, install_task.ps1); frontend `lib/scales-view.ts` (+test), `lib/api.ts`, `app/dashboard/scales/page.tsx`, menyu; hujjatlar `docs/SCALES_ARCHITECTURE.md`, `VESOVOY_ANALYSIS.md`; `.gitignore`.
- Tested: `test_scales.py` 14 (pure 11 + PG 3, haqiqiy hajmli bazada ham); to'liq backend toza bazada 595 o'tdi + 1 eski sanaga bog'liq xato; migratsiya down/up; tsc/eslint 0 xato, 80 unit, build OK. Haqiqiy ikki tarozidan 55 249 sostav/595 734 vagon sinov bazasiga yuklandi: GTK oynasida 88% taniladi, tarkib 98% mos. Joylandi: backend+frontend healthy, alembic `0034_scales`, jonli endpointlar tokensiz 401.
- NOT TESTED: UI ma'lumot bilan (jonli), kollektorning doimiy rejimi va Task Scheduler, jonli bazaga yuklash (token `.env` da yo'q).
- Keyingi qadam: foydalanuvchi `scripts/scales_collector/README.md` bo'yicha token qo'yadi, backfill va `install_task.ps1` ishga tushiradi; keyin ТО intervaliga tonna/reys (qaror).

## 2026-11-17 (kech): Vesovoy vagon tartibi, kollektor jonli ishga tushirildi
- Task: GTK tartibi tasdiqlandi, vagonga aniq tonna; foydalanuvchi buyruqlari `pyodbc` (venv) xatosi berdi.
- O'zgardi: `0035_scale_car_net`, `scales_matching.assign_units_to_carriages`, rematch/asset_work (`exact_share`), `docker-compose.yml` (`SCALES_INGEST_TOKEN`), kollektor (https + ildiz sertifikat, HY109 bo'yicha sana skani), `install_task.ps1` (pyodbc o'zi o'rnatadi), README, docs.
- Tested: `test_scales.py` 15, backend toza bazada 596 o'tdi + 1 eski xato, migratsiya down/up, tsc/eslint 0 xato. Joylandi (backup `pre_scale_net_20261117_1552.dump`). Jonli: backend tokenni oldi, birinchi o'tish 93: 1446 sostav/21 408 vagon, 97: 2826/41 225 yuklandi.
- NOT TESTED: UI jonli ma'lumot bilan, doimiy rejim va Task Scheduler.
- Keyingi qadam: `install_task.ps1`; `/dashboard/scales` ni tekshirish.

## 2026-11-17 (kech): Vagonlar daftari (qaysi vagon, qachon, qancha yuk)
- Task: har bir vagonning reyslari va tonnasi: mantiq va realizatsiya.
- O'zgardi: yangi `services/scales_trips.py`, `/scales/wagons`, `/scales/wagon-trips`, `/scales/wagon-trips/export.csv`, sxemalar; `asset_work` (taxminiy sostavlarda ham ulush); status hisobi (GTK tarixigacha alohida); frontend `WagonLedger.tsx`, `lib/scales-view.ts`, `lib/api.ts`; e2e `t12_scales_verify.py`, `browser/b07_scales.mjs`.
- Tested: `test_scales.py` 15; backend toza bazada 596 o'tdi (+1 eski xato); tsc/eslint 0 xato, 83 unit; jonli API `t12` (data tekshiruvlari PASS; faqat «kollektor jonli» FAIL: doimiy vazifa o'rnatilmagan); Edge `b07` 11/11 (telefonda yon siljish topildi va tuzatildi); ZZTEST qoldig'i 0.
- Xato (o'zimniki): `rehearse_env.sh` ni `docker compose` bilan bir shellda yuklab, backendni noto'g'ri bazaga ulab qo'ydim (crashloop); toza shellda qayta yaratildi, ma'lumot yo'qolmadi. Qoida: sinov env'ini compose bilan aralashtirmaslik.
- Keyingi qadam: `install_task.ps1`.

## 2026-11-17 (kech): Весовая boshqaruv markazi va kartochkalar
- Task: sahifa va undan o'tiladigan sahifalarni maksimal ma'lumotli, ko'p join li, tushunarli va ijodiy dizaynda qilish.
- O'zgardi: yangi `services/scales_insights.py`, `schemas/scales_insights.py`, endpointlar `/scales/overview`, `/trains/{id}`, `/wagon-card`, `/loco-card/{id}`; frontend `lib/scales-insights.ts` (+test), `_components/{viz,Overview,cards}.tsx`, sahifalar `train/[id]`, `wagon/[key]`, `loco/[id]`, asosiy sahifa qayta tuzildi, jadvallar havolali; e2e `t12` (+30 tekshiruv), `b08_scales_cards.mjs`.
- Tested: `test_scales_insights.py` + `test_scales.py` 16; backend toza bazada 597 o'tdi (+1 eski xato); tsc/eslint 0 xato, 89 unit, build OK; jonli API t12: 57 PASS (faqat «kollektor jim» FAIL: doimiy vazifa yo'q); Edge b07 11/11, b08 11/11 (telefon kengligi ham); skrinshotlar ko'rib chiqildi; ZZTEST qoldig'i 0.
- Keyingi qadam: `install_task.ps1`; vagonlarni ОС ga bog'lash.

## 2026-11-17 (kech): Karta qayta dizayn va pozitsiya tarixi
- Task: karta sahifasini Весовая kabi kuchli qilish; «qaysi vagon qachon qayerda edi, qaysi tortuv agregat bilan, nima qilgan».
- O'zgardi: yangi `0036_position_history`, `models/position_history.py`, `services/position_history.py` (yozish qoidasi, Wialon/GTK kancalari, backfill), `WialonClient.fetch_tracks`, CLI `wialon-track-backfill`, `services/asset_history.py` + `GET /map/history`, retention; frontend `lib/map-history.ts` (+test), `TrackMap.tsx`, sahifa `map/history/[key]`, `map/page.tsx` qayta tuzildi (KPI, filtrlar, Составы/Единицы/Сводка, inspektor); e2e `t13`, `b09`, `b05` yangi interfeysga moslandi.
- Tested: backend toza bazada 601 o'tdi (+1 eski xato), `test_asset_history.py` 4; tsc/eslint 0 xato, 97 unit, build OK; jonli: t11 44 PASS, t13 25 PASS, Edge b05 11/11, b06 11/11, b09 12/12; Wialon backfill 87 birlik/206 704 nuqta; ZZTEST qoldig'i 0.
- Topildi/tuzatildi: sinxron testi commit sonini sanaydi (kanca commit qilmasligi kerak); telefonda grid elementi `min-w-0`siz kengayardi; «trek boshlanishi» global minimum edi (endi shu aktivlar bo'yicha).
- Backup: `backups/pre_poshist_20261117_2055.dump`.

## 2026-11-17 (kech): Xaritada ikonkalar va masshtabdagi poyezdlar
- Task: nuqtalar o'rniga elektrovoz/teplovoz/vagon ikonkalari; poyezd aniq ketma-ketlik va kerakli o'lchamda.
- O'zgardi: `services/train_formation.py` + `schemas/train_formation.py` + `GET /map/trains`; frontend `lib/map-icons.ts` (+test), `OsmAssetMap.tsx` qayta yozildi (ikonkalar, poyezd ikonkasi, zoom ≥16 masshtabdagi formatsiya, tanlash/popup), `map/page.tsx` (legenda, poyezdlar), e2e `t14`, `b10`, `b05` moslandi.
- Tested: backend toza bazada 606 o'tdi (+1 eski xato), `test_train_formation.py` 5; tsc/eslint 0 xato, 105 unit, build OK; jonli: t14 16 PASS, Edge b05 11/11 (2 marta), b06 11/11, b09 12/12, b10 8/8; ZZTEST qoldig'i 0; skrinshotlar ko'rildi (poyezd temir yo'l izi bo'ylab).
- Topildi/tuzatildi: tanlash har safar hamma markerni qayta chizardi va popup bilan poyga holati bergan (`getRootNode`); endi faqat ikkita ikonka almashadi.

## 2026-11-17 (kech): GTK saytini o'rganish — GTK treki/probegi bormi?
- Task: GTK'dan Wialondan tashqari probeg olish mumkinmi.
- O'zgardi: faqat hujjatlar (`DECISIONS.md` #58 qayta yozildi, `HANDOFF.md`); kod/baza o'zgarmadi. Skriptlar scratchpad'da (faqat GET).
- Tested (o'qish): 1-akkaunt faqat poyezd sahifasi (probeg yo'q); 2-akkaunt: `get_vehicles` 242, `get_track` ishladi, 36 lokomotiv × 2 kun GTK vs Wialon median 0,96, GTK'da teshiklar.
- Xato: dastlab "GTK'dan probeg yo'q" deb yozdim (faqat 1-akkaunt asosida) — tuzatildi. Keyingi qadam: sinxron rejasi (yangi jadval) tasdiqlanishi.

## 2026-11-17 (tun): GTK GPS kanali + GPS sahifasi + birlashgan xarita
- Task: Wialon va GTK GPS alohida (trek, probeg, xarita), TOIR xaritasida birlashtirish va farqlarni ko'rsatish.
- O'zgardi: migratsiya `0037_gtk_gps`; `integrations/gtk_gps_client.py`, `services/{gps_compare,gtk_gps,gps_overview}.py`, `repositories/gps.py`, `routers/gps.py`, `schemas/gps.py`, `models/gtk_gps.py`; `asset_map` (repo/schema/service), `asset_history` (source filtri), config, compose, CLI `gtk-gps-backfill`, `main.py`; frontend `/dashboard/gps`, `/dashboard/gps/[assetId]`, `lib/gps-view.ts`, xarita sahifasi va `OsmAssetMap`; e2e `t15`, `b11`, `t11`/`b10` moslandi.
- Tested: backend 641 o'tdi (+1 eski xato), tsc/eslint 0, 125 unit, build OK; jonli: t15 40/40, t11 44/44, t13/t14 o'tdi, brauzer b11 17/17, b05 11/11, b09 12/12, b10 8/8; ZZTEST qoldig'i 0. Backup `backups/pre_gtkgps_20261117_2322.dump`.
- Topildi/tuzatildi: (1) birinchi xulosam («GTK'dan probeg yo'q») noto'g'ri edi; (2) 30 kunlik yuklash hamma trekni xotirada ushlardi -> paketlar; (3) tugamagan sinxron «failed» ko'rinardi -> faqat tugagan ishga tushirish; (4) test muhitini `docker compose` bilan bir shellda yuklash backend'ni buzdi (yana!) -> toza shellda qayta yaratildi.


- 2026-11-17: menyu qayta guruhlandi: «GPS: Wialon ↔ GTK» ostida «Карта», «Данные GTK», «Данные Wialon» (ichkarida); brauzerda admin/master uchun ko'rildi.

## 2026-11-18 (tun): GPS analitikasi (sabab, yagona trek, sog'lik), filtrlar/drawer/eksport, vagonlar bo'limi
- Task: `docs/ROADMAP_GPS_PROBEG_2026-11-18.md` bo'yicha P0–P3, P4 (faqat dry-run), P5 (AI siz: qoidali belgilar va izohlar).
- O'zgardi: migratsiya `0038_gps_analytics`; `services/{gps_analytics,gps_assessment,wagon_gps,gps_wagons,gps_overview}.py`, `routers/gps.py`, `schemas/gps.py`, `repositories/gps.py`, models, CLI `gps-analytics`, `gtk_gps` sikliga ulandi; frontend `/dashboard/gps` (filtr/facet/drawer/URL/eksport/sog'lik paneli), `/dashboard/gps/wagons`, `/dashboard/gps/wagons/[key]`, menyu (Карта, Данные GTK, Данные Wialon, Вагоны); e2e `t15` (70), `b11`, `b12`; testlar `test_gps_analytics.py`, `test_gps_analytics_pg.py`.
- Tested: backend 667 o'tdi (+1 eski xato), tsc/eslint 0 xato, 149 unit, build OK; jonli: t15 70/70, t11/t13/t14 85/86 (1 INFO), brauzer b05 11, b09 12, b10 8, b11 17, b12 15; ZZTEST qoldig'i 0. Backup `backups/pre_gpsanalytics_20261118_0033.dump`.
- Topildi/tuzatildi: faqat GTK bor birlikda haversine GTK'ning o'z masofasidan 19–27% katta chiqdi -> GTK `distance`i; vagon dry-run dastlab ledger oynasi mos emasligi uchun 15× farq ko'rsatdi -> ledger davrlari bo'yicha proporsional; wagons sahifasi telefonda yon aylanardi (`min-w-0`); bash heredoc xatolari -> fayl orqali.
- Ochiq: ledger'ga ulash (P4 oxirgi qadam) tasdiq kutadi; GTK 30 kunlik tarixi qayta yuklanmoqda (orqa fonda).

## 2026-11-18 (ertalab): aniqlangan kamchiliklarni tuzatish va rejalarni yakunlash
- Task: GTK mustaqilligini tekshirish; odometrni uchinchi manba qilish; yetim «ishlayotgan» yozuvlar; eski test xatolari; 31 kunlik tezlik; vagon dvigateli (P4) integratsiyasi.
- O'zgardi: migratsiya `0039_gps_odometer_heartbeat`; `gps_analytics` (odometr, ishonch), `gps_assessment` (odometr yuklash/saqlash/izoh), `gtk_gps` (`close_stale_runs`, heartbeat), `audit_log` (retention), `wagon_gps.make_track_fallback` + `wagon_mileage_run` (bayroq ortida), config/compose; frontend odometr ustuni; testlar (`test_gps_analytics*.py`, `test_gtk_gps_pg.py`, `test_wagon_mileage_run_pg.py` +1, 2 ta eski test tuzatildi); e2e `t15` (73), `b12` (sinxronlash mustahkamlandi).
- Tested: backend 671 o'tdi, 0 xato; tsc 0 xato; jonli: t15 73/73, b05 11, b09 12, b10 8, b11 17, b12 15 (3 marta ketma-ket); sahifa tezligi 0,33 s (31 kun, facets), sog'liq 0,14 s; yetim run'lar yopildi (0 ta tugamagan). Backup `backups/pre_gps0039_20261118_0803.dump`.
- Topildi: (1) jonli bazada o'z-o'ziga qo'shilish bilan diagnostika so'rovi ~10 daqiqa yuk berdi -> darhol to'xtatildi (bundan keyin jonli bazada faqat chegaralangan so'rovlar, statement_timeout bilan); (2) uzoq GTK tarix yuklash juda sekin (GTK eski oynalarga sekin javob beradi) — 14 kunga qisqartirib qayta ishga tushirildi.
- Ochiq: trek-zaxirani yoqish (qaror foydalanuvchida).

## 2026-11-18 (kun): Ovozli buyruq markazi (qoidali, lokal, tekin)
- Task: `docs/ROADMAP_OVOZLI_YORDAMCHI_2026-11-18.md` P0–P4: yozma va ovozli buyruqlar bilan tizimni boshqarish, erkin suhbatsiz.
- O'zgardi: migratsiya `0040_assistant`; `services/assistant/{normalize,numbers,entities,parser,catalog,engine,registry,types,speech}.py` va `handlers/*` (27 niyat, 3 yozuv executori); `routers/assistant.py`; `schemas/assistant.py`; `whisper/` konteyneri + compose; frontend `components/assistant/*`, `lib/assistant.ts`, admin sahifa; e2e `t16`, `b13`; testlar `test_assistant_{parser,engine_pg,handlers_pg,speech}.py`.
- Tested: backend 813 o'tdi (0 xato), 123 oltin jumla (uz/ru) va katalogning barcha misollari o'z niyatiga tushadi.
- Topildi/tuzatildi: katalog to'qnashuvlari (nav/summary/gps.km/mileage...), ko'p so'zli ibora va qisqa o'zak (`*`) muammolari; naryad raqami faqat «naryad N» ko'rinishida (oldindagi raqam texnika); `gtk_gps_runs` audit shovqini (11 501 qator/kun) — auditdan chiqarildi.

## 2026-11-18 (kechqurun): Ovoz tushunish darajasi
- Task: foydalanuvchi: buyruqlar 40–50% aniqlanyapti va tasdiqlashga majbur. Majburiy tasdiq olib tashlandi, parserga xato-tuzatuvchi qatlam, Whisper `small` + til tanlash + prompt.
- O'zgardi: `services/assistant/repair.py` (yangi), `parser.py`, `speech.py` (prompt_uz/ru), `whisper/{app.py,Dockerfile}`, `docker-compose.yml` (model small), `lib/assistant.ts` (+test), `components/assistant/AssistantCenter.tsx` («Исправить»), testlar (`GARBLED`, engine PG).
- Tested: backend 853 o'tdi, tsc + 165 unit; backend/frontend jonli joylandi. NOT TESTED: o'zbekcha real aniqlik, `small` kechikishi.
- Keyingi: whisper `small` image'ini joylash va o'zbekcha yozuvlar bilan o'lchash.

## 2026-11-18 (kech): AGMK tahlili asosida tekshiruv
- `entities.numbers_in`: standart (GOST/ГОСТ/ISO…) va «yil» raqamlari chiqarildi; yangi test. Backend 862 o'tdi, backend jonli joylandi (`--no-deps`). Ko'p bosqichli naryad dialogi qilinmadi (tasdiq kerak).

## 2026-11-18 (kech): ko'p bosqichli dialog
- `schemas/assistant.py` (DialogState), `engine.py`, `parser.py` (create fe'li), `lib/assistant.ts`, `AssistantCenter.tsx`; testlar: backend 864 o'tdi, frontend 165, tsc xatosiz. Backend+frontend jonli joylandi (`--no-deps`). Wake word va LLM/RAG qilinmadi.

## 2026-11-19: yordamchi tugmasi va shaxsiy tarix
- Changed: `AssistantCenter.tsx` (FAB, kichik modal, tarix ko'rinishi, foydalanuvchi kaliti), `routers/assistant.py` + `schemas` (`/assistant/history`), `lib/api.ts`, `lib/assistant.ts`, `components/ui/icons.tsx`, yangi `browser/b14_assistant_fab.mjs`.
- Tested: backend 865, unit 165, tsc; jonli brauzer b14 7/7 va b13 13/13; ZZTEST tozalandi (qoldiq 0). Telefon haqiqiy qurilmada sinalmadi.

## 2026-11-19: naryad formasi avtomatikasi
- Changed: migratsiya `0041_work_order_audit_duration`, `models/{work_orders,maintenance}.py`, `schemas/{work_orders,references}.py`, `repositories/work_orders.py`, `services/work_orders.py`, `postgres/schema.sql`; frontend `components/ui/search-select.tsx`, `lib/work-order-defaults.ts` (+test), `CreateWorkOrderModal`, `ViewEditOrderModal`, `WorkOrderList`, `RepairItemsModal`, `repairDraft.ts`, spravochnik `directories/work-types`; testlar `test_work_order_automation_pg.py`, `e2e_workorders.py` (+3 tekshiruv), `browser/b15_work_order_form.mjs`, `b16_work_type_duration.mjs`.
- Tested (lokal, tajriba bazasi + lokal next start): backend 871 o'tdi, unit 171, tsc/build, b15 12/12, b16 4/4. Jonli serverda deploy qilinmadi, migratsiya jonli bazada ishga tushmadi.

## 2026-11-20: gibrid nutq tanish
- Changed: `lib/browser-stt.ts` (+test), `components/assistant/useBrowserStt.ts`, `AssistantCenter.tsx` (parallel tanish, tanlov), `config.py`/`schemas`/`speech.py` (`browser_stt`), `docker-compose.yml`, yangi `browser/b15_hybrid_stt.mjs`.
- Tested: unit 178, tsc, backend speech/parser; jonli brauzer b15 5/5 (soxta SpeechRecognition), b14 8/8, b13 13/13; ZZTEST tozalandi. NOT TESTED: haqiqiy Google tanuvchisi.

## 2026-11-20: jurnal bo'yicha tuzatishlar
- Changed: `repair.py`, `catalog.py` (_OPEN o'zaklari, sys.bye, salomlashuv, думпкар), `numbers.py` (tartib son, ajralgan so'zlar), `handlers/system.py`, `speech.py`, testlar. Backend 882 o'tdi, jonli backend joylandi. NOT TESTED: haqiqiy ovozda.

## 2026-11-22 — audit tuzatishlari
Vazifa: tarozi kollektori, GTK poyezd yopish, vagon dvigatel. O'zgargan: `backend/app/repositories/gtk.py`, `services/gps_wagons.py`, `app/dashboard/map/page.tsx`, `docker-compose.yml`; Windows vazifa TOIR-Scales-Collector (5 daqiqalik trigger). Tekshirildi: SQL (open 37, ledger bugun), tsc. Tekshirilmadi: brauzer, testlar. Keyingi: ТО boshlang'ich ma'lumotlari, HTTP/dump qarorlari.

## 2026-11-23 — Справочник ОС «Паспорт 360°»
Yangi: `backend/app/services/asset_overview.py`, `POST /fixed-assets/overview`, `components/fixed-assets/asset-360-dialog.tsx`, jadvalga 4 ustun, `lib/api.ts` overview, `browser/b17_asset360.mjs`. Tekshirildi: Edge 11/11, tsc, eslint. Tekshirilmadi: master/management, unit test. Keyingi: overview uchun pytest, master testi.
