# Vesovoy (tarozi) integratsiyasi — arxitektura va mantiq

Maqsad: ikki temir yo'l tarozisi (93 va 97 kompyuter, har biri o'z yo'lida) natijalarini TOIR ga **doimiy, avtomatik** olib kelish, ularni GTK (sostav, lokomotiv, vagonlar) va ОС bilan bog'lash va natijada har bir lokomotiv va vagon uchun **haqiqiy ish** (reys, tonna) hisoblash. Ma'lumot noto'g'ri bo'lsa, tizimda to'g'rilanadi va to'g'rilash **o'tmishga ham** o'zi qo'llanadi. Tarozi tahlili: `docs/VESOVOY_ANALYSIS.md`.

## 1. Qismlar

```
 Tarozi PC 93 ─┐  \\192.168.19.93\Scales$\Bridge_Scale.mdb   (SMB1, Access 2000, tarozi dasturi yozadi)
               ├─► KOLLEKTOR (Windows, TOIR serveri bilan bir kompyuter)        scripts/scales_collector/collector.py
 Tarozi PC 97 ─┘     • faqat o'qiydi (ReadOnly), har 60 s; id bo'yicha "suv belgisi" + oxirgi ~120 sostavni qayta o'qish
                     • kuniga 1 marta oxirgi 3 kunni qayta o'qiydi; arxivlarni (oylik .mdb) bir marta yuklaydi
                     • parol Windows Credential Manager'da, token foydalanuvchi muhit o'zgaruvchisida
                                   │  POST /api/v1/scales/ingest  (Bearer token, ≤ 4 MB, takrorlanuvchi)
                                   ▼
 BACKEND  routers/scales.py ─► services/scales.py ─► (xom jadvallar)  scale_posts, scale_trains, scale_weighings
                                   │                       ▲
                                   │  rematch(): hamma hosila ma'lumotni QAYTA hisoblaydi
                                   │     kirishlar: xom qatorlar + GTK tarkib tarixi + ОС↔GTK bog'lar + OPERATOR TUZATISHLARI
                                   ▼
                      hosila: unit_kind, dump_count, net_total_t, loco_asset_id, gtk_train_id, scale_train_carriages,
                              match_status, flags       ──►  /scales/status, /trains, /unmatched, /assets/{id}/work, /summary
                                   ▲
 UI  /dashboard/scales «Весовая»: holat kartalari (jim tarozi signali), reyslar, «Не распознано» (taklif + 1 bosish), korrektirovkalar
```

Nega bunday: (1) Access drayveri va SMB1 faqat Windows'da; (2) push modeli Wialon ingest bilan bir xil (token, takrorlanuvchi); (3) **xom ma'lumot o'zgarmaydi, hosila har safar qayta hisoblanadi**, shuning uchun tuzatish, yangi GTK bog'i yoki yangi alias o'tmishga ham ta'sir qiladi va "to'g'rilash" uchun alohida skript kerak emas.

