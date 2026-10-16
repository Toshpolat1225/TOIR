# TOIR — AI WORKLOG

Append-only. After every AI session add 3-5 lines. Do not read this file unless asked.

Format:
`YYYY-MM-DD | tool/model | task | changed files | tested? (command -> result) | next step`

2026-10-16 | Claude chat | created AGENTS.md, rewrote docs/HANDOFF.md, added DECISIONS.md and this log | docs only, no code | n/a | switch to local Ollama assistant (Continue); first test task must be tiny
2026-10-16 | Copilot SDK | P-T8 cleanup: removed obsolete client, route, SQL, and archive copies; standardized npm metadata | frontend, backend scripts, docs | validation pending | run tsc/build, Python syntax checks, and source scan
2026-10-16 | Copilot SDK | P-T8 validation | npm build + tsc passed after refreshing generated route types; Python syntax checks passed; source scan empty | PostgreSQL and browser NOT TESTED | next: implement P-T9 ML worker
2026-10-16 | Codex | Added API-based demo seed/remove script | backend/scripts/seed_demo.py, docs/HANDOFF.md, docs/AI_WORKLOG.md | Python AST syntax check only; script/API/server NOT TESTED | user review, then run against intended API if desired
2026-10-16 | Codex | Investigated Maintenance fetch and TMC 404; added read-only TMC list API and UI error states | backend TMC router/service/repository/schema, main.py, lib/api.ts, Maintenance/TMC pages, docs | tsc + Python syntax passed; build/API/CORS NOT TESTED | inspect browser request URL/CORS and deploy backend change
