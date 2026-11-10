# TOIR Wagon Mileage Engine — P0.2 implementation rejasi

Sana: 2026-11-10  
Holat: **faqat audit va texnik reja; kod yozishga ruxsat emas**  
Asosiy qarorlar: [WAGON_MILEAGE_P0_DECISIONS.md](WAGON_MILEAGE_P0_DECISIONS.md)

## Qaror maqomlari

- `CONFIRMED` — P0.1’da foydalanuvchi tasdiqlagan biznes qoidasi yoki repository’da tekshirilgan kod fakti.
- `PROPOSED` — mavjud TOIR arxitekturasiga mos texnik taklif; tasdiqlanmaguncha biznes qoidasi emas.
- `UNKNOWN` / `PENDING APPROVAL` — egasi, qiymati yoki xulqi hali tasdiqlanmagan.

Bu hujjat implementation emas. Kod, migration, DB, Docker yoki production amali bajarilmadi.

## 1. Executive summary

P0.1 qoidalarini hozirgi tizimga ulash uchun pure engine funksiyalarining o‘zi yetarli emas. GTK snapshot va Wialon o‘lchovlarini audit bilan qabul qilish, membership va odometer vaqtlarini to‘g‘ri bog‘lash, ishonchli locomotive source’ni tanlash, ledger’ni idempotent publish qilish va faqat wagon mileage’ni `fixed_assets.mileage`ga chiqarish uchun orchestration kerak.

Hozir yangi engine GTK/Wialon oqimlariga ulanmagan. GTK sync eski `_attribute_snapshot_mileage`ni chaqiradi. Wialon Pull gate’dan o‘tgan delta’ni, Push esa kelgan qiymatni umumiy asset mileage update’iga uzatishi mumkin. 0027 migration va model manbalari bor, ammo `postgres/schema.sql`, `schema_actual.sql`, `schema_fresh.sql` statik qidiruvida oltita jadval ta’rifi topilmadi. Live DB’ga ulanilmagan: deployed revision va jadvallar mavjudligi `UNKNOWN`.

**Natija:** P0 implementatsiya boshlanishidan avval §15 dagi `UNKNOWN`/`PENDING APPROVAL` masalalari hal qilinishi yoki ochiq qolishi rasman tasdiqlanishi kerak.

## 2. Amaldagi arxitektura va kod holati

### GTK

- `backend/app/integrations/gtk_client.py::build_snapshot` GTK sahifasidan lokomotiv, vagon, train va wagon-state ro‘yxatlarini normallashtiradi; train locomotive a’zolarida `is_main`, tartib va train `begin_time` bor.
- `backend/app/services/gtk.py::sync_gtk` snapshot oladi, mirror va membership’ni yangilaydi, sync run va raw payload’ni saqlaydi.
- Raw snapshot’dagi `effective_at` sync vaqti (`run_at`) bilan yoziladi. Bu source’da qayd etilgan locomotive handoff yoki wagon transfer vaqti ekani tasdiqlanmagan.
- Source `observed_at`, biznes `effective_from/effective_to` va TOIR `received_at` alohida maydon/ma’noga ega. Maqsadli oqim barcha timestamp’larni UTC’ga normalize qiladi va intervalni `[start,end)` deb oladi; GTK snapshot’i exact transfer time emas.
- Raw/mirror/run transaction’i tugagach, eski `_attribute_snapshot_mileage` alohida session’da ishlaydi. Demak snapshot saqlash va mileage publish bitta atomic transaction emas.
- `backend/app/repositories/gtk.py::sync_memberships` yo‘qolgan membership’ni `observed_to` bilan yopadi. Ochiq-row unique index ayni train/kind/object takrorini bloklaydi, lekin bir vagonning boshqa train’lar bilan vaqt overlap’ini cheklamaydi.

### Wialon

- Pull (`backend/app/services/wialon.py::_gated_mileage`) explicit link’ni topadi, `wialon_quality.evaluate` bilan cumulative `cnm` delta’ni tekshiradi va mapped asset, odometer hamda message timestamp bo‘lsa `WialonOdometerReading` yozadi.
- Pull avval Wialon unit mirror’ini commit qiladi, keyin unit’larni alohida `receive_wialon_update`ga uzatadi. Batch partial failure va retry semantikasi hozir bir butun emas.
- Push (`backend/app/routers/wialon.py::_handle_input`) payload’ni parse qilib `receive_wialon_update`ni chaqiradi. U Wialon quality gate yoki raw reading table’ni ishlatmaydi va source measurement timestamp’ini canonical reading’ga o‘tkazmaydi.
- `backend/app/services/assets.py::receive_wialon_update` `_save_mileage_change` orqali kelgan qiymatni `fixed_assets.mileage`ga yozishi mumkin. Asset turi bo‘yicha locomotive/wagon projection ajratilmagan.

### Asset va UI

- `backend/app/models/assets.py::FixedAsset.mileage` — `Numeric(12,2) NOT NULL DEFAULT 0`; `MileageHistory` source/value/time saqlaydi, source reading yoki calculation run’ga FK yo‘q.
- Manual mileage generic `PATCH /fixed-assets/{id}` va `POST /fixed-assets/{id}/mileage` orqali yozilishi mumkin. Bu opening balance approval jarayoni emas.
- Mavjud endpoint’lar: `GET /fixed-assets/{id}/mileage-history`, `GET /gtk/wagon-mileage`, `GET /fixed-assets/{id}/gtk`, `POST /wialon/input`, `POST /wialon/sync`, `GET /wialon/status`.
- Alohida wagon mileage sahifasi topilmadi. `app/dashboard/directories/assets/page.tsx` mileage’ni tahrirlaydi va eski GTK log’ni ko‘rsatadi; GTK/Wialon source sahifalari alohida.
- Work-order `mileage_at_creation`ni snapshot qiladi. Yangi projection maintenance va work-order oqimlarining mavjud ma’nosini buzmasligi kerak.

## 3. P0.1 qarorlariga moslik auditi

