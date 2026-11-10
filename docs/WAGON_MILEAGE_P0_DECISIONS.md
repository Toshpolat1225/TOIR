# TOIR Wagon Mileage Engine — P0.1 qarorlar

Sana: 2026-11-10  
Holat: **foydalanuvchi tasdiqlagan biznes qoidalari kiritildi; qolgan parametrlar ochiq**  
Doira: qarorlarni qayd etish. Bu hujjat implementatsiya yoki migration ruxsati emas.

## Qaror maqomlari

- `CONFIRMED` — foydalanuvchi tasdiqlagan biznes qoidasi yoki mavjud kodda tekshirilgan fakt. Kodda borligi production’da ishlayotganini anglatmaydi.
- `PROPOSED` — texnik taklif; foydalanuvchi tasdig‘isiz yakuniy qoida emas.
- `UNKNOWN` / `PENDING APPROVAL` — qo‘shimcha ma’lumot yoki tasdiq kerak.

Bu hujjat odometr tezligi, agreement tolerance, maksimal vaqt yoki idle davomiyligi kabi biznes qiymatlarini belgilamaydi. Kodda mavjud konstantalar tasdiqlangan policy hisoblanmaydi.

## 1. Hozirgi kodning tekshirilgan holati

1. `backend/app/services/wagon_mileage_engine.py` ichida `select_main_locomotive` va `allocate_distance_to_wagons` pure funksiyalari bor. Bu yangi engine hozir GTK/Wialon service’lariga ulanmagan.
2. `backend/app/services/gtk.py::sync_gtk` raw snapshot’ni saqlagach eski `_attribute_snapshot_mileage`ni chaqiradi. U `backend/app/services/mileage_attribution.py::compute_attribution` orqali locomotive checkpoint’dan delta hisoblab, `GtkWagonMileageLog`, wagon `fixed_assets.mileage` va `mileage_history`ni yangilaydi. Eski flow locomotive checkpoint’i uchun ham `fixed_assets.mileage`dan foydalanadi; bu yangi “lokomotiv probegi alohida” qaroriga mos emas.
3. Eski attribution joriy GTK snapshot’dagi `is_main=True` locomotive’ga tayanadi. Asosiy locomotive yo‘q yoki bir nechta bo‘lsa hisoblamaydi; yangi vagonga oldingi delta berilmaydi; ikki snapshot’da turli train’larda ko‘ringan vagon attribution’dan chiqariladi.
4. GTK service raw payload’ni `gtk_raw_snapshots`ga yozadi. Payload’da `fetched_at` bor; hash butun payload’dan tuziladi va `effective_at`ga sync paytidagi `run_at` yoziladi. Demak `effective_at` source’dagi tasdiqlangan hodisa vaqti emas. Raw snapshot, mirror/membership va sync run birinchi transaction’da saqlanadi; eski attribution keyingi session/transaction’da ishlaydi.
5. Wialon pull (`backend/app/services/wialon.py::_gated_mileage`) mapped asset, odometer va message timestamp mavjud bo‘lsa normalized raw reading’ni `wialon_odometer_readings`ga yozadi. `ACCEPTED`, `BASELINE`, `UNCHANGED` holatlari `accepted=True` bo‘lishi mumkin; unmapped asset yoki timestamp/mileage yo‘q bo‘lsa raw reading saqlanmaydi.
6. Wialon pull delta’si va push handler (`backend/app/routers/wialon.py::_handle_input`) kiritgan mileage `assets.receive_wialon_update` orqali `fixed_assets.mileage`ga yuboriladi. Push `wialon_quality.evaluate`/raw-reading table’ni chaqirmaydi va source measurement timestamp’ini o‘qimaydi. Hozirgi service asset turidan qat’i nazar mileage yozishi mumkin; bu yangi wagon-only projection qaroriga zid.
7. `backend/app/models/mileage.py` raw snapshot/reading, opening balance, calculation run, ledger va idle period modellarini ta’riflaydi. Bu modellarga yozuvchi application service yoki route topilmadi.
8. Eski attribution `is_main` va checkpoint delta’dan foydalanadi; yangi selector GTK/Wialon candidate’larini tekshiradigan orchestration’ga ulanmagan.
9. `backend/tests/test_wagon_mileage_engine.py` pure selection/allocation’ni tekshiradi. GTK/Wialon integration, raw replay, ledger transaction, opening approval yoki idle detection coverage’i yo‘q.
10. `FixedAsset` modeli `backend/app/models/assets.py`da (`fixed_asset.py` yo‘q). `mileage` — `numeric(12,2) NOT NULL DEFAULT 0`; `MileageHistory` source/value/time saqlaydi, ammo source reading yoki calculation run FK’si yo‘q. `0027_wagon_mileage_engine` `0026_audit_logs`dan keyin turadi; bu bosqichda migration yoki DB ishlatilmadi. Oldingi test run `test_schema_drift` orqali yangi model jadvallari va `postgres/schema.sql` orasida tafovut topgan.

