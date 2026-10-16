Ishlash qoidalari
- Har bir promptni alohida yuboring. Agent bir bosqichni tugatib, tekshiruv natijasini bermaguncha keyingisiga o‘tmang.
- Dastlab kod va ma’lumotlar bazasini o‘zgartirmasdan, mavjud holatni o‘rgansin.
- Ma’lumotlar bazasini tozalash, jadvalni o‘chirish, mavjud ma’lumotlarni almashtirish yoki ishlab turgan serverga deploy qilishga avtomatik ruxsat bermang.
- Har bir bosqichda frontend, backend, ma’lumotlar bazasi, ruxsatlar va testlarni birgalikda hisobga olsin.
- Model taxmin bilan kod yozmasin: avval mavjud fayllarni ochsin, keyin aniq o‘zgarish kiritsin.
- Har bir bosqich yakunida o‘zgartirilgan fayllar, bajarilgan testlar, aniqlangan muammolar va qo‘lda tekshirish yo‘riqnomasini bersin.
TOIR uchun bajarish ketma-ketligi

0. Mustaqil audit va rejalashtirish
Arxitektura, mavjud jadvallar, API, bog‘liqliklar va xavflarni aniqlash.




1. Uch tilli tizim
O‘zbek lotin, o‘zbek kirill va rus tili — interfeysdan tortib dinamik ma’lumotlargacha.




2. Asosiy vositalar spravochniklari
Asosiy vosita turlari va statuslarini boshqarish.




3. Dinamik tashkiliy ierarxiya
Korxona → sex → uchastka yoki xizmat → ichki bo‘linmalar.




4. Asosiy vositalar sahifasi
Vizual kartalar, statistikalar, bosilganda jadvalni filtrlash.




5. Наряды-заказы va TMЦ
Remont turi, vazifalar, materiallar va bajarilgan ishlar.




6. Har bir rol uchun alohida ruxsatlar
Sahifa, amal va ma’lumot doirasidagi server tekshiruvlari.




7. Foydalanuvchini faollashtirish va bloklash
Backend, JWT va faol sessiyalar bilan birgalikda.




8. Hisobotlarda probeg
Наряд-заказ ochilgan paytdagi probeg ko‘rsatkichi va uning tarixi.




9. Barcha sahifalardagi qulay filtrlar
Qidiruv, kombinatsiyalangan filtrlar, saralash, pagination va eksport.




10. Yakuniy integratsiya auditi
Barcha modullar, migratsiyalar, testlar va xavfsizlikni tekshirish.




0-PROMPT. Avval loyihani to‘liq o‘rganish
Birinchi bo‘lib aynan shu promptni yuboring. Bu bosqichda agent hali kodni o‘zgartirmasligi kerak.
TOIR — 0-BOSQICH: MUSTAQIL ARXITEKTURA AUDITI VA ISH REJASI
Rol
Sen tajribali Senior Full-Stack Engineer, Software Architect, Database Architect va Application Security Engineer sifatida ishlaysan.
Loyiha haqida
TOIR loyihasining mavjud arxitekturasini saqla. Loyiha Next.js 15 App Router, React 19, TypeScript, Python 3.12 FastAPI, SQLAlchemy async, PostgreSQL 16, Alembic, Docker Compose va JWT autentifikatsiyasidan foydalanishi mumkin. Bu ma’lumotlarni taxmin sifatida qabul qilma: haqiqiy repository va konfiguratsiyalardan tekshir.
Qat’iy cheklovlar
Ushbu bosqich faqat READ-ONLY audit hisoblanadi.
- Kodni o‘zgartirma.
- Fayl yaratma yoki o‘chirma.
- Database yozuvlarini o‘zgartirma.
- Alembic migratsiyasini ishga tushirma.
- Dependency o‘rnatma yoki yangilama.
- Docker containerlarni qayta ishga tushirma.
- Production serverga ulanma va deploy qilma.
- .env, JWT secret, parol, token va boshqa maxfiy ma’lumotlarni natijaga chiqarma.
O‘rganilishi shart bo‘lgan qismlar
1. Repository tuzilmasi va haqiqiy Git holati.
2. Frontend sahifalari, komponentlar, routing va mavjud UI dizayni.
3. Backend routerlar, service, repository va permission tekshiruvlari.
4. PostgreSQL jadvallari, foreign key, indekslar va mavjud Alembic migratsiyalari.
5. Asosiy vositalar (Основные средства) modeli va CRUD API.
6. Участки va boshqa tashkiliy bo‘linmalar modeli.
7. Наряды-заказы, remont turlari, vazifalar va TMЦ bilan bog‘liqliklar.
8. Role, permission, user active/inactive va JWT tekshiruvlari.
9. Отчёты moduli va probeg saqlanishi.
10. Filtrlar, qidiruv, pagination, eksport va mavjud testlar.
11. Uch tilli tarjima mexanizmi mavjud yoki mavjud emasligi.
12. docs/HANDOFF.md, PROJECT.md, README.md va boshqa loyiha hujjatlari.
Topshiriq
Quyidagi 10 ta talabni mavjud tizim bilan solishtir:
- O‘zbek lotin, o‘zbek kirill va rus tillarida barcha ma’lumotlarni ko‘rsatish.
- Asosiy vosita turlari uchun boshqariladigan spravochnik.
- Asosiy vosita statuslari uchun boshqariladigan spravochnik.
- Asosiy vositalar sahifasida interaktiv statistik kartalar.
- Istalgan chuqurlikdagi tashkiliy ierarxiya.
- Наряд-заказ, remont, vazifalar va TMЦning tushunarli ko‘rinishi.
- Har bir rol uchun sahifa va amal bo‘yicha granular permissionlar.
- Foydalanuvchini aktiv/noaktiv qilish.
- Hisobotlarda наряд-заказ ochilgan vaqtdagi probeg.
- Barcha kerakli sahifalarda qulay filtrlar.
Har bir talab uchun quyidagilarni ko‘rsat:
1. Mavjud implementatsiya.
2. Tegishli fayllar va aniq kod joylari.
3. Mavjud database jadvallari va bog‘liqliklar.
4. Nimalar tayyor, nimalar yetishmaydi.
5. Boshqa modullarga ta’siri.
6. Xavfsizlik va ma’lumotlarni yo‘qotish xavfi.
7. Amalga oshirish uchun tavsiya etilgan tartib.
8. Kerak bo‘ladigan testlar.
Natija formati
docs/IMPLEMENTATION_PLAN.md faylini yaratma yoki o‘zgartirma. Hozircha faqat audit hisobotini chatda chiqar.
Hisobot oxirida:
- Har bir talab uchun P0/P1/P2 ustuvorlik.
- Fayllar bo‘yicha taxminiy o‘zgarishlar ro‘yxati.
- Database migratsiyalari zarurati.
- Oldingi auditdagi tasdiqlangan va tasdiqlanmagan xulosalar.
- Birinchi bo‘lib bajarilishi kerak bo‘lgan bosqich.
- Hali tekshirilmagan jihatlar.
Manba kodida ko‘rmagan narsangni mavjud deb aytma. Testni ishga tushirmagan bo‘lsang, test o‘tdi deb yozma. Auditni tugatgach, kodni o‘zgartirmasdan to‘xta.




