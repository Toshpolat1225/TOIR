-- Read-only preflight for migration 0008.
-- First restore a backup to a test database and apply migration 0007 there.

-- Existing section IDs remain unchanged; this is the explicit legacy -> new ID map.
SELECT id AS old_section_id, id AS new_unit_id
FROM sections
ORDER BY id;

-- Must return no rows: invalid typed parent-child relationships.
SELECT child.id AS child_id, child.unit_type AS child_type,
       parent.id AS parent_id, parent.unit_type AS parent_type
FROM sections child
JOIN sections parent ON parent.id = child.parent_id
WHERE NOT (
    (child.unit_type = 'division' AND parent.unit_type IN ('department', 'division'))
    OR (child.unit_type = 'section' AND parent.unit_type IN ('department', 'division', 'section'))
    OR (child.unit_type = 'team' AND parent.unit_type IN ('division', 'section', 'team'))
);

-- Must return no rows: unsupported unit types.
SELECT id, unit_type
FROM sections
WHERE unit_type NOT IN ('department', 'division', 'section', 'team');

-- Must return no rows: parent cycles.
WITH RECURSIVE ancestors(start_id, current_id, parent_id, visited, has_cycle) AS (
    SELECT id, id, parent_id, ARRAY[id], false
    FROM sections
    UNION ALL
    SELECT a.start_id, parent.id, parent.parent_id,
           a.visited || parent.id, parent.id = ANY(a.visited)
    FROM ancestors a
    JOIN sections parent ON parent.id = a.parent_id
    WHERE NOT a.has_cycle
)
SELECT DISTINCT start_id
FROM ancestors
WHERE has_cycle
ORDER BY start_id;

-- Must return no rows before downgrading 0008: duplicate names block restoring
-- the legacy unique sections_name_key constraint.
SELECT name, count(*) AS duplicate_count
FROM sections
GROUP BY name
HAVING count(*) > 1
ORDER BY name;

-- Must return no rows: active children beneath archived parents.
SELECT child.id AS child_id, parent.id AS archived_parent_id
FROM sections child
JOIN sections parent ON parent.id = child.parent_id
WHERE parent.is_archived AND NOT child.is_archived;

-- Review rows that will remain historically linked after soft archival.
SELECT 'users' AS source_table, count(*) AS linked_rows FROM users WHERE section_id IS NOT NULL
UNION ALL
SELECT 'employees', count(*) FROM employees WHERE section_id IS NOT NULL
UNION ALL
SELECT 'fixed_assets', count(*) FROM fixed_assets WHERE section_id IS NOT NULL
UNION ALL
SELECT 'work_orders', count(*) FROM work_orders WHERE section_id IS NOT NULL
UNION ALL
SELECT 'maintenance_log', count(*) FROM maintenance_log WHERE section_id IS NOT NULL
UNION ALL
SELECT 'tmc_documents', count(*) FROM tmc_documents WHERE section_id IS NOT NULL
UNION ALL
SELECT 'daily_readiness_snapshots', count(*)
FROM daily_readiness_snapshots
WHERE section_id IS NOT NULL;
