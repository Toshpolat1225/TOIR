# TOIR

TOIR — texnik xizmat ko'rsatish va ta'mirlash tizimi. Ilova Next.js frontend,
FastAPI backend va PostgreSQL 16 bazasidan iborat. Production kirish nuqtasi Caddy;
backend va baza host portlarini ochmaydi.

## Talablar

- Docker Engine va Docker Compose v2
- Production uchun DNS A/AAAA yozuvi serverga yo'naltirilgan public domen va tashqaridan
  ochiq TCP 80/443 (Caddy avtomatik Let's Encrypt sertifikatini oladi)
- Domen yoki HTTPS sertifikat mavjud bo'lmasa, TLS usulini tanlamasdan production deploy qilmang.

## Birinchi ishga tushirish

1. Ildizda `.env.example` nusxasini `.env` qiling.
2. `POSTGRES_PASSWORD` va `JWT_SECRET` ni noyob, kuchli qiymatlarga almashtiring.
   `JWT_SECRET` kamida 32 bayt bo'lishi kerak. Maxfiy qiymatlarni git'ga qo'shmang.
3. `DOMAIN` ni DNS bilan serverga yo'naltirilgan haqiqiy domen bilan almashtiring.
   `CORS_ORIGINS` aynan frontend origin'i bo'lsin, masalan `https://toir.example.com`;
   wildcard (`*`) ishlatmang.
4. Productionda `API_DOCS_ENABLED=false` qoldiring; docs zarur bo'lsa vaqtincha yoqing.
5. Quyidagilarni bajaring:

```sh
docker compose up --build -d
docker compose ps
docker compose logs --tail=100 proxy backend
```

Compose backend startida Alembic migratsiyalarini bajaradi. `DOMAIN` DNS'i tayyor bo'lmasa
yoki 80/443 tashqaridan yetib bormasa, Caddy TLS sertifikatini ola olmaydi.
Ilovaga `https://<DOMAIN>` orqali kiring. Faqat Caddy hostning 80/443 portlarini chiqaradi;
PostgreSQL, backend va frontend faqat ichki Compose tarmog'ida qoladi.
Muvaffaqiyatsiz loginlar parol yoki emailni ochiq saqlamaydigan HMAC kaliti bo'yicha
PostgreSQL'da 15 daqiqalik sliding window bilan hisoblanadi; beshta xatodan keyin 429 qaytadi.

## Lokal frontend/backend ishlanmasi

`docker compose up` production Caddy konfiguratsiyasidan foydalanadi. Lokal kod ishlab
chiqishda PostgreSQL va backendni alohida ishga tushirib, frontend uchun
`NEXT_PUBLIC_API_URL=http://localhost:8010/api/v1` ni belgilang. Backend `.env` da
`CORS_ORIGINS=http://localhost:3000` (yoki aniq dev origin) bo'lishi kerak.

## Backup va tiklash

Kundalik custom-format backup yaratish va 14 kundan eski backup'larni aylantirish:

```sh
BACKUP_RETENTION_DAYS=14 bash scripts/backup_postgres.sh
```

`BACKUP_DIR` bilan saqlash joyini o'zgartirish mumkin. Backup katalogi maxfiy ma'lumot
saqlaydi: ruxsatlari cheklangan diskda saqlang, off-host nusxani shifrlang va nusxalash
hamda tiklashni muntazam sinang. Skript `backups/` ichiga yozadi; u Docker build context'dan
chiqarilgan.

Linux serverda har kuni 02:15 da ishga tushirish uchun cron'ga (loyiha joylashuvini moslab)
quyidagini qo'shing:

```cron
15 2 * * * cd /opt/toir && BACKUP_RETENTION_DAYS=14 bash scripts/backup_postgres.sh
```

Backup'ni joriy bazaga tiklash mavjud obyektlarni almashtirishi mumkin. Avval ilovani to'xtating
va tiklanadigan bazaning alohida backup'ini oling. Keyin:

```sh
docker compose stop backend
docker compose exec -T postgres sh -ec \
  'pg_restore --clean --if-exists --no-owner --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"' \
  < backups/toir-YYYYMMDDTHHMMSSZ.dump
docker compose start backend
```

Tiklash buyrug'ida tanlangan arxiv faylining aniq nomini kiriting. Avval production bo'lmagan
nusxada tiklashni sinash tavsiya etiladi. DB rollari va global PostgreSQL sozlamalari custom
database dump'iga kirmaydi.

## CI va lokal tekshiruv

GitHub Actions Python 3.12 backend unit testlarini, frontend TypeScript/lint/build va ikkala
Docker image build'ini bajaradi. Lokal frontend tekshiruvi:

```sh
npm ci
npx tsc --noEmit
npm run lint
npm run build
```

Backend unit testlari (`backend/` ichida, Python 3.12):

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

## Nosozliklarni aniqlash

- **Caddy sertifikat olmayapti:** `DOMAIN` to'g'riligini, DNS A/AAAA yozuvini va TCP 80/443
  firewall/NAT'da ochiqligini tekshiring. Proxy logi: `docker compose logs --tail=200 proxy`.
- **Backend ishga tushmaydi:** `.env` dagi DB/JWT/CORS sozlamalarini tekshirib,
  `docker compose logs --tail=200 postgres backend` ko'ring. `.env` ni log/chatga ko'chirmang.
- **Migratsiya xatosi:** `docker compose logs backend` buyrug'i bilan logni ko'ring; deployni davom ettirishdan oldin
  DB backup oling va migratsiya xabarini tekshiring.
- **Frontend API xatosi:** production image build qilinganda `DOMAIN` to'g'ri berilganini va
  `CORS_ORIGINS` aynan `https://<DOMAIN>` ekanini tekshiring.
- **API docs ko'rinmaydi:** bu production uchun odatiy holat (`API_DOCS_ENABLED=false`).
  Zarur bo'lsa `.env` orqali yoqib, servisni qayta yarating.

Production deploy yoki server tekshiruvi alohida foydalanuvchi ruxsatini talab qiladi.
