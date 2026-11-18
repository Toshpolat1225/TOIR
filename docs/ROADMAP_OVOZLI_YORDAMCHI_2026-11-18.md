# Ovozli buyruq markazi — optimal reja (TZ)

Sana: 2026-11-18. Holat: **faqat reja, kod yozilmagan.** Hujjat loyiha egasi (qaror uchun) va keyin amalga oshiruvchi uchun.
Belgilar: **[REJA]** qurilmagan · **[OCHIQ]** foydalanuvchi qarori / o'lchov kerak · **[FAKT]** tizim kodidan olingan.

## 0. Qaror (qisqa)

- **Erkin suhbat YO'Q, LLM YO'Q.** Yordamchi — *buyruq markazi*: aytilgan yoki yozilgan jumlani aniq qoidalar bilan tanib, tizimning o'z xizmatlarini chaqiradi va natijani kartochka + (ixtiyoriy) ovoz bilan beradi.
- **Hammasi lokal va tekin, oddiy Docker'da, GPU'siz.** Faqat ovozni matnga aylantirish uchun kichik lokal model (Whisper tiny/base/small, 75–500 MB) alohida konteynerda. Ovoz xohlanmasa o'chiriladi, matnli rejim ishlayveradi.
- **Tizimni to'liq boshqaradi:** sahifalarga o'tish, qidirish, savollarga javob, va (tasdiq bilan) amallar: naryad ochish, holat o'zgartirish, izoh. O'chirish (delete) ovoz bilan TAQIQLANGAN.
- **Ruxsat tizimi o'zgarmaydi:** buyruq foydalanuvchining o'z tokeni bilan, mavjud servislar orqali bajariladi → rol va uchastka cheklovlari (master faqat o'z uchastkasi, begonaga 404) avtomatik saqlanadi.
- Ko'rsatkich: yozma buyruq niyatini aniqlash ≥ 95%, ovozli ≥ 90%, raqamlar (inventar, sostav №) ≥ 97% — 300+ jumlalik oltin to'plamda o'lchanadi.

## 1. Nima uchun aynan shunday (optimal)

| Variant | Hukm |
|---|---|
| LLM bilan erkin suhbat | Kerak emas (siz aytdingiz), serverda GPU'siz sekin, o'zbekchani zaif tushunadi, xavfsizlik yuzasi katta |
| Brauzerning Web Speech | Lokal ham, oflayn ham emas (tashqariga ketadi) → TAQIQ |
| **Qoidali niyat tanish + lokal Whisper + mavjud API** | Tez (ms), aniq, tushuntiriladigan, xatolik takrorlanadi va tuzatiladi, server resursini kam oladi → **tanlandi** |
| Keyinroq LLM qo'shish | Mumkin: buyruq katalogi LLM uchun tayyor «vositalar» ro'yxati bo'ladi |

## 2. Arxitektura [REJA]

```
Brauzer (mikrofon tugmasi / Ctrl+K / matn)
   │  audio (≤30 s, webm/opus)                    │ matn
   ▼                                              ▼
POST /assistant/transcribe  ──► whisper konteyner (ichki tarmoq, port tashqariga chiqmaydi)
   │  matn + ishonch                              │
   ▼                                              ▼
POST /assistant/command {text, locale, context{page, asset_id}}
   1. normalizatsiya (lotin/kirill/ru, kichik harf, imlo variantlari)
   2. raqam so'zlari → raqam («o'ttiz yetti to'qqiz yuz o'n to'qqiz» → 37919)
   3. entitetlarni topish (inventar №, sostav №, uchastka, sana, tur) — fuzzy (pg_trgm / rapidfuzz), faqat foydalanuvchi ko'ra oladigan ob'ektlar orasidan
   4. niyat (intent) tanlash — katalog (YAML): iboralar uz/ru/en, majburiy/ixtiyoriy slotlar, ruxsat kodi
   5. handler → mavjud servis (gps_overview, gps_wagons, maintenance, work_orders, scales, mileage…) foydalanuvchi bilan
   6. javob: {kartochkalar[], navigatsiya?, aytiladigan matn, tasdiq kerakmi?, tushunmadi? takliflar}
   ▼
Frontend: umumiy buyruq paneli (barcha sahifada), natija kartochkasi, «Ochish» havolasi, TTS (brauzer ovozlari, ruscha)
```

- **Servis qatlami**: handlerlar HTTP orqali emas, to'g'ridan-to'g'ri servis funksiyalarini chaqiradi (`routers → services → repositories` qoidasi saqlanadi); yangi router `routers/assistant.py`, servis `services/assistant/` (parser, entities, catalog, handlers, speech).
- **Whisper konteyneri**: `faster-whisper`, int8, CPU; modeli image'ga oldindan joylanadi (internet serverda kerak bo'lmasin); `mem_limit`/`cpus` chegarasi; faqat TOIR ichki tarmog'ida; serverdagi «fuel» konteynerlari, portlar (80, 443, 3000, 8000, 5432, 9090, 3100) va nginx'ga tegilmaydi.
- **Ovoz sifatini oshirish**: Whisper'ga `initial_prompt` (tizim atamalari: «naryad», «sostav», «lokomotiv», «Wialon»…) va tanilgan matnni haqiqiy entitetlarga moslash (masalan «ottiz yetti» → 37…).
- **Ma'lumot**: yagona yangi jadval `assistant_queries` (user_id, matn, niyat, entitetlar, natija: ok/unmatched/denied/confirmed, ms, vaqt). **Audio saqlanmaydi** (qayta ishlangach o'chadi). Migratsiya + `schema.sql` + dump qoidasi.
- **Kontekst**: «bu lokomotiv», «uni xaritada ko'rsat» — joriy sahifa obyekti yoki oxirgi natija bo'yicha.
- **Amallar uchun 2 bosqichli tasdiq**: buyruq → qoralama kartochka («37919 uchun naryad: ТО-2, uchastka …») → «ha / tasdiqlayman» (ovoz yoki tugma) → bajarish + audit. Tasdiq 60 soniya amal qiladi, bir marta ishlatiladi.
- **Xavfsizlik**: LLM yo'q → prompt-injection yuzasi yo'q; tezlik cheklovi (daqiqasiga 30 buyruq, 10 ovoz); audio ≤30 s, ≤2 MB; rol bo'yicha katalog filtri (ko'rishga ruxsati yo'q niyat «tushunarli», lekin «ruxsat yo'q» deydi); hech qachon bazaga erkin SQL.

