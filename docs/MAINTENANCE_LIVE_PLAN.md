# «Tirik reja» — ТО rejalash modeli (runbook)

Holat: joriy etilgan 2026-11-16 (migratsiya `0032_tirik_reja`). Loyiha taklifi: artifact «Tirik reja modeli».

## Asosiy qoida
**Majburiyat yo'qolmaydi.** Reja holatini o'zgartiradi (bloklanadi, qamrab olinadi, o'tkazib yuboriladi), lekin o'chirilmaydi; har bir o'zgarish «qarorlar jurnali»da qoladi.

## Qanday hisoblanadi
- **Hisob boshi = oxirgi ТО** (`asset_maintenance_baseline`), qat'iy panjara emas. km — TOIR shkalasida (kuzatuv boshlangandan beri); ТО kuzatuvdan oldin bo'lgan bo'lsa manfiy bo'ladi.
- **Temp** har bir texnika uchun alohida: oxirgi 30 kunning kunlik o'sishi, p25/p50/p75. Ma'lumot kam bo'lsa guruh tempiga tortiladi (`n/(n+7)`), umuman bo'lmasa `maintenance_settings.daily_average_km`, u ham bo'lmasa 200.
- **Uch sana**: `dateEarly` (p75, ehtiyotkor — shu kungacha bajarilsin), `dateTypical` (p50), `dateLate` (p25). **Oyna** = ehtiyotkor sana − `lead_days`; oyna ochilganda reja yaratiladi.
- **Допуск** (`tolerance_pct`): limitdan oshishga ruxsat. Undan tashqari ko'chirish faqat admin tasdig'i bilan.
- **Kaskad (`rank`)**: yuqori daraja bajarilsa, pastlari `covered` bo'ladi va hisobi shu nuqtadan boshlanadi. `rank` bo'sh = mustaqil. Standart: ТО-1=1 … ТО-3=3, ТР-1=4 … ТР-3=6, СР=7, КР=8.
- **Birlashtirish**: past daraja yuqorisidan oldin `maintenance_merge_pct` (15 %) ichida tushsa, bir tashrifga birlashtiriladi.
- **Ustuvorlik 0–100** (vazn: vaqt 40, oqibat 20, salomatlik 15, kechiktirishlar 10, tayyorlik 10, kalendar 5; limitga yetgan ≥ 80) va sababi oddiy tilda.
- **Ishonch**: `high` / `low` (taxminiy hisob boshi yoki ma'lumot kam) / `stale` (datchik 24 soatdan beri jim yoki sensor_failure).

## Vagonlar: qaysi probeg ishonchli hisoblanadi
Qaror D9: vagon probegi (`fixed_assets.mileage`) = administrator **tasdiqlagan boshlang'ich** + hisobga yaroqli `CONFIRMED` **va** `ESTIMATED` ledger km. Shuning uchun reja vagon km'ini tasdiqlangan boshlang'ich probeg (`wagon_mileage_opening_balances.status='approved'`) bo'lsa ishonchli deb oladi (`mileage_repository.has_approved_projection`; reja, naryad va ML bir xil qoidadan foydalanadi). Avval «kamida bitta `CONFIRMED` ledger qatori» talab qilinardi: bu qoida D9 dan oldin yozilgan edi va 481 vagondan 480 tasini tashlab yuborardi.
- Probegi `ESTIMATED` km'dan iborat vagonlar «Прогноз приблизительный» belgisi bilan chiqadi (`mileageEstimated`), hech qachon «надёжный» emas.
- Tasdiqlangan boshlang'ich yo'q vagon (ledger bo'lsa ham) km majburiyatiga ega bo'lmaydi: probeg e'lon qilinmagan.
- **Vagon tempi `wagon_mileage_ledger` dan olinadi** (`_wagon_ledger_rates`): tasdiqlangan boshlang'ichi bor har bir vagon uchun kunlik km. Ledger qoplagan oyna ichida km'siz vaqt = bekor turish (0), oynadan tashqari = noma'lum. Faqat qisman kuzatilgan kun (birinchi/oxirgi) kuzatilgan ulushga ko'ra shkalalanadi (`partial_day_rates`), 25 % dan kam kuzatilgan kun tashlanadi. Ma'lumot kam bo'lsa temp vagonlar guruhiga tortiladi (guruh 1 kunlik ma'lumotdan boshlab tuziladi, lokomotivlarda 3 kun). 7 kundan keyin vagon o'z tempi bilan ishlaydi, shu paytgacha ishonch «low».
- Cheklov: ledgerda `HELD` (hisoblab bo'lmagan) davrlar bekor turish sifatida hisoblanadi, shuning uchun temp bir oz past chiqishi mumkin.

## Holatlar
`scheduled → in_progress → completed`; `blocked` (sabab bilan), `covered` (yuqori ТО qamrab oldi), `waived` (admin o'tkazib yubordi), `cancelled` (faqat tizim: nogiron aktiv). PATCH orqali `cancelled` — 409.
- Naryad bekor qilinsa/o'chirilsa reja `scheduled` ga qaytadi; naryad tugasa `completed` + yangi hisob boshi + kaskad.
- Ruxsatlar: operator va admin ko'chiradi/bloklaydi; **operator** допуск'dan tashqariga yoki 3-ko'chirishga o'tolmaydi (admin tasdig'i); `waive` faqat admin.

## Buyruqlar (backend konteyneri ichida)
```
python -m app.cli maintenance-shadow-report          # faqat o'qish: tizim nimani ko'ryapti
python -m app.cli maintenance-health [--fix]         # invariantlar (--fix faqat xavfsizlarini tuzatadi)
python -m app.cli maintenance-baseline-import --file baza.csv [--apply]   # sukut bo'yicha dry-run
```
CSV ustunlari: `inv_number,interval_code,done_at,odometer_km,km,hours,note` (`odometer_km` — pasportdagi/Wialon real ko'rsatkich, tizim TOIR shkalasiga o'zi aylantiradi; yoki `km` — to'g'ridan-to'g'ri TOIR shkalasida; ikkalasi birga bo'lmaydi). Sana `YYYY-MM-DD`.

## Fon ishi
Har soatda (`MAINTENANCE_JOB_INTERVAL_MINUTES`, o'chirish: `MAINTENANCE_JOB_ENABLED=false`): hisoblagich snapshot (`asset_meter_daily`) → muddati o'tgan blok/uzilishlarni tuzatish va nogiron rejalar → hamma aktivni qayta rejalash. Bitta transaksiya, advisory lock — bir necha worker bo'lsa ham bittasi ishlaydi.

## API
`GET /maintenance-kpis`, `GET|POST /maintenance-disruptions`, `POST /maintenance-disruptions/{id}/close`, `GET|PUT /maintenance-baselines`, `POST /maintenance-plan/{id}/block|unblock|waive`, `GET /maintenance-plan/{id}/decisions`, `GET /maintenance-health`. Jadval javobi (`/maintenance-schedule`) markerlar, ishonch, ustuvorlik va sabablarni qo'shadi.

## Joriy etish natijasi (2026-11-16)
- Jonli baza nusxasida (213 MB zaxiradan) sinaldi: up/down/up, ikki marta ishga tushirish farqsiz, nosozlik 0.
- Jonli: 87 aktiv, 775 majburiyat; barchasining hisob boshi **taxminiy** (`provisional`) — shuning uchun «Прогноз приблизительный». Limitga yetgani 0, oyna ochilgani 1 (38390, `test`).
- Temp ma'lumoti faqat 2026-11-09 dan beri (6 kun) — `n_days < 7`, shuning uchun hammasi «blend»; 7 kundan keyin o'zining tempi bilan ishlaydi.
- 14 ta mavjud reja sanasi haqiqiy tempga qarab yangilandi (avval hammasi 2026-11-19 edi).

## Foydalanuvchi bergan bo'lishi kerak (kod buni o'zi topa olmaydi)
1. Har bir lokomotivning har bir ТО turi bo'yicha oxirgi bajarilgan sana va pasport/1С probegi → `maintenance-baseline-import`.
2. Kaskad xaritasini (qaysi ТО qaysini qamrab oladi) va допуск/`lead_days` qiymatlarini tasdiqlash (standart qiymatlar migratsiyada qo'yilgan).
3. Dizellar uchun moto-soat limitlari (`interval_hours`) — ma'lumot (`cneh`) bor, limit yo'q.
4. Vagonlar uchun haqiqiy me'yorlar (hozir faqat `test`), brigada/pozitsiya sig'imi, ombor qoldig'i.

## Orqaga qaytarish
Zaxira: `backups/pre0032_20261116_181356.dump` (git'da yo'q). `alembic downgrade 0031_plan_manual_date`: `blocked → scheduled`, `covered/waived → completed`; yangi jadvallar o'chadi (baza, qarorlar, uzilishlar, snapshotlar — ma'lumot yo'qoladi).
