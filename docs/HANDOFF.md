# TOIR — HANDOFF (holat, qarorlar, keyingi ishlar)

> Sana: 2026-10-06. Bu fayl yangi chat/agent sessiyasi uchun **yagona kontekst manbai**.
> Avvalgi sessiyaning xotirasi yangi akkauntda YO'Q. Hamma narsa shu faylda va repoda.
> Faylni oxirigacha o'qimasdan kod o'zgartirma.

---

## 0. Agent uchun qoidalar (majburiy)

1. **Halol hisobot.** "Ishladi/tasdiqlandi" faqat o'zing haqiqatan bajargan buyruq natijasi bilan aytiladi. Bajarilmagan narsani "bajarildi" deb yozma. Har bosqich oxirida: *nima ishga tushirildi → qanday natija* va *nima tekshirilmadi*.
2. **Supabase'ga tegma.** Supabase dashboard'da user yaratma, uning kalitlarini ishlatma. Maqsad — uni butunlay olib tashlash.
3. **Maxfiy ma'lumotlarni chiqarma.** `.env`, `.env.local` qiymatlari, parollar, tokenlar, parolli DB URL — terminalga ham, chatga ham, logga ham chiqarilmasin (`print(url)` kabi tekshiruvlar taqiqlanadi).
4. **Taxmin qilma.** `PROJECT.md` yoki `postgres/schema.sql` bilan ziddiyat bo'lsa — to'xta va savol ber.
5. **Windows / CRLF.** Repo Windows'da (CRLF). `str_replace` "No match found" bersa — faylni avval to'liq o'qib, so'ng to'liq qayta yoz. Bir xil muvaffaqiyatsiz urinishni takrorlama.
6. **Bosqichma-bosqich.** Bir vaqtda bitta vazifa. Oxirida o'zgargan fayllar ro'yxati va tekshiruv buyruqlari.
7. **Dependency'lar.** Lokal venv uchun **Python 3.12** (Docker image ham 3.12). Python 3.14 da pinned paketlar (asyncpg, pydantic-core) o'rnatilmasligi mumkin.

---

## 1. Maqsad va qabul qilingan qarorlar

