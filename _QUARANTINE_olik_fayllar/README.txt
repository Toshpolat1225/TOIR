KARANTIN: o'lik deb gumon qilingan fayllar (2026-11-23). Hech narsa o'chirilmagan, faqat shu yerga ko'chirilgan.

Agar bir hafta ichida tizim normal ishlasa, butun shu papkani o'chirib yuborishingiz mumkin.
Biror narsa buzilsa, faylni ASL JOYIGA qaytaring:

root/requirements.txt                  -> requirements.txt            (loyiha ildizi; eski versiyalar, Docker/CI ishlatmaydi)
root/alembic.ini                       -> alembic.ini                 (loyiha ildizi; Docker backend/alembic.ini ni oladi)
root/p03_20261113_153306.dump          -> p03_20261113_153306.dump    (ildizdagi 133 MB bazaning eski nusxasi)
scripts/anomaly_detection.py           -> scripts/
scripts/import_nomenclature.py         -> scripts/
scripts/read-excel.mjs                 -> scripts/
scripts/requirements_anomaly.txt       -> scripts/
scripts/requirements_nomenclature.txt  -> scripts/
scripts/excel_folder.txt               -> scripts/
backend_app_services_assistant_handlers/_i18n.py -> backend/app/services/assistant/handlers/

Tegilmadi (kerak!): Bridge_Scale 93.mdb, Bridge_Scale 97.mdb, backups/, scripts/backup_*.sh, scripts/scales_collector.
Tafsilot: docs/audit/10_PERFORMANCE_AND_DEAD_CODE.md
