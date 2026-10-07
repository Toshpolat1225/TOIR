# TOIR — chatbot uchun promptlar

Qanday ishlatiladi:

1. Avval `docs/HANDOFF.md` va `PROJECT.md` ni repo ichiga qo'ying (agar yo'q bo'lsa).
2. Yangi chat/akkauntda **har doim P0 dan boshlang**, keyin vazifa promptini (P-T0, P-T1, ...) bering.
3. Bir vaqtda bitta vazifa. Bot "tayyor" desa, "qaysi buyruqni ishga tushirding va natijasi nima?" deb so'rang.
4. Har vazifadan keyin `git commit` qilib qo'ying, limit tugasa ham ish yo'qolmaydi.

---

## P0 — Har yangi sessiyaning birinchi xabari

```
Sen TOIR loyihasida senior Python/FastAPI + Next.js muhandisisan. Bu yangi sessiya: avvalgi
suhbat xotirang yo'q, hamma kontekst repoda.

Avval shu fayllarni TO'LIQ o'qi (o'zgartirma, hali kod yozma):
1) docs/HANDOFF.md  — holat, qarorlar, qoidalar, vazifalar ro'yxati
2) PROJECT.md       — tizimning to'liq tavsifi
3) postgres/schema.sql, docker-compose.yml, .env.example
4) backend/app/ ning hozirgi tuzilmasi (faqat fayllar ro'yxati va main.py)

Keyin 10 qatordan oshmaydigan xulosa yoz:
- loyiha maqsadi va qabul qilingan qarorlar,
- nima tasdiqlangan, nima faqat kod darajasida,
- hozirgi asosiy blokirovka.
Keyin menga "qaysi vazifadan boshlaymiz?" deb so'ra va men aytguncha kod o'zgartirma.

Qoidalar (HANDOFF.md 0-bo'lim bilan bir xil, qisqacha):
- "Ishladi/tasdiqlandi" faqat o'zing real bajargan buyruq natijasi bilan. Bajarilmagan narsani
  bajarildi deb yozma; oxirida har doim "nima tekshirilmadi" ro'yxatini ber.
- Supabase'ga tegma, uning dashboard'ida hech narsa qilma.
- Maxfiy qiymatlarni (parol, token, parolli URL, .env mazmuni) hech qayerga chiqarma.
- Windows/CRLF: str_replace yiqilsa faylni to'liq o'qib, to'liq qayta yoz; bir xil urinishni takrorlama.
- Lokal venv: Python 3.12.
- Ziddiyat yoki noaniqlik bo'lsa taxmin qilma, savol ber.
- Har fayl uchun to'liq yo'lni ko'rsat; "..." bilan qisqartirma.
```

---

## P-T0 — Runtime: Docker/PostgreSQL va real login (BIRINCHI vazifa)

```
Vazifa T0 (docs/HANDOFF.md 6-bo'lim). Maqsad: backend va PostgreSQL REAL ishlaydigan holatga
kelsin va admin login real DB bilan tasdiqlansin. Hozirgacha hamma narsa faqat xotira-DB
adapteri bilan sinalgan.

1) Muhitni aniqla (faqat o'qiydigan buyruqlar): `docker --version`, `docker compose version`,
   `psql --version`, `python --version`, 5432 va 8000 portlar holati. Natijani menga ko'rsat.
2) Docker bor bo'lsa: .env yarat (.env.example dan). JWT_SECRET va POSTGRES_PASSWORD ni
   `python -c "import secrets; ..."` bilan o'zing generatsiya qil, lekin QIYMATLARINI CHIQARMA —
   faqat "yozildi" de. CORS_ORIGINS=http://localhost:3000.
   `docker compose up --build -d`, `docker compose logs backend --tail 50` — xatolarni tuzat.
3) Docker YO'Q bo'lsa: to'xta va menga ayt. Men Docker Desktop o'rnataman yoki lokal PostgreSQL
   16 ga o'tamiz (HANDOFF.md 7-bo'lim, muqobil yo'l). O'zingdan Docker o'rnatishga urinma.
4) Alembic baseline real Postgres'da o'tishini tasdiqla: `alembic upgrade head`, keyin jadvallar
   soni (22 bo'lishi kerak, + alembic_version) va `schema.sql` bilan farqlarni tekshir
   (ustun nomlari, constraint, indekslar). Farq topsang — migratsiyani tuzat.
5) Admin yaratish: `python -m app.cli create-admin` (men parolni o'zim kiritaman; sen parol
   tanlama va standart admin yaratma).
6) Real HTTP: login → me → refresh (rotatsiya: eski refresh ishlamasin) → logout (refresh
   ishlamasin). 5 ta noto'g'ri parol → 429. is_active=false user kira olmasin.
7) Shu oqim uchun backend/tests/ ga pytest testlarini yoz (test DB: alohida baza yoki
   testcontainers) va ularni ishga tushir.

Oxirida jadval ber: har qadam → qaysi buyruq ishga tushirildi → natija. Tekshirilmaganlarni alohida yoz.
```

