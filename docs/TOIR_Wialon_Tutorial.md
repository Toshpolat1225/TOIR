# TOIR ↔ Wialon: boshidan oxirigacha to'liq qo'llanma

> Bu qo'llanma "choynak uchun" yozilgan: hech narsani bilmasangiz ham, qadamma-qadam bajarsangiz ish tugaydi.
> Har qadamda: **nima uchun**, **qayerda**, **buyruq**, **kutiladigan natija**, **boshqacha chiqsa nima qilish**.
> Oxirida "ish tugadi" mezonlari bor.

---

## 0. Eng qisqa mazmun

**Maqsad:** Wialon (gps.agmk.uz) dagi texnika ma'lumotlarini (yurgan km, moto-soat) TOIR'ga **xavfsiz** olib kelish.

**Asosiy muammo (topildi):** HILUX 4x2 584 SAA (Wialon ID 366) hisoblagichida `1 007 343 489 km` yozilgan.
Sabab: 2024-06-07 soat 06:00:04 UTC da qurilmadan **buzilgan paket** kelgan (`param199 = 992 137 445 377`),
Wialon uni "yurgan masofa" deb qo'shib yuborgan: **+1 007 019 507 km**.
Hisoblagichning o'sishi esa **to'g'ri** (kunlik 52,9 km = report'dagi 52,9 km).

**Yechim:** TOIR Wialon'dagi *absolyut* qiymatni emas, uning **o'sishini (delta)** oladi.
Buzilgan sakrashlar avtomatik **rad etiladi** va jadvalga yoziladi.

**Siz nima qilasiz:** (1) kodni joylaysiz, (2) bazaga 2 ta yangi jadval qo'shasiz, (3) bootstrap skriptini ishga tushirasiz,
(4) shubhali km'larni qo'lda to'g'rilaysiz, (5) sinxronlashni yoqasiz.

---

## 1. Hozirgi holat (nima tayyor, nima qoldi)

### ✅ Tayyor va tekshirilgan

