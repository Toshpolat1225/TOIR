# Yangi serverga ko'chirish

Buyruqlar loyiha papkasidagi PowerShell oynasida bajariladi. Yangi serverda faqat TOIR uchun bo'sh PostgreSQL volume ishlating. Mavjud `fuel` xizmatlari va ularning volume'lariga tegmang.

## 1. Toza o'rnatish

Compose `postgres/schema.sql` faylini avtomatik yuklamaydi. Backend konteyneri ishga tushganda `entrypoint.sh` `alembic upgrade head` bajaradi. Shuning uchun sxemani qo'lda `psql -f postgres/schema.sql` bilan yuklamang: bu migratsiyalar bilan ikkinchi, mustaqil yo'l bo'lib, natijani buzishi mumkin.

```powershell
# [PC] Loyiha papkasida, yangi va bo'sh TOIR bazasi bilan
docker compose up -d --build
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.cli seed-reference
docker compose exec backend python -m app.cli seed-intervals
```

Migratsiyalar aktiv turlar, statuslar va ruxsatlar uchun kerakli katalog qatorlarini ham qo'shadi. `seed-reference` bo'lim/uchastka ma'lumotlarini, `seed-intervals` esa texnik xizmat intervalini kiritadi.

## 2. Mavjud bazani ko'chirish

Avval mavjud bazaning maxsus formatdagi zaxira nusxasini oling. Bu buyruqlar parolni terminalga chiqarmaydi.

```powershell
# [PC] Eski TOIR serverida; fayl konteynerda yaratiladi, so'ng kompyuterga olinadi
docker compose exec postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/toir-backup.dump'
docker compose cp postgres:/tmp/toir-backup.dump .\toir-backup.dump
```

Yangi serverda zaxirani avval tekshirilgan, bo'sh TOIR bazasiga tiklang. `--clean` shu maqsad bazasidagi mavjud obyektlarni almashtiradi; noto'g'ri bazaga ishlatmang.

```powershell
# [PC] Yangi serverda: faqat TOIR ilova xizmatlarini to'xtatib, Postgresni qoldiring
docker compose stop backend frontend proxy
docker compose cp .\toir-backup.dump postgres:/tmp/toir-backup.dump
docker compose exec postgres sh -c 'pg_restore --clean --if-exists --no-owner --no-acl -U "$POSTGRES_USER" -d "$POSTGRES_DB" /tmp/toir-backup.dump'
```

Zaxirada `alembic_version` bo'lsa, uning yozuvini tekshiring. `0022_asset_number_dupes` bo'lsa, `stamp` qilmang; yangi migratsiyalarni bajaring:

```powershell
# [PC] Backup tiklangandan so'ng
docker compose run --rm --no-deps --entrypoint alembic backend current
docker compose run --rm --no-deps --entrypoint alembic backend upgrade head
```

Agar eski bazada `alembic_version` bo'lmasa, `stamp` faqat oldingi barcha migratsiyalar (0001–0022) haqiqatan qo'llangani va sxema 0022 holatiga mosligi tasdiqlangandan keyin ishlatiladi. Bunda `head` emas, 0022 belgilanadi, so'ng 0023–0024 bajariladi:

```powershell
# [PC] Faqat yuqoridagi shartlar tasdiqlansa
docker compose run --rm --no-deps --entrypoint alembic backend stamp 0022_asset_number_dupes
docker compose run --rm --no-deps --entrypoint alembic backend upgrade head
```

`stamp head` bilan yangi migratsiyalarni o'tkazib yubormang. Migratsiya tugagach, xizmatlarni qayta ishga tushiring:

```powershell
# [PC]
docker compose up -d --build
```

## 3. Sxemani dump bilan solishtirish

Toza o'rnatish va migratsiya tugagach, PostgreSQLdan faqat sxemani oling va `schema_actual.sql` bilan satrma-satr solishtiring. Eski dump P9 oldingi holati bo'lsa, 7 ta olib tashlangan ustun va indeks tuzatishi kutiladigan farqdir.

```powershell
# [PC] Loyiha papkasida
docker compose exec postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --schema-only --no-owner --no-privileges > /tmp/schema_fresh.sql'
docker compose cp postgres:/tmp/schema_fresh.sql .\schema_fresh.sql
Compare-Object (Get-Content .\schema_actual.sql) (Get-Content .\schema_fresh.sql)
```
