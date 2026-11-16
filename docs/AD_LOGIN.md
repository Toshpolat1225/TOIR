# Active Directory (LDAPS) orqali kirish

Holat: kod va testlar tayyor (2026-11-16), standart **o'chiq**. Haqiqiy domen paroli bilan jonli sinov hali bajarilmagan.

## Asosiy qoida
Parolni **qaysi backend** tekshirishini loginning shakli emas, `users.auth_source` ustuni belgilaydi:

| auth_source | Parol | Kim tekshiradi |
|---|---|---|
| `ad` | saqlanmaydi (`hashed_password` NULL) | domen (LDAPS) |
| `local` | bcrypt hash | TOIR bazasi, domenga umuman murojaat qilinmaydi |

Bir xil parol bo'lsa ham manba ajraladi. Kirishning har bir urinishi `audit_logs.details.auth_source` ga (`ad`/`local`) yoziladi. Parol hech qachon yozilmaydi.

## Foydalanuvchiga ruxsat berish
- **Admin → Пользователи → «Выдать доступ»**: faqat doménli login, ФИО, rol, uchastka. Parol maydoni yo'q. Server `login@agmk.uz` email va `auth_source='ad'` bilan yozuv yaratadi (`POST /api/v1/users/ad`).
- Domen akkaunti mavjudligi **kiritishda tekshirilmaydi** (servis akkaunti yo'q). U **birinchi muvaffaqiyatli kirishda** tasdiqlanadi va `objectGUID` yoziladi. Keyinroq boshqa GUID kelsa (login boshqa odamga berilgan), kirish rad etiladi. Bir GUID ikki foydalanuvchiga bog'lanmaydi.
- **Aвария**: «Аварийная локальная запись» (login+parol) faqat `admin` roli uchun (`POST /api/v1/users`).
- Domenda yozuvi bor, TOIR'da yo'q user kirsa: rad (hech narsa avtomatik yaratilmaydi). TOIR'da `is_active=false` bo'lsa ham rad.

## Mavjud mahalliy userni AD'ga o'tkazish
Faqat admin aniq amali bilan, qaytarib bo'lmaydi: parol hash o'chadi, sessiyalar bekor qilinadi, audit logga yoziladi (`details.event=convert_to_ad`).
- UI: foydalanuvchini tahrirlash → «Перевести на вход через домен» (o'z akkauntingizni o'tkaza olmaysiz).
- O'zingizni o'tkazish (yagona admin) yoki UI ishlamasa, serverda:
```
docker compose exec -T backend python -m app.cli user-convert-to-ad --email <email> --ad-username <login>          # ko'rish
docker compose exec -T backend python -m app.cli user-convert-to-ad --email <email> --ad-username <login> --apply  # bajarish
```
**Ehtiyot:** o'tkazgandan keyin kirish faqat domen orqali. Avval boshqa AD akkauntida kirishni sinab ko'ring yoki bitta aварийная local admin qoldiring.

## Qanday ishlaydi (kirish)
- Login maydoniga `t.turakulov` yoki `t.turakulov@agmk.uz`. Parol domen paroli.
- `ldaps://dc-r.agmk.uz:636` (zaxira `dc.agmk.uz`), CA (`backend/app/certs/agmk-DC-R-CA-3.crt`) va server nomi majburiy tekshiriladi; "Who am I?" va `sAMAccountName` qidiruvi.
- Domen ishlamasa AD userga 503 (mahalliy parolga **o'tilmaydi**: AD userning parol hashi yo'q). Mahalliy (`local`) userlar domen holatiga bog'liq emas.

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