## 2. Muammolar va oqibatlar

| Muammo | Kod dalili | Oqibat |
|---|---|---|
| Yangi engine ulanmagan | `services/gtk.py::sync_gtk` -> `_attribute_snapshot_mileage`; yangi selector/allocation call-site yo‘q | Hozirgi hisob yangi qoidalarga o‘tmagan. |
| Push/Pull qoidalari farqli | `routers/wialon.py::_handle_input` -> `assets.receive_wialon_update`; pull -> `services/wialon.py::_gated_mileage` | Push va pull turli mileage semantikasini ishlatishi mumkin; push raw/gate yo‘lidan o‘tmaydi. |
| Lokomotiv probegi noto‘g‘ri projection’ga tushadi | Pull va push `receive_wialon_update`ni chaqiradi; u `fixed_assets.mileage`ni yangilaydi | Tasdiqlangan yangi qoidaga ko‘ra bu ustun wagon projection; locomotive counter/ledger alohida bo‘lishi kerak. |
| Ayni timestamp conflict aniqlanmaydi | `wialon_quality.evaluate` ayni/oldingi timestamp’ni `UNCHANGED` qilishi mumkin; pull raw row `accepted=True` bo‘lishi mumkin | Turli probeg qiymatlari raw’da saqlanishi va segment `HELD` bo‘lishi kerak; hozirgi kodda bu conflict policy yo‘q. |
| GTK dedup va run audit’i aralash | `GtkRawSnapshot.payload_hash` unique; hash payload ichidagi `fetched_at`ni ham qamraydi | Raw receipt auditi va hisob idempotency’si bitta mexanizmga bog‘lanmasligi kerak. |
| Ledger publisher yo‘q | Model constraint bor, ledger insert/publish service topilmadi | Cache, history, retry va recalculation yaxlitligi kafolatlanmagan. |
| Idle detector yo‘q | GTK’da `state_duration_s`, Wialon’da joriy `speed` bor; tarixiy idle detector yo‘q | Joriy holatning o‘zi idle intervalni tasdiqlamaydi. |
| DB parity ochiq | Oldingi `test_schema_drift` run yangi model jadvallari va `postgres/schema.sql` orasida tafovut topgan | Schema policy hal bo‘lmasdan migration tayyor deb bo‘lmaydi. |

## 3. Biznes qoidalari va texnik qarorlar

### A. Fizik probeg

- `CONFIRMED` — Tizim GTK va Wialon ma’lumotlarini tekshirib, bir fizik vaqt segmenti uchun bitta ishonchli locomotive odometer manbasini avtomatik tanlaydi. Ishonchli tanlov bo‘lmasa, lokomotiv taxmin qilinmaydi va hisob `HELD` bo‘ladi.
- `CONFIRMED` — Odometrlar qo‘shilmaydi yoki o‘rtachalanmaydi. Fizik masofa va har bir vagonga ajratilgan wagon-km alohida ko‘rsatkichlar; wagon-km yig‘indisi fizik masofaga teng bo‘lishi shart emas.
- `CONFIRMED` — Misol: 100 km fizik yo‘nalishda ikki vagon to‘liq qatnashsa, har biriga 100 wagon-km ajratilishi mumkin. Fizik yo‘nalish 100 km, wagon-km yig‘indisi 200 km; bu 200 km fizik yo‘l bosildi degani emas.
- `UNKNOWN` — GTK va Wialon signallarini solishtirganda selection’ning aniq ustuvorlik va ishonch mezoni tasdiqlanmagan.

