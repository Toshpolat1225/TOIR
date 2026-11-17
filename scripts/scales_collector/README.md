# TOIR — tarozi (Vesovoy) kollektori

Ikki tarozi kompyuteridagi `Bridge_Scale.mdb` ni **faqat o'qish** rejimida o'qiydi va yangi/o'zgargan qatorlarni TOIR ga yuboradi
(`POST /api/v1/scales/ingest`). Tarozi kompyuteriga hech narsa yozmaydi. Arxitektura: `docs/SCALES_ARCHITECTURE.md`.

Nega Windows'da: Access ODBC drayveri va SMB1 ulanish ma'lumoti (Windows Credential Manager) shu kompyuterda; Linux konteynerlarda yo'q.

## Bir martalik sozlash

**[PC]** (TOIR ishlayotgan kompyuter, PowerShell, loyiha papkasida) token yaratish. Qiymat ekranga chiqmaydi:
```powershell
cd C:\Users\okmkh\OneDrive\Documents\GitHub\TOIR
$t = [Convert]::ToBase64String((1..32 | ForEach-Object { [byte](Get-Random -Maximum 256) }))
Add-Content -Path .env -Value "`nSCALES_INGEST_TOKEN=$t"
[Environment]::SetEnvironmentVariable("SCALES_INGEST_TOKEN", $t, "User")
$env:SCALES_INGEST_TOKEN = $t
```
Keyin backend ni tokenni o'qiydigan qilib qayta yarating (migratsiya `0034_scales` allaqachon qo'llangan):
```powershell
docker compose up -d --no-deps --force-recreate backend
```

Tarozi kompyuterlariga ulanish ma'lumoti Credential Manager'da bo'lishi kerak (bir marta, parol faylga yozilmaydi):
```powershell
cmdkey /add:192.168.19.93 /user:LOGIN
cmdkey /add:192.168.19.97 /user:LOGIN
```
(`/pass` ni yozmasangiz parol so'raladi.)

`pyodbc` kerak: `python -m pip install pyodbc` (qaysi Python bilan ishlasangiz, shunisiga; loyiha `.venv` ni yoqqan bo'lsangiz ham bo'ladi). `install_task.ps1` yo'q bo'lsa o'zi o'rnatadi.

## Tekshirish va birinchi yuklash
```powershell
python scripts\scales_collector\collector.py --check              # ikkala tarozi ulanishi (hech narsa yuborilmaydi)
python scripts\scales_collector\collector.py --backfill-archives   # 2025-01 … oxirgi arxiv (bir marta, takrorlansa zarar yo'q)
python scripts\scales_collector\collector.py --backfill-live       # jonli bazadagi hamma narsa (2025-01-01 dan)
```
Hammasi takrorlanuvchi (idempotent): kalit `(tarozi, qator id)`; o'zgarmagan qator tegilmaydi.

## Doimiy ishlash
```powershell
powershell -ExecutionPolicy Bypass -File scripts\scales_collector\install_task.ps1
```
- `TOIR-Scales-Collector`: tizimga kirganda ishga tushadi, har 60 soniyada bir marta o'qiydi, to'xtasa o'zi qayta ishga tushadi.
- `TOIR-Scales-Rescan`: har kuni 03:30 da oxirgi 3 kunni qayta o'qiydi (operator keyin tuzatgan qatorlar uchun).
- Log: `%LOCALAPPDATA%\toir_scales\collector.log`, holat: `%LOCALAPPDATA%\toir_scales\state.json`.
- Eslatma: vazifa shu Windows foydalanuvchisi tizimga kirgan paytda ishlaydi (Credential Manager shu foydalanuvchiniki).

## Muhit o'zgaruvchilari
`SCALES_INGEST_TOKEN` (majburiy), `TOIR_URL` (standart `https://192.168.28.104`), `TOIR_CA_FILE` (PEM; standart: loyiha ildizidagi `toir-local-root.crt`),
`SCALES_POSTS` (standart `93=192.168.19.93,97=192.168.19.97`).

## Xavfsizlik
- Token va parol hech qachon logga yozilmaydi.
- Ulashma uchun faqat o'qish huquqli alohida akkaunt ishlatish tavsiya etiladi (shaxsiy akkaunt emas).
- TOIR tomonida token yo'q bo'lsa `/scales/ingest` yopiq (401).
