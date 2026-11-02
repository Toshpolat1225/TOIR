-- 0) FAQAT O'QISH. Migratsiyadan OLDIN ishga tushiring, natijani saqlang.
SELECT count(*) AS jami_aktiv, count(wialon_id) AS wialon_id_bor FROM fixed_assets;
SELECT wialon_id, count(*) FROM fixed_assets WHERE wialon_id IS NOT NULL GROUP BY 1 HAVING count(*) > 1;   -- bo'sh bo'lishi kerak
SELECT id, inv_number, name, mileage, wialon_id, wialon_last_sync FROM fixed_assets
 WHERE wialon_id = '366' OR name ILIKE '%HILUX%' ORDER BY name;
SELECT id, name, mileage, wialon_id FROM fixed_assets WHERE mileage > 1000000 ORDER BY mileage DESC;      -- shubhali mileage
SELECT a.name, h.mileage, h.recorded_at FROM mileage_history h JOIN fixed_assets a ON a.id = h.asset_id
 WHERE h.source = 'wialon' AND h.mileage > 1000000 ORDER BY h.recorded_at DESC LIMIT 50;
SELECT wialon_online, count(*) FROM fixed_assets WHERE wialon_id IS NOT NULL GROUP BY 1;
