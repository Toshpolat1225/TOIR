# Vagon ta'mir me'yorlari (norma) fayllari: tahlil (2026-11-24)

Papka: `docs/templates/вагон/`, 8 ta fayl «Норма расхода на ДР/КР … на 2027 г.». Faqat o'qildi. Bazaga hech narsa yozilmadi.
Imzo qatorlaridagi shaxs ismlari tahlilga olinmadi va hech qayerga yuborilmadi.

## 1. Bu qanday ma'lumot
Har fayl = **bir tur vagon × bir tur ta'mir** uchun «bir dona vagonga material va ehtiyot qismlar sarfi me'yori»: nomi, birligi, miqdori.

| Fayl | Asosiy varaq | Satrlar (me'yor) |
|---|---|---|
| ДР 2ВС-105 | «2025» | 213 |
| ДР 6ВС-60 | «2023» | 177 |
| ДР платформа | «2023» | 119 |
| ДР цистерна | «2025» | 106 |
| КР 2ВС-105 | «2025» (va «2023») | 200 |
| КР 6ВС-60 | «2025» | 175 |
| КР платформа | «2023» | 129 |
| КР цистерна | «2025» | 122 |

Jami **1 241 me'yor satri**, **451 ta noyob material nomi** (148 tasi faqat bitta faylda, 20 tasi hamma 8 faylda).
Bo'limlar: «Материаллар» (materiallar) va «Запасные части» (o'zbekcha: Ehtiyot qismlar) (ehtiyot qismlar).

## 2. Tizim bilan solishtirish (hozirgi holat)
- Tizimda me'yor jadvallari **bo'sh**: `nomenclature` 0, `nomenclature_norms` 0, `work_type_templates` 0.
- Ish turlari bor: **ДР** va **КР** (boshqalar bilan 16 ta).
- Bazadagi modellar fayllarga **aynan mos**: 2ВС-105 (698 texnika), 6ВС-60 (137 texnika); platforma va sisterna modellari ham bor.
- Me'yor tizimda `(nomenklatura, uchastka, ish turi)` bo'yicha saqlanadi. **Vagon turi/modeli o'lchovi yo'q**, ya'ni «2ВС-105 uchun ДР» va «6ВС-60 uchun ДР» ni ajratib bo'lmaydi.
- Faylda **narx yo'q**; me'yor jadvalida `avg_price` bor. Narxsiz «нормативные затраты» hisoblanmaydi.

## 3. Nega kerak (foyda)
1. **Naryad (наряд-заказ) tekshiruvi:** naryadda sarflangan material me'yordan oshganini avtomatik aniqlash (`norm-check` allaqachon bor, lekin me'yor yo'q).
2. **Analitika:** «Нормативные затраты» va «Экономия/Перерасход» kartochkalari hozir 0 ko'rsatadi, chunki me'yor bo'sh.
3. **Rejalash:** ta'mirga kirayotgan vagonlar uchun kerakli material ro'yxatini oldindan hisoblash (omborga talab).
4. **ТМЦ shablonlari:** naryad yaratishda materiallarni avtomatik to'ldirish.

## 4. Topilgan muammolar va qarorlar kerak bo'lgan joylar
1. **Imzo qatorlari (22 ta)** oxirida shaxs ismlari va lavozimlar («Тулдибаев С.И.», «ИЧТБ начальник» (lavozim nomi)…). Import qilinmaydi.
2. **Miqdor formatlari:** oddiy son 1 275 ta; «dona/kg» ko'rinishidagi 124 ta («12/1,44-2,4» = 12 dona, og'irligi 1,44–2,4 kg); boshqacha 41 ta («20./5», «10/15-16,6-18,6» = quvur qalinligiga qarab); diapazon 2 ta; bo'sh 25 ta (imzo qatorlari). Tizimda faqat bitta son (`standard_quantity`) bor, shuning uchun asl matn alohida saqlanishi kerak.
3. **Birliklar:** «дона», «шт», «шт.» bir narsa; «дона/кг», «м/кг», «кг/дона» juft birliklar (8 ta nomda bir xil material turli birlik bilan yozilgan, masalan «болт М12»).
4. **Muqobil satrlar (37 ta)** «при замене на …» («Сталь лист δ 4» o'rniga «δ 3»): asosiy materialning muqobili. Tizimda bunday tushuncha yo'q.
5. **Yillar:** fayl nomi «2027», lekin varaqlar «2023» va «2025». КР 2ВС-105 da ikkala varaq bor: 53 qator faqat bir tomonda, 3 tasida miqdor farq qiladi. Qaysi varaq amaldagi?
6. **Qo'shimcha varaqlar** (КР 2ВС-105): «локолизация» (2013–2020 yillar bo'yicha 1/bo'sh belgilar, me'yor emas) va «процент». Me'yor deb olinmaydi.
7. **Til:** o'zbek kirill va rus aralash (nomlar, bo'limlar). Interfeys ruscha; matnlar asl holida saqlanadi.
8. **Takror:** «кронштейн борта» ДР 2ВС-105 da ikki marta.
9. **Uchastka:** `nomenclature` va me'yor uchun `department_id` majburiy. Qaysi uchastka (masalan, «Участок ВРП»)?

## 5. Migratsiya rejasi (taklif, hali bajarilmagan)
**A. Sxema (tasdiq kerak):** `nomenclature_norms` ga: vagon turi (`asset_type`) va ixtiyoriy model (`asset_model_id`); asl matn (`quantity_text`, masalan «12/1,44-2,4»); muqobil belgisi (`alt_for_id`); izoh. Noyoblik kaliti shunga mos kengaytiriladi.
**B. Import (CLI, dry-run standart):**
  1. Faqat asosiy varaqlar; imzo, bo'sh va qo'shimcha varaqlar tashlanadi.
  2. Nomlar normallashtirib, `nomenclature` ga bir marta yoziladi (451 ta).
  3. Har satr → norma: tur/model + ДР/КР + uchastka + miqdor (birinchi son) + asl matn.
  4. «при замене» satrlari muqobil sifatida bog'lanadi.
  5. Hamma narsa «Миграция данных» jurnaliga yoziladi (ko'rish, tahrirlash, qaytarish).
**C. Tekshiruv:** quruq yurish hisoboti (nechta material, nechta norma, tushunarsiz qatorlar ro'yxati), keyin tasdiq, zaxira dump bilan yozish.
**D. Narx:** alohida bosqich (1С yoki qo'lda), shundan keyin analitika qiymatlarni ko'rsatadi.

## 6. Sizdan javob kerak
1. 5-band: qaysi varaq amaldagi (men 2025 ni taklif qilaman)?
2. 9-band: me'yor qaysi uchastkaga tegishli?
3. 4-band: muqobil satrlarni kiritamizmi, yoki faqat asosiy materiallarni?
4. Narxlar qayerdan olinadi (keyinroq, 1С fayli)?
5. Sxema o'zgarishiga (A) rozimisiz?
