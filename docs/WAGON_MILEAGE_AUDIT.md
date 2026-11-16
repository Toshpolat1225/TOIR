# Vagon probegi: AUDIT (Faza 1)

Sana: 2026-11-13. Kod o'zgartirilmagan. Baza faqat o'qildi (SELECT). Fakt = kod yoki SQL natijasida ko'rilgan. Taxmin va tavsiya alohida belgilangan. Testlar bu fazada ishga tushirilmagan: "dalil" ustuni faqat kodni o'qishga tayanadi.

## 1. D1–D10 holati

| № | Qaror | Holat | Dalil |
|---|---|---|---|
| D1 | `observed_at` = xabar vaqti | QISMAN | Pull: `reading_at=unit.last_message_at`, `source_time_verified=True` (`services/wialon.py:88,93`). Push: `source_time_verified=False` (`routers/wialon.py:244`), shuning uchun push o'qishlari hech qachon hisobga kirmaydi. `last_message_at` aynan `lmsg.t` dan olinishi **tekshirilmagan** (`wialon_client.py` o'qilmadi). |
| D2 | Faqat `wialon_id` | BAJARILDI (kod) | `find_wialon_asset` faqat `unit_id` bo'yicha (`services/assets.py:594-600`); ingest `get_asset_by_wialon_id` (`wialon_ingestion.py:99`). Nom bilan moslash yo'q. |
| D3 | Bracket 30 daq, 0 km CONFIRMED, harakat ESTIMATED | BAJARILDI (kod) | `sum_wialon_sample_deltas` (`wagon_mileage.py:144-286`): `sample_km>0` va bracket>30 daq → HELD; teng odometr → 0 km; bracket>2 daq va km>0 → ESTIMATED. Chegara `config.py:42`. Eslatma: real oraliq p50=120 s, p90=144 s (SQL), 144 s > 120 s bo'lgani uchun harakatli segmentlarning ko'pi ESTIMATED bo'ladi. Bu D3 ga mos. |
| D4 | Lokomotiv almashishi faqat GTK vaqti bilan | BAJARILDI (kod) | `_candidate_decisions` (`wagon_mileage_run.py:206-207`): lokomotiv a'zoligi vagon oralig'ini to'liq qoplamasa `locomotive_handoff_time_unknown` HELD. |
| D5 | Snapshotlar orasida o'tgan vagon: ESTIMATED | BAJARILDI (kod) | `boundaries_exact` (`wagon_mileage_run.py:299-319`). `observed_from` snapshot vaqti, `gtk_begin_time` poyezd boshlanishi, shuning uchun amalda deyarli hamma km>0 ESTIMATED bo'ladi (taxmin, tekshirilmagan). |
| D6 | Asosiy lokomotiv, farq `max(2 km,5%)` | BAJARILDI (kod) | `select_main_locomotive` (`wagon_mileage_engine.py:76-134`). Mahalliy bazada hamma poyezdda 1 ta lokomotiv (SQL), ya'ni ko'p-lokomotivli yo'l real ma'lumotda sinalmaydi. |
| D7 | Idle faqat odometr 0 + GTK holati | QISMAN | `run_wagon_mileage` `decide_wagon_idle` ni `gtk_wagon_stationary=None, wialon_locomotive_stopped=None` bilan chaqiradi (`wagon_mileage_run.py:516-521`), natija doim `HELD insufficient_gtk_and_wialon_evidence`, holat `unknown_activity`. Idle hech qachon `confirmed` bo'lmaydi. Idle km qo'shmaydi (to'g'ri). |
| D8 | Maker≠checker, admin tasdiqlaydi | QISMAN | Maker≠checker bor (`mileage_opening.py:88`); eski qiymat `superseded` bo'ladi (`:103-106`); tasdiqlanmasa HELD (`wagon_mileage_run.py:293-295`). `OPENING_BALANCE_ALLOW_SELF_APPROVAL` sozlamasi kodda **yo'q** (grep bo'sh). Admin tekshiruvi `routers/mileage.py:83` (`user.role != "admin"`), yuqori qismi o'qilmadi. |
| D9 | Projection formulasi, HELD kirmaydi | BAJARILDI (kod) | `calculate_wagon_projection` va yig'indi faqat `CONFIRMED/ESTIMATED` (`wagon_mileage_run.py:582-596`). Vagon `fixed_assets.mileage` ning yagona yozuvchisi shu (`:598`); qo'lda tahrir 422 (`services/assets.py:269-273`, `509-519`). Ekranda uch qiymat: API `WagonMileageSummary` da bor (`mileage_opening.py:183-194`), UI **tekshirilmagan**. |
| D10 | Lokomotiv mileage'iga dvigatel yozmaydi | QISMAN | Dvigatel yozmaydi (`wagon_mileage_run.py:572-573` non-wagon rad). Bayroq `false` standart (`config.py:44`) va faqat `gtk.py:981` da. **Lekin** Wialon delta yo'li ham lokomotiv mileage'ini yozmaydi: `receive_wialon_update` faqat ogohlantirish yozadi (`services/assets.py:623-627`), `_gated_mileage` har doim `None` qaytaradi (`services/wialon.py:101`). Ya'ni lokomotiv `fixed_assets.mileage` hozir yangilanmaydi (qarorda yozilgan "Wialon pull delta" yo'li kodda yo'q). |

## 2. Ma'lumot oqimi

| Bo'g'in | Kim chaqiradi | Avtomatikmi |
|---|---|---|
| GTK sync | `run_periodic_gtk_sync` (`gtk.py:975`) | Ha, `GTK_SYNC_ENABLED=true`, 5 daq |
| A'zolik (`gtk_train_members`) | `repositories/gtk.py:751-795` GTK sync ichida | Ha |
| Wialon o'qish | `run_periodic_wialon_sync` → `ingest_wialon_reading` | Ha, `WIALON_SYNC_ENABLED=true`, 2 daq |
| Engine run → ledger → projection → ТО-reja | `gtk.py:981` yoki CLI `wagon-mileage-run` | **Avtomatik emas**: `WAGON_MILEAGE_ENGINE_ENABLED` konteynerda o'rnatilmagan (standart false). CLI bayroqni tekshirmaydi, shuning uchun CLI har doim ishlaydi. |
| ТО-reja qayta hisobi | `reconcile_asset_plans` run ichida (`wagon_mileage_run.py:600`) | Run bilan birga. Faqat vagon va `has_confirmed_projection` bo'lsa. |

Eslatma: run a'zolik va Wialon o'qishni o'zi chaqirmaydi, ularning tayyor natijasini o'qiydi. Faza 2.1 dagi "yagona ketma-ketlik" hozir yo'q.

## 3. `fixed_assets.mileage` yozuvchilari

- `services/wagon_mileage_run.py:598`: vagon projection (D9, yagona).
- `services/gtk.py:718, 890`: yangi aktiv yaratishda `0`. `gtk.py:812` snapshot ma'lumotida o'qiladi.
- `services/assets.py:623`: Wialon: yozmaydi (faqat log).
- Qo'lda: rad etiladi (422).
- Boshqa to'g'ridan-to'g'ri UPDATE grep bilan topilmadi. Lekin `core/asset_field_policy.py:24` da mileage "wialon" egaligida turadi, bu amaldagi xulq-atvorga mos emas.

## 4. Mahalliy baza qamrovi (faqat SELECT, 2026-11-13 ~10:00 UTC)

- Alembic: `0029_wagon_mileage_ledger` (baza allaqachon 0029 da).
- Aktivlar (soni / mileage yig'indisi): vagon 835 / 384 (832 tasi 0), lokomotiv 51 / 5181, teplovoz 35 / 796, platforma 24, sisterna 129, maxsus 1.
- GTK bog'lanishlar (faol): vagon 563 (+2 tugagan), lokomotiv 51, teplovoz 25. Wialon bog'lanish: lokomotiv 51, teplovoz 35.
- GTK poyezdlar: 79, hammasi ochiq, oxirgi sync 2026-11-13 09:44 UTC.
- A'zoliklar: vagon 1098 (ochiq 478), lokomotiv 79 (ochiq 37, hammasida `is_main=true`). Aktivga bog'langan: vagon 1073 qator / 496 aktiv, lokomotiv 79 / 44. Ochiq a'zolikdagi bog'langan vagon: 466.
- Ochiq poyezdlar: har birida 1 lokomotiv, jami 37 poyezd, 478 vagon. Bir vagon ikki ochiq poyezdda: 0.
- Wialon o'qishlari: jami 231 915, aktivga bog'langan 135 794, `calculation_eligible` atigi 1708 (birinchisi 2026-11-12 23:01 UTC). 87 aktiv.
- Oxirgi 24 soat, aktivga bog'langan: `source_time_policy_pending` 37 557 (HELD), CONFIRMED 1307, `same_time_different_odometer` 240, `counter_state_blocked_by_unresolved_conflict` 31, "24 soatdan eski" 13, "cnm sakradi" bir nechta.
- Oraliq (eligible, 24 s): 59 lokomotiv, p50 120 s, p90 144 s, maks 5400 s, 1244 / 1247 tasi ≤ 30 daq.
- Eligible o'qishi bor va GTK poyezdiga bog'langan lokomotivlar: 43 (44 dan).
- Tasdiqlangan boshlang'ich balans: **0** (jadval bo'sh). Ledger: **0** qator. `mileage_calculation_runs`: 0. Idle: 0.
- ТО-intervallar: 8 ta, hammasi faqat `{locomotive,diesel}`; **vagon uchun interval yo'q**.

## 5. Bo'shliqlar (muhimlik tartibida)

1. **Boshlang'ich balans yo'q (0 ta).** Hozir run bersa hamma vagon `approved_opening_balance_missing` HELD bo'ladi. Faza 2.2 (taklif + ommaviy tasdiq) shart. 832 vagon mileage=0: avtomatik tasdiqlanmaydi (D8), 3 ta nolmas vagon bor.
2. **Eligible Wialon ma'lumoti juda yangi:** 2026-11-12 23:01 UTC dan boshlab. Vagon a'zoligi 2026-11-04 dan. Oldingi davrlar `missing_odometer_sample_bracket` HELD bo'ladi. Sabab (taxmin, tekshirilmagan): eski kod `source_time_policy_pending` bilan HELD yozgan; oxirgi 24 soatda ham 37 557 ta shunday qator bor, ya'ni eligible ulushi (1307) kichik. Buni Faza 2.3 da aniqlash kerak.
3. **Vagon ТО-intervali yo'q.** Boshqa to'g'ri ish bo'lsa ham ТО-reja hosil bo'lmaydi. Biznes qarori kerak (intervallar qiymati): **PENDING**.
4. **Lokomotiv `fixed_assets.mileage` yangilanmayapti** (D10 bo'yicha qaror va kod ziddiyati). Lokomotiv ТО-rejasi eskirgan qiymatda hisoblanadi. Tuzatish loyiha egasi qarorini talab qiladi (bu vagon vazifasidan tashqari).
5. **Yagona ishga tushirish yo'q** (2.1): run-level advisory lock yo'q (faqat poyezd/aktiv bo'yicha), xato bo'lsa run `running` holatida qoladi (`FAILED` o'tkazilmaydi), CLI bayroqni hisobga olmaydi.
6. **Invariantlar run oxirida tekshirilmaydi** (2.6): lokomotiv checksum, qayta run farqsizligi, projection tengligi.
7. **Idle D7**: GTK/Wialon holat dalili ulanmagan, idle har doim `unknown_activity`.
8. **`wagon-mileage-report`, `wagon-opening-propose` CLI yo'q** (2.2, 2.4). `routers/mileage.py` da ommaviy tasdiq yo'q.
9. **HELD sabablari standartlashtirilmagan:** `gtk_id yo'q` va `lokomotivda Wialon mapping yo'q` uchun alohida kod yo'q (vagon uchun GTK bog'lanishi bo'lmasa u umuman proposalga tushmaydi, sababi ko'rinmaydi: 835 vagondan 466 tasi ochiq a'zolikda).
10. **`OPENING_BALANCE_ALLOW_SELF_APPROVAL` sozlamasi yo'q**; maker≠checker qat'iy (xavfsiz tomonda).
11. **Ishlash tezligi:** `_load_inputs` barcha tarixiy o'qishlarni (231k) xotiraga yuklaydi. Hozircha 87 aktiv uchun ahamiyatsiz, kuzatish kerak.
12. **Test:** vagon uchun `pg` testi bitta (`test_wagon_mileage_postgres.py`); `test_wagon_mileage_run.py` da 3 ta test. Faza 3 ro'yxatining ko'pi qamrab olinmagan (tekshirilmagan: `test_wagon_mileage_orchestration.py` ning 18 testi nimani qoplashi).

## 6. Tekshirilmagan

- Hech qanday test ishga tushirilmadi; `tsc`, lint, build ham.
- `wialon_client.py` (`lmsg.t` manbasi), `routers/mileage.py` ning to'liq rol tekshiruvi, `repositories/*`, UI sahifasi o'qilmadi.
- `wagon-mileage-run --dry-run` Faza 4 da ishga tushiriladi.
- 5 ta test fayli (`source_check_utils.py`, `uz-Cyrl` istisnosi) susaymaganligi tekshirilmadi.

## 7. Davom etish sharti

Mahalliy bazada GTK snapshot **bor** (79 poyezd, 1098 a'zolik), shuning uchun Faza 4 to'xtatilmaydi. Faza 2 dan oldin bitta qaror kerak: vagon ТО-intervallari va lokomotiv mileage egaligi (3 va 4-bandlar).
