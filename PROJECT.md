# TOIR — Texnik xizmat ko'rsatish va ta'mirlash tizimi (A dan Z gacha)

> **TOIR** (Система технического обслуживания и ремонтов) — temir yo'l harakat tarkibi (lokomotiv, teplovoz, vagon-samosval) uchun texnik xizmat (ТО) va ta'mirlash (ТР/СР/КР) jarayonlarini boshqaruvchi veb-tizim. Interfeys brendi: **STTB — Система ТО**. Interfeys tili — rus tili, pul birligi — so'm (сум).
>
> Bu hujjat `TOIR.zip` arxividagi barcha fayllarni o'qib chiqib tuzilgan. Qayerda kod bo'yicha taxmin qilingan bo'lsa, "ko'rinishicha" deb belgilangan.

---

## 1. Qisqacha mazmun

| Savol | Javob |
|---|---|
| Tizim nima qiladi? | Asosiy vositalar (ОС) reyestri, nariyad-buyurtmalar (наряд-заказы), ТО/ТР grafigi (Gantt), TMC (ТМЦ) hujjatlari va normativlari, hisobotlar, tahlil va AI-prognozlarni yagona joyda yuritadi |
| Kim foydalanadi? | `admin`, `operator`, `master` (uchastka ustasi); backend modelida yana `management` roli bor |
| Qanday ishlaydi? | Frontend (Next.js) → Supabase (to'g'ridan-to'g'ri) va/yoki FastAPI backend; pробег Wialon GPS-dan avtomatik keladi; ML skripti nariyad yopilganda anomaliya va nosozlik xavfini hisoblaydi |
| Hozirgi holat | **Migratsiya jarayonida**: Supabase → FastAPI + PostgreSQL. Ba'zi sahifalar yangi API'da, ba'zilari hali Supabase'da (7-bo'limga qarang) |
| Kod hajmi | ~13 600 qator TS/TSX (UI kit'siz), ~2 900 qator Python, ~1 800 qator SQL, 58 ta UI komponent |

---

## 2. Texnologiyalar steki

**Frontend**
- Next.js **15.2.6** (App Router), React **19**, TypeScript 5
- Tailwind CSS **4** (`@tailwindcss/postcss`), `tailwindcss-animate`, `tw-animate-css`
- shadcn/ui uslubidagi komponentlar (Radix UI), `lucide`-uslubidagi ikonlar (`components/ui/icons.tsx`), `bootstrap-icons`
- Grafiklar: **Recharts 2.15**
- Formalar: `react-hook-form` + `zod`; bildirishnomalar: `sonner`; mavzular: `next-themes`
- `@supabase/supabase-js` ^2.117, `@vercel/analytics`, `date-fns`, `xlsx` (faqat devDependencies, skriptlar uchun)
- Paket menejeri: `pnpm-lock.yaml` va `package-lock.json` ikkalasi ham bor (bitta tanlash kerak)

**Backend (FastAPI)**
- Python 3.12 (Dockerfile), FastAPI 0.111, Uvicorn 0.30, SQLAlchemy 2.0 (async, `asyncpg`), Alembic 1.13
- `pydantic` 2.8 + `pydantic-settings`, `python-jose` (JWT, HS256), `passlib` + `bcrypt`
- PostgreSQL 16 (docker-compose)

**ML / skriptlar**
- pandas, numpy, scikit-learn (IsolationForest, LinearRegression, StandardScaler)
- Flask + gunicorn (ML webhook serveri), `supabase` Python klienti
- Node.js: Express (Wialon qabul qiluvchi) — **package.json'da yo'q**, qarang 12-bo'lim

**Tashqi tizimlar**: Supabase (Auth, Postgres, Realtime), Wialon (GPS/pробег), Vercel Analytics.

---

## 3. Arxitektura

```
                       ┌─────────────────────────────┐
                       │  Brauzer (Next.js, React)   │
                       │  app/ · lib/ · components/  │
                       └──────┬───────────────┬──────┘
                 (eski yo'l)  │               │  (yangi yo'l)
       supabase-js (anon key) │               │  lib/api.ts  (Bearer JWT, fetch)
                              ▼               ▼
        ┌──────────────────────────┐   ┌───────────────────────────────┐
        │ Supabase                 │   │ FastAPI  (/api/v1/…)          │
        │  Auth · Postgres · RT    │   │  routers → services → repos   │
        │  views, triggerlar, RLS  │   │  SQLAlchemy async + Postgres  │
        └───▲───────────▲──────────┘   └───────────────▲───────────────┘
            │           │                              │ WebSocket /ws
   ┌────────┴──┐   ┌────┴─────────────┐                │ (lib/use-realtime.ts)
   │ Wialon    │   │ ML engine        │◄───────────────┘ (rejalashtirilgan)
   │ receiver  │   │ services/        │  webhook: nariyad status = completed
   │ (Express) │   │ ml_engine.py     │
   └───────────┘   └──────────────────┘
        ▲
   Wialon retranslyator (POST/GET /input: pробег, tezlik)
```

**Asosiy g'oya**: loyiha avval to'liq Supabase ustida qurilgan (RLS ochiq, sahifalar `supabase.from(...)` bilan ishlaydi). Keyin "Phase" tartibida FastAPI + oddiy PostgreSQL'ga o'tkazish boshlangan. Natijada **hozir ikki parallel dunyo** mavjud (qarang 7 va 15-bo'limlar).

### Eslatma: ZIP tuzilmasi buzilgan
Arxivdagi fayllar "yassilangan" (flat). Masalan, `main.py`, `config.py`, `database.py`, `auth.py`, `jwt.py`, `password.py`, `dependencies.py`, `user.py` ildizda yotibdi, backend routerlari/servislari esa `app/dashboard/work-orders/` va `app/dashboard/tmc/` ichida. Ularning import yo'llari (`..services.work_order`, `..repositories.…`, `..schemas.…`, `..security.dependencies`, `..models.user`) haqiqiy `backend/app/` paket tuzilmasini ko'rsatadi. **`repositories/`, aksariyat `schemas/`, `models/` (User'dan tashqari), `services/` katalogi, `alembic/` va `postgres/schema.sql` arxivda yo'q.** Backend to'liq tiklanishi uchun asl `backend/` papkasi kerak.

---

## 4. Papkalar xaritasi

```
TOIR/
├── app/                              # Next.js App Router
│   ├── layout.tsx                    # Root: Providers, Geist shrift, Vercel Analytics
│   ├── page.tsx                      # "/" → redirect /auth/login
│   ├── globals.css                   # 6 ta mavzu (data-theme), tokenlar
│   ├── auth/login/page.tsx           # Kirish sahifasi
│   ├── input/route.ts                # Wialon uchun yo'l-yo'riq (haqiqiy qabul — alohida server)
│   ├── api/
│   │   ├── v1/auth/login/route.ts    # Supabase signInWithPassword + profiles
│   │   ├── v1/auth/me/route.ts       # Token bo'yicha profil
│   │   ├── mileage/route.ts          # Pробег → ТО bashorati, maintenance_plan upsert
│   │   ├── mileage/history/route.ts  # Pробег tarixi (grafik uchun)
│   │   ├── maintenance-plan/route.ts # GET/POST/PATCH ТО rejalari
│   │   └── maintenance-schedule/route.ts  # Birlashgan ТО grafigi (Supabase versiyasi)
│   └── dashboard/
│       ├── layout.tsx                # Sidebar, rol bo'yicha menyu, uchastka tanlash
│       ├── page.tsx                  # Dashboard (KPI, donut, trendlar)
│       ├── analytics/                # Tahlil + AI
│       ├── os/                       # Основные средства
│       ├── maintenance/              # ТО va ремонты (Gantt/jadval)
│       ├── work-orders/              # Наряд-заказы (eng katta modul, 2114 qator)
│       ├── tmc/                      # ТМЦ hujjatlari + nomenklatura
│       ├── reports/                  # CSV hisobotlar
│       ├── admin/users/              # Foydalanuvchilar (faqat admin)
│       ├── directories/              # Справочники (employees, sections, work-types, maintenance-intervals)
│       ├── work-orders/*.py, tmc/*.py  # ⚠ adashib shu yerga tushgan backend fayllari
├── components/ (theme-*, ui/ — 58 ta)
├── lib/                              # api.ts, auth-context, supabase, realtime, hooks
├── hooks/                            # use-toast, use-mobile
├── server/                           # wialon-receiver.js, check-db.js
├── services/                         # ml_engine.py + requirements.txt
├── scripts/                          # SQL migratsiyalar, import/seed/anomaliya skriptlari
├── docs/                             # PERFORMANCE_AUDIT.md, WEBHOOK_SETUP.md
├── *.sql                             # schema.sql, supabase_schema.sql, profiles/sections/departments sxemalari
├── *.py (ildizda)                    # FastAPI yadrosi: main, config, database, auth, jwt, password, dependencies, user
├── Dockerfile, docker-compose.yml, alembic.ini, requirements.txt
├── next.config.mjs, middleware.ts, tsconfig*.json, components.json, postcss.config.mjs
└── .env.example, .env.local.example, .env.local, .gitignore, README.md
```

---

## 5. Rollar va ruxsatlar

Rollar: `admin`, `operator`, `master` (frontend), `management` (faqat backend/`api.ts` tipida).

| Bo'lim | admin | operator | master |
|---|:-:|:-:|:-:|
| Дашборд | ✅ | ✅ | ❌ |
| Аналитика | ✅ | ✅ | ❌ |
| Осн. средства | ✅ | ✅ | ❌ |
| ТО и ремонты | ✅ | ✅ | ❌ |
| Наряд-заказы | ✅ | ✅ | ✅ (faqat o'z uchastkasi) |
| ТМЦ | ✅ | ✅ | ❌ |
| Отчёты | ✅ | ✅ | ❌ |
| Справочники | ✅ | ✅ | ❌ |
| Пользователи | ✅ | ❌ | ❌ |

- Menyu `ALL_NAV` massivi (`app/dashboard/layout.tsx`) orqali rol bo'yicha filtrlanadi. **Faqat UI darajasida**: `middleware.ts` hech narsa tekshirmaydi (`NextResponse.next()`), master URL'ni qo'lda yozib boshqa sahifaga kira oladi.
- **Uchastka konteksti** (`lib/section-view-context.tsx`): master uchun `effectiveSection = profile.section`; admin sidebar'dagi ro'yxatdan "Barcha uchastkalar" yoki bitta uchastkani tanlaydi. Dashboard va TMC shu qiymat bilan filtrlanadi.
- Backend work-order ruxsatlari: ro'yxatni barcha autentifikatsiyalangan rollar ko'radi (master faqat o'z uchastkasini); yaratish — `admin, management, operator, master` (master faqat o'z uchastkasida); yangilash — `admin, management, operator, master` (master faqat o'z uchastkasida); o'chirish — faqat `admin, management` (operator va master uchun taqiqlangan).

---

## 6. Autentifikatsiya oqimi

**Haqiqatda ishlayotgan yo'l (Supabase Auth):**
1. `LoginPage` → `useAuth().signIn(email, password)`.
2. `lib/auth-context.tsx` → `POST /api/v1/auth/login` (Next.js route).
3. Route `supabase.auth.signInWithPassword` chaqiradi, `profiles` jadvalidan `{id, email, full_name, role, section}` oladi, `{access_token, refresh_token, user}` qaytaradi.
4. Klient `supabase.auth.setSession(...)` qiladi; sessiya `localStorage`da saqlanadi (`lib/supabase.ts`da Web Locks o'rniga `noopLock`).
5. `onAuthStateChange` profilni qayta yuklaydi. `signOut` → `supabase.auth.signOut()`.
6. `/api/v1/auth/me` — Bearer tokenni tekshirib profilni qaytaradi.

**Foydalanuvchi yaratish** (`admin/users`): klientdan `supabase.auth.signUp({ options: { data: { full_name, role, section } } })`. `auth.users`ga INSERT bo'lganda `handle_new_user()` triggeri `profiles` qatorini avtomatik yaratadi. Tahrirlash — `profiles.update(...)`; `admin_users_sync` Realtime kanali ro'yxatni yangilaydi.

**Rejalashtirilgan yo'l (FastAPI JWT):** `jwt.py` (HS256, `ACCESS_TOKEN_EXPIRE_MINUTES` = 24 soat), `password.py` (bcrypt), `dependencies.py` (`OAuth2PasswordBearer("/api/v1/auth/login")`, `get_current_user`, `require_role`), `auth.py` (LoginRequest, TokenResponse). `lib/api.ts`: tokenni xotirada saqlaydi, 401 bo'lsa `POST /auth/refresh` bilan yangilab, so'rovni bir marta takrorlaydi.

---

## 7. Migratsiya holati (Supabase → FastAPI)

| Modul / sahifa | Hozirgi ma'lumot manbai |
|---|---|
| Sections (uchastkalar) | ✅ FastAPI (`api.sections`) |
| Departments | ✅ FastAPI |
| Nomenclature (TMC spravochnigi) | ✅ FastAPI |
| Fixed assets (ОС) | ✅ FastAPI (+ Realtime WebSocket) |
| TMC hujjatlari (ro'yxat) | ✅ FastAPI (`api.tmcDocuments`) |
| Dashboard | ✅ FastAPI (`api.dashboard.getSummary`) |
| ТО grafigi (Gantt) | ✅ FastAPI (`api.maintenanceSchedule`) |
| Nariyad-buyurtmalar | ❌ **Supabase** (`work_orders`, `fixed_assets`, `employees`, `work_types`) + FastAPI (normativlar, shablonlar) |
| Analytics | ❌ Supabase (view'lar: `executive_summary`, `section_efficiency`, … `ai_insights`, `fleet_health`) |
| Reports | ❌ Supabase (`work_orders`, `tmc_documents`, `fixed_assets`) |
| Admin/users | ❌ Supabase (`auth`, `profiles`) |
| Employees, Work-types, Maintenance-intervals | ❌ Supabase |
| Wialon receiver, ML engine, import skriptlari | ❌ Supabase |
| Realtime | `lib/use-realtime.ts` (WebSocket `…/ws`) — hozir faqat klient tomoni yozilgan |

`sections_migration_notes.md` va `departments_nomenclature_assets_notes.md` migratsiya qoidasini belgilaydi: komponentlarda `fetch`/`supabase` o'rniga faqat `lib/api.ts`dagi `api.<resurs>.<metod>()` chaqiriladi; ro'yxat javobi `{items,total,limit,offset}` ko'rinishida; xatolar `Error(detail)` sifatida tashlanadi.

---

## 8. Ma'lumotlar bazasi

### 8.1 Ikki parallel sxema
| | **Supabase sxemasi** (`supabase_schema.sql` + `scripts/*.sql`) | **FastAPI sxemasi** (`schema.sql`) |
|---|---|---|
| `work_orders.id` | `text` (`НЗ-YYYYMMDD-HHMMSS`) | `VARCHAR(50)` |
| Bog'lanish usuli | matn maydonlari: `unit`, `section`, `depot`, `equipment` | FK: `fixed_asset_id`, `department_id`, `section_id` |
| `fixed_assets.id` | `text` (inventar raqam) | `UUID` |
| `fixed_assets.mileage` | `text` | `NUMERIC(10,2)` |
| `wialon_id` | `INTEGER` | `VARCHAR(100)` |
| Foydalanuvchilar | `auth.users` + `profiles` | `users` jadvali (`hashed_password`, rol) |
| Nariyad statuslari | `pending/in_progress/completed` | `pending/in_progress/completed/cancelled` (service'da esa `draft→planned→…`) |

> ⚠ Ikki sxema bir-biriga mos emas — migratsiya tugamaguncha frontend turlari (`lib/api.ts`) va haqiqiy ustunlar o'rtasida nomuvofiqlik chiqadi.

### 8.2 Jadvallar (Supabase tomoni)

| Jadval | Vazifasi | Muhim ustunlar |
|---|---|---|
| `profiles` | Foydalanuvchi profili/roli | `id`→`auth.users`, `full_name`, `email`, `role` (`admin/operator/master`), `section` |
| `sections` | Uchastkalar | `id uuid`, `name unique` (FastAPI'da `department_id` ham bor) |
| `departments` | Rangli bo'limlar (nomenklatura egasi) | `name unique`, `color` (default `#3b82f6`) |
| `employees` | Xodimlar | `tab_number unique`, `full_name`, `position`, `section_id`, `location_id` |
| `fixed_assets` | ОС: lokomotiv/teplovoz/vagon | `name`, `asset_type` (`locomotive/diesel/wagon`), `series`, `depot`, `status` (`operational/maintenance/repair/out_of_service`), `comm_date`, `year_built`, `mileage`, `last_maint`, `next_maint`, `inv_number`, `initial_cost`, `owner`; ML: `failure_probability`, `health_score`, `predicted_failure_km`, `last_ml_update`; Wialon: `wialon_id`, `wialon_last_sync`, `wialon_speed`, `wialon_online` |
| `work_orders` | Nariyad-buyurtmalar | `id`, `unit_type`, `unit`, `depot`, `section`, `equipment`, `work_type`, `repair_kind`, `status`, `priority`, `tech`, `chief`, `description`, `note`, `created`, `closed`, `repair_items jsonb`, `date_start`, `date_end`, `mileage_at_creation`, `mileage_threshold` |
| `tmc_documents` | Требование-накладная | `doc_no`, `date`, `work_order_id`, `loco`, `work_type`, `depot`, `warehouse`, `issued_by`, `accepted_by`, `chief`, `status` (`draft/issued/closed`), `items jsonb` |
| `nomenclature` | TMC spravochnigi | `department_id`, `name`, `code`, `unit`, `extra jsonb`; `UNIQUE(department_id,name)` |
| `nomenclature_norms` | Sarf normativlari | `nomenclature_id`, `department_id`, `work_type`, `standard_quantity`, `avg_price`, `min/max_quantity`; `UNIQUE(nomenclature_id,department_id,work_type)` |
| `work_types` | Ish turlari (ТО-1, ТР-2…) | `code unique`, `name`, `unit_type` (`locomotive/wagon`), `sort_order` |
| `work_subtasks` | Ish turi ichki vazifalari | `work_type_id`, `name`, `sort_order` |
| `work_type_tmc` | Ish turi bo'yicha TMC shablon | `work_type_id`, `name`, `inv_no`, `unit`, `qty`, `note` |
| `work_type_templates` | TMC avto-to'ldirish shabloni | `work_type`, `department_id`, `nomenclature_id`, `default_quantity`, `is_required` |
| `maintenance_intervals` | ТО normativ pробеglari | `code unique`, `name`, `interval_km`, `interval_days`, `asset_types text[]`, `is_active` |
| `maintenance_plan` | Avto-rejalashtirilgan ТО | `asset_id`, `asset_name`, `maintenance_type`, `status` (`Scheduled/InProgress/Completed/Cancelled`), `trigger_mileage`, `scheduled_date`, `completed_date`; `UNIQUE(asset_id,maintenance_type,trigger_mileage)` |
| `mileage_history` | Pробег tarixi | `asset_id`, `mileage`, `source` (`wialon/manual`), `recorded_at` |
| `wialon_settings` | Wialon sozlamalari | `host`, `token`, `sync_interval_minutes`, `auto_sync_enabled`, `last_sync_*` |
| `maintenance_log` | Tarixiy sarf (Excel'dan import) | `section_name`, `item_name`, `qty`, `unit`, `equipment`, `work_type`, `maintenance_date` |
| `ai_insights` | ML natijalari | `equipment_id`, `work_order_id`, `insight_type` (`anomaly/prediction/efficiency`), `probability`, `severity` (`low…critical`), `message`, `suggested_action`, `details jsonb`, `is_resolved` |

`work_orders.repair_items` tuzilmasi: `[{ id, kind: "ТО-2", rows: [{ id, name, invNo, unit, qty, note }] }]` — ya'ni har bir ta'mir turi (kind) ichida TMC qatorlari.

### 8.3 View'lar
`active_maintenance_plans` (qolgan km va shoshilinchlik: overdue/critical/warning/normal), `maintenance_schedule` (har bir ОС × har bir interval, `overdue/due/upcoming`), `active_maintenance_orders`, `work_order_tmc_details` (JSONB'ni qatorlarga ochadi, normativ bilan bog'laydi, og'ish % va narxni hisoblaydi), `executive_summary` (xarajat vs normativ, tejash, nariyadlar orasidagi pробег/kunlar — `LAG` bilan), `section_efficiency`, `work_type_efficiency`, `monthly_efficiency`, `ai_insights_summary` (30 kun), `fleet_health` (sog'lom/ogohlantirish/xavf/kritik sonlari, o'rtacha health, ishonchlilik %).

### 8.4 Triggerlar va funksiyalar
- `handle_new_user()` — `auth.users` INSERT → `profiles` yaratadi.
- `auto_schedule_maintenance()` — `fixed_assets.mileage` o'zgarsa, 8 ta chegara (5 000 / 15 000 / 30 000 / 100 000 / 200 000 / 400 000 / 800 000 / 1 600 000 km ↔ ТО-1, ТО-2, ТО-3, ТР-1, ТР-2, ТР-3, СР, КР) bo'yicha, chegaraga ≤10% qolganda `maintenance_plan` upsert qiladi; sana = bugun + ceil(qolgan_km / 200).
- `record_mileage_change()` — pробег o'zgarganda `mileage_history`ga yozadi (manba: wialon yoki manual).
- `update_maintenance_plan_timestamp()` — `updated_at`.
- `notify_ml_on_completion()` — nariyad `completed` bo'lganda `pg_notify('work_order_completed', …)`.
- `docs/WEBHOOK_SETUP.md`dagi muqobillar: `call_ml_webhook()` + `pg_net`, Supabase Database Webhook yoki Edge Function.

### 8.5 Indekslar
`scripts/analytics_indexes.sql`: `fixed_assets` (type, series, depot, status, type+status, failure_probability qisman), `work_orders` (created_at, status, section, depot, unit, section+status+created_at, unit+repair_kind, faol statuslar uchun qisman), `ai_insights` (created_at, equipment_id va h.k.).

### 8.6 RLS
Deyarli barcha jadvallarda siyosatlar `USING (true)` — **anon kalit bilan hamma narsani o'qish/yozish/o'chirish mumkin** (qarang 15-bo'lim).

---

## 9. Modullar (sahifalar) bo'yicha batafsil

### 9.1 Kirish — `/auth/login`
Email + parol, "ko'rsatish/yashirish" tugmasi, xato xabari, mavzu almashtirgich. Muvaffaqiyatli kirishdan so'ng `/dashboard`.

### 9.2 Dashboard — `/dashboard`
`api.dashboard.getSummary({ section })`; `work_orders` va `fixed_assets` hodisalarida Realtime orqali qayta yuklanadi. Kartochkalar: jami ОС, ekspluatatsiyada, ТО/ta'mirda, ochiq nariyadlar (pending+in_progress). Donut (park holati), 6 oylik nariyad trendi, ta'mir turlari (top-7), seriyalar bo'yicha taqsimot (top-8), yaqinlashayotgan ТО (pending + `date_start`), oxirgi 5 nariyad.
Qoida: ochiq nariyadi bor `operational` ОС "на ТО" hisoblanadi.
> ⚠ "Готовность по месяцам" grafigi **simulyatsiya**: joriy foizga `sin()` bilan sun'iy tebranish qo'shiladi, haqiqiy tarix emas.

### 9.3 Asosiy vositalar — `/dashboard/os`
Ro'yxat (sahifa o'lchami 50, server tomonda filtr/qidiruv: nom, tur, depo, status), 6 ta sanagich, qo'shish/ko'rish-tahrirlash/o'chirish modallari, Wialon holati (online/sinxron vaqti). `api.fixedAssets.*` + Realtime.

### 9.4 ТО va ремонты — `/dashboard/maintenance`
Oy bo'yicha **Gantt diagrammasi** va jadval ko'rinishi; filtrlar: status (upcoming/in_progress/completed/overdue), ТО turi, uskuna nomi. Bildirishnoma "qo'ng'irog'i" (maks. 100 ta, takrorlarsiz) va toast'lar. Gantt'dan "Tez nariyad" (`QuickOrderModal`) — keyingi ТО chegarasi va qolgan km ko'rsatiladi. Grafik serverda (`/maintenance-schedule?month=YYYY-MM`) yig'iladi.
> ⚠ `QuickOrderModal` `supabase.from("work_orders").insert(...)` chaqiradi, lekin faylda `supabase` **import qilinmagan** — nariyad yaratish ishlamaydi / build xatosi.

### 9.5 Nariyad-buyurtmalar — `/dashboard/work-orders`
Eng katta modul. Yorliqlar: Открытые / Запланировано / Выполняется / Выполнено; qidiruv (id, birlik, tavsif, uchastka, uskuna); filtr: uchastka, uskuna, birlik turi. Master faqat o'z uchastkasini ko'radi.
- **Yaratish** (`CreateWorkOrderModal`): birlik turi (lokomotiv/teplovoz/vagon) → seriya → birlik (ОС'dan), ish turi (Плановое/Внеплановое/Ремонтное/Аварийное), ta'mir turlari (`RepairItemsModal`), TMC qatorlari (`TmcModal`), ijrochi (employees), mas'ul, prioritet (critical/high/normal/low), rejalashtirilgan sana-vaqt, tavsif. Majburiy: birlik, ish turi, kamida bitta ta'mir turi, tavsif, ijrochi.
- **ID formati**: `НЗ-YYYYMMDD-HHMMSS` (klientda yaratiladi).
- **TMC normativ nazorati**: uchastka normativlari `api.nomenclatureNorms.list` orqali; miqdor normadan **>20%** oshsa ogohlantirish ("Превышение норматива на X%"), `qty × avg_price` bilan taxminiy narx. `ТО-2`/`ПТОЛ` tanlanganda `api.workTypeTemplates` bo'yicha qatorlar avtomatik to'ldiriladi.
- **Zaxira (fallback)**: DB'da ish turlari/shablonlar bo'lmasa, kodga yozilgan `tmcCatalog` (≈40 pozitsiya, `МТР-…` raqamlari) va `tmcTemplates` (ТО-1…КР, ВНП, vagon turlari ТО-1В…ВНВ) ishlatiladi.
- **Ko'rish/tahrirlash** (`ViewEditOrderModal`): `completed` — faqat o'qish; status o'zgarsa va `completed` bo'lsa `closed` = bugungi sana.
- URL: `?create=1&unit=…&section=…` (Gantt'dan) formani oldindan to'ldirib ochadi.
- Ma'lumot: `work_orders`, `fixed_assets`, `employees`, `work_types` — **Supabase'dan**; yozish ham Supabase'ga.

### 9.6 ТМЦ — `/dashboard/tmc`
Ikki qism: (1) **Требования-накладные** ro'yxati (draft/issued/closed sanagichlari, bosib chiqarish — `PrintDocument`, `window.print()`: tashkilot jadvali, TMC jadvali, imzolar); (2) **Nomenklatura spravochnigi** — qidiruv, bo'lim filtri (admin/ustada `effectiveSection` bo'yicha avto-filtr), qo'shish/tahrirlash/o'chirish. Birliklar: шт., кг, л, м, м², рул., кан., уп., к-т, ед.

### 9.7 Hisobotlar — `/dashboard/reports`
Uch turi: Наряд-заказы, Основные средства, ТМЦ документы. Filtrlar, jadval, **CSV eksport** (UTF-8 BOM bilan, Excel'da kirill ochilishi uchun).

### 9.8 Tahlil — `/dashboard/analytics`
KPI: jami nariyadlar, haqiqiy va normativ xarajat, o'rtacha og'ish, >20% oshishlar soni. Grafiklar: uchastkalar bo'yicha xarajat, tejash ulushi (pie), og'ishlar, oylik trend, ish turlari bo'yicha xarajat/pробег. **AI bloklari**: park salomatligi (`fleet_health`), AI-prognozlar (risk >0.3 bo'lgan top-5 ОС), AI-bildirishnomalar (`ai_insights` so'nggi 10). Barcha so'rovlar `Promise.all` bilan parallel; ma'lumot Supabase view'laridan.

### 9.9 Foydalanuvchilar — `/dashboard/admin/users`
Faqat admin (boshqalar uchun "ruxsat yo'q" ekrani). Qidiruv, rol sanagichlari, yaratish (parol ≥6 belgi), tahrirlash (ism, rol, uchastka), Realtime yangilanish.

### 9.10 Справочники — `/dashboard/directories`
- **Работники** — tabel raqami (unique), F.I.Sh., lavozim, uchastka, joylashuv (`location_id`).
- **Участки** — qo'shish/o'chirish (`api.sections`).
- **Виды работ и ТМЦ** — ish turi (kod, nom, tavsif, birlik turi), ichki vazifalar, TMC shablonlari (`work_types`, `work_subtasks`, `work_type_tmc`, `nomenclature` bilan).
- **Интервалы ТО** — kod, nom, `interval_km`, `interval_days`, ОС turlari, faol/nofaol.
- **Номенклатура ТМЦ** — `/dashboard/tmc` ga havola.

---

## 10. Biznes qoidalar va formulalar

**ТО/ремонт turlari (lokomotiv):** ТО-1, ТО-2, ТО-3, ТР-1, ТР-2, ТР-3, СР (o'rta), КР (kapital), ВНП (rejadan tashqari).
**Vagon:** ТО-1В, ТО-2В, ТОР, ТОВ, ДР (depo ta'miri), КРВ, ВНВ.

**Nariyad status oqimi (UI):** `pending → in_progress → completed` (+ UI'da `overdue` belgisi). Backend servisi esa `draft → planned → in_progress → completed/cancelled` ni talab qiladi (nomuvofiq — 15-bo'lim).

**Dashboard KPI:** `availability = operational / total`; `operational` — status `operational` va ochiq nariyadi yo'q.

**Normativdan og'ish (DB view):** `(fakt − norma) / norma × 100`; `>20%` — "перерасход" (overrun). `cost_savings = norm_cost − actual_cost`.

> ⚠ **Uch xil ТО-chegara tizimi bir vaqtda mavjud va bir-biriga zid:**
> 1. `auto_schedule_maintenance` triggeri va `/api/mileage` route: 5 000 … 1 600 000 km, sutkasiga 200 km.
> 2. `maintenance_intervals` jadvali (standart qiymatlar): ТО-1 = 50 km, ТО-2 = 90, ТО-3 = 200, ТР-1 = 500, ТР-2 = 1 000, ТР-3 = 2 000, СР = 5 000, КР = 10 000; grafik taxmini sutkasiga 200 km (SQL view) yoki 10 km (`/api/maintenance-schedule`).
> 3. Wialon receiver: pробег ≥ 90 bo'lsa qat'iy `ТО-90` rejasi yaratadi.
> Qaysi biri "haqiqat manbai" ekanini bitta qilib belgilash kerak.

---

## 11. API

### 11.1 Next.js route'lari (`/app/api/…`)
| Yo'l | Metod | Vazifa |
|---|---|---|
| `/api/v1/auth/login` | POST | Supabase login + profil |
| `/api/v1/auth/me` | GET | Bearer token → profil |
| `/api/mileage` | GET | Barcha lokomotiv/teplovozlar uchun 8 ta ТО bashorati, `due/overdue` bo'lsa `maintenance_plan` upsert |
| `/api/mileage` | POST | `{asset_id, mileage}` — pробegni yangilab, bashorat va ogohlantirishlar qaytaradi |
| `/api/mileage/history` | GET | `?asset_id&days=30&limit=100` — grafik uchun tarix |
| `/api/maintenance-plan` | GET / POST / PATCH | ТО rejalari (status, `urgency`, summary) |
| `/api/maintenance-schedule` | GET | `?month=YYYY-MM` — nariyadlar + rejalar + interval-hisoblangan kelajak ТО |
| `/input` | GET/POST | Faqat yo'l-yo'riq xabari (Wialon uchun haqiqiy port 3002) |

### 11.2 FastAPI (`/api/v1`, `lib/api.ts` kutadigan)
`/auth/{login,logout,me,refresh}`, `/sections`, `/departments`, `/nomenclature`, `/fixed-assets`, `/work-orders`, `/tmc-documents`, `/nomenclature-norms`, `/work-type-templates`, `/maintenance-schedule`, `/dashboard/summary`, `/employees`, `/work-types`, `/health` (ildizda), WebSocket `/ws`.

**Umumiy qoidalar:** ro'yxat javobi `Paginated<T> = {items,total,limit,offset}`; `limit` 1–1000 (standart 50); `sort_by` ruxsat etilgan maydonlar ro'yxati bilan (`created_at, updated_at, date_start, date_end, status, priority`); xatolar `{detail}`; 204 — bo'sh javob. Nariyadlar filtri: `status, section_id, department_id, fixed_asset_id, date_from, date_to, q`. `lib/api.ts` da `fetchAllPaginated()` yordamchisi bor.

**Arxivdagi backend routerlari:** `work_orders` (GET list/one, POST, PATCH), `employees` (GET), `work_types` (GET), `maintenance_intervals` (GET), `maintenance_schedule` (GET). Qolganlari (sections, departments, nomenclature, fixed-assets, tmc-documents…) arxivda yo'q.

---

## 12. Wialon integratsiyasi (pробег)

`server/wialon-receiver.js` — alohida Express server:
- Endpointlar: `POST/GET /input`, `GET /health`, `GET /` (test sahifasi: "Тест GET/POST"). Port `WIALON_PORT` (standart **3002**), `0.0.0.0`.
- Kiruvchi format (JSON/form/matn): birlik — `i | unitId | unit_id | id | uid | unit`, nom — `nm | name | unit_name | na`, pробег — `mileage | odo | odometer | km | total_odometer | total_km | run | …`, tezlik — `speed | spd | vel`.
- **Moslashtirish** (`findAsset`): `wialon_id` → nom → nomdagi 2–4 xonali raqam (`ПЭ-2У 111` → `111`, `094` ↔ `94` ↔ `#094`). `fixed_assets` keshi 60 soniya.
- **Saqlash**: `wialon_last_sync`, `wialon_speed`, `wialon_online=true`; pробег > 0 bo'lsa `mileage` (Wialon — "haqiqat manbai", pробег kamaysa ham yoziladi, logda qayd etiladi), `mileage_history` ga yozuv, ≥90 bo'lsa `ТО-90` rejasi.
- Faqat `locomotive`/`diesel` turidagi ОС'lar kesh'ga olinadi.
- `server/check-db.js` — pробeglari bor 10 ta ОС holatini konsolga chiqaradi.
- `scripts/test-wialon-server.js`, `scripts/wialon_integration.sql` — test va migratsiya.

> ⚠ `package.json`da `express` bog'liqligi va `"wialon"` skripti **yo'q** (README/komment `npm run wialon` deydi). Izoh sarlavhasida port 3001 yozilgan, kodda 3002; `next start` esa 3001 da — chalkashlik.

---

## 13. ML / AI moduli

Fayl: `services/ml_engine.py` (+ `scripts/anomaly_detection.py` — qo'lda tahlil hisoboti).

**Ishga tushirish:** `--analyze` (butun park), `--work-order <ID>` (bitta nariyad), `--serve --port 5000` (Flask). Flask endpointlari: `POST /webhook/work-order-completed`, `POST /analyze`, `GET /health`. Nariyad `pending/in_progress → completed` bo'lganda Supabase webhook yoki `pg_notify` orqali chaqiriladi (`docs/WEBHOOK_SETUP.md` — 4 usul).

**1) TMC sarf anomaliyasi** (nariyad yopilganda): shu `repair_kind + section` bo'yicha tarixiy (≤200 ta) umumiy miqdor → o'rtacha/std. Kamida 3 ta tarix kerak. Anomaliya: `z-score > 2.0` **yoki** `|og'ish| > 30%`. Jiddiylik: `critical` (og'ish >50% yoki z>3), `high` (>30% yoki z>2.5), aks holda `medium`. `probability = min(z/4, 1)`. Tavsiya matni og'ish yo'nalishiga qarab (nomaqbul sarf / tejash sifati / tanlab tekshiruv).
**2) Nosozlik prognozi (RUL):** birlikning yopilgan nariyadlari (≥3) orasidagi kunlar → `LinearRegression` bilan keyingi interval trendi → `failure_prob = 1 − exp(−kunlar_oxirgi_ТО_dan / o'rtacha_interval)`; bashoratiy km = qolgan_kun × (5 000 / o'rtacha_interval). Chegaralar: yuqori ≥0.7, o'rta ≥0.4; qolgan km <500 bo'lsa `critical`. Past xavf uchun insight yaratilmaydi.
**3) Health score (0–100):** `(1 − p) × 100 − min(anomaliyalar_30kun × 5, 20) − min(ТО'siz_kunlar/30 × 5, 15)`.
Natijalar `ai_insights` ga, ML maydonlari `fixed_assets` ga yoziladi. `IsolationForest` (contamination 0.1) yordamchi funksiya sifatida bor, asosiy oqimda z-score ishlatiladi.

> ⚠ Docstring'da `--listen` rejimi tilga olingan, lekin kodda yo'q. `analyze_all_equipment` faqat `locomotive` va `wagon`ni ko'radi (`diesel` tushib qoladi).

---

## 14. Skriptlar (`scripts/`)

| Fayl | Vazifasi |
|---|---|
| `import_nomenclature.py` | Excel (`ПТОВ.xlsx`, `ПТОЛ ТО-2.xlsx`, `ЭЛ_ДЕПО.xlsx`, `ВРП.xlsx`) → `departments` + `nomenclature`; 100 tadan partiyalar, upsert `(department_id,name)`; papka yo'li `excel_folder.txt` / argument / `EXCEL_BASE_DIR` |
| `import_maintenance_history.py` | Excel tarixi → `maintenance_log` (ustun nomlarini avto-aniqlash, `--folder`) |
| `seed_nomenclature_norms.py` | Test normativlarni tasodifiy to'ldirish (ТО-1…КР) |
| `anomaly_detection.py` | `maintenance_log`/`work_orders`dan uchastka×pozitsiya bo'yicha IsolationForest + N-sigma, zarar hisobi (50 000 so'm/birlik), konsol hisobot va CSV |
| `import-assets.mjs`, `check-assets.mjs`, `read-excel.mjs` | ОС importi/tekshiruvi/Excel o'qish (Node) |
| `cleanup_test_data.sql` | `WO-ML-%` nariyadlari, test ОС (`TEP70-0325`, `Wagon-%`…) va AI-insight'larni o'chiradi |
| `*_schema.sql`, `analytics_indexes.sql`, `executive_summary_view.sql`, `wialon_integration.sql`, `work_orders_mileage.sql`, `add_departments_color.sql`, `fix_departments_nomenclature_rls.sql` | Migratsiyalar (Supabase SQL Editor'da bajariladi) |

Uchastkalar: **ПТОВ, ПТОЛ, ВРП, ЭЛ_ДЕПО** (Электровозное депо).

---

## 15. Frontend arxitekturasi

- **Providers** (`lib/providers.tsx`): `ThemeProvider` (kalit `toir-theme`) → `ThemeClassSync` → `AuthProvider`.
- **Mavzular** (6 ta, `data-theme`): Арктика (light), Полночь (dark), Океан, Изумруд, Аметист (light variantlar), Графит (dark). `ThemeSwitcher` login va header'da.
- **Kontekstlar/hook'lar:** `useAuth`, `useSectionView`, `useSections` (uchastkalar + `getSectionId`), `useRealtime(handler)` (singleton WebSocket, 5 soniyada qayta ulanish), `use-toast`, `use-mobile`.
- **`lib/supabase-utils.ts`:** `withTimeout`, `safeFetch`, `parallelFetch`, `batchLoadRelated`, `createQueryController`.
- **Optimizatsiya** (`next.config.mjs`): `optimizePackageImports`, `recharts` va `radix-ui` uchun alohida chunk'lar, AVIF/WebP, `poweredByHeader:false`, `/os → /dashboard/os` redirect; `loading.tsx` skeletonlari (dashboard, analytics, work-orders, os).
- **Adaptivlik:** mobil uchun siljiydigan sidebar (`md:` breakpoint), kenglik 272px.
- Hujjat `docs/PERFORMANCE_AUDIT.md` (19.02.2026): Analytics 4 s+ → maqsad 1–1.5 s; waterfall so'rovlar `Promise.all`ga o'tkazilgan.

---

## 16. O'rnatish va ishga tushirish

**Muhit o'zgaruvchilari**

| Fayl | O'zgaruvchi | Izoh |
|---|---|---|
| `.env.local` (frontend) | `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase |
| | `NEXT_PUBLIC_API_URL` | FastAPI bazasi (standart `http://localhost:8000/api/v1`) |
| | `SUPABASE_SERVICE_ROLE_KEY` (ixtiyoriy) | Next route'lari birinchi navbatda shuni, bo'lmasa anon kalitni ishlatadi |
| | `WIALON_PORT` (ixtiyoriy) | Standart 3002 |
| `.env` (backend) | `DATABASE_URL` | `postgresql+asyncpg://user:pass@host:5432/toir` |
| | `JWT_SECRET`, `JWT_ALGORITHM` (HS256), `ACCESS_TOKEN_EXPIRE_MINUTES` (1440) | |
| | `CORS_ORIGINS` | Standart: `localhost:3000`, `localhost:3001` |

**Frontend**
```bash
pnpm install        # yoki npm install
pnpm dev            # http://localhost:3000
pnpm build && pnpm start   # production: port 3001
```
**Backend**
```bash
docker compose up -d postgres            # Postgres 16, schema.sql avtomatik yuklanadi
cd backend && pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
curl http://localhost:8000/health        # {"status":"ok","service":"toir-backend"}
```
**Boshqalar**
```bash
node server/wialon-receiver.js                       # Wialon qabul qiluvchi (port 3002)
python services/ml_engine.py --analyze               # ML tahlil
python services/ml_engine.py --serve --port 5000     # ML webhook
python scripts/import_nomenclature.py "<papka>"      # Excel importi
```
Supabase uchun SQL'larni tartib bilan bajaring: `supabase_schema.sql` → `sections/departments_nomenclature/profiles/employees/work_types` sxemalari → `wialon_integration.sql` → `maintenance_plan_schema.sql` → `maintenance_log_schema.sql` → `nomenclature_norms_schema.sql` → `ai_insights_schema.sql` → `work_orders_mileage.sql` → `executive_summary_view.sql` → `analytics_indexes.sql`.

---

## 17. Ma'lum muammolar va texnik qarz

### 🔴 Xavfsizlik (birinchi navbatda)
1. **Maxfiy ma'lumotlar kodda**: `services/ml_engine.py`, `scripts/anomaly_detection.py`, `import_maintenance_history.py`, `seed_nomenclature_norms.py` ichida Supabase URL va kalit qattiq yozilgan; `test-auth.js`da Supabase URL, kalit va **admin login/paroli** ochiq. `.env.local` ham arxivga tushgan. Kalitlarni **almashtiring (rotate)**, parolni o'zgartiring, skriptlarni `os.environ` ga o'tkazing. (Ikki xil Supabase loyihasi ko'rinadi — qaysi biri joriy ekanini aniqlang.)
2. **RLS ochiq** (`USING (true)`): `profiles_all` siyosati bilan istalgan kishi o'z `role`ini `admin` qilib qo'yishi mumkin; hamma jadval anon kalit bilan o'zgartiriladi.
3. **Faqat UI himoyasi**: `middleware.ts` bo'sh; rol tekshiruvi sahifa darajasida.
4. **Wialon receiver autentifikatsiyasiz** va anon kalit bilan yozadi; ML webhook uchun maxfiy token faqat hujjatda tavsiya.
5. `JWT_SECRET` standart qiymati kodda (`config.py`) — productionda majburiy almashtirilsin.
6. Admin yaratishda klientdan `supabase.auth.signUp` ishlatiladi (service role bilan server tomonda qilish to'g'riroq).
7. `.vscode/settings.json`da `claudeCodeChat.permissions.yoloMode: true` — repoda qoldirmaslik maqsadga muvofiq.

### 🟠 Funksional nomuvofiqliklar
- **Auth ikkiga bo'lingan**: kirish Supabase orqali, lekin `lib/api.ts` FastAPI tokenini xotirada izlaydi (`api.auth.login` hech qachon chaqirilmaydi) → FastAPI'ga o'tgan sahifalar `POST /auth/refresh` ga tushadi. Ko'rinishicha, token ko'prigi (Supabase JWT'ni FastAPI qabul qilishi yoki yagona login) hali qurilmagan — tekshirish kerak.
- `dependencies.require_role(required_role)` **bitta** rol qabul qiladi, routerlar esa bir nechta rol uzatadi (`require_role(admin, management, …)`); `..security.dependencies` yo'li ham ildizdagi `dependencies.py` bilan mos emas.
- `maintenance/page.tsx` — `supabase` import qilinmagan (9.4).
- `schema.sql` `users.role VARCHAR default 'user'` ↔ `models/user.py` `Enum(admin, operator, master, management)` — mos emas.
- Nariyad statuslari: UI/DB `pending…` ↔ backend `draft/planned…`.
- `departments` va `sections` — bir-biriga o'xshash ikki spravochnik; nomlari ham farq qiladi (`"Участок ПТОВ"` ↔ `"ПТОВ"`), view'lar esa nom bo'yicha JOIN qiladi.
- `fixed_assets.mileage` turi har xil (`text`/`numeric`); `last_maint` ↔ `last_maint_date` nomlari.
- `DashboardSummary` tipi (`kpi, fleetStatus…`) bilan sahifa o'qiydigan `summary.orders/assets` mos emas.
- Uchta ТО-chegara tizimi (10-bo'lim).
- ML: `diesel` e'tiborga olinmaydi; `--listen` yo'q.
- Dashboard "Готовность" grafigi — sun'iy (9.2).
- Yo'qolgan `express` bog'liqligi va `wialon` skripti (12-bo'lim); `package.json` nomi `my-v0-project` (v0.dev shablonidan).
- Ikki lock-fayl (`pnpm` + `npm`); `tsconfig.tsbuildinfo` kabi build artefaktlari arxivda.
- `README.md` aralash: bir qismi frontend/Docker, boshqasi `backend/` bo'yicha ingliz tilida; `docker-compose.yml` `./backend` va `./postgres/schema.sql` ga tayanadi (arxivda yo'q).

### 🟡 Sifat
- Katta fayllar: `work-orders/page.tsx` (2 114), `maintenance/page.tsx` (1 588), `analytics/page.tsx` (1 051) — komponentlarga bo'lish tavsiya.
- Testlar yo'q (`test-auth.js` qo'lda skript); CI/CD yo'q.
- `lib/api.ts`da izohga olingan eski kod bloklari.
- "Master faqat o'z uchastkasi" filtri klient tomonida (`orders.filter`) — serverda ham majburlanishi kerak.

---

## 18. Tavsiya etilgan yo'l xaritasi

1. **Xavfsizlik**: kalitlarni almashtirish, `.env`ga ko'chirish, RLS'ni rolga bog'lash, `middleware.ts`da sessiya/rol tekshiruvi.
2. **Backend'ni tiklash**: asl `backend/` papkasini repoga qaytarish; ildizdagi/yassilangan `.py` fayllarni `app/{models,schemas,services,routers,security}` ga joylash; Alembic migratsiyalarini yozish.
3. **Yagona auth**: Supabase yoki FastAPI JWT'dan birini tanlash va `lib/auth-context` ↔ `lib/api` ni bog'lash.
4. **Sxemalarni birlashtirish**: bitta `work_orders`/`fixed_assets` sxemasi, bitta status lug'ati, bitta ТО-chegara manbai (`maintenance_intervals`).
5. **Qolgan modullarni ko'chirish**: nariyadlar, tahlil, hisobotlar, foydalanuvchilar, spravochniklar; Wialon va ML'ni FastAPI/Postgres'ga ulash; WebSocket `/ws` ni backend'da amalga oshirish.
6. **Sifat**: katta sahifalarni bo'lish, test va CI qo'shish, haqiqiy "готовность" tarixi.

---

## 19. Glossariy

| Atama | Ma'nosi |
|---|---|
| ТОИР | Техническое обслуживание и ремонты |
| ОС | Основные средства (asosiy vositalar) |
| ТМЦ | Товарно-материальные ценности |
| НЗ / наряд-заказ | Ish buyrug'i (ta'mir/ТО topshirig'i) |
| Требование-накладная | TMC omborxonadan chiqarish hujjati |
| ТО-1/2/3 | Texnik xizmat ko'rsatish №1/2/3 |
| ТР-1/2/3 | Joriy ta'mir №1/2/3 |
| СР / КР | O'rta / kapital ta'mir |
| ВНП / ВНВ | Rejadan tashqari ta'mir (lokomotiv / vagon) |
| ТОР / ТОВ | Joriy otsepka (ajratib) ta'miri |
| ДР / КРВ | Depo ta'miri / vagon kapital ta'miri |
| ПТОВ, ПТОЛ, ВРП, ЭЛ_ДЕПО | Uchastkalar (vagon/lokomotiv TXK punktlari, vagon-ta'mir, elektrovoz deposi) |
| RUL | Remaining Useful Life — qolgan xizmat resursi |
| Wialon | GPS-monitoring platformasi (pробег va tezlik manbai) |
| Мастер / Оператор / Администратор | Foydalanuvchi rollari |
