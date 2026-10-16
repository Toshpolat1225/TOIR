# TOIR — loyiha tavsifi

## 1. Maqsad

TOIR lokomotiv, teplovoz va vagonlar uchun texnik xizmat, ta'mirlash, ehtiyot qismlar,
asosiy vositalar, hisobot va tahlilni boshqaradi. Interfeys rus tilida; valyuta — so'm.

## 2. Arxitektura

- Frontend: Next.js 15 App Router, React 19, TypeScript, Tailwind, Radix UI va Recharts.
- Backend: FastAPI, Python 3.12, SQLAlchemy async, asyncpg va Alembic.
- Database: PostgreSQL 16. Kanonik sxema `postgres/schema.sql`; evolyutsiya `backend/alembic/`.
- Frontend API so'rovlari `lib/api.ts` orqali `/api/v1` ga boradi.
- Realtime: Postgres `LISTEN/NOTIFY` backend listener'iga, so'ng autentifikatsiyalangan `/ws` ga uzatiladi.
- Wialon telemetriyasi FastAPI `POST/GET /api/v1/wialon/input` orqali qabul qilinadi.
- Nginx/Caddy, CI va production Docker frontend hali keyingi infratuzilma ishlaridir.

## 3. Papkalar

```text
app/                    Next.js sahifalari va UI
backend/app/            FastAPI routers, services, repositories, schemas, models
backend/alembic/        Database migratsiyalari
backend/scripts/        API end-to-end tekshiruv skriptlari
components/, hooks/     Umumiy frontend komponent va hook'lar
lib/api.ts              Backend API klienti va frontend turlari
lib/use-realtime.ts     Autentifikatsiyalangan WebSocket klienti
postgres/schema.sql     Yangi o'rnatishlar uchun kanonik schema
scripts/                PostgreSQL orqali ishlaydigan ma'lumot utilitalari
```

## 4. Auth va rollar

Backend JWT access token qaytaradi; frontend access tokenni xotirada saqlaydi. Refresh token
`HttpOnly`, `SameSite=Lax` cookie'da bo'ladi. 401 javobida klient bir marta refresh qilib,
so'rovni takrorlaydi.

Rollar: `admin`, `operator`, `master`, `management`. Master scope'i serverda majburlanadi;
klient filtri ruxsat nazorati o'rnini bosmaydi.

## 5. Asosiy biznes qoidalari

- Ish buyurtmasi statusi: `pending -> in_progress -> completed | cancelled`.
- `overdue` statusi saqlanmaydi; muddati o'tgan ochiq buyurtma API javobida hisoblanadi.
- Ish buyurtmasi raqami backend tomonidan `НЗ-YYYYMMDD-HHMMSS` shaklida yaratiladi.
- Ish buyurtmasi ta'mir turlari va TMC qatorlari bilan bir DB tranzaksiyasida yoziladi.
- Nomenklatura normasi >20% oshsa ogohlantirish chiqadi; bu buyurtmani bloklamaydi.
- ТО chegaralarining yagona manbai — `maintenance_intervals`; hardcoded kilometrlik intervallar yo'q.
- Probeg yangilanganda tarix yoziladi; jadval rejasi backend servis qatlamida yangilanadi.

## 6. Ma'lumotlar modeli

Asosiy jadvallar:

| Guruh | Jadvallar |
|---|---|
| Tashkilot va foydalanuvchi | `departments`, `sections`, `employees`, `users`, `refresh_tokens` |
| Park va telemetriya | `fixed_assets`, `mileage_history`, `wialon_settings` |
| Ish turlari va intervallar | `work_types`, `work_subtasks`, `maintenance_intervals` |
| TMC va normalar | `nomenclature`, `nomenclature_norms`, `work_type_templates` |
| Ish buyurtmalari | `work_orders`, `work_order_repairs`, `work_order_items` |
| Rejalash va tahlil | `maintenance_plan`, `maintenance_settings`, `maintenance_log`, `ai_insights` |
| Hisobotlar | `tmc_documents`, `tmc_document_items`, analytics view'lari va readiness snapshots |

Jadval va FK ta'riflarining manbai `postgres/schema.sql`; yangilanishlar uchun Alembic migratsiyalari
ishlatiladi. Eski ma'lumotlar avtomatik ko'chirilmaydi.

## 7. API

Backend routerlari `backend/app/routers/` da. Faol API guruhlari:

- Auth va foydalanuvchilar: `/api/v1/auth/*`, `/api/v1/users`.
- Spravochniklar: `/sections`, `/departments`, `/employees`, `/work-types`,
  `/maintenance-intervals`, `/nomenclature`, `/nomenclature-norms`.
