# Vagon ta'mirlari Excel fayli: dastlabki ko'rib chiqish (2026-11-24)

Fayl: `Downloads/Telegram Desktop/последная ремонт вагон-самосвал.xlsx`, varaq «Вагон-самосвал».
(«(2)» nusxasi bir xil, varaq ham bir xil.) Faqat o'qildi. Bazaga hech narsa yozilmadi.

## Tuzilishi
- 532 ta vagon-samosval qatori, 1 ta MOL qiymati («Начальник ЖДЦ-1»).
- Oxirgi ta'mir turi: **ДР** 487 ta, **КР** 45 ta.
- Ta'mir sanasi: 419 tasida Excel sanasi bor, 113 tasida yo'q.
- Probeg ustuni: **hammasi «-»** (0 ta raqam).
- Varaq «Лист1» da lokomotivlar ham bor (ПЭ2М). Ular vagon emas, alohida ko'rib chiqiladi.
- Shaxsiy ma'lumot (ФИО, табель): topilmadi. MOL ustuni faqat lavozim nomi.

## Eng muhim topilma: ustunlar sarlavhasi tizimga mos emas
Solishtirish natijasi (bazadagi 835 vagon bilan):

| Excel ustuni (sarlavha) | Haqiqatda nimaga mos | Mos kelgan qatorlar |
|---|---|---|
| «Инвентарный номер» (masalan 8099) | GTK **reg_number**; bazaning `serial_number` i | 530 / 299 |
| «Заводской/серийный номер» (masalan 37539) | bazaning **inv_number** i (asosiy inventar raqam) | **529 / 532** |
| «Гос.номер» | hamma «-» | 0 |

Demak, ikki ustun **almashib qolgan** ko'rinadi. Men buni 529 ta qatorda tasdiqladim (`inv_number` = «Заводской» ustuni). Qaror: tizimga kiritishda inventar raqam sifatida **«Заводской/серийный номер»** olinadi. Bu sizning tasdiqingizni talab qiladi.

## Tizimdagi holat (kiritishdan oldin)
- 529 ta vagon bazada bor (asosiy inv bo'yicha). 3 tasi topilmadi.
- Shu 529 tadan: **`last_maint_date` hammasida bo'sh**. Ya'ni Excel sanasi va turi tizimga to'liq yangi ma'lumot bo'ladi.
- Bazadagi probeg: 474 tasida 0 dan katta. Excelda probeg yo'q, shuning uchun **bazadagi probegga tegilmaydi**.

## Kiritish rejasi (taklif, hali bajarilmagan)
1. Inv raqam: «Заводской/серийный номер» → `fixed_assets.inv_number` (qat'iy moslik, faqat bitta vagon).
2. Oxirgi ta'mir: sana → `last_maint_date`, tur (ДР/КР) → `last_maint_type` (agar ustun yo'q bo'lsa, qo'shish sxemani o'zgartiradi, bu sizning tasdig'ingizni talab qiladi).
3. Probeg: kiritilmaydi (fayl bo'sh).
4. «Гос.номер» va «Инвентарный номер»: kiritilmaydi, chunki mapping noaniq; keyin alohida.
5. 113 ta sanasiz qator: o'tkazib yuboriladi, «sana yo'q» ro'yxatiga yoziladi.
6. 3 ta topilmagan vagon: ro'yxatga, qo'lda tekshiriladi.
7. Quruq yurish (dry-run) hisoboti, so'ng sizning tasdig'ingiz bilan yozish. Zaxira dump avval.

## Ochiq savollar (sizdan)
1. «Инвентарный номер» va «Заводской/серийный номер» almashgan degan xulosaga rozimisiz?
2. ДР va КР turlarini tizimdagi ish turlariga qanday bog'laymiz? (`work_types` jadvalida ДР/КР kodi hozircha yo'q.)
3. 113 ta sanasiz vagonni nima qilamiz: bo'sh qoldiramizmi?
4. «Лист1» dagi lokomotivlar (ПЭ2М) ham kiritilsinmi, yoki faqat vagonlarmi?