0-bosqichdan keyin: audit natijasini menga yuborsangiz, promptlar loyihaning haqiqiy fayllariga mos kelishini tekshirish mumkin. Lekin hozirgi qolgan promptlar ham agentga repositoryni avval tekshirish va taxmin qilmaslik talabini beradi.

1-PROMPT. Uch tilni butun tizimga joriy qilish
Bu eng muhim asoslardan biri. Faqat menyu va sarlavhalar tarjima qilinishi yetarli emas. Masalan, asosiy vosita nomi, statusi, korxona, sex, remont turi, bajarilgan ish va material nomlari ham tanlangan tilda ko‘rinishi kerak.
TOIR — 1-BOSQICH: TO‘LIQ UCH TILLI LOCALIZATION
Maqsad
Butun TOIR tizimida uchta tilni to‘liq joriy qil:
1. O‘zbek tili — lotin alifbosi: uz-Latn.
2. O‘zbek tili — kirill alifbosi: uz-Cyrl.
3. Rus tili: ru.
1. Avval arxitekturani tekshir
Mavjud i18n kutubxonasi, Next.js App Router, frontend state, API response va database modellarini o‘rgan. Mavjud ishlaydigan mexanizm bo‘lsa, uni asossiz almashtirma.
2. Tilni boshqarish
- Interfeysda til almashtirgich bo‘lsin.
- Tanlangan til sahifalar o‘rtasida saqlansin.
- Sahifa yangilanganda tanlangan til yo‘qolmasin.
- Foydalanuvchi profili bilan bog‘lash imkoniyatini hisobga ol.
- Til qiymatlarini faqat ruxsat etilgan uchta variant bilan chekla.
- Server va frontend bir xil tilni izchil qo‘llasin.
3. Interfeys tarjimalari
Quyidagilarning hammasini tarjima qil:
- Menyu, sahifa nomlari va tugmalar.
- Formadagi label, placeholder va tooltip.
- Validatsiya va xatolik xabarlari.
- Loading, empty state va confirmation dialoglar.
- Jadval ustunlari, filtrlar va pagination.
- Dashboard, kartalar, diagramma legendalari.
- Login, foydalanuvchi boshqaruvi va permission interfeysi.
- Hisobotlar, eksport sarlavhalari va bildirishnomalar.
Kod ichida foydalanuvchiga ko‘rinadigan qattiq yozilgan matnlarni qidir.
4. Dinamik ma’lumotlar
Database ichidagi biznes ma’lumotlari uchun tarjima arxitekturasini ishlab chiq.
Asosiy vosita turlari, statuslar, tashkiliy bo‘linmalar, remont turlari, vazifalar va TMЦ nomenklaturasi uchala tilda ko‘rsatilishi kerak.
Mavjud schema va loyihaga mos quyidagi usullardan birini tanla:
- Har bir obyekt uchun alohida name_uz_lat, name_uz_cyrl, name_ru kabi maydonlar.
- Yoki normalizatsiyalangan tarjima jadvallari.
Usulni tanlashdan oldin mavjud ma’lumotlar, API, SQLAlchemy modellari va kelajakdagi kengayish imkoniyatini hisobga ol.
Foydalanuvchi kiritadigan erkin matnlar uchun avtomatik tarjimani haqiqiy tarjima deb ko‘rsatma. Agar uchala til uchun qiymat mavjud bo‘lmasa, belgilangan fallback siyosatini qo‘lla va tarjima yetishmayotganini administratorga ko‘rsat.
Eski ma’lumotlar uchun migratsiya rejasini tuz. Mavjud qiymatlarni o‘chirma va noto‘g‘ri tarjimalarni avtomatik yaratma.
5. Backend va API
- API tanlangan til bo‘yicha lokalizatsiyalangan ma’lumot qaytarsin.
- Bir obyektning identifikatori til almashganda o‘zgarmasin.
- Filter va sort lokalizatsiyalangan maydonlar bilan to‘g‘ri ishlasin.
- Backend xatoliklari foydalanuvchiga tarjima qilinadigan kod yoki xavfsiz xabar orqali uzatilsin.
- Ichki loglar va diagnostika uchun zarur texnik ma’lumotlar yo‘qolmasin.
6. Testlar
Uchala til bo‘yicha:
- Barcha sahifalar.
- CRUD formalar.
- Jadval va filtrlar.
- API response.
- Validation xatolari.
- Database migratsiyasi.
- Eksport va hisobotlar.
- Bo‘sh tarjima va fallback holatlari.
Qabul mezonlari
1. Har bir sahifada uchala tilga o‘tish ishlaydi.
2. Menyu emas, dinamik biznes ma’lumotlari ham tilga mos chiqadi.
3. Til almashtirish obyektlarni yoki ularning identifikatorlarini o‘zgartirmaydi.
4. Hardcoded matnlar inventarizatsiyasi tuzilgan.
5. Migratsiyalar va testlar tekshirilgan.
6. Ishlab turgan ma’lumotlar yo‘qolmagan.
Avval kodni o‘rgan, keyin o‘zgartirishlarni amalga oshir. Yakunda fayllar, migratsiyalar, testlar va qolgan kamchiliklarni hisobot qil.




Muhim: agar tizimda allaqachon ko‘p ruscha yoki o‘zbekcha yozuvlar bo‘lsa, ularni faqat avtomatik transliteratsiya qilish to‘liq tarjima hisoblanmaydi. Lotin va kirill yozuvi boshqa, rus tiliga tarjima esa boshqa masala.

