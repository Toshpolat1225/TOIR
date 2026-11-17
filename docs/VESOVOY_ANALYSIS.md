# Vesovoy (vagon tarozisi) bazasi — tahlil (2026-11-17)

Manba: loyiha ildizidagi `Bridge_Scale 93.mdb` (285 MB) va `Bridge_Scale 97.mdb` (420 MB). Ikkalasi Jet 4 (Access 2000/2003) fayli. Tahlil nusxalar ustida, faqat o'qish rejimida o'tkazildi; asl fayllar o'zgartirilmadi. Fayllar `.gitignore` ga qo'shildi (`*.mdb`, `*.accdb`, `*.ldb`, `*.laccdb`): katta va ichida operator paroli bor, git'ga tushmasligi kerak. Hamma raqam buyruq natijasidan olingan; taxmin **GIPOTEZA** deb belgilangan.

## 1. Bu nima
Almalyk GMK, stansiya «Кольцевая»: **harakatdagi (dinamik) vagon tarozisi** `ТСД-ЖД «ИнфаТрэк»` (tarozi `ИТ-03-097-06`, so'nggi poverka 11.01.2007, xizmat ko'rsatuvchi `ЦЛАГ`) yozuvlari. Tarozi sostav o'tayotganda har bir birlikni tortadi va natijani Access'ga yozadi. Ikkala fayl bir xil dastur nusxasi (bir xil `Весы`, `Реквизиты`, `Грузы`, `Клиенты` jadvallari), lekin **ichidagi sostavlar deyarli kesishmaydi**. Egasi tasdiqladi: **93 va 97 ikki alohida kompyuter, ikki tarozi, ikki alohida temir yo'lda** (`\\192.168.19.93\Scales$` va `\\192.168.19.97\Scales$`, SMB1). Tarozi dasturi (`Scales.exe`) har oy arxiv yaratadi (`Archives\N. oy YYYY г.mdb`, 2025-01 … 2026-09) va jonli bazani qisqartiradi.

## 2. Jadvallar va mazmuni
Faqat 3 ta jadvalda haqiqiy ma'lumot bor.

| Jadval | Qator (93 / 97) | Mazmun |
|---|---:|---|
| `Составы` | 1 754 / 2 986 | Bitta tortilgan sostav: `Код состава` (PK), `Регистрация` (sana), `Номер состава`, `Количество вагонов`, `Вес`, `Вес по документам`, `Начало/Конец взвешивания`, `Код груза`, `Экскаватор`, `Расположение` (xom `.ecg` fayl nomi, masalan `17112026_1344.ecg`), `Направление`, `Статика или динамика`, `Номер весов`, `Погрешность` |
| `Вагоны` | 21 443 / 41 751 | Sostavdagi har bir tortilgan birlik: `Код вагона` (PK), `Код состава` (FK), `Номер по порядку`, `Вагон`, `Брутто`, `Тара`, `Нетто`, `Грузоподъемность`, `Перегруз`, `Скорость`, `Дата взвешивания`, `Осей`, o'qlar bo'yicha yuklama (8 o'q, chap/o'ng), `Телега1/2`, `Экскаватор` |
| `Грузы` | 7 | Yuk/karyer: 1 Кальмакыр, 2 С отвала, 3 Сары-Чеку, 4 Каульды, 5 Перевеска, 6 сбой весов, 7 УПЖТ ДСК |
| `Экскаваторы` | 26 | Ekskavator raqamlari (qaysi ekskavator yuklagan) |
| `Клиенты` | 3 | `МОФ ДЦ-1`, `МОФ ДЦ-2`, `Отвал` (sostavlarda `Код клиента` doim 0, ishlatilmaydi) |
| `Весы`, `Реквизиты предприятия` | 1 / 1 | Tarozi pasporti va sozlamalar (`Тара по умолчанию` 49 t, `Норма` 105 t, tezlik 0–7 km/s) |
| `Доступ` | 1 | Operator: tabel raqami, FIO, **parol ochiq matnda** (o'qilmadi, qiymati chop etilmadi) |
| `Станции`, `шахты`, `Составы`-dan boshqalar | 0 | Bo'sh (`Станции`, `шахты`, `Ошибки вставки` deyarli bo'sh, `Тенросиб` 1 ta bayroq) |

Bog'lanish: faqat `Вагоны.Код состава → Составы.Код состава`. Access'da rasmiy `Relationships` yo'q (`MSysRelationships` ga ruxsat yo'q), lekin ma'lumotda bog'lanish to'g'ri: `Количество вагонов` ning faktik qatorlar soniga mosligi 1446/1446 (93) va 2819/2819 (97). Yetim vagon qatorlari: 14 (93) va 558 (97); sostavi yo'q.