| P0.1 talabi | Hozirgi kod | Rejadagi oqibat |
|---|---|---|
| `CONFIRMED`: GTK/Wialon’dan bitta ishonchli locomotive tanlash; ishonchsiz bo‘lsa `HELD` | Pure `select_main_locomotive` bor, ammo GTK/Wialon candidate’larini yig‘adigan orchestration yo‘q; GTK `is_main` eski yo‘l uchun ishlatiladi | Candidate builder va policy-aware selector kerak. Priority/tolerance tasdiqlanmaguncha ziddiyat `HELD`. |
| `CONFIRMED`: locomotive handoff faqat GTK qayd etgan aniq vaqtda | GTK’da `observed_from/to`, train `begin_time` va `gtk_begin_time` bor; kod ularning hammasini exact handoff deb tasdiqlamaydi | Source field mapping tasdiqlanmasa handoff `HELD`; `observed_at` bilan almashtirilmaydi. |
| `CONFIRMED`: Wialon gap faqat bitta locomotive’ning ikki tasdiqlangan o‘lchovi orasida interpolatsiya qilinadi | Engine bracket orchestration va max-age policy’ni qurmaydi | Same-locomotive bracket validator, `ESTIMATED` provenance; max interval `UNKNOWN`. |
| `CONFIRMED`: wagon snapshot transfer’i `ESTIMATED`; snapshot vaqti exact transfer emas | Eski attribution wagon’dan ikki snapshot’da ayni tarkibda bo‘lishini talab qiladi; partial interval allocation yo‘q | Oxirgi eski va birinchi yangi snapshot `observed_at` oralig‘ida estimate; formula `UNKNOWN`. |
| `CONFIRMED`: opening manual, admin approve; alohida action va audit | Model’da `created_by` bor, approval state/actor alohida yo‘q; generic manual mileage endpoint mavjud | Submit/approve endpoint, status, approver tarixi va faqat approved balance’ni ishlatish. Same actor `UNKNOWN`. |
| `CONFIRMED`: idle GTK+Wialon’dan; zid/yetarli bo‘lmasa auto-confirm yo‘q | `WagonIdlePeriod` model’i bor, detector/writer yo‘q; joriy state/speed tarixiy interval’ni isbotlamaydi | Evidence evaluator; ziddiyat yoki yetishmovchilik `HELD`; duration `UNKNOWN`. |
| `CONFIRMED`: `fixed_assets.mileage` faqat wagon projection; locomotive alohida | Eski GTK checkpoint va Wialon Pull/Push shu maydonga yozishi mumkin | Writer’larni ajratish va locomotive uchun alohida read/store yo‘li kerak. |
| `CONFIRMED`: Push/Pull umumiy validation/raw/idempotency; bir vaqtdagi turli qiymatlar saqlanib `HELD` | Pull raw saqlaydi, Push gate/raw table’ni chetlab o‘tadi; `accepted: bool` conflict’ni ifodalamaydi | Unified ingestion, raw conflict group va `HELD` downstream holati. |

## 4. Hozirgi koddagi kamchiliklar

1. **Engine ulanmagan.** `select_main_locomotive` va `allocate_distance_to_wagons` application call-site’ga ega emas. GTK sync eski `_attribute_snapshot_mileage` bilan increment yozadi.
2. **Projection aralashgan.** Wialon Pull/Push, manual mileage endpoint va generic asset PATCH `fixed_assets.mileage`ni o‘zgartirishi mumkin. Wagon-only qilishdan oldin locomotive current mileage’ni qaysi service berishi belgilanadi.
3. **Snapshot va effective time farqli.** Membership `observed_from/to` sync kuzatuvlari; P0.1 ularni aniq transfer deb ko‘rsatishni taqiqlaydi.
4. **Koddagi limitlar biznes tasdig‘i emas.** Engine defaults `max_speed_kmh=150`, `agreement_tolerance_km=3`, `max_received_lag_seconds=900`; `wialon_quality`da 150 km/h va 10 km slack bor. Bular mavjud kod qiymatlari, tasdiqlangan policy emas.
5. **Handoff va boundary policy yetishmaydi.** Selector turli start/end boundary’larni conflict qiladi; same-locomotive gap interpolation orchestration’i yo‘q.
6. **Cross-train overlap himoyasi yo‘q.** Allocation dedup key train ID’ni o‘z ichiga oladi; bir vagon ikki train interval’ida bo‘lsa ikki allocation chiqishi mumkin.
7. **Raw identity va replay aralash.** GTK hash `fetched_at`ni qamraydi. Wialon raw unique hash bor, lekin bir unit/time uchun turli odometer qiymatlarini bitta conflict group’ga bog‘lash yo‘q.
8. **Run input provenance to‘liq emas.** `MileageCalculationRun.snapshot_id` bitta GTK snapshot’ga FK; run ko‘p snapshot/reading ishlatishi mumkin. `input_watermark` JSONB bor, relational input link yo‘q.
9. **Opening approval constraints yo‘q.** `created_by` bor, ammo approval state, `approved_by/at`, supersedes link va active uniqueness yo‘q.
10. **Ledger/idle status mapping’i yetarli emas.** Ledger DB status’i `active/superseded/rejected`; `HELD` yo‘q. Idle status’i `confirmed/unknown_activity/estimated`; `HELD` va idempotency yo‘q.
11. **Unmapped Push raw saqlanmaydi.** `WialonOdometerReading.asset_id` non-null; unmapped input’ni saqlash mumkin emas. Push raw event yozmaydi.
12. **Transaction partial bo‘lishi mumkin.** GTK raw/mirror/run va eski attribution alohida transaction; Pull mirror commit’i reading/asset updates’dan oldin.
13. **Schema/runtime noma’lum.** Model va 0027 migration source’da oltita jadval bor; canonical SQL fayllarda statik qidiruv topmadi. Live DB revision/catalog tekshirilmagan.
14. **Opening uchun UI yo‘q.** Fixed-asset modal mileage’ni generic PATCH orqali saqlaydi; administrator tasdiqlash amali ko‘rinmadi.

## 5. Maqsadli arxitektura va ma’lumotlar oqimi

### Oqim

```text
GTK adapter -> raw snapshot receipt -> GTK mirror + membership intervals
Wialon Pull ----\
                 -> common measurement ingestion -> raw reading/conflict
Wialon Push ----/                           -> cumulative counter gate
                                                   -> locomotive odometer intervals
GTK memberships + exact GTK handoff events ------> trusted source selector
                                                   -> HELD / CONFIRMED segment
                                                   -> bracket interpolation (ESTIMATED)
                                                   -> wagon membership allocation
                                                   -> idle evidence evaluator
                                                   -> calculation run + input links + ledger/issues
                                                   -> approved opening + eligible ledger projection
                                                   -> fixed_assets.mileage (WAGONS ONLY)
                                                   -> mileage_history + maintenance reconciliation
```

### Component boundary’lari

- **Source adapters:** GTK parser va Wialon client transport/parse qiladi; credential’lar calculation domain’ga uzatilmaydi. Push query token’lari hozir `main.py` middleware’da redaction qilinadi; raw payload’ga credential kirmasligi kerak.
- **Ingestion services:** `gtk.py` va Wialon router/service’lar canonical raw input’ni qabul qiladi, identity va persistence’ni boshqaradi. Pull va Push bir validation/persistence entrypoint’dan o‘tadi.
- **Measurement status:** `accepted` raw o‘lchov qabul qilinib saqlanganini bildiradi. `calculation_eligible` esa mapping, timestamp, gate va conflict tekshiruvlaridan keyin hisobga kiritishga ruxsatni bildiradigan alohida qaror. Raw accepted bo‘lishi uni avtomatik eligible qilmaydi.
- **Domain engine:** `wagon_mileage_engine.py` pure decision/allocation funksiyalarini saqlaydi; DB, HTTP, asset update, maintenance yoki permission boshqarmaydi.
- **Application orchestration — PROPOSED:** yangi `services/wagon_mileage.py` input watermark, source selection, membership allocation/idle, issue va ledger publish’ni boshqaradi.
- **Persistence — PROPOSED:** `repositories/mileage.py` raw link, run/ledger query, opening transition, unique retry va locking’ni bajaradi.
- **Projection:** umumiy mileage service faqat wagon `fixed_assets.mileage` cache’ini va history’ni yangilaydi. Locomotive odometer alohida saqlanadi; work-order/maintenance uchun locomotive current value manbasi migration’dan oldin belgilanadi.
- **API/UI:** router’lar RBAC va section scope’ni serverda enforce qiladi; frontend faqat `lib/api.ts` orqali chaqiradi.