---

## P-T1 — Frontend auth: Supabase → FastAPI

```
Vazifa T1. Maqsad: kirish/sessiya to'liq FastAPI orqali bo'lsin, brauzerdan Supabase'ga hech
so'rov ketmasin.

Avval holatni aniqla (o'zgartirishdan oldin):
- `app/api/v1/auth/login/route.ts`, `app/api/v1/auth/me/route.ts` hozir nima qiladi? (oldingi
  sessiyada ularni FastAPI'ga yo'naltirish urinishi qisman muvaffaqiyatsiz bo'lgan)
- `lib/auth-context.tsx`, `lib/api.ts`, `lib/supabase.ts` da auth qanday ishlaydi?
Natijani menga ko'rsat.

Keyin:
1) Next.js'dagi `/api/v1/auth/*` route'larini O'CHIR (frontend to'g'ridan-to'g'ri backend'ga
   boradi, yoki next.config rewrites orqali `/api/v1/*` → backend).
2) `lib/api.ts`: login, refresh, logout, me. Access token xotirada. 401 bo'lsa bir marta
   refresh va so'rovni takrorlash. Refresh token: avval menga ikki variantni taqqosla —
   (a) httpOnly cookie (backend Set-Cookie, SameSite=Lax/Strict, Secure) — tavsiya,
   (b) xotira + sessionStorage — va men tanlayman. Tanlovsiz kod yozma.
3) `lib/auth-context.tsx`: `supabase.auth.*` va `onAuthStateChange` o'rniga api.ts.
   Profil maydonlari backend `/me` javobiga mos (section — endi section_id/nom, backend
   schemasiga qara).
4) Admin foydalanuvchilar sahifasi (`dashboard/admin/users`) — `supabase.auth.signUp` va
   `profiles` o'rniga backend Users API (list/create/update/reset-password).
5) Rol bo'yicha himoya: `middleware.ts` da token/rol tekshiruvi (hozir bo'sh).

Tekshiruv: brauzerda (Playwright yoki qo'lda) login → dashboard → refresh sahifa → logout.
Network tabida supabase.co ga so'rov YO'Q ekanini tasdiqla. `next build` (typescript
ignoreBuildErrors yoqilgan bo'lsa, buni menga ayt va alohida `tsc --noEmit` ishga tushir).
```

---

## P-T2 — Spravochniklar CRUD

```
Vazifa T2. Backend'da quyidagi resurslar uchun CRUD yoz: sections, departments, employees,
work-types (+ subtasks va work_type_templates), maintenance-intervals, nomenclature,
nomenclature-norms.

Arxitektura: routers → services → repositories → models; schemas/ (pydantic v2).
API qoidalari (PROJECT.md 11.2): /api/v1 prefiksi; ro'yxat {items,total,limit,offset}, limit 1–1000
(standart 50); sort_by faqat whitelist; xato {"detail":...}; o'chirish 204.
Ruxsatlar: o'qish — barcha autentifikatsiyalangan rollar (master uchun faqat o'z uchastkasi
bilan bog'liq ma'lumot); yozish — admin va operator; users/roles — faqat admin. Har endpointda
rol tekshiruvi aniq ko'rinsin.
Biznes qoidalar: employees.tab_number unique; nomenclature UNIQUE(department_id,name);
norms UNIQUE(nomenclature_id,department_id,work_type_id); maintenance_intervals da
interval_km yoki interval_days kamida bittasi. FK bo'yicha o'chirishda 409 va tushunarli xabar.

Har resurs uchun pytest (ruxsat, validatsiya, unique, pagination). Ishlayotgan Postgres'da ishga
tushir. Tayyor bo'lgach frontend'dagi tegishli sahifalar (directories, tmc nomenklatura)
`api.<resurs>.*` ga ko'chirilsin (supabase chaqiruvlari olib tashlansin).
Oxirida: nima ishga tushirildi/natija, nima tekshirilmadi.
```

---

## P-T3 — Fixed assets, mileage, Wialon ingest

```
Vazifa T3. 1) /fixed-assets CRUD (filtr: asset_type, status, section_id, depot, q; server tomonda
qidiruv; sahifa 50). 2) mileage_history: pробег o'zgarganda yozuv (manba wialon|manual).
3) Wialon qabul qilish: `POST/GET /api/v1/wialon/input` — talab: `WIALON_INGEST_TOKEN`
(Authorization header yoki query param; tokensiz/noto'g'ri → 401, vaqt-doimiy solishtirish).
Kiruvchi format PROJECT.md 12-bo'lim (unit id/nom, mileage/odo/..., speed). Moslashtirish:
wialon_id → nom → nomdagi raqam (ПЭ-2У 111 → 111; 094 ↔ 94 ↔ #094). Saqlash: wialon_last_sync,
wialon_speed, wialon_online, mileage (Wialon haqiqat manbai), mileage_history.
Qattiq yozilgan "ТО-90" mantig'i YO'Q — ТО-reja T5 da maintenance_intervals asosida.
Express receiver (server/wialon-receiver.js) o'rniga shu endpoint; eski receiver o'chiriladi.
Testlar: token tekshiruvi, moslashtirish variantlari, mileage_history yozilishi.
Frontend: /dashboard/os sahifasi shu API'ga (allaqachon qisman api.fixedAssets).
```

---

## P-T4 — Nariyad-buyurtmalar va TMC hujjatlari

```
Vazifa T4 (eng katta modul; PROJECT.md 9.5, 9.6 ni qayta o'qi).
Backend: /work-orders (list/get/create/update, status o'tishlari), /tmc-documents (+items).
- number: `НЗ-YYYYMMDD-HHMMSS` serverda generatsiya, unique; to'qnashuvda qayta urinish.
- repairs va items: work_order_repairs / work_order_items (JSONB yo'q). Nariyadni bitta so'rovda
  repairs+items bilan yaratish/yangilash (tranzaksiya).
- Status: pending → in_progress → completed | cancelled; teskari/noto'g'ri o'tish → 409.
  completed bo'lganda closed_at = hozir; completed nariyad tahrirlanmaydi.
- "overdue" saqlanmaydi: javobda is_overdue = status ochiq va date_end < hozir.
- Master FAQAT o'z uchastkasini ko'radi va yaratadi/yangilaydi — server majburlaydi (boshqa
  uchastka → 404). Ruxsatlar: yaratish admin/management/operator, yangilash + master (o'z uchastkasi).
- TMC norma nazorati: qty normadan >20% oshsa javobda warning (nomenclature_norms bo'yicha),
  narx = qty × avg_price. work_type_templates bo'yicha avto-to'ldirish endpointi.
- Filtrlar: status, section_id, department_id, fixed_asset_id, date_from, date_to, q.
- pg NOTIFY triggeri allaqachon schema'da — o'zgartirma.
Testlar: master izolyatsiyasi, status mashinasi, tranzaksiya (xato bo'lsa hech narsa yozilmasin),
norma ogohlantirishi.
Frontend: work-orders/page.tsx (2114 qator) ni ko'chirish bilan birga komponentlarga bo'l
(CreateWorkOrderModal, ViewEditOrderModal, RepairItemsModal, TmcModal alohida fayllar),
supabase chaqiruvlarini olib tashla. ID matn emas, uuid + number.
```

---

## P-T5 — ТО-reja xizmati

```
Vazifa T5. Backend servis qatlamida (DB trigger EMAS) ТО-rejalashtirishni yoz.
Manba: faqat maintenance_intervals (is_active, asset_types, interval_km/days, warn_percent).
Qattiq yozilgan 5000…1 600 000 km ro'yxati va "ТО-90" ishlatilmasin.
Mantiq: ОС pробег o'zgarganda (Wialon yoki manual) har faol interval uchun keyingi chegarani
hisobla; chegaraga warn_percent dan kam qolsa maintenance_plan yozuvini upsert qil
(UNIQUE(asset_id,interval_id,trigger_mileage)); scheduled_date = bugun + ceil(qolgan_km / kunlik_yurish).
Kunlik yurish taxmini endi bitta konfiguratsiya qiymati (env/settings), 200 va 10 aralashmasin —
qiymatni menga so'rab aniqla.
Endpoint: GET /maintenance-schedule?month=YYYY-MM (nariyadlar + rejalar + hisoblangan kelajak ТО,
status upcoming/in_progress/completed/overdue), GET/PATCH /maintenance-plan.
Nariyad completed bo'lganda tegishli reja completed bo'lsin.
Testlar: chegara hisobi, upsert takrorlanmasligi, o'tkazib yuborilgan chegara (overdue).
Frontend: /dashboard/maintenance (Gantt) shu API'ga; QuickOrderModal dagi yo'q `supabase` importi
muammosi shu bilan yo'qoladi (nariyadni backend orqali yarat).
```

---

## P-T6 — Analytics, dashboard, hisobotlar

```
Vazifa T6. 1) Alembic migratsiyasi bilan view'lar: executive_summary, section_efficiency,
work_type_efficiency, monthly_efficiency, ai_insights_summary, fleet_health,
work_order_tmc_details (endi JSONB emas, work_order_items dan JOIN), maintenance_schedule.
Eski Supabase SQL (scripts/*.sql) ni namuna sifatida o'qi, lekin yangi sxemaga moslab yoz.
Normadan og'ish: (fakt − norma) / norma × 100; >20% overrun; cost_savings = norm_cost − actual_cost.
2) Endpointlar: GET /dashboard/summary?section_id, GET /analytics/{...} (har blok uchun),
GET /reports/{work-orders|fixed-assets|tmc-documents} (filtr + CSV, UTF-8 BOM).
3) Dashboard: "Готовность по месяцам" grafigi hozir sin() bilan SUN'IY — haqiqiy tarix kerak.
Buning uchun qaysi manbadan (masalan oylik snapshot jadvali) foydalanishni menga taklif qil,
men tanlayman; keyin amalga oshir.
4) Master uchun uchastka filtri serverda.
Testlar: bo'sh ma'lumotda view'lar xato bermasligi, og'ish hisobi.
Frontend: analytics, reports, dashboard sahifalarini ko'chir; analytics/page.tsx (1051 qator)ni bo'l.
```

---

## P-T7 — WebSocket (realtime)

```
Vazifa T7. Supabase Realtime o'rniga: backend `/ws` WebSocket endpoint.
- Autentifikatsiya: access token bilan (query param emas, tavsiya: birinchi xabar yoki subprotocol;
  muddati o'tsa yopish).
- Backend startida asyncpg bilan `LISTEN toir_changes` (schema'dagi notify_change() triggeri
  work_orders, fixed_assets, users uchun event yuboradi: {table, op, id}).
- Klient obunasi: jadval nomlari; master faqat o'z uchastkasi event'larini oladi.
- Ulanish uzilsa LISTEN qayta ulanish; klient 5 soniyada qayta ulanadi (lib/use-realtime.ts mavjud).
Dashboard, OS, work-orders va admin users sahifalari shu event'lar bilan qayta yuklansin.
Testlar: event kelishi, ruxsatsiz token yopilishi, master filtri.
```

---

## P-T8 — Supabase'dan to'liq tozalash

```
Vazifa T8. Maqsad: repoda Supabase izi qolmasin.
1) `grep -ri "supabase"` (node_modules, lock fayllar, .next dan tashqari) ro'yxatini ber va har
   joyni backend/Postgres ekvivalenti bilan almashtir yoki o'chir.
2) O'chirish: lib/supabase.ts, lib/supabase-utils.ts, app/api/* dagi Supabase route'lari
   (mileage, maintenance-plan, maintenance-schedule — T3/T5 backend'ga ko'chgach),
   server/wialon-receiver.js, scripts/*supabase*, eski scripts/*.sql (referens kerak bo'lsa docs/legacy/ ga),
   test-auth.js, .vscode yoloMode.
3) package.json: @supabase/* olib tashla; bitta paket menejeri (pnpm YOKI npm; ikkinchi lock-fayl o'chiriladi).
   `name: my-v0-project` ni "toir-frontend" ga o'zgartir.
4) Ildizdagi arxivdan qolgan dublikat .py/.ts fayllar (config.py, auth.py, main.py, database.py, user.py, api.ts...)
   va app/dashboard/{work-orders,tmc}/*.py — avval hech narsa ularni import qilmasligini
   isbotla, keyin o'chir.
5) .env.local.example/.env.example faqat kerakli o'zgaruvchilar: NEXT_PUBLIC_API_URL va backend sozlamalari.
6) Python skriptlar (import_nomenclature.py, anomaliya) kalitsiz, DATABASE_URL env orqali ishlasin.
Tekshiruv: `grep -ri supabase` bo'sh; `tsc --noEmit` va `next build` toza; brauzerda barcha sahifa ochiladi.
```

---

## P-T9 — ML worker

```
Vazifa T9. services/ml_engine.py mantig'ini (PROJECT.md 13-bo'lim) backend ichiga worker
sifatida ko'chir, Supabase'siz.
- Trigger: nariyad completed bo'lganda (NOTIFY yoki servis chaqiruvi) background task.
- 1) TMC sarf anomaliyasi: repair_kind+section bo'yicha tarix (≤200, kamida 3); z>2.0 yoki |og'ish|>30%;
  severity critical/high/medium; probability=min(z/4,1).
- 2) Nosozlik prognozi (RUL): LinearRegression; failure_prob = 1 − exp(−kunlar_oxirgi_ТО_dan/o'rtacha_interval);
  chegaralar 0.7/0.4; qolgan km<500 → critical.
- 3) Health score: (1−p)×100 − min(anomaliya_30kun×5,20) − min(ТО'siz_kunlar/30×5,15).
- Natijalar ai_insights va fixed_assets (failure_probability, health_score, predicted_failure_km, last_ml_update).
- Eski xatolar tuzatilsin: diesel turi ham tahlilga kirsin; docstring'dagi yo'q --listen olib tashlansin.
- Qattiq yozilgan URL/kalit YO'Q. ML og'ir bo'lsa alohida compose servisi (worker) sifatida.
- Endpointlar: POST /ml/analyze (admin), GET /ml/insights.
Testlar: sintetik ma'lumot bilan anomaliya va RUL hisobi; kam tarixda insight yaratilmasligi.
```

---

## P-T10 — Production qotirish

```
Vazifa T10. 1) Frontend Dockerfile (multi-stage, standalone output, non-root). 2) Proxy servisi
(Caddy yoki Nginx): faqat shu tashqi port ochiq; /api va /ws backend'ga, qolgani frontend'ga;
HTTPS (domen bo'lsa Let's Encrypt, bo'lmasa ichki self-signed — avval menga savol ber).
Backend 127.0.0.1 portini ham yop (proxy orqali). 3) Login limiter ni jarayon xotirasidan
Redis yoki DB jadvaliga ko'chir (bir nechta worker'da ishlashi uchun). 4) `/docs` va `/openapi.json`
env flag bilan o'chiriladigan bo'lsin; xavfsizlik headerlari; CORS faqat prod domen.
5) Postgres zaxira nusxa skripti (pg_dump, rotatsiya) va tiklash tartibi. 6) CI (GitHub Actions):
backend pytest + frontend tsc/lint/build + docker build. 7) README: noldan ishga tushirish
(.env, compose, create-admin) va muammolar bo'limi.
Tekshiruv: `docker compose up --build` bilan butun stek, tashqaridan faqat proxy portiga kirish mumkin.
```

---

## Yordamchi promptlar

**Holat audit (limit tugaganda yoki yangi akkauntda):**
```
Hech narsa o'zgartirma. Repo holatini audit qil: git status/log, backend/ va frontend'dagi Supabase
qoldiqlari (grep), ishlayotgan servislar, oxirgi build natijasi, testlar. docs/HANDOFF.md dagi 2-bo'limni
HAQIQIY holatga qarab yangila (faqat o'zing tekshirganlarini "tasdiqlangan" deb belgila) va farqlarni ayt.
```

**Sessiya oxirida (limit tugashidan oldin):**
```
Limitim tugayapti. docs/HANDOFF.md ni yangila: 2-bo'lim (nima tasdiqlangan/yo'q), 3-bo'lim (nima
bo'ldi), 6-bo'lim (bajarilgan vazifalarni belgila), yangi topilgan muammolar va ochiq savollar.
Maxfiy qiymat yozma. Keyin o'zgargan fayllar ro'yxatini va tavsiya etilgan git commit xabarini ber.
```

**Kodni tekshirtirish (men yoki boshqa model yozgan kod uchun):**
```
Shu o'zgarishlarni code review qil: xavfsizlik (auth, rol, SQL injection, sizib chiqadigan
maxfiy ma'lumot), schema.sql bilan moslik, xatolarni qayta ishlash, testlar yetarliligi.
Topilmalarni jiddiylik bo'yicha ber va har biriga aniq tuzatish ko'rsat.
```