## 3. Ma'lumot profili (2026-10 dan boshlab; avvalgisi sinov/eski qoldiq)
- Oraliq: 93 — 10.2026…16.11.2026, 97 — 10.2026…17.11.2026 (bugun 13:44 gacha). 2009–2012, 2023, 2025 dagi yozuvlar sinov/qoldiq (ko'pi 0 vagonli).
- Sostavlar (vagonli): 93 — 1 446, 97 — 2 819. Kuniga 28–86 (median 59) sostav, bir sostavni tortish ~11,6 daqiqa (p90 30 daq).
- Sostav hajmi: 2 534 tasi **15 birlik**, 128 tasi 14, qolgani kichik.
- Yuk: 84% (2 514/2 986, 97-fayl) `33 = Кальмакыр`. Yo'nalish: 99,9% `1` (bitta yo'nalish).
- Yuklanish: tortilgan dumpkarlarning 35 220 tasi **yuklangan** (>20 t), 368 tasi bo'sh. Demak tarozi faqat **yuklangan reys** ni qayd etadi (karyerdan MOF ga).
- `Номер состава` = 71 ta alohida qiymat, asosan 3 xonali (`405`, `165`, `161`, `094`…), 63 ta 4 xonali (masalan `3202`).
- `Накладная` hech qachon to'ldirilmagan (0/2986). `Погрешность` doim 50.

## 4. Mantiq: nimani nimaga ko'rsatadi (isbotlangan)

**(a) `Номер состава` = bosh lokomotivning garaj raqami.** GTK da `gtk_trains.number` ham shu raqam (`ТА 360` → `360`), `gtk_locomotives.garage_number`. Vesovoy sostavlarining (05.11 dan keyin, 1 109 ta) **88% i** (979/1 109) vaqt va raqam bo'yicha GTK sostaviga topildi; 102 tasida raqam GTK lokomotivlarida yo'q (4 xonali `3202`… yoki xato), 28 tasida lokomotiv bor, lekin o'sha paytda sostavda emas.

**(b) 15 birlik = 2 tortuvchi agregat birligi + 13 dumpkar.** Isboti: 15 birlikli sostavda 1- va 2-pozitsiyaning 93% i `Тара` > 100 t (median 125,65 t), 3-pozitsiyada 18% (bular GTK ko'ra oddiy dumpkar; real chegara 115 t, 2026-11-17 dagi tuzatish); qolganlari `Тара = 49` (32 800 ta, ya'ni **standart tara**, haqiqiy emas). GTK sostavida 13 vagon bor: farq (GTK − Vesovoy) **−2 ni 928/979 holatda** beradi. Qoida: pozitsiya 1–2 (tara>100) — `ТА` lokomotiv/motor birligi, pozitsiya 3…15 — dumpkarlar (GTK `carriage`).

**(c) Sostav `Вес` hisobi.** Aniq formula: `Вес = ΣБрутто (hamma birlik) − 736` (n=15 uchun, ~15×49). Ya'ni sostav og'irligiga tortuvchi agregatlar ham standart tara bilan qo'shilgan. Natija: `Вес` haqiqiy yukdan ~190–260 t (12–16%) **ko'p**. Haqiqiy yuk = faqat dumpkarlar `Нетто` yig'indisi.

**(d) Vagon `Нетто`** = `Брутто − Тара` (41 124 qatorning hammasida mos). `Тара` 49 standart bo'lgani uchun dumpkar `Нетто` taxminiy. `Нетто` median 108 t va 60% qatorda 105 t (`Грузоподъемность`) dan oshadi: bu ko'p yuklash (`Перегруз` ustuni shu farq, manfiy = yetishmaydi).

**(e) `Вагон` ustuni vagon raqami emas**: u sostavdagi tartib raqamining matni (`'1'…'30'`), 40 454/41 124 holatda `Номер по порядку` bilan teng. **Tarozi vagonni raqami bilan aniqlamaydi.** Vagon shaxsi faqat GTK tarkibi orqali olinadi.

