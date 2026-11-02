-- SHABLON: shubhali mileage'ni QO'LDA tuzatish. :asset_id va :real_km ni priborning HAQIQIY ko'rsatkichi bilan to'ldiring.
-- HILUX 366 uchun taxminiy ~323 976 km edi, lekin bu TAXMIN: pribordan tasdiqlamasdan kiritmang.
BEGIN;
UPDATE fixed_assets SET mileage = :real_km, updated_at = now() WHERE id = :'asset_id';
INSERT INTO mileage_history (asset_id, mileage, source) VALUES (:'asset_id', :real_km, 'manual');
COMMIT;
