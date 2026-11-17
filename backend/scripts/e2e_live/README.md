# Jonli tizimning end-to-end tekshiruvi (2026-11-16)

Natijalar: `docs/E2E_REPORT_2026-11-16.md`. Bu papkadagi skriptlar o'sha tekshiruvni qayta o'tkazish uchun.

## QOIDALAR (bajarilmasa jonli ma'lumot buziladi)
1. Yaratiladigan hamma narsa `ZZTEST` bilan boshlanadi (email `zztest-…@example.test`, inv `ZZTEST-…`, bo'lim `ZZTEST-…`).
2. **Muvaffaqiyatli bo'lishi mumkin bo'lgan yozuv-proba yubormang.** 2026-11-16 da «zararsiz» `PATCH /maintenance-settings` jonli sozlamani o'zgartirib yubordi. Ruxsat probasi faqat yo'q UUID (404) yoki bo'sh tana (422) yuboradi; xavfli tugmalar (`wialon/sync`, `gtk/sync`, `ml/analyze`) faqat ruxsati yo'q rollar uchun chaqiriladi.
3. Boshlashdan oldin zaxira + `snapshot.sql` (barcha jadvallar qator soni va statik jadvallar xeshi). Tugagach `zz_cleanup_all.sql`, so'ng `zz_leftovers.sql` (hammasi 0 bo'lishi kerak) va snapshotni qayta olib solishtirish.
4. Test akkaunt parollari faqat `zztest_creds.json` ga yoziladi (`{"admin": {"email": …, "password": …}, …}` rollar: admin, operator, master, management), hech qachon chop etilmaydi; tugagach fayl o'chiriladi.
5. Brute-force testi akkauntni 15 daqiqaga bloklaydi — uni oxirida o'tkazing.

## Tartib
```
# 1) marshrutlar va ruxsatlar matritsasi (konteyner ichida / bazadan)
docker compose exec -T -e PYTHONPATH=/app backend python /tmp/dump_routes.py > routes.json     # dump_routes.py ni avval docker cp qiling
docker compose exec -T postgres psql -U toir_local -d toir_local -At -F '|' -c "select permission_code, max(granted::int) filter (where role='admin'), max(granted::int) filter (where role='operator'), max(granted::int) filter (where role='master'), max(granted::int) filter (where role='management') from role_permissions group by 1 order by 1" > matrix.txt
# 2) vaqtinchalik akkauntlar (zz_setup.py /tmp/zz_creds.json ni o'qiydi) -> zz_ids.json
# 3) testlar
python t01_auth_security.py      # kirish, tokenlar, sarlavhalar (oxirida: brute-force)
python t02_rbac.py admin operator master management
python t04_maintenance_flow.py   # ТО oqimi (91 tekshiruv)
python t11_map_verify.py        # xarita endpointi (faqat GET, 19 tekshiruv)
python t10_fixall_verify.py      # HTTPS, refresh-token qayta ishlatilishi, sozlama oralig'i, departament, bo'lim qo'riqchisi, unforecasted (32 tekshiruv; TOIR_ROOT_CERT=toir-local-root.crt)
python t05_get_sweep.py ; python t06_users_mileage.py ; python t08_misc_crud.py ; python t09_load.py
node browser/b01_browser_sweep.mjs   # haqiqiy brauzer (Edge), barcha sahifa va rollar
# 4) tozalash
docker compose exec -T postgres psql -U toir_local -d toir_local < zz_cleanup_all.sql
docker compose exec -T postgres psql -U toir_local -d toir_local < zz_leftovers.sql
```
`zz_lib.py` dagi `BASE`/`REPO` va `browser/*.mjs` dagi `SC`/`BASE` yo'llarini o'z muhitingizga moslang.

`dq.sql` va `wagons.sql` — faqat o'qiydigan ma'lumot sifati tekshiruvlari.
