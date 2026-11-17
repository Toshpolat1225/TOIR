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

## 4. HTTPS va avtomatik zaxira

- `proxy` 80 (HTTP) va 443 (HTTPS, Caddy ichki CA) portlarini tinglaydi; ikkalasi bir xil ishlaydi. Ildiz sertifikati nusxasi: `toir-local-root.crt`. Mijoz PC'da uni «Ishonchli ildiz sertifikatlari»ga o'rnating (Windows: faylga ikki marta bosing → «Install Certificate» → «Local Machine» → «Trusted Root Certification Authorities»). Sertifikat Caddy hajmi `caddy_data` da saqlanadi — shu hajmni o'chirmang, aks holda yangi ildiz yaratiladi va mijozlarga qayta o'rnatish kerak bo'ladi.
- `NEXT_PUBLIC_API_URL` nisbiy (`/api/v1`): manzil yoki protokol o'zgarsa frontendni qayta qurish shart emas.
- `backup` xizmati har kecha 21:00 UTC (`BACKUP_HOUR_UTC`) `backups/auto-*.dump` yaratadi va `BACKUP_RETENTION_DAYS` (standart 14) dan eskisini o'chiradi. Holat: `docker compose logs backup`.
- Bitta xizmatni qayta joylash: `docker compose up -d --no-deps <xizmat>` (aks holda bog'liq xizmatlar ham qayta ishga tushadi).

## 5. Karta sahifasi: Google Maps kaliti

Sahifa `/dashboard/map` Wialon (GPS) va GTK koordinatalarini ko'rsatadi. Barcha nuqtalarni bitta interaktiv Google xaritada ko'rish uchun **Maps JavaScript API** kaliti kerak:

1. Google Cloud'da loyiha oching, **Maps JavaScript API** ni yoqing, API kalit yarating va uni «HTTP referrers» bilan TOIR manziliga (`https://<DOMAIN>/*`, kerak bo'lsa `http://<DOMAIN>/*`) cheklang. Kalit sahifa kodiga tushadi (bu odatiy), shuning uchun cheklash shart.
2. Serverdagi `.env` fayliga `GOOGLE_MAPS_API_KEY=<kalit>` qatorini qo'shing (mazmunni chatga yozmang).
3. Frontendni qayta quring: `docker compose build frontend` va `docker compose up -d --no-deps frontend`.

Kalit bo'lmasa ham sahifa ishlaydi: ro'yxat va tanlangan birlikning Google xaritadagi o'rni (kalitsiz). Mijoz kompyuterlarda `maps.googleapis.com` ga internet kerak.

Kalit bo'lmasa sahifa OpenStreetMap xaritasini (Leaflet) ko'rsatadi: barcha nuqtalar, klaster va popup bilan, kartasiz. Kalit qo'yilsa Google xarita ishlatiladi. Ikkalasi uchun ham mijoz kompyuterda internet kerak (`tile.openstreetmap.org` yoki `maps.googleapis.com`).

Kalit noto'g'ri bo'lsa (`InvalidKeyMapError`, referrer yoki billing xatosi) sahifa o'zi OpenStreetMap xaritasiga o'tadi. Google kaliti `AIza` bilan boshlanadi; boshqa xizmat kaliti (masalan, qidiruv API) bu yerga mos kelmaydi.
