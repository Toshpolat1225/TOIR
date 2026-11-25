# DEMO copy (https://<host>/demo/)

The demo is a second backend + frontend that use the same Postgres container but their OWN database `toir_demo` (a copy of the
main one) and their OWN JWT secret. The main site and its database are not touched by the demo.

## What is shared and what is not
- Code (backend image, migrations): SHARED. Rebuild both after a code change: `docker compose build backend frontend frontend-demo`
  (backend-demo uses the same image as backend). Then recreate: `up -d --no-deps backend` and the demo block below.
- Data typed in the demo: stays in `toir_demo` only. It never reaches the main database.
- Login: AD as on the main site (same users table copy). Cookies are separate (paths /demo/...).
- Integrations (GTK, Wialon pulls) run in the demo too, as decided. Watch for GTK login conflicts: if GTK shows login failures,
  set GTK_SYNC_ENABLED=false in .env.demo and recreate backend-demo.

## One-time setup (user runs)
1. `.env.demo` = copy of `.env` with a DIFFERENT `JWT_SECRET` and `POSTGRES_DB=toir_demo`.
   Check that the secret differs (prints True/False only):
   `(Select-String -Path .env -Pattern '^JWT_SECRET=').Line -eq (Select-String -Path .env.demo -Pattern '^JWT_SECRET=').Line`
   -> must print False.
2. Copy the database (read-only for the main one), then build and start:
   see the step list in the chat message that came with this commit (create database, pg_dump | pg_restore, build, up, caddy reload).
3. Demo data (added after the copy): `docker compose --env-file .env.demo -f docker-compose.yml -f docker-compose.demo.yml exec -T backend-demo python -m app.cli demo-seed`
   (use `demo-seed --reset` to wipe the earlier demo rows and load again; refuses to run unless the database name is toir_demo and refuses a second run; demo records are marked: employee tab numbers D-..., nomenclature codes DEMO-..., notes contain the demo marker).
   Then load the real files into the demo the same way as for the main system (data-migration-import, repair-norms-import); the work type KR-2 is created by demo-seed.

## Removing the demo (go-live)
Give the assistant this prompt:

> Remove the demo. Stop and delete backend-demo and frontend-demo containers and the toir-frontend-demo image, drop the database
> toir_demo (after one fresh backup of the main database), remove the /demo block from Caddyfile and reload Caddy, delete
> docker-compose.demo.yml, .env.demo, docs/DEMO.md and the demo seed code (demo-seed in backend/app/cli.py, backend/app/services/demo_seed.py and
> backend/tests/test_demo_seed_guard.py; the KR-2 work type only exists in the demo until it is added to the main system by hand), keep every code change that was made for both systems (base-path support, cookie path
> setting are harmless defaults), and keep the main database untouched. List every step and what was NOT verified.
