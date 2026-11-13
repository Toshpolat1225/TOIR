# TOIR — loyiha tavsifi (to'liq, zip bo'yicha tekshirilgan)

> Bu fayl `TOIR-main.zip` ichidagi haqiqiy kodni o'qib tuzildi (backend ~25 800 qator Python, frontend ~16 900 qator TS/TSX, 29 ta migratsiya, 60 ta jadval).
> Oldingi qoralama (migratsiya 0009 gacha, "TMC backend yo'q", "Supabase izlari bor" deb yozilgan) **eskirgan**. Shu fayl uning o'rnini bosadi.

## Holat belgilari

| Belgi | Ma'no |
|---|---|
| ✅ | Kodda ko'rildi (zipdagi fayllar o'qildi). Ishlashi degani emas. |
| 🟢 | Serverda sinalgani foydalanuvchi/oldingi hujjat tomonidan xabar qilingan. Men tasdiqlay olmayman. |
| 🟡 | Kod va testlar yozilgan, lekin serverda/brauzerda sinalmagan. |
| ❓ | Zipdan aniqlab bo'lmaydi. Foydalanuvchi serverda tekshirishi kerak. |

**Men nimani qilmadim:** testlarni, build'ni, migratsiyani ishga tushirmadim (muhitda tarmoq va Python bog'liqliklari yo'q). `.git` papkasi zipda yo'q, shuning uchun commit tarixi va git tarixidagi maxfiy qiymatlar tekshirilmadi. Server, baza va brauzer tekshirilmadi.

---

## 1. Maqsad

TOIR — lokomotiv (elektrovoz), teplovoz va vagonlar uchun texnik xizmat (ТО), ta'mirlash (ТР), ehtiyot qismlar (ТМЦ), asosiy vositalar (ОС), hisobot va tahlilni yuritadigan veb-tizim. Interfeys faqat rus tilida, valyuta — so'm (UZS).

Asosiy g'oya: barcha ma'lumot bitta PostgreSQL bazada, backend orqali boshqariladi. Tashqi tizimlar (Wialon, GTK) faqat ma'lumot beradi, TOIR'ning asosiy jadvallarini o'zi o'zgartirmaydi.

**Foydalanuvchi rollari:** `admin`, `operator`, `master`, `management`. Master faqat o'z uchastkasini ko'radi (serverda SQL darajasida cheklanadi).

**Tashqi manbalar:**
- **Wialon** — GPS/telemetriya, birliklar va odometr (probeg). Pull (tizim o'zi so'raydi) va push (`/wialon/input`) usullari.
- **GTK** — temir yo'l poyezdlari/vagonlar ma'lumoti (HTML sahifadan o'qiladi, faqat o'qish).
- **Весовой, 1С** — bog'lash joyi tayyorlangan, hali ulanmagan ("Скоро").

## 2. Arxitektura

| Qatlam | Texnologiya |
|---|---|
| Frontend | Next.js 15.5.28 (App Router), React 19, TypeScript, Tailwind 4, Radix UI, Recharts |
| Backend | Python 3.12, FastAPI 0.115, SQLAlchemy 2 (async) + asyncpg, Alembic, pydantic 2 |
| Baza | PostgreSQL 16 |
| Auth | JWT access token (30 daqiqa, xotirada) + refresh token (7 kun, httpOnly cookie, bazada faqat xeshi), bcrypt |
| Realtime | PostgreSQL LISTEN/NOTIFY, so'ng autentifikatsiyalangan WebSocket `/ws` |
| Deploy | Docker Compose: postgres, backend, frontend, proxy (Caddy) |
| CI | GitHub Actions: backend testlar, frontend tsc/lint/build, Docker build |

**Backend qatlamlari:** `routers → services → repositories → schemas` (`backend/app/`). Ro'yxat javobi `{items,total,limit,offset}`, xato `{"detail": ...}`, o'chirish 204, `sort_by` faqat whitelist'dan.

