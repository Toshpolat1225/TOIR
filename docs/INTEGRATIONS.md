# Tashqi manbalarni ulash shartnomasi

Yangi manba qo‘shishdan oldin ushbu shartnomani bajaring. Har bir manbaning
ma’lumoti alohida ko‘zgu jadvallarida saqlanadi; mavjud manba jadvallari boshqa
manbaning ma’lumotlari bilan aralashtirilmaydi.

## Majburiy qismlar

1. **Ko‘zgu jadvallari:** manbaning tashqi identifikatorini barqaror birlamchi
   kalit qiling. `name`, `number`, `serial`, `inventory`, `model`, `type`
   maydonlarini matching’ga uzating. Sinxron holatini va manbada oxirgi
   ko‘rilgan vaqtni ham saqlang. Faol bog‘lanishlar `asset_source_links` da
   yagona vakolatli manba hisoblanadi.
2. **Adapter:** `app/integrations/base.py` dagi `SourceAdapter` protokolini
   bajaring. Adapter manba nomi va ko‘zgu jadvali nomini beradi;
   `fetch_snapshot()` esa `SourceObject` ro‘yxatini qaytaradi. Parol va
   tokenlar jurnallarga yoki xato matniga yozilmaydi.
3. **Egalik matritsasi:** `app/core/asset_field_policy.py` ga har bir passport
   maydoni uchun ega manba va rejim qo‘shing. Mavjud qiymatni jim almashtirmang:
   faqat `auto_fill_if_empty` avtomatik yozishi mumkin; boshqa farqlar taklif
   sifatida jurnalga tushadi.
4. **Ruxsat:** ko‘zgu va bog‘lanmagan obyektlarni ko‘rish uchun
   `asset_links.view`; qo‘lda bog‘lash yoki manbaga xos boshqaruv uchun
   `asset_links.manage` ishlating. Yangi ruxsat kerak bo‘lsa, uni
   `core/permissions.py` va Alembic migratsiyasida aniq rollar bilan seed qiling.
5. **Matching:** faqat `services/asset_matching.py` dagi umumiy
   normalizatsiya va `high` / `ambiguous` / `none` darajalaridan foydalaning.
   Nom bo‘yicha avtomatik bog‘lamang; tasdiq odam tomonidan beriladi.
6. **Endpointlar:** bog‘lanmagan ko‘zgu yozuvlari uchun umumiy
   `/api/v1/asset-links/unmatched?source=...` endpointini qayta ishlating.
   Javob `{items,total,limit,offset}` shaklida bo‘lsin.

## Yangi manba qo‘shish ro‘yxati

- [ ] Yangi ko‘zgu jadvallari va ORM/repository qatlamini qo‘shish.
- [ ] `SourceAdapter` realizatsiyasini qo‘shish va sinxronni ulash.
- [ ] `SourceObject` maydonlarini to‘ldirish hamda policy jadvaliga ega qatorlarni qo‘shish.
- [ ] Kerak bo‘lsa ruxsatni migratsiyada seed qilish; `master` ruxsatini alohida
  tasdiqlamasdan bermaslik.
- [ ] Matching, normalizatsiya, takror, bog‘langan/bog‘lanmagan va
  `high` / `ambiguous` / `none` holatlarini tarmoqsiz test qilish.
- [ ] Sinxron xatosi, takliflar va ruxsatlarni test qilish.
- [ ] Yangi endpoint yoki yozish amali bo‘lsa, loyiha uslubida E2E skript qo‘shish.
- [ ] PostgreSQL migratsiyasini alohida test bazasida tekshirish; jonli serverga
  agent tomonidan ulanmaslik.

Vesavoy va 1C uchun hozircha integratsiya qo‘shilmagan. Ular kelajakda ushbu
shartnomani qo‘llashi kerak.