## 3. Buyruq katalogi (tizimni to'liq qamrash) [REJA]

Har niyat: ruxsat kodi, slotlar, handler, javob turi. Jumlalar uz (lotin), ru; kirill-uz ham qabul qilinadi.

| Modul | Misol buyruqlar | Ruxsat |
|---|---|---|
| Navigatsiya | «xaritani och», «naryadlar», «GPS sahifasi», «vesovoy», «ТО» | sahifa ruxsati |
| Qidiruv | «37919 ni top», «vagon 35656», «№ 439 sostav», «naryad 1024» | `assets.view` va h.k. |
| GPS / xarita | «37919 qayerda», «37919 GPS holati», «bugun necha km yurdi», «GTK o'lik trekerlar», «Wialon va GTK nega farq qildi» (tayyor izoh), «shu lokomotivni xaritada ko'rsat» | `analytics.view` |
| Vagonlar | «35656 qaysi lokomotiv bilan», «N sostavda nechta vagon», «vagon 35656 bu hafta necha km» | `analytics.view` |
| ТО | «muddati o'tgan ТО», «bu oy ТО jadvali», «37919 keyingi ТО qachon», «uchastka bo'yicha ТО» | `maintenance.view` |
| Naryad | «ochiq naryadlar», «uchastkamdagi naryadlar soni», **«37919 uchun naryad och»**, **«naryad 1024 ni bajarildi qil»** | `work_orders.view` / `create` / `update` |
| Vesovoy | «bugun nechta sostav tortildi», «bugun necha tonna», «vagon 35656 yuk tarixi» | `scales.view` |
| Probeg | «lokomotiv 37919 probegi», «vagon 35656 probegi» | `assets.view` |
| TMC / ombor | «ombor qoldig'i …», «TMC hujjatlari» | `tmc.view` / `inventory.view` |
| Hisobot | «hisobotlarni och», «oy hisobotini yuklab ol» | `reports.view` / `export` |
| Tizim | «Wialon oxirgi marta qachon yangilandi», «GTK sinxron holati», «yordam / nima so'ray olaman» | tegishli |
| Admin (faqat admin) | «oxirgi audit hodisalari», «foydalanuvchilar soni» | `users.manage_users` |

Tushunilmagan jumla: eng yaqin 3 ta niyat taklif qilinadi; log'ga yoziladi (admin «Tushunilmagan» ro'yxatini ko'rib katalogni kengaytiradi — avtomatik o'rganish YO'Q).

## 4. Frontend [REJA]

- Sarlavhada doimiy **mikrofon tugmasi** + `Ctrl+K` buyruq paneli; Space bosib turib gapirish (push-to-talk), qo'yib yuborganda yuboriladi; telefonda katta tugma.
- Natija kartochkasi (tur bo'yicha: lokomotiv, vagon, ro'yxat, son), «Ochish» havolasi, «Ovozda o'qi» (brauzer ruscha ovozi; o'zbekcha ovoz lokal mavjud emas → matn).
- Tasdiq kartochkasi (amallar uchun): «Tasdiqlash» / «Bekor».
- Yordam oynasi: katalogdan avtomatik yig'ilgan «nima deyish mumkin» ro'yxati (rolga mos).
- Ruxsat bo'lmasa ovoz tugmasi yashirin; mikrofon ruxsati rad etilsa — matnli rejim.
- Telefon kengligida yon aylanish yo'q; klaviatura bilan to'liq boshqariladi.

