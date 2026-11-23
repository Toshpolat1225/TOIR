# Sirlarni almashtirish (CODEX CONF-01) — 2026-11-23

## Nima topildi
`gitleaks` butun git tarixini tekshirdi (237 commit). **HEAD toza** (sir saqlovchi fayl yo'q, `.env.example` faqat bo'sh qiymatlar), lekin **tarixda** quyidagilar qolgan:

| Nima | Qayerda / qachon | Xavf |
|---|---|---|
| Serverdan olingan `.env` nusxasi: `POSTGRES_PASSWORD`, `JWT_SECRET`, `WIALON_INGEST_TOKEN`, `WIALON_TOKEN` (va sozlamalar) | `local-backups/server-copy.env.local`, 7 ta commit, 2026-10-23 … 2026-11-10 (13-noyabrda olib tashlangan, tarixda qolgan) | **Yuqori.** Repo GitHub'ga yuborilgan (`origin`), shuning uchun sir oshkor bo'lgan deb hisoblanadi |
| Eski Supabase `anon` kaliti (JWT, `role: anon`) | eski skriptlar (2026-08-11), HEAD da yo'q | Past (anon kalit ommaviy bo'lishi mumkin); eski loyiha uchun |
| Google API kaliti | GTK saytidan saqlangan sahifalar (`gtk_page_*`, `*_files`), 2026-11-04 | Past: bu GTK'ning o'z kaliti, bizniki emas |

Sirlarning o'zi bu hujjatga va hech qaysi jurnalga yozilmagan.

## Nima qilish kerak (tartib bilan) — hammasini **siz** bajarasiz
Tarixdan faylni o'chirish sirni qaytarib olmaydi (klonlar va fork'lar saqlanib qoladi). **Asosiy yechim — sirlarni almashtirish.**

1. **GitHub**: repo `Toshpolat1225/TOIR` ochiqmi yoki yopiqmi, qarang (Settings → General). Ochiq bo'lsa, 2–5 ni zudlik bilan bajaring. Settings → Code security → *Secret scanning* ni yoqing.
2. **`JWT_SECRET`**: yangisini yarating, `.env` ga yozing, backendni qayta ishga tushiring. Hamma foydalanuvchi qayta kiradi (AD orqali).
   ```powershell
   python -c "import secrets; print(secrets.token_urlsafe(64))"
   ```
3. **`POSTGRES_PASSWORD`**: avval bazada o'zgartiring, keyin `.env` da.
   ```powershell
   docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "ALTER USER \"$POSTGRES_USER\" PASSWORD ''YANGI_PAROL''"'
   ```
   So'ng `.env` dagi `POSTGRES_PASSWORD` ni yangilab, `docker compose up -d backend backup` (postgres konteynerini qayta yaratmang: ma'lumot saqlanadi).
4. **`WIALON_INGEST_TOKEN`**: yangisini yarating, `.env` va Wialon'dagi qabul qilish (retranslator) sozlamasida almashtiring.
5. **`WIALON_TOKEN`**: Wialon'da eski tokenni bekor qiling (User settings → Tokens), yangisini chiqarib, `.env` ga yozing.
5b. **`SCALES_INGEST_TOKEN`** (ehtiyot chorasi): tarixda yo'q, lekin 2026-11-23 sessiyasida bitta test xatosi ushbu tokenning bir qismini (boshi va oxiri) jurnalga chiqarib yuborgan. Tarozi kollektori `.env` va Windows vazifasida yangilanadi.
6. **Tarixni tozalash (ixtiyoriy, sizning qaroringiz)**: faqat 2–5 dan keyin. `git filter-repo --path local-backups --invert-paths`, so'ng majburiy push. Bu hamma klonlarni buzadi; men buni bajarmayman (loyiha qoidalari).
7. Almashtirgandan keyin `gitleaks` ni qayta ishga tushirib, yangi kalitlar tarixda yo'qligini tasdiqlang.

## Qayta takrorlanmasligi uchun
- `.gitignore` ga `local-backups/`, `*.env.local`, `server-copy*` qo'shildi.
- Serverdan nusxa olinsa, repo papkasidan tashqarida saqlang.
