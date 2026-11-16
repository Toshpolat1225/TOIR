# TOPSHIRIQ: vagon probegini to'liq ishlaydigan qilish (Claude Code)

Til: faqat o'zbek (lotin). Fakt, taxmin va tavsiyani alohida yoz. Tekshirilmagan narsani "tekshirilgan" dema.

## 0. Maqsad va "tugadi" mezonlari

Maqsad: mahalliy Docker bazasida GTK sostavi va Wialon lokomotiv probegidan **har bir vagon uchun** probeg hisoblansin: ledger → projection → ТО-reja → ekran. Hisoblab bo'lmaydigan vagon `HELD` bo'lsin va **sababi ko'rinsin**.

Tugadi hisoblanadi, agar hammasi bajarilgan va isbotlangan bo'lsa:
1. Real ishga tushirish (mahalliy baza) har bir vagon uchun status + sabab beradi; qamrov hisoboti bor (vagon soni, `CONFIRMED/ESTIMATED/HELD` bo'yicha km va soni, `HELD` sabablari va ularni qanday tuzatish).
2. Invariantlar yashil: vagon projection = tasdiqlangan boshlang'ich + Σ(`CONFIRMED`+`ESTIMATED`); ledger km ≥ 0; qayta ishga tushirish farq bermaydi; lokomotiv `fixed_assets.mileage` ishga tushirishdan oldin va keyin **bir xil**.
3. To'liq backend suite, PostgreSQL (`pytest -m pg`), `tsc`, lint, build: yashil, **real sonlar bilan**.
4. Hujjat: `docs/WAGON_MILEAGE_RUNBOOK.md` va yakuniy hisobot.

## 1. Ish tartibi va cheklovlar

- **So'ramasdan qilinadi:** kod, test, hujjat, git shoxcha (`wagon-mileage-final`) va commit, vaqtinchalik baza (`pg_rehearse`), mahalliy Docker'da build/restart.
- **Mahalliy bazaga (`toir-postgres-1`) yozishdan oldin zaxira** (`pg_dump`) oling. Ma'lumotni o'chiradigan (`DROP/TRUNCATE/DELETE`) amal yoki xavfli migratsiya bo'lsa, **avval so'ra**.
- **Taqiqlangan:** production server/baza, SSH, `/srv/apps/fuel`, tashqi tizimga yozish. `.env*` ni o'qima, tahrirlama, chop etma. Token, parol, ulanish satrini logga yozma.
- **Avval audit, keyin kod.** Uydirma fayl/funksiya yo'q: har narsani repodan top. Keraksiz refaktor yo'q. Kerakmas faylni qayta o'qima.
- **Bitta narsa yetishmasa, bitta aniq savol ber**, taxmin qilma. Kontekst to'lib borsa `docs/WAGON_MILEAGE_PROGRESS.md` ga holat va keyingi qadamni yoz.
- Birlik testlari uchun bazani vaqtinchalik konteynerda yurgiz:
  `docker run --rm -d --name pg_rehearse -e POSTGRES_USER=rehearse -e POSTGRES_PASSWORD=rehearse -e POSTGRES_DB=rehearse -p 55432:5432 postgres:16-alpine`
  (muhit: `POSTGRES_USER/PASSWORD/DB=rehearse`, `DATABASE_HOST=127.0.0.1`, `DATABASE_PORT=55432`, test `JWT_SECRET`, `CORS_ORIGINS`). Tugagach `docker stop pg_rehearse`.

## 2. Qat'iy qarorlar (o'zgartirma)

| № | Qoida |
|---|---|
| D1 | Wialon `observed_at` = xabar vaqti (`lmsg.t`, UTC), sinxronlash vaqti emas |
| D2 | Wialon identifikatori faqat `wialon_id`; nom bilan moslash yo'q |
| D3 | Bracket maks. 30 daq (`WAGON_MILEAGE_MAX_BRACKET_GAP_MIN`). Odometr nuqtalari ~2 daq oraliqda keladi: bu norma, chegara emas. Odometr teng bo'lsa 0 km `CONFIRMED` (har qanday oraliq). Harakat bor va ≤30 daq: chiziqli, `ESTIMATED`. >30 daq yoki reset/konflikt: `HELD` |
| D4 | Lokomotiv almashishi faqat GTK vaqti bilan; vaqt yo'q: `HELD` |
| D5 | Vagon snapshotlar orasida o'tdi (GTK aniq vaqt bermasa): har doim `ESTIMATED` |
| D6 | Asosiy lokomotiv: GTK `is_main` aniq bitta > eligible Wialon o'qishi > eng yangi. Ikki lokomotiv farqi `max(2 km, 5%)` dan oshsa `HELD`. Probeglar hech qachon qo'shilmaydi/o'rtachalanmaydi, fizik masofa bir marta |
| D7 | Idle: odometr deltasi 0 (≥ `WAGON_MILEAGE_IDLE_MIN_MINUTES`, standart 30, PENDING) VA GTK holati mos. Faqat GPS tezlikka tayanma. Idle km qo'shmaydi |
| D8 | Boshlang'ich balans: kiritgan ≠ tasdiqlovchi, tasdiqlovchi admin (`OPENING_BALANCE_ALLOW_SELF_APPROVAL=false`, PENDING). Tasdiqlanmasa shu vagon `HELD`. O'zgartirishda eski qiymat saqlanadi |
| D9 | Projection = tasdiqlangan boshlang'ich + `CONFIRMED` + `ESTIMATED`; `HELD` kirmaydi va ogohlantiradi; ekranda uch qiymat alohida; `fixed_assets.mileage` vagon uchun faqat projection yozuvchisi |
| D10 | Lokomotiv/teplovoz mileage'iga dvigatel yozmaydi (faqat Wialon pull, `wialon_quality` delta). `WAGON_MILEAGE_ENGINE_ENABLED=false` da eski yo'l o'zgarmaydi, ikkalasi birga yozmaydi |

Segment: `CONFIRMED` faqat a'zolik chegarasi GTK tomonidan aniq va km to'g'ridan-to'g'ri Wialon o'lchovidan (yoki 0-harakat). Taqsimot: a'zolik oralig'idagi qo'shni Wialon nuqta juftliklari farqlari yig'iladi; chegara juftlik ichidan o'tsa, faqat shu ulush `ESTIMATED`. Misol: lokomotiv 09:00–10:00 da 40 km, vagon 09:00–09:30: **20 km**. Oraliqlar `[start, end)`, vaqt UTC.

## 3. Mavjud holat (oldingi ish, Copilot)

Fakt: migratsiyalar `0027–0029`, `pg_rehearse` da `upgrade→downgrade -1→upgrade` o'tgan; to'liq suite 317 o'tdi; `pg` testi atigi 1 ta; `tsc/lint/build` o'tgan. Fayllar: `services/wagon_mileage.py`, `wagon_mileage_engine.py`, `wagon_mileage_run.py`, `mileage_opening.py`, `gtk_membership.py`, `wialon_ingestion.py`, `wialon_counters.py`, `wialon_quality.py`, `routers/mileage.py`, `cli.py`, UI `app/dashboard/directories/assets/page.tsx`. Hujjatlar: `docs/WAGON_MILEAGE_P0_DECISIONS.md`, `docs/WAGON_MILEAGE_P0_2_IMPLEMENTATION_PLAN.md`, `docs/HANDOFF.md`.
Noma'lum (isbotlanmagan): kod D1–D10 ga to'liq mosligi; qaysi qadamlar avtomatik ulangan; mahalliy bazada GTK va Wialon ma'lumoti yetarliligi. 5 ta test fayli (`source_check_utils.py` va `uz-Cyrl` istisnosi) tahrirlangan: tekshiruv susaymaganini ko'r.
Mahalliy muhit: Docker Compose (`postgres`, `backend`, `frontend`, `proxy`), sayt `https://localhost`, CLI: `docker compose exec backend python -m app.cli ...`.

## 4. Fazalar

### Faza 1: AUDIT (kod o'zgartirmasdan, `docs/WAGON_MILEAGE_AUDIT.md`)
1. D1–D10 jadvali: qaror | BAJARILGAN/QISMAN/YO'Q | dalil (fayl:qator, test nomi).
2. Ma'lumot oqimi: GTK sync → a'zolik → Wialon o'qish → engine run → ledger → projection → ТО-reja qayta hisobi. Har bo'g'in kim chaqiradi, **avtomatik yoki ulanmagan**, bayroq ortidami.
3. `fixed_assets.mileage` yozuvchilari ro'yxati (fayl:qator), egalik (D10) bo'yicha.
4. Mahalliy bazadan **faqat o'qiydigan** qamrov hisoboti (SQL): vagonlar soni; `gtk_id` borlari; ochiq a'zoliklar; lokomotivlar va ularning `wialon_id`; eligible Wialon o'qishlari (so'nggi 24 soat); tasdiqlangan boshlang'ich balanslar; ledger qatorlari; GTK snapshotlar soni va oxirgi vaqti.
5. Bo'shliqlar ro'yxati (Faza 2 uchun), muhimlik tartibida.
**Agar mahalliy bazada GTK snapshot yo'q bo'lsa:** uydirma ma'lumot yaratma. Faza 2–3 ni kod va fixture testlari bilan bajar, Faza 4 real ishga tushirishni to'xtat va foydalanuvchiga bitta savol ber (GTK sinxronlashni yurgizish yoki namuna JSON berish).