**Frontend:** backendga faqat `api.<resurs>.<metod>()` orqali (`lib/api.ts`). Brauzer kodida to'g'ridan-to'g'ri baza klienti yo'q. Supabase kod ichida **yo'q** ✅ (faqat `docs/HANDOFF.md` va `AI_WORKLOG.md` matnida eslatilgan).

**Fon vazifalari (backend `lifespan`)** ✅: bazadan voqealarni tinglash va tarqatish, audit jurnalini 365 kundan keyin tozalash, ixtiyoriy Wialon sinxronlash (`WIALON_SYNC_ENABLED`), ixtiyoriy GTK sinxronlash (`GTK_SYNC_ENABLED`). Ikkalasi ham sukut bo'yicha **o'chiq**.

## 3. Papkalar

```text
app/                      Next.js sahifalari (20 ta sahifa)
components/, hooks/, lib/ Umumiy UI, hook'lar, api.ts, auth-context, realtime
backend/app/              core, models, repositories, routers, schemas, services, integrations, cli.py, realtime.py, main.py
backend/alembic/versions/ 29 ta migratsiya (0001–0029)
backend/scripts/          20 ta e2e_*.py, seed_demo.py, seed_history.py, wialon_*.py, gtk_sync_once.py
backend/tests/            38 ta test fayl (~317 ta test funksiya)
backend/prod/             Wialon uchun qo'lda bajariladigan SQL (audit, tekshiruv, rollback)
postgres/schema.sql       Yakuniy sxema namunasi (reference). Compose uni YUKLAMAYDI
docs/                     HANDOFF, DECISIONS, AI_WORKLOG, AUDIT, DEPLOY, INTEGRATIONS, PROD_RUNBOOK, Wialon/vagon probegi hujjatlari
scripts/                  Excel/nomenklatura import, anomaliya, backup_postgres.sh
```

## 4. Joylashuv va muhit (oldingi qoralamadan; zipdan tasdiqlab bo'lmaydi ❓)

- GitHub: `github.com/Toshpolat1225/TOIR` (private). PC'dagi klon bilan ishlanadi, serverga `git pull` bilan tushadi.
- Server: SSH alias `ris`, Ubuntu, Docker + Compose. Papka `/srv/apps/toir/TOIR`. Serverdan GitHub'ga faqat o'qish uchun deploy key.
- Backend serverda `127.0.0.1:8010` da, frontend PC'da ishlab chiqiladi (SSH tunnel orqali).
- **Serverda boshqa ishlab turgan loyiha — `fuel`** (`upjt_*`, `sttb_*` konteynerlar). Band portlar: 80, 443, 3000, 8000, 5432, 9090, 3100. TOIR ularga tegmasligi shart.
- Lokal PC'da Docker yo'q. Backend testlari (`e2e_*`) serverda foydalanuvchi tomonidan ishga tushiriladi.

> ⚠️ **Nomuvofiqlik:** repodagi `docker-compose.yml` postgres'ni `127.0.0.1:5432` ga va Caddy'ni `80:80` ga ochadi. Bu fuel'ning 80 va 5432 portlari bilan to'qnashishi mumkin. Serverda `docker-compose.override.yml` (u `.gitignore`da) yoki boshqa sozlama ishlatilayotgan bo'lishi mumkin. Birinchi sessiyada serverdagi haqiqiy compose'ni (`docker compose -p toir config`) o'qib solishtiring ❓.

## 5. Ma'lumotlar bazasi