2-PROMPT. Asosiy vosita turlari va statuslari spravochnigi
TOIR — 2-BOSQICH: ОСНОВНЫЕ СРЕДСТВА SPRAVOCHNIKLARI
Maqsad
Asosiy vositalar turlari va statuslarini mustaqil boshqariladigan spravochniklarga aylantir.
1. Avval mavjud tizimni tekshir
Asosiy vositalar modeli, database jadvallari, API, formalar, filtrlar, hisobotlar va mavjud enum/reference qiymatlarini o‘rgan. Takroriy spravochnik yaratma.
2. Asosiy vosita turlari
Administrator yoki ruxsat berilgan foydalanuvchi:
- Yangi tur qo‘sha olsin.
- Tur nomlarini uch tilda kiritsin.
- Mavjud turni tahrirlay olsin.
- Turni o‘chirish yoki foydalanishdan chiqarish imkoniga ega bo‘lsin.
- Tur bo‘yicha qidirish va filtrlash imkoniga ega bo‘lsin.
3. Asosiy vosita statuslari
Xuddi shu CRUD imkoniyatlarini statuslar uchun yarat:
- Uch tilda nom.
- Zarur bo‘lsa, qisqa kod.
- Faollik holati.
- UI rang belgisi, agar loyihadagi dizayn tizimi qo‘llab-quvvatlasa.
- Statusning ishlatilish qoidalari.
- Asosiy vositalar ro‘yxati va filterlarda foydalanish.
Mavjud biznes statuslarini tekshirmasdan yangilarini o‘zboshimchalik bilan belgilama.
4. O‘chirish xavfsizligi
Agar tur yoki status mavjud asosiy vositalarda ishlatilayotgan bo‘lsa:
- Uni oddiy DELETE bilan yo‘qotma.
- Foreign key va mavjud ma’lumotlar yaxlitligini saqla.
- Zarur bo‘lsa, is_active=false yoki archived_at orqali arxivlashni qo‘lla.
- Ishlatilayotgan obyektlar sonini ko‘rsat.
- Foydalanuvchiga bog‘liq yozuvlar borligi haqida aniq xabar ber.
- Hard delete faqat foydalanilmagan yozuvlar uchun va loyihadagi siyosatga muvofiq ruxsat etilsin.
5. Backend
- CRUD API yarat yoki mavjudini to‘ldir.
- Schema validation qo‘sh.
- Nomlar bo‘sh bo‘lmasin.
- Uchala tildagi nomlar uchun belgilangan siyosatga rioya qil.
- Duplicate qiymatlar va unique constraintlarni tekshir.
- Ruxsatsiz foydalanuvchi yaratish, tahrirlash yoki o‘chira olmasin.
- Frontenddagi tugmani yashirishni xavfsizlik chorasi deb hisoblama; backend ham ruxsatni tekshirsin.
6. Frontend
Alohida boshqaruv interfeysini yarat yoki mavjud spravochniklar sahifasiga qo‘sh:
- Jadval.
- Qidiruv va status filtri.
- Qo‘shish/tahrirlash modal yoki sahifasi.
- O‘chirishdan oldin tasdiqlash.
- Foydalanilayotgan qiymatlar uchun ogohlantirish.
- Loading, empty va error holatlari.
- Uch til va light/dark theme bilan mos dizayn.
7. Testlar
CRUD, duplicate, bo‘sh qiymat, ruxsat, foydalanilayotgan yozuvni o‘chirish va migratsiya holatlarini tekshir.
Qabul mezonlari
- Asosiy vosita turi va statusini kodni o‘zgartirmasdan UI orqali boshqarish mumkin.
- Boshqa jadvallardagi bog‘lanishlar buzilmaydi.
- Uchala til ishlaydi.
- Barcha o‘zgartirishlar server tomonda permission bilan himoyalangan.
Mavjud ma’lumotlarni saqla. Migratsiyani avtomatik productionda bajarma.





3-PROMPT. Участки spravochnigini dinamik ierarxiyaga aylantirish
Bu oddiy dropdownni almashtirish emas. Keyinchalik yangi korxona, sex, uchastka, xizmat yoki boshqa ichki bo‘linma qo‘shish mumkin bo‘lishi kerak.
TOIR — 3-BOSQICH: DINAMIK TASHKILIY IERARXIYA
Maqsad
Qattiq belgilangan Участки strukturasini cheksiz yoki oqilona chegaralangan chuqurlikka ega tashkiliy daraxtga aylantir.
Misol:
AGMK
└── Korxona A
├── Sex 1
│   ├── Uchastka 1
│   └── Uchastka 2
└── Xizmat 1
└── Bo‘linma 1
Bu faqat namuna. Real tashkilot nomlari va mavjud ma’lumotlarni repository/database orqali aniqlab ol.
1. Database modeli
Mavjud Участки jadvali va barcha foreign keylarni o‘rgan. Quyidagi xususiyatlarga ega modelni loyihala:
- id
- parent_id — yuqori bo‘linma identifikatori
- Uch tildagi nom
- Bo‘linma turi yoki category
- Kod, agar zarur bo‘lsa
- is_active
- sort_order, agar zarur bo‘lsa
- Yaratilgan va yangilangan vaqt
Mavjud arxitekturaga mos bo‘lsa, organization_units kabi umumiy jadvaldan foydalan. Biroq mavjud ma’lumotlar va bog‘lanishlarni tekshirmasdan eski Участки jadvalini o‘chirib yuborma.
2. Ierarxiya qoidalari
- Yuqori bo‘linma bo‘lmagan ildiz obyektlarini qo‘llab-quvvatla.
- Istalgan amaliy chuqurlikdagi bo‘linmalarni yaratish mumkin bo‘lsin.
- Obyekt o‘ziga parent bo‘la olmasin.
- Parent tanlashda siklik bog‘lanishlar bloklansin.
- O‘chirish yoki ko‘chirishda farzand bo‘linmalar va bog‘langan asosiy vositalar, narяд-заказlar hamda foydalanuvchilar hisobga olinsin.
- Ishlatilayotgan bo‘linmalarni xavfsiz arxivlash imkonini ber.
- O‘chirilgan yoki nofaol bo‘linmalar tarixiy hujjatlardan yo‘qolmasin.
3. Interfeys
Участки spravochnigini ierarxik boshqaruv sahifasiga aylantir:
- Tree view yoki kengaytiriladigan daraxt.
- Bo‘linmalarni qo‘shish, tahrirlash va ko‘rish.
- Parent bo‘linmani tanlash.
- Bo‘linma turini tanlash.
- Aktiv/noaktiv holat.
- Uch tilli nomlar.
- Qidiruv.
- Daraxt bo‘yicha filtrlash.
- Bo‘linmani ko‘chirishdan oldin tasdiqlash va ta’sirini ko‘rsatish.
Agar mavjud dizayn tizimi qo‘llasa, jadval va daraxt ko‘rinishi o‘rtasida almashish imkonini ber.
4. Boshqa modullarga ta’siri
Quyidagilarning barchasini tekshir va kerak bo‘lsa yangila:
- Asosiy vositalar.
- Foydalanuvchi va uning bo‘linmasi.
- Наряды-заказы.
- Remont va vazifalar.
- TMЦ harakati.
- Dashboard.
- Hisobotlar.
- Filterlar va API querylar.
- Role-based data scope.
Bo‘linma filtri tanlangan bo‘linmaning o‘zini va, biznes qoidasi talab qilsa, uning barcha ichki bo‘linmalarini qamrab olishi kerak.
5. Backend va xavfsizlik
- Parent mavjudligini tekshir.
- O‘ziga yoki o‘z avlodiga parent bo‘lishni blokla.
- Bo‘linma scope bo‘yicha ruxsatlarni backendda tekshir.
- Frontend yuborgan parent ID yoki unit IDga ko‘r-ko‘rona ishonma.
- Transaction va referential integrityni saqla.
6. Migratsiya
Mavjud uchastkalarni yangi modelga moslashtirish rejasini tuz. Avval eski va yangi IDlar orasidagi mappingni ko‘rsat. Noaniq ma’lumotlar uchun taxminiy parentni avtomatik belgilama. Migratsiya dry-run va rollback rejasi bo‘lsin.
Qabul mezonlari
- Administrator yangi tashkiliy darajalarni kod yozmasdan qo‘sha oladi.
- Barcha bog‘langan modullar to‘g‘ri bo‘linmani ko‘rsatadi.
- Sikl va noto‘g‘ri parent bloklanadi.
- Tarixiy yozuvlar saqlanadi.
- Uch til, filtrlar va permissionlar ishlaydi.
Avval database va bog‘liqliklarni xaritalab, keyin implementatsiya qil.