- [x] Wialon'ga ulanish, token ishlaydi, 177 ta birlik o'qiladi.
- [x] `wialon_tool.py` — terminal skripti (natija ekranga **va** matn faylga).
- [x] HILUX muammosi sababi topildi (yuqorida).
- [x] Ikki manba (terminal API va Telegram oqimi) bir-birini tasdiqladi.
- [x] TOIR uchun kod yozildi: sifat darvozasi, holat jadvallari, bootstrap, rebaseline.
- [x] 18 ta avtomatik test (sandbox'da) o'tdi.

### ☐ Qoldi (bu qo'llanma shularni qamrab oladi)

- [ ] Kodni TOIR'ga joylash va prod bazaga migratsiya.
- [ ] Bootstrap: Wialon birliklarini TOIR aktivlari bilan moslash.
- [ ] Shubhali km'larni priborga qarab to'g'rilash.
- [ ] Birinchi sinxronlash va tekshirish.
- [ ] Wialon administratoriga topshiriladigan ishlar.

### ⚠️ Halol ogohlantirish: nima sinalMAGAN

- Haqiqiy **PostgreSQL** bilan sinalmagan (faqat soxta modullar bilan).
- Sizning `services/assets.py` faylingizni ko'rmadim. Men `receive_wialon_update(..., mileage=None)` mileage'ni
  **o'zgartirmaydi** deb faraz qildim. Buni 9-bosqichda tekshirasiz.
- Prod server va bazaga mening muhitimdan ulanib bo'lmaydi: hamma buyruqni **siz** bajarasiz.

---

## 2. Lug'at (qisqa)

| So'z | Ma'nosi |
|---|---|
| **Wialon** | GPS kuzatuv tizimi (gps.agmk.uz) |
| **Token** | Wialon'ga kirish paroli. **Hech kimga yubormang**, chatga yozmang |
| **cnm** | Wialon'dagi "yurgan masofa" hisoblagichi (km) |
| **cneh** | Wialon'dagi "dvigatel soati" hisoblagichi (soat) |
| **Baseline** | Birinchi o'qilgan qiymat. Faqat solishtirish nuqtasi, TOIR'ga yozilmaydi |
| **Delta** | Oxirgi o'qishdan beri o'sish. TOIR'ga **faqat shu** qo'shiladi |
| **Gate (darvoza)** | Shubhali qiymatni to'xtatadigan qoida |
| **Rad etildi** | Gate to'xtatgan o'qish; `wialon_rejected_readings` jadvaliga yoziladi |
| **Mapping** | Wialon birligi ↔ TOIR aktivi juftligi (aniq `wialon_id` bo'yicha) |
| **Dry-run** | "Quruq yurish": hisobot beradi, bazaga **yozmaydi** |
| **Rebaseline** | Yangi baseline o'rnatish (Wialon tuzatilgandan keyin) |

---

## 3. Gate qoidalari (nima rad etiladi)

| Holat | Qaror |
|---|---|
| Birinchi o'qish | Baseline sifatida saqlanadi, TOIR mileage'i o'zgarmaydi |
| `cnm` ≤ 1 km kamaydi | Xato emas (API kasr qismini qirqadi), e'tiborga olinmaydi |
| `cnm` > 1 km kamaydi | **Rad etiladi** |
| `cnm` o'sishi > `150 km/soat × vaqt + 10 km` | **Rad etiladi** (sakrash) |
| `cneh` o'sishi > `vaqt + 1 soat` | **Rad etiladi** |
| `cneh = 0` | "Ma'lumot yo'q" (**NULL**, nol emas) |
| Oxirgi xabar 24 soatdan eski | E'tiborga olinmaydi |
| `wialon_id` bo'yicha aktiv topilmasa | Mileage yozilmaydi (tezlik va online avvalgidek) |

---

## 4. Tayyorgarlik (10 daqiqa)

### 4.1. Nima kerak

- [ ] Windows kompyuter: PowerShell, Python (`c:\python315\python.exe`).
- [ ] TOIR repo: `C:\Users\okmkh\OneDrive\Documents\GitHub\TOIR`.
- [ ] Prod serverga kirish (SSH yoki masofaviy ish stoli) va **baza paroli/ulanish manzili** (`DB_URL`).
- [ ] `psql` va `pg_dump` dasturlari (serverda yoki kompyuteringizda).
- [ ] Backend'ni qayta ishga tushirish huquqi.
- [ ] Wialon administratori bilan aloqa (11-bosqich uchun).

### 4.2. Qulay vaqt tanlang

- Ish vaqtidan tashqarida yoki smena almashishidan oldin **emas**.
- 3–10-bosqichlar uchun **1,5–2 soat** ajrating va biror kishi yoningizda tursin.
- Dushanba ertalab yoki juma kechqurun boshlamang: muammo chiqsa, yordam topish qiyin.

### 4.3. Maxfiylik qoidalari (har doim)

- Token, `.env.local`, `eid`/`sid`, bazaning paroli **chatga yuborilmaydi**.
- Repo **public**: `wialon_natija_*.txt` va `wialon_bootstrap_*.csv` fayllarini Git'ga qo'shmang:

```powershell
Set-Location "C:\Users\okmkh\OneDrive\Documents\GitHub\TOIR"
Add-Content .gitignore "wialon_natija_*.txt"
Add-Content .gitignore "backend/scripts/wialon_bootstrap_*.csv"
```

---

## 5. BOSQICH 1 — Wialon tomonini yana bir marta tekshirish (ixtiyoriy, 5 daqiqa)

**Nima uchun:** bugungi holatni fayl sifatida saqlab qo'yish ("oldin" surati).
**Qayerda:** o'z kompyuteringizda, PowerShell.

```powershell
Set-Location "C:\Users\okmkh\OneDrive\Documents\GitHub\TOIR"
$py = "c:\python315\python.exe"
& $py .\wialon_tool.py full
```

**Kutiladi:** ekranga uzun matn chiqadi, oxirida `Natija fayli: ...wialon_natija_full_....txt`.
Oxiridagi `6/6 XULOSA` bo'limida `[DIQQAT]` HILUX uchun chiqishi normal.

**Boshqacha chiqsa:**

| Xato | Nima qilish |
|---|---|
| `Выражение, расположенное после "&"...` | `$py` bo'sh. Yuqoridagi `$py = ...` qatorini qayta yozing |
| `CONFIG XATOSI` | `.env.local` da `WIALON_HOST` va `WIALON_TOKEN` borligini tekshiring |
| `xato 7` | Token huquqi yetmaydi: Wialon administratoriga ayting |
| `xato 1` / `1011` | Sessiya eskirgan: buyruqni qayta ishga tushiring |

---

## 6. BOSQICH 2 — Kodni olish va kompyuteringizda tekshirish (15 daqiqa)

**Nima uchun:** kod bor, lekin hali TOIR repo'siga qo'yilmagan.

### 6.1. Git'da alohida shoxcha oching (xavfsizlik uchun)

```powershell
Set-Location "C:\Users\okmkh\OneDrive\Documents\GitHub\TOIR"
git status                      # "nothing to commit" bo'lsa yaxshi
git checkout -b wialon-delta
```

Agar `git status` o'zgarishlar ko'rsatsa: avval ularni commit qiling yoki menga ayting.

### 6.2. Arxivni oching va fayllarni nusxalang

`toir_wialon_patch.zip` ni yuklab oling (Downloads papkasiga), so'ng:

```powershell
$repo = "C:\Users\okmkh\OneDrive\Documents\GitHub\TOIR"
Expand-Archive "$HOME\Downloads\toir_wialon_patch.zip" -DestinationPath "$HOME\Downloads\toir_patch" -Force
$src = "$HOME\Downloads\toir_patch\toir_wialon_patch\backend"
Copy-Item "$src\app"     "$repo\backend\" -Recurse -Force
Copy-Item "$src\scripts" "$repo\backend\" -Recurse -Force
Copy-Item "$src\prod"    "$repo\backend\" -Recurse -Force
Copy-Item "$src\tests"   "$repo\backend\" -Recurse -Force
git status
```

**Kutiladi:** `git status` da shular ko'rinadi:

- **O'zgargan (modified):** `backend/app/services/wialon.py`, `backend/app/integrations/wialon_client.py`
- **Yangi (untracked):** `wialon_quality.py`, `wialon_bootstrap_plan.py`, `wialon_counters.py` (model va repository), `scripts/`, `prod/`, `tests/test_wialon_*.py`

Agar boshqa fayllar ham "modified" bo'lsa, to'xtang va menga ro'yxatni yuboring.

### 6.3. Testlarni ishga tushiring (tavsiya, 2 daqiqa)

```powershell
Set-Location "$repo\backend"
& $py -m pytest tests/test_wialon_quality.py tests/test_wialon_client_parse.py tests/test_wialon_bootstrap_plan.py tests/test_wialon_sync_flow.py -q
```

**Kutiladi:** `18 passed`. Boshqa son yoki xato chiqsa, matnni menga yuboring (token yo'q, shunchaki matn).

### 6.4. Alembic ishlatsangiz (faqat shunda)

Agar loyihada Alembic bo'lsa, `backend/app/models/__init__.py` (yoki modellar import qilinadigan joy) ga qo'shing:

```python
from app.models.wialon_counters import WialonCounterState, WialonRejectedReading  # noqa: F401
```

**Nima uchun:** aks holda Alembic keyinroq bu jadvallarni "ortiqcha" deb o'chirishni taklif qilishi mumkin.
Alembic ishlatmasangiz, bu qadam kerak emas.

### 6.5. Commit

```powershell
git add backend .gitignore
git commit -m "Wialon: delta + baseline + sifat darvozasi"
```

---

## 7. BOSQICH 3 — Prod: zaxira nusxa va audit (15 daqiqa)

> ⛔ **Zaxirasiz davom etmang.** Muammo bo'lsa, shu fayldan tiklaysiz.

**Qayerda:** prod serverda (yoki bazaga ulanadigan kompyuterda).
Quyida `<DB_URL>` o'rniga bazaning ulanish manzili yoziladi (misol: `postgresql://user:parol@host:5432/toir`).
Docker ishlatsangiz, buyruqlarni `docker compose exec <db-xizmati> ...` ichida bajaring (loyihangizdagi nomni o'zingiz bilasiz).

### 7.1. Zaxira nusxa

```bash
pg_dump -Fc -f toir_before_wialon_$(date +%Y%m%d_%H%M).dump "<DB_URL>"
ls -lh toir_before_wialon_*.dump        # fayl bor va hajmi 0 emas
```

### 7.2. Audit (faqat o'qiydi)

```bash
psql "<DB_URL>" -f backend/prod/00_audit_readonly.sql > audit_before.txt
cat audit_before.txt
```

**Nimaga qarash kerak:**

| Tekshiruv | Normal | Boshqacha bo'lsa |
|---|---|---|
| `jami_aktiv` / `wialon_id_bor` | `wialon_id_bor` > 0 | 0 bo'lsa, mapping hali yo'q: 8-bosqich (bootstrap) hal qiladi |
| Dublikat `wialon_id` | **bo'sh** | Bo'sh bo'lmasa, **to'xtang**, menga yuboring |
| HILUX 366 qatori | `mileage` ko'rinadi | `mileage` ~10⁹ bo'lsa, 10-bosqichda to'g'rilaymiz |
| `mileage > 1 000 000` ro'yxati | Qisqa | Ro'yxatni **saqlang**: shular shubhali aktivlar |

`audit_before.txt` ni saqlab qo'ying (keyin solishtirish uchun). Uni **menga yuborishingiz mumkin**, unda parol yo'q.

---

## 8. BOSQICH 4 — Prod: migratsiya (5 daqiqa)

**Nima qiladi:** 2 ta **yangi** jadval qo'shadi. Mavjud jadvallarga tegmaydi.

```bash
psql "<DB_URL>" -v ON_ERROR_STOP=1 -f backend/prod/001_wialon_counters.sql
```

**Kutiladi:** `CREATE TABLE`, `CREATE TABLE`, `CREATE INDEX`, `COMMIT`.

**Tekshiring:**

```bash
psql "<DB_URL>" -c "\dt wialon_*"
```

Ko'rinishi kerak: `wialon_counter_state`, `wialon_rejected_readings` (hamda mavjud `wialon_settings`).

**Boshqacha chiqsa:** xato matnini menga yuboring. Migratsiya `BEGIN/COMMIT` ichida, shuning uchun xatoda yarim holatda qolmaydi.

---

## 9. BOSQICH 5 — Prod: kodni joylash va qayta ishga tushirish (15 daqiqa)

### 9.1. Sinxronlash O'CHIQ ekanini tasdiqlang

Serverdagi backend sozlamasida (`.env` yoki `docker-compose.yml`):

```
WIALON_SYNC_ENABLED=false
```

> ⚠️ Bootstrap skripti ishlashi uchun serverda `WIALON_HOST` va `WIALON_TOKEN` ham o'rnatilgan bo'lishi kerak
> (sinxronlash o'chiq bo'lsa ham). Ular allaqachon bor bo'lsa, tegmang.

### 9.2. Kodni serverga olib chiqing

Odatdagi yo'lingiz bilan (misol: serverda `git pull` shu shoxchadan, yoki yangi docker image build).
Muhimi: serverdagi `backend/` ichida yangi fayllar bo'lsin.

### 9.3. Backendni qayta ishga tushiring

Misol (sizning usulingiz boshqacha bo'lishi mumkin): `docker compose restart backend` yoki `systemctl restart toir-backend`.

### 9.4. Ishlayotganini tekshiring

- Sayt ochiladi, kirish ishlaydi.
- `GET /api/v1/wialon/status` javob beradi (`enabled: false`).

**Boshqacha chiqsa** (backend ishga tushmasa): log'ni o'qing. Odatda sabab import xatosi. Log matnini yuboring, tuzataman.
Shoshilinch qaytarish: 14-bo'limga qarang.

---

## 10. BOSQICH 6 — Bootstrap DRY-RUN (10 daqiqa)

**Nima qiladi:** Wialon'dan 177 birlikni oladi, TOIR aktivlari bilan solishtiradi, **hisobot beradi. Bazaga yozmaydi.**

```bash
cd backend
python scripts/wialon_bootstrap.py
```

(Docker bo'lsa: `docker compose exec backend python scripts/wialon_bootstrap.py`)

**Kutiladi:** birinchi qatorlarda `Rejim: DRY-RUN (yozmaydi)`, so'ng umumiy sonlar va "E'TIBOR TALAB QILADIGANLAR" ro'yxati,
oxirida `CSV: ...wialon_bootstrap_....csv` va `DRY-RUN: DB'ga hech narsa yozilmadi`.

### Statuslar nimani bildiradi

| Status | Ma'nosi | Nima qilish |
|---|---|---|
| `mapped` | Aniq `wialon_id` mos | Hech narsa, yaxshi |
| `name_unique` | `wialon_id` yo'q, lekin nomi **aynan** va **yagona** mos | `--map-exact-names` bilan bog'lanadi (7-bosqich) |
| `ambiguous` | Bir nechta aktiv/birlik bir xil nomli | **Avtomatik bog'lanmaydi.** Qo'lda hal qilinadi (quyida) |
| `unmapped` | TOIR'da mos aktiv yo'q | Aktiv TOIR'da yo'q bo'lishi mumkin. Keyin hal qilinadi |
| `asset_without_unit` | TOIR'da `wialon_id` bor, Wialon'da yo'q | Eski/o'chirilgan birlik bo'lishi mumkin |

### Hisobotni o'qish

- `suspect_absolute` soni ≥ 4 bo'lishi kutiladi (HILUX 366, T-28, 2 ta XCMG shular).
- `big_diff_gt_1000km`: TOIR mileage va Wialon `cnm` o'rtasida 1000 km dan katta farq. **Bu normal ko'p holatda**
  (TOIR qo'lda kiritilgan, Wialon boshqa boshlang'ich). Yangi tizimda bu muammo emas: faqat o'sish qo'shiladi.
- `mapped_without_state`: baseline yozilishi kerak bo'lgan aktivlar soni.

### Ambiguous/unmapped'ni qo'lda hal qilish

CSV faylni Excel'da oching, `ambiguous` va `unmapped` qatorlarini toping.
Har biri uchun TOIR'da to'g'ri aktivni toping va `fixed_assets.wialon_id` ga Wialon ID ni qo'lda yozing
(TOIR interfeysida yoki SQL bilan). Shoshilmang: bog'lanmagan birlik shunchaki mileage olmaydi, zarari yo'q.

**CSV'ni menga yuborsangiz**, ro'yxatni tekshirib beraman (ichida texnika nomlari bor: ichki ma'lumot, o'zingiz qaror qiling).

---

## 11. BOSQICH 7 — Bootstrap APPLY (5 daqiqa)

**Faqat dry-run hisoboti sizga mantiqiy ko'ringandan keyin.**

```bash
python scripts/wialon_bootstrap.py --apply --map-exact-names
```

**Nima qiladi:**
1. `mapped` aktivlar uchun **baseline** yozadi (`wialon_counter_state`).
2. `name_unique` aktivlarga `wialon_id` beradi.
3. **TOIR mileage'iga tegmaydi.**

**Kutiladi:** `APPLY: baseline yozildi: N ta. TOIR mileage o'zgartirilmadi.`

**Tekshiring:**

```bash
psql "<DB_URL>" -c "SELECT count(*) FROM wialon_counter_state;"
```

Son `N` ga yaqin bo'lishi kerak.

**Xato `unique constraint` chiqsa:** ikki aktivga bitta `wialon_id` berilmoqchi. To'xtang, matnni yuboring.
`--map-exact-names` ni qo'shmasdan qayta yuritib ko'ring (u faqat baseline yozadi).

---

## 12. BOSQICH 8 — Shubhali km'larni to'g'rilash (HILUX va boshqalar)

**Nima uchun:** TOIR mileage'i o'zgarmaydi, ya'ni agar u allaqachon noto'g'ri bo'lsa (masalan 10⁹),
noto'g'ri bo'lib qoladi. Uni **bir marta qo'lda** to'g'ri qiymatga o'rnatish kerak.

### 12.1. Haqiqiy km ni qayerdan olish

**HILUX (id 366):** mashinaning **priborlar panelidagi odometrni** o'qing.
Mening taxminim ~**323 976 km**, lekin bu faqat hisob. **Pribordan tasdiqlamasdan kiritmang.**

Boshqa shubhali aktivlar (audit'dagi `mileage > 1 000 000` ro'yxatidan): T-28х4 (1509), XCMG-958 (2830, 2832).
Ular uchun ham haqiqiy km ni pribordan yoki texnik pasportdan oling.

### 12.2. Aktiv ID sini toping

```bash
psql "<DB_URL>" -c "SELECT id, name, mileage FROM fixed_assets WHERE wialon_id = '366';"
```

`id` (uzun UUID) ni nusxalang.

### 12.3. To'g'rilang

```bash
psql "<DB_URL>" -v asset_id=<UUID_SHU_YERGA> -v real_km=<HAQIQIY_KM> -f backend/prod/003_fix_mileage_TEMPLATE.sql
```

Misol (qiymatlar uydirma): `-v asset_id=1f0c... -v real_km=323976`.

Bu `UPDATE` bilan birga `mileage_history` ga `manual` yozuv qo'shadi (iz qoladi).

**Tekshiring:** `SELECT name, mileage FROM fixed_assets WHERE wialon_id = '366';` → yangi qiymat.

---

## 13. BOSQICH 9 — Birinchi sinxronlash va tekshirish (20 daqiqa)

**Qayerda:** admin sifatida TOIR API orqali (Swagger yoki Postman yoki `curl`).

### 13.1. Bitta marta qo'lda sinxronlash

`WIALON_SYNC_ENABLED=true` qilishingiz **kerak** (aks holda endpoint `503` qaytaradi). Shuning uchun:

1. `WIALON_SYNC_ENABLED=true` qiling va backendni qayta ishga tushiring.
2. **Darhol** `POST /api/v1/wialon/sync` ni admin token bilan chaqiring.

> Davriy sinxronlash ham yoqiladi (odatda har 2 daqiqada). Bu yaxshi: baseline'lar allaqachon yozilgan, shuning uchun
> birinchi o'tishlar kichik deltalar bo'ladi.

### 13.2. Natijani tekshiring

```bash
psql "<DB_URL>" -f backend/prod/002_verify.sql
```

**Kutiladi:**

| Tekshiruv | Normal |
|---|---|
| `wialon_counter_state` statuslari | Ko'pchiligi `mileage=unchanged/accepted` |
| `wialon_rejected_readings` | **Kam yoki bo'sh** |
| HILUX 366 | `suspect_absolute = true`, **mileage o'zgarmagan** (12-bosqichdagi qiymat) |
| `mileage > 1 000 000` soni | 12-bosqichdan keyin kamaygan |
| `cneh_ma_lumot_yoq` | ~45 gacha (kontakt datchigi ishlamaydigan birliklar) |

### 13.3. Eng muhim tekshiruv: `mileage=None` xavfsizmi?

HILUX uchun qiymat o'zgarmaganini **ko'z bilan** tekshiring:

```bash
psql "<DB_URL>" -c "SELECT name, mileage, wialon_last_sync FROM fixed_assets WHERE wialon_id='366';"
```

- `mileage` = 12-bosqichda qo'ygan qiymat (yoki unga kichik o'sish) → **hammasi yaxshi**.
- `mileage` = 10⁹ ga o'zgarib ketgan → **darhol `WIALON_SYNC_ENABLED=false`**, backendni qayta ishga tushiring,
  va menga `services/assets.py` faylini yuboring (men noto'g'ri faraz qilgan bo'laman).

### 13.4. Log'da qidiring

Backend log'ida `Wialon counter gate:` qatori chiqadi, masalan:
`{'mileage_unchanged': 90, 'mileage_accepted': 12, 'unmapped': 20, ...}`. Bu qator sinxronlash ishlayotganini ko'rsatadi.

---

## 14. Qaytarish (nimadir noto'g'ri ketsa)

Tartib bilan:

1. `WIALON_SYNC_ENABLED=false` → backendni qayta ishga tushiring (**eng birinchi**, darhol to'xtatadi).
2. Eski kodni qaytaring (`git checkout <oldingi-shoxcha>` yoki oldingi image) → qayta ishga tushiring.
3. Yangi jadvallarni o'chirish (ixtiyoriy, ular zararsiz): `psql "<DB_URL>" -f backend/prod/rollback.sql`
4. Mileage buzilgan bo'lsa: zaxiradan tiklang (`pg_restore`) yoki 12-bosqichdagi shablon bilan qo'lda to'g'rilang.

---

## 15. BOSQICH 10 — Avtomatik sinxronlashni qoldirish va kuzatish (1 soat)

13-bosqich muvaffaqiyatli bo'lsa, `WIALON_SYNC_ENABLED=true` **qoladi**.

Birinchi 1 soat davomida har 15 daqiqada:

```bash
psql "<DB_URL>" -f backend/prod/002_verify.sql
```

- `wialon_rejected_readings` tez o'smayaptimi? (o'ssa, sababni `reason` ustunidan o'qing)
- Backend log'ida xato yo'qmi?

**Birinchi kunning oxirida** (kechqurun) yana bir marta tekshiring va HILUX kunlik o'sishini Wialon reportidagi bilan solishtiring:
`python wialon_tool.py full` (sizning kompyuteringizdan). Kutiladi: farq 1–3% dan kam.

---

## 16. BOSQICH 11 — Wialon administratoriga topshiriladigan ishlar (parallel)

TOIR tomoni Wialon'ni **o'zgartirmaydi**. Quyidagilarni faqat Wialon administratori to'g'rilay oladi.
Shu matnni unga yuboring:

> **Wialon (gps.agmk.uz) hisoblagich muammolari, tekshirish va tuzatish uchun:**
>
> 1. **HILUX 4x2 584 SAA (ID 366):** 2024-06-07 06:00:04 UTC da buzilgan paket (`param199 = 992 137 445 377`) hisoblagichga
>    +1 007 019 507 km qo'shgan. Hisoblagichni haqiqiy qiymatga (pribor bo'yicha) o'rnatish kerak.
> 2. **Boshqa kattaroq `cnm` (> 1 mln km):** ID 1509 (T-28х4), 2830 va 2832 (XCMG-958): shunga o'xshash.
> 3. **Mumkin bo'lmagan `cneh` (yuz ming soatlab):** ID 394 (HILUX 4x4 526 NAA), 2204 (ZL 50), 2725 (ТЭМ18 164).
> 4. **Tezlik/soat nomutanosibligi:** ID 2915 va 2916 (КамАЗ), 784 (КЖДЭ-16 809).
> 5. **Kontakt datchigi doim «Откл.»** (moto-soat hisoblanmayapti): taxminan 45 ta birlik, asosan ПЭ-2у / ПЭ-2М / ПЭ-2м seriyasi.
>    Ikkitasida doim «Вкл.»: МПЭ-2у 002 va ПЭ-2м 261.
> 6. **Yoqilg'i:** `calcTypes = 0` (hisoblash usuli yoqilmagan), me'yor 25,7 L/100 km HILUX uchun yuqori ko'rinadi: tekshirib bering.

### Wialon admini hisoblagichni tuzatgandan KEYIN (juda muhim)

Hisoblagich 1 007 343 489 dan ~324 000 ga tushadi. Yangi kod buni "**cnm kamaydi**" deb **rad etadi** (to'g'ri xulq).
Rad etish to'xtashi uchun yangi baseline o'rnatiladi:

```bash
cd backend
python scripts/wialon_rebaseline.py --unit-id 366            # avval ko'rish
python scripts/wialon_rebaseline.py --unit-id 366 --apply    # yozish
```

Bu **TOIR mileage'iga tegmaydi**, faqat solishtirish nuqtasini yangilaydi.

---

## 17. Muammolar jadvali

| Belgi | Ehtimoliy sabab | Nima qilish |
|---|---|---|
| `$py` xatosi | O'zgaruvchi bo'sh | `$py = "c:\python315\python.exe"` |
| `ModuleNotFoundError: app...` | Skript `backend/` dan tashqarida ishga tushdi | `cd backend` va qayta |
| Bootstrap: `CONFIG XATOSI` | Serverda `WIALON_HOST`/`WIALON_TOKEN` yo'q | Backend sozlamasiga qo'shing |
| Bootstrap: `xato 7` | Token huquqi yetmaydi | Wialon administratori |
| `unique constraint` | Bir `wialon_id` ikki aktivda | To'xtang, matnni yuboring |
| Sinxronlashdan keyin hamma `rejected` | Baseline yozilmagan yoki vaqt noto'g'ri | `002_verify.sql` va log'ni yuboring |
| HILUX mileage 10⁹ ga o'zgardi | `mileage=None` faraz noto'g'ri | 13.3 ga qarang |
| Aktiv mileage'i yangilanmayapti | Mapping yo'q (`unmapped`) | CSV'dan toping, `wialon_id` bering |
| Report vaqtlari 5 soat siljigan | API UTC'da | Toshkent = UTC+5 |

---

## 18. "Ish tugadi" mezonlari

Hammasi belgilangan bo'lsa, integratsiyaning **hisoblagich qismi** tugagan:

- [ ] Zaxira nusxa olingan va saqlangan.
- [ ] 2 ta yangi jadval bazada bor.
- [ ] Yangi kod prodda, backend ishlayapti.
- [ ] Bootstrap `--apply` bajarilgan, `wialon_counter_state` to'ldirilgan.
- [ ] `ambiguous`/`unmapped` ro'yxati ko'rib chiqilgan (hal qilingan yoki ongli qoldirilgan).
- [ ] HILUX va boshqa shubhali aktivlarning mileage'i pribordan to'g'rilangan.
- [ ] Birinchi sinxronlashdan keyin HILUX mileage'i **o'zgarmagan** (13.3).
- [ ] Rad etilganlar jadvali kam; sababi tushunarli.
- [ ] Birinchi kun oxirida HILUX kunlik o'sishi Wialon report'iga mos (±1–3%).
- [ ] Wialon administratoriga 16-bo'limdagi ro'yxat yuborilgan.

---

## 19. Hali qilinmagan ishlar (keyingi bosqich, ixtiyoriy)

| Ish | Nima kerak mendan | Izoh |
|---|---|---|
| **Moto-soatni TOIR ekranida ko'rsatish** | `routers/wialon_pull.py`, `schemas/wialon.py`, aktivlar router/schema fayllari | Hozir faqat `wialon_counter_state.engine_hours` jadvalida |
| **Wialon hisobotlarini TOIR'da bajarish va eksport** | Yuqoridagi fayllar + frontend `app/dashboard/reports/page.tsx` | Report API (`wialon_tool.py report`) ishlashi isbotlangan; TOIR moduli yozilmagan |
| **Kunlik tekshiruv** (hisoblagich o'sishi vs report GPS masofasi) | Qaror: qaysi birliklar uchun | Yangi buzilishni erta aniqlaydi |
| **Hisobot vaqt zonasi** | Wialon SDK'dan tekshirish | API UTC beradi; hozircha +5 soat qo'lda |
| **Eski `/api/v1/wialon/input` bilan to'qnashuv tekshiruvi** | Server loglari | Production'dan oldin bilish kerak: u ishlatiladimi? |

---

## 20. Fayllar xaritasi (nima qayerda)

| Fayl | Vazifasi |
|---|---|
| `wialon_tool.py` (repo ildizi) | Terminal diagnostikasi, `full` buyrug'i |
| `backend/app/services/wialon_quality.py` | Gate qoidalari |
| `backend/app/services/wialon.py` | Sinxronlash (delta bilan) |
| `backend/app/integrations/wialon_client.py` | Wialon API klienti (+`cneh`, `cfl`) |
| `backend/app/models/wialon_counters.py` | Yangi jadvallar modeli |
| `backend/app/repositories/wialon_counters.py` | Yangi jadvallar bilan ishlash |
| `backend/scripts/wialon_bootstrap.py` | Baseline va mapping (dry-run standart) |
| `backend/scripts/wialon_rebaseline.py` | Tuzatilgandan keyin yangi baseline |
| `backend/prod/00_audit_readonly.sql` | Audit (o'qish) |
| `backend/prod/001_wialon_counters.sql` | Migratsiya |
| `backend/prod/002_verify.sql` | Sinxronlashdan keyin tekshiruv |
| `backend/prod/003_fix_mileage_TEMPLATE.sql` | Mileage qo'lda tuzatish shabloni |
| `backend/prod/rollback.sql` | Yangi jadvallarni o'chirish |

---

## 21. Menga nimani yuborasiz (har bosqichdan keyin)

| Bosqich | Yuboring | **Yubormang** |
|---|---|---|
| 3 (audit) | `audit_before.txt` | DB paroli |
| 6 (dry-run) | Terminal matni va CSV | Token |
| 7 (apply) | Terminal matni | — |
| 9 (sinxronlash) | `002_verify.sql` natijasi, log'dan `Wialon counter gate:` qatori | Token, `eid`/`sid`, `.env` |
| Xato bo'lsa | Xato matni (to'liq) | Parol va tokenlar |

**Eslatma:** terminal chiqishida token yoki parol ko'rinib qolsa, yuborishdan oldin o'chirib tashlang.