- Asosiy vositalar: `/fixed-assets`, mileage va mileage history.
- Nariyadlar: `/work-orders`, `/work-orders/norm-check`,
  `/work-orders/template-items`.
- Rejalash: `/maintenance-schedule`, `/maintenance-plan`, `/maintenance-settings`.
- Hisobot va tahlil: `/dashboard/summary`, `/analytics/*`, `/reports/*`.
- Wialon qabul qilish: `/wialon/input`; health: `/health`; realtime: WebSocket `/ws`.

Ro'yxatlar `{items,total,limit,offset}` shaklida. `limit` 1–1000, standart 50.
`sort_by` whitelist bilan tekshiriladi. API xatolari `{detail}`; o'chirish javobi 204.
TMC hujjatlari sxemada mavjud; ularning alohida CRUD routeri keyingi ish doirasida.

## 8. Frontend sahifalari

- `/auth/login` — backend auth.
- `/dashboard` — KPI, readiness grafigi va ochiq buyurtmalar.
- `/dashboard/os` — asosiy vositalar va telemetriya.
- `/dashboard/work-orders` — nariyadlar.
- `/dashboard/maintenance` — ТО/ТР rejasi.
- `/dashboard/tmc` — nomenklatura va TMC hujjatlari UI.
- `/dashboard/directories/*` — bo'lim, uchastka, xodim, ish turi va interval spravochniklari.
- `/dashboard/analytics`, `/dashboard/reports` — tahlil va hisobotlar.
- `/dashboard/admin/users` — foydalanuvchilar.

Realtime obunalar dashboard (`work_orders`, `fixed_assets`), ОС (`fixed_assets`),
work-orders (`work_orders`) va admin users (`users`) sahifalarida ishlatiladi.

## 9. TMC normalari va import

`nomenclature.department_id` bo'limga tegishli; `nomenclature_norms` yozuvi nomenklatura,
bo'lim va ish turini birlashtiradi. Shablonlar `work_type_templates` jadvalidan olinadi.
`scripts/import_nomenclature.py` va `scripts/anomaly_detection.py` PostgreSQL'ga
`DATABASE_URL` muhit o'zgaruvchisi orqali ulanadi; kalit yoki endpoint tokeni talab qilmaydi.

## 10. Boshlang'ich ma'lumot

`python -m app.cli seed-reference` buyrug'i bo'limlar, uchastkalar va ish turlarini idempotent
tarzda yaratadi. Maintenance interval qiymatlari avtomatik seed qilinmaydi.

## 11. Runtime sozlamalari

Backend `.env` sozlamalari `backend/app/core/config.py` orqali o'qiladi: PostgreSQL ulanish
maydonlari, JWT secret, CORS origin, Wialon ingest tokeni va API docs bayrog'i. Frontend
`.env.local` da `NEXT_PUBLIC_API_URL` bo'ladi. Excel va anomaliya skriptlari uchun `DATABASE_URL`
talab qilinadi; qiymatlarni terminal yoki chatga chiqarmang.

## 12. Tekshiruvlar va deploy

Frontend lokal tekshiruvi:

```powershell
npx tsc --noEmit
npm run build
```

Backend unit/E2E testlari tegishli Python 3.12 muhitida bajariladi. Real PostgreSQL migratsiyasi,
API, WebSocket va brauzer tekshiruvlari deployment muhitida foydalanuvchi ruxsati bilan qilinadi.

## 13. ML / AI moduli — keyingi vazifa

ML worker backend ichida hali amalga oshirilishi kerak. Rejalashtirilgan qoidalar:

- TMC sarf anomaliyasi: repair turi + uchastka bo'yicha ko'pi bilan 200 ta tarixiy yozuv;
  kamida 3 yozuv bo'lganda z-score >2 yoki og'ish >30% ni aniqlash.
- RUL: `LinearRegression` va `failure_prob = 1 - exp(-kunlar_oxirgi_ТО_dan/o'rtacha_interval)`;
  0.7/0.4 xavf chegaralari, qolgan masofa 500 km dan past bo'lsa critical.
- Health score: `(1-p)*100 - min(anomaliya_30kun*5,20) - min(ТО'siz_kunlar/30*5,15)`.
- Natijalar `ai_insights` va `fixed_assets` ga yoziladi; diesel aktivlari ham qamrab olinadi.
- Endpointlar: `POST /api/v1/ml/analyze` (admin), `GET /api/v1/ml/insights`.