### Faza 2: Bo'shliqlarni yopish (audit ro'yxati bo'yicha; quyidagilar majburiy minimum)
- **2.1 Yagona ishga tushirish:** `wagon-mileage-run [--dry-run]` ketma-ketligi: a'zolik → Wialon o'qishlari → hisoblash → ledger → projection → ТО-reja (bir marta, faqat o'zgargan vagonlar). Advisory lock, run holati va hisoblagichlari `mileage_calculation_runs` ga. Davriy sinxronlashga ulanish `WAGON_MILEAGE_ENGINE_ENABLED` ortida (standart `false`).
- **2.2 Boshlang'ich balanslar ommaviy:** vagonlarning hozirgi `fixed_assets.mileage` qiymatidan **taklif** yaratish (`wagon-opening-propose`, standart dry-run: soni, nol/NULL, `>1 000 000` belgilari). Ommaviy tasdiqlash alohida admin tomonidan (API yoki CLI, kim tasdiqlagani saqlanadi, maker≠checker). Nol/NULL va shubhali qiymatlar avtomatik tasdiqlanmaydi. `effective_at` parametr (standart: tasdiqlash vaqti). Idempotent.
- **2.3 `HELD` sabablari:** sababni kod va matn bilan standartlashtir (`gtk_id` yo'q, lokomotivda Wialon mapping yo'q, GTK vaqt belgisi yo'q, bracket >30 daq, konflikt, boshlang'ich balans tasdiqlanmagan va hokazo). Faqat haqiqiy xato bo'lsa kodni tuzat; D4/D5 qoidalarini yumshatma.
- **2.4 Qamrov hisoboti:** `wagon-mileage-report` (faqat o'qiydi): har vagon uchun status, km (3 qiymat), sabab; jami; CSV `.gitignore` ga qo'shilgan joyga.
- **2.5 UI (minimal):** vagon sahifasida `confirmed/estimated/held`, probeg tarixi (ledger), `HELD` sabablari, boshlang'ich balansni kiritish/tasdiqlash va admin uchun ommaviy tasdiqlash. Uch tilda (o'zbek lotin, kirill, rus), mavjud rol tekshiruvi uslubida.
- **2.6 Invariantlar (kod va test):** 0-bandda sanalganlar. Ular har run oxirida tekshirilsin; buzilsa run `FAILED`, projection yozilmasin.

### Faza 3: Test
D1–D10 uchun test (mavjudlarini qayta ishlat, yetishmaganini qo'sh): Wialon `10^9 km` sakrashi km bermaydi; push+pull dublikat bitta; `[start,end)` chegara; 3 soatlik teng odometr 0 km `CONFIRMED`; 4 daq harakat `ESTIMATED`, 45 daq `HELD`; 40 km misoli 20 km; ikki lokomotiv farqi; qayta ishga tushirishda yangi qator yo'q; maker≠checker; lokomotivga yozish rad; bayroq `false`da eski yo'l; ikki parallel run bitta to'plam (PostgreSQL). Keyin: to'liq suite, `pytest -m pg`, `tsc --noEmit`, lint, build, migratsiya `upgrade→downgrade -1→upgrade` (`pg_rehearse`).

### Faza 4: Mahalliy Docker'da real ishga tushirish
1. Zaxira: `docker compose exec postgres sh -c 'pg_dump -U $POSTGRES_USER -d $POSTGRES_DB -Fc -f /tmp/p03.dump'` va `docker compose cp postgres:/tmp/p03.dump .\p03_<vaqt>.dump`.
2. `docker compose up -d --build backend frontend`, `alembic upgrade head`, `alembic current` = oxirgi head.
3. **Oldin** SQL: asset_type bo'yicha `count(*)`, `sum(mileage)` va lokomotivlar mileage checksum.
4. `wagon-mileage-run --dry-run`, hisobotni ko'rsat.
5. Real ishga tushirish `.env` ga tegmasdan: `docker compose run --rm -e WAGON_MILEAGE_ENGINE_ENABLED=true backend python -m app.cli wagon-mileage-run`.
6. **Keyin** SQL: lokomotiv checksum o'zgarmagan; invariantlar; ikkinchi run farqsiz; qamrov hisoboti.
7. Brauzer tekshiruvini foydalanuvchiga qoldir (`https://localhost`, vagon sahifasi); o'zing brauzer ochma.

### Faza 5: Hujjat va hisobot
- `docs/WAGON_MILEAGE_RUNBOOK.md`: kunlik ishlatish, buyruqlar, `HELD` sabablari va nima qilish, rebaseline, qaytarish. Server chiqarish checklistini **yoz, bajarma** (zaxira, migratsiya, Wialon host mask serverga, bayroqni bosqichma-bosqich yoqish).
- `docs/HANDOFF.md` va `docs/AI_WORKLOG.md` (faqat o'zbek lotin).

## 5. Yakuniy hisobot formati
- Fazalar: BAJARILDI / QISMAN / BAJARILMADI. Har "BAJARILDI" uchun dalil (buyruq + natija).
- 0-bandning 4 mezoni: PASS / FAIL / NOT TESTED.
- Qamrov hisoboti jadvali (statuslar, `HELD` sabablari soni).
- Test sonlari (suite, pg, tsc, lint, build) va muhit.
- O'zgargan fayllar; PENDING qarorlar; sinalmagan narsalar (brauzer, server, jonli GTK/Wialon).
- Foydalanuvchiga bitta eng muhim keyingi qadam.