### B. Lokomotiv almashishi

- `CONFIRMED` — Handoff vaqti faqat GTK’da qayd etilgan aniq vaqtdan olinadi. GTK vaqti bo‘lmasa vaqt taxmin qilinmaydi va tegishli hisob `HELD` bo‘ladi.
- `CONFIRMED` — Eski va yangi locomotive’larning cumulative counter’lari o‘zaro ayirilmaydi. Yangi locomotive’ning birinchi ishonchli o‘lchovi faqat o‘zining baseline’i.
- `PROPOSED` — Handoff overlap’ida bir fizik vaqt uchun bitta source tanlash; bir xil vaqtni ikki marta publish qilmaslik.
- `UNKNOWN` — Eski/yangi interval overlap yoki gap berganda umumiy qismini solishtirish policy’si tasdiqlanmagan; ishonchli bog‘lanmaydigan qism `HELD`.

### C. Interpolation va vaqt chegaralari

- `CONFIRMED` — Wialon uzilishida faqat aynan bir locomotive’ga tegishli oldingi va keyingi tasdiqlangan o‘lchovlar bracket bo‘lsa interpolation qilinadi. Bracket bo‘lmasa `HELD`; boshqa locomotive counter’i bilan gap to‘ldirilmaydi.
- `CONFIRMED` — Interpolation natijasi `ESTIMATED`; tasdiqlangan masofa sifatida ko‘rsatilmaydi.
- `PROPOSED` — Bracket’langan bitta source interval’ida vaqt ulushi bo‘yicha taqsimla; natija `ESTIMATED` bo‘lsin. To‘g‘ridan-to‘g‘ri o‘lchov ham manba va vaqt tekshiruvlaridan o‘tishi kerak.
- `UNKNOWN` — Wialon bracket uchun maksimal vaqt oralig‘i, interpolation formulasi va GTK/Wialon timestamp field’larining effective ma’nosi tasdiqlanmagan. Bu bosqichda sonli limit belgilanmaydi.

### D. Vagon tarkibga kirishi va chiqishi

- `CONFIRMED` — Bitta vagon bir timestamp’da ikki xil tarkibga bir vaqtda tegishli bo‘lishi mumkin emas.
- `CONFIRMED` — Vagon bir tarkibdan boshqasiga o‘tganda oxirgi eski va birinchi yangi GTK snapshot vaqtlari orasida taqsimotga ruxsat bor; natija `ESTIMATED`. Snapshot vaqti aniq almashish vaqti deb ko‘rsatilmaydi.
- `CONFIRMED` — Bir xil membership/snapshot replay mileage’ni ikkinchi marta oshirmaydi. Takror input raw audit uchun saqlanishi mumkin; calculation idempotency raw receipt dedup’dan alohida.
- `PROPOSED` — Membership interval’lari `[from,to)` bo‘lsin va overlap DB constraint yoki DB-level serialization bilan bloklansin.
- `UNKNOWN` — Snapshot’lar orasidagi taqsimotning yakuniy matematik formulasi tasdiqlanmagan.

### E. Opening balance