## 5. Bosqichlar (optimal tartib: har bosqich ishlaydigan foyda beradi)

| # | Bosqich | Mazmuni | Qabul mezoni |
|---|---|---|---|
| P0 | Tayyorgarlik (0,5 kun) | Server resursi (`free -h`, `nproc`) → Whisper hajmi; oltin jumlalar to'plami (300+: uz/ru, raqamlar, xato imlo); katalog loyihasi | Foydalanuvchi katalogni va yozuvchi amallar ro'yxatini tasdiqlaydi |
| P1 | Yozma buyruq markazi (3 kun) | Parser, raqam-so'z, entitetlar, katalog, o'qish handlerlari (GPS, vagon, ТО, naryad, vesovoy, probeg, tizim), umumiy buyruq paneli, `assistant_queries` | Oltin to'plamda niyat ≥ 95%, raqam ≥ 97%; master begona uchastkaga 404; jonli e2e + brauzer testi |
| P2 | Ovoz (2 kun) | Whisper konteyneri, `/assistant/transcribe`, vocabulary biasing, push-to-talk, TTS | Ovozli to'plamda (shovqinsiz + ofis shovqini) niyat ≥ 90%; audio saqlanmaydi; konteyner chegarasi ichida; 5 s gap < 4 s javob (CPU, o'lchanadi) |
| P3 | Amallar tasdiq bilan (2 kun) | Naryad ochish, holat o'zgartirish, izoh; 2 bosqichli tasdiq; audit; kontekst («bu lokomotiv») | Tasdiqsiz yozuv yo'q (test); ruxsatsiz rol rad etiladi; qayta-qayta tasdiq ishlamaydi |
| P4 | Mustahkamlash (1–2 kun) | Tushunilmagan ro'yxat (admin), tezlik cheklovi, yuk testi, hujjat, qo'llanma | 20 bir vaqtli foydalanuvchi; xatosiz; `HANDOFF/DECISIONS/AI_WORKLOG` |

Jami ≈ 9–10 ish kuni. P1 ovoz va modelsiz ham to'liq foydali.

## 6. Test strategiyasi (test-first)
1. **Oltin to'plam** (`backend/tests/assistant_golden.yaml`): jumla → kutilgan niyat va slotlar; har yangi buyruq shu to'plamga qo'shiladi.
2. **Sof funksiya testlari**: raqam-so'z (uz/ru), imlo variantlari, fuzzy moslash, katalog to'qnashuvlari (bir jumla ikki niyat).
3. **PG testlari**: ruxsat va uchastka (master 404), tasdiq oqimi (muddat, bir martalik), audit yozuvi.
4. **Ovoz testlari**: yozilgan namunalar (o'zbek/rus, turli tezlik va shovqin) → WER va niyat aniqligi hisoboti; natija sonlari hujjatga.
5. **Jonli e2e + haqiqiy brauzer** (Edge; mikrofon ruxsati stub): buyruq paneli, kartochkalar, tasdiq, telefon kengligi.
6. Hech narsa «ishladi» deb aytilmaydi — buyruq chiqishi ko'rilmasa **NOT TESTED**.

## 7. Xavflar va ochiq savollar [OCHIQ]
1. **Server xotirasi/CPU** — Whisper `base` (~150 MB) yoki `small` (~500 MB, o'zbekchada aniqroq) tanlovi shunga bog'liq.
2. **Til ustuvorligi:** o'zbek (lotin) birinchi, rus ikkinchi? Whisper o'zbekchani ruschadan zaifroq taniydi → muhim buyruqlarda matn bilan tasdiqlash (kartochkada «Siz aytdingiz: …»).
3. **Qaysi yozuvchi amallar ruxsat etiladi** (tavsiya: naryad ochish, holat, izoh; qolganlari yo'q).
4. **Shovqinli joy** (sex): ovoz aniqligi tushadi; tashqi mikrofon/garnitura tavsiya; matn zaxirasi doim bor.
5. **Whisper modelini serverga yetkazish:** model faylini image'ga joylab (PC'da yig'ib) yuborish; serverda internet shart emas.
6. Kelajakda LLM qo'shilsa — bu katalog «vositalar» sifatida tayyor; hozir kerak emas.

## 8. Nimaga tegilmaydi
Mavjud endpointlar, ruxsatlar, rollar, «fuel» tizimi va uning portlari, mavjud jadvallar. Yangi narsa: `assistant` router/servis, `assistant_queries` jadvali (migratsiya), ixtiyoriy `whisper` konteyneri, frontend buyruq paneli.
