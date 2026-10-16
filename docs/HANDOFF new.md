# TOIR — HANDOFF (current state and next task)

Updated: 2026-10-16. Update this file after every task. Write only facts proven by command output; everything else is **NOT VERIFIED**.

## 0. NEXT TASK (read this first)
Check the result of T4b (work-orders page moved to the API). Steps: (1) `git log --oneline -5`; (2) `grep -ri supabase app/dashboard/work-orders`; (3) `npx tsc --noEmit`; (4) ask the user to test `/dashboard/work-orders` in the browser: create an order, norm warning above 20%, status flow, no requests to supabase.co. After that: T4c tmc-documents (see section 6).

## 1. Goal
Move TOIR (maintenance/repair system for locomotives and wagons) from Supabase to: Next.js 15 frontend + FastAPI backend + PostgreSQL 16, all in Docker. Supabase is removed completely. Old Supabase data is NOT migrated, only the structure.

## 2. Where things are
- PC: `D:\Profiles\t.turakulov\My Documents\GitHub\TOIR` (git, frontend dev).
- Server (Ubuntu, SSH): `/srv/apps/toir/TOIR`. Docker project `toir`: containers `toir-backend-1`, `toir-postgres-1`. Backend only on `127.0.0.1:8010`; Postgres is not published.
- The same server runs another production system, "fuel" (containers `upjt_*`, `sttb_*`; ports 80, 443, 3000, 8000, 5432, 9090, 3100). Never touch it.
- GitHub: `Toshpolat1225/TOIR`, branch `main`. The server pulls with a read-only deploy key (ssh alias `github-toir`).
- Deploy (user only, on the server): `cd /srv/apps/toir/TOIR && ./deploy.sh`. It does git pull, build, import check, up, health check and checks that fuel containers are unchanged. `deploy.sh` is not in git.
- Frontend dev (PC): tunnel `ssh -L 8010:127.0.0.1:8010 user@SERVER`, then `npm run dev -- -H 127.0.0.1`, open `http://localhost:3000`. `NEXT_PUBLIC_API_URL=http://localhost:8010/api/v1`. CORS allows `http://localhost:3000`.

## 3. Backend (`backend/app`: core, models, schemas, repositories, services, routers)
Existing endpoints (the code in `routers/` is the truth): `/health`; `/api/v1/auth/{login,refresh,logout,me}`; users (admin only); sections, departments, employees, work-types (+subtasks), work-type-templates, maintenance-intervals; fixed-assets (+stats, mileage, mileage-history); `wialon/input` (ingest token); nomenclature, nomenclature-norms; work-orders (+`norm-check`, `template-items`).
CLI (on server): `docker compose -p toir exec backend python -m app.cli create-admin` and `... seed-reference`.
DB: 23 tables (22 + `alembic_version`), Alembic baseline `0001_baseline`, same as `postgres/schema.sql`.
Test users `*@example.invalid` stay (inactive) after e2e runs; they can be deleted with SQL.

## 4. Verified on the real server (e2e scripts, run by the user: `python3 backend/scripts/<name>.py`)
- `e2e_smoke.py` (cookie refresh, rotation, logout, 429 limiter, roles, CORS): all passed.
- `e2e_refs.py`: all passed BEFORE the employee-scope change. **Not re-run after it.**
- `e2e_assets.py` (needs env var: `WIALON_INGEST_TOKEN=$(grep '^WIALON_INGEST_TOKEN=' .env | cut -d= -f2-) python3 backend/scripts/e2e_assets.py`): all passed.
- `e2e_nomenclature.py`: all passed.
- `e2e_workorders.py`: all passed (nested repairs/items, status flow, master isolation, delete only admin/management, norm-check).

## 5. Frontend state
- On the API (tsc + build passed; login/logout/refresh checked in browser): auth, admin users, directories (employees, work-types, maintenance-intervals, sections), OS page (fixed assets), nomenclature part of the TMC page.
- **Unclear: work-orders page (T4b).** A bot was asked to move it to the API and split it into components. The result was not reported here and it was NOT browser-tested. First step: `git log --oneline -5` and `grep -ri supabase app/dashboard/work-orders`.
- Still on Supabase (not migrated): analytics, reports, maintenance (Gantt + QuickOrderModal), tmc-documents part of the TMC page, `app/api/mileage*`, `app/api/maintenance-plan`, `app/api/maintenance-schedule`, `lib/supabase*.ts`. The dashboard summary has no backend endpoint yet, so the dashboard shows errors.

## 6. Roadmap (in order)
T4b verify work-orders page -> T4c tmc-documents (backend + frontend) -> T5 ТО-plan service from `maintenance_intervals` (needs the "daily km" assumption from the user) -> T6 analytics views, dashboard summary, reports -> T7 WebSocket `/ws` (LISTEN/NOTIFY) -> T8 remove Supabase fully and leftover duplicate root files (check for `config.py`, `auth.py`, `main.py`, `api.ts` in the repo root) -> T9 ML worker -> T10 production hardening (frontend Dockerfile, HTTPS proxy, limiter in Redis/DB, CI, backups).

## 7. Open risks
- Old Supabase URL/keys were hardcoded in git history (current files are cleaned). The Supabase project must be deleted/paused or its keys rotated. The user has NOT confirmed this. The repo seems private now (the server clone needed a deploy key); not confirmed.
- `PROJECT.md` sections 7, 8, 11, 12, 13 describe the old Supabase era (outdated).
- No pytest and no CI yet. The login limiter lives in process memory.

## 8. Questions waiting for the user
Daily mileage assumption for ТО planning; delete users or only deactivate; domain/HTTPS for production; whether Wialon ingest is exposed to the internet (later, via proxy).