4-PROMPT. Asosiy vositalar sahifasini vizual va interaktiv qilish
TOIR — 4-BOSQICH: ОСНОВНЫЕ СРЕДСТВА DASHBOARD VA INTERAKTIV KARTALAR
Maqsad
Asosiy vositalar sahifasini ma’lumotni tez tushunish, kerakli obyektni topish va holat bo‘yicha filtrlashga qulay qil.
1. Avval ma’lumotlarni tekshir
Asosiy vositalar jadvalidagi haqiqiy ustunlarni, statuslar va turlarni, ierarxik bo‘linmalarni va API imkoniyatlarini o‘rgan. Mavjud bo‘lmagan qiymatlarni taxmin qilib ko‘rsatma.
2. Statistik kartalar
Ma’lumotlar bazasi imkoniyatiga qarab quyidagi kartalarni ko‘rib chiq:
- Jami asosiy vositalar.
- Aktiv vositalar.
- Nofaol vositalar.
- Remontdagi vositalar, agar bu holat ishonchli manbada mavjud bo‘lsa.
- Turlar bo‘yicha taqsimot.
- Statuslar bo‘yicha taqsimot.
- Korxona/sex/uchastka bo‘yicha taqsimot.
Faqat real va aniqlangan biznes ma’lumotlariga asoslangan kartalarni yarat. Bir xil obyekt bir nechta kartada sanalganda bu ma’noni aniq belgilab qo‘y.
3. Kartalarning ishlashi
- Har bir tegishli karta bosilganda jadval filtrlansin.
- Faol karta vizual ravishda ajralib tursin.
- Boshqa filtrlar bilan birgalikda ishlasin.
- Bir kartadan ikkinchisiga o‘tilganda eski filtrning saqlanish yoki bekor bo‘lish qoidasi tushunarli bo‘lsin.
- Filtrlarni tozalash tugmasi bo‘lsin.
- URL query parametrlaridan foydalanish mavjud arxitekturaga mos bo‘lsa, filtr holatini URLda saqla.
- Jadval natijasi va kartadagi sonlar bir xil backend query mantig‘iga asoslangan bo‘lsin.
4. Dizayn
- Light va dark theme.
- Hover, focus va active holatlari ikkala temada ham yaqqol ko‘rinsin.
- Faqat rang bilan farqlashga tayanma; ikonka, matn va border holatlarini ham qo‘lla.
- Klaviatura orqali foydalanish imkoniyati.
- Mobil va desktop layout.
- Kartalar ma’lumotni ortiqcha bezamasdan tushuntirsin.
- Mavjud UI kutubxonasi va dizayn tizimini saqla.
5. Jadval va filtrlar
Asosiy vositalar sahifasida haqiqatan mavjud maydonlarga mos:
- Matnli qidiruv.
- Tur.
- Status.
- Korxona/sex/uchastka.
- Aktivlik.
- Boshqa muhim atributlar.
Filtrlar birgalikda ishlasin. Backendda pagination mavjud bo‘lsa, uni buzma. Jami natijalar soni va sahifalashni aniq ko‘rsat.
6. Testlar
- Har bir karta to‘g‘ri filtrni qo‘llashi.
- Filtrlar kombinatsiyasi.
- Karta bosish va tozalash.
- Light/dark theme.
- Mobil ko‘rinish.
- Permissionga ega bo‘lmagan foydalanuvchi.
- Bo‘sh ma’lumot va API xatolari.
Qabul mezonlari
Kartadagi sonlar va jadval natijalari mos bo‘lsin. Karta bosilganda tegishli ro‘yxat ko‘rinsin. Hover va focus holatlari ikkala temada ham tushunarli bo‘lsin.





