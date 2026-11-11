# TOIR — yakuniy audit va handoff

Audit sanasi: 2026-10-16. Xulosalar lokal repository'dagi o'qilgan fayllar va mavjud oldingi
tekshiruv natijalariga asoslanadi. Server, production database va deploy tekshirilmagan. Maxfiy
qiymatlar bu hujjatga kiritilmaydi.

## 1. Maqsad va arxitektura

TOIR lokomotiv, teplovoz va vagonlar uchun texnik xizmat, ta'mirlash, ehtiyot qismlar, asosiy
vositalar, hisobot va tahlilni boshqaradi.

- Frontend: Next.js 15 App Router, React 19, TypeScript; API klienti `lib/api.ts`.
- Backend: Python 3.12, FastAPI, SQLAlchemy async, asyncpg, Alembic.
- Ma'lumotlar bazasi: PostgreSQL 16; kanonik yangi-install sxemasi `postgres/schema.sql`,
  evolyutsiya `backend/alembic/versions/`.
- Production konfiguratsiyasi: Caddy reverse proxy, Docker Compose; faqat proxy host portlarini
  chiqaradi, backend/PostgreSQL Compose ichki tarmog'ida (`docker-compose.yml`, `Caddyfile`).
- Auth: JWT access token va HttpOnly refresh cookie. Realtime: Postgres LISTEN/NOTIFY orqali
  backend `/ws`. Wialon qabul qilish: `/api/v1/wialon/input`.
- Eski ma'lumotlar avtomatik ko'chirilmaydi.

Manbalar: `PROJECT.md`, `README.md`, `backend/app/main.py`, `docker-compose.yml`.

## 2. Git holati

- [CONFIRMED] `.git/HEAD` `refs/heads/main` ga ishora qiladi. Branch ref'dagi HEAD:
  `cb7dd81674d35fda2e9ca8cce25a67ec3f98fd73` (`P-T10`).
- [CONFIRMED] HEAD reflog'da P-T5–P-T10 commit yozuvlari bor. P-T9:
  `a983493c1db25980e9c2b96c8e1d7cab1c069a0b`; P-T10: yuqoridagi HEAD.
- [UNKNOWN] Staged/unstaged o'zgarishlar va `.env.local` tracked yoki yo'qligi. Git CLI
  joriy PATH'da topilmadi; `git status` va `git diff` bajarilmadi. Reflog ishchi daraxtni
  ko'rsatmaydi.
- [CONFIRMED] Ushbu auditda faqat `docs/HANDOFF.md` o'zgartirildi; commit qilinmadi.
- [UNKNOWN] Auditdan oldin mavjud bo'lgan o'zgarishlar va ularning commitga kirgani.

Git mavjud muhitda tekshirish uchun:

```sh
git status --short --branch
git log -8 --oneline --decorate
git diff --check
git diff --stat
git ls-files .env .env.local backups
```

`git ls-files` maxfiy fayl yoki backup uchun hech narsa qaytarmasligi kerak. `.env.local` mazmunini
chiqarma.

## 3. Frontend/backend holati

- [CONFIRMED] `backend/app/main.py` auth, users, references, nomenclature, assets, Wialon,
  work-orders, maintenance, ML va analytics routerlarini `/api/v1` ostida ulaydi; realtime
  `/ws` sifatida ulanadi. Backend qatlamlari routers/services/repositories/schemas/models.
- [CONFIRMED] Frontend sahifalari `app/`, umumiy API so'rovlari `lib/api.ts`; E2E skriptlar
  `backend/scripts/e2e_*.py` ichida.
- [UPDATED] TMC hujjatlari uchun GET ro'yxat route'i `backend/app/routers/tmc_documents.py`
  orqali ulandi; mahalliy manba kodi bu route'ni taqdim etadi. Backend runtime/deployment
  tekshirilmagan. Keyingi UI tekshiruvida hujjatlar faqat ko'rish/chop etish uchun; hozircha
  create/update/delete endpoint talab qilinmaydi.
- [REPORTED] Oldingi sessiyada `npx tsc --noEmit`, `npm run lint`, `npm run build` muvaffaqiyatli
  bo'lgani xabar qilingan; lint/build'da 2 ta React Hook dependency warning bo'lgan. Bu auditda
  build qayta bajarilmadi.
- [UNKNOWN] Joriy ishchi daraxt bilan frontend/backend build va browser runtime holati.

## 4. Supabase migratsiyasi

- [CONFIRMED] Source ichida `supabase`/`Supabase`, `@supabase`, `createClient` qidiruvlari
  (node_modules, `.next`, `.git` chiqarilgan) natija bermadi. `**/*supabase*` file glob ham
  natija bermadi; `package.json` va `package-lock.json` ichida Supabase dependency yo'q.
- [UNKNOWN] Git tarixidagi o'chirilgan fayllar yoki ignored lokal fayllarda oldingi Supabase
  kod/credentials bo'lgan-bo'lmagani; Git history secret scan bajarilmadi.
- [CONFIRMED] TMC hujjatlari frontend API chaqiruvlari Supabase ishlatmaydi, lekin tegishli
  backend CRUD route'i yo'q (3-bo'lim). Bu qolgan Supabase izi emas, tugallanmagan integratsiya.

## 5. Auth, rollar va ruxsatlar

- [CONFIRMED] `/api/v1/auth/login`, `/refresh`, `/logout`, `/me` `backend/app/routers/auth.py`
  da mavjud va `backend/app/main.py` orqali ulanadi. `get_current_user` access token turini,
  subject UUID'ni va aktiv userni tekshiradi.
- [CONFIRMED] Parol bcrypt bilan hash qilinadi; 72 UTF-8 byte'dan uzun parol rad etiladi.
  Refresh token o'zi emas, SHA-256 xeshi saqlanadi. Manbalar:
  `backend/app/core/security.py`, `backend/app/services/auth.py`, `postgres/schema.sql`.
- [CONFIRMED] User CRUD faqat admin; ko'rilgan references/assets/work-orders/analytics/WebSocket
  yo'llarida server-side role yoki section tekshiruvlari mavjud.
- [CONFIRMED] Login limiter PostgreSQL `login_attempts` jadvalida HMAC key bilan 15 daqiqalik
  sliding window va 5 ta muvaffaqiyatsiz urinish limitini ishlatadi. Model, `0005_login_attempts`
  migration va schema ta'riflari mavjud. Ishlab turgan DB'da migration qo'llangani noma'lum.
- [HIGH][CONFIRMED] Maintenance schedule/plan GET'larida master section scope yo'q:
  `backend/app/routers/maintenance.py` userni qabul qilsa-da service'ga uzatmaydi;
  `backend/app/services/maintenance.py` va `backend/app/repositories/maintenance.py` esa
  section filter'siz barcha reja va schedule work-order'larini so'raydi. Boshqa section
  ma'lumotlari master javobiga kirishi mumkin. Bu statik kod xulosasi; API exploit testi yo'q.
- [UNKNOWN] Barcha endpointlarning to'liq role/scope correctness'i va production user/role
  sozlamalari; DB/API integration tekshiruvi bajarilmadi.

## 6. Database schema va kod mosligi

- [CONFIRMED] `postgres/schema.sql` jadval nomlari ORM `__tablename__` nomlari bilan asosan
  mos ko'rinadi; login limiter jadvali ham schema va `0005` migratsiyada bor. `0001_baseline`
  SQL faylidan bazaviy sxemani qo'llaydi; keyingi migratsiyalar 0002–0005.
- [UNKNOWN] Har bir ustun, type, nullable, constraint, index va FK'ning schema/model/migration
  bilan to'liq 1:1 mosligi. Schema diff qilinmadi va real PostgreSQL migration ishlatilmadi.
  Production database holati noma'lum.
- [CONFIRMED] Ko'rilgan analytics raw SQL'da view nomi `ANALYTICS_VIEWS` allowlist bilan,
  section/limit/offset qiymatlari bind parameter bilan cheklangan. Statik qidiruvda boshqa
  interpolatsiya orqali user input kiritish topilmadi. Bu formal to'liq repository guarantee
  emas.
- [MEDIUM][CONFIRMED] `GET /api/v1/dashboard/summary` `save_daily_readiness_snapshots` chaqiradi;
  `backend/app/repositories/analytics.py` upsert va `db.commit()` qiladi. Ya'ni GET so'rovi
  ma'lumotlar bazasini o'zgartiradi. Snapshot yozuvini scheduler/command yoki aniq mutation
  endpointiga ko'chirish, yoxud bu xatti-harakatni hujjatlashtirib testlash kerak.

## 7. Test/build dalillari

- [CONFIRMED] Backend test fayllari: `test_auth_limiter.py`, `test_analytics.py`,
  `test_analytics_sql.py`, `test_maintenance_planning.py`, `test_ml.py`, `test_realtime.py`.
  E2E skriptlar: `e2e_smoke.py`, `e2e_refs.py`, `e2e_assets.py`, `e2e_nomenclature.py`,
  `e2e_workorders.py`.
- [REPORTED] Oldingi sessiyada frontend TypeScript check/build o'tgan, lint 2 warning bilan
  yakunlangan; Compose/CI YAML parse qilingan.
- [REPORTED] Oldingi sessiyada backend testlari Python 3.12 yo'qligi (muhitda 3.14.7 va backend
  dependency'lari o'rnatilmagan) sabab bajarilmagan. Docker CLI yo'qligi sabab Docker/Compose
  runtime, image build va shell skript tekshiruvi ham bajarilmagan.
- [NOT_DONE] Joriy auditda test, build, Alembic, E2E, Docker, browser, server yoki DB
  tekshiruvlari ishlatilmadi; oldingi natijalar qayta tasdiqlanmadi.
- [UNKNOWN] GitHub Actions'dagi oxirgi CI natijasi.

## 8. Xavfsizlik natijalari

### Critical

- [CONFIRMED] Statik auditda Critical darajadagi zaiflik tasdiqlanmadi.

### High

