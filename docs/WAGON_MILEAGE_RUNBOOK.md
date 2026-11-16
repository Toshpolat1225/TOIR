# Vagon probegi: ishlatish qo'llanmasi (RUNBOOK)

Holat: kod va testlar tayyor (2026-11-13). Mahalliy Docker'da real run **hali bajarilmagan** (HANDOFF ga qarang).

## 1. Qanday ishlaydi

GTK sinxronlash vagon a'zoligini yozadi. Wialon pull lokomotiv odometr o'qishlarini yozadi. `wagon-mileage-run` ularni o'qib, har vagon uchun davr bo'yicha km hisoblaydi (ledger), keyin projection (`fixed_assets.mileage`) yangilanadi.

- Formula: projection = tasdiqlangan boshlang'ich + Σ(`CONFIRMED` + `ESTIMATED`). `HELD` kirmaydi.
- Hisob tasdiqlangan boshlang'ichning `effective_at` vaqtidan boshlanadi. Undan oldingi davrlar hisoblanmaydi va `HELD` ham sanalmaydi (orqaga to'ldirish yo'q).
- Vagon probegi ТО-rejasidan mustaqil. Vagon uchun ТО-interval yo'q (me'yorlar keyin beriladi).
- Lokomotiv/teplovoz `fixed_assets.mileage` ni faqat Wialon pull yozadi (sifat darvozasidan o'tgan delta). Push va vagon dvigateli lokomotivga yozmaydi.
- Idle: `unknown_activity` qoladi (GTK holat dalili ulanmagan).

## 2. Buyruqlar (hammasi `backend` konteynerida)

Hamma buyruq: `docker compose exec backend python -m app.cli <buyruq>`. Bir martalik `docker compose run` da albatta `--entrypoint python` bering, aks holda butun ilova (GTK/Wialon sinxronlash bilan) ishga tushib ketadi. Real run uchun bayroq kerak: `docker compose run --rm --no-deps -e WAGON_MILEAGE_ENGINE_ENABLED=true --entrypoint python backend -m app.cli wagon-mileage-run` (`.env` ga tegilmaydi).

| Buyruq | Vazifa |
|---|---|
| `wagon-mileage-run --dry-run` | Hisobni yozmasdan ko'rsatadi. Bayroqsiz ham ishlaydi. |
| `wagon-mileage-run` | Real run. `WAGON_MILEAGE_ENGINE_ENABLED=true` bo'lmasa rad etadi (chiqish kodi 3). Boshqa run ketayotgan bo'lsa `skipped: run_in_progress` qaytaradi. |
| `wagon-mileage-report [--csv yo'l]` | Faqat o'qiydi: har vagon uchun status, 3 qiymat, sabab. CSV `reports/` papkasiga (gitignore'da). |
| `wagon-opening-propose --actor-email E [--effective-at ISO] [--apply]` | Joriy `fixed_assets.mileage` dan boshlang'ich **taklif** yaratadi. `--apply`siz faqat hisob (nol/NULL, >1 000 000). Takrorlansa yangi qator yaratmaydi. |
| `wagon-opening-approve --actor-email E [--effective-at ISO] [--apply]` | Ommaviy tasdiq. Faqat admin, taklif qilgandan **boshqa** foydalanuvchi. Nol/NULL va >1 000 000 qiymatlar tasdiqlanmaydi (alohida ko'rib chiqiladi). `effective_at` berilmasa, tasdiqlash vaqti qo'yiladi. |

API: `POST /api/v1/wagon-mileage/openings/bulk-approve` (`{"dry_run": true, "effective_at": null}`), faqat admin.

## 3. Kunlik tartib

1. `wagon-mileage-run --dry-run`: `status_counts` va `held_reasons` ni ko'ring.
2. Kerak bo'lsa real run (bayroq bilan). `completed` bo'lishi shart.
3. `wagon-mileage-report --csv reports/wagon_mileage.csv`: `HELD` vagonlar sababini ko'ring.

Run oxirida invariantlar tekshiriladi (ledger km ≥ 0, bir davrda bir faol qator, projection faqat vagonga yoziladi). Buzilsa run `FAILED` (`mileage_calculation_runs.error`), projection yozilmaydi. Hisobot `locomotive_checksum_before/after` ni ko'rsatadi: jonli Wialon pull ayni vaqtda lokomotiv probegini oshirishi mumkin, shuning uchun bu qiymatlar farq qilsa, bu xato emas (run lokomotivga yozmaydi; buni invariant tekshiradi).

## 4. `HELD` sabablari va nima qilish

| Kod | Ma'nosi | Nima qilish |
|---|---|---|
| `gtk_link_missing` | Vagon GTK bilan bog'lanmagan | Aktivni GTK vagoniga bog'lash |
| `no_gtk_membership` | GTK sostavida hali ko'rilmagan | GTK sinxronlashni kutish |
| `approved_opening_balance_missing` | Boshlang'ich tasdiqlanmagan | Taklif qilish, boshqa admin tasdiqlasin |
| `no_calculated_period_yet` | Tasdiqlangandan keyin davr yo'q | Keyingi run |
| `no_linked_locomotive` | Lokomotiv aktivga bog'lanmagan | GTK lokomotivini bog'lash |
| `locomotive_has_no_wialon_readings` | Lokomotivda Wialon o'qishi yo'q | `wialon_id` bog'lanishini va sinxronlashni tekshirish |
| `no_eligible_locomotive_odometer` | Hisobga olinadigan o'qish yo'q | Sifat darvozasi rad sabablarini ko'rish |
| `locomotive_handoff_time_unknown` | Lokomotiv almashish vaqti aniq emas (D4) | GTK vaqtini kutish; qo'lda taxmin yo'q |
| `missing_odometer_sample_bracket` | Odometr nuqtalari yetarli emas | Ma'lumotni kutish (orqaga to'ldirish yo'q) |
| `odometer_sample_gap_exceeded` | 30 daqiqadan katta uzilish va harakat bor | Hisoblanmaydi |
| `reading_not_calculation_eligible`, `invalid_or_decreasing_odometer_sample`, `locomotive_bracket_mismatch` | O'qish sifati | `wialon_odometer_readings.rejection_reason` |
| `locomotive_distance_conflict` | Ikki lokomotiv farqi max(2 km, 5%) dan katta | Odometrlarni solishtirish |
| `wagon_membership_overlap` | Vagon bir vaqtda ikki sostavda | GTK ma'lumotini tekshirish |

To'liq ro'yxat va matnlar: `backend/app/services/wagon_mileage_reasons.py`.

## 5. Rebaseline va qaytarish

- Boshlang'ichni o'zgartirish: yangi taklif (`POST /wagon-mileage/openings`) va boshqa admin tasdig'i. Eski qiymat `superseded` bo'lib saqlanadi, tarix yo'qolmaydi. `effective_at` dan oldingi davrlar hisobga olinmaydi.
- Ledger qatorlari o'chirilmaydi: yangi hisob eskisini `superseded` qiladi.
- Qaytarish: run'ni to'xtatish uchun bayroqni `false` qoldiring (standart). Migratsiya qaytarish: `alembic downgrade -1` (faqat zaxiradan keyin, va faqat 0029 ma'lumotini yo'qotishga rozi bo'lsangiz).

## 6. Serverga chiqarish ro'yxati (YOZILGAN, BAJARILMAGAN)

1. Zaxira: `pg_dump -Fc`, faylni tekshirish (`pg_restore --list`), nusxa bazada migratsiyani sinash. Dump ichida Wialon token bor: maxfiy saqlang.
2. Kod chiqarish; entrypoint `alembic upgrade head` ni o'zi bajaradi. `alembic current` = `0029_wagon_mileage_ledger`.
3. Wialon host mask serverga moslangan bo'lishi kerak (serverning IP manzili Wialon token host maskasiga kiritilgan).
4. `WAGON_MILEAGE_ENGINE_ENABLED=false` bilan boshlang. Avval `wagon-opening-propose` (dry-run, keyin `--apply`), boshqa admin `wagon-opening-approve` (dry-run, keyin `--apply`).
5. `wagon-mileage-run --dry-run`, hisobotni ko'rish; keyin bitta qo'lda real run; `wagon-mileage-report`.
6. Faqat natija to'g'ri bo'lsa, bayroqni `true` qiling (davriy ishga tushish GTK sinxronlashdan keyin). Bir necha kun kuzating.
7. Lokomotiv probegi endi Wialon pull orqali o'sadi: birinchi kunlarda `mileage_history` (source=wialon) ni tekshiring.

## 7. PENDING qarorlar

- Vagon ТО-intervallari (me'yorlar keyin).
- `OPENING_BALANCE_ALLOW_SELF_APPROVAL`: sozlama yo'q, maker≠checker qat'iy.
- `WAGON_MILEAGE_IDLE_MIN_MINUTES` (30) va idle dalili (GTK holati ulanmagan).
- Lokomotiv ТО-rejasi: `reconcile_asset_plans` lokomotiv uchun 0 qaytaradi (test bilan mustahkamlangan); lokomotiv probegi qayta yozilgani uchun bu qaror qayta ko'rilishi kerak.

## Konfliktlarni hal qilish (2026-11-16)
Asos: 668 ta "bir xil xabar vaqti, har xil odometr" juftining hammasida keyingi qiymat KATTAROQ (kamayish 0), 666 tasi 150 km/soat chegarasiga sig'adi. Ya'ni hisoblagich xabar vaqti o'zgarmay oldinga yurgan, bu ma'lumot xatosi emas.

Yangi qoida (`wialon_quality.is_counter_advance`): bir xil xabar vaqtida YUQORIROQ qiymat kelsa va o'sish tezlik chegarasidan oshmasa, hisoblagich bloklanmaydi. Birinchi o'qish asosiy bo'lib qoladi, keyingisi `counter_advanced_same_message_time` sababi bilan HELD, o'sish keyingi yangi vaqtli o'qish bilan hisoblanadi. Kamaygan, noma'lum vaqtli yoki juda tez o'sgan bo'lsa, avvalgidek to'qnashuv.

Eski 50 ta blokni ochish (har doim avval ko'rish, `--apply`siz hech narsa o'zgarmaydi):
```
docker compose exec -T backend python -m app.cli wialon-counter-release
docker compose exec -T backend python -m app.cli wialon-counter-release --inv-number 37062 --actor-email <admin> --apply   # sinov: bitta lokomotiv
docker compose exec -T backend python -m app.cli wialon-counter-release --actor-email <admin> --apply                      # hammasi
docker compose exec -T -e WAGON_MILEAGE_ENGINE_ENABLED=true backend python -m app.cli wagon-mileage-run
```
Tarixni darvoza (`evaluate`) orqali qayta o'ynaydi; hisoblagich kamaygan bo'lsa blok qoladi (qo'lda tekshirish). Hisoblagich holati (`last_cnm`) o'zgartirilmaydi, shuning uchun lokomotiv probegi blok davridagi masofani keyingi o'qish bilan o'zi to'ldiradi. Har bir lokomotiv uchun bitta audit yozuvi.

Pasport raqamlari: GTK 8 xonali nolli raqam yuboradi (`00000069`), pasportda `69`. Endi bu to'qnashuv emas. Eski kutayotganlar:
```
docker compose exec -T backend python -m app.cli asset-conflicts-clean                                  # ko'rish
docker compose exec -T backend python -m app.cli asset-conflicts-clean --actor-email <admin> --apply
```
Faqat nol farqli yozuvlar "rejected" bo'ladi (pasport qiymati o'zgarmaydi). Haqiqiy farqli 4 tasi qoladi va UI'da qo'lda hal qilinadi.