5-PROMPT. Наряды-заказы, remont, vazifalar va TMЦ
Bu modulda foydalanuvchi bitta narяд-заказni ochganda, qaysi asosiy vosita ta’mirlanayotgani, qanday remont yoki xizmat ko‘rsatilayotgani, qanday vazifalar bajarilgani va qanday material sarflangani tushunarli ko‘rinishi kerak.
TOIR — 5-BOSQICH: НАРЯДЫ-ЗАКАЗЫ, REMONT, ISHLAR VA TMЦ
Maqsad
Наряд-заказ ma’lumotlarini biznes jarayoni bo‘yicha mantiqiy va vizual ierarxiyada ko‘rsat.
1. Mavjud modelni o‘rgan
Work order, asosiy vositalar, remont turi, xizmat turi, ish vazifalari, TMЦ nomenklaturasi, ombor chiqimi, miqdor, birlik, qiymat, xodimlar va statuslar orasidagi mavjud bog‘lanishlarni aniqlab ol.
Mavjud jadval va APIlar bilan tanishmasdan yangi parallel tizim yaratma.
2. Наряд-заказ tafsilotlari sahifasi
Ma’lumotlar mavjudligiga qarab sahifani quyidagi mantiqiy qismlarga ajrat:
A. Umumiy ma’lumot:
- Наряд-заказ raqami.
- Ochilgan sana va vaqt.
- Joriy status.
- Mas’ul bo‘linma.
- Mas’ul xodim.
- Ustuvorlik, agar mavjud bo‘lsa.
B. Asosiy vosita:
- Nomi va inventar raqami.
- Turi.
- Joriy status.
- Bo‘linma.
- Ochilish paytidagi probeg, agar saqlangan bo‘lsa.
C. Remont yoki xizmat:
- Remont turi yoki xizmat nomi.
- Sabab yoki nuqson tavsifi.
- Rejalashtirilgan ishlar.
- Bajarilgan ishlar.
- Ishning holati va sanalari.
D. Vazifalar:
- Vazifa nomi.
- Mas’ul shaxs.
- Status.
- Reja va fakt sanalari.
- Bajarilganlik holati.
- Faqat mavjud modelda saqlanadigan ma’lumotlarni ko‘rsat.
E. TMЦ:
- Material yoki nomenklatura nomi.
- Kod.
- O‘lchov birligi.
- Rejalashtirilgan miqdor.
- Haqiqiy sarflangan miqdor.
- Qaytarilgan miqdor, agar modelda mavjud bo‘lsa.
- Ombor yoki hujjat manbasi.
- Narx va summa, agar mavjud va ruxsat etilgan bo‘lsa.
F. Tarix:
- Status o‘zgarishlari.
- Ishlar bo‘yicha o‘zgarishlar.
- TMЦ operatsiyalari.
- Kim va qachon o‘zgartirgani, agar audit trail mavjud bo‘lsa.
3. Vizual ierarxiya
- Umumiy ma’lumotni ixcham summary blokda ko‘rsat.
- Remont, vazifalar va TMЦni alohida section yoki tablarda joylashtir.
- Vazifalar ketma-ketligi va statuslarini tushunarli ko‘rsat.
- TMЦni alohida jadvalda chiqar.
- Yirik sahifada zarur bo‘lsa accordion yoki tablardan foydalan.
- Light/dark theme va uch tilli lokalizatsiyani saqla.
- Bo‘sh bo‘limlarni noto‘g‘ri ma’lumot bilan to‘ldirma.
4. Data integrity
- Vazifa yoki TMЦ yozuvini noto‘g‘ri наряд-заказga bog‘lashga yo‘l qo‘yma.
- Backendda foreign key va obyekt scope tekshiruvlarini bajargin.
- Rejalashtirilgan va haqiqiy miqdorlarni chalkashtirma.
- Ma’lumotlar yetishmasa, soxta qiymat ko‘rsatma.
- Mavjud biznes qoidalarini tekshirmasdan status o‘tishlarini o‘zgartirma.
- Tarixiy hujjatlarning ma’lumotlarini o‘chirib yuborma.
5. Filtrlar
Наряд-заказlar ro‘yxatida:
- Raqam bo‘yicha qidiruv.
- Sana oralig‘i.
- Asosiy vosita.
- Remont yoki xizmat turi.
- Status.
- Bo‘linma.
- Mas’ul shaxs.
- TMЦ yoki material bo‘yicha qidiruv, agar API arxitekturasi buni qo‘llab-quvvatlasa.
Filtrlarni server querylariga mos ravishda amalga oshir.
6. Testlar
- Narяд-заказ tafsilotlari.
- Vazifa va materiallar bilan bog‘lanish.
- Turli statuslar.
- Ruxsat va data scope.
- Uch til.
- Bo‘sh va xatolik holatlari.
- Filterlar kombinatsiyasi.
Qabul mezonlari
Foydalanuvchi bitta наряд-заказni ochganda, asosiy vosita, remont turi, vazifalar va sarflangan TMЦni bir-biridan aniq ajrata olsin. Barcha qiymatlar real backend ma’lumotlaridan olinsin.





6-PROMPT. Har bir rol uchun sahifa va amal bo‘yicha ruxsatlar
Bu xavfsizlik nuqtayi nazaridan eng muhim bosqichlardan biri. Frontendda checkbox qo‘yishning o‘zi yetarli emas: backend har bir himoyalangan amalni tekshirishi kerak.
TOIR — 6-BOSQICH: GRANULAR RBAC PERMISSION TIZIMI
Maqsad
Har bir rol uchun sahifa, funksiya va zarur bo‘lganda ma’lumot doirasi bo‘yicha ruxsatlarni boshqarish imkonini yarat.
1. Mavjud xavfsizlik modelini tekshir
Role, user, JWT, backend dependency, router, service va mavjud permission tekshiruvlarini o‘rgan. Mavjud rollarni tekshirmasdan qayta nomlama yoki o‘chirib yuborma.
2. Permission darajalari
Kamida quyidagi amallarni loyihaga mos ravishda ajrat:
- view
- create
- update
- delete
- export
- approve, agar tasdiqlash jarayoni mavjud bo‘lsa.
- manage_permissions
- manage_users
- manage_reference_data
Bularni barcha sahifalarga ko‘r-ko‘rona berma. Har bir modul uchun mantiqan kerakli amallarni aniqlab chiq.
Modullar misollari:
- Dashboard.
- Asosiy vositalar.
- Asosiy vosita turlari va statuslari.
- Tashkiliy ierarxiya.
- Наряды-заказы.
- Vazifalar va remont.
- TMЦ.
- Hisobotlar.
- Foydalanuvchilar.
- Spravochniklar.
- Sozlamalar.
3. Admin interfeysi
Ruxsat berilgan administrator quyidagilarni bajara olsin:
- Rolni tanlash.
- Sahifalar ro‘yxatini ko‘rish.
- Har bir sahifa uchun tegishli amallarga checkbox orqali ruxsat berish yoki cheklash.
- O‘zgarishlarni saqlashdan oldin umumlashtirilgan ro‘yxatni ko‘rish.
- O‘zgarishlarni bekor qilish.
- Ruxsatlar o‘zgarganini tushunarli tarzda ko‘rish.
Faqat UI emas, serverda permissionni saqlash va tekshirish mexanizmini ham yarat.
4. Backend xavfsizligi
- Har bir himoyalangan endpoint serverda ruxsatni tekshirsin.
- Default holatda ruxsat yo‘q bo‘lsin (deny by default).
- Noma’lum permission yoki noto‘g‘ri formatdagi so‘rov rad etilsin.
- Foydalanuvchi boshqa rolga o‘z-o‘zidan ruxsat bera olmasin.
- Oddiy administratorga o‘z vakolatidan tashqarida yuqori darajadagi ruxsatlarni berish imkonini bermagin.
- Eng yuqori darajadagi administrator ruxsatlarini himoya qil.
- Oxirgi faol super-administratorni bloklash yoki vakolatdan mahrum qilishni xavfsiz chekla.
- Foydalanuvchi faqat o‘ziga tegishli bo‘lmagan resurslarga murojaat qilganda ham object-level authorization tekshirilsin.
- Bo‘linma scope cheklovlari permissiondan alohida tekshirilsin.
- Frontend tugmasini yashirish backend ruxsat tekshiruvining o‘rnini bosmasin.
5. JWT va ruxsatlar keshi
Agar permissionlar JWT ichiga joylangan bo‘lsa, ruxsat o‘zgarganda eskirgan token bilan eski huquqlar saqlanib qolmasligini ta’minla. Mavjud arxitekturaga mos ravishda:
- server tomondan joriy permissionlarni tekshirish;
- token versiyasi;
- sessiyani bekor qilish;
- yoki xavfsiz cache invalidation.
Eng mos variantni mavjud auth tizimiga qarab tanla.
6. Audit va monitoring
Permission o‘zgarishlari uchun imkon qadar:
- Kim o‘zgartirdi.
- Qaysi rol o‘zgartirildi.
- Qaysi permission qo‘shildi yoki olib tashlandi.
- Vaqt.
- Natija.
Maxfiy token yoki parollarni logga yozma.
7. Testlar
- Ruxsatli va ruxsatsiz so‘rovlar.
- To‘g‘ridan-to‘g‘ri API chaqiruvi.
- Boshqa bo‘linma ma’lumotiga kirish.
- Eski JWT bilan murojaat.
- Permissionni boshqarish vakolati yo‘qligi.
- Oxirgi super-adminni himoyalash.
- Har bir muhim CRUD endpoint.
Qabul mezonlari
Permission cheklovi faqat interfeysda emas, backendda ham ishlaydi. Ruxsatsiz API so‘rovlari server tomonidan rad etiladi. Testlar xavfsizlik qoidalarini tasdiqlaydi.
Mavjud auth mexanizmini o‘rganmasdan yangi parallel authorization tizimi yaratma. Xavfsizlikka oid muammolarni yakuniy hisobotda alohida ko‘rsat.





