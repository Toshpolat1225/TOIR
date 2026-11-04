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