### Uch status oqimi

| Holat | Ledger/run | API/UI | `fixed_assets.mileage` |
|---|---|---|---|
| `CONFIRMED` | Tekshirilgan bevosita source o‘lchovi yoki policy bo‘yicha tasdiqlangan allocation; active ledger bo‘lishi mumkin | Tasdiqlangan probeg | Wagon-only projection’ga kiradi (approved opening + eligible confirmed ledger). |
| `ESTIMATED` | `estimated=true`, manba/formula/boundary provenance bilan. Wialon bracket orqali hisoblangan masofa doim `ESTIMATED`. | Taxminiy deb alohida ko‘rsatiladi; confirmed km bilan aralashtirilmaydi | **PENDING APPROVAL:** A) projection’ga kiritmasdan alohida ko‘rsatish; B) admin tasdig‘idan keyin projection’ga qo‘shish. Reja variant tanlamaydi. |
| `HELD` | Run/issue, sabab va dalil saqlanadi; active ledger emas | Review queue; tasdiqlash/qayta hisoblash explicit amal | Projection va confirmed mileage o‘zgarmaydi. |

Tekshiruvdan o‘tgan, bevosita olingan Wialon o‘lchovi `CONFIRMED` bo‘lishi mumkin; bracket orqali o‘lchovlar orasidan hisoblangan masofa `ESTIMATED` bo‘ladi.

## 6. Jadvallar va schema o‘zgarishlari rejasi

**Amaldagi manba holati:** ORM va `0027_wagon_mileage_engine.py` mavjud. Canonical SQL fayllarida oltita `CREATE TABLE` statik qidiruvda topilmadi. Runtime DB table/revision holati `UNKNOWN`; DB’ga ulanilmadi.

| Jadval | Hozirgi holat | Reja / ehtimoliy schema ishi |
|---|---|---|
| `gtk_raw_snapshots` | 0027/model’da payload, sync run, effective/received time, unique payload hash | `effective_at`ni source event deb qabul qilmaslik. Raw receipt audit’i va calculation idempotency’sini ajratish; incomplete/suspicious snapshot retention qoidasi. |
| `wialon_odometer_readings` | 0027/model’da mapped `asset_id NOT NULL`, source unit, reading/received time, `accepted` bool, reason, unique hash | Push/Pull uchun unified persistence. Conflict group/status va unmapped raw zaruratini hal qilish; same unit/time turli values’ni ikkalasini ham saqlash. |
| `wagon_mileage_opening_balances` | 0027/model’da asset, value, effective time, `created_by`, note; approval fields yo‘q | `pending/approved/superseded`, approver/time, audit va supersedes; active approved unique. Same actor policy `UNKNOWN`. |
| `mileage_calculation_runs` | 0027/model’da version, status (`running/completed/partial/failed`), JSON watermark/summary, `snapshot_id` | Ko‘p snapshot/reading input linkage; `HELD` semantics yoki issue table; status lifecycle. |
| `wagon_mileage_ledger` | 0027/model’da wagon/loco assets, period/km/estimated/status/idempotency; raw FK yo‘q | Source input linkage, active projection query, rounding residual va recalculation scope semantics. |
| `wagon_idle_periods` | 0027/model’da wagon, aggregate, period, status/evidence | Run/input linkage, HELD/conflict va idempotency; threshold tasdiqlangach detector yozish. |
| `mileage_calculation_inputs` — yangi, `PROPOSED` | Mavjud emas | Run’ni ko‘p GTK snapshot/Wialon reading bilan relational bog‘lash; typed FK va source identity. |
| `mileage_calculation_issues` — yangi, `PROPOSED` | Mavjud emas | Conflict, missing handoff/bracket va HELD sabablarini input/time scope bilan saqlash; manual resolution audit. |
| `gtk_train_members` | Mavjud history: `observed_from/to`, `gtk_begin_time`, `is_main`; train/object polymorphic ID’larda FK/overlap guard yo‘q | Snapshot boundary’ni exact transfer demaslik; cross-train wagon overlap uchun DB guard usuli. |
| `fixed_assets`, `mileage_history` | `mileage` default 0; history source `wialon/manual/gtk`, raw/run FK yo‘q | `fixed_assets.mileage` wagon-only projection; locomotive alohida read model; history provenance migration’da hal qilinadi. |

**Migration tartibi:** deployed Alembic head noma’lum. 0027 source’da mavjudligi DB’da qo‘llanganini isbotlamaydi. Keyingi forward migration faqat current head/schema’ni ruxsatli disposable PostgreSQL nusxada tekshirgach rejalashtiriladi; `0028` faqat nomzod, tasdiqlangan revision emas. 0027 downgrade oltita jadvalni o‘chiradi; data yozilgach bu xavfsiz rollback emas. `postgres/schema.sql` bu ishda o‘zgartirilmaydi; `test_schema_drift` parity talabi va Alembic-only siyosatini repo owner hal qiladi.

## 7. Backend service va router rejasi