- `CONFIRMED` — Har bir vagonning boshlang‘ich probegi qo‘lda kiritiladi va faqat administrator tasdiqlagandan keyin hisobda ishlatiladi.
- `CONFIRMED` — Kiritish va tasdiqlash alohida amallar; actor, vaqt, qiymat va tarix audit qilinadi. Tasdiqlanmagan balans hisobga kirmaydi.
- `PROPOSED` — Tasdiqlangan balans o‘zgarmas tarix bo‘lib qolsin; tuzatishda eski qatorni o‘chirish emas, yangi version va `superseded` munosabati ishlatilsin.
- `UNKNOWN` — Kirituvchi va tasdiqlovchi administrator bir shaxs bo‘lishi mumkinmi, effective date’ni orqaga qo‘yish va talab qilinadigan dalil aniqlanmagan.

### F. Ledger va yakuniy probeg

- `CONFIRMED` — Har bir hisob natijasining manbasi va calculation version’i saqlanadi; takror sync/replay mileage’ni ikki marta oshirmaydi.
- `CONFIRMED` — `fixed_assets.mileage` faqat wagon probegi projection’i. Wagon Mileage Engine bu qiymatni faqat vagonlar uchun publish qiladi; locomotive probegi alohida counter/ledger’da yuritiladi va bu maydonga yozilmaydi.
- `PROPOSED` — Ledger canonical calculation record bo‘lsin: run, policy version, source reading/snapshot, membership interval, locomotive, vaqt, km, status va idempotency key’ga bog‘lansin. Recalculation eski active qatorlarni `superseded` qilib, yangi ledger/cache/history’ni bitta transaction’da publish qilsin.
- `UNKNOWN` — `ESTIMATED` ledger natijasi administrator ko‘rib chiqqandan keyin projection’ga qo‘shiladimi yoki alohida estimate bo‘lib qoladimi — tasdiqlanmagan. Tasdiqkacha uni confirmed mileage deb ko‘rsatma.
- `UNKNOWN` — Eski mileage/history’ni opening balance’ga aylantirish va maintenance reconciliation’ning boshlang‘ich contract’i hal qilinmagan.

### G. Wialon Push/Pull

- `CONFIRMED` — Push va Pull bir xil validation, raw persistence, deduplication va mileage publish mexanizmidan foydalanadi.
- `CONFIRMED` — Idempotency receive timestamp’ga emas, measurement identity’ga asoslanadi; aynan bir xil o‘lchov takrori ikki marta hisoblanmaydi.
- `CONFIRMED` — Bir unit va bir o‘lchov vaqtida turli probeg kelsa, ikkala raw qiymat saqlanadi, conflict qayd etiladi va segment `HELD` bo‘ladi. Qiymatlardan biri jim tanlanmaydi yoki o‘chirilmaydi.
- `PROPOSED` — Ikkala transport’ni umumiy canonical DTO va ingestion transaction orqali o‘tkaz; push timestamp/ID bermasa measurement time’ni `received_at` bilan avtomatik almashtirma.
- `UNKNOWN` — Push payload event ID’i, timestamp timezone/unit’i va push/pull bitta qurilmada parallel ishlashi mumkinligi Wialon owner tomonidan tasdiqlanishi kerak.

### H. Bekor turish (idle)

- `CONFIRMED` — Idle GTK va Wialon ma’lumotlari birgalikda tekshirilib aniqlanadi; idle probegga qo‘shilmaydi va fizik masofa emas.
- `CONFIRMED` — Manbalar zid yoki dalil yetarli bo‘lmasa idle avtomatik tasdiqlanmaydi; `HELD`/review bo‘ladi. `ESTIMATED` idle tasdiqlangan idle deb ko‘rsatilmaydi.
- `UNKNOWN` — Minimal idle davomiyligi va idle’ni tasdiqlash uchun authoritative signal/evidence belgilanmagan.

## 4. Hali tasdiqlanmagan parametrlar

