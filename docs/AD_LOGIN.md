# Active Directory (LDAPS) orqali kirish

Holat: AD faol (3 ta foydalanuvchi AD orqali kirgan, objectGUID tasdiqlangan). Mahalliy parollar olib tashlandi (AUTH-01, 2026-11-23).

## Asosiy qoida (AUTH-01, 2026-11-23)
**TOIR'da parol saqlanmaydi.** Kirishning yagona yo'li — domen (AD). `users.hashed_password` ustuni yo'q (migratsiya `0042`), `users.auth_source` faqat `'ad'`, `ad_username` majburiy. Mahalliy login, avariya yozuvi, parolni tiklash va «AD'ga o'tkazish» olib tashlangan.

Kirishning har bir urinishi `audit_logs.details.auth_source='ad'` bilan yoziladi. Parol hech qachon yozilmaydi.

## Foydalanuvchiga ruxsat berish
- **Admin → Пользователи → «Выдать доступ»**: faqat domen logini, ФИО, rol, uchastka. Parol maydoni yo'q. Server `login@agmk.uz` email va `auth_source='ad'` bilan yozuv yaratadi (`POST /api/v1/users/ad`).
- Domen akkaunti mavjudligi **kiritishda tekshirilmaydi** (servis akkaunti yo'q). U **birinchi muvaffaqiyatli kirishda** tasdiqlanadi va `objectGUID` yoziladi. Keyinroq boshqa GUID kelsa, kirish rad etiladi.
- Domenda yozuvi bor, TOIR'da yo'q user kirsa: rad (hech narsa avtomatik yaratilmaydi). TOIR'da `is_active=false` bo'lsa ham rad.
- Yangi o'rnatishdagi birinchi admin: `python -m app.cli create-ad-admin --email ... --ad-username ... --full-name ...` (parolsiz, faqat admin yo'q bo'lsa).

## Domen ishlamay qolganda: favqulodda seans
Faqat **server shell**'ga kira oladigan odam uchun (HTTP endpoint yo'q, parol yo'q):
```
docker compose exec -T backend python -m app.cli emergency-session --admin <email yoki domen logini>
```
- Faqat faol AD-admin uchun; 15 daqiqa; yangilash bilan uzaytirib bo'lmaydi.
- Audit jurnaliga yoziladi (`details.event=emergency_session`, operator = shell foydalanuvchisi@host). Token jurnalga yozilmaydi.
- Chiqargan buyruq brauzer konsoliga qo'yiladigan `cookieStore.set(...)` qatorini beradi; token bir marta ko'rsatiladi.
- Foydalanish tartibi: faqat domen o'chganda, keyin sababini yozib qo'ying.

## Qanday ishlaydi (kirish)
- Login maydoniga `t.turakulov` yoki `t.turakulov@agmk.uz`. Parol domen paroli.
- `ldaps://dc-r.agmk.uz:636` (zaxira `dc.agmk.uz`), CA (`backend/app/certs/agmk-DC-R-CA-3.crt`) va server nomi majburiy tekshiriladi; "Who am I?" va `sAMAccountName` qidiruvi.
- Domen ishlamasa AD userga 503 (mahalliy parolga **o'tilmaydi**: AD userning parol hashi yo'q).

## Xavfsizlik qoidalari (kodda)
- Faqat 636. Sertifikat tekshiruvi o'chirilmaydi. Bo'sh parol LDAP'ga yuborilmaydi.
- Xato paroldan keyin zaxira DC'ga o'tilmaydi (faqat tarmoq/TLS xatosida).
- TOIR'da yozuvi yo'q login uchun domenga umuman so'rov yuborilmaydi (TOIR domen parollarini taxmin qilish vositasiga aylanmasin).
- Bitta domen hisobi uchun 15 daqiqada 3 ta xatodan keyin 429 (AD o'zi 5 tadan keyin qulflaydi). Bitta IP'dan 20 ta xatodan keyin 429.
- UPN tuzog'idan himoya: parol aynan terilgan hisobni ochishi shart.
- AD xato kodi (52e, 775, 533...) faqat serverning logiga yoziladi (parolsiz). Foydalanuvchi har doim bir xil xabarni ko'radi.
- Login qiymati filtrga qo'yilishdan oldin escape qilinadi; `*()\` va bo'sh joyli loginlar API'da rad etiladi.

## Yoqish (siz qilasiz, `.env` ga men tegmayman)
`.env` ga `AD_AUTH_ENABLED=true` (shu nom; `.env.example` ga ham faqat nomini qo'shing). So'ng `docker compose up -d --build backend frontend` (migratsiya `0030_user_auth_source` konteyner ishga tushganda avtomatik bajariladi).
Eski `AD_LOCAL_FALLBACK_ON_ERROR` sozlamasi olib tashlandi.

## Ma'lum cheklovlar (ochiq)
- Servis akkaunti yo'qligi sababli «AD'da mavjudligini tekshirish» kiritish paytida emas, birinchi kirishda bajariladi. Servis akkaunti (`AD_BIND_DN`/`AD_BIND_PASSWORD`, faqat o'qish) berilsa, ruxsat berish paytida tekshirish va `objectGUID` ni darrov yozish mumkin.
- AD so'rovi bazadagi tranzaksiya ichida bajariladi: DC juda sekin bo'lsa (5+10 s) ulanish shu vaqt band turadi.
- Hisob AD'da o'chirilsa/bloklansa kirish to'xtaydi; TOIR'da `is_active=false` qilish alohida.
- UI faqat rus tilida (loyiha «Russian only», migratsiya 0025); uch tilli UI uchun i18n tizimi yo'q.