| Fayl | Holat | Rejalashtirilgan o‘zgarish | Sabab / bog‘liqlik | Test |
|---|---|---|---|---|
| `backend/app/services/wagon_mileage_engine.py` | Mavjud, pure funksiyalar | Policy input, status/provenance va qaror natijasini kengaytirish; tasdiqlanmagan qiymatni hardcode qilmaslik | Selector/allocation bazasi; orchestration emas | Unit: tanlov, bracket, handoff, overlap, rounding |
| `backend/app/services/wagon_mileage.py` | Yangi, `PROPOSED` | Run orchestration, watermark, selector, membership split, idle evidence, ledger publish | Domain flow’ni GTK/Wialon va DB’dan ajratish | Service tests + DB transaction |
| `backend/app/repositories/mileage.py` | Yangi, `PROPOSED` | Raw/input/run/ledger/opening query, lock, replay/idempotency | DB persistence va concurrency | PostgreSQL integration |
| `backend/app/schemas/mileage.py` | Yangi, `PROPOSED` | Run, ledger, opening, issue, status response | Router request/response contract | Schema/API tests |
| `backend/app/services/gtk.py` | Mavjud | Raw receipt/run’ni saqlash; `sync_gtk`ni yangi engine’ga ulash; eski `_attribute_snapshot_mileage` writer’ini controlled cutover qilish | Ayni paytda eski attribution ishlaydi | GTK sync, raw replay, held snapshot tests |
| `backend/app/services/mileage_attribution.py` | Mavjud eski pure engine | Cutover’da eski writer’ni o‘chirish/deprecate qilish yoki vaqtincha faqat compatibility tests’da qoldirish | Ikki writer double-count qilmasin | Old/new parity va cutover tests |
| `backend/app/services/wialon.py` | Mavjud Pull | Pull reading’ni unified ingestion service’ga ulash; direct asset mileage publish’ni ajratish | Hozir gate/raw va asset update turli qadamlarda | Pull gate, raw, transaction, retry |
| `backend/app/routers/wialon.py` | Mavjud Push | Payload’ni canonical measurement’ga normalize qilib umumiy service’ga berish | Push hozir gate/raw’ni chetlab o‘tadi | FastAPI route + `httpx.MockTransport` transport tests |
| `backend/app/routers/wialon_pull.py` | Mavjud admin Pull routes | Status/sync API contract’ini saqlash; yangi run/held information talabini schema’ga ulash | Mavjud admin sync path | Permission/API tests |
| `backend/app/services/assets.py` | Mavjud | `receive_wialon_update`, generic manual save va `_save_mileage_change`ni projection service’ga moslash | `fixed_assets.mileage`, history va maintenance reconcile shu yerda | Asset/service regression |
| `backend/app/routers/assets.py` | Mavjud | Generic mileage PATCH/POST’ni opening approval’ni chetlab o‘tmaydigan contract’ga o‘tkazish; history/read scope saqlash | Hozir manual mileage API mavjud | Role/scope/API tests |
| `backend/app/routers/gtk.py` | Mavjud | Run/ledger/HELD read route’larini ehtiyojga ko‘ra qo‘shish | GTK hozir eski wagon log/status API’ni beradi | E2E scripts |
| `backend/app/routers/mileage.py` | Yangi, `PROPOSED` | Opening submit/approve, ledger/run/issue read API’lari | Mileage schema/service; RBAC/section scope | Router/API tests |
| `backend/app/main.py` | Mavjud | Router va background lifecycle’ni ulash; parallel task writer’larini oldini olish | Sync task’lar shu yerda boshqariladi | Lifespan/task tests |
| `backend/alembic/versions/0028_*.py` | Yangi, faqat future candidate | 0027’dan keyingi forward migration; aniq filename/revision current deployed head tasdig‘idan keyin | 0027 schema mismatch va approval/input/status ehtiyojlari | Offline render + disposable PostgreSQL upgrade/downgrade |
| `backend/app/models/mileage.py` | Mavjud | Faqat tasdiqlangan schema o‘zgarishlariga mos model update | Oltita 0027 model shu yerda | ORM/schema parity |
| `backend/app/models/__init__.py` | Mavjud | Yangi model qo‘shilsa `Base.metadata` import’iga kiritish | `alembic/env.py` shu metadata’dan foydalanadi | Metadata/migration tests |
| `backend/app/models/assets.py` | Mavjud | Wagon projection/locomotive mileage ownership’ni model contract’da ajratish zarurati tekshiriladi | `FixedAsset.mileage`, `MileageHistory` | Model/API/maintenance regression |
| `backend/app/models/gtk.py` | Mavjud | Raw/member/log FK va interval identity ehtiyoji ko‘rib chiqiladi | GTK source IDs va joriy membership history | ORM/schema + membership tests |
| `backend/app/models/wialon_counters.py` | Mavjud | Pull counter state’ni alohida locomotive source state sifatida saqlash; schema faqat tasdiq bilan | `wialon_quality`, Wialon ingestion | Counter gate/persistence tests |
| `backend/app/models/wialon_units.py` | Mavjud | Latest-unit mirror’i raw history’ning o‘rnini bosmasligi tekshiriladi | Wialon Pull UI/status | Pull unit tests |
| `backend/app/repositories/gtk.py` | Mavjud | Raw receipt lookup, effective membership query, cross-train locking’ni qo‘shish zarurati | `GtkTrainMember`, `GtkRawSnapshot` | PostgreSQL membership/replay tests |
| `backend/app/repositories/wialon_counters.py` | Mavjud | Accepted counter state’ni unified ingestion transaction’iga ulash | Pull baseline/delta gate | Pull concurrency/replay tests |
| `backend/app/repositories/wialon_units.py` | Mavjud | Latest mirror upsert’ini raw reading persistence’dan aniq ajratish | Wialon unit list/status | Pull integration tests |
| `backend/app/repositories/assets.py` | Mavjud | `mileage_history` source/run provenance va wagon-only projection query’larini baholash | Asset service va history API | Projection/history tests |
| `backend/app/services/maintenance.py` | Mavjud | `reconcile_asset_plans`ni umumiy wagon projection publish’idan chaqirish | Mileage save hozir maintenance’ni reconcile qiladi | Maintenance mileage regression |
| `backend/app/repositories/maintenance.py` | Mavjud | Asset row lock/reconciliation dependency’larini transaction plan’da qayta ishlatish | Mavjud `lock_asset_mileage` | Lock/concurrency integration |
| `backend/app/services/audit_log.py` | Mavjud | Opening approval va calculation action’larida actor/system context’ni reuse qilish | Mavjud audit actor/system context | Audit actor tests |
| `backend/app/models/audit_log.py` | Mavjud | Mavjud audit log’dan foydalanish; schema kengayishi faqat ehtiyoj tasdiqlansa | Audit actor/action history | Audit integration |
| `backend/app/integrations/gtk_client.py` | Mavjud | Raw snapshot timestamp/complete contract’ini aniqlashtirish; source bermagan event time uydirmaslik | `GtkSourceAdapter`, `sync_gtk` | Parse/time normalization tests |
| `backend/app/integrations/wialon_client.py` | Mavjud | Push/Pull canonical reading unit/time mapping’ini saqlash | `WialonClient`, `httpx.MockTransport` | Transport parse/retry tests |
| `backend/app/schemas/assets.py` | Mavjud | Generic mileage write va opening approval DTO scope’ini ajratish | Asset router, `lib/api.ts` | Schema/role tests |
| `backend/app/schemas/gtk.py` | Mavjud | GTK run/status/ledger response extension’i kerakmi, aniqlash | GTK router/client | API contract tests |
| `backend/app/schemas/wialon.py` | Mavjud | Push/Pull canonical timestamp/reading response contract’i | Wialon routers | Payload validation tests |
| `backend/app/services/wialon_quality.py` | Mavjud | Mavjud gate constants’larini approved MileagePolicy’dan ajratish | Pull ingestion; policy values `UNKNOWN` | Gate boundary tests |
| `backend/app/core/config.py` | Mavjud | Faqat tasdiqlangan runtime policy config’larini qo‘shish; hozircha qiymat belgilamaslik | Max interval/idle policy owners | Config validation tests |
| `lib/api.ts` | Mavjud | Opening/run/ledger/issue types va client metodlari | Backend mileage API | Typecheck, client tests |
| `app/dashboard/directories/assets/page.tsx` | Mavjud | Generic mileage edit’ni opening approval/projection/status bilan almashtirish | FixedAsset API va GTK detail | UI/API contract tests |
| `app/dashboard/os/gtk/page.tsx` | Mavjud | Raw snapshot emas, faqat ruxsatli run/membership/held status ko‘rsatish zarurati | GTK API | Component/API tests |
| `app/dashboard/os/wialon/page.tsx` | Mavjud | Raw reading conflict va held status ko‘rsatish zarurati | Wialon API | Component/API tests |
| `app/dashboard/os/wagon-mileage/page.tsx` | Yangi, `PROPOSED` | Ledger/run/held review uchun alohida sahifa, agar modal yetarli bo‘lmasa | Mileage API; mahsulot owner tasdig‘i | Component/e2e |
| `backend/tests/test_wagon_mileage_engine.py` | Mavjud | Handoff/conflict/snapshot transfer/idle policy unit coverage’ini kengaytirish | Pure engine | Unit tests |
| `backend/tests/test_mileage_attribution.py` | Mavjud eski test | Cutover’da eski semantics’ni regression/retirement sifatida boshqarish | Eski GTK writer | Parity/cutover tests |
| `backend/tests/test_gtk.py` | Mavjud | `sync_gtk` raw + new engine orchestration/transaction tests | GTK service/repository | Async unit tests |
| `backend/tests/test_wialon_pull.py` | Mavjud | Raw persistence, Push/Pull parity, conflict va retry tests | Wialon ingestion/service | `httpx.MockTransport` + async tests |
| `backend/tests/test_wialon_quality.py` | Mavjud | Approved policy bilan counter gate boundary tests | `wialon_quality.py` | Unit tests |
| `backend/tests/test_schema_drift.py` | Mavjud | ORM/SQL parity va Alembic-only schema policy kelishilgach expectation’larni yangilash | Model metadata + canonical SQL contract | Schema parity test |
| `backend/tests/test_asset_p6_audit.py` | Mavjud | Migration head expectation’ini tasdiqlangan forward chain’ga moslashtirish | Alembic revision chain | Migration chain test |
| `backend/tests/test_wagon_mileage_integration.py` | Yangi, `PROPOSED` | Disposable PostgreSQL transaction, overlap, idempotency, projection tests | Models/repositories/services | DB integration |
| `backend/scripts/e2e_wagon_mileage.py` | Yangi, `PROPOSED` | Yangi endpoint’lar uchun project uslubidagi E2E | Mileage API | User-run test API |
| `postgres/schema.sql` | Mavjud; bu scope’da o‘zgartirilmaydi | Repo owner `test_schema_drift` va Alembic-only policy’ni hal qilmaguncha tegilmaydi | Schema parity CI blocker | Schema drift test |

