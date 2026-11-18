# «GPS: Wialon ↔ GTK» — yo'l xaritasi va texnik topshiriq (TZ)

Sana: 2026-11-18. Holat: **faqat reja, kod/baza o'zgarmagan.** Muallif: tahlil jonli ma'lumotda (faqat o'qish) bajarilgan.
Hujjat ikki kishiga: loyiha egasiga (qaror qilish uchun) va keyin amalga oshiruvchiga (men/dasturchi).

Belgilar: **[O'LCHANDI]** — jonli bazada hisoblab ko'rildi. **[REJA]** — hali qurilmagan. **[OCHIQ]** — foydalanuvchi qarori yoki alohida tadqiqot kerak.

---

## 0. Qisqa xulosa (4 savolga javob)

| # | Savol | Qisqa javob |
|---|---|---|
| 1 | Nega sahifada faqat tortuv agregatlar bor, vagonlar yo'q? | Vagonning **o'z GPS'i yo'q**: GTK vagonlarida `sim` yo'q va koordinata o'zgarmaydi (586 vagon, 148 kuzatuv, 0 o'zgarish); Wialon'da vagonga bog'langan faol unit 0 ta. Vagon joyi/probegi faqat **lokomotivdan hosila**. Yechim: sahifaga «Вагоны (по составу)» bo'limi — hosila, ochiq belgilangan. |
| 2 | Nega ikki tizim probegi orasida farq katta? | **Sabab GTK ma'lumotining yo'qolishi, o'lchov xatosi emas.** 30 kunda 1527 faol lokomotiv-kundan 862 tasida farq bor; ulardan 773 tasi (90%) — GTK shu kuni umuman nuqta bermagan (408) yoki ≥2 soat jim (365). Teshiksiz kunlarda ikki tizim ~1–2% ichida mos (GTK/Wialon medianasi 0,988). AI sababni topish uchun **kerak emas**; kerak: sabab-klassifikator, «yagona trek» (teshikni to'ldirish), ishonch bahosi. AI — keyingi, ixtiyoriy bosqich (5.6). |
| 3 | Vagon probegi uchun qaysi manba eng yaxshi? | Hozir: bitta manba (Wialon odometr, sostav a'zoligi davrida). Reja: har davr uchun **3–4 nomzod** (odometr, Wialon trek, GTK trek, yagona trek), tanlash qoidasi va ishonch; avval faqat ko'rsatish (dry-run), tasdiqdan keyin dvigatelga ulash (5.4). |
| 4 | Sahifa bosiladigan va filtrlari maksimal bo'lsin | Hozir faqat qator va tugma bosiladi. Reja: KPI/diagramma/legenda/marker bosilsa filtr bo'ladi, yon panel (drawer), server tartiblash, 15+ filtr, URL holati, CSV eksport, xarita-ro'yxat sinxroni (5.5). |

**Muhim halol xulosa:** 30 kunda Wialon 130 927 km, GTK 72 449 km (55%); «kuniga eng kattasi» (max) 134 251 km — Wialon'dan atigi +2,5%. Demak GTK probegi **asosiy manba bo'la olmaydi**; uning qiymati: (a) Wialon'ni tasdiqlash, (b) Wialon uzilganda to'ldirish (hozir 2 kun), (c) GTK treker nosozliklarini ko'rsatish (probegning 46% i GTK teshiklari tufayli yo'qolgan).

---

## 1. Hozirgi holat (nima qurilgan)

- Kanallar alohida: Wialon — `wialon_units`, `asset_position_history` (source `wialon`), `wialon_odometer_readings` (443 877 o'qish, 87 aktiv, 2021 dan). GTK GPS — `gtk_gps_units` (242 birlik), `gtk_gps_days` (kunlik masofa), `asset_position_history` (source `gtk_gps`), `gtk_gps_runs`. GTK sostav tarixi — `gtk_train_members` (**2026-11-04 dan**, 513 vagon, 92 poyezd; hozir har ochiq poyezdda aynan 1 lokomotiv).
- Servislar: `gps_compare` (hukmlar), `gtk_gps` (sinxron), `gps_overview` (sahifa), `asset_map` (birlashgan xarita).
- Sahifa: `/dashboard/gps` (KPI, 2 diagramma, 3 xarita, jadval, kanal holati), `/dashboard/gps/[assetId]` (kunlik jadval, trek xaritalari).
- Vagon probegi: `wagon_mileage_engine` — lokomotiv odometr oralig'i × GTK a'zolik davri; bir nechta lokomotiv bo'lsa **bittasi tanlanadi** (odometrlar hech qachon qo'shilmaydi/o'rtalanmaydi); `estimated`/`HELD` belgilari; qoidalar `docs/WAGON_MILEAGE_RUNBOOK.md`.

## 2. Savol 1 — nega vagonlar yo'q: faktlar va yechim

### 2.1 Faktlar
- **[O'LCHANDI]** GTK `get_vehicles` 242 birlik beradi; ular lokomotiv va boshqa texnika (samosval, ekskavator...); **vagonlar (carriages) bu ro'yxatda yo'q**. Vagon holati GTK'da alohida (`carriageStates`): `point` bor, lekin 586 vagonning 475 tasi bitta (40.81238, 69.60285) nuqtada va bir haftada hech biri siljimagan.
- **[O'LCHANDI]** `asset_source_links` da Wialon'ga faol bog'langan vagon/platforma/sisterna yo'q (faqat lokomotivlar: 87).
- Xulosa: tizimda vagon uchun **o'lchangan** GPS yo'q; mavjud faqat «vagon lokomotiv bilan birga bo‘lgan davr».

### 2.2 Yechim — «Вагоны (по составу)» bo'limi [REJA]
Ma'no: vagon joyi va yo'li = uning lokomotivining joyi/yo'li, **faqat GTK sostav a'zoligi davrida**. Har qiymat ochiq belgi bilan: `basis = train_derived`.

Ko'rsatiladi (har vagon uchun):
1. Hozirgi joyi: lokomotiv fixi (qaysi manba yangi: Wialon/GTK) + lokomotiv raqami + sostav №.
2. Ishonch: `high` (lokomotivda ikkala trekker tasdiqlagan), `medium` (bitta trekker), `low` (lokomotiv fixi eski/jim), `none` (sostavda emas yoki lokomotivda GPS yo'q).
3. Davr bo'yicha segmentlar: [qachondan–qachongacha] – sostav – lokomotiv – km (nomzodlar bilan, 4-bo'lim).
4. Nazorat belgilari (xato topuvchi): vagon bir vaqtda ikki sostavda; sostav a'zoligi 24 soatdan eski, lokomotivi jim; vagonning GTK koordinatasi lokomotivdan > X km uzoqda (u «sobit nuqta» bo'lsa — e'tiborga olinmaydi, sabab yuqorida); sostavda lokomotiv yo'q; a'zolik tarixi boshlanishidan (2026-11-04) oldingi davr — «tarix yo'q».
5. Filtrlar: sostav, lokomotiv, uchastka, ishonch, vagon turi, «hozir yo'lda/turibdi», belgi turi.

Arxitektura: yangi alohida jadval **shart emas** (1-bosqichda): hosila `gtk_train_members` × lokomotivning `gps_overview` qatori orqali o'qishda hisoblanadi; vagonlar ko'p (964 ta) — server tomonida sahifalash va `limit ≤ 500`. Master: faqat o'z uchastkasi vagonlari, boshqa uchastka lokomotivi nomi yashiriladi (xarita bilan bir xil qoida, 404 begonaga).

Chegara [OCHIQ]: 2026-11-04 dan oldingi davr uchun vagon↔lokomotiv bog'lanishi yo'q — orqaga to'ldirish mumkin emas (GTK tarix bermaydi; faqat yangi kuzatuvlar).

## 3. Savol 2 — nega farq katta va uni qanday hal qilish

### 3.1 O'lchov (2026-10-18 … 2026-11-16, yopilgan kunlar, 67 lokomotiv, faol kun = ≥5 km) [O'LCHANDI]

| Ko'rsatkich | Qiymat |
|---|---|
| Faol lokomotiv-kun | 1527 |
| GTK/Wialon mos (0,85–1,15) | 665 (44%) |
| GTK past (<0,85) | 790 (52%) |
| GTK baland (>1,15) | 72 (5%) |
| Farqli 862 kun sababi: GTK shu kuni 0 nuqta | 408 (47%) |
| … GTK ≥2 soat jim, Wialon uzluksiz | 365 (42%) |
| … ikkalasida teshik | 29 (3%) |
| … hech birida uzun teshik yo'q («tizimli»: GTK nuqtalar kam yuboradi, harakatda tez-tez emas) | 58 (7%) |
| … Wialon ≥2 soat jim, GTK uzluksiz | 2 (0,2%) |
| Teshiksiz kunlarda GTK/Wialon mediana | 0,988 |
| GTK o'z `distance` / bizning haversine (GTK nuqtalaridan) | 0,989 (usul farqi ~1%) |
| Jami km: Wialon / GTK / kuniga max | 130 927 / 72 449 / 134 251 |
| GTK teshiklari tufayli yo'qolgan km (Wialon bilan solishtirganda) | ≈ 59 925 (46%) |

Lokomotivlar bo'yicha (67 faol): **14 tasida GTK deyarli hech qachon mos kelmaydi** (masalan 38914, 38913, 38909, 38910, 38402, 38390, 38956 — GTK umuman nuqta bermaydi; 37080, 37924 — nuqtalar bor, lekin joyi sobit/noto'g'ri), 10 tasida <30% mos, 30 tasi oraliq (vaqti-vaqti bilan jim), 13 tasi ≥80% mos. Dinamika: mos kunlar ulushi haftalar bo'yicha 38% → 42% → 46% → 44% → 58% (yaxshilanmoqda).

Odometr (uchinchi fikr): taqqoslash mumkin 404 kun; Wialon trek/odometr mediana 0,97; farqli kunlarda odometr 210 tadan **154 tasida Wialon'ga yaqin** (73%), 56 tasida GTK'ga. Lekin kunlik odometr delta usuli hozir oddiy va shovqinli (10–90 persentil 0,59…4,6) — uni nazorat manbai qilishdan oldin alohida tadqiqot kerak [OCHIQ].

Xulosa: farqning **asosiy sababi o'lchov emas, ma'lumot yetishmasligi** (GTK 90%). Shuning uchun «aqlli model»dan oldin **sabab-klassifikator + teshikni to'ldirish + ishonch** kerak.

### 3.2 Yechim bloklari [REJA]

**A. Sabab-klassifikator** (aniq qoidalar, sof funksiya, testlanadi). Har lokomotiv-kun uchun bitta `cause`:
`gtk_dead` (≥7 kun ketma-ket GTK nuqta yo'q yoki hech qachon), `gtk_no_day`, `gtk_gaps` (≥2 soat jimlik), `gtk_sparse` (uzun teshik yo'q, lekin GTK nuqta soni Wialon'ning <40% i), `wialon_gaps`, `both_gaps`, `position_mismatch` (bir paytda fixlar uzoq), `day_open` (bugun), `method` (farq ≤15%, teshiksiz), `ok`.
Chiqish: sahifada «Причина» ustuni va filtri; kunlik jadvalda sabab belgisi; KPI «sabab bo'yicha taqsimot» diagrammasi.

**B. GTK Health (treker sog'ligi)** — lokomotiv uchun 30 kunlik ko'rsatkich: `ok_days / none_days / partial_days`, oxirgi GTK fiksi yoshi, siljimaydigan koordinata belgisi («sobit nuqta»: GTK vaqti yangi, lekin joyi o'zgarmaydi va Wialon bilan >2 km farq — 37080 misoli), sinf: `ok | intermittent | dead | frozen`. Chiqish: «Рейтинг трекеров GTK» paneli (eng yomonlari birinchi) — IT/GTK administratoriga berish uchun eksport. Bu foydali: 14 ta o'lik treker aniq ro'yxat bo'ladi.

**C. «Yagona trek» (fused track)** — teshikni to'ldirish:
1. Kirish: Wialon nuqtalari W va GTK nuqtalari G (ikkalasi `asset_position_history` da, siyraklangan, ≥1 nuqta/20 daq. turgan holatda).
2. Tozalash: ketma-ket nuqtalar orasida >120 km/soat «teleport» chiqarib tashlanadi.
3. Asos — Wialon vaqt chizig'i (zich va to'liq). Wialon'da >10 daqiqa teshik bo'lsa va G shu oraliqda nuqta bersa, G nuqtalar qo'shiladi; teshik ikkalasida bo'lsa — to'g'ri chiziq ko'prigi, `unknown_gap_m` alohida hisoblanadi, ishonch tushadi.
4. Kunlik `fused_m` = birlashgan yo'l uzunligi (+ `unknown_gap_m` ajratilgan holda).
5. Ishonch `confidence` 0–1: `coverage` (faol soatlarning nechasi ≥1 manba nuqtasi bilan qoplangan) × `agreement` (ikki manba mos kelganda ↑). Foydalanuvchiga «ishonchli / taxminiy / noaniq» sifatida ko'rsatiladi.
6. Chiqish: sahifadagi «Единый пробег» endi oddiy `max` emas, `fused_m ± unknown_gap_m` bo'ladi (hozirgi o'rtacha/maks qoidasi `gps_compare.unify_distance` o'rniga, eskisi zaxira sifatida qoladi).

Kutilgan natija (tasdiqlanadi, 8-bo'lim): Wialon uzilgan 2 kunda GTK to'ldiradi; qolgan holatlarda `fused_m` ≈ Wialon (≥98% kunlarda). Ya'ni **qiymat — ishonch va sababni aniq aytish**, jami km'ni ko'paytirish emas.

**D. Odometr — uchinchi nazorat** [OCHIQ → tadqiqot]: Wialon odometr hisoblagichi kunlik delta bilan; alohida backtest (3-bosqich), natija yaxshi bo'lsa `odo_m` nomzod sifatida qo'shiladi va 2-ta-3 qoidasi (ikki manba mos → ular g'olib).

**E. AI haqida halol baho:**
- Hozir kerak emas: sabab aniq, qoidalar bilan 100% tasniflanadi.
- Foydali bo'ladigan joylar (5.6, ixtiyoriy, keyin): (1) anomaliya aniqlovchi (kunlik nisbat, qoplama, tezlik profili bo'yicha: «bu lokomotivning bugungi pozitsiyasi odatdagidan farq qiladi»); (2) GTK teshigini bashorat qilish (shu lokomotiv, shu smena, o'tgan haftalar) — km'ni «to'ldirish» emas, **ogohlantirish** uchun; (3) LLM «izoh generatori»: tuzilgan sabab ma'lumotidan oddiy rus tilida kunlik/lokomotiv xulosa («GTK 14:10–19:40 jim; Wialon uzluksiz; probeg 112 km Wialon bo'yicha»). `docs/AI_ASSISTANT_TZ.md` mavjud — shunga ulash.
- Cheklov: haqiqiy «to'g'ri javob» (ground truth) yo'q — odometr siyrak va shovqinli. Shuning uchun ML bilan probegni «tuzatish» **tavsiya etilmaydi**; faqat belgilash/izohlash.

## 4. Savol 3 — vagon probegi: manba tanlash

### 4.1 Hozirgi usul va kamchiliklari
`wagon_mileage_engine`: har (vagon, sostav a'zolik davri) uchun lokomotiv odometr oralig'i. Kamchiliklar: (a) bitta manba; (b) odometr o'qishlari siyrak (config bo'yicha oralig'i 240 daqiqagacha) — davr chegaralarida xato; (c) GTK sostavi har 5 daqiqada kuzatiladi: a'zolik chegarasi ±5 daqiqa; (d) lokomotiv odometri jim bo'lsa vagon `HELD`.

### 4.2 Yangi: nomzodlar va tanlash [REJA]
Har davr [t0, t1], lokomotiv L uchun to'rt nomzod:
- **A** — odometr delta (mavjud usul, chegaralarda interpolyatsiya bilan).
- **B** — Wialon trek integrali t0…t1 (chegaralarda vaqt bo'yicha interpolyatsiya).
- **C** — GTK trek: ikki yo'l: saqlangan nuqtalar integrali yoki GTK'dan aynan [t0,t1] oynasi uchun `get_track` → server `distance` (1 so'rov/davr; faqat kerak bo'lganda).
- **D** — yagona trek integrali (3.2.C).

Tanlash qoidasi (aniq, deterministik; **o'rtalash va qo'shish yo'q**, dvigatelning avvalgi falsafasiga mos):
1. `coverage(D) ≥ 90%` → **D** (basis `fused_track`).
2. Aks holda A va B ikkalasi bor va |A−B|/max ≤ 10% → **B** (zichroq).
3. Aks holda ikkalasi bor, farq >10% → `conflict`: qoplamasi yuqori nomzod olinadi, `estimated=true`, sabab yoziladi.
4. Faqat bitta nomzod → o'sha, `estimated=true`, ishonch `low`.
5. Hech biri → `HELD` (hozirgidek).
Har natija bilan: `basis`, `confidence`, barcha nomzodlar `calculation_details` (mavjud jsonb, sxema o'zgarmaydi) ga yoziladi; `algorithm_version` yangilanadi (eski qatorlar `supersedes` orqali saqlanadi).

### 4.3 Bosqichma-bosqich xavfsizlik
1. **Faqat ko'rsatish** (sahifada «Вагоны» bo'limi, nomzodlar yonma-yon, dvigatelga tegmaydi).
2. **Backtest**: 2026-11-04 dan 92 poyezd/513 vagon bo'yicha A/B/D farqi; qabul: tozalangan davrlarda median |A−B| ≤ 5%.
3. **Dry-run diff hisoboti**: yangi qoida eski ledger'dan qancha vagonda qanchaga farq qiladi (`wagon-mileage-report` uslubida CSV).
4. Foydalanuvchi tasdig'i → dvigatelni bayroq (`WAGON_MILEAGE_SELECTION=multi_source`) ortida yoqish; eski natija o'chirilmaydi.

## 5. Savol 4 — sahifani bosiladigan qilish va maksimal filtrlar

### 5.1 Bosish (interaktivlik) [REJA]
- **KPI plitkalari** bosiladi: «Подтверждено», «Расхождения», «GTK молчит», «Wialon молчит», «Только Wialon», «Проблемные» → mos filtr yoqiladi (faol plitka belgilanadi).
- **Diagramma segmentlari** (pozitsiya hukmi va kunlik hukm) bosiladi → filtr.
- **Legenda/chip** bosiladi → filtr (ko'p tanlov, aria-pressed).
- **Xarita markeri** bosiladi → qator tanlanadi, **yon panel (drawer)** ochiladi (sahifadan chiqmasdan: ikki fix, hukm, sabab, 7 kunlik mini-grafik, «Подробно» havolasi).
- **Jadval qatori** bosiladi → drawer; inventar raqam → tafsilot sahifasi; ustun sarlavhasi → tartiblash.
- **Sabab belgisi** bosiladi → «shu sababli hamma» filtri.
- **Xarita chegarasi**: «ro'yxat xarita ko'rinishiga ergashsin» (bbox filtr).
- **Kunlik jadval** (tafsilotda): kun bosilsa shu kun trek xaritalarida ajratiladi; vaqt slayderi bilan trek «qayta ijro» (replay) — ixtiyoriy.
- Klaviatura: ↑/↓ qator, Enter drawer, Esc yopish.

### 5.2 Filtrlar (to'liq ro'yxat) [REJA]
Qidiruv (inv, nom, model, sostav №) · uchastka · aktiv turi/model · pozitsiya hukmi (ko'p) · kunlik hukm (ko'p) · sabab (ko'p) · severity (ok/warn/bad) · bog'lanish (faqat Wialon / faqat GTK / ikkalasi / hech biri) · GTK sog'ligi sinfi (ok/intermittent/dead/frozen) · «jim» muddati (> X soat) · fixlar orasidagi masofa (> X m) · oxirgi fix yoshi · tezlik («yurmoqda» >0) · km oralig'i (davr bo'yicha) · GTK/Wialon nisbati oralig'i · sana oralig'i (dan–gacha, 1…31 kun; tayyor: bugun / kecha / 7 / 14 / 30) · «Faqat muammolilar» · «yopilmagan kunlar»ni yashirish · xarita chegarasi.
Qo'shimcha: **facets** (har filtr varianti yonida «(34)» soni, joriy boshqa filtrlarga qarab), «Filtrlarni tozalash», filtr chiplari qatori (o'chirish uchun ×).

### 5.3 Holat va saqlash
- Barcha filtr/tartib/sahifa **URL query**'da (ulashish va «orqaga» ishlashi uchun).
- «Saqlangan ko'rinishlar»: avval brauzerda (`localStorage`, try/catch), keyin server tomonida foydalanuvchi bo'yicha [OCHIQ].
- Avtoyangilash 60 s (to'xtatish tugmasi bilan); so'rovlar bekor qilinadi (race yo'q).

### 5.4 Backend o'zgarishlari [REJA]
`GET /gps/overview` ga: `sort_by` (oq ro'yxat: `severity, inv_number, diff_m, gtk_age, wialon_age, week_wialon_m, week_gtk_m, ratio, cause`), `sort_dir`, `distance_verdict[]`, `cause[]`, `asset_type`, `model_id`, `link` , `gtk_health`, `min_diff_m`, `min_silence_h`, `moving`, `date_from/date_to` (≤31 kun; `days` saqlanadi), `bbox`, `facets=true`. Javob: `items,total,limit,offset` + `summary` (butun doira) + `facets`. Yangi: `GET /gps/overview/export` (CSV/XLSX, shu filtrlar, ≤5000 qator, UTF-8 BOM), `GET /gps/health` (treker reytingi), `GET /gps/wagons` (2.2). Xatolar `{"detail":…}`; `sort_by` faqat oq ro'yxatdan; master — o'z uchastkasi, begonaga 404, status tekshiruvidan **oldin**.

## 6. Arxitektura va bog'lanishlar

```
GTK API (get_vehicles, get_track)         Wialon (pull, messages, odometr)        GTK poyezd sahifasi
        │ gtk_gps (har 10 daq, faqat GET)        │ wialon (har 2 daq)                   │ gtk (har 5 daq)
        ▼                                         ▼                                      ▼
 gtk_gps_units/days/runs ──┐          wialon_units, wialon_odometer_readings       gtk_train_members
 asset_position_history    │          asset_position_history (wialon)               (sostav a'zoligi, 2026-11-04 dan)
   (source gtk_gps)        │                    │                                      │
                           ▼                    ▼                                      │
                ┌──────────────────────────────────────┐                               │
                │ gps_assessment (kechasi + bugun)     │  sof funksiyalar:             │
                │  causes · health · fusion · confidence│  gps_compare, gps_causes,    │
                └───────────────┬──────────────────────┘  gps_fusion (testlanadi)      │
                                ▼                                                        │
                   gps_day_assessment (yangi jadval)  ◄──── wagon_gps (hosila) ◄───────┘
                                │                               │
        ┌───────────────────────┼───────────────┬───────────────┴──────────────┐
        ▼                       ▼               ▼                              ▼
 /gps/overview (+facets,     /gps/health     /map/assets (verdikt,        wagon_mileage_engine
  export, sort)                              ishonch halqasi)             (nomzodlar → tanlash, bayroq ortida)
        ▼                       ▼               ▼                              ▼
 /dashboard/gps (+drawer)   Reytinglar     Karta sahifasi               Vagon probegi (ТО, hisobotlar)
```

Yangi jadvallar (migratsiya `0038…`, **ruxsat + dump keyin**) [REJA]:
- `gps_day_assessment(asset_id, day, wialon_m, gtk_m, odo_m NULL, fused_m, unknown_gap_m, wialon_cov_h, gtk_cov_h, cause, confidence, algorithm_version, computed_at, is_final)`, PK `(asset_id, day)`. Hajm: 87 × 365 ≈ 32 000 qator/yil — arzimas.
- `gps_unit_health(asset_id PK, window_days, ok_days, none_days, partial_days, frozen, health_class, last_gtk_fix_at, computed_at)` — yoki `gps_day_assessment` dan o'qishda hisoblash (afzal: avval hisoblash, jadval keyin).
- Vagon qismi uchun yangi jadval **yo'q** (1–3 bosqich); 4-bosqichda faqat mavjud `wagon_mileage_ledger.calculation_details`.
`postgres/schema.sql` va `alembic` bir vaqtda; `test_schema_drift` mos; oldingi migratsiyalar o'zgarmaydi.

Bog'lanishlar qoidalari:
- GTK lokomotiv id = `asset_source_links.external_id` (faol, source `gtk`); vagon id'lari boshqa fazo — vagon faqat sostav orqali.
- Birlamchi probeg manbasi **Wialon odometr** bo'lib qoladi: lokomotiv `fixed_assets.mileage` (ТО rejalash) **o'zgarmaydi** [OCHIQ: yagona km ni ТО'ga berish — tavsiya: yo'q, kamida 3 oy kuzatuvdan keyin].
- GTK'ga yuk: bir sikl ≤ 2 parallel so'rov, har 10 daq; `get_track` interval so'rovlari (4.2-C) faqat talabga ko'ra, kuniga limit bilan.
- Ruxsat: o'qish `analytics.view`; qayta hisoblash/eksport — mavjud rollar doirasida, yangi ruxsat qo'shilmaydi (kerak bo'lsa alohida qaror).
- Xavfsizlik: parol/token hech qayerda yozilmaydi; GTK'ga faqat GET; eksportda uchastka cheklovi saqlanadi.

## 7. Bosqichlar (yo'l xaritasi)

Har bosqich oxirida: testlar, jonli e2e, hujjat (`HANDOFF`, `AI_WORKLOG`, `DECISIONS`), dump (migratsiya bo'lsa). **Qoida: bitta bosqich = bitta deploy; oldin test-fayl bilan mantiq isboti.**

| # | Bosqich | Mazmuni | Qabul mezoni | Xavf |
|---|---|---|---|---|
| P0 | Backtest va qarorlar (≈1 kun) | Sabab-klassifikator va yagona trek qoidalarini 30+ kun tarixda (faqat o'qish) sinash; chegaralarni (15%, 60%, 2 soat, 10 daq) tasdiqlash | Sabab bilan tushuntirilgan farqli kunlar ≥ 95% (hozir qoidalar 100% tasniflaydi, «method/sparse» ni chegaralash kerak); fused ≈ Wialon ≥ 98% kunda | Past |
| P1 | Analitika yadrosi (≈3 kun) | `gps_compare`ga `causes`, `health`, `fusion` (sof, testlar); migratsiya `0038` `gps_day_assessment`; tungi + bugungi hisoblash; API: `cause`, `fused_m`, `confidence`, `/gps/health`; UI: «Причина» ustuni, treker reytingi paneli, «Единый пробег ± неопределённость» | pytest (sof + PG), jonli t-skript, brauzer; `gps_day_assessment` 87×31 qator; sahifa p95 < 1,5 s | O'rta (migratsiya) |
| P2 | Interaktivlik va filtrlar (≈3–4 kun) | 5-bo'lim: bosiladigan KPI/diagramma/legenda/marker, drawer, server tartiblash, filtrlar+facets, URL holati, CSV/XLSX, bbox | Har filtr uchun API testi; brauzer testi: har bosish natijasi; telefon kengligida yon aylanish yo'q; URL qayta ochilganda bir xil natija | Past |
| P3 | Vagonlar bo'limi (≈3–4 kun) | `/gps/wagons` (hosila), UI bo'limi, nazorat belgilari; nomzodlar A/B/D **faqat ko'rsatish** | 964 vagon sahifalanadi; master 404/yashirish testlari; backtest hisoboti (A vs B vs D, 92 poyezd) | Past (o'qish) |
| P4 | Vagon dvigateliga ulash (≈2–3 kun) | 4.2 tanlash qoidasi, `algorithm_version`, dry-run diff CSV, bayroq | Foydalanuvchi diff'ni ko'rib tasdiqlaydi; eski ledger saqlanadi; `wagon-mileage` testlari yashil | **Yuqori** (jonli probeg) |
| P5 | Ixtiyoriy: AI va yo'l grafigi | Anomaliya aniqlovchi, GTK jimlik ogohlantirishi, LLM izohlari; OSM temir yo'l grafigiga «yopishtirish» (snap-to-rail) tadqiqoti | Offline baholash; faqat belgilash/izoh, probegni o'zgartirmaydi | O'rta |

## 8. Test strategiyasi (test-first)
1. **Sof funksiyalar** (`causes`, `health`, `fusion`, `candidate_select`): har qoida uchun jonli o'lchovlardan olingan misol (37919 — kun o'rtasi uzilish; 38914 — o'lik; 37080 — «sobit»; 37896 — mos kun), chegaraviy qiymatlar, bo'sh/None.
2. **PG testlari**: `gps_day_assessment` hisoblash idempotentligi, yopilgan kun qayta yozilmasligi, master 404 (status tekshiruvidan oldin), `sort_by` oq ro'yxati, facets yig'indisi = umumiy.
3. **Backtest skriptlari** (faqat o'qish, `scripts/e2e_live`): 30 kunlik klassifikator taqsimoti; fused vs Wialon; A/B/D vagon davrlari.
4. **Jonli e2e** (`t15` uslubi) + **haqiqiy brauzer** (`b11` uslubi): har bosish/filtr; telefon kengligi; konsolda xato yo'q.
5. Hech narsa «ishladi» deb aytilmaydi — buyruq chiqishi ko'rilmasa **NOT TESTED**.

## 9. Xavflar va ochiq savollar (qaror kerak)
1. **GTK o'lik treker ro'yxati** (14 ta) — GTK administratori/IT bilan ishlash kerakmi? (Tizim ro'yxatni beradi; tuzatish GTK tomonida.)
2. Yagona km lokomotiv ТО'siga ta'sir qilsinmi? (Tavsiya: yo'q.)
3. Chegaralar (0,85–1,15; 0,6; 2 soat; 10 daq; 30 daq «yangi») — tasdiqlash yoki o'zgartirish.
4. Vagon dvigatelini ko'p manbali qoidaga o'tkazish (P4) — roziligingiz va diff hisobotini ko'rish sharti.
5. Servis akkaunt GTK uchun (hozir shaxsiy akkaunt; parol o'zgarsa sinxron to'xtaydi). IT'dan so'rash tavsiya.
6. AI doirasi va joyi (ichki model/tashqi xizmat, ma'lumot maxfiyligi) — P5 oldidan.
7. 2026-11-04 dan oldingi vagon tarixi tiklanmaydi (GTK a'zolik tarixini bermaydi).
8. Hajm: `asset_position_history` GTK'dan kuniga ~28 000 qator (76 lokomotiv); 180 kunlik saqlash ≈ 5 mln qator — kuzatish; kerak bo'lsa GTK uchun saqlash 90 kun.
9. Tekshirilmagan: GTK GPS Wialon'dan mustaqilmi (vaqt belgilari mustaqil ko'rinadi, isbotlanmagan); odometr delta usuli aniqligi.

## 10. Nimaga tegilmaydi
Mavjud migratsiyalar, `fixed_assets.mileage` (lokomotiv probegi), vagon ledger'ining mavjud qatorlari, Wialon pull, GTK poyezd sinxroni, Vesovoy, rollar/ruxsatlar. Hamma yangi narsa qo'shimcha va bayroq/alohida endpoint ortida.

## Ilova A. Hisoblash usuli (takrorlash uchun)
Davr 2026-10-18…2026-11-16 (mahalliy kun, UTC+5); faqat `gtk_gps_days.is_final = true`; faol kun: `max(gtk, wialon) ≥ 5000 m`. Wialon kunlik masofa = `asset_position_history` (source `wialon`) saqlangan nuqtalar haversine yig'indisi; GTK = `gtk_gps_days.distance_m`. Teshik = ketma-ket nuqtalar orasida >60 daqiqa (jami soat). Odometr = shu kunning oxirgi qabul qilingan o'qishi − oldingi kun oxirgisi. Skript: sessiya vaqtinchalik papkasida (`mileage_diff.py`); loyihaga qo'shilmagan.
