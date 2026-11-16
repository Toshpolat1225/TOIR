-- exact row count of every table + a content hash of the tables that real activity does not touch constantly
select c.table_name,
       (xpath('/row/c/text()', query_to_xml(format('select count(*) as c from %I', c.table_name), false, true, '')))[1]::text::bigint as n,
       case when c.table_name in ('users','sections','departments','work_types','work_subtasks','maintenance_intervals','maintenance_settings',
                                  'fixed_asset_types','fixed_asset_statuses','permissions','role_permissions','employees','nomenclature')
            then (xpath('/row/h/text()', query_to_xml(format('select md5(coalesce(string_agg(t::text, ''|'' order by t::text), '''')) as h from %I t', c.table_name), false, true, '')))[1]::text
            else null end as content_hash
from information_schema.tables c
where c.table_schema = 'public' and c.table_type = 'BASE TABLE'
order by 1;