## 8. Frontend va API rejasi

### Hozirgi API

- `POST/GET /api/v1/wialon/input` — Push transport; hozir Pull gate/history bilan umumiy emas.
- `POST /api/v1/wialon/sync`, `GET /api/v1/wialon/status` — admin Pull.
- `POST /api/v1/gtk/sync`, `GET /api/v1/gtk/wagon-mileage`, `GET /api/v1/fixed-assets/{id}/gtk` — GTK sync va eski log.
- `GET /api/v1/fixed-assets/{id}/mileage-history`, `POST /api/v1/fixed-assets/{id}/mileage`, `PATCH /api/v1/fixed-assets/{id}` — history/manual write; opening approval alohida emas.

### API additions — `PROPOSED`, nomlar yakuniy emas

- Opening balance submit va admin-only approve/reject/history.
- Calculation run/status va HELD/conflict issue list/detail; resolution faqat yangi calculation request, raw input’ni tahrirlash emas.
- Wagon ledger/history’ni asset va vaqt bo‘yicha o‘qish; `CONFIRMED/ESTIMATED/HELD` status’lari alohida.
- Idle period/evidence/status o‘qish; threshold tasdiqlanmaguncha auto-confirm action bo‘lmasin.
- `POST /fixed-assets/{id}/mileage` va umumiy PATCH opening approval’ni chetlab o‘tmasin; backward compatibility uchun staged migration/deprecation reja kerak.
- Barcha frontend chaqiruvlari `lib/api.ts` orqali; brauzer DB’ga to‘g‘ridan-to‘g‘ri ulanmaydi.

### Frontend

- `app/dashboard/directories/assets/page.tsx`: hozir umumiy mileage edit va GTK log detail bor; opening submit/approve, estimate/held history yo‘q. Projection/status/provenance’ni farqlash va manual edit’ni approval flow’ga o‘tkazish rejalashtiriladi.
- `app/dashboard/os/gtk/page.tsx`: GTK source; `app/dashboard/os/wialon/page.tsx`: Wialon unit source. Bular ledger review sahifasining o‘rnini bosmaydi.
- Alohida wagon mileage sahifasi topilmadi. `app/dashboard/os/wagon-mileage/page.tsx` — yangi, `PROPOSED`; ledger/run/held triage modal’ga sig‘masa mahsulot owner tasdiqlaydi.
- `lib/api.ts`: yangi opening, ledger, run va issue typelar/client metodlari. Work-order opening snapshot `mileage_at_creation` o‘zgartirilmaydi.

## 9. Ledger, transaction va idempotency

1. **Raw receipt:** payload fingerprint receipt identity’dan alohida. GTK/Wialon raw audit talabi calculation dedup’ni raw history’ni o‘chirishga olib kelmasin.
2. **Wialon identity:** normalized source unit + source reading time + measurement identity. Bir xil time’da turli odometer bo‘lsa ikkala raw row saqlanadi, conflict group yaratiladi va scope `HELD`; avtomatik tie-break yo‘q.
3. **Calculation key:** algorithm version + approved policy version + GTK snapshot IDs + Wialon reading IDs + membership bounds + wagon scope. Unique idempotency key retry/replay’ni bir hisobga keltiradi.
4. **Run input:** bitta run ko‘p snapshot va reading ishlatishi mumkin; faqat `snapshot_id` yoki JSON watermark bilan cheklanmaslik. Relational input link — `PROPOSED`.
5. **Recalculation:** muvaffaqiyatli yangi run oldingi active qatorlarni scope bo‘yicha `superseded` qilib, yangisini active qiladi. Failed run eski active ledger/projection’ni saqlaydi.
6. **Atomic publish:** affected wagon asset’larni barqaror ID tartibida lock; ledger, opening eligibility, cache, `mileage_history`, maintenance reconciliation bitta transaction’da. Raw ingestion alohida commit bo‘lishi mumkin, hisob xatosida raw saqlanadi.
7. **Opening:** faqat approved row calculation’ga kiradi; approval actor/time audit qilinadi; har vagonda bitta active approved balance. Same actor policy `UNKNOWN`.
8. **Projection:** active eligible wagon ledger + approved opening’dan recompute. Increment-only `+= delta` replay’ga chidamli emas. `ESTIMATED` bo‘yicha Option A: projection’ga qo‘shmasdan alohida ko‘rsatish; Option B: admin tasdig‘idan so‘ng projection’ga qo‘shish va provenance’ni saqlash. **`PENDING APPROVAL`; reja variant tanlamaydi.**
9. **Locomotive:** Wialon cumulative state/accepted readings alohida. `fixed_assets.mileage`ga locomotive qiymati publish qilinmaydi; work-order/maintenance consumer’lar uchun current locomotive value manbasi belgilanadi.
10. **Concurrency:** Python `asyncio.Lock` faqat bitta process’ga tegishli. Multi-replica uchun unique idempotency va DB row/advisory lock yoki tasdiqlangan serial scope kerak.

