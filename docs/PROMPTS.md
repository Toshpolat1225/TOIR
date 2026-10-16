# TOIR — keyingi vazifalar

Har vazifa oldidan `docs/HANDOFF.md`, kerakli `PROJECT.md` bo'limlari va tegishli kodni o'qi.
Serverga SSH qilma; real deploy, DB va brauzer tekshiruvlarini faqat foydalanuvchi ruxsat bergandan keyin bajar.
Maxfiy qiymatlarni ko'rsatma, commit qilma, tekshirilmagan narsani "o'tdi" deb yozma.

## P-T9 — ML worker

```
PROJECT.md 13-bo'limdagi ML xatti-harakatini FastAPI backend ichida worker sifatida amalga oshir.
- Trigger: nariyad `completed` bo'lganda background task.
- TMC sarf anomaliyasi: repair kind + section bo'yicha tarix (ko'pi bilan 200, kamida 3);
  z > 2 yoki |og'ish| > 30%; severity critical/high/medium; probability=min(z/4,1).
- RUL: LinearRegression; failure_prob = 1 − exp(−kunlar_oxirgi_ТО_dan/o'rtacha_interval);
  chegaralar 0.7/0.4; qolgan km <500 → critical.
- Health score: (1−p)×100 − min(anomaliya_30kun×5,20) − min(ТО'siz_kunlar/30×5,15).
- Natijalarni ai_insights va fixed_assets (failure_probability, health_score,
  predicted_failure_km, last_ml_update) ga yoz.
- Diesel aktivlari ham tahlilga kirsin. Yo'q `--listen` CLI variantini hujjatlashtirma.
- Qattiq URL/kalit ishlatma. Zarur bo'lsa ML dependency'leri alohida compose servisi bo'lsin.
- Endpointlar: POST /ml/analyze (admin), GET /ml/insights.
- Sintetik testlar: anomaliya, RUL, kam tarixda insight yozilmasligi.
```

## P-T10 — Production qotirish

```
1. Frontend multi-stage Dockerfile: standalone output, non-root user.
2. Caddy yoki Nginx proxy: faqat proxy porti tashqariga ochiq; /api va /ws backend'ga,
   qolgan yo'llar frontend'ga. HTTPS domen bo'lmasa, sertifikat usulini oldin tasdiqlat.
3. Login limiter'ni process xotirasidan Redis yoki PostgreSQL'ga ko'chir.
4. Xavfsizlik headerlari, CORS production domenlari bilan; API docs env orqali boshqarilsin.
5. pg_dump backup/rotatsiya va tiklash yo'riqnomasi.
6. GitHub Actions: backend test, frontend tsc/lint/build va Docker build.
7. README'ni noldan o'rnatish hamda nosozliklarni tuzatish bo'yicha yangila.
Deploy yoki server tekshiruvi uchun foydalanuvchi ruxsati kerak.
```