- [HIGH][CONFIRMED] Master maintenance schedule/plan scope muammosi (5-bo'lim): boshqa section
  aktivlari/rejalari/buyurtmalari ochilishi mumkin. P0 sifatida tuzating va regression test yozing.
- [HIGH][REPORTED] Oldingi `npm audit` natijasida production dependency'larda 1 High va
  1 Moderate, to'liq dependency tree'da 7 High va 1 Moderate advisory bildirilgan. Next.js
  `15.5.28` patchidan keyin ham `next` ichidagi PostCSS advisory qolgan, npm force update uchun
  Next.js `16.4.2` taklif qilgan; `xlsx` uchun fix yo'q deb ko'rsatilgan. Joriy auditda audit
  qayta ishlatilmadi, amaldagi holat [UNKNOWN].

### Medium

- [MEDIUM][UPDATED] TMC ro'yxat GET route'i qo'shildi; production'da mavjudligi tekshirilmagan.
  TMC create/update/delete route'lari yo'q.
- [MEDIUM][CONFIRMED] `scripts/backup_postgres.sh` `./backups` ichiga DB dump yozadi, ammo root
  `.gitignore` `backups/` ni ignore qilmaydi. `.dockerignore` uni chiqaradi; Git'ga tasodifan
  qo'shib yuborish xavfi qolgan. Hozir backup borligi yoki track qilingani noma'lum.
- [MEDIUM][CONFIRMED] Dashboard summary GET database snapshot yozadi (6-bo'lim).
- [MEDIUM][UNKNOWN] `.env.local` diskda mavjud; `.gitignore` `.env.*` ni ignore qiladi, ammo
  Git CLI yo'qligi sabab tracked holati noma'lum. Fayl mazmuni o'qilmadi.

### Low va kuzatuvlar

- [LOW][CONFIRMED] `PROJECT.md` production proxy/Docker/CI'ni hali kelajak ishi deb ko'rsatadi,
  `README.md` va production fayllar esa P-T10 setup'ini hujjatlashtiradi. Hujjatlarni
  moslashtirish kerak.
- [LOW][REPORTED] Lint/build'da 2 React Hook dependency warning bo'lgan.
- [CONFIRMED] `backend/app/core/config.py` aniq HTTP(S) CORS origin'larini talab qiladi va
  wildcard origin'ni rad etadi. Bu config xususiyati, production qiymatlar tekshirilmagan.
- [UNKNOWN] Git tarixida secret mavjudligi; secret-history scan bajarilmadi. Maxfiy fayl
  mazmuni ataylab ochilmadi.
- SQL injection: [CONFIRMED] ko'rilgan analytics SQL allowlist va bind parameter ishlatadi;
  statik source qidiruvi user input bilan xavfli SQL interpolation topmadi. Audit formal/to'liq
  repository verification emas.

## 9. Uchta audit topshirig'i holati

| Topshiriq | Holat | Dalil |
|---|---|---|
| Git holati/tarixi, frontend/backend va Supabase read-only auditi | `PARTIALLY_COMPLETED` | Branch/HEAD/reflog va source Supabase qidiruvi tekshirildi; working-tree status, diff va tracked secrets Git CLI yo'qligi sabab tekshirilmadi. |
| `docs/HANDOFF.md`ni real holat bo'yicha yangilash | `CONFIRMED_COMPLETED` | Ushbu audit faylni status belgilari, kod dalillari, xavflar va yangi-session prompt bilan yangiladi. |
| Auth/role/SQL injection/secrets/schema/error/test auditi | `PARTIALLY_COMPLETED` | Auth, tanlangan router/service/repository, migration va test fayllari statik ko'rildi. Runtime, DB, to'liq schema parity, barcha route va Git history tekshiruvi yo'q. |

## 10. Avvalgi P-T vazifalari

Holatlar repository dalili yoki oldingi sessiyada xabar qilingan lokal tekshiruvlarga tegishli;
production tayyorligi degani emas.

- [CONFIRMED] HEAD reflog'da P-T5, P-T6, P-T7, P-T8, P-T9 va P-T10 commitlari qayd etilgan.
- [CONFIRMED] Joriy source qidiruvda P-T8 talabiga ko'ra Supabase matn/fayl/dependency izlari
  topilmadi; TMC documents CRUD route'i esa hali yo'q.
- [PARTIALLY_COMPLETED] P-T9 ML service/router/model kodlari va `test_ml.py` mavjud; test va
  background DB flow ushbu auditda ishga tushirilmadi.
- [PARTIALLY_COMPLETED] P-T10 Docker/proxy, PostgreSQL login limiter, backup script, CI va README
  mavjud; frontend tsc/build oldingi sessiyada o'tdi deb xabar qilingan. Docker build, backend
  tests, migration, backup/restore, TLS va deploy tasdiqlanmagan.
- [UNKNOWN] Oldingi auth/users/references/assets/work-orders/maintenance/analytics/realtime
  vazifalari server deployment'da amalda ishlaydimi; server tekshiruvi o'tkazilmadi.

## 11. Ochiq savollar va bloklovchi tekshiruvlar

1. Git CLI bor muhitda `git status`, `git diff`, `.env.local` va backup tracking holatini aniqlash;
   Git history secret scan'ni maxfiy qiymatlarni chiqarmasdan o'tkazish.
2. Master maintenance GET schedule va GET plan uchun server-side section scope qo'shish.
3. TMC GET list route'ini xavfsiz test API muhitida tasdiqlash. Hujjat create/update/delete
   faqat UI talabi tasdiqlansa alohida rejalashtiriladi.
4. Amaldagi Next/PostCSS/xlsx audit holatini lockfile bilan qayta tekshirish; tasdiqsiz
   `--force` major upgrade qilmaslik.
5. `PROJECT.md`ni production arxitekturasi bilan moslashtirish.
6. Production domen/DNS va deploy/remote tekshiruv ruxsati mavjudligi noma'lum. Caddy Let's
   Encrypt uchun public DNS hamda TCP 80/443 talab etiladi.
7. Deployed DB schema/migration holati noma'lum; production DB'ga tegish uchun avval backup va
   foydalanuvchining aniq ruxsati kerak.

## 12. Keyingi eng muhim vazifa (P0)

`backend/app/routers/maintenance.py`, `backend/app/services/maintenance.py` va
`backend/app/repositories/maintenance.py` orqali `master` foydalanuvchisining section scope'ini
GET maintenance schedule va GET maintenance plan'ga server tomonda qo'llang. Master uchun
scope'ni authenticated user'dan oling; query parametri yoki klient filtriga ishonmang.
Schedule ichidagi work-order'lar ham faqat shu section'dan bo'lsin. Scope'siz master'ga
ma'lumot bermang. Boshqa section ID bilan ma'lumot olinmasligini regression testlar bilan
tasdiqlang; admin/operator xatti-harakatini saqlang. Deployment yoki production DB tekshiruvidan
oldin foydalanuvchidan alohida ruxsat oling.

Keyingi tartib: P1 — TMC documents CRUD; P1 — dependency advisory'larni qayta tekshirib
bartaraf etish rejasini tuzish; P2 — `backups/` ni Git ignore'ga kiritish va tracking'ni tekshirish;
P2 — dashboard GET snapshot side effect'ini hal qilish; P3 — Python 3.12 backend test, Docker/
Compose, PostgreSQL migration, backup/restore, TLS va browser integration'ni ruxsat etilgan
muhitda tasdiqlash.

## 13. Claude/Ollama uchun tayyor boshlang'ich prompt

```text
TOIR repository'da davom et. Avval docs/HANDOFF.md, PROJECT.md va README.md ni o'qi.
P0 vazifa: maintenance schedule/plan GET endpointlarida master foydalanuvchi boshqa section
ma'lumotini ko'rmasligi uchun server-side scope qo'sh va regression test yoz.

O'zgarishdan oldin git status --short --branch va git diff'ni o'qi; foydalanuvchining mavjud
o'zgarishlarini bosib ketma. Mavjud FastAPI auth, service/repository va test uslubidan foydalan;
yangi auth arxitekturasi yaratma. Master section ID'ni serverdagi authenticated user'dan ol,
klient filtri/query parametriga ishonma. Admin/operator xatti-harakatini saqla.

Secretlarni ko'rsatma: .env/.env.local/token/password fayl qiymatlarini ochma, terminal/chat/log
yoki hujjatga chiqarmagin. Serverga SSH, deploy yoki production DB komandalarini ishlatma;
bunday tekshiruv oldidan foydalanuvchidan alohida ruxsat ol. Faqat tegishli testlarni ishga tushir;
dependency/DB bo'lmasa o'tdi deb yozma. TMC documents routeri, npm audit advisory'lari,
dashboard GET snapshot yozuvi va P-T10 Docker/DB/deploy tekshiruvlari hamon ochiq.
Commit qilma. Yakunda o'zgargan fayllar, real tekshiruv natijalari va UNKNOWN holatlarni yoz.
```

## Latest task status (2026-10-16)

### Verified

- `backend/scripts/seed_demo.py` uses authenticated HTTP API calls to create or remove sample records.
- Admin credentials are prompted with `getpass`; the script contains no file writes for credentials.
- Python syntax was checked with `ast.parse`; the seed script was not executed.
- No server, deployment, or database connection was attempted.

### Next task

- Review the demo payloads, then run `seed_demo.py` only against the intended API environment. Use `--remove` to remove its DEMO-prefixed records.
- Production API and database behavior remain unverified.

## Latest error follow-up (2026-10-16)

### Verified

- The local maintenance router defines `GET /maintenance-schedule`; the browser's `Failed to fetch` is not an HTTP status and needs the configured API origin/CORS/runtime to identify the cause.
- No process was listening on local TCP port 8010 at check time. This matters only if the frontend uses the default API URL; `.env.local` was not read.
- A read-only TMC documents GET router/schema/service/repository was added and mounted locally. Python syntax check and frontend `npx tsc --noEmit` completed successfully.
- The active Next.js dev server was left running; build was not run.

### Next task

- Confirm the browser Network tab's request URL and CORS/HTTP result for the maintenance call; deploy the TMC GET route before expecting it on a remote API. TMC write routes are not implemented.

## Asset catalog management (2026-10-16)

### Verified

- Added an authenticated API for listing asset types/statuses and admin-only create/update/delete operations. Usage counts are returned; DELETE rejects referenced values with HTTP 409. Status behavior cannot be changed while assets use that status.
- Added admin page `/dashboard/admin/asset-catalogs` for three-language labels, active state, behavior and color, search/filter, usage display, and CRUD.
- Fixed-asset create/update validation now checks that selected catalog values are active. Status summaries and readiness snapshots use the status behavior group.
- Added Alembic `0007_asset_catalog_management` and updated `postgres/schema.sql`; migration was not run. Added `backend/scripts/e2e_asset_catalogs.py`; it was not run.
- Python AST syntax check passed for 12 changed Python files; `npx.cmd tsc --noEmit` exited 0; `npm.cmd run build` exited 0 with two existing React Hook warnings in work-orders files.
- No server, database, migration, API E2E, browser, or visual check was run.

### Next task

- Review the migration and catalog page, then run `e2e_asset_catalogs.py` and migration/API checks only in the intended test environment. Production migration remains a manual user-controlled step.

## Localization implementation status (2026-10-16)

### Verified

- Added locale allowlist (`uz-Latn`, `uz-Cyrl`, `ru`), validated cookie persistence, root `<html lang>`, and browser `Accept-Language` header handling.
- Added Alembic `0006_localization`, matching ORM models and fresh-install schema tables for translation rows and fixed-asset type/status catalogs. Existing names are not auto-translated.
- Added authenticated translation list/detail endpoints, admin translation edits, localized response fields for selected references, and a temporary translation E2E script. E2E script was not run.
- Localized label use is partial: navigation, login copy, parts of dashboard/reports, and selected business-data displays. See `docs/LOCALIZATION_INVENTORY.md` for the scanned source list and remaining work.
- `npx.cmd tsc --noEmit` completed with exit code 0. `npm.cmd run build` completed with exit code 0 and two React Hook warnings. Python AST syntax check completed for 18 changed Python files.
- No server, database, migration, API E2E, unit test, or browser check was run.

### Next task

- Finish `docs/LOCALIZATION_INVENTORY.md` remaining pages and components: translate every visible string, validation/error/empty/loading state, accessibility label, filter, chart and permission screen; then make ordinary resource filtering/sorting and all exports locale-aware.
- Add catalog activation/creation management and decide whether user locale should be stored on the profile. Verify migrations and the full UI/API/CRUD/export/fallback flows in an authorized test environment.
- Current implementation is partial and is not ready to claim full three-language localization.

## ОС dashboard cards (2026-10-18)

### Verified

- Asset list and dashboard stats now share server-side filters for type, exact status, status behavior, section, depot, and text search. Stats return facet counts for type, status, status behavior, section, and depots; masters are scoped to their assigned section in the query.
- The OS page has clickable type, exact-status, behavior, and section cards, separate section/depot filters, visible API errors, and retains server pagination. Cards show only known catalog types/status behaviors; there is no active/inactive asset card because `fixed_assets` has no such field.
- Added `backend/scripts/e2e_asset_dashboard.py`; it was not run. No migration or database change was made.
- Python AST syntax check passed for 5 files. `npx.cmd tsc --noEmit` exited 0. `npm.cmd run build` exited 0; it reported two existing React Hook warnings in work-orders files. No `node.exe` process was present before build.
- Browser interaction, visual/theme/mobile checks, API E2E, server, and database were not run.

### Next task

- Run `backend/scripts/e2e_asset_dashboard.py` only against the intended test API. Then review the OS cards in browser at desktop/mobile sizes and in both themes; verify master section scoping and filter combinations with actual test data.

## Organizational hierarchy assessment (2026-10-18)

### Verified

- Repository schema has separate `departments` and `sections`; `sections.department_id` is optional. `backend/app/cli.py` defines four static department/section seed pairs, but the source text is mojibaked and does not confirm live organization names.
- Existing section IDs are referenced by users, employees, fixed assets, work orders, TMC documents, maintenance logs, translations, and readiness snapshots. Their FK delete rules vary; work orders restrict deletion, while some history links become NULL.
- Current section filters are generally exact-ID filters. Master scope is currently constrained to the assigned section in backend repositories. Section CRUD is admin/operator; there is no hierarchy, active flag, or archive flow.
- No live database or server was accessed. Current production rows, actual IDs, migration revision, and parent relationships are unknown. No code, schema, or migration was changed in this assessment.

### Next task

- Await approval of the proposed additive `sections` tree plan: preserve every existing ID and FK, set all existing `parent_id` values to NULL (no guessed relationships), keep `departments` as the separate TMC/norm dimension, add translated names/category/activity/order, recursive cycle-safe moves, and archive instead of delete. Then implement the endpoint/UI and descendant filters, with master scope remaining the exact assigned unit pending an explicit business change.
- Migration dry-run, live ID mapping, rollback feasibility after new hierarchy data is entered, E2E, and UI behavior remain NOT TESTED.

## Наряд-заказ detail va filtrlar (2026-10-18)

### Verified

- Work-order list API filtrlari mavjud `date_start`, executor, work type va nested work-order item nomi/kodi bo‘yicha kengaytirildi. Sana, asset, uchastka, status, mas’ul, ish turi va material filtrlari birga yuboriladi; master section scope queryda saqlanadi.
- TMC document list API `work_order_id` filtri oldi. Master uchun service avval наряд-заказni o‘z uchastkasi bo‘yicha tekshiradi va begona/yo‘q orderda 404 qaytaradi.
- Detail modal umumiy ma’lumot va ОС holati, ishlar/reja materiallari, bog‘langan TMC hujjatlari uchun alohida tablar ko‘rsatadi. TMC miqdori “hujjat miqdori” deb belgilanadi; alohida vazifa, material qaytarish va audit trail modeli topilmadi.
- `backend/scripts/e2e_workorders.py` yangi list filterlar, detail relations, bo‘sh TMC ro‘yxati, locale ID barqarorligi va master TMC scope holatlarini tekshirish uchun yangilandi. E2E skript ishga tushirilmadi.
- Python AST sintaksis tekshiruvi 7 backend/script faylida o‘tdi. `npx.cmd tsc --noEmit` exit 0. `npm.cmd run build` exit 0; build’da 2 React Hook ogohlantirishi chiqdi. Build oldidan `node.exe` process topilmadi.
- Schema yoki migration o‘zgarmadi. Server, API, DB, E2E va browser tekshiruvlari bajarilmadi.

### Next task

- `backend/scripts/e2e_workorders.py` ni mo‘ljallangan test API’da ishga tushirish. So‘ng detail tablari va filtrlashni browser’da tekshirish, TMC document CRUD mavjud bo‘lmaganligi sabab haqiqiy bog‘langan ombor hujjati bilan UI oqimini alohida tekshirish.

## Granular RBAC (2026-10-18)

### Verified

- Existing roles remain `admin`, `operator`, `master`, and `management`. JWT access tokens do not carry roles; authenticated API requests load the active user from PostgreSQL.
- Added permission catalog, per-role grants, audit rows, an additive Alembic revision `0008_granular_permissions`, permission checks on API routers, `/permissions/me`, and an admin permissions page. Existing role access is seeded from the source role policy. `admin` permission grants are immutable; creating another admin through the users API is blocked. Master data scope remains a separate server-side query rule.
- `backend/scripts/e2e_permissions.py` covers permission denial with an existing access token, unknown/elevated grants, protected admin role, last-admin case when test DB has exactly one active admin, no-token 401, and master cross-section reads when at least two sections exist. The script was not run.
- Python AST syntax check passed for 88 files. `npx.cmd tsc --noEmit` exited 0. `npm.cmd run build` exited 0; Next.js reported two React Hook warnings in work-orders files. Build ran after confirming no `node.exe` process.

### Security notes and next task

- Production server, database, Alembic migration, E2E API calls, browser behavior, and actual permission matrix were not tested. Do not deploy the code before applying migration 0008; code expects seeded permission rows.
- All current `admin` accounts are effectively highest-level administrators; repository has no distinct super-admin identity. Admin permissions are protected, and only initial setup may create new admins through the API path.
- Existing maintenance schedule/plan master-scope issue documented in the earlier audit was not addressed here. Long-lived websocket subscriptions re-check permission every 30 seconds; this timing was not runtime-tested.
- Next: review the default role matrix, then apply migration and run `backend/scripts/e2e_permissions.py` only against the intended test API. Afterwards verify page/action visibility and section scopes in browser/API.

## User active/inactive management (2026-10-18)

### Verified

- `users.is_active` already existed with default `true`; login, refresh, HTTP access-token authentication, and WebSocket authentication already reject inactive users. No user-column schema migration was needed.
- User status changes now require the dedicated `users.set_active` permission in addition to user-management access. Migration `0009_user_active_permission` adds the permission safely after RBAC migration 0008. Admin remains the only role eligible for this protected permission.
- Deactivation rejects self-blocking, retains the account/history row, preserves the last-active-admin check, and revokes all active refresh tokens in the same database transaction. Existing access JWTs fail on the next authenticated HTTP request because the current active user is read from the database.
- The admin user page displays/filter statuses and asks for confirmation before activation changes. No user-status audit rows existed; the page cannot show who made an earlier change or when.
- Added `backend/scripts/e2e_user_status.py` for login, inactive access/refresh rejection, permission denial, last-admin/self protection, and account retention. The script was not run.
- [CONFIRMED] Python AST syntax check passed for 6 backend/service/migration/E2E files. `npx.cmd tsc --noEmit` exited 0. `npm.cmd run build` exited 0 with two existing React Hook warnings in work-orders files; no `node.exe` process was running before build.

### Next task

- Apply migration 0009 and run the new E2E script only against the intended test API; verify the user page in a browser.
- Migration, API, database, E2E, and browser behavior are NOT TESTED. The E2E script will leave its temporary account inactive because there is no user-delete API.

## Work-order opening mileage report (2026-10-18)

### Verified

- `work_orders.mileage_at_creation` already exists and is set by the server when opening an order. A client cannot provide this snapshot. The asset row is locked during creation so its current mileage does not change inside that transaction.
- An asset's default mileage `0` is treated as unknown unless `mileage_history` confirms a recorded zero. Historical NULL snapshots remain NULL; they are never filled from today's asset mileage.
- Reports and CSV now use the stored opening snapshot. The work-order report has an asset/order search, status filter, and mileage range; the displayed column names cover Russian, Uzbek Latin, and Uzbek Cyrillic.
- Reassigning a work order to another asset after opening is rejected to preserve the snapshot's meaning. Negative manual and Wialon mileage is rejected. No schema or migration change was needed.
- `backend/scripts/e2e_workorders.py` now covers known and unknown snapshots, snapshot immutability, reassignment rejection, negative readings, report filters, and CSV output. It was not run.
- Python AST syntax check passed for the changed backend and E2E files. `npx.cmd tsc --noEmit` exited 0. `npm.cmd run build` exited 0 with two React Hook warnings in existing work-order files; no `node.exe` process was running before build.

### Next task

- Run `backend/scripts/e2e_workorders.py` against the intended test API, then check the report table and filters in a browser. Production server, database, API, E2E, and browser behavior are NOT TESTED. Snapshot source and exact measurement timestamp are not stored reliably, so the report shows the opening snapshot and km unit without claiming a source timestamp.

## Global list filters (2026-10-18)

### Verified

- List-page audit: fixed assets already use server-side search/facets with pagination; work orders already use server-side date, status, asset, section, executor, work type, and material filters with pagination and a sort whitelist. Nomenclature already supports server-side name/code and department filters. Reports use server-side query filters and CSV, but the report page requests up to 1000 rows. Section/department/work-type/reference pages commonly request up to 1000 rows; maintenance planning is a schedule view, not a conventional paginated list.
- Added server-side `q` and active status filters for employees; `q` for work types; `q` and active status for users; and search, status, and document-date filters for TMC documents. Employee, user, and TMC document screens now request 50-row pages and show result totals/navigation. Search inputs use a shared debounce helper on the updated pages.
- Existing master scope remains in the repository query for employees and TMC documents; user access remains admin-permission protected. Filter values are bound through SQLAlchemy expressions and query string lengths are capped at 200; TMC date ranges reject reversed dates.
- Added E2E assertions to `e2e_refs.py`, `e2e_user_status.py`, and `e2e_workorders.py`. Python AST syntax check passed for 12 backend/script files. `npx.cmd tsc --noEmit` exited 0. `npm.cmd run build` exited 0 with two React Hook warnings in work-orders files.
- `postgres/schema.sql` has indexes for common section/status/date and relation filters, but no trigram index for substring `ILIKE` search. No index, schema, or migration was added because no database `EXPLAIN` was run. No server, DB, API, E2E, or browser test was performed.
- `git status` could not be read because Git CLI is unavailable in this PC environment; pre-existing working-tree changes are UNKNOWN.

### Gaps and next task

- URL query state was not added. Department, section, maintenance-interval, translation, and catalog list screens were not all given new search controls; work-type/template and report screens retain existing high page limits. TMC status summary cards count the currently loaded page, as now disclosed in the UI.
- Run the updated E2E scripts against the intended test API, then review filter combinations, scopes, pagination and mobile/browser behavior. Before adding search indexes, inspect representative PostgreSQL plans and data size. These runtime checks remain NOT TESTED.

## Stage 10 integration and security audit (2026-10-18)

### Verified

- Static review found migrations linked in order from `0001_baseline` through `0009_user_active_permission`; model declarations include the translation, catalog, permission, active-user, maintenance-plan, TMC, and work-order mileage entities. No live database or migration was accessed, so deployed revision and live schema alignment are unknown.
- `npx.cmd tsc --noEmit`, `npm.cmd run lint`, `npm.cmd run build`, and Python AST parsing for 116 backend files exited 0. Lint and build reported two React Hook warnings. `.eslintignore` now excludes Next.js-generated `next-env.d.ts` from standalone ESLint; build ran after no node listener was found.
- Static security review found maintenance schedule/plan listing and plan update repositories/services did not apply master section scope. User update logic could demote an admin when more than one active admin existed, despite the recorded immutable-admin policy; see the later maintenance security task for code changes.
- Organization units remain flat `departments`/`sections` without a parent relationship. At audit time, the frontend declared unsupported TMC document create/update calls; see the later TMC contract task. Dashboard issues were corrected in the later dashboard task. Localization inventory confirms broad Russian hardcoded UI remains.
- Work-order report uses the opening snapshot through `executive_summary.current_mileage`, which derives from `work_orders.mileage_at_creation`. At audit time, dashboard readiness counted cancelled orders with NULL `closed_at` as open and matched orders to assets by name; see the later dashboard correction task. Git status/diff could not be checked because Git CLI is unavailable. No database, migration, API, production server, E2E, backend unit test, or browser test was run.

### Next task

- Git diff, live migration/schema alignment, API behavior, and production readiness remain NOT TESTED.

## Maintenance scope and admin role protection (2026-10-19)

### Verified

- Static source review confirmed the schedule route did not pass the authenticated user into the service; maintenance schedule and plan queries were not consistently section-scoped. `update_plan` looked up plans without a section filter before status checks. Work-order creation also looked up a supplied maintenance plan without master scope.
- Maintenance services now derive master scope only from authenticated `User.section_id`, reject a master with no section, and pass that scope to schedule asset/order/plan queries, plan listing, plan update lookup, and linked work-order lookups. Repository queries filter assets/plans/orders in SQL. Out-of-scope plans and linked work orders return 404 before status/conflict checks.
- Admin demotion is rejected server-side even when multiple active admins exist; the last-active-admin guard runs first and retains its 409 protection. Existing self-deactivation protection remains in place. Added mock-only regression tests for master scope, missing section, cross-section update/link, admin demotion/last admin, and ordinary role update.
- No schema or migration was changed. Python syntax, unit behavior, API behavior, database scope, E2E, and browser behavior are NOT TESTED yet.

### Next task

- Have the user run the mock regression tests in the local test environment and any API E2E only against the intended test API. Do not use production server or database. Test execution and runtime authorization remain NOT TESTED.

## Dashboard calculation corrections (2026-10-19)

### Verified

- Business status rules confirm `pending -> in_progress -> completed | cancelled`; only `completed` requires `closed_at`, and the update service writes `closed_at` when completing an order. Monthly readiness trend now excludes `cancelled` orders while preserving the existing historical close-date predicate for the other statuses.
- Dashboard work-order rows now include `fixed_asset_id` in the SQL response, API schema, and TypeScript type. Dashboard availability cards match open orders to assets by ID instead of display name. Daily readiness snapshot code was not changed.
- Added backend mock regression tests for cancelled exclusion and retained close-date logic, master section scope, and distinct asset IDs when names match. Python AST syntax check passed for 6 files. `npx.cmd tsc --noEmit` exited 0. `npm.cmd run build` exited 0; it reported two React Hook warnings in work-orders files.
- Backend tests, database query results, API response at runtime, E2E, and browser behavior are NOT TESTED.

### Next task

- Have the user run the dashboard regression tests against a safe local test setup and confirm master scoping and duplicate-name asset matching through the API/UI. Production server/database and runtime behavior remain NOT TESTED.

## TMC document API contract (2026-10-19)

### Verified

- TMC document UI uses GET list to show and print existing documents. Work-order detail also uses GET list for linked warehouse documents; its TMC draft editor updates work-order repair items through work-order create/update. No UI calls TMC document create, update, or delete. Nomenclature CRUD on the TMC page uses separate inventory endpoints.
- Backend TMC document router exposes GET only; service applies master section scope and checks a requested work order before querying linked documents. `tmc.view` is the only TMC permission. Document statuses are constrained to `draft`, `issued`, and `closed`; item rows belong to documents. No document history/audit model was found.
- Removed unused TMC document create/update/delete client methods. No endpoint, permission, migration, or schema change was added. Added contract tests for read-only routes and master section behavior. Fixed the TMC repository's missing SQLAlchemy `exists` import used by search.
- Python AST syntax check passed for 6 TMC/backend test files. `npx.cmd tsc --noEmit` exited 0. `npm.cmd run build` exited 0 with two React Hook warnings in work-orders files. Backend tests, API, E2E, database, and browser behavior are NOT TESTED.

### Next task

- Have the user run the TMC contract tests in a safe local test setup. If document creation or editing becomes a UI requirement, first define stock movement, status transitions, audit/history, scope, granular permissions, and migration plan; do not add hard-delete behavior.

## Read-only system analysis (2026-10-19)

### Verified

- Read `docs/HANDOFF.md`, `PROJECT.md`, `docs/DECISIONS.md`, `README.md`, `docker-compose.yml`, `backend/app/main.py`, schema `CREATE TABLE` list, router/model/service/repository listings, frontend page list, and `docs/AI_WORKLOG.md` tail. No application code was changed.
- `git status --short --branch`: clean working tree, `main` in sync with `origin/main`; recent commits `8090d7e server refresh`, `ddfd342 local error`, `6817aa3` PROMPT F, `9418179` PROMPT E, `dbcb306` PROMPT C. Section 2 git notes above are outdated.
- No server, database, API, tests, builds, or browser checks were run.

### Next task

- Unchanged from the pending items above: the user runs the mock regression tests (maintenance scope, dashboard, TMC contract) and the E2E scripts only against the intended test API; migrations 0006–0009 must be applied before that code is deployed.

## Full audit report (2026-10-19)

### Verified

- Full 6-section audit written to `docs/AUDIT_2026-10-19.md` (secrets/git history, auth/RBAC, backend/DB, frontend, deploy, tests). Research was static and read-only via 4 parallel agents plus direct checks; no application code changed.
- Git history: no secret-like file ever added; secret markers (`BEGIN PRIVATE KEY`, `ghp_`, `AKIA`, `xoxb-`, `Bearer ey`) absent from history; only `.env.example` (CHANGE_ME placeholders) tracked. Tracked files contain no real server addresses (only 127.0.0.1/0.0.0.0/192.0.2.x test IPs).
- `backups/` is missing from `.gitignore` [MEDIUM]. `postgres/schema.sql` lacks the 0008 permission tables [MEDIUM]. `server/deploy.sh` referenced in DECISIONS.md does not exist in the repo [MEDIUM]. Dashboard page swallows API errors [MEDIUM]. Unit tests (48 in 10 files) and 12 E2E scripts remain unexecuted.
- Updated vs earlier notes: `GET /dashboard/summary` is now read-only; the snapshot writer `save_daily_readiness_snapshots` is unrouted dead code, so `daily_readiness_snapshots` has no active writer while `monthly_readiness` reads it.
- Backend liveness through the user's SSH tunnel confirmed: `GET /health` returned `{"status":"ok","service":"toir-backend"}`. No other server calls made. gh CLI unavailable, so latest CI result is UNKNOWN.

### Next task

- Data-generation project (user-requested): generate ~2 years of history (1000 wagons, 100 electric locomotives, 50 diesel locomotives, small + major repairs) via the API for full visual/functional testing. Scale, production-DB confirmation, and admin access method were asked of the user; awaiting answers. API constraints found: `closed_at` is always set to server now() on completion; `MileageUpdate` accepts only a value (no date), so `mileage_history.recorded_at` cannot be backdated via the API; work-order `date_start`/`date_end` accept past dates.

## History data generator for full-scale UI testing (2026-10-20)

### Verified

- Added `backend/scripts/seed_history.py`: API-only generator for two years of marked history (defaults: 1000 wagons, 100 electric locomotives, 50 diesel locomotives; 100 small + 2–3 major repairs per asset, about 118 000 work orders). Rows use `GT-HIST` / `GT-` markers; progress is resumable through a state file in the system temp directory; the access token refreshes automatically; mileage is posted monthly so `mileage_at_creation` varies.
- Added `backend/scripts/sql/fix_history_dates.sql`: backdates `work_orders.created_at/updated_at/closed_at`, rebuilds historical order numbers, and spreads `mileage_history.recorded_at` over two years.
- Static checks: `python -m py_compile backend/scripts/seed_history.py` passed. Offline plan test with 9 synthetic assets produced 923 orders (100 small + 2–3 major each), all four statuses, unique descriptions, positive quantities, completed ends in the past, open ends in the future; shifting "now" by one day reproduced identical descriptions and content (resume determinism).
- NOT TESTED: any real API call, login, creation, status transition, production database write, SQL execution, and browser UI. The generator has not been run.

### Next task

- The user runs the generator on the PC through the SSH tunnel (admin credentials are typed into the terminal, never into chat). From the repo root:
  - [PC] `$env:TOIR_API_BASE_URL="http://localhost:8010"`
  - [PC] `python backend/scripts/seed_history.py`
- Small smoke run first: [PC] `python backend/scripts/seed_history.py --wagons 2 --electric 1 --diesel 1`
- After the run, execute `backend/scripts/sql/fix_history_dates.sql` with the usual server psql/docker access, then perform browser visual/functional testing (dashboard KPIs/graphs, asset pagination, work-order filters, reports/CSV, analytics, master scope). Full scale is about 118 000 orders and roughly 280 000 API calls, so runtime depends on tunnel/server throughput.

## Dynamic organization hierarchy (2026-10-21)

### Verified

- Existing `sections` remains the unit table. Old section IDs are retained as new unit IDs (`old_section_id = new_unit_id`); no FK rewrite or data copy is planned. Section references in users, employees, fixed assets, work orders, maintenance logs, and TMC remain attached; dashboard/reports use those same IDs.
- The separate legacy `departments` table and its `department_id` links were not merged or remapped; no confirmed department-to-unit mapping was available.
- Added recursive tree, localized three-name CRUD, typed parent validation, cycle-safe moves, archived-record handling, and UI search/type/status/archive controls. `DELETE /sections/{id}` now archives and refuses active children.
- Added migration `0008_safe_section_hierarchy.py`, corrected the invalid FK syntax in `0007_section_hierarchy.py`, aligned `postgres/schema.sql`, and added read-only migration preflight SQL.
- Added `0010_merge_section_hierarchy.py` to merge the section and permissions branches. Python AST graph check found one head (`0010_merge_section_hierarchy`) and no missing parent revisions.
- Search-tree behavior was corrected so a matching parent keeps its full descendant tree. Direct legacy-name edits also keep an existing Russian translation synchronized; section GET uses the same master-scope guard as list/tree.
- Added mock/unit and API E2E coverage for translations, recursive tree, cycle/typed-parent rejection, role permissions, archiving, and historical FK preservation.
- This review: Python syntax checks and `git diff --check` passed. Read-only SQL scan found no write/DDL statement. `npx tsc --noEmit` and `npm run build` passed; build showed two existing React Hook warnings in work-orders files.
- Duplicate section-name assumptions were corrected in dashboard selection, reports, TMC filtering, asset depot-to-section mapping, analytics name lookup, and reference seeding. Ambiguous UI labels are distinguished by ID; ambiguous asset depot names are rejected rather than mapped to an arbitrary section.
- Added a regression test requiring HTTP 422 when the legacy analytics name filter matches multiple active sections; test execution remains blocked by missing FastAPI.
- `cd backend && python3 -m unittest discover -s tests -p 'test_sections_hierarchy.py'` was attempted and failed during import because `fastapi` is not installed. Backend E2E, PostgreSQL syntax/preflight/migration, live FK preservation, browser behavior, and server deployment are NOT TESTED. No DB was connected or changed; no server was started.
- Follow-up visibility diagnosis: `git status` shows the hierarchy changes only in this checkout (modified/untracked, not committed); branch reports `main...origin/main`. No shared browser page or server/DB access was available, so the exact running image and live API response remain unknown.
- The local `.next` build contains `http://localhost:8010/api/v1`; source fallback is the same. Production Compose is configured to build with `https://${DOMAIN}/api/v1`, and Caddy forwards `/api/*` to the backend. Thus this checkout's build is not proof of the browser's build; if this local bundle is served to a remote browser, its API points at that browser's own localhost. The actual production build setting was not inspected.
- Static source confirms `/dashboard/directories/sections` calls `GET /sections/tree` and the client expects nested `SectionTreeNode[]`; the backend route and router mount are present. Actual response, DB columns, and permissions were NOT tested against a running backend/database.
- `backend/entrypoint.sh` runs `alembic upgrade head` before starting Uvicorn. Any server image restart can therefore apply pending migrations automatically; do not restart production until the migration has been reviewed and tested on an isolated copy.
- Isolated follow-up (2026-10-21): backend requirements were installed in `/tmp/toir-hierarchy-test-venv`, not globally. All 61 backend unit tests passed after correcting an unawaited async test, two incorrectly synchronous DB mocks, and the next-point regression prediction formula in `backend/app/services/ml.py`.
- A fresh frontend build passed in `/tmp/toir-hierarchy-isolated-build`, separate from the already-listening local port 3000 and its shared `.next`; `npx tsc --noEmit` passed. The build has two existing React Hook warnings in work-orders files. The isolated bundle embeds local API URL `http://localhost:8010/api/v1`; Compose production build uses `https://${DOMAIN}/api/v1`.
- Alembic `upgrade head --sql` rendered offline with one head; `pglast` parsed 320 upgrade SQL statements and 8 rollback SQL statements, plus the hierarchy trigger and both hierarchy `DO` blocks. This is parser validation only, not PostgreSQL execution. No `psql`, `pg_isready`, `postgres`, or `initdb` executable is installed. A 5432 listener exists but its identity/environment is unknown, so no database connection was attempted.
- The 0008-to-0007 rollback SQL adds the legacy unique name constraint (and can fail if duplicate names exist), then drops the hierarchy trigger/function/check constraint. A further downgrade through 0007 removes hierarchy columns. Neither downgrade was executed.
- `backend/tests/test_sections_hierarchy.py` and `test_analytics.py` passed (12 and 3 tests) before the full 61-test run. API E2E scripts were not run because no confirmed isolated API/database exists. No browser page is shared; local listeners on 3000/8010 could not be attributed to this workspace, and were not contacted or restarted. Real three-level CRUD, persisted tree, translations, archive binding, historical database FKs, migration application, and browser behavior remain NOT TESTED.

### Next task

- There is no verified department-to-unit mapping; keep `departments` separate. TMC currently exposes read-only document routes, so no API write path exists to test rejecting a new TMC-to-archived-section link.
- Do not connect to a database or apply a migration as part of this task. If a later task explicitly authorizes an isolated disposable test database, first review its migration state and run `backend/scripts/dry_run_section_hierarchy.sql` read-only.
- Do not use a downgrade command yet. Migration 0008 downgrade can fail if duplicate section names exist; migration 0007 downgrade drops parent/type/code/archive/sort columns and therefore loses hierarchy data. The 0010 merge also joins the permission branch, so a branch-aware rollback plan must first be rehearsed against a disposable DB copy.
- To make the feature visible in a production browser, the user must first review and publish these uncommitted repository changes, validate the full migration chain on an isolated database copy, then deploy the frontend/backend build using the existing domain-based Compose API URL. Confirm the live frontend/API only after the user authorizes that server operation; it was not done here.
- Next: provision a clearly isolated disposable PostgreSQL database, apply migrations there, inspect schema/FKs and run the hierarchy API E2E; then test the released build in a shared browser. Do not treat offline SQL parsing or mocked unit tests as database/API/browser verification.

## Translation list PostgreSQL JSONB typing (2026-10-21)

### Verified

- The reported authenticated `GET /api/v1/translations/section` 500 was traced to SQLAlchemy typing: `jsonb_object_agg(...)` had no explicit result type, so the subquery column did not support `[locale].astext`.
- `backend/app/repositories/localization.py` now declares the aggregate result as PostgreSQL `JSONB`. This fixes the shared localized-name expression used for all seven supported translation entity types.
- `python3 -m py_compile backend/app/repositories/localization.py` passed. PostgreSQL-dialect compilation emitted the JSON `->>` operator for department, section, work_type, work_subtask, nomenclature, asset_type, and asset_status.
- The page's existing write API is `PUT /translations/{entity}/{id}/{locale}` (upsert) and `DELETE` for a locale; both router operations exist. The page does not call POST/PATCH.
- No database query, live authenticated request, browser test, or production/server action was performed.

### Next task

- Verify the list and translation upsert/delete against an authorized isolated PostgreSQL/API environment. Check rendered values and permissions there; do not infer live success from SQL compilation alone.

## Wialon pull sync (2026-10-21)

### Verified

- Added Wialon token login, unit search, logout, safe retry handling, stale-session re-login, and the required `sid` session query parameter. The token remains in the login POST body.
- Added environment configuration, Compose forwarding, admin-only `POST /api/v1/wialon/sync` and `GET /api/v1/wialon/status`, plus one lifespan-managed background loop guarded against overlapping syncs.
- Reused the existing fixed-asset Wialon matching/update and mileage-history path. Existing `wialon_settings.last_sync_at` and `last_sync_status` columns are present in the model and baseline migration; no migration was added. The code does not read or write the legacy `host`/`token` columns.
- `python3 -m py_compile` passed for the changed backend modules and test. Isolated `unittest` run passed all 16 `test_wialon_pull.py` tests, including `httpx.MockTransport`, retry, session expiry, status redaction, mapping, mileage decrease, and periodic retry coverage. `git diff --check` passed.
- No database, migration, real Wialon endpoint, Docker, server, API E2E, or browser was used. Production behavior remains unverified.

### Next task

- Test the implementation against a disposable PostgreSQL database and a Wialon test account/mock API in an explicitly authorized environment. Confirm the live Wialon item flags and mileage counter units before enabling periodic sync in production.

## Wialon stage W1 (2026-10-22)

### Verified

- Added `python -m app.cli wialon-probe`. It performs one login and one `core/search_items` request, logs out, and prints at most 20 units with field names and selected diagnostic values; it does not print the token, session ID, or request URL.
- Corrected unit search flags using the official [unit format](https://sdk.wialon.com/wiki/en/sidebar/remoteapi/apiref/format/unit): general fields `0x1`, last message/position `0x400`, and mileage/engine-hour counters `0x2000`. The documented fields are `cnm` (km or miles) and `cneh` (engine hours); the Wialon Local response has not been observed, so actual values/units remain unconfirmed.
- Added safe status messages for login error codes 4/8, access denied including the reported host-mask reason, expired session, network failure, timeout, and server response errors. Official [error codes](https://sdk.wialon.com/wiki/en/sidebar/remoteapi/apiref/errors/errors) document generic meanings; the specific host-mask reason came from the supplied runtime report, not a live check in this stage.
- `python3 -m py_compile backend/app/cli.py backend/app/integrations/wialon_client.py backend/app/services/wialon.py backend/tests/test_wialon_pull.py` passed. Isolated Wialon unit suite: 25 tests passed. `git diff --check` passed.
- The first test attempt failed because the harness patched a read-only SQLAlchemy engine method; the test now replaces the engine dependency with a mock, and the final suite passed.
- No live Wialon request, database, E2E, Docker, browser, server, or deploy was used. Results apply to code and mock tests only.

### Next task

- Stop after W1 as requested. Wait for explicit approval before starting W2. Before any real probe, use the protected server environment; do not paste or print `.env` or Wialon credentials.

## Wialon delta quality gate (2026-11-02)

### Verified

- Added the async Wialon counter repository, exposed both counter models, and added an Alembic revision for only `wialon_counter_state` and `wialon_rejected_readings`.
- Added pure unit tests for quality-gate and bootstrap-plan decisions. `receive_wialon_update` checks `mileage is not None` before saving mileage, so `mileage=None` does not change `assets.mileage`, including with `allow_zero_mileage=True`.
- Python 3.14 `py_compile` passed for the Wialon modules/scripts and new tests; `git diff --check` passed.
- The requested Python 3.12 tests were not run because Python 3.12 is not installed here. PostgreSQL and Alembic execution were not tested.

### Next task

- Run only `test_wialon_quality.py` and `test_wialon_bootstrap_plan.py` under Python 3.12 with project dependencies available; then validate the migration against a disposable PostgreSQL database.

## Wialon bootstrap container access (2026-11-02)

### Verified

- Added `backend/scripts` to the backend image. Copied scripts/directories use Docker's default readable permissions for `appuser`; no write access to the image's root-owned scripts directory is needed.
- The backend Compose service already maps `WIALON_HOST`, `WIALON_TOKEN`, and `WIALON_SYNC_ENABLED` to their matching Pydantic Settings environment names. Empty host/token values normalize to `None`, and the pull-enabled property remains false unless explicitly enabled and fully configured.
- Bootstrap CSV output now targets `/tmp` and prints that path.
- No terminal commands, Docker, container, `.env`, or secret values were accessed. Runtime/build behavior is NOT TESTED.

### Next task

- On the user's machine, build/run the backend bootstrap dry-run, then copy its printed `/tmp/wialon_bootstrap_*.csv` path from the container with `docker compose cp`.

## Wialon new asset import (2026-11-02)

### Verified

- Added a dry-run-by-default importer. It uses exact existing `wialon_id` checks only; it does not match by name or update existing assets. Unsupported names and `inv_number` conflicts are skipped with reasons.
- Added pure Cyrillic/Latin case-insensitive type and series parsing for the supported locomotive/diesel prefixes. Suspicious absolute mileage is imported as zero and reported for manual correction.
- `--apply` creates each new asset, writes its quality-gate baseline and one `wialon` mileage-history row, then commits once after all planned rows.
- Backend Python 3.12.10 pytest run: 41 Wialon tests passed, including asset import, pull, quality, and bootstrap plan tests. Pytest emitted an existing `pytest-asyncio` loop-scope deprecation warning.
- No import script execution, real Wialon request, or database transaction was performed.

### Next task

- Review the dry-run CSV from an approved backend environment, then explicitly decide whether to run `--apply`. Check suspicious units and duplicate inventory-number skips first.

## Maintenance planning service T5 (2026-11-02)

### Verified

- Added pure kilometer-threshold planning with a configurable `DAILY_KM_ESTIMATE` (default 200). Existing database-backed maintenance settings remain available for their settings endpoint; planning and schedule forecasts use the environment setting.
- Mileage changes from manual asset updates and Wialon pass through a savepoint-protected plan reconciliation. Failures are logged without rolling back mileage/history. Plan upsert uses the existing unique constraint and does not reopen completed/in-progress plans.
- Added paginated maintenance-plan urgency filters (`high` ≤3%, `medium` >3–7%, `low` >7% through `warn_percent`), authenticated reads, and admin/operator plan updates. Schedule query returns this month’s plans plus overdue non-cancelled plans; overdue is based on a past scheduled date unless completed.
- Added idempotent `python -m app.cli seed-intervals` for the requested eight intervals. Work-order completion already updates its linked plan through the existing service path.
- Backend `.venv` Python 3.12.10 pytest: maintenance planning and all Wialon test modules passed (51 tests). The run emitted an existing pytest-asyncio loop-scope deprecation warning.
- No PostgreSQL execution, API E2E, migration, Docker, Wialon, or server check was run. Existing `test_maintenance_security_scope.py` was updated for the schedule query but was not run per the requested test scope.

### Next task

- Run the maintenance security-scope suite and API tests in the approved test environment; then verify interval seeding and mileage-triggered plan persistence against a disposable PostgreSQL database.

## Plan recalculation command (2026-11-02)

### Verified

- Added `python -m app.cli recalculate-plans` for `operational` locomotive and diesel assets.
- Each asset is reconciled inside its own savepoint and committed separately. A failed asset is rolled back and logged, while processing continues. Reconciliation counts only rows inserted by the unique-key upsert, avoiding duplicate plans.
- Backend `.venv` Python 3.12.10 pytest: recalculation and maintenance planning/security-scope tests passed (25 tests).
- PostgreSQL, actual CLI-to-DB execution, Docker, and server behavior were not tested.

### Next task

- Run the command against the approved database after reviewing interval configuration; inspect the printed counts and logs.

## Maintenance dashboard FastAPI migration follow-up (2026-11-02)

### Verified

- The maintenance page already used the centralized FastAPI client and contained no Supabase imports or calls. It now also queries paginated maintenance plans with month/status/asset/urgency filters and exposes status updates only to admin/operator roles.
- Schedule month changes continue to request the schedule endpoint. Loading, error, retry, and empty states are present; key dashboard strings use the existing Uzbek Latin, Uzbek Cyrillic, and Russian locale provider.
- Backend `MaintenancePlanRead`, `MaintenanceScheduleRead`, update schema, and router signatures were inspected as the API contract. `lib/api.ts` uses the shared request layer, which handles auth tokens, refresh, locale header, and API errors.
- Frontend tests matching test/spec file patterns were not found.
- Lint and TypeScript checks could not execute: PowerShell blocked npm scripts; `npm.cmd run lint` found no ESLint executable, and no local TypeScript compiler was available. No dependency was installed into the project.
- Follow-up TS fix: added `MaintenanceScheduleItem.urgency` to the frontend API type after confirming the backend schema defines `MaintenanceUrgency | None`. `asset_id`, `plan_id`, and the other fields used by the page are also present in that backend schema.
- The follow-up TypeScript fix was not run through lint/tsc because terminal execution was prohibited for that task.

### Next task

- Run frontend lint and `tsc --noEmit` when permitted and the repository's frontend dependencies are available; then verify the Gantt, filters, and role-gated status update in the browser.

## Dashboard realtime refresh flicker (2026-11-02)

### Verified

- `postgres/schema.sql` sends a `fixed_assets` realtime notification for each row-level INSERT, UPDATE, or DELETE. `backend/app/services/wialon.py` processes fetched units one by one.
- `app/dashboard/page.tsx` previously refetched the summary and set full-page loading for every received `work_orders` or `fixed_assets` event.
- Dashboard now groups events received within 750 ms into one summary refresh and keeps the loaded page visible during background refreshes. The pending timer is cleared on unmount.
- The user still sees the exact old callback and log string in the browser bundle; a source search finds no such string in current TS/JS source. This indicates the browser is receiving an older frontend build (or a different deployment); the current browser was not available to inspect directly.
- Lint and TypeScript checks were attempted; both could not run because frontend dependencies (`eslint` and `typescript`) are unavailable locally. Browser behavior was not tested.

### Next task

- Ensure the updated frontend source is on the production host, rebuild/recreate only the TOIR `frontend` service, hard-refresh the browser, then verify the old log is gone and an event burst does not flicker. Rerun lint and `tsc --noEmit` when dependencies are available.

## Wialon unit separation and unified asset view (2026-11-02)

### Verified

- Added `wialon_units` ORM model and Alembic `0012_wialon_units` after revision `0011`; the new table has no fixed-asset foreign key. Its model and migration include the same columns and indexes.
- Wialon pull now upserts every fetched unit as one batch and commits that snapshot batch before the existing per-asset gate/update flow. Unit API online status is computed from `last_message_at` using the existing 15-minute window.
- Added authenticated paginated Wialon unit list/detail/suggestions APIs and admin/operator-only asset creation. Creation validates the three existing asset types, writes the unit link, counter baseline, and mileage history in one transaction, and uses mileage zero with a warning for suspect counters.
- Added a full outer join unified fixed-asset view. TOIR asset fields win for linked rows; master queries force their own section and exclude Wialon-only rows. Existing fixed-asset and stats routes remain based on `fixed_assets`.
- `fixed_assets.wialon_id` was already nullable and unique in the ORM; PATCH already accepted null. A changed link now rebaselines the counter state. Wialon writes now resolve only exact `wialon_id`; fuzzy name/number matches remain suggestion-only.
- Backend `.venv` Python 3.12.10 pytest: requested Wialon and maintenance tests passed (72 tests, 17 subtests).
- Added `backend/scripts/e2e_wialon_units.py` for unit list/detail/suggestions, create/link/unlink, unified rows, and master isolation. Pylance found no syntax errors or diagnostics; the API script was not run.
- No PostgreSQL migration, API end-to-end, Wialon service, Docker, browser, or server execution was performed.

### Next task

- Apply Alembic `0012_wialon_units` to a disposable PostgreSQL copy, run a test sync to populate `wialon_units`, then execute `backend/scripts/e2e_wialon_units.py` before production rollout.

## ОС dashboard: unified API and Wialon page (2026-11-02)

### Verified

- `/dashboard/os` now loads its main table from `GET /api/v1/fixed-assets/unified`, with source badges/filter and Wialon counter/connectivity columns. Wialon-only rows have no edit/delete action; admin/operator can open the create-asset flow.
- Fixed-asset create/edit uses the optional `wialon_id` field and can unlink it. Viewing a linked asset loads Wialon detail data.
- Added `/dashboard/os/wialon` for unit filters, detail, rejected readings, suggestions, linking, and Wialon-based asset creation. Its sidebar entry and client route are hidden/redirected for master; writes are limited to admin/operator.
- API types now follow `FixedAssetRead`, `UnifiedAssetRead`, and Wialon schemas. Removed four translation-label/missing-translation properties from the `FixedAsset` response type because they are not in `FixedAssetRead`.
- VS Code Problems showed no errors in the four changed TS/TSX files; source scan found no Supabase calls in either OS page.
- `npx tsc --noEmit` and `npm run build` were NOT TESTED successfully: PowerShell blocked `npx.ps1`, `npx.cmd tsc --noEmit` reported TypeScript is not installed, and `npm.cmd run build` reported `next` is unavailable. No dependencies were installed.

### Next task

- Make the already-declared frontend dependencies available in the local environment, then run `npx tsc --noEmit` and `npm run build`; after that, verify OS/Wialon flows in a browser against a test API.

## GTK separate read-only source (2026-11-04)

### Verified

- Added GTK HTML parsing and an HTTP client that uses the configured login form and a single authenticated report-page fetch. Missing required data blocks raise a parse error.
- Added the separate GTK mirror tables, membership history, guarded sync service, RBAC, paginated APIs, periodic worker, one-shot script, and read-only API E2E script. `fixed_assets` and existing migrations were not changed.
- GTK synthetic parsing/config/upsert/membership/guard tests and existing Wialon tests passed with `backend/.venv` pytest: 62 passed. The test runner reported the existing `pytest-asyncio` loop-scope deprecation warning.
- No live GTK request, server access, database migration, API E2E, Docker, or production run was performed. `.env*` and `gtk_*.json/html` files were not inspected.

### Next task

- Configure GTK values in the intended environment, apply `0013_gtk_source` to a disposable database, run one sync, then run `backend/scripts/e2e_gtk.py` before deployment.

## GTK links to fixed assets (2026-11-04)

### Verified

- Added nullable unique `fixed_assets.gtk_id` in Alembic `0014_fixed_assets_gtk_id`. Fixed-asset create/PATCH accept optional numeric GTK IDs, validate locomotive/carriage type compatibility, and map uniqueness conflicts to 409.
- Added suggestion-only matching, normalization, linked-asset fields, JSON/CSV match reports, transactional manual link/unlink, and single/bulk carriage-asset creation with `dry_run=true` by default. Bulk creation excludes inactive, duplicate, and linked carriages.
- GTK reads remain under `gtk.view`; link and creation writes require `gtk.manage`. Masters remain denied. `/fixed-assets/unified` and stats were not changed.
- `backend/.venv` pytest for GTK matching, links, unified-asset regression, and existing GTK/Wialon tests: 74 passed. The existing pytest-asyncio loop-scope deprecation warning remains.
- Pylance syntax checks found no syntax errors in the new E2E script and modified GTK matcher/repository/tests. The E2E script was not run. No `.env*` or `gtk_*.json/html` files were opened, and no live GTK/server access occurred.

### Next task

- Apply `0014_fixed_assets_gtk_id` to a disposable database, then run `backend/scripts/e2e_gtk_links.py` against the intended test API. Migration, PostgreSQL, API E2E, Docker, deployment, and browser behavior remain NOT TESTED.

## GTK locomotive-to-wagon mileage attribution (2026-11-04)

### Verified

- Added pure attribution for a linked main locomotive’s TOIR mileage increase to linked, active wagons present in the same train in both snapshots. New/detached wagons, inactive wagons, and wagons seen in multiple trains are excluded. Non-positive and over-limit deltas are not attributed.
- Added a separate TOIR mileage checkpoint table so GTK’s imported `gtk_locomotives.checkpoint_mileage` remains unchanged. A newly linked locomotive starts at its current TOIR mileage; link changes reset its checkpoint.
- Added migration `0015_gtk_wagon_mileage`, `gtk` as a mileage-history source, wagon attribution logs, run-count metrics, `GET /gtk/wagon-mileage`, and `GET /fixed-assets/{id}/gtk`.
- Focused GTK mileage, GTK, unified-assets regression, and existing Wialon tests passed with `backend/.venv` pytest: 83 passed. Pylance syntax checks found no syntax errors in changed Python files. The existing pytest-asyncio loop-scope deprecation warning remains.
- Migration/PostgreSQL, API E2E, Docker, server, and live GTK were NOT TESTED. `.env` and GTK raw JSON/HTML files were not opened; Wialon implementation files were not changed.

### Next task

- Apply migrations through `0015_gtk_wagon_mileage` to a disposable database and verify the GTK sync attribution and both read endpoints against test data before deployment.

## GTK frontend page (2026-11-04)

### Verified

- Added `/dashboard/os/gtk` with GTK status/quality indicators and locomotive, carriage, and train tabs. Admin/operator-only controls cover locomotive link confirmation, unlinking, and carriage bulk-create dry-run review and confirmation.
- Added API types and methods for GTK list/detail, matching, links, carriage creation, status, mileage, and fixed-asset GTK detail. `FixedAsset.gtk_id` is optional and `MileageHistory.source` includes `gtk`; no existing type fields were removed.
- Added a GTK information section to the existing fixed-asset view modal. The main fixed-assets table and `/fixed-assets/unified` behavior were not changed. The sidebar hides GTK for master.
- `npx tsc --noEmit` and `npm run build` were NOT TESTED successfully: PowerShell blocked `npx.ps1`; `npx.cmd tsc --noEmit` reported TypeScript is not installed; `npm.cmd run build` reported `next` is unavailable. No dependencies were installed.
- No `.env.local` was opened or changed; no Supabase calls or commits were added.

### Next task

- Make the already-declared frontend dependencies available in the local environment, then rerun `npx tsc --noEmit` and `npm run build`. Browser behavior, GTK API, migrations, and server remain NOT TESTED.

## GTK offline consistency review (2026-11-04)

### Verified

- Migration IDs `0013`–`0016` form a linear chain and are within Alembic’s 32-character limit. The `mileage_history_source_check` name matches the PostgreSQL-generated baseline name, ORM constraint, and `0015` upgrade/downgrade definitions.
- The canonical SQL schema was missing GTK mirror tables and `fixed_assets.gtk_id`; it now matches the GTK ORM table columns. GTK permission seeding in `0013` was already present; conflict-safe inserts now avoid collision with permissions seeded by the existing `0008` mechanism while preserving role overrides.
- GTK source-side locomotive checkpoint fields were only copied/stored/exposed, not used by G3 attribution. Migration `0016_gtk_mirror_cleanup` removes them; the separate TOIR checkpoint model remains.
- Empty GTK credentials with `GTK_SYNC_ENABLED=true` now produce a value-free warning and disable the background task. Sync failures use fixed safe error text; tests cover logs, saved runs, status output, and enabled state.
- GTK API/UI contract and Russian status/skip-reason labels have regression checks. Master-role page data loading is gated until authorization resolves.
- Backend `.venv` pytest for GTK, matching, mileage attribution, unified assets, and Wialon: **90 passed, 17 subtests passed**. Pytest emitted the existing `pytest-asyncio` loop-scope deprecation warning.
- `.env*`, GTK raw JSON/HTML, and secrets were not opened or printed; no commit was made.

### Next task

- Apply Alembic through `0016_gtk_mirror_cleanup` to a disposable PostgreSQL database and verify upgrade/downgrade. Frontend TypeScript/build, browser, API E2E, live GTK, Docker, and server remain NOT TESTED.

## GTK residual issues G6 (2026-11-04)

### Verified

- The OS page's real-time callback previously caused its WebSocket listener to be replaced whenever the callback identity changed; one `fixed_assets` event also launched both stats and unified-list requests. The hook now retains the latest callback without resubscribing, and the OS page coalesces row events into a single refresh within 750 ms. Browser Network-panel behavior was not verified.
- Root and backend `.dockerignore` files now exclude environment files, GTK snapshots/pages/data, CSV/dump files, dependency/build directories, and TypeScript build metadata. The frontend Dockerfile still contains `COPY . .`; its ignore coverage is checked by pytest. Docker was not run and build-context size was not measured.
- `next.config.mjs` does not set `typescript.ignoreBuildErrors` or `eslint.ignoreDuringBuilds`; it was not changed.
- Added tests for forbidden alphabet characters in the specified GTK/frontend/backend/docs files, migration chain `0012`–`0016`, and offline upgrade/downgrade SQL rendering. The offline render test isolates Alembic logging configuration.
- Backend `.venv` pytest for GTK, matching, attribution, unified assets, and all Wialon modules: **94 passed**. Pytest emitted the existing `pytest-asyncio` loop-scope deprecation warning.
- No commit was made. Frontend TypeScript/build, PostgreSQL execution, Docker build/context measurement, browser, API E2E, live GTK, and server were NOT TESTED.

### Next task

- Run frontend `npx tsc --noEmit` and `npm run build`, then check the OS page's Network panel during a real-time update burst. Rehearse Alembic `0012`–`0016` upgrade/downgrade on a disposable PostgreSQL database before deployment.

## Canonical external asset links P1 (2026-11-04)

### Verified

- Before this change, GTK links were stored in `fixed_assets.gtk_id`; Wialon mapping used `fixed_assets.wialon_id` (including Wialon counter lookup). GTK links were handled in `services/gtk.py` and Wialon links in asset/unit services and import/bootstrap scripts.
- Added Alembic `0017_asset_source_links` after head `0016_gtk_mirror_cleanup`. It creates active-link uniqueness constraints, seeds `asset_links.view/manage`, and backfills non-empty legacy GTK/Wialon IDs as `migrated` with `ON CONFLICT DO NOTHING`. Existing columns remain unchanged.
- Added the shared asset-link service and history API. GTK and Wialon link writes now use the shared service and mirror the old columns; Wialon/GTK lookup paths read active canonical links.
- Backend `.venv` pytest for source links, GTK, matching, attribution, unified assets, and Wialon: **102 passed**. `git diff --check` reported no whitespace errors.
- No commit was made.

### Next task

- Rehearse migration `0017` upgrade and downgrade, including backfill and permission grants, on a disposable PostgreSQL database; then run API E2E checks for link, unlink, duplicate, type mismatch, and history behavior.

### NOT TESTED

- PostgreSQL migration execution/rollback, API E2E, full backend suite, concurrency under real PostgreSQL, production server, or deployment.

## Fixed asset passport P2 (2026-11-04)

### Verified

- Read existing `inv_number`, `series`, `depot`, `comm_date`, `year_built`, and `owner` usage across backend and frontend; existing fields remain. Wialon and GTK matching normalization helpers are reused.
- Added Alembic `0018_asset_passport` after `0017_asset_source_links`, passport columns and `asset_models`, backfill/report logic, validation, and the admin/operator passport report endpoint. `sections` is used as the canonical org unit; no automatic `departments` mapping was added.
- Updated fixed-asset, GTK, and Wialon asset-creation paths and TypeScript API types without removing existing type fields. Added passport-report E2E coverage and updated fixed-asset E2E payloads for required model/number data.
- Backend `.venv` pytest for passport, source links, GTK, matching, unified assets, and Wialon: **102 passed**. No commit was made.

### Next task

- Rehearse Alembic `0018` upgrade/downgrade and backfill on a disposable PostgreSQL database, then run fixed-asset/passport API E2E checks against the intended test API.

### NOT TESTED

- PostgreSQL migration execution and real-data backfill, API E2E, frontend TypeScript/build, browser, production server, and deployment.

## Asset source-to-passport policy P3 (2026-11-04)

### Verified

- Added one field-policy table for TOIR, GTK, OneC, and Wialon-owned fields. GTK proposals only load assets through active canonical GTK links; auto-fill, normalized conflict detection, duplicate pending suppression, and manual passport change journaling are implemented.
- Added Alembic `0019_asset_field_changes`, its ORM/repository/schemas, and `asset_conflicts.manage` permission grants for admin/operator only. Added paginated conflict listing and accept/reject endpoints; stale acceptance returns 409.
- Added the GTK sync proposal transaction in an isolated session; proposal failures are logged and do not escape the sync helper. Wialon telemetry behavior was not changed; Wialon-created assets now record their initial passport values.
- Added an E2E script requiring a disposable API with GTK configured. Backend `.venv` pytest for field changes, passport, source links, GTK, matching, attribution, unified assets, and Wialon: **128 passed**. No commit was made.

### Next task

- Rehearse Alembic `0019` upgrade/downgrade on disposable PostgreSQL, then run `e2e_asset_conflicts.py` against a disposable API with GTK connected.

### NOT TESTED

- PostgreSQL migration execution, GTK network sync, API E2E, frontend, production server, and deployment.

## Shared source matching foundation P4 (2026-11-04)

### Verified

- Added source-neutral `SourceObject`, normalization/name extraction, and `high` / `ambiguous` / `none` matching. GTK compatibility helpers and Wialon link suggestions now use the shared matching functions; existing GTK and Wialon tests remain unchanged and pass.
- Added the `SourceAdapter` protocol and GTK adapter. Existing GTK sync still consumes its full snapshot payload and its prior parsing/network behavior remains unchanged.
- Added the paginated `/api/v1/asset-links/unmatched?source=gtk|wialon` endpoint. It reads only mirror rows without an active canonical source link and includes candidate level/suggestion data.
- Added the Uzbek integration onboarding contract in `docs/INTEGRATIONS.md` and an API E2E script for unmatched sources. Backend `.venv` pytest across matching, GTK, P3 passport/conflicts, attribution, unified assets, and Wialon: **134 passed**. No migration or external integration was added; no commit was made.

### Next task

- Run `e2e_asset_unmatched.py` against the intended test API to verify live GTK/Wialon mirror data and the `asset_links.view` role grants.

### NOT TESTED

- API E2E, database-backed unmatched query against PostgreSQL, live GTK/Wialon sources, frontend, production server, or deployment.

## Asset passport, source links, and conflicts UI P5 (2026-11-04)

### Verified

- Added the passport editor to the fixed-asset detail modal for asset type, catalog model, number, serial number, inventory number/provisional marker, accounting number, commissioning date, build year, organizational unit, and decommission date. Organizational-unit changes require confirmation.
- Added source-link history with active/ended records and link/unlink controls for Wialon, GTK, Весовой, and 1С. Added the missing paginated `GET /fixed-assets/models` and generic source-link `POST` / `DELETE` API operations, using the existing asset model repository and asset-link service.
- Added the pending asset-conflicts page with Russian labels, current/proposed values, source/date, confirmed accept/reject actions, and a sidebar entry restricted to admin/operator. Existing `FixedAsset` fields, including operational fields, were retained; new API types were added for models, links, and field changes.
- Added `backend/scripts/e2e_asset_sources.py` to check model-list pagination and source-link create/history/end behavior against a disposable API; it was not run.
- `npx.cmd tsc --noEmit` could not run because the local TypeScript compiler is unavailable. `npm.cmd run build` could not run because the Next.js executable is unavailable. No dependencies were installed.

### Next task

- Restore frontend dependencies through the approved workflow, then rerun the two permitted checks; follow with authorized API/browser verification for passport edits, source-link history, and conflict resolution.

### NOT TESTED

- TypeScript check and production build (required local executables are missing); backend pytest, API/database behavior, authorization, browser interactions, production server, and deployment.

## P6 offline audit continuation (2026-11-04)

### Verified

- Added the admin/operator `POST /fixed-assets/bulk-org-unit` endpoint. It validates the selected section and assets, locks assets in stable ID order, records each changed `org_unit_id` in `asset_field_changes`, and commits the batch atomically. Existing single-asset PATCH already supports `org_unit_id`; the bulk UI is deferred to P7.
- Added API schemas/types, an E2E script, and audit tests for bulk assignment, single PATCH, permissions, migration graph, source mirrors, and provisional inventory numbers. Existing source-link unique-race handling remains a 409.
- The final focused P6 audit test run passed: **18 passed**. The requested asset, GTK, mileage-attribution, unified, and Wialon test set passed: **152 passed**.
- Static revision-graph and model/schema checks pass. No applied migration or `postgres/schema.sql` was changed. `DECISIONS.md` records that revision 0018 uses existing database rows for backfill and cannot be fully rehearsed through offline SQL rendering.
- Frontend build and TypeScript checks were attempted earlier but could not run because the local Next.js and TypeScript executables were unavailable.

### Next task

- Restore frontend dependencies through the approved workflow, run `npm run build` and `npx tsc --noEmit`, then run the asset/org-unit E2E script against a disposable test API and rehearse migrations against a disposable PostgreSQL copy.

### NOT TESTED

- PostgreSQL migration execution/rollback, endpoint E2E, browser behavior, production/deployment, and live database role/link data. Frontend build and TypeScript checks remain NOT TESTED because their executables were unavailable.

## P7 permissions, bulk section assignment, and inventory import (2026-11-04)

### Verified

- In permission checks, `role_permissions.granted` controls non-admin access; `require_permission` also applies explicit `ROLE_DENIED` overrides. Migration 0008 seeds grants from `ROLE_DEFAULTS`; 0017/0019 used `ON CONFLICT DO NOTHING`, so they did not repair a previously wrong grant. Added migration 0020 with an idempotent upsert: admin/operator receive all three asset-link/conflict permissions; management receives only `asset_links.view`; master receives none. The live database values were not queried.
- Added the admin/operator-only bulk section-assignment UI with the “Без участка” server filter, page checkboxes, select-all, confirmation showing the count and section, and list/stat refresh. The unified API now returns `org_unit_id`.
- Added admin/operator inventory-import preview and apply APIs. Preview accepts CSV text or JSON rows and reports empty, missing, ambiguous, duplicate, or valid rows without writing. Apply rechecks IDs and number conflicts under row locks, journals manual changes, clears the provisional flag, and commits once; an integrity failure rolls back and returns 409. Added CSV selection, preview table, and confirmation in the OS page.
- `next.config.mjs` does not set `typescript.ignoreBuildErrors` or `eslint.ignoreDuringBuilds`.
- Backend `.venv` requested test set: **163 passed**. P7-specific tests: **11 passed**. No applied migration 0001–0019 or `postgres/schema.sql` was edited.

### Next task

- Restore frontend dependencies through the approved workflow, rerun build and TypeScript checks, then run the import/org-unit E2E scripts and migration 0020 on a disposable test API/database.

### NOT TESTED

- Frontend build and TypeScript checks (Next.js and TypeScript executables are missing); migration execution, live permission rows, API E2E, browser interactions, production, and deployment.

## P8 OS API and passport save fixes (2026-11-05)

### Verified

- Fixed-asset inventory-import methods were accidentally attached to the `gtk` client, while the OS page called them on `api.fixedAssets`. Moved preview/apply methods to the fixed-asset client and verified their paths match `/fixed-assets/inv-import/preview` and `/apply`; bulk assignment remains on the same client.
- The OS modal PATCH already passes `org_unit_id` from the passport editor. The parent modal's legacy save payload omitted this field, and the parent state refresh omitted the latest passport fields. Added `org_unit_id` to the common asset update payload and synchronize it and other passport values from the API response.
- Backend PATCH accepts `org_unit_id`, validates an active section (422 if unavailable), records manual field changes, commits, then returns the refreshed asset. A missing asset is 404; permission failure is 403; uniqueness/integrity conflict is 409. Database/schema errors not handled as integrity conflicts can return 500. No catches silently suppress the PATCH error; passport, create, update, and delete errors now display Russian messages with the HTTP status when available.
- Create uses the same service validation, manual journal, and commit path; successful create is 201. Delete commits only when no work-order references exist (204); missing asset is 404 and referenced assets conflict (409).
- Removed the Vercel Analytics component from the root layout; package dependencies were left unchanged.
- Requested asset, GTK, Wialon, unified, and attribution suites: **171 passed**. No migrations or database schema were changed.

### Next task

- Install/restore frontend dependencies only through the approved workflow, rerun `npm run build` and `npx tsc --noEmit`, and verify passport save/create/delete in a disposable API/database environment.

### NOT TESTED

- Frontend build and TypeScript (Next.js and TypeScript executables are unavailable); live API/database, migration state, browser behavior, production, and deployment.

## JSON passport register import (2026-11-05)

### Verified

- Removed the import snapshot model/table and rollback API/UI. Added migration `0021_fixed_asset_types` for `tank_car`, `platform`, and `special_self_propelled`; earlier migrations remain unchanged.
- Read all of `assets_list.json`: **1,075 records**. Counts by imported type: wagon 835, locomotive 51, tank car 129, platform 24, diesel 35, special self-propelled 1. Sections: ЖДЦ-1 573 and ЖДЦ-2 502. All rows have the required fields used by preview; `number` is absent from the source; both external IDs are null in every row.
- Ran the complete JSON through the import parser using section names extracted from the same file: **1,075 accepted, 0 blocked**, including 45 duplicate-warning rows (15 repeated inventory groups and 7 repeated model/type/serial groups). Wialon and GTK IDs are null in all source rows. Repeated external IDs remain blocking because canonical source-link indexes require uniqueness.
- With user approval, added migration `0022_asset_number_dupes`: it replaces the real-inventory and active model/number unique indexes with non-unique indexes; accounting inventory-number uniqueness remains. The import uses one transaction, rechecks the preview hash, and sets `number = serial_number`.
- The delete path checks ORM-known direct foreign keys and returns HTTP 409 when other module records refer to old assets; it deletes only `fixed_assets` rows and relies on their declared cascades for asset source links and field-change rows. It no longer deletes `asset_models`.
- Fixed the Russian type mapping typo (`тяговой агрегат`) found by the preview regression test. The Wialon-only asset-type selector is scoped to the create modal.
- The temporary full-file parser probe passed: **1,075 accepted, 0 blocked**. Related asset, GTK, Wialon, unified, and attribution suites: **183 passed**. `npx.cmd tsc --noEmit` exited 0; `npm.cmd run build` exited 0 with three pre-existing React Hook warnings.
- No PostgreSQL test database, migration execution, or register import was run; there are no measured before/after database counts. The JSON file was read but not modified. No commit was made.

### Next task

- Run migration `0022_asset_number_dupes` and the import only on a user-controlled disposable PostgreSQL database; verify 1,075 inserted rows and preserved business-module records before considering any production change.

### NOT TESTED

- Actual PostgreSQL FK rows/blockers and cascades, Alembic execution/downgrade, import transaction and resulting row count in PostgreSQL, API/browser flow, production, and deployment.

## P9 canonical schema and legacy-column retirement (2026-11-06)

### Verified

- Confirmed Compose does not mount `postgres/schema.sql`; the backend entrypoint runs `alembic upgrade head`, and revision 0001 reads its immutable `0001_baseline.sql`. The schema is not applied twice during the normal clean install.
- Added forward-only revisions 0023 and 0024. Revision 0023 reconciles duplicate-permitting asset indexes; 0024 copies legacy values to canonical fields, updates dependent views, then drops `name`, `series`, `depot`, `number`, `number_normalized`, `org_unit_id`, and `comm_date`. Applied revisions 0001–0022 were not edited.
- The fixed-asset API name is computed from its translated type name, `serial_number`, and `inv_number`; `section_id` and `commissioned_at` are canonical, with `org_unit_id` and `comm_date` retained as response aliases. Search/sort and unified assets now use model/section relations rather than removed columns.
- Updated `postgres/schema.sql` with the final fixed-asset columns, supplementary permission/Wialon tables, indexes, and analytics views. Catalog and permission seed rows remain in migrations only.
- Schema drift checks validate ORM-vs-schema columns/indexes, legacy-column absence, view/seed definitions, locale characters, Alembic single head and revision lengths, and offline SQL for 0023–0024. Requested asset, GTK, Wialon, unified, attribution, and drift tests: **187 passed, 17 subtests passed** using backend `.venv`.

### Next task

- On a disposable PostgreSQL copy, apply revisions 0023–0024, verify the migration history and row mappings, then compare `pg_dump --schema-only` with the supplied `schema_actual.sql`. Do not run these operations on production from this workspace.

### NOT TESTED

- PostgreSQL execution of either new migration, actual view replacement, database row preservation, live schema dump comparison, API E2E, frontend typecheck/build, browser, server, or deployment.

## Russian-only interface (2026-11-09)

### Verified

- Frontend React source no longer contains `t()` call sites, locale-switcher references, or Uzbek locale tags; the i18n helper retains only Russian.
- The translations admin page and old locale helper were removed. Reference forms and API types now use Russian names.
- Backend locale selection now resolves to Russian. The new forward migration `0025_russian_only` deletes non-Russian translation rows and restricts translation tables to `ru`.
- `postgres/schema.sql` and related frontend/backend code were updated. The `0025` migration has not been run against a database.
- `npx.cmd tsc --noEmit`, frontend build, lint, Python syntax checks for 17 changed files, and `git diff --check` exited successfully. Lint/build reported three React Hook warnings.
- `docker-compose.yml` was already modified before this task and was not changed as part of this work.

### Next task

- Validate migration `0025` and localization E2E on an authorized disposable database before any production migration. Backend tests, browser behavior, and database migration remain NOT TESTED.

## Fixed-assets directory navigation (2026-11-09)

### Verified

- The fixed-assets register page moved from `/dashboard/os` to `/dashboard/directories/assets`; its loading state moved with it.
- The directory index now has an access-controlled "Основные средства" card with description "Справочник основных средств".
- The standalone fixed-assets sidebar item was removed. Dashboard and OS-related links/redirects now use the new path.
- Frontend production build, `npx.cmd tsc --noEmit`, focused ESLint, and `git diff --check` exited successfully. Build reported three existing React Hook warnings.

### Next task

- Verify navigation and permission visibility in a browser. Browser behavior remains NOT TESTED.

## ОС catalogs in directories (2026-11-09)

### Verified

- The ОС type/status catalog page moved from `/dashboard/admin/asset-catalogs` to `/dashboard/directories/asset-catalogs`.
- The standalone sidebar link was removed. The `Справочники` index shows `Справочники ОС` only to users with `asset_catalogs.manage_reference_data`.
- Frontend build, `npx.cmd tsc --noEmit`, focused ESLint, old-route source search, and `git diff --check` completed successfully. Build showed three existing React Hook warnings.

### Next task

- Verify the new route and permission-gated card in a browser. Browser behavior remains NOT TESTED.

## Fixed-assets filters and section tree (2026-11-09)

### Verified

- Fixed-assets filters now use icon capsules with counts for the requested vehicle types and statuses, plus a total-count header.
- Sections are loaded dynamically from `/sections/tree` and displayed as nested clickable buttons with hierarchy indentation, unit-type labels, counts, selection highlighting, and hover transitions.
- Frontend production build, TypeScript, focused ESLint, and `git diff --check` succeeded. Build reported two existing React Hook warnings in work-orders.
- NOT TESTED: API data behavior, browser layout/interaction, and live spare-parts status availability.

### Next task

- Verify the capsule filters and clickable hierarchy with an authorized API/browser. Confirm the configured waiting-for-parts status code if its count remains zero.

## Permissions under users (2026-11-09)

### Verified

- The role-permissions page moved from `/dashboard/admin/permissions` to `/dashboard/admin/users/permissions`.
- The standalone sidebar link was removed. The users page now links to "Права доступа"; the permissions page links back to users.
- Frontend build, TypeScript, focused ESLint, old-route source search, and `git diff --check` completed successfully. Build showed three existing React Hook warnings.

### Next task

- Verify the new route and admin-only access in a browser. Browser behavior remains NOT TESTED.

## Data conflicts under directories (2026-11-09)

### Verified

- The data-conflicts page moved from `/dashboard/os/conflicts` to `/dashboard/directories/conflicts`.
- Its standalone sidebar item was removed. The `Справочники` index shows `Конфликты данных` to users with `asset_conflicts.manage`.
- The existing admin/operator page check remains in place; loading state now waits for auth resolution in its callback dependencies.
- Frontend build, TypeScript, focused ESLint, old-route source search, and `git diff --check` completed successfully. Build showed two existing React Hook warnings in work-orders.

### Next task

- Verify the new route and permission-gated card in a browser. Browser behavior remains NOT TESTED.

## Header profile duplicate removed (2026-11-09)

### Verified

- Removed the user role badge and initial avatar from the top-right dashboard header; the theme switcher remains.
- The sidebar user profile block remains unchanged.
- Focused ESLint, production build, TypeScript, and `git diff --check` succeeded. Build reported two existing React Hook warnings in work-orders.
- NOT TESTED: browser appearance and responsive layout.

### Next task

- Verify the header and sidebar layout in a browser at desktop and mobile widths.

## Fixed-asset source picker (2026-11-09)

### Verified

- Added searchable, paginated Wialon and GTK object selection in the fixed-asset source section; GTK supports locomotives and carriages.
- Selection saves through the fixed-asset source-link API; Весовой and 1С show a disabled “Скоро” control.
- `npx.cmd tsc --noEmit`, `npm.cmd run build`, and `git diff --check` exited successfully. Build reported two existing React Hook warnings in work-orders.
- NOT TESTED: browser behavior, live Wialon/GTK responses, and source-link API behavior.

### Next task

- Verify search, paging, link/unlink, and placeholder states in a browser with an authorized API account.

## Wagon mileage P0.3 implementation (2026-11-10)

### Verified

- Added revision `0028_wagon_mileage_approval_and_inputs` after `0027`; source history reports one Alembic head. No database migration was run.
- Added opening-balance submit/list/admin-approval, GTK membership evidence, Wialon raw-input ingestion, and pure wagon-mileage calculation rules. Uncertain Wialon mileage remains `HELD`; no ledger publisher or projection writer was connected.
- Prevented legacy fixed-asset mileage writes and removed locomotive mileage from maintenance/work-order/ML calculations. Wagon mileage is read only from an active, calculation-eligible `CONFIRMED` ledger projection.
- Frontend production build and `npx.cmd tsc --noEmit` exited successfully; build reported two React Hook warnings in work-orders. Python syntax check and `git diff --check` exited successfully.
- A selected backend test run earlier in this work reported 117 passed and 4 subtests passed; it was not rerun after final response/UI/E2E refinements.

### Next task

- Resolve `UNKNOWN/PENDING` policies in `WAGON_MILEAGE_P0_DECISIONS.md` (Wialon timestamp/identity, GTK handoff and allocation, idle behavior, source priority, estimated projection, and maker-checker). Then implement the idempotent ledger publisher, confirmed projection/read path, and sync orchestration against those approved rules.
- Still required: PostgreSQL integration and migration rehearsal, E2E scripts, browser checks, and any production rollout. None was run in this task.

## GTK exact-inventory link proposals (2026-11-11)

### Verified

- GTK locomotive and carriage suggestions now use the same rule: raw, non-empty inventory strings must be exactly equal. Model, registration, name, and partial matches do not create proposals. Duplicate TOIR inventory candidates are marked ambiguous without selecting an asset.
- Existing GTK links and assets already linked to GTK are not proposed again. Confirming a proposal sends `expected_inventory_number`; the API locks and reloads the GTK row and fixed asset, checks the exact number and unique candidate count again, and returns 409 for stale/ambiguous proposals or a conflicting existing link. Repeating the same confirmation uses the existing idempotent source-link service.
- The carriage table now shows its proposal, ambiguity state, and the same explicit confirmation dialog as locomotives. No route or migration was added.
- `npx.cmd tsc --noEmit`, `npm.cmd run lint`, `npm.cmd run build`, backend `compileall`, and `git diff --check` completed successfully. Lint/build reported two existing React Hook warnings in work-orders.
- Added offline unit coverage and extended `backend/scripts/e2e_gtk_links.py` for exact proposal shapes and stale confirmation rejection; backend pytest and API E2E were not run under the local-only syntax-check rule.

### Next task

- Run `python scripts/e2e_gtk_links.py` only against a disposable test API/database, then verify the locomotive and carriage proposal/confirm flows in an authorized browser.

### NOT TESTED

- Backend pytest, API E2E, PostgreSQL transaction/race behavior, browser interaction, production, and deployment.