## 10. Xatoliklar va conflict handling

| Vaziyat | Saqlash | Holat | Projection/amal |
|---|---|---|---|
| GTK parse/incomplete/suspicious | Raw receipt + sync run/error | `HELD` | Membership/mileage publish qilinmaydi. |
| GTK exact handoff time yo‘q | Snapshot va oldingi membership dalili | Handoff `HELD` | `observed_at` bilan almashtirilmaydi. |
| Wialon bracket yo‘q/yaroqsiz | Raw reading + gate reason | `HELD` | Gap boshqa locomotive counter’i bilan yopilmaydi. |
| Bir unit/time’da turli odometer | Ikkala raw + conflict identity | `HELD` | Qiymatlardan biri avtomatik tanlanmaydi. |
| Odometer pasayishi/reset/stale | Raw + rejection reason; accepted state oldinga surilmaydi | `HELD`/rejected input | Wagon projection o‘zgarmaydi. |
| Vagon ikki train interval’ida overlap | Raw/membership evidence + issue | `HELD` | Allocation qilinmaydi; DB concurrency ham bloklanadi. |
| Wialon locomotive stop, lekin wagon idle dalili yo‘q | GTK membership va Wialon telemetry birga tekshiriladi | Dalil mos/yetarli bo‘lmasa `HELD` | Faqat locomotive stop’i vagon bekor turganini tasdiqlamaydi; idle km qo‘shilmaydi. |
| Idle dalili zid/yetarli emas | Ikkala source dalili | `HELD`/unknown activity | Idle tasdiqlanmaydi; km qo‘shilmaydi. |
| Ledger/projection transaction fail | Raw va oldingi active ledger qoladi; failed run yoziladi | Failed/`HELD` | Cache/history/maintenance qisman o‘zgarmaydi. |

Conflict’ni kim va qanday ko‘rib chiqishi `UNKNOWN`; reja avtomatik resolution belgilamaydi.

## 11. Test rejasi

### Unit va pure tests

- Bitta locomotive/bitta wagon; bitta locomotive/ko‘p wagon; fizik intervalda odometrlarni qo‘shmaslik/o‘rtachalam aslik.
- Ko‘p locomotive candidate: ishonchli tanlov, conflict, reliable source yo‘q -> `HELD`. Priority qiymatlari faqat tasdiqdan keyin test qilinadi.
- GTK handoff exact timestamp bor/yo‘q; timestamp yo‘q -> estimate emas, `HELD`.
- Same-locomotive Wialon bracket interpolation; bracket yo‘q, max interval’dan oshish, odometer reset/pasayish.
- Snapshot transfer window allocation `ESTIMATED`; snapshot vaqtini exact handoff demaslik.
- Cross-train overlap rejection, duplicate snapshot replay va idempotency.
- Push/Pull ayni reading: bir marta persist/process; bir unit/time turli qiymat: ikkalasi saqlanib conflict + `HELD`.
- Opening pending/approved, tasdiqlanmagan balans hisobga kirmasligi, audit actor/time; same submitter/approver policy’ning tasdiqlangan varianti.
- Wialon locomotive stop’ining o‘zi wagon idle’ini tasdiqlamasligi; GTK membership va Wialon telemetry birga tekshirilishi; conflict/insufficient evidence `HELD`; duration threshold faqat tasdiqdan keyin.
- `CONFIRMED/ESTIMATED/HELD` API/projection farqi; locomotive mileage wagon projection’ga kirmasligi.

### Integration tests — disposable PostgreSQL

- GTK raw snapshot/membership/run flow; incomplete/suspicious snapshot raw saqlab mileage publish qilmasligi.
- Push/Pull bir xil canonical ingestion, validation, raw/idempotency va conflict rule’dan o‘tishi.
- Bir unit/time’da turli probeg: ikkala raw saqlanishi, segment `HELD`, projection o‘zgarmasligi.
- GTK exact handoff va snapshot-only wagon transfer; `observed_at`/`effective_from/to` farqini tekshirish.
- Ikki worker replay/concurrency; bitta active ledger/projection natijasi.
- Failure rollback: ledger/cache/history/maintenance birga rollback, raw va oldingi projection saqlanishi.
- Opening admin approval audit’i, role/section scope; approval’siz asset mileage o‘zgarmasligi.
- Maintenance plan va `work_orders.mileage_at_creation` regression; existing snapshot’lar qayta yozilmasligi.
- Wialon HTTP transport testlarida mavjud `httpx.MockTransport` uslubini qayta ishlatish; yangi API route’lar uchun `backend/scripts/e2e_*.py` uslubidagi E2E.

**Audit cheklovi:** P0.2 davomida testlar ishga tushirilmaydi. Oldingi test natijalari yangi flow integration’i uchun dalil emas; implementation’da qayta bajariladi.

## 12. Bosqichma-bosqich implementatsiya tartibi

P0.3 quyidagi oltita mustaqil, alohida review qilinadigan scope’ga bo‘linadi. Ular o‘zaro dependency’ga ega: 3.1 schema contract’lari 3.2–3.5 uchun kerak; 3.6 verification barcha oldingi scope’lar birlashgach bajariladi. Hech bir bosqich P0.2’da ishga tushirilmaydi.

### P0.3.1 — Database/model/ledger/opening balance

- **Fayllar:** `backend/app/models/mileage.py`, `backend/app/models/__init__.py`, yangi `backend/app/repositories/mileage.py`, `backend/app/schemas/mileage.py`, opening service uchun yangi `backend/app/services/mileage_opening.py`, yangi Alembic revision (`0028` faqat live head tasdiqlansa), `backend/tests/test_schema_drift.py`, `backend/tests/test_asset_p6_audit.py`.
- **Dependency:** `0027` deployed/repository head’i va DB schema disposable nusxada tekshiriladi; approval state/actor, raw-input linkage, `CONFIRMED/ESTIMATED/HELD` mapping’i va schema parity qarori tasdiqlanadi. `postgres/schema.sql` bu reja doirasida o‘zgarmaydi.
- **Testlar:** revision chain bitta head; ORM/model parity; FK/check/unique; one-active-approved balance; submit/approve audit; downgrade data-loss behavior’ni disposable DB’da ko‘rib chiqish.
- **Acceptance:** tasdiqlanmagan opening ledger hisobiga kirmaydi; admin tasdig‘i alohida amal va audit actor/time bilan yoziladi; bir vagonda faqat bitta active approved balance; har calculation run source input’lariga audit qilinadigan linkka ega.
- **Rollback/security:** faqat forward Alembic; backup va restore rehearsal; downgrade data’ni o‘chirishi hujjatlashtiriladi. Opening approve admin-only; section scope backend query’da. Production DB/deploy tasdiqsiz yo‘q.

### P0.3.2 — GTK membership va snapshot integration