## 5. TOIR bilan bog'lash algoritmi (prototip, faqat o'qish; kodga qo'shilmagan)
```
Vesovoy sostavi S (Номер состава=N, vaqt oynasi [Начало, Конец])
 1. lokomotiv:  gtk_locomotives.garage_number == N  →  gtk_trains.number == N
                (gtk_train_members, kind='locomotive', is_main, oraliq [observed_from, observed_to] S oynasi bilan kesishadi)
                → TOIR aktivi: asset_source_links (source='gtk') orqali fixed_assets (lokomotiv)
 2. vagonlar:   shu sostavning kind='carriage' a'zolari (xuddi shu vaqt kesishmasi)
                → gtk_carriages.gtk_id → asset_source_links → fixed_assets (vagon)
 3. pozitsiya:  Vagoni.Номер по порядку 1–2 (Тара>100) o'tkaziladi (tortuvchi agregat);
                3..15 ↔ GTK vagonlari (tartibi `ord`; yo'nalish tekshirilmagan)
 4. har bir dumpkar reysi:  { asset_id, vaqt, Нетто, Перегруз, karyer(Код груза), ekskavator, lokomotiv_asset_id }
```
Sinov natijasi: topilish 88%; tarkib hajmi 13 = 15−2 → 928/979. Cheklovlar: GTK tarkibi tarixi faqat **04.11.2026 dan** (13 kun); 05.11 gacha bo'lgan Vesovoy reyslari vagonga bog'lanmaydi. 401 bog'lanmagan aktivning vagonlari uchun (xaritadagi kabi) reys ham hisoblanmaydi.

Vaqt mintaqasi: Access'dagi vaqt naive (zonasiz). UTC yoki Toshkent (+5) deb olsa ham moslik deyarli bir xil (979 va 976), ya'ni farq sezilarli emas; aniq zonani tekshirish kerak.

## 6. Nima uchun foydali (taklif, qaror kutiladi)
1. **Ish bo'yicha eskirish:** vagon uchun real ish o'lchovi: reyslar soni va tashilgan tonna (hozirgi probeg/GTK km dan farqli, vagonning haqiqiy yuklanishi). ТО rejasiga `interval_tons`/`interval_trips` turidagi interval qo'shish mumkin (yangi migratsiya, tasdiq kerak).
2. **Ko'p yuklash nazorati:** 60% qatorda `Нетто` > 105 t: vagon/lokomotiv bo'yicha ko'p yuklash tarixi va ekskavator/karyer kesimi, xavf bahosiga (ML) kirish.
3. **Lokomotiv ishi:** lokomotiv bo'yicha reyslar va tonnalar (hozir faqat probeg bor).
4. **Tarozi sifati:** sostav `Вес` va dumpkar `Нетто` yig'indisi orasidagi farq; yetim vagonlar; `сбой весов` yuki; poverka muddati (2007) ogohlantirishi.

## 7. Ochiq savollar (yangilangan: 93/97 javobi olindi; qolganlari `docs/SCALES_ARCHITECTURE.md` da hal qilingan)
1. 93 va 97 nima? Ikkita tarozi posti/yo'l mi, yoki ikki kompyuter/smena? Ikkalasi bir xil tarozi raqami (`ИТ-03-097-06`) ni ko'rsatadi, lekin ma'lumoti boshqa.
2. Haqiqiy dumpkar tarasi qancha? 49 t standart; boshqa tara (masalan 27 t, 82 t) bo'lgan qatorlar bor. Qaysi biri haqiqiy?
3. Nega tortuvchi agregat ham tortiladi va `Вес` ga qo'shiladi? Hisobotda qaysi ko'rsatkich (Вес yoki Нетто yig'indisi) rasmiy?
4. Fayllarni TOIR ga qanday olib kelamiz? Docker (Linux) ACE drayverini o'qiy olmaydi: variantlar — (a) Windows'da davriy eksport (CSV/`pyodbc` skript) va TOIR ga yuklash, (b) Access'ni PostgreSQL'ga o'tkazish, (c) 4 xonali `Номер состава` (`3202`…) qaysi lokomotiv ekanini aytish.
5. Eski yozuvlar (2009–2012, 2023, 2025) kerakmi yoki sinov qoldig'imi?

## 8. NOT TESTED / cheklovlar
- Haqiqiy `.ecg` xom fayllari va tarozi dasturi ko'rilmadi; faqat Access mazmuni.
- Tara/yuklanish ma'nolari ma'lumotdan chiqarilgan (GIPOTEZA), egasi tasdiqlamagan.
- Vagon darajasidagi to'liq bog'lash (`asset_source_links` orqali TOIR aktivigacha) ishlab chiqilmagan; sinov faqat sostav va tarkib hajmi darajasida.
- Hech narsa TOIR ga yozilmadi; baza va kod o'zgartirilmadi.
- Nusxalar scratchpad'da (`.../scratchpad/mdb/`); kerak bo'lsa o'chiriladi.
