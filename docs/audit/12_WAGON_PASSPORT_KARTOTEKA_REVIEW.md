# Vagon pasport kartotekasi: dastlabki ko'rib chiqish (2026-11-24)

Fayl: `OneDrive/Рабочий стол/Новая папка (5)/Электрон картотека ВАГОН 2026надзор - Тошпулат.xls`
Faqat o'qildi. Bazaga hech narsa yozilmadi.

## Tuzilishi
Varaqlar (jami 1039 qator):
- **2ВС-105**: 698 qator (vagon-samosval)
- **6ВС-60**: 137 qator
- **Платформа**: 130 qator
- **Хоппера**: 44 qator
- **Цистерна**: 30 qator (boshqa ustunlar: «Дата последних плановых ремонтов», ДР/КР yo'q)
- «Лист1» (turlar jadvali), «2021», «Лист2»: kartoteka emas, tahlil qilinmadi.

Har varaqda ustunlar boshqacha joylashgan. Sanalar Excel sanasi ko'rinishida.
ДР va КР sanalari bor (2ВС-105, 6ВС-60, platforma, xopper). Ta'mir sanasi oralig'i: ДР 2017–2026, КР 1995–2026, kelajak sanasi yo'q.
Shaxsiy ma'lumot (ФИО, табель) topilmadi. «Кем продлен» ustunida tashkilot nomlari.

## Tizim bilan moslik
- Kartotekadagi noyob inventar raqam: **1025**.
- Bazadagi faol vagonlar (`fixed_assets`) bilan mos: **988**.
  - vagon: 835 (bazadagi 835 vagonning **hammasi** kartotekada bor)
  - sisterna (tank_car): 129
  - platforma: 24
- Kartotekada bazaga mos kelmagan: **37** raqam (1025 − 988). Ular qo'lda tekshiriladi.
- Bazada `last_maint_date` mos qatorlarda **hammasida bo'sh**. Ya'ni kartoteka ta'mir sanalarini birinchi marta kiritadi.

## Oldingi fayl («последная ремонт вагон-самосвал») bilan solishtirish
- Ikki faylda umumiy inventar raqam: 529.
- Oldingi faylning ДР sanasi bilan kartotekaning ДР sanasi **bir xil emas** (mos kelgan 0 ta).
- Kartoteka sanasi yangiroq: 366 ta.
- Oldingi fayl yangiroq bo'lgan holat: 0 ta.
- Xulosa: bu ikki fayl bir xil ma'lumot emas, yoki ularning sana ma'nosi boshqacha. Kartotekani asosiy manba deb olish tavsiya qilinadi, lekin buni siz tasdiqlashingiz kerak.

## Tekshirilishi kerak bo'lgan qatorlar
- **14 ta inventar raqam** kartotekada ikki marta uchraydi. 13 tasida ikkala qator bir xil, 1 tasida sanalar farq qiladi (masalan, 33-9909 modelida ДР 2025-05-14 va 2025-12-02). Qaysi biri to'g'ri, siz hal qilasiz.
- **37 ta** bazada topilmagan raqam.

## Oldingi xulosa tasdiqlandi
Oldingi faylda «Инвентарный номер» va «Заводской/серийный номер» almashgan degan xulosa bu kartotekada ham to'g'ri: inventar raqam «Инв. №» ustunida (masalan 37539), va u bazaning `inv_number` iga mos.

## Kiritish rejasi (taklif, hali bajarilmagan)
1. Inventar raqam bo'yicha aniq moslik (`inv_number`). Bitta raqam bitta vagonga.
2. Har vagon uchun oxirgi ДР va КР sanasi → `last_maint_date` (eng so'nggi ta'mir sanasi) va tur. Tur ustuni tizimda yo'q, qo'shish sxemani o'zgartiradi (sizning tasdig'ingiz kerak).
3. Bazadagi probegga tegilmaydi (kartotekada probeg yo'q).
4. 14 ta ikki martalik va 37 ta topilmagan qator o'tkazib yuboriladi, alohida ro'yxatga.
5. Quruq yurish, keyin yozish, zaxira dump bilan.

## Sizdan javob kerak
1. Ikki fayldan qaysi biri ishonchli? Kartoteka (2026) asosiy manbami?
2. ДР/КР sanasi «oxirgi ta'mir sanasi» ekanini tasdiqlaysizmi?
3. 14 ta ikki martalik raqam va 37 ta topilmagan vagon uchun nima qilamiz?
4. Цистерна varag'idagi «Дата последних плановых ремонтов» ham kiritilsinmi?