7-PROMPT. Foydalanuvchini aktiv/noaktiv qilish
TOIR — 7-BOSQICH: USER ACTIVE / INACTIVE BOSHQARUVI
Maqsad
Ruxsatli administrator foydalanuvchini o‘chirmasdan aktiv yoki noaktiv holatga o‘tkaza olsin.
1. Mavjud auth tizimini o‘rgan
User modeli, JWT, refresh token, login endpoint, session, role va mavjud audit mexanizmlarini tekshir.
2. Backend
Agar mavjud bo‘lmasa, user modeliga is_active kabi aniq status maydonini va kerakli migratsiyani qo‘sh.
- Yangi foydalanuvchilar uchun mavjud biznes qoidalariga mos default belgila.
- Nofaol foydalanuvchi login qila olmasin.
- Agar refresh token yoki sessiya mexanizmi bo‘lsa, noaktiv qilingan foydalanuvchining eskirgan sessiyalari ham bekor qilinsin yoki yaroqsiz holatga keltirilsin.
- Har bir himoyalangan endpoint joriy foydalanuvchi aktivligini tekshirsin.
- Faqat frontenddagi disabled tugmaga ishonma.
- Nofaol foydalanuvchining tarixiy yozuvlarini o‘chirib yuborma.
- Administrator o‘zini tasodifan bloklab qo‘yishiga qarshi xavfsiz qoidani qo‘lla.
- Oxirgi faol super-administrator noaktiv qilinmasin.
- Aktiv/noaktiv holatni o‘zgartirish uchun maxsus permission talab qil.
3. Frontend
Foydalanuvchilar sahifasida:
- Aktiv/noaktiv statusi.
- Status bo‘yicha filter.
- Aktivlashtirish va noaktiv qilish amali.
- O‘zgarishdan oldin tasdiqlash dialogi.
- Amal bajarilmasa tushunarli xatolik.
- Kim va qachon statusni o‘zgartirganini ko‘rsatish, agar audit ma’lumoti mavjud bo‘lsa.
4. Testlar
- Aktiv foydalanuvchi login qila oladi.
- Nofaol foydalanuvchi login qila olmaydi.
- Avval olingan JWT yoki refresh token orqali kirish siyosati to‘g‘ri ishlaydi.
- Ruxsatsiz foydalanuvchi statusni o‘zgartira olmaydi.
- Oxirgi super-admin himoyalangan.
- Tarixiy hujjatlar foydalanuvchi noaktiv qilinganda buzilmaydi.
Qabul mezonlari
Foydalanuvchini o‘chirmasdan bloklash mumkin. Nofaol foydalanuvchining kirishi backendda to‘xtatiladi va tarixiy ma’lumotlar saqlanadi.