- **Fayllar:** `backend/app/integrations/gtk_client.py`, `backend/app/integrations/gtk_adapter.py`, `backend/app/services/gtk.py`, `backend/app/repositories/gtk.py`, `backend/app/models/gtk.py`, `backend/app/models/mileage.py`, `backend/tests/test_gtk.py`, `backend/tests/test_mileage_attribution.py`; ehtiyoj bo‘lsa keyingi Alembic revision.
- **Dependency:** exact `effective_from/effective_to` uchun GTK field mapping; snapshot transfer formulasi `UNKNOWN` bo‘lsa faqat interval dalilini saqlash va `ESTIMATED`ni publish’dan ajratish; cross-train exclusion usuli va raw receipt identity tasdiqlanadi.
- **Testlar:** complete/incomplete/suspicious snapshot; duplicate receipt; membership close/open; transfer bo‘yicha observed window (snapshot vaqti exact event emas); same wagon cross-train overlap `HELD`; transaction failure.
- **Acceptance:** har raw receipt audit qilinadi; `observed_at` source effective time sifatida ishlatilmaydi; aniq GTK handoff bo‘lmasa locomotive handoff `HELD`; wagon transfer natijasi `ESTIMATED`; raw snapshot qabulidan keyingi calculation failure raw’ni yo‘qotmaydi.
- **Rollback/security:** GTK mirror/membership’ni buzmaslik; yangi writer feature-controlled va eski writer bilan parallel emas; raw payload API orqali ommaviy chiqarilmaydi; GTK credential/log himoyasi saqlanadi.

### P0.3.3 — Wialon Push/Pull unified ingestion

- **Fayllar:** `backend/app/integrations/wialon_client.py`, `backend/app/routers/wialon.py`, `backend/app/routers/wialon_pull.py`, `backend/app/services/wialon.py`, `backend/app/services/assets.py`, `backend/app/repositories/wialon.py`, `backend/app/repositories/wialon_counters.py`, `backend/app/repositories/wialon_units.py`, `backend/app/models/mileage.py`, `backend/app/schemas/wialon.py`, `backend/tests/test_wialon_pull.py`, `backend/tests/test_wialon_quality.py`.
- **Dependency:** Push event ID/source timestamp/unit contract’i va bitta unit/time conflict policy’si; max bracket/freshness policy `UNKNOWN`; unmapped raw row saqlash talabi; counter-state va raw retention alohida ko‘riladi.
- **Testlar:** `httpx.MockTransport` Pull parse/retry; FastAPI Push payload; bir xil event Push+Pull replay; same unit/time turli values’ni ikkalasini saqlash va `HELD`; stale/decrease/reset/unmapped; partial batch failure.
- **Acceptance:** Push va Pull bir canonical validation/raw/idempotency/publish service’dan o‘tadi; `accepted` raw input qabul qilinganini bildiradi, `calculation_eligible` esa gate + source mapping + time/conflict tekshiruvlaridan keyingi alohida qaror bo‘ladi. Ayni vaqt, turli qiymatlar o‘chirilmaydi, conflict bo‘ladi, `HELD`; Wialon locomotive mileage `fixed_assets.mileage`ga yozilmaydi.
- **Rollback/security:** Push token’lari URL/log/raw payload’ga yozilmaydi; credential response’da qaytarilmaydi. Pull per-unit/sync transaction boundary hujjatlashtiriladi; rollback raw input’ni o‘chirmaydi. Eski writer faqat kontrolli cutover’dan keyin o‘chiriladi.

### P0.3.4 — Calculation orchestration

- **Fayllar:** `backend/app/services/wagon_mileage_engine.py`, yangi `backend/app/services/wagon_mileage.py`, `backend/app/services/gtk.py`, `backend/app/services/wialon.py`, `backend/app/services/mileage_attribution.py`, `backend/app/repositories/mileage.py`, `backend/app/models/mileage.py`, `backend/tests/test_wagon_mileage_engine.py`, `backend/tests/test_mileage_attribution.py`.
- **Dependency:** 3.1 ledger/input schema; 3.2 GTK interval input; 3.3 canonical Wialon reading; selection priority va policy max interval qiymatlari owner tomonidan tasdiqlangan yoki tegishli segment `HELD` qilinishi rasman qabul qilingan.
- **Testlar:** P0.1 test ssenariylarining pure/unit qismi; locomotive handoff, same-loco bracket, snapshot transfer, `CONFIRMED/ESTIMATED/HELD`, idle evidence, deterministic idempotency/recalculation.
- **Acceptance:** engine real sync pipeline’dan chaqiriladi; bir physical segment’da bitta locomotive source; boshqa locomotive’larning cumulative odo’lari qo‘shilmaydi/ayrilmaydi; no exact GTK handoff `HELD`; same-loco bracket interpolation `ESTIMATED`; cross-train overlap `HELD`; idle km qo‘shmaydi.
- **Rollback/security:** calculation fail bo‘lsa run fail/held qilib raw va oldingi active ledger/projection’ni saqlash; old writer bilan parallel publish yo‘q; run log’ida maxfiy qiymat bo‘lmaydi.

### P0.3.5 — API/frontend/projection

- **Fayllar:** `backend/app/routers/mileage.py` (yangi), `backend/app/routers/assets.py`, `backend/app/routers/gtk.py`, `backend/app/schemas/mileage.py` (yangi), `backend/app/schemas/assets.py`, `lib/api.ts`, `app/dashboard/directories/assets/page.tsx`, `app/dashboard/os/gtk/page.tsx`, `app/dashboard/os/wialon/page.tsx`; yangi `app/dashboard/os/wagon-mileage/page.tsx` faqat mahsulot owner tasdiqlasa.
- **Dependency:** 3.1–3.4 service/schema; opening same-actor approval `UNKNOWN`; `ESTIMATED` projection inclusion `PENDING APPROVAL`; existing `mileage_at_creation` contract’ini saqlash.
- **Testlar:** route role/section scope; opening submit/admin approve/reject; ledger/run/issue read; TypeScript typecheck/build; API E2E; UI’da uch status va source ko‘rinishi.
- **Acceptance:** approval’siz balance hisobga kirmaydi; admin tasdig‘i va audit ko‘rinadi; `HELD`/`ESTIMATED` confirmed mileage deb ko‘rsatilmaydi; `fixed_assets.mileage` faqat wagon projection; locomotive probegi alohida; current history/work-order snapshot saqlanadi.
- **Rollback/security:** API role va master section scope server-side; generic PATCH/POST opening approval’ni chetlab o‘tmaydi; frontend faqat `api` client’dan; route’larni feature/permission’siz ochmaslik.

### P0.3.6 — Regression va integration tests