## 2. Ma'lumot oqimi
- **Jonli:** har 60 s `Составы` (`Код состава` > oxirgi − 120) va `Вагоны` (`Код вагона` > oxirgi − 1500) o'qiladi. Operator sostavni tortgandan keyin tuzatsa, qayta o'qish buni ushlaydi; `row_hash` o'zgarsa qator yangilanadi va qayta moslanadi.
- **Chuqur qayta o'qish:** har kuni 03:30, oxirgi 3 kun.
- **Arxiv/tarix:** `Archives\N. oy YYYY г.mdb` (2025-01…2026-09) kichik nusxa qilib o'qiladi (`--backfill-archives`), jonli bazaning o'zi `--backfill-live`. Kalit `(tarozi, Код состава)` arxiv va jonli bazada bir xil id fazosi (uzluksiz o'sadi): ikki marta kelsa bitta qator.
- **Yurak urishi:** bo'sh o'tishda ham yuboriladi: `last_pull_at` shuni ko'rsatadi (kollektor o'ldi-yo'qligi).
- Vaqt: tarozi mahalliy vaqtni zonasiz yozadi; `SCALES_UTC_OFFSET_HOURS` (standart +5).

## 3. Moslashtirish algoritmi (`scales_matching.py`, DB'siz, test qilingan)
1. **Birlik turi:** `Тара ≥ 100 t` → tortuvchi agregat birligi (`traction`), qolgani dumpkar (`dump`).
2. **Yuk massasi:** `Σ Нетто` dumpkarlar (faqat to'liq qatorlar bo'lsa). Qatorlar yo'q/to'liq emas bo'lsa: `Вес − offset`, bunda `offset` = oxirgi 60 kunda to'liq sostavlar uchun `Вес − Σ Нетто` medianasi (kamida 20 sostav), tarozi uchun alohida. Bunday massa `estimated` deb belgilanadi (UI'da «≈»). Offset keyin paydo bo'lsa, tonnasi noma'lum sostavlar o'zi qayta hisoblanadi.
3. **Lokomotiv:** `Номер состава` normallashtiriladi (bo'sh joy, harf kattaligi); avval operator **alias**, keyin GTK `garage_number` (aniq, keyin oldingi nollarsiz). Lokomotiv ОС = GTK lokomotiv bog'i (`asset_source_links`, tur bo'yicha: GTK lokomotiv va vagon id fazolari har xil).
4. **GTK sostavi:** shu lokomotiv bosh a'zo bo'lgan sostav, tortish oynasi (`boshlanish−15 daq … tugash+15 daq`, GTK kuzatuvi ~10 daqiqada bir) bilan eng uzoq kesishgani; **tarkib tarixi** (`observed_from/to`) ishlatiladi, shuning uchun o'tgan reyslar ham to'g'ri sostavga tushadi.
5. **Vagonlar:** o'sha sostavning oynada turgan vagonlari (`scale_train_carriages`), ОС bog'langan bo'lsa `asset_id` bilan. **Har bir dumpkarning o'z tonnasi:** tortuvchi birliklar olib tashlangach, tarozi pozitsiyasi (3, 4, 5…) GTK `ord` (1, 2, 3…, lokomotivdan boshlab) bilan ketma-ketlik bo'yicha juftlanadi (tartib egasi tomonidan tasdiqlangan, `SCALES_CARRIAGE_ORDER=asc`). Faqat son aniq mos kelganda juftlanadi (13=13); mos kelmasa yoki vagon qatorlari yo'q/to'liq bo'lmasa, sostav yuki dumpkarlarga teng taqsimlanadi. Juftlash `scale_train_carriages.unit_position/net_t` da; API'da `exact_share` shuni ko'rsatadi.
6. **Holat:** `ok` | `no_loco` (raqam hal bo'lmadi) | `no_gtk_train` (lokomotiv ma'lum, lekin o'sha paytda GTK sostavi yo'q, masalan GTK tarixi 04.11.2026 dan oldin) | `excluded` | `pending`.
7. **Belgilar (flags):** `count_mismatch`, `default_tare`, `overload`, `negative_net`, `no_wagon_rows`, `partial_wagon_rows`, `estimated_net`.

## 4. Dinamik to'g'rilash (ma'lumot noto'g'ri bo'lsa)
Tuzatishlar `scale_corrections` da saqlanadi (auditga yoziladi) va **har bir keyingi o'tishda qayta qo'llanadi**:

| Tuzatish | Qachon | Ta'siri |
|---|---|---|
| `loco_alias` (raqam → lokomotiv ОС) | operator xato yozgan raqam (`3202`, harf, nol) | shu raqamli **barcha** sostavlar (o'tmish ham) darhol qayta moslanadi |
| `train_gtk` (sostav → GTK sostavi) | raqam to'g'ri, lekin avtomatik tanlash adashgan | shu sostav majburan shu GTK sostaviga |
| `train_exclude` | sinov, dublikat, xato | hisobdan chiqadi (bekor qilinsa qaytadi) |

Taklif: «Не распознано» da har bir sostav uchun o'sha paytda GTK da ishlagan lokomotivlar (kesishish daqiqalari bilan) chiqadi; «Это он» bir bosish bilan alias yaratadi. **Hech narsa avtomatik bog'lanmaydi** (loyiha qoidasi: faqat operator tasdig'i).
Qo'shimcha o'z-o'zini tuzatish: (a) yangi GTK↔ОС bog'i keyingi `rematch` da barcha reyslarga yetadi (`Пересчитать всё`, CLI `scales-rematch`, har kirishda oxirgi 30 kundagi hal bo'lmaganlar); (b) operator tarozida sostavni tuzatsa, kollektor qayta o'qiydi; (c) offset yangilansa, taxminiy massalar yangilanadi.

## 5. Ishonchlilik va xavfsizlik
- Tarozi PC ga hech qachon yozilmaydi; ulanish `ReadOnly=1`, qisqa; bir tarozi o'chiq bo'lsa ikkinchisi davom etadi.
- Suv belgisi faqat TOIR muvaffaqiyatli qabul qilgandan keyin siljiydi; xato bo'lsa keyingi o'tish takrorlaydi.
- Qabul qilish **token bilan** (`SCALES_INGEST_TOKEN`, `.env` ga); token yo'q bo'lsa endpoint yopiq (401); `hmac.compare_digest`; 4 MB chegarasi.
- Tarozi telemetriyasi auditga yozilmaydi (hajm), tuzatishlar yoziladi. `master` roli tarozi ma'lumotini ko'rmaydi (`scales.*` taqiqlangan, GTK kabi).
- Jim tarozi signali: oxirgi vagon > 6 soat (sariq), > 24 soat (qizil); kollektor 10 daqiqadan ortiq jim bo'lsa alohida belgi.
- Parol Windows Credential Manager'da; repoda, logda, `.env` da yo'q.

## 6. Hisoblash natijalari (API)
`GET /scales/status`, `/trains`, `/unmatched`, `/summary?days=`, `/assets/{id}/work?date_from&date_to` (vagon: reyslar, tonna, kunlar kesimi; lokomotiv: sostavlar, tonna), `GET|POST|DELETE /scales/corrections`, `POST /scales/rematch`. Ruxsat: `scales.view` (admin, operator, management), `scales.manage` (admin, operator).

## 6a. Vagonlar daftari: «qaysi vagon, qachon, qancha yuk olib bordi»
Bitta qator = bitta vagonning bitta reysi (`scale_train_carriages` × `scale_trains`), servis `scales_trips.py`.
- **Tonna manbasi (`basis`):** `own` = vagonning o'z tortilishi (GTK tartibi bo'yicha juftlangan); `train_avg` = sostav yukining vagonlarga teng ulushi; `estimated` = sostav yukining o'zi baholangan (vagon qatorlari yo'q: «Вес» − 189 t); `unknown` = yuk aniqlanmadi. UI'da `own` dan boshqasi «≈» bilan.
- **Vagon kimligi:** GTK vagoni ОС ga bog'langan bo'lsa ОС inventar raqami, aks holda GTK nomi/inventar raqami. Bog'lanmagan vagon ham ko'rinadi; ОС ga bog'langach keyingi `rematch` o'tmish reyslariga `asset_id` ni to'ldiradi.
- **Endpointlar:** `GET /scales/wagons` (vagonlar bo'yicha jami: reyslar, tonna, o'rtacha, oxirgi reys, nechtasi o'z tortilishi bilan), `GET /scales/wagon-trips` (reyslar: vagon, vaqt, tonna, asos, lokomotiv, yuk/karyer, ekskavator, tarozi, sostav jami), `GET /scales/wagon-trips/export.csv` (Excel: UTF-8 BOM, `;`). Filtrlar: vagon (id yoki nom bo'yicha qidiruv), sana (mahalliy kun), tarozi, yuk, «faqat ОС bilan bog'langan»; tartiblash oq ro'yxati.
- **UI:** `/dashboard/scales` → «Вагоны»: «Итоги по вагонам» (tonna bo'yicha reyting) → vagonni bosish → «Все рейсы» shu vagon; «Выгрузить в Excel».
- **Hisob holati:** «требуют внимания» = lokomotivi topilmagan yoki GTK tarixi qamragan vaqtda GTK sostavi topilmagan sostavlar; GTK tarixidan oldingi sostavlar (53 ming) alohida sanaladi (ular lokomotiv bo'yicha hisobga olinadi, vagon bo'yicha aniqlanmaydi).

## 6b. Boshqaruv markazi va kartochkalar (UI)
Har bir ekran bitta so'rov bilan to'ladi (`services/scales_insights.py`, ko'p join), grafiklar qo'lda SVG bilan chiziladi (kutubxonasiz).

| Sahifa | Nima ko'rsatadi | Qaysi jadvallar birlashadi |
|---|---|---|
| `/dashboard/scales` (Весовая) | Katta KPI (tonna, sostav, vagon reysi, o'rtacha sostav/vagon, perегруз ulushi, taniish ulushi) o'tgan davr bilan solishtirib (7/30/90 kun); kunlar bo'yicha tonna (tarozi rangida); «Bugun yo'llarda» 24 soatlik chiziq (blok = sostav, kengligi = vaqt, balandligi = tonna); soatlar issiqlik xaritasi; yuk/karyer; ekskavatorlar; TOP lokomotivlar va vagonlar; ma'lumot sifati; pastda yorliqlar: Вагоны / Составы / Не распознано / Корректировки | scale_trains, scale_train_carriages, scale_posts, scale_cargo, fixed_assets, asset_models |
| `/dashboard/scales/train/[id]` | Sostav «tasviri»: tortuvchi birliklar va dumpkarlar (to'ldirilish balandligi = yuk/105 t; yashil/sariq/qizil), «tonnalar qayerdan» (Вес − yuk farqi), kim tortdi (ОС, GTK, qaysi usul bilan topildi), GTK sostavi, har bir birlikning brutto/tara/netto/tezlik/o'qlar, GTK vagonlari bilan juftlik, замечания tushuntirishi, operator tuzatishlari, oldingi/keyingi sostav | + gtk_trains, gtk_locomotives, gtk_carriages, sections, scale_corrections |
| `/dashboard/scales/wagon/[key]` | Vagon: ОС ma'lumoti (tur, holat, uchastka, model, probeg, ТО sanalari), davr va butun vaqt bo'yicha reys/tonna/aniqlik/перегруз, kunlik tonna, qayerdan/qaysi lokomotiv/qaysi ekskavator bilan, **ТО bilan bog'lash** (oxirgi ТО sanasi: naryad / kiritilgan baza / ОС kartasi, undan beri reys va tonna, ochiq ТО rejasi, naryadlar), GTK ma'lumoti va koordinata, oxirgi reyslar. `key` = ОС id yoki `gtk-<id>` (bog'lanmagan vagon) | + maintenance_plan, maintenance_intervals, asset_maintenance_baseline, work_orders, gtk_carriages |
| `/dashboard/scales/loco/[id]` | Lokomotiv: ОС, GTK (garaj raqami), Wialon (aloqa, tezlik, GPS), operator terib kelgan raqamlar (xatolar ko'rinadi), sostavlar/tonna/o'rtacha vagon, yuk va ekskavator kesimi, qaysi vagonlarni tortgan, ТО bilan bog'lash, oxirgi sostavlar | + wialon_units, asset_source_links |

Havolalar: TOP ro'yxatlar, daftar qatorlari, bugungi chiziq bloklari, sostav chizmasidagi vagonlar va jadvallar sahifalar orasida o'tadi. Endpointlar: `GET /scales/overview?days=`, `/scales/trains/{id}`, `/scales/wagon-card?asset_id|carriage_gtk_id&days=`, `/scales/loco-card/{asset_id}?days=`.

## 7. Keyingi bosqich (qaror kerak, sxema o'zgaradi)
1. ТО intervaliga `interval_trips` / `interval_tons` (ish bo'yicha eskirish) va «Tirik reja» hisobiga ulash: reja km va moto-soat bilan birga tonna/reys bo'yicha ham ishlaydi.
2. (Bajarildi 2026-11-17, migratsiya `0035_scale_car_net`) pozitsiya → GTK tartibi bo'yicha vagon ichidagi aniq tonna.
3. ОС kartasida «Работа по весам» bloki; dashboardda tonna KPI; xaritada reys.
4. Perevalka/ko'p yuklash (`overload`) hisoboti ekskavator va karyer kesimida.

## 8. Haqiqiy ma'lumotda sinov natijalari (2026-11-17)
Sinov: jonli bazaning yangi zaxirasi (`pre_scales_20261117_1512.dump`) alohida PostgreSQL ga tiklandi, migratsiya `0034` qo'llandi, kollektor ikkala **haqiqiy** tarozidan hammasini yukladi (jonli baza o'zgarmadi).
- Yuklandi: **55 249 sostav, 595 734 vagon qatori** (2025-01 … bugun, 40 oylik arxiv + jonli), ~2 daqiqada; qayta yuklash 0 o'zgarish (takrorlanuvchi).
- Hamma sostavni qayta hisoblash (`rematch`): ~30 soniya.
- GTK tarkib tarixi mavjud oynada (05.11.2026 dan, 1 093 sostav): **961 tasi (88%) avtomatik taniladi**, 131 tasida GTK sostavi topilmadi (102 tasida lokomotiv GTK da hech qachon sostav boshi emas: `001`, `002`, `162`…; qolgan 29 tasi vaqt bo'shlig'i), 1 tasida raqam bo'sh.
- Sostav tarkibi: GTK vagonlari soni va tarozida tortilgan dumpkarlar soni **998/1 015 sostavda aniq mos** (98%), 969 sostavda 13 dumpkar.
- Muhim topilma va tuzatish: dastlab «tara ≥ 100 t = tortuvchi birlik» qoidasi 41% sostavda 3-chi birlikni (haqiqiy tarasi 100–112 t bo'lgan oddiy dumpkar) tortuvchi deb sanardi va ~100 t yukni tashlab yuborardi (mos kelish 56%). Tara gistogrammasi: tortuvchi birliklar 115–140 t da to'planadi, dumpkarlar 60–115 t. Endi: chegara 115 t, GTK bor bo'lsa tortuvchi birliklar soni GTK dan olinadi (`tortilgan birlik − GTK vagonlari`, eng og'ir taralar) va `traction_inferred` belgisi qo'yiladi.
- «Вес − real yuk» offseti ikkala tarozida bir xil: **189 t** (mediana, 17 251 va 23 402 sostav). Vagon qatorlari yo'q 14 532 sostavning massasi shu offset bilan baholanadi (`estimated`, jami ~7,1 mln t).
- Hajm xatosi topildi va tuzatildi: 55 mingta id ni bir `IN (...)` ga qo'yish drayver chegarasidan (32 767 parametr) oshardi; endi bo'laklanadi.
- Raqamlar: oxirgi 7 sutkada ~805 ming t (597 sostav), sostavning o'rtacha yuki ~1 383 t, dumpkar o'rtachasi ~106,6 t (grузоподъемность 105 t).
- Taniy olmagan raqamlar: bo'sh raqam 578 ta (operator yozmagan), `181` 41 ta, qolgani bittadan-ikkitadan (4 xonali: `3301`, `3152`, `7302`…). Eski (GTK tarixidan oldingi) sostavlar uchun taklif berib bo'lmaydi; alias qo'lda.
- Hali tekshirilmagan: UI sahifasining ma'lumot bilan ko'rinishi jonli tizimda (token `.env` ga qo'yilgach), kollektorning doimiy rejimdagi (har 60 s) ishlashi, `TOIR-Scales-*` vazifalari.