| Savol | Kerakli javob beruvchi | Ta’siri |
|---|---|---|
| GTK/Wialon selection’ning aniq ustuvorlik mezoni qanday? | Biznes egasi + GTK/Wialon data owner | Avtomatik tanlov yoki `HELD`. |
| GTK handoff uchun qaysi field aniq effective time hisoblanadi? | GTK data owner | Effective timestamp topilmasa handoff `HELD`. |
| Wialon bracket maximum interval va speed/agreement policy qancha? | Biznes/faoliyat egasi + telemetry owner | Policy config; raqam tasdiqlanmagan. |
| Idle minimal davomiyligi va manbalar ustuvorligi qanday? | Faoliyat egasi + telemetry owner | Idle status tasdig‘i; raqam tasdiqlanmagan. |
| Bir xil unit va vaqtda turli probeg kelgandagi conflict’ni kim va qanday ko‘rib chiqadi? | Wialon owner + biznes egasi | Manual review roli, navbat va qayta hisoblash tartibi. |
| Snapshotlar orasidagi vagon taqsimotining matematik formulasi qanday? | Biznes egasi + GTK data owner | Faqat `ESTIMATED`; formula tasdiqlanmagan. |
| Opening balance’ni kirituvchi va tasdiqlovchi bir odam bo‘lishi mumkinmi? | TOIR business/security owner | Maker-checker permission. |
| `ESTIMATED` qachon projection’ga qo‘shilishi mumkin? | Biznes egasi | `fixed_assets.mileage`ning tasdiqlangan ma’nosi. |
| Alembic-only schema policy va `test_schema_drift` parity’si qanday hal qilinadi? | Repo/DB owner | `0027`dan keyingi migration strategy. |

## 5. Algorithm pseudocode

Quyidagi orchestration **`PROPOSED`**; tasdiqlanmagan policy qiymatlari berilmagan.

```text
on_gtk_snapshot(raw_payload):
    persist each raw receipt and its fingerprint
    observed_at = TOIR receipt time; never treat it as source effective time
    if snapshot is incomplete/suspicious:
        mark run HELD; retain raw; do not publish confirmed mileage
        return
    validate wagon membership intervals do not overlap across trains
    if membership conflict:
        mark affected scope HELD; return

on_wialon_reading(raw_event, origin):
    normalize push/pull into one measurement contract
    deduplicate by measurement identity, not received_at
    if same unit + same measurement time has different odometer values:
        retain both raw readings; mark conflict and affected scope HELD; return
    validate source mapping, timestamp, monotonicity and approved policy
    if invalid:
        retain raw and rejection reason; do not advance accepted counter state
        return

for each physical time segment:
    inspect GTK and Wialon candidates; select one trusted locomotive source
    if no trustworthy selection: mark HELD; do not estimate a locomotive
    on locomotive handoff:
        use only exact GTK-recorded handoff time
        if absent: mark affected segment HELD
        never subtract cumulative counters of different locomotives
    on Wialon gap:
        interpolate only between confirmed readings from the same locomotive
        if bracket missing or exceeds approved max interval: mark HELD
        otherwise mark result ESTIMATED, not CONFIRMED
    on wagon transfer:
        allocate within last-old/first-new GTK snapshot observed-time window
        mark result ESTIMATED; do not label either snapshot as exact transfer time
    keep physical route km separate from per-wagon km allocations

evaluate idle from GTK + Wialon:
    if evidence conflicts or is insufficient: mark idle HELD
    never add idle duration to distance

publish transaction:
    lock calculation scope and affected wagon rows
    enforce idempotency and no overlapping wagon membership
    write run and ledger; supersede replaced active rows
    update fixed_assets.mileage for wagons only, plus mileage_history
    keep locomotive odometer/probeg in its separate store
    do not present ESTIMATED or HELD as confirmed; estimated projection inclusion
        remains UNKNOWN until approved
    reconcile maintenance and commit atomically
on failure:
    rollback ledger/cache/history/maintenance changes
    retain raw evidence and prior active projection; record failed run separately
```

## 6. Database va transaction talablari

Quyidagi DB constraint va transaction tavsiyalari `PROPOSED`; migration va implementatsiyadan oldin schema/DB egasi tasdig‘i kerak.

