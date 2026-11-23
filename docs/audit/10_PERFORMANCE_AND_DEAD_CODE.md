# Tizim yuki va o'lik kod auditi — 2026-11-23 (faqat o'qish; hech narsa o'zgartirilmadi, o'chirilmadi)

Bu hujjat ko'rib chiqish uchun. Kodni o'chirish yoki sozlamani o'zgartirish faqat siz tasdiqlagandan keyin.

## A. Nega tizim sekin: o'lchangan sabablar

| # | Topilma | Dalil (o'lchandi) | Ta'siri |
|---|---|---|---|
| A1 | **Baza statistikasi eskirgan** (planner jadvallarni «kichik» deb o'ylaydi) | `asset_position_history`: haqiqatda 2 341 157 qator, statistikada 13 699; `wialon_odometer_readings`, `wialon_raw_receipts`: hech qachon analiz qilinmagan | Keraksiz **to'liq skanerlash**: 380 marta 532 mln qator o'qilgan; postgres konteyneri 4 soatda **149 GB** diskdan o'qigan |
| A2 | Har so'rovda butun jadval bo'yicha agregat | `repositories/gps.py:116` — `count(*), min(at) ... GROUP BY source` 2,3 mln qatorda; GPS umumiy ko'rinish (`gps_overview`) 1,4 s | GPS sahifasi sekin |
| A3 | **Backend xotirasi limitga yaqin** | 966 MiB / 1 GiB (94%) | Xotira bosimi, sekinlashish, ikkinchi jarayon ishga tushsa OOM (137 xato bergan) |
| A4 | **Postgres juda kichik sozlangan** | DB 2,7 GB; `shared_buffers=128MB`, konteyner limiti 512 MiB (54% band) | Kesh yetmaydi, doimiy disk o'qish |
| A5 | `mileage_calculation_runs.input_watermark` juda katta | 337 qator = 291 MB (har bir qator ~830 KB); har 10 daqiqada yangi qator (kuniga ~100–225) | Kuniga ~200 MB qo'shiladi, bazani shishiradi |
| A6 | Audit jurnali tez o'smoqda | `audit_logs` 23-noyabrda 84 565 qator (20-noyabrda 64); `wagon_mileage_ledger` 42 048 qator/kun | Vagon dvigateli har siklda ledger va audit yozadi |
| A7 | Katta jadvallar o'sishi | `wialon_raw_receipts` ~100 ming qator/kun; `asset_position_history` 25–60 ming/kun (2025-04 dan beri) | Saqlash muddati yo'q (audit_logs dan tashqari) |
| A8 | Ortiqcha indeks | `ix_asset_position_history_asset_at` (169 MB) — `uq_…(asset_id, at, source)` ning prefiksi | Yozishni sekinlashtiradi, joy egallaydi |
| A9 | Yetarlicha avtovakuum yo'q | `scale_weighings`: 108 782 o'lik qator (18%) | Kichik sekinlashuv |

Endpoint tezligi (sovuq, to'g'ridan-to'g'ri xizmat): ТО jadvali 1,32 s; GPS umumiy 1,41 s; karta 0,06 s; vagonlar 0,09 s. So'rovlar soni past (10 daqiqada ~100), ya'ni **muammo trafikda emas, baza va xotirada**.

Disk: C: 85% band (129 GB bo'sh). `backups/` 4,7 GB (20 dump), repo ildizida `Bridge_Scale 93/97.mdb` 673 MB, `p03_20261113_153306.dump` 133 MB, `.next` 532 MB (hammasi git'da emas).

### Tavsiya etilgan tuzatishlar (hech biri bajarilmagan)
1. `ANALYZE` ni katta jadvallarga bir marta ishga tushirish (xavfsiz, faqat statistikani yangilaydi) — A1.
2. `gps.py:116` agregatini indeksli so'rov yoki kichik keshga almashtirish — A2.
3. Backend xotirasini 1 GiB dan 2 GiB ga (xost RAM 14 GB bo'sh) — A3.
4. Postgres: konteyner 1 GiB, `shared_buffers` 256–384 MB — A4.
5. `input_watermark` ni qisqartirish va eski run'larni (masalan, 7 kundan eskilarini) tozalash — A5.
6. `asset_position_history` va `wialon_raw_receipts` uchun saqlash muddati; `wagon-ledger-purge` ni fon vazifasiga — A6/A7.
7. Ortiqcha indeksni olib tashlash — A8.

## B. O'lik kod va fayllar (tekshirish uchun ro'yxat)

### B1. Ishlatilmaydigan fayllar (repo ildizida, git'da)
- `requirements.txt` (ildizda): eski versiyalar (`fastapi==0.111.1`), Docker va CI ishlatmaydi (`backend/requirements.txt` ishlatiladi).
- `alembic.ini` (ildizda): `backend/alembic.ini` dan farq qiladi, Docker `backend/alembic.ini` ni oladi.
- `scripts/anomaly_detection.py`, `scripts/import_nomenclature.py`, `scripts/read-excel.mjs`, `scripts/requirements_anomaly.txt`, `scripts/requirements_nomenclature.txt`, `scripts/excel_folder.txt`: faqat hujjatlarda eslatilgan, kod va Docker ishlatmaydi.
- Git'da yo'q, lekin diskda bor: `Bridge_Scale 93.mdb`, `Bridge_Scale 97.mdb` (haqiqiy tarozi bazalari — o'chirmang, saqlash joyini aniqlang), `p03_20261113_153306.dump`, `tsconfig.tsbuildinfo`, `reports/`.

### B2. Ishlatilmaydigan Python kodi (qo'ng'iroq topilmadi; har biri 1 ta eslatma = faqat e'loni)
- `app/services/assistant/handlers/_i18n.py` — hech qayerda import qilinmaydi.
- `repositories/asset_field_changes.py: list_changes`
- `repositories/gps.py: stored_day_distances`, `gtk_days`
- `repositories/gtk.py: get_locomotive_mileage_checkpoints`
- `services/scales_insights.py: _per_car`
- `services/assistant/engine.py: _text_card`
- `services/assistant/handlers/_common.py: suggest`, `tone_for_status`

(Router funksiyalari — dekorator bilan chaqiriladi, ular o'lik emas. Skript ularni noto'g'ri ko'rsatgan edi.)

### B3. UI dan chaqirilmaydigan API (11 ta, taxminiy)
`POST /gtk/sync`, `POST /wialon/sync` (qo'lda ishga tushirish), `GET /maintenance-health`, `POST /ml/analyze`, `GET /ml/insights`, `POST /scales/ingest` (tashqi kollektor ishlatadi — **o'lik emas**), `POST /wagon-mileage/openings/bulk-approve` (CLI), `GET/PUT/DELETE /translations/...` (4 ta; UI faqat ruscha, i18n ishlatilmaydi).

### B4. Frontend
- Hamma fayllar sahifalardan import orqali yetib boriladi (yetim fayl yo'q).
- 169 ta eksport hech qayerda import qilinmaydi (aksari `components/ui/icons.tsx` ikonkalari va turlar). Tavsiya: tegmaslik, xavfi past.
- `components/ui/`: 7 ta komponent, hammasi ishlatiladi.

## C. Tekshirilmagan
- Haqiqiy foydalanuvchi brauzer tezligi (bundle hajmi, tarmoq) o'lchanmadi.
- Sekin so'rovlar jurnali yoqilmagan (`pg_stat_statements` yo'q), shuning uchun eng og'ir so'rovlar reytingi aniq emas.
- B2/B3 ro'yxati statik tahlil: dinamik chaqiruvlar (`getattr`, tashqi tizimlar) hisobga olinmagan.
