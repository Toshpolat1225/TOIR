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
| ML worker | Servis, endpointlar va completed nariyad background tahlili yozildi; sintetik testlar qo'shildi |
| P-T10 production qotirish | Frontend standalone/non-root image, Caddy proxy, PostgreSQL login limiter migratsiyasi, backup/restore hujjati va CI workflow qo'shildi; deploy bajarilmadi |

## Tekshiruvlar

- Frontend: P-T8 da `npm run build` va undan keyingi `npx tsc --noEmit` o'tdi. Birinchi type-check eski `.next` route type'lari sabab yiqildi; build ularni yangiladi.
- Python: `scripts/import_nomenclature.py` va `scripts/anomaly_detection.py` sintaksis tekshiruvidan o'tdi.
- Repository source scan'da eski platform nomiga mos keluvchi fayl topilmadi (node_modules, `.next`, lock fayllari chiqarilgan).
- Importerlarning DB amali, PostgreSQL/Alembic, server HTTP/WebSocket va brauzer oqimi ishga tushirilmadi.
- ML sintetik unit testlari lokal Python muhiti bilan tekshirilishi kerak; PostgreSQL, endpoint va background DB oqimi deployment muhitiga bog'liq.
- P-T10 `npx tsc --noEmit`, `npm run lint` va `npm run build` Next.js 15.5.28 bilan lokalda muvaffaqiyatli; lint/build 2 ta React Hook dependency warning chiqardi. Compose/CI YAML parse qilindi.
- `npm audit` topgan kritik Next.js zaifligi 15.5.28 patchiga yangilash bilan bartaraf etildi. Production dependency auditi 2 ta (1 moderate, 1 high) qolgan advisoriyni ko'rsatmoqda; force-fix Next.js 16 major yangilanishini talab qiladi, shuning uchun qo'llanmadi. To'liq auditda jami 8 ta (1 moderate, 7 high) advisory bor; jumladan `xlsx` uchun hozir fix yo'q.
- Backend testlari Python 3.12 mavjud emasligi (lokal interpreter 3.14.7, backend paketlari o'rnatilmagan) sabab bajarilmadi. Docker CLI yo'q, shuning uchun Docker image va Compose runtime tekshiruvlari bajarilmadi.
- Production TLS, PostgreSQL migration/login limiter, backup rotation va tiklash amalda bajarilmadi; deploy va DB tekshiruvi foydalanuvchi ruxsatiga bog'liq.

## Keyingi ish

Production domen/DNS'ni `.env` ga kiritib, deploy ruxsati olingach TLS va backup-restore tekshiruvlarini bajarish.
