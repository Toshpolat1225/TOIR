# «ЖДЦ-1 ПТОВ готов.xlsx»: ko'rib chiqish (2026-11-24)

Fayl: `docs/templates/вагон/ЖДЦ-1 ПТОВ готов.xlsx`, varaq «Лист1». Faqat o'qildi. Bazaga hech narsa yozilmadi.
(Oldingi ikki fayl bilan solishtirilmadi: bu alohida, yangi manba.)

## Tuzilishi
529 qator, hammasi **ЖДЦ-1**, hammasi «Вагон-самосвал 2ВС-105».
Ustunlar: №, Наименование, Производитель, Зав.номер, **Инв. №**, Год постр., Участок, **«Охирги ПТОВ ремонт»** (oxirgi ПТОВ ta'miri sanasi).
Boshqa ustunlarda ma'lumot yo'q. Shaxsiy ma'lumot yo'q.

## Bazaga moslik (inventar raqam = `fixed_assets.inv_number`)
- Noyob inventar raqam: **529**, takrori yo'q.
- Bazadagi vagonga mos: **529 / 529**. Hammasi `wagon`, hammasi «operational», hech biri hisobdan chiqarilmagan.
- Bazadagi uchastka: **hammasi ЖДЦ-1**. Faylning uchastkasi bilan mos.
- Bazada ЖДЦ-1 vagonlari 529 ta, faylda ham 529: **qoldirilgani yo'q**.
- Mos vagonlarning `last_maint_date` maydoni **hammasida bo'sh**: fayl birinchi marta to'ldiradi.

## Sanalar
- To'g'ri `dd.mm.yyyy`: 482 ta (ba'zilarida oxirida nuqta: «12.11.2026.»).
- Ikki xonali yil `dd.mm.yy` (masalan «06.11.26»): 42 ta. Bularni 2026 deb o'qish mumkin.
- Bo'sh: 5 ta.
- Oraliq: 2016-11-12 … 2026-11-22. Kelajak sanasi yo'q.
- Shubhali: **2 ta eski sana**: inv 38220 → `07.10.2023`, inv 38531 → `12.11.2016`. Ikkinchisi «2026» ning xatosi bo'lishi mumkin (boshqa sanalarning hammasi 2026 noyabr atrofida).

## Nima haqida ma'lumot
«ПТОВ» ta'miri ДР yoki КР emas, balki alohida tur (oraliq texnik xizmat). Tizimda vagonlar uchun ТО intervali **yo'q**. Faqat bitta umumiy `last_maint_date` maydoni bor (tur saqlanmaydi).

## Kiritish rejasi (taklif, hali bajarilmagan)
1. Inventar raqam bo'yicha aniq moslik. 529 ta vagon.
2. Sana → `fixed_assets.last_maint_date`. Sxema o'zgarmaydi.
3. `dd.mm.yy` → 20yy. Oxiridagi nuqta olib tashlanadi.
4. Bo'sh sanali 5 ta va shubhali 2 ta qator o'tkazib yuboriladi, alohida ro'yxatga.
5. Probegga va boshqa maydonlarga tegilmaydi.
6. Quruq yurish hisoboti, keyin siz tasdiqlaysiz, zaxira dump bilan.

## Sizdan javob kerak
1. Sana «oxirgi ПТОВ ta'miri»: uni `last_maint_date` ga yozish to'g'rimi? (Tizimda ПТОВ turi alohida saqlanmaydi.)
2. 2 ta shubhali sana (38220, 38531): o'tkazib yuboramizmi yoki to'g'rilaysizmi?
3. 5 ta bo'sh sana: bo'sh qoldiramizmi?
4. ЖДЦ-2 va boshqa uchastkalar uchun ham shunday fayl bo'ladimi?