8-PROMPT. Hisobotlarda narяд-заказ ochilgan paytdagi probeg
Bu yerda muhim farq bor: narяд-заказ ochilgan paytdagi probeg bilan asosiy vositaning hozirgi probegi bir xil narsa emas. Hozirgi qiymat keyinchalik o‘zgarishi mumkin, shuning uchun ochilish paytidagi qiymat alohida saqlanishi kerak.
TOIR — 8-BOSQICH: НАРЯД-ЗАКАЗ OCHILISHIDAGI PROBEGNI HISOBOTGA QO‘SHISH
Maqsad
Отчёты sahifasining Наряды-заказы bo‘limida har bir наряд-заказ uchun tegishli asosiy vositaning наряд-заказ ochilgan paytdagi probegini ko‘rsat.
1. Mavjud ma’lumot manbasini tekshir
- Asosiy vositalar modelini.
- Probeg yoki mileage qayerda saqlanishini.
- Wialon integratsiyasi mavjud bo‘lsa, mileage qaysi endpoint yoki telemetriya maydonidan kelishini.
- Наряд-заказ yaratilish vaqti va asosiy vosita bog‘lanishini.
- Hisobot endpointi va frontend jadvalini.
Agar tarixiy probeg allaqachon saqlansa, mavjud manbadan foydalan. Agar saqlanmasa, qaysi ishonchli manbadan olish mumkinligini aniqlab, reja tuz.
2. Qiymatni saqlash
Agar biznes talabi va mavjud schema tasdiqlasa, наряд-заказ ochilganda probeg snapshotini saqla.
Masalan, mavjud naming conventionga mos opening_mileage va zarur bo‘lsa opening_mileage_recorded_at maydonlari.
- Snapshot наряд-заказ ochilgan vaqtdagi qiymatni bildirishi kerak.
- Asosiy vositaning hozirgi probegi o‘zgarsa, snapshot o‘zgarmasin.
- Probeg mavjud bo‘lmasa, nol deb taxmin qilma.
- Qiymat manbasi va vaqti ma’lum bo‘lsa, ularni saqla.
- Kilometr yoki boshqa o‘lchov birligini aniq belgilab qo‘y.
- Manba qiymati ishonchsiz yoki eskirgan bo‘lsa, buni yashirma.
3. Tarixiy yozuvlar
Oldingi наряд-заказlar uchun tarixiy probegni keyinchalik olingan hozirgi qiymat bilan almashtirma.
Agar tarixiy telemetriya mavjud bo‘lsa, uni tiklash imkonini alohida bahola. Qiymatni ishonchli aniqlab bo‘lmasa, unknown yoki bo‘sh holatni saqla va hisobotda shunday ko‘rsat.
4. Hisobot interfeysi
Отчёты → Наряды-заказы jadvaliga:
- Asosiy vosita nomi yoki inventar raqami.
- Наряд-заказ raqami.
- Ochilgan sana.
- Ochilish paytidagi probeg.
- O‘lchov birligi.
- Zarur bo‘lsa, probegning manbasi yoki yozib olingan vaqti.
Ustun nomlarini uch tilda tarjima qil. Jadvalda ustun kengligi, mobil ko‘rinish va saralashni hisobga ol.
5. Filtr va eksport
Agar ma’lumot turi va biznes talabiga mos bo‘lsa:
- Sana oralig‘i.
- Asosiy vosita.
- Probeg oralig‘i.
- Bo‘linma.
- Наряд-заказ statusi.
Hisobot eksportida ham aynan shu snapshot qiymati chiqsin.
6. Validatsiya
- Manfiy probegni blokla, agar tizimda alohida asoslangan istisno bo‘lmasa.
- Noto‘g‘ri formatni qabul qilma.
- Katta qiymatlar uchun mos numeric turdan foydalan.
- Frontend yuborgan snapshotga ko‘r-ko‘rona ishonma.
- Snapshotni yaratishning yagona ishonchli server-side nuqtasini belgilab qo‘y.
7. Testlar
- Yangi наряд-заказ ochilganda snapshot.
- Asosiy vosita probegi keyinchalik o‘zgarganda snapshot saqlanishi.
- Probeg mavjud bo‘lmagan holat.
- Tarixiy ma’lumotlar.
- Hisobot va eksport mosligi.
- Ruxsatlar va filtrlar.
Qabul mezonlari
Hisobotdagi probeg наряд-заказ ochilgan paytdagi ishonchli qiymat bo‘lishi kerak. Keyingi o‘zgarishlar tarixiy qiymatni o‘zgartirmasligi shart.





9-PROMPT. Barcha kerakli sahifalarga qulay filtrlar
TOIR — 9-BOSQICH: GLOBAL FILTER UX VA SERVER-SIDE QIDIRUV
Maqsad
Loyihaning barcha muhim ro‘yxat sahifalarini qulay, izchil va samarali filtrlash imkoniyati bilan ta’minla.
1. Audit
Har bir list sahifani aniqlab chiq. Har bir sahifa uchun mavjud ustunlar, backend querylar, pagination, sort va permissionlarni tekshir.
Hamma sahifaga bir xil filtrlarni majburan qo‘shma. Faqat o‘sha ma’lumotga tegishli filtrlarni tanla.
2. Filtr imkoniyatlari
Ma’lumotga mos ravishda quyidagilarni qo‘llab-quvvatla:
- Matnli qidiruv.
- Sana oralig‘i.
- Status.
- Tur yoki kategoriya.
- Asosiy vosita.
- Tashkiliy bo‘linma va uning ichki bo‘linmalari.
- Mas’ul xodim.
- Remont turi.
- TMЦ nomenklaturasi.
- Probeg oralig‘i.
- Aktiv/noaktiv.
- Boshqa real biznes maydonlari.
3. UX talablari
- Filterlar aniq nomlangan bo‘lsin.
- Ko‘p filtr bo‘lsa, ixcham panel yoki ochiladigan advanced filters ishlat.
- Faol filtrlar chip yoki shunga o‘xshash tushunarli ko‘rinishda ko‘rsatilishi mumkin.
- Bitta filtrni alohida tozalash mumkin bo‘lsin.
- Barcha filtrlarni tozalash tugmasi bo‘lsin.
- Natijalar soni ko‘rsatilsin.
- Loading, empty va error holatlari bo‘lsin.
- Qidiruv matni kiritilganda ortiqcha API so‘rovlarini kamaytirish mexanizmini qo‘lla.
- Mobil va desktop ekranlarda qulay bo‘lsin.
- Light/dark theme va uch tilni qo‘llab-quvvatlasin.
4. Backend
- Katta jadvallarda qidiruv va filtrlar server tomonida bajarilsin.
- Pagination va sort backend bilan izchil ishlasin.
- Sort qilinadigan ustunlar whitelist orqali tekshirilsin.
- Noto‘g‘ri sana, ID, diapazon va parametrlar validatsiyadan o‘tsin.
- SQL injection xavfini oldini olish uchun ORM yoki parametrli querylardan foydalan.
- Har bir queryda permission va bo‘linma scope tekshirilsin.
- Filtrlar permission cheklovini chetlab o‘tmasin.
5. URL va holatni saqlash
Mavjud routing arxitekturasiga mos bo‘lsa, filtrlar URL query parametrlarida saqlansin. Bu qayta yuklash, bookmark va sahifani ulashishda yordam beradi.
Sahifalar o‘rtasida filter holati tasodifan aralashib ketmasin.
6. Samaradorlik
- Zarur indekslarni tekshir.
- Indeks qo‘shishdan oldin querylarni bahola.
- Keraksiz N+1 so‘rovlarni aniqlab, xavfsiz optimallashtir.
- Backend paginationni saqla.
- Barcha yozuvlarni birdan frontendga yuklab filtrlashga yo‘l qo‘yma.
7. Testlar
- Bitta filtr.
- Bir nechta filtr kombinatsiyasi.
- Filtrlarni tozalash.
- Sana chegaralari.
- Bo‘sh natija.
- Pagination va sort.
- Noto‘g‘ri parametr.
- Ruxsatsiz data scope.
- Uch til va mobil interfeys.
Qabul mezonlari
Filtrlar real backend natijalariga ta’sir qiladi, kombinatsiyada ishlaydi, pagination va permissionlarni buzmaydi. Qidiruv foydalanuvchiga tushunarli va izchil bo‘ladi.