- **Yagona yo'l: Alembic.** `backend/entrypoint.sh` har ishga tushganda `alembic upgrade head` bajaradi. Shuning uchun serverda backend konteynerini qayta ishga tushirish kutilayotgan migratsiyalarni **avtomatik** qo'llaydi. Avval zaxira oling.
- **Head: `0029_wagon_mileage_ledger`** ✅ (chiziqli zanjir 0001→0029, 0007/0008 shoxlari `0010_merge_section_hierarchy` da birlashtirilgan).
- `postgres/schema.sql` — yakuniy sxema namunasi (60 jadval, 8 view). Yangi o'rnatishda qo'lda yuklanmaydi.
- Serverda qo'llangan migratsiya qaysi ekani ❓: `docker compose -p toir run --rm --no-deps --entrypoint alembic backend current`.

**Jadvallar (guruhlar bo'yicha):**

| Guruh | Jadvallar |
|---|---|
| Tashkilot | `departments`, `sections` (daraxt, arxivlanadi), `employees`, `*_translations` (faqat `ru`) |
| Foydalanuvchi va xavfsizlik | `users`, `refresh_tokens`, `login_attempts`, `permissions`, `role_permissions`, `permission_audit`, `audit_logs` |
| Asosiy vositalar | `fixed_assets`, `fixed_asset_types`, `fixed_asset_statuses`, `asset_models`, `asset_source_links`, `asset_field_changes`, `mileage_history` |
| Ish buyurtmalari | `work_orders`, `work_order_repairs`, `work_order_items`, `work_types`, `work_subtasks`, `work_type_templates` |
| ТО rejasi | `maintenance_intervals`, `maintenance_plan`, `maintenance_settings`, `maintenance_log` |
| ТМЦ | `nomenclature`, `nomenclature_norms`, `tmc_documents`, `tmc_document_items` |
| Wialon | `wialon_settings`, `wialon_units`, `wialon_counter_state`, `wialon_rejected_readings`, `wialon_raw_receipts`, `wialon_odometer_readings` |
| GTK (faqat o'qish ko'zgusi) | `gtk_locomotives`, `gtk_carriages`, `gtk_trains`, `gtk_train_members`, `gtk_membership_observations`, `gtk_raw_snapshots`, `gtk_sync_runs`, `gtk_wagon_mileage_log`, `gtk_locomotive_mileage_checkpoints` |
| Vagon probegi mexanizmi | `wagon_mileage_opening_balances`, `mileage_calculation_runs`, `mileage_calculation_inputs`, `wagon_mileage_ledger`, `wagon_idle_periods` |
| Tahlil | `ai_insights`, `daily_readiness_snapshots`; view'lar: `executive_summary`, `section_efficiency`, `work_type_efficiency`, `monthly_efficiency`, `ai_insights_summary`, `fleet_health`, `maintenance_schedule`, `work_order_tmc_details` |

## 6. Rollar va ruxsatlar ✅

- 4 rol: `admin` (o'zgarmas, hamma ruxsat), `operator`, `master`, `management`.
- Ruxsatlar bazada (`role_permissions.granted`), har so'rovda tekshiriladi, admin tahrirlaydi (`/permissions/{role}`). Katalog `backend/app/core/permissions.py` (~40 ta kod: `assets.view`, `work_orders.update`, `gtk.manage`, `users.set_active` va h.k.).
- **Master doirasi** serverda SQL so'rovda majburlanadi; begona uchastka yozuvi **404** qaytaradi va status/konflikt tekshiruvidan **oldin** ishlaydi. `master` GTK, asset-links va konfliktlarni ko'ra olmaydi (`ROLE_DENIED`).
- Yangi admin API orqali yaratilmaydi (faqat `python -m app.cli create-admin`). Admin rolini pasaytirish bloklangan, oxirgi faol adminni o'chirish/bloklash bloklangan.
- Login limiti: 15 daqiqada 5 ta xato → 429, `login_attempts` jadvalida (HMAC kalit bilan).

## 7. Modullar holati

| Modul | Backend | Frontend | Test | Eslatma |
|---|---|---|---|---|
| Auth (login/refresh/logout/me) | ✅ | ✅ | 🟢 e2e_smoke xabar qilingan | |
| Foydalanuvchilar, faol/nofaol, ruxsatlar | ✅ | ✅ | 🟡 | `0008`, `0009` kerak |
| Audit jurnali (admin) | ✅ `0026` | ✅ | 🟡 | 365 kun saqlanadi, CSV eksport |
| Spravochniklar (bo'lim/uchastka daraxti, xodim, ish turi, interval) | ✅ | ✅ | 🟢 `e2e_refs` 56/56 (eski xabar) | Uchastka = `sections`, `departments` alohida qoldi |
| Asosiy vositalar (ОС), pasport, katalog | ✅ | ✅ | 🟡 | 1075 yozuvli JSON import mavjud |
| Manba bog'lari va konfliktlar | ✅ | ✅ | 🟡 | `asset_source_links` — kanonik jadval |
| Wialon (pull/push, birliklar, sifat filtri) | ✅ | ✅ | 🟡 | Jonli Wialon bilan sinalmagan |
| GTK (ko'zgu, bog'lash, vagon yaratish) | ✅ | ✅ | 🟡 | Jonli GTK bilan sinalmagan |
| Vagon probegi mexanizmi (P0.3) | ✅ | ✅ ОС kartasida opening balance va yig'ma ko'rinadi | 🟡 | `WAGON_MILEAGE_ENGINE_ENABLED=false` (sukut). PENDING qarorlar bor, 11-bo'lim |
| Ish buyurtmalari (work-orders) | ✅ | ✅ (komponentlarga bo'lingan) | 🟢 e2e eski xabar | Status: pending→in_progress→completed/cancelled |
| ТО reja/jadval | ✅ master doirasi qo'shilgan | ✅ | 🟡 | `recalculate-plans` CLI bor |
| Nomenklatura va normalar | ✅ | ✅ | 🟢 35/37 (eski xabar) | Norma >20% oshsa ogohlantirish, bloklamaydi |
| ТМЦ hujjatlari | ✅ faqat `GET /tmc-documents` | ✅ ko'rish/chop | 🟡 | Yaratish/tahrirlash **yo'q**, hozircha talab qilinmagan |
| Dashboard | ✅ read-only | ✅ | 🟡 | Bekor qilinganlar ochiq hisoblanmaydi ✅ |
| Analytics, hisobotlar (CSV) | ✅ | ✅ | 🟡 | `/reports/{work-orders\|fixed-assets\|tmc-documents}` |
| ML (RUL, anomaliya, health score) | ✅ | Analytics sahifasida `ai_insights_summary` view orqali; `/ml/*` endpointlari frontendda to'g'ridan-to'g'ri chaqirilmaydi | 🟡 | `/ml/analyze`, `/ml/insights` |
| Tarjima (i18n) | Rus tiliga qisqartirilgan `0025` | — | 🟡 | `/translations` router qoldiq sifatida turibdi |

## 8. Backend API (qisqa xarita, `/api/v1` ostida) ✅

- **Auth/foydalanuvchi:** `/auth/login|refresh|logout|me`, `/users` (+`/{id}`, `/reset-password`), `/permissions/me|{role}`, `/audit-logs` (+`/filters`, `/export.csv`, `/{id}`).
- **Spravochniklar:** `/departments`, `/sections` (+`/tree`), `/employees`, `/work-types` (+`/subtasks`), `/work-type-templates`, `/maintenance-intervals`, `/nomenclature`, `/nomenclature-norms`.
- **ОС:** `/fixed-assets` (+`/stats`, `/unified`, `/models`, `/passport-report`, `/bulk-org-unit`, `/inv-import/preview|apply`, `/passport-import/preview|apply`, `/{id}/mileage`, `/{id}/mileage-history`, `/{id}/links`, `/{id}/gtk`), `/fixed-asset-catalogs/{kind}`, `/asset-conflicts`, `/asset-links/unmatched`.
- **Probeg:** `/wagon-mileage/openings` (+`/{id}/approve`), `/wagon-mileage/assets/{id}`.
- **Wialon:** `/wialon/input` (token bilan), `/wialon/units`, `/wialon/sync`, `/wialon/status`.
- **GTK:** `/gtk/status|sync|locomotives|carriages|trains|match-report|links|wagon-mileage`.
- **Ish va reja:** `/work-orders` (+`/norm-check`, `/template-items`), `/maintenance-schedule`, `/maintenance-plan`, `/maintenance-settings`.
- **Tahlil:** `/dashboard/summary`, `/analytics/{block}`, `/reports/{name}`, `/ml/*`, `/tmc-documents`.
- **Boshqa:** `/health` (bazani tekshirmaydi), WebSocket `/ws`.

## 9. Frontend sahifalari (rus UI)

`/auth/login`, `/dashboard`, `/dashboard/analytics`, `/dashboard/maintenance`, `/dashboard/work-orders`, `/dashboard/tmc`, `/dashboard/reports`, `/dashboard/os/gtk`, `/dashboard/os/wialon`, `/dashboard/directories` (+`assets`, `asset-catalogs`, `conflicts`, `sections`, `employees`, `work-types`, `maintenance-intervals`), `/dashboard/admin/users` (+`permissions`), `/dashboard/admin/audit-logs`.

## 10. Sozlamalar (env) — qiymatlarni hech qachon chatga yozmang

Majburiy: `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `JWT_SECRET` (≥32 bayt), `CORS_ORIGINS` (aniq origin, `*` yo'q), `DOMAIN`.
Ixtiyoriy: `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`, `API_DOCS_ENABLED`, `NEXT_PUBLIC_API_URL`, `DATABASE_URL` (skriptlar uchun).
Wialon: `WIALON_INGEST_TOKEN`, `WIALON_HOST`, `WIALON_TOKEN`, `WIALON_SYNC_ENABLED`, `WIALON_SYNC_INTERVAL_MINUTES`.
GTK: `GTK_HOST`, `GTK_USER`, `GTK_PASSWORD`, `GTK_PAGE_PATH`, `GTK_PAGE_QUERY`, `GTK_SYNC_ENABLED`, `GTK_SYNC_INTERVAL_MINUTES`.
Hisob: `DAILY_KM_ESTIMATE` (200), `WAGON_MILEAGE_MAX_BRACKET_GAP_MIN` (30), `WAGON_MILEAGE_IDLE_MIN_MINUTES` (30), `WAGON_MILEAGE_ENGINE_ENABLED` (false).

CLI (`python -m app.cli ...`): `create-admin`, `seed-reference`, `seed-intervals`, `recalculate-plans`, `wialon-probe`, `wagon-mileage-run`.

## 11. Qabul qilingan arxitektura qarorlari

To'liq ro'yxat: `docs/DECISIONS.md` (34 ta). Eng muhimlari:
- FastAPI + PostgreSQL + Docker Compose — yagona backend. Eski ma'lumot ko'chirilmaydi.
- ТО intervallari — spravochnik (`maintenance_intervals`), kodda qattiq qiymat yo'q.
- `sections` — kanonik tashkiliy birlik (daraxt); `departments` alohida qoldi, ularni avtomatik moslashtirmang.
- Wialon va GTK — alohida manba. Ular avtomatik `fixed_assets`ni o'zgartirmaydi. Bog'lash faqat operator tasdig'i bilan (`asset_source_links`). Nom/seriya bo'yicha moslik faqat taklif.
- Arxiv qilinadi, o'chirilmaydi (uchastkalar, katalog qiymatlari).
- Yangi migratsiya faqat oldinga ketadi. Qo'llangan migratsiyani tahrirlamang (0013 bir marta tahrirlangan, bu hisobga olingan).
- Rus tilidan boshqa til yo'q (`0025`). `DECISIONS.md` #11 (3 tillilik) eskirgan, #33 amal qiladi.
- Vagon probegi: aniq bo'lmagan qiymat `HELD` bo'ladi, hisobga kirmaydi.

**Vagon probegi bo'yicha ochiq (`PENDING`) biznes qarorlari** (`docs/WAGON_MILEAGE_P0_DECISIONS.md`): bitta kishi opening balance'ni kiritib o'zi tasdiqlay oladimi; idle'ning minimal davomiyligi; GTK/Wialon vaqt belgilarining aniq ma'nosi; manbalar ustuvorligi; snapshotlar orasida taqsimlash formulasi. Bularni o'zboshimchalik bilan belgilamang.

## 12. Ma'lum muammolar va xavflar (kodni o'qib, 2026-11-13)

**Oldingi qoralamadagi muammolarning hozirgi holati:**

| Oldingi muammo | Hozir |
|---|---|
| ТО reja master uchun uchastka bo'yicha cheklanmagan | ✅ Kodda tuzatilgan (`_master_section_scope`). 🟡 Testlari mock; haqiqiy API/DB'da sinalmagan |
| Admin rolini pasaytirish bloklanmagan | ✅ Kodda bloklangan (`services/users.py`). 🟡 sinalmagan |
| Dashboard bekor qilinganlarni ochiq hisoblaydi | ✅ `status <> 'cancelled'` qo'shilgan. 🟡 sinalmagan |
| ТМЦ backend yo'q | Qisman: faqat `GET`. Yaratish/tahrirlash yo'q (qaror: hozircha kerak emas) |
| Supabase kalit/URL kodda | ✅ Kodda **yo'q**. Git tarixi tekshirilmadi (`.git` zipda yo'q) ❓ |

**Hozir ochiq:**
1. 🔴 **Hech bir yangi modul serverda/brauzerda sinalmagan.** Hujjatlarda "NOT TESTED" ko'p. Eng katta xavf: sinalmagan 0006–0029 migratsiyalar productionga tushishi.
2. 🔴 **Migratsiya avtomatik qo'llanadi** (`entrypoint.sh`). Konteynerni qayta ishga tushirishdan oldin bazadan zaxira oling.
3. 🟠 **CI va testlar mos emas:** 12 ta test fayl `pytest` ishlatadi, lekin `requirements.txt` da `pytest`/`pytest-asyncio` yo'q va CI `unittest discover` ishlatadi. CI'dagi haqiqiy natija ❓ (GitHub Actions ko'rilmadi).
4. 🟠 **`docker-compose.yml` va server sozlamasi farqi** (4-bo'lim) — fuel portlari bilan to'qnashuv xavfi ❓.
5. 🟠 **`Caddyfile` faqat HTTP** (`http://{$DOMAIN}`), `docker-compose.yml` frontendga `http://` beradi, README esa HTTPS/Let's Encrypt deydi. TLS qarori qabul qilinmagan; parol HTTP orqali ketmasligi kerak.
6. 🟠 **`server/deploy.sh` repoda yo'q** (DECISIONS #7 unga tayanadi). Fuel'ni himoya qilish tekshirib bo'lmaydi ❓.
7. 🟡 `docker-compose.local.yml` eskirgan: mavjud bo'lmagan `./frontend` papkasiga ishora qiladi va dev parolni ochiq yozgan. Ishlatmang yoki o'chiring.
8. 🟡 `.gitignore`da `backups/` yo'q (backup skripti shu papkaga yozadi). `Caddyfile.backup-*`, `docker-compose.backup-*.yml`, `toir-local-root.crt`, `assets_list.json` (380 KB), bo'sh `assets.csv` repoda turibdi.
9. 🟡 `postgres/schema.sql` ga 0029 jadvallari kirgan, lekin sxema barcha migratsiyalar bilan 1:1 mosligi to'liq tekshirilmagan (`test_schema_drift` bor, ishga tushirilmagan).
10. 🟡 Dependency: `next 15.5.28` (PostCSS advisory), `xlsx ^0.18.5` (tuzatma yo'q) — oldingi `npm audit` bo'yicha. Qayta tekshirilmagan. `@vercel/analytics` paketda qolgan (layout'dan olib tashlangan).
11. 🟡 Dashboard har safar katta hajmdagi aktiv/buyurtmani LIMIT'siz yuklaydi (eski audit), ILIKE qidiruvlarga indeks yo'q.
12. 🟡 `daily_readiness_snapshots` ni yozadigan faol kod yo'q (`save_daily_readiness_snapshots` hech qayerga ulanmagan), `monthly_readiness` esa uni o'qiydi.
13. 🟡 Qoldiqlar: `app/input/route.ts` (eski Wialon eslatma), `/translations` router va `e2e_localization.py` (til olib tashlangan), ildizdagi `wialon_*probe*.py`, `gtk_*.py` skriptlari, `docs/AGENTS.md` (ildizdagi nusxa).
14. ❓ **Korxona standarti (`codex-standard`):** tizimda o'z login/parol bor, standart AD orqali kirishni talab qilishi mumkin. Alohida qaror kerak. Xodim shaxsiy ma'lumotini tashqi servis/AI'ga yubormang (lokal Ollama mos).

## 13. Tekshiruv va ishga tushirish buyruqlari

**Frontend (PC, PowerShell):**
```powershell
npx tsc --noEmit
npm run lint
npm run build      # dev server o'chiq bo'lsin
```

**Backend testlari:** Python 3.12 va `backend/.venv` da, `pytest` bilan (`pg` markerli test uchun alohida `pg_rehearse` bazasi kerak). E2E skriptlar (`backend/scripts/e2e_*.py`) faqat foydalanuvchi tomonidan test API'ga qarshi ishga tushiriladi.

**Server (faqat o'qish, xavfsiz):**
```bash
docker compose -p toir ps
docker compose -p toir run --rm --no-deps --entrypoint alembic backend current
curl -s http://127.0.0.1:8010/health
```

**Birinchi o'rnatish:** `docs/DEPLOY.md`. Zaxira: `scripts/backup_postgres.sh`. Wialon prod tartibi: `docs/PROD_RUNBOOK.md`.

## 14. Ishlash qoidalari (AI uchun) — `AGENTS.md` bilan bir xil

- Foydalanuvchi boshlang'ich: **o'zbek tilida, sodda, qisqa**. Buyruqlar kichik nusxa-ko'chirish bloklarida, har biri **[PC]** yoki **[SERVER]** deb belgilanadi.
- Avval `AGENTS.md`, keyin `docs/HANDOFF.md` oxirgi bo'limlari, kerak bo'lsa `PROJECT.md` va `docs/DECISIONS.md`. Butun repoyni o'qima.
- Buyruq natijasini ko'rmasdan "ishladi/tuzatildi" dema. Aks holda **NOT TESTED** yoz. Oxirida tekshirilmaganlar ro'yxatini ber.
- Maxfiy qiymat (parol, token, kalit, DB URL) chiqarma. `.env`, `.env.local`ni ochma.
- Taqiq: `git reset --hard`, `git clean`, `git push --force`, `git checkout .`, `rm -rf`, `docker system prune`, `docker volume prune`, `docker compose down -v`. Ommaviy o'chirish/nomlash yo'q.
- `git pull/commit/push` ni foydalanuvchi qiladi. Sxema/migratsiyani rejasiz va tasdiqsiz o'zgartirma.
- `fuel` tizimi, uning konteynerlari, portlari, nginx'iga tegma. Serverga ulanma, deploy/docker/e2e'ni foydalanuvchi ishga tushiradi.
- Eng kichik to'g'ri o'zgarish. Bir vaqtda bitta vazifa. Katta/xavfli ishda avval reja, tasdiqni kut.
- Rol: master faqat o'z uchastkasi, serverda, so'rov ichida, **404** qaytar, status tekshiruvidan oldin.
- Frontend: faqat `api.*()`. UI matni rus tilida.
- Vazifadan keyin: `docs/HANDOFF.md` ("Verified" va "Next task"), `docs/AI_WORKLOG.md` (3–5 qator), yangi qaror bo'lsa `docs/DECISIONS.md`.

## 15. Hozirgi bosqich va keyingi vazifalar

**Bosqich:** kod yozish bosqichi katta qismi tugagan (modullar mavjud), **tekshirish va production'ga xavfsiz chiqarish bosqichi** boshlanmagan. Oxirgi ish: vagon probegi P0.3 (2026-11-10…12), unda 317 test o'tgani va 0029 migratsiya vaqtinchalik bazada up/down/up bajarilgani xabar qilingan 🟢.

**Tavsiya etilgan tartib:**
1. **Hozirgi holatni aniqlash (faqat o'qish):** serverdagi alembic revision, ishlayotgan compose, konteynerlar, `git log -5`. Bu 4-bo'lim va 12-bo'limdagi ❓ larni yopadi.
2. **Zaxira** (`backup_postgres.sh`) va uni tiklab ko'rish.
3. **Migratsiyalarni bir nusxa bazada sinash** (0006–0029), keyin `schema.sql` bilan solishtirish.
4. **CI'ni tuzatish:** `pytest`, `pytest-asyncio` ni requirements'ga qo'shish yoki CI'ni pytest'ga o'tkazish; GitHub Actions natijasini ko'rish.
5. **E2E skriptlarni test API'da ishga tushirish** (`e2e_refs`, `e2e_assets`, `e2e_workorders`, `e2e_permissions`, `e2e_user_status`, `e2e_dashboard`, `e2e_gtk*`, `e2e_wialon_units`, `e2e_audit_logs`).
6. **Brauzerda qo'lda tekshirish:** login, ОС ro'yxati/pasport, work-orders, ТО jadvali, ruxsatlar, master doirasi.
7. **Xavfsizlik:** TLS qarori (HTTPS), `.gitignore` tuzatish (`backups/`), keraksiz fayllarni olib tashlash, `npm audit`.
8. **Wialon/GTK:** jonli ulanishni bosqichma-bosqich yoqish (`PROD_RUNBOOK.md`), dastlab bitta sinxronlash.
9. **Biznes qarorlar** (vagon probegi PENDING ro'yxati) — egasi bilan kelishish.
10. **Keyin:** ТМЦ hujjatlari CRUD (agar kerak bo'lsa, avval talab va ombor harakati qoidalari), `daily_readiness_snapshots` yozuvchisi, `xlsx`/Next yangilash.

## 16. Qayerdan nimani topish

| Savol | Fayl |
|---|---|
| Hozirgi holat va oxirgi vazifa | `docs/HANDOFF.md` (katta, faqat oxirgi bo'limlarni o'qing) |
| Nima uchun shunday qaror qilingan | `docs/DECISIONS.md` |
| Kim, qachon, nimani o'zgartirgan | `docs/AI_WORKLOG.md` |
| Server o'rnatish / ko'chirish | `docs/DEPLOY.md`, `README.md` |
| Wialon ishga tushirish | `docs/PROD_RUNBOOK.md`, `docs/TOIR_Wialon_Tutorial.md` |
| GTK/Wialon/1С ulash qoidalari | `docs/INTEGRATIONS.md` |
| Vagon probegi qoidalari | `docs/WAGON_MILEAGE_P0_DECISIONS.md`, `docs/WAGON_MILEAGE_P0_2_IMPLEMENTATION_PLAN.md` |
| Eski audit | `docs/AUDIT_2026-10-19.md` (qisman eskirgan) |
| Ruxsatlar katalogi | `backend/app/core/permissions.py` |
| Sxema | `backend/alembic/versions/`, `postgres/schema.sql` |
