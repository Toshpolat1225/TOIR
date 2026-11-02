# TOIR <-> Wialon: PROD ishga tushirish tartibi

Hamma buyruqni O'ZINGIZ prod serverda bajarasiz. Har bosqichdan keyin natijani tekshiring; xato bo'lsa TO'XTANG.
`WIALON_SYNC_ENABLED=false` bo'lib turadi to 7-bosqichgacha.

0. **Zaxira** (majburiy): `pg_dump -Fc -f toir_before_wialon_$(date +%Y%m%d_%H%M).dump <DB_URL>`
1. **Audit (o'qish)**: `psql <DB_URL> -f prod/00_audit_readonly.sql > audit_before.txt`
   - dublikat `wialon_id` bo'lmasligi kerak; `mileage > 1 000 000` ro'yxatini saqlang.
2. **Migratsiya**: `psql <DB_URL> -v ON_ERROR_STOP=1 -f prod/001_wialon_counters.sql`  (faqat 2 ta yangi jadval)
3. **Kod**: fayllarni `backend/` ichiga qo'ying (README.txt), yangi modelni `Base.metadata` import ro'yxatiga qo'shing,
   backendni qayta ishga tushiring. Sinxronlash hali O'CHIQ.
4. **Bootstrap DRY-RUN** (yozmaydi): `cd backend && python scripts/wialon_bootstrap.py`
   - hisobotdagi `ambiguous`, `unmapped`, `asset_without_unit`, katta `farq` va `shubhali` qatorlarini ko'rib chiqing.
5. **Bootstrap APPLY**: `python scripts/wialon_bootstrap.py --apply --map-exact-names`
   - faqat baseline yozadi va nomi AYNAN va YAGONA mos aktivlarga `wialon_id` beradi. TOIR mileage'iga tegmaydi.
6. **Shubhali mileage** (HILUX va b.): priborning haqiqiy km sini kiritib `prod/003_fix_mileage_TEMPLATE.sql` bilan tuzating.
7. **Bitta sinxronlash** (alohida jarayon; server yoqilmaydi):
   `docker compose run --rm -e WIALON_SYNC_ENABLED=true backend python scripts/wialon_sync_once.py`
   (Docker bo'lmasa: shu env bilan `python scripts/wialon_sync_once.py`). Keyin `psql <DB_URL> -f prod/002_verify.sql`.
   - kutiladi: `wialon_counter_state` qatorlari ~ mapped soni; rad etilganlar kam; HILUX mileage o'zgarmagan.
8. Hammasi joyida bo'lsa `WIALON_SYNC_ENABLED=true` qiling va 1 soat log/jadvallarni kuzating.

**Qaytarish:** `WIALON_SYNC_ENABLED=false` -> eski kodni qaytaring -> `prod/rollback.sql`. Mileage buzilgan bo'lsa zaxiradan tiklang.
