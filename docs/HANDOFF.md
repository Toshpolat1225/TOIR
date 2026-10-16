# TOIR — handoff

## Qoidalar

- "Ishladi" faqat shu sessiyada ishga tushirilgan tekshiruv natijasiga asoslanadi.
- Maxfiy qiymatlarni, `.env` va `.env.local` mazmunini ko'rsatma.
- Serverga SSH qilma va foydalanuvchi deploy qilmaguncha serverda tekshiruv o'tkazma.
- Backend sxemasi `postgres/schema.sql`; migratsiyalar `backend/alembic/` ichida.
- Python muhiti Python 3.12; backend runtime sinovlarini faqat tasdiqlangan muhitda o'tkaz.
- O'zgarishlarni tor doirada saqla; commit/push qilma.

## Arxitektura qarorlari

- Frontend: Next.js 15, TypeScript, npm.
- Backend: FastAPI, SQLAlchemy async, PostgreSQL 16.
- Auth: backend JWT; refresh cookie `HttpOnly`, access token brauzer xotirasida.
- Rollar: `admin`, `operator`, `master`, `management`; master scope serverda qo'llanadi.
- Narяд statuslari: `pending -> in_progress -> completed | cancelled`; overdue hisoblab chiqariladi.
- ТО intervallari uchun yagona manba `maintenance_intervals`.
- Realtime: Postgres `LISTEN/NOTIFY` → backend WebSocket `/ws`; access token birinchi xabarda.
- Wialon ma'lumotlari `/api/v1/wialon/input` ga yuboriladi.
- Eski ma'lumotlar ko'chirilmaydi.

## Hozirgi holat

| Qism | Holat |
|---|---|
| Auth, users, reference CRUD, nomenclature, assets, work orders | Kod yozilgan; real PostgreSQL tekshiruvi deployga bog'liq |
| Maintenance planner, analytics, reports | Kod va frontend API integratsiyasi yozilgan; real DB tekshiruvi deployga bog'liq |
| Realtime `/ws` | Backend listener, token tekshiruvi, obuna va master section-scope kodi yozilgan |
| P-T8 tozalash | Eski client, route, server/SQL skript, ML prototype va arxiv nusxalar olib tashlandi; Python utilitalari `DATABASE_URL` ishlatadi |
| ML worker | Keyingi ish; `docs/PROMPTS.md` va `PROJECT.md` 13-bo'limda talablar saqlangan |

## Tekshiruvlar

- Frontend: P-T8 da `npm run build` va undan keyingi `npx tsc --noEmit` o'tdi. Birinchi type-check eski `.next` route type'lari sabab yiqildi; build ularni yangiladi.
- Python: `scripts/import_nomenclature.py` va `scripts/anomaly_detection.py` sintaksis tekshiruvidan o'tdi.
- Repository source scan'da eski platform nomiga mos keluvchi fayl topilmadi (node_modules, `.next`, lock fayllari chiqarilgan).
- Importerlarning DB amali, PostgreSQL/Alembic, server HTTP/WebSocket va brauzer oqimi ishga tushirilmadi.

## Keyingi ish

P-T9: `docs/PROMPTS.md` dagi ML worker vazifasini bajarish. Avval Python 3.12 va backend dependency muhitini aniqlab, testlarni o'sha muhitda ishga tushir.