10-PROMPT. Yakuniy integratsiya va xavfsizlik auditi
TOIR — 10-BOSQICH: YAKUNIY INTEGRATSIYA, REGRESSION VA SECURITY AUDIT
Rol
Senior QA Engineer, Security Engineer va Software Architect sifatida ishlaysan.
Maqsad
Oldingi bosqichlarda bajarilgan barcha o‘zgarishlarning birgalikda to‘g‘ri ishlashini tekshir.
1. Kod va Git
- Git status va diffni tekshir.
- O‘zgartirilgan fayllarni sanab chiq.
- Tasodifan o‘zgargan fayllarni aniqlagin.
- Secret yoki .env ma’lumotlari Git diffga tushmaganini tekshir.
- Bajarilmagan ishni bajarildi deb ko‘rsatma.
2. Database
- Alembic migratsiyalarining ketma-ketligini tekshir.
- Modellar va migratsiyalar mosligini tekshir.
- Foreign key, unique constraint va indekslarni tekshir.
- Eski ma’lumotlarni saqlash rejasini tekshir.
- Migration rollback imkoniyatini bahola.
- Production databasega ruxsatsiz ulanma va migratsiya bajarma.
3. Localization
Uchala til bo‘yicha:
- Barcha sahifalar.
- Dinamik spravochniklar.
- Asosiy vositalar.
- Tashkiliy ierarxiya.
- Наряд-заказ, remont, vazifalar va TMЦ.
- Foydalanuvchi boshqaruvi.
- Hisobotlar va eksport.
Hardcoded matnlar va tarjimasi yetishmayotgan ma’lumotlarni aniqlab chiq.
4. Permission va autentifikatsiya
- Har bir muhim endpoint uchun ruxsat tekshiruvi.
- Role va permission o‘zgarishlari.
- User active/inactive.
- JWT va refresh token.
- Tashkiliy scope.
- Nofaol obyektlar bilan ishlash.
- Ruxsatsiz API so‘rovlari.
- Admin vakolatlarini himoyalash.
5. Biznes jarayonlari
Quyidagi zanjirni tekshir:
1. Tashkiliy bo‘linma yaratish.
2. Asosiy vosita turi va statusini yaratish.
3. Asosiy vosita yaratish va uni bo‘linmaga bog‘lash.
4. Наряд-заказ ochish.
5. Remont yoki xizmat turini tanlash.
6. Vazifalarni ko‘rsatish.
7. TMЦ sarfini ko‘rsatish.
8. Ochilish paytidagi probegni saqlash.
9. Hisobotda narяд-заказ va probegni ko‘rsatish.
10. Bularning hammasini uch tilda ko‘rsatish.
11. Rolga qarab ruxsatlarni tekshirish.
12. Filtrlar va paginationni tekshirish.
Bu zanjirni test muhitida yoki xavfsiz mock testlarda tekshir. Ishlab turgan ma’lumotlarni o‘zgartirma.
6. Frontend va backend
- Lint.
- TypeScript type-check.
- Frontend build.
- Backend testlari.
- API schema tekshiruvi.
- Regression testlari.
- UI testlari, agar mavjud bo‘lsa.
Buyruqlarni ishga tushirishdan oldin loyiha ko‘rsatmalarini o‘rgan. Zarur dependency yoki xizmat yetishmasa, uni yashirma.
7. UI/UX
- Light/dark theme.
- Uch tilli interfeys.
- Kartalar va hover.
- Responsive dizayn.
- Jadval va filtrlar.
- Loading, empty va error holatlari.
- Accessibility va klaviatura boshqaruvi.
8. Yakuniy hisobot
Quyidagi formatda chiqar:
A. Bajarilgan ishlar.
B. O‘zgartirilgan fayllar.
C. Yaratilgan yoki o‘zgartirilgan migratsiyalar.
D. O‘tgan testlar — aniq buyruq va natija bilan.
E. O‘tmagan testlar — sabab bilan.
F. Hali bajarilmagan ishlar.
G. Aniqlangan xavfsizlik muammolari.
H. Production deploydan oldin bajarilishi zarur bo‘lgan ishlar.
I. Git diff va working tree holati.
J. Har bir 10 ta talabning holati: PASS, PARTIAL yoki FAIL.
Qat’iy talab
Audit davomida aniqlangan muammolarni yashirish yoki test natijalarini taxmin qilish mumkin emas. Production deploy, database migratsiyasi va ma’lumotlarni o‘zgartirish uchun alohida aniq ruxsat talab qilinadi.





Har bir bosqichdan keyin modelga yuboriladigan nazorat prompti
Ollama modeli ba’zan umumiy kod namunalarini berib, mavjud fayllarni tekshirmasdan “tayyor” deb aytishi mumkin. Shuning uchun har bir bosqich oxirida quyidagi promptni yuboring.
TOIR — BOSQICHNI TEKSHIRISH VA QABUL QILISH
Hozir bajarilgan bosqichni mustaqil tekshir. Oldingi javobingni dalil deb qabul qilma.
1. Haqiqatan o‘zgartirilgan fayllarni Git diff orqali ko‘rsat.
2. Yangi API endpointlar, database modellari va frontend komponentlari orasidagi bog‘lanishni tekshir.
3. Har bir talabni tegishli kod bilan solishtir.
4. Frontenddagi tugma backenddagi haqiqiy amalni bajarishini tekshir.
5. Permissionlar server tomonda tekshirilishini tasdiqla.
6. Uch tilli ma’lumotlar faqat menyuda emas, real biznes ma’lumotlarida ham ishlashini tekshir.
7. Migratsiya va mavjud ma’lumotlar xavfsizligini ko‘rib chiq.
8. Mavjud testlarni ishga tushir; ishga tushmagan testni PASS deb belgilama.
9. Muvaffaqiyatsiz testlarni tuzatish zarur bo‘lsa, sababini aniqlab, faqat joriy bosqich doirasida tuzat.
10. Boshqa bosqichga tegishli o‘zgarishlarni ruxsatsiz bajarma.
Har bir talab uchun PASS, PARTIAL yoki FAIL holatini ko‘rsat va dalil keltir.
Yakunida:
- O‘zgartirilgan fayllar.
- Ishga tushirilgan testlar va natijalar.
- Qolgan xatolar.
- Ma’lumotlar bazasi yoki xavfsizlik xavflari.
- Keyingi bosqichni boshlash mumkinmi yoki yo‘qmi.
Git diff, testlar va kod bilan tasdiqlanmagan ishni bajarildi deb e’lon qilma.