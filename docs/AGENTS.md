# TOIR — rules for AI assistants

Reply to the user in Uzbek, in simple short words. The user is a beginner: give terminal commands as small copy-paste blocks and label each one **[PC]** (Windows PowerShell) or **[SERVER]** (SSH).

## Read order (do not read the whole repo)
1. This file.
2. `docs/HANDOFF.md` — current state and next task.
3. Only if the task needs it: `PROJECT.md` (business rules: sections 5, 9, 10), `docs/DECISIONS.md`, `backend/app/routers/` and `schemas/`, `postgres/schema.sql`.

## Project in 3 lines
TOIR = web system for locomotive/wagon maintenance and repair. Russian UI, currency UZS.
Next.js 15 frontend + FastAPI backend + PostgreSQL 16 in Docker. Supabase is being removed completely.

## Hard rules
- Never say "works / passed / fixed" unless you ran a command and saw its output. Otherwise write **NOT TESTED**. At the end always list what you did NOT verify.
- Never print or write secrets: passwords, tokens, keys, DB URLs with passwords. Never open or edit `.env` or `.env.local`.
- Forbidden commands: `git reset --hard`, `git clean`, `git push --force`, `git checkout .`, `rm -rf`, `docker system prune`, `docker volume prune`, `docker compose down -v`. No mass delete or rename of files.
- Do not run `git pull`, `git commit`, `git push` yourself. The user does it.
- Do not change the database schema or migrations (`backend/alembic`, `postgres/schema.sql`) without an explicit plan and approval.
- Server: another production system called "fuel" runs on the same server. Never touch its containers (`upjt_*`, `sttb_*`), its ports (80, 443, 3000, 8000, 5432, 9090, 3100), nginx or files. You never connect to the server (no ssh). Deploy, docker and e2e tests are run only by the user; give them as copy-paste blocks.
- Smallest correct change. Do not rewrite working code. One task at a time. For a big or risky change show a plan first and wait for approval.
- If an error appears: read the error/log and find the cause first. No random repeated edits.

## Code rules
- Backend layers: `routers -> services -> repositories -> schemas` in `backend/app/`. List response `{items,total,limit,offset}`; errors `{"detail": ...}`; delete returns 204; `sort_by` only from a whitelist.
- Roles: admin, operator, master, management. A **master sees only his own section**. Enforce it on the SERVER inside the DB query, return **404** for other sections' records, and do it BEFORE any status or conflict checks.
- Frontend: call the backend only through `api.<resource>.<method>()` in `lib/api.ts`. No `supabase-js` in new code. UI text stays Russian.
- Python 3.12 (Docker image). Frontend dev: `npm run dev -- -H 127.0.0.1`. If styles break: stop the dev server, delete the `.next` folder, start again.

## Checks before saying "done"
- Frontend: `npx tsc --noEmit` and `npm run build` (never while the dev server is running).
- Backend: locally only a syntax check. Real tests are the e2e scripts in `backend/scripts/` that the user runs on the server. Write e2e checks for every new endpoint in the same style, but never claim they passed.

## After every task (keep it short)
- Update `docs/HANDOFF.md`: sections "Verified" and "Next task" (only facts proven by output).
- Add 3-5 lines to `docs/AI_WORKLOG.md` (date, task, changed files, tested or not, next step).
- New decision: add to `docs/DECISIONS.md`.
- Tell the user: changed files, what was NOT tested, and the first step of the next task.