- **Fayllar:** mavjud `backend/tests/test_wagon_mileage_engine.py`, `test_mileage_attribution.py`, `test_gtk.py`, `test_wialon_pull.py`, `test_wialon_quality.py`, `test_schema_drift.py`, `test_asset_p6_audit.py`; yangi `backend/tests/test_wagon_mileage_integration.py` va `backend/scripts/e2e_wagon_mileage.py` — yangi endpoint bo‘lsa.
- **Dependency:** P0.3.1–3.5 code freeze; disposable PostgreSQL va test API; live/production DB emas.
- **Testlar:** §11 unit/integration ro‘yxati; `httpx.MockTransport`; replay, conflict, exact/unknown handoff, opening approval, idle evidence, concurrency, rollback, migration upgrade/downgrade rehearsal, work-order/maintenance regression.
- **Acceptance:** barcha relevant unit va disposable DB integration test’lari o‘tadi; schema/revision contract mos; API E2E va frontend typecheck/build natijasi qayd etiladi; no secret output; no production action.
- **Rollback/security:** test data disposable; E2E faqat test API’da; migration rehearsal’dan keyin DB snapshot/restore; test failure’da rollout’ni to‘xtatish va kod yoki ma’lumotni yashirincha qayta tiklamaslik.

## 13. Bosqichlar uchun acceptance criteria

| Bosqich | Qabul mezoni |
|---|---|
| P0.3.1 Database/model/ledger/opening | Migration head disposable DB’da aniq; approval va active uniqueness constraint ishlaydi; migration downgrade data loss xavfi dokumentlangan; approved balance bo‘lmasa wagon projection’ga opening qo‘shilmaydi. |
| P0.3.2 GTK membership/snapshot | Raw snapshot receipt saqlanadi; `observed_at` UTC va `effective_from/to`dan ajralgan; ayni membership replay idempotent; cross-train overlap `HELD`; snapshot transfer faqat `ESTIMATED`. |
| P0.3.3 Wialon Push/Pull | Ikkala oqim canonical service’dan o‘tadi; `accepted` va `calculation_eligible` alohida; duplicate event bir marta hisoblanadi; same-time/different-value ikkala raw bilan `HELD`; secretlar log/raw/API’da yo‘q. |
| P0.3.4 Orchestration | Bir physical segment bir odometer source; locomotive handoff faqat aniq GTK vaqti; same-loco bracket bo‘lsa `ESTIMATED`, aks holda `HELD`; idle GTK+Wialon bilan tekshiriladi va locomotive stop’i yolg‘iz tasdiq bo‘lmaydi; idle km qo‘shmaydi. |
| P0.3.5 API/frontend/projection | Opening admin approval va audit; role/section scope server’da; uch status farqi aniq; `fixed_assets.mileage` wagon-only; locomotive probegi alohida; legacy work-order/maintenance contract saqlangan. |
| P0.3.6 Regression/integration | Unit, disposable PostgreSQL integration, API E2E va frontend typecheck/build natijalari qayd etilgan; concurrency/replay/rollback hamda schema/migration chain qamrab olingan. |

## 14. Risklar va rollback rejasi

- **Ikki writer:** eski GTK attribution va yangi engine parallel yozsa double count. Cutover’da faqat bitta writer; rollback toggle yangi va eski writer’ni birga yoqmasin.
- **Asset semantikasi:** `fixed_assets.mileage` locomotive uchun ishlatilgan. Wagon-only qilish work-order/maintenance current mileage’ni buzishi mumkin; locomotive read source belgilanmasdan cutover qilinmaydi.
- **Raw dedup data loss:** unique payload hash receipt history’ni o‘tkazib yuborishi mumkin. Raw retention identity’ni calculation idempotency’dan ajratish.
- **Partial commit:** GTK va Wialon bir nechta transaction qiladi. Raw saqlanadi; publish atomic bo‘ladi; fail run eski active projection’ni saqlaydi.
- **Constraint extension:** overlap exclusion `btree_gist` talab qilishi mumkin; DB owner/disposable rehearsal tasdiqlamasdan migration yo‘q.
- **0027 downgrade:** oltita table’ni tushiradi. Data yozilgach downgrade xavfsiz rollback emas; forward fix va backup/restore rejasi kerak.
- **Schema parity:** `test_schema_drift` yangi ORM table’larni canonical SQL’da kutadi, ammo Alembic-only siyosat `schema.sql`ni o‘zgartirishga ruxsat bermaydi. Repo owner hal qilmaguncha CI blocker.
- **Rollback taklifi — `PROPOSED`:** feature’ni o‘chirish, yangi publish’ni to‘xtatish va oldingi approved projection’ni ko‘rsatish; raw/ledger’ni o‘chirmaslik. Eski GTK writer’ni avtomatik yoqmaslik.

## 15. UNKNOWN va PENDING APPROVAL savollari

### Biznes tasdig‘i

1. GTK/Wialon source mos kelganda locomotive selection’ning aniq ustuvorlik formulasi qanday? Ziddiyat bo‘lsa `HELD` — confirmed.
2. GTK’da qaysi field haqiqiy locomotive handoff time’ni tasdiqlaydi? Field bo‘lmasa handoff `HELD` — confirmed; source mapping noma’lum.
3. Wialon same-locomotive bracket uchun max vaqt oralig‘i va freshness limit qanday? `UNKNOWN`; koddagi 150/10/900 qiymatlari tasdiq emas.
4. GTK/Wialon ziddiyatini kim va qaysi review action bilan hal qiladi?
5. Snapshot oralig‘idagi wagon allocation formulasi qanday? Natija `ESTIMATED` — confirmed; formula noma’lum.
6. Idle minimal davomiyligi, speed/state ustuvorligi va confirmed-idle dalili nima?
7. Opening balance submitter va approver bir odam bo‘lishi mumkinmi? `UNKNOWN`.
8. `ESTIMATED` `fixed_assets.mileage`ga kiradimi? Option A: confirmed-only projection; Option B: admin approval’dan keyin qo‘shish. **`PENDING APPROVAL`.**
9. Locomotive current mileage uchun alohida read service’ni maintenance/work-order’da ishlatish biznes tomonidan tasdiqlanganmi?

### Repo/DB egasi tasdig‘i

10. Live DB Alembic revision’i va 0027 table’lari borligi (bu auditda tekshirilmagan).
11. 0027 downgrade/data retention, overlap constraint extension va migration rehearsal.
12. `postgres/schema.sql`ga tegmaslik talabi bilan `test_schema_drift` parity’sini qanday hal qilish.
13. Opening submit/approve/read API role’lari va master section scope.

## 16. Implementatsiyani boshlash shartlari

- P0.1 `CONFIRMED` qoidalari acceptance test’lariga aylantirilishi.
- §15’dagi sonli policy, review, same-actor approval va estimated projection savollari tasdiqlanishi yoki rasman `HELD/UNKNOWN` qolishi.
- 0027 deployed holati va schema parity’ni disposable muhitda aniqlash rejasi bo‘lishi.
- Wagon-only `fixed_assets.mileage` uchun locomotive maintenance/work-order read source belgilanashi.
- Eski GTK/Wialon writer cutover va rollback/feature-disable rejasi; parallel writer’ga yo‘l yo‘q.
- DB transaction/idempotency/overlap va raw audit acceptance owner’lari belgilanishi.
- Shundan keyin alohida implementation task va explicit migration approval ochilishi. **P0.2’ning o‘zi implementation boshlamaydi.**
