-- Birinchi sinxronlashdan KEYIN (FAQAT O'QISH)
SELECT last_status, count(*) FROM wialon_counter_state GROUP BY 1 ORDER BY 2 DESC;
SELECT counter, left(reason, 60) AS sabab, count(*) FROM wialon_rejected_readings GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 20;
SELECT a.name, a.mileage, s.last_cnm, s.suspect_absolute, s.engine_hours, s.last_status
  FROM wialon_counter_state s JOIN fixed_assets a ON a.id = s.asset_id
 WHERE s.suspect_absolute OR a.wialon_id = '366' ORDER BY a.name;           -- HILUX mileage O'ZGARMAGAN bo'lishi kerak
SELECT count(*) AS mileage_1e6_dan_katta FROM fixed_assets WHERE mileage > 1000000;
SELECT count(*) AS cneh_ma_lumot_yoq FROM wialon_counter_state WHERE engine_hours IS NULL;