**Maqsad:** TOIR (temir yo'l harakat tarkibi uchun ТО/ТР boshqaruvi) tizimini Supabase'siz, lokal va xavfsiz ishlaydigan qilish: **Next.js frontend + Python FastAPI backend + PostgreSQL 16, hammasi Docker Compose'da.**

| Qaror | Tafsilot |
|---|---|
| Supabase | Butunlay olib tashlanadi: Auth, RLS, Realtime, `supabase-js`, view/trigger'lar |
| Eski ma'lumotlar | **Ko'chirilmaydi.** Faqat struktura va bog'lanishlar (`postgres/schema.sql`) |
| Auth | Backend'ning o'z JWT'si: access 30 daqiqa, refresh 7 kun (rotatsiya), parol bcrypt |
| Rollar | `admin`, `operator`, `master`, `management`. Master faqat o'z uchastkasi — **serverda** majburlanadi |
| Nariyad statuslari | `pending → in_progress → completed \| cancelled`. `overdue` saqlanmaydi, `date_end` bo'yicha hisoblanadi |
| ТО chegaralari | Yagona manba — `maintenance_intervals` jadvali. Qattiq yozilgan 5 000…1 600 000 km va `ТО-90` ishlatilmaydi |
| Realtime | Postgres `LISTEN/NOTIFY` (kanal `toir_changes`) → backend WebSocket `/ws` |
| Til/valyuta | UI rus tilida, pul — so'm (сум) |

Tizimning to'liq tavsifi (modullar, biznes qoidalar, rollar jadvali): `PROJECT.md`.

---

## 2. Hozirgi holat — ishonch darajasi bilan

Avvalgi agent sessiyasi logidan olingan. **"Tasdiqlangan" = real ishga tushirib ko'rilgan. "Faqat kod" = yozilgan, lekin real DB/serverda sinalmagan.**

### 2.1 Backend (`backend/`)

| Qism | Holat | Tasdiq |
|---|---|---|
| Skelet: `app/{core,models,schemas,repositories,services,routers}`, `main.py` | Yozilgan | Faqat kod (30 ta .py fayl sintaksis/import tekshiruvidan o'tgan) |
| ORM modellari: 22 jadval | `schema.sql` bilan ustun nomlari mosligi tekshirilgan | Faqat kod |
| Alembic baseline | Yozilgan; backend startida `alembic upgrade head` (entrypoint) | **Real Postgres'da hech qachon ishlamagan** |
| Auth: `/api/v1/auth/login`, `/refresh`, `/logout`, `/me` | Yozilgan | Faqat vaqtinchalik **xotira-DB adapteri** bilan smoke-test; PostgreSQL bilan emas |
| Refresh token: DB'da faqat SHA-256 xesh, rotatsiya, logout'da revoke | Yozilgan | Xuddi shunday (xotira-DB) |
| Login limiter: IP+email bo'yicha 15 daqiqada 5 ta xato → `429` | Yozilgan | Xotira darajasida sinalgan. Eslatma: jarayon xotirasida — bir nechta worker/replika bo'lsa ishlamaydi |
| `require_role(*roles)` (ko'p rolli), `is_active` tekshiruvi | Yozilgan | Xotira-DB bilan |
| CLI: `python -m app.cli create-admin` (interaktiv) | Yozilgan | **Admin hali yaratilmagan** |
| Users API (faqat admin): ro'yxat (limit/offset, `sort_by` whitelist), yaratish, tahrirlash, parol reset (refresh'lar revoke) | Yozilgan | Faqat kod. O'chirish endpointi ataylab yo'q |
| Work-orders API: list/get/create/PATCH, repairs/items, status oqimi, master scope, norm-check va template-items | Yozilgan (`T4a`), ID bo'yicha master GET/PATCH scope filtri status tekshiruvlaridan oldin qo'llanadi; `DELETE` faqat admin/management uchun | Faqat kod; `backend/scripts/e2e_workorders.py` cross-section pending/completed regressiyalarini ham qamraydi, real API/DB test hali bajarilmagan |
| ТО planner (`maintenance_intervals`, mileage hook, `maintenance-schedule`, `maintenance-plan`, editable `daily_average_km`) | Yozilgan (`T5`); settings jadvali Alembic `0002` migratsiyasi bilan; lokal unit-testlar qo'shilgan | Testlar hali ishga tushirilmagan; PostgreSQL migratsiyasi, backend API va brauzer real muhitda tekshirilmagan |
| CORS faqat `CORS_ORIGINS` env'dan, compose'da majburiy | Yozilgan | Faqat kod |
| Testlar (`backend/tests`) | Logdan mavjudligi ko'rinmaydi | — |

### 2.2 Infratuzilma

| Qism | Holat |
|---|---|
| `docker-compose.yml`: postgres (port tashqariga ochilmagan) + backend (`127.0.0.1:8000`) | Yozilgan, YAML siyosati tekshirilgan, **ishga tushirilmagan** |
| `.env.example` | Bor. `.env` sozlanmagan |
| Docker CLI / `psql` | **Avvalgi agent muhitida yo'q.** 5432 va 8000 portlarda hech narsa ishlamayapti |
| Frontend/proxy Dockerfile, HTTPS | Hali yo'q |

### 2.3 Frontend (Next.js)

| Qism | Holat |
|---|---|
| Dev server `localhost:3000`, login sahifasi ochiladi | Tasdiqlangan (brauzerda ko'rilgan) |
| Autentifikatsiyani Supabase'dan FastAPI'ga o'tkazish | **Noaniq.** Agent `/api/v1/auth/me` route'ini o'zgartirmoqchi bo'ldi, lekin edit ikki marta "No match found" (CRLF) bilan **muvaffaqiyatsiz** tugadi; logout route yaratish ham bir marta "Parent directory does not exist" bilan yiqildi. Qaysi biri keyin muvaffaqiyatli bo'lgani logdan aniq emas. **Birinchi vazifa — grep bilan tekshirish** (T1) |
| Sahifa tuzatishlari | Agent `os/page.tsx` (sintaksis), `work-orders/page.tsx` (xato holati), `dashboard/layout.tsx`, `directories/employees`, `maintenance`, `dashboard/page.tsx`, `reports`, `mileage/history` route (TS xato) fayllarini o'zgartirgan. Analytics tuzatishi muvaffaqiyatsiz |
| `npm run build` | Agent "Compiled successfully" dedi. **Qayta tekshirish kerak**: `next.config.mjs` da `typescript.ignoreBuildErrors` yoqilgan bo'lsa, bu tip xatolarini ko'rsatmaydi |
| Supabase kodi | Hali **to'liq** qolgan: `lib/supabase.ts`, `lib/supabase-utils.ts`, `app/api/*` (mileage, maintenance-plan, …), analytics/reports/users/directories/work-orders sahifalari |

### 2.4 Repo'dagi axlat / xavf belgilari

- Ildizda arxivdan qolgan **dublikat fayllar**: `config.py`, `auth.py`, `main.py`, `database.py`, `user.py`, `api.ts` va h.k. Haqiqiy kod `backend/app/` va `lib/` ichida. Ildizdagilar chalkashlik manbai — o'chirilishi kerak (avval import qilinmayotganini tekshirib).
- `app/dashboard/work-orders/*.py`, `app/dashboard/tmc/*.py` — adashib tushgan backend fayllari.
- Log'da agent `.env.local` ni `POSTGRES_*`/`DATABASE_HOST` o'zgaruvchilari bilan ishlatishga urindi — `.env.local` (frontend) bilan backend `.env` aralashib ketmasin.
- Playwright urinishida agent "Add user" / "Search by email" tugmasini bosmoqchi bo'ldi (UI Supabase Studio'ga o'xshaydi). Bu **Supabase dashboard orqali user yaratishga urinish** bo'lishi mumkin — qaror (Supabase yo'q) bilan zid, ishlamadi.

---

## 3. Nima bo'lyapti (qisqa xronologiya)

1. Backend skeleti + Alembic baseline yozildi (1-bosqich).
2. Auth, login limiter, CLI, admin-only Users API qo'shildi — faqat kod va xotira-DB smoke-test darajasida.
3. Real tekshiruv uchun Docker/Postgres kerak edi — muhitda yo'q. Agent venv yaratib paket o'rnatishga urindi (Python 3.14.7, pip xatosi), keyin xotira-DB adapteri bilan sinadi.
4. Frontend hali Supabase orqali kirayotgani aniqlandi; login/me route'larini FastAPI'ga yo'naltirishga urinildi (qisman muvaffaqiyatsiz).
5. Frontend'dagi build xatolari tuzatildi; dev server ishga tushdi; backend'siz login tasdiqlanmadi.
6. Chat limiti tugadi. **Real DB bilan hech narsa tasdiqlanmagan.**

**Asosiy blokirovka: backend ishlaydigan runtime yo'q (Docker yoki lokal PostgreSQL).** Shundan keyin hammasi tekshiriladi.

---

## 4. Xavfsizlik — shoshilinch ishlar

1. **Eski Supabase kalitlari** (`services/ml_engine.py`, `scripts/*.py`, `test-auth.js`) va `test-auth.js` dagi **admin login/paroli** kodda ochiq edi. `test-auth.js` olib tashlandi; saqlangan skriptlar endi `SUPABASE_URL` va `SUPABASE_KEY` muhit o'zgaruvchilarini talab qiladi. Avval oshkor bo'lgan yoki boshqa joyda ishlatilgan kalit/parollarni bekor qiling/almashtiring.
2. Agar repo GitHub'ga yuborilgan bo'lsa, eski kalitlar **git tarixida** qolishi mumkin; tarixni tozalash alohida tasdiq talab qiladi. Tozalanmaguncha oshkor bo'lgan kalitlarni yaroqsiz deb hisoblang va repoga kirishni cheklang.
3. `JWT_SECRET`, `POSTGRES_PASSWORD` — faqat `.env` da; `.gitignore` `.env` va `.env.*` ni e'tiborsiz qoldiradi, `.env.example` bundan mustasno. `.env.example` dagi `CHANGE_ME` qiymatlarini ishga tushirishdan oldin almashtiring. Parol logga chiqqan bo'lsa (agent `print(url)` qilgan) — almashtiring.
4. `.vscode/settings.json` da `claudeCodeChat.permissions.yoloMode: true` — repodan olib tashlang.
5. Login limiter hozir jarayon xotirasida; production uchun Redis yoki DB asosidagi variant (T10).
6. Frontend tokenlarni saqlash usuli (localStorage vs httpOnly cookie) — T1 da hal qilinadi (tavsiya: refresh token httpOnly cookie).

---

## 5. Maqsadli arxitektura

```
Brauzer ── HTTPS ──▶ proxy (Caddy/Nginx)
                       ├── /api, /ws ─▶ backend (FastAPI) ─▶ postgres (faqat internal tarmoq)
                       └── /        ─▶ frontend (Next.js)

backend ichida: routers → services → repositories → SQLAlchemy(async) → Postgres
                + auth(JWT) + wialon-ingest + ML worker + ws(LISTEN/NOTIFY)
```

Hozirgi repo tuzilmasi (bilingan qismi):

```
TOIR/
├── backend/
│   ├── app/{core,models,schemas,repositories,services,routers}/, main.py, cli.py
│   ├── alembic/, requirements.txt, entrypoint.sh, Dockerfile
├── postgres/schema.sql          # referens sxema (Alembic baseline shundan)
├── docker-compose.yml, .env.example
├── app/ lib/ components/ ...     # Next.js (hali Supabase'ga bog'liq qismlar bilan)
├── docs/HANDOFF.md              # shu fayl
└── PROJECT.md                   # tizimning to'liq tavsifi
```

Sxema qisqacha (23 jadval): `departments, sections, users, refresh_tokens, employees, fixed_assets, mileage_history, wialon_settings, work_types, work_subtasks, maintenance_intervals, nomenclature, nomenclature_norms, work_type_templates, work_orders, work_order_repairs, work_order_items, tmc_documents, tmc_document_items, maintenance_plan, maintenance_settings, maintenance_log, ai_insights`. Analytics view'lari (`executive_summary`, `section_efficiency`, `work_type_efficiency`, `monthly_efficiency`, `fleet_health`, `ai_insights_summary`, `maintenance_schedule`, `work_order_tmc_details`) **hali yozilmagan** — alohida migratsiya.

---

## 6. Keyingi vazifalar (tartib bilan)

Har bir vazifaning "tayyor" mezoni — **real ishga tushirilgan** tekshiruv. Prompt'lar `PROMPTS.md` da.

| # | Vazifa | Tayyor mezoni |
|---|---|---|
| **T0** | **Runtime:** Docker Desktop (yoki lokal PostgreSQL 16 + Python 3.12 venv); `.env`; `alembic upgrade head`; admin yaratish; real login + `/me` | `docker compose up` yashil, `create-admin` ishlaydi, curl/Invoke-RestMethod bilan login → me 200 |
| **T1** | **Frontend auth ko'prigi:** Supabase auth → FastAPI; `lib/auth-context.tsx` ↔ `lib/api.ts`; Next `/api/v1/auth/*` route'larini o'chirish | Brauzerda login/refresh/logout; Supabase'ga hech so'rov ketmaydi |
| **T2** | **Spravochniklar CRUD:** sections, departments, employees, work-types (+subtasks, templates), maintenance-intervals, nomenclature, norms | Har bir resurs uchun list/get/create/update/delete, rol tekshiruvi, pytest |
| **T3** | **Fixed assets + mileage + Wialon ingest** (`WIALON_INGEST_TOKEN`) | ОС CRUD; `POST /wialon/input` tokensiz 401; mileage_history yoziladi |
| **T4a** | **Work-orders backend** (repairs/items, `number` generatsiyasi, status o'tishlari, master server filtri, norma >20% tekshiruvi) | Kod va E2E skript yozilgan; deploy/PostgreSQL orqali real test kutilmoqda |
| **T4b** | Work-orders frontend va **tmc-documents** API | Hali bajarilmagan |
| **T5** | **ТО-reja xizmati** (`maintenance_intervals` asosida) + `maintenance-schedule` | Kod yozilgan; `daily_average_km` interfeysdan sozlanadi, mileage-hook va interval forecast mavjud. Alembic/PostgreSQL, API va brauzer deploydan keyin tekshiriladi |
| **T6** | **Analytics view'lari** + `dashboard/summary` + reports | Kod yozilgan: 8 ta view, FastAPI analytics/report API, frontend analytics/reports/dashboard FastAPI'dan foydalanadi. `Готовность по месяцам` kunlik snapshotlardan yig'iladi; migratsiya qo'llangandan va dashboard ilk bor ochilgandan boshlab tarix yig'iladi, oldingi tarix sun'iy to'ldirilmaydi. PostgreSQL/Alembic va brauzer deploydan keyin tekshiriladi |
| **T7** | **WebSocket `/ws`** (LISTEN/NOTIFY, JWT bilan autentifikatsiya) | Kod yozilgan: access-token birinchi xabarda, `users`/`work_orders`/`fixed_assets` obunalari, PostgreSQL listener reconnect va master section-scope filtr. `0004_realtime_scopes` migratsiyasi, backend va brauzer deploydan keyin tekshirilishi kerak |
| **T8** | **Frontend'ni to'liq Supabase'dan tozalash**, ildizdagi dublikat fayllarni o'chirish, `package.json`dan `@supabase/*` | `grep -ri supabase` natijasi bo'sh; build toza |
| **T9** | **ML worker** (anomaliya, RUL, health score) backend ichida | Nariyad `completed` bo'lganda `ai_insights` yoziladi |
| **T10** | **Production qotirish:** frontend Dockerfile, Caddy + HTTPS, rate-limit (Redis/DB), `/docs` o'chirish flag'i, CI, testlar, zaxira nusxa | `docker compose up` bilan butun stek; CI yashil |

---

## 7. Tekshiruv buyruqlari (PowerShell)

```powershell
cd "D:\Profiles\t.turakulov\My Documents\GitHub\TOIR"
Copy-Item .env.example .env
# Maxfiy qiymatlar generatsiyasi (openssl shart emas):
python -c "import secrets; print(secrets.token_hex(32))"      # JWT_SECRET uchun
python -c "import secrets; print(secrets.token_urlsafe(24))"  # POSTGRES_PASSWORD uchun
# .env ni tahrirlang: POSTGRES_PASSWORD, JWT_SECRET, CORS_ORIGINS=http://localhost:3000, WIALON_INGEST_TOKEN

docker compose up --build -d
docker compose logs backend --tail 50
docker compose exec backend python -m app.cli create-admin

$login = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/auth/login `
  -ContentType 'application/json' -Body '{"email":"ADMIN_EMAIL","password":"ADMIN_PASSWORD"}'
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/auth/me `
  -Headers @{ Authorization = "Bearer $($login.access_token)" }
```

Docker o'rnatilmasa muqobil (vaqtincha): lokal PostgreSQL 16 → bo'sh `toir` bazasi → `backend` papkasida Python 3.12 venv → `pip install -r requirements.txt` → `DATABASE_URL`, `JWT_SECRET`, `CORS_ORIGINS` ni muhit o'zgaruvchisi qilib `alembic upgrade head` va `uvicorn app.main:app --port 8000`.

---

## 8. Ochiq savollar (foydalanuvchi hal qiladi)

1. Refresh token frontend'da qanday saqlansin: httpOnly cookie (xavfsizroq, tavsiya) yoki xotira/localStorage?
2. `maintenance_intervals` standart qiymatlari qanday bo'lsin (ТО-1 = 50 km yoki 5 000 km)? Hozir hujjatda uch xil tizim bor.
3. Foydalanuvchini o'chirish kerakmi yoki faqat `is_active=false`?
4. Production serverda HTTPS uchun domen bormi yoki faqat ichki tarmoq (self-signed)?
5. Docker Desktop kompaniya kompyuterida o'rnatilishi mumkinmi (admin huquqi, litsenziya)? Bo'lmasa — lokal PostgreSQL varianti.
