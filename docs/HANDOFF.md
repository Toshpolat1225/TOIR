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
  tekshirilmagan. TMC create/update/delete route'lari hanuz yo'q.
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
3. TMC create/update/delete route'larini amalga oshirish; GET list route'ini API muhitida
   tasdiqlash.
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