- **Raw GTK/Wialon:** har receipt/run source timestamp, `observed_at`, payload fingerprint va payload bilan audit qilinadi. Fingerprint replay dedup’i raw receipt tarixini o‘chirib yubormasin.
- **Wialon raw:** hozirgi `asset_id NOT NULL` unmapped source event’ni saqlashga yo‘l bermaydi; “barcha raw event” talabi uchun source ID va mapping tarixini migration’dan oldin hal qil.
- **Wialon conflict:** bir unit/time uchun farqli qiymatlar ikkita raw row sifatida saqlansin; conflict publish’ni to‘xtatsin.
- **Opening balance:** nonnegative constraint; submitter/approver/time/status/history; har vagonda bitta active approved balance. Submission va approval alohida action bo‘lsin.
- **Membership:** `[from,to)` semantics, `period_to >= period_from`, bir vagonda overlap’ni DB darajasida to‘sish va replay uchun deterministic identity. `btree_gist`/exclusion constraint’ga ruxsat bo‘lmasa DB-level lock strategy tanlansin.
- **Ledger:** run/asset/raw-source FK, `km >= 0`, period/status checks, unique idempotency key va active/superseded lifecycle. `CONFIRMED/ESTIMATED/HELD` mapping’ini kelajakdagi migration hal qiladi.
- **Idle:** bir vagonda takroriy period, evidence/source, status va idempotency tekshirilsin; idle mileage’ga qo‘shilmasin.
- **Projection:** `fixed_assets.mileage` faqat wagonlar uchun qayta hisoblanadi. Locomotive odometer/probeg alohida saqlanadi.
- **Transaction:** raw ingest xatosiz saqlanadi; publish’da ledger, wagon cache, `mileage_history` va maintenance bir atomic transaction’da. Failure’da bular rollback bo‘ladi, raw va oldingi projection qoladi. Multi-replica uchun process-local `asyncio.Lock` yetarli emas.
- **Migration:** faqat Alembic forward migration. `0027` downgrade raw/ledger ma’lumotlarini o‘chiradi; bu bosqichda migration yoki DB ishlatilmaydi. `postgres/schema.sql` o‘zgartirilmaydi.

## 7. Test ssenariylari va qabul mezonlari

### Unit

- GTK + Wialon candidate selection; ishonchsiz tanlov `HELD`.
- Bitta locomotive bracket’i, bracket yo‘q/eskirgan, policy max interval’dan oshish, odometer reset va bir vaqtdagi conflict.
- GTK exact handoff bor/yo‘q; yangi locomotive baseline; turli cumulative odo’larni ayirmaslik.
- Snapshot transfer window allocation `ESTIMATED`; snapshot vaqtlarini exact handoff demaslik.
- Cross-train overlap’ni rad etish, duplicate snapshot replay’i va idempotency.
- Opening pending/approved, alohida audit, bitta active balance va same-actor approval policy’si.
- Idle GTK/Wialon agreement, conflict/insufficient evidence `HELD`, duration threshold tasdiqlangandan keyin.
- `CONFIRMED`/`ESTIMATED`/`HELD`dan qaysi biri wagon projection’ga kirishi; hozircha `ESTIMATED` inclusion `UNKNOWN`.

### Integration — disposable PostgreSQL

- GTK raw snapshot/membership/run va hisob transaction’lari; incomplete/suspicious snapshot mileage publish qilmasin.
- Push/Pull bir xil canonical ingestion, validation, raw/idempotency va conflict rule’dan o‘tsin.
- Bir unit/time’da turli probeg: ikkala raw saqlansin, segment `HELD`, projection o‘zgarmasin.
- GTK exact handoff va snapshot-only wagon transfer; `observed_at`/`effective_from/to` chegaralari tekshirilsin.
- Ikki worker replay/concurrency; bitta active ledger/projection natijasi.
- Failure rollback: ledger/cache/history/maintenance birga rollback, raw va oldingi projection saqlansin.
- Role/approval audit, FK/check/unique/exclusion constraint va Alembic migration chain.

