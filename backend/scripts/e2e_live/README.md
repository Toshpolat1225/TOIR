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

`python t11_map_verify.py` endi `/map/unplaced` ni ham tekshiradi (faqat GET); brauzer: `node browser/b05_map.mjs` (xarita) va `node browser/b06_unplaced.mjs` («Без координат» sahifasi).

`python t12_scales_verify.py` (faqat GET): tarozi endpointlari va vagonlar daftari (jami = reyslar yig'indisi, CSV, ruxsatlar); brauzer: `node browser/b07_scales.mjs` («Весовая» sahifasi, vagon → reyslar → CSV, telefon kengligi).

`node browser/b08_scales_cards.mjs`: boshqaruv markazidan vagon → sostav → lokomotiv kartochkalariga yurish, davr tugmalari, bog'lanmagan vagon, telefon kengligi. `t12` ga overview/kartochka izchillik tekshiruvlari qo'shilgan (yig'indilar daftar va holat bilan mos).

`python t13_map_history_verify.py` (faqat GET): `/map/history` (lokomotiv/vagon tarixi, izchillik, master 404); brauzer: `node browser/b09_map_history.mjs` (yangi karta, inspektor, tarix sahifasi, vaqt ползунки), `b05_map.mjs` yangi interfeysga moslandi.

`python t14_map_trains_verify.py` (faqat GET): `/map/trains` (lokomotiv boshida, GTK tartibi, haqiqiy o'lchamlar, oraliqlar, master); brauzer: `node browser/b10_map_icons.mjs` (ikonkalar, poyezd ikonkasi, zoom ≥16 da masshtabdagi poyezd).

## GPS (2026-11-17)
`t15_gps_verify.py` (faqat GET, 40 tekshiruv: Wialon↔GTK GPS, `/gps/*`, birlashgan xarita, rollar) va `browser/b11_gps.mjs` (Edge: 3 xarita, tafsilot, verdikt chiplari, telefon kengligi). Tarixni yuklash: `docker compose exec -d backend python -m app.cli gtk-gps-backfill --days 30`.

`t15_gps_verify.py` endi 70 tekshiruv (sabablar, facets, filtrlar, eksport, sog'lik, vagonlar); `browser/b12_gps_analytics.mjs` (Edge, 15). `docker compose exec backend python -m app.cli gps-analytics --days 31 --wagons` — tahlilni qayta hisoblash; `--days 14 --diff` — vagon nomzodlarini ledger bilan solishtirish (faqat o'qish).

## Ovozli buyruq markazi (2026-11-18)
`t16_assistant_verify.py` (64 tekshiruv: niyatlar uz/ru, raqam so'zlari, kontekst, ruxsat va uchastka, ikki bosqichli yozuv ZZTEST aktiv/xodim bilan, tezlik cheklovi; oxirida 429 sinovi uchun 61 s kutadi) va `browser/b13_assistant.mjs` (Edge, soxta mikrofon; t16 dan keyin `B13_WAIT_MS=65000` bering).