**Acceptance:** har fizik segment uchun bitta trusted source; odometrlar qo‘shilmaydi; `HELD` publish qilinmaydi; `ESTIMATED` confirmed deb ko‘rsatilmaydi; `fixed_assets.mileage` wagon-only projection; locomotive mileage alohida; Push/Pull replay ikki marta hisoblamaydi; legacy maintenance/history regression tekshirilgan.

## 8. P0/P1 implementatsiya ketma-ketligi

Ketma-ketlik `PROPOSED`; P0.1 hujjati implementatsiyani boshlashga ruxsat bermaydi.

### P0

1. UNKNOWN policy va open questions’ni biznes/GTK/Wialon/DB owner’lari bilan tasdiqlash; sonli qiymatlarni o‘zboshimchalik bilan belgilamaslik.
2. `0027` model/constraint’lari, `test_schema_drift` va Alembic-only migration policy’sini muvofiqlashtirish; schema yoki DB’ni bu bosqichda o‘zgartirmaslik.
3. Yangi engine’ni GTK orchestration’ga ulash; eski `_attribute_snapshot_mileage` writer’ini cutover qilish, parallel publish’ni taqiqlash.
4. Lokomotiv counter’ini alohida yuritish; GTK-only exact handoff va Wialon same-locomotive bracket/max interval policy’sini qo‘llash.
5. Membership overlap/idempotency va snapshot transfer’ning `ESTIMATED` natijasini ledger’ga yozish.
6. Wialon Push/Pull’ni yagona ingestion service/transaction’ga o‘tkazish; conflict raw history’sini saqlash va `HELD` qilish.
7. Opening balance admin approval, ledger recalculation, wagon-only `fixed_assets.mileage` projection va history/maintenance publish’ni atomic qilish.

**P0 qabul:** confirmed decisions service flow’da bajariladi; UNKNOWN parametrlar approval bilan version’langan policy’ga aylanadi; conflict/HELD projection’ga kirmaydi; retry/concurrency bir marta hisoblaydi; raw audit saqlanadi; integration/regression tests o‘tadi.

### P1

1. Opening submit/approve, ledger/run/conflict ko‘rish API’lari va server-side permission/scope.
2. Frontend’da confirmed va estimated/held natijalarni aralashtirmasdan ko‘rsatish; administrator opening tasdig‘ini audit bilan berish.
3. Monitoring, retention/backup, support/recovery runbook; disposable muhitda migration/rollback rehearsal.

**P1 qabul:** API role’lari va audit tekshiriladi; UI status/source’ni aniq ko‘rsatadi; typecheck/build/API E2E va DB integration tekshiruvlari bajariladi.

## 9. P0.1 yakuniy holat

- `CONFIRMED`: GTK va Wialon’ni tekshirib locomotive’ni avtomatik tanlash (ishonch bo‘lmasa `HELD`); handoff uchun faqat GTK qayd etgan aniq vaqt; Wialon gap interpolation’i faqat bir locomotive bracket’ida; wagon snapshot transfer faqat `ESTIMATED`; administrator tasdiqlaydigan va audit’li opening balance; GTK+Wialon idle, conflict/insufficient evidence bo‘lsa avtomatik tasdiq yo‘q.
- `CONFIRMED`: bir fizik segment uchun bir odometer source; odometrlarni qo‘shmaslik/o‘rtachalaslik; `fixed_assets.mileage` faqat wagon projection, locomotive probegi alohida; Push/Pull umumiy validation/raw/idempotency/publish; bir vaqtdagi turli qiymatlar saqlanib conflict sifatida `HELD` qilinadi.
- `UNKNOWN` / `PENDING APPROVAL`: selection priority; Wialon max bracket time; idle minimum duration; snapshot allocation formulasi; GTK/Wialon conflict manual-review tartibi; submitter=approver mumkinligi; `ESTIMATED` projection inclusion; schema parity va constraint implementation policy.
- Ushbu qarorlar hujjatga kiritildi, implementatsiyaga ruxsat bermaydi. P0.1’da kod, test, migration, DB, Docker va `postgres/schema.sql` o‘zgartirilmadi yoki ishga tushirilmadi.
