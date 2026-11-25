# Parts (ТМЦ) analytics: API contract

Base: `/api/v1`. Permission `analytics.view` for the four cards (admin, operator, master, management). A **master** always gets his own section;
`section_id` of another section is **404** (checked first). Errors are `{"detail": ...}`. Migration: `0046_stock_risk` (3 new tables, additive).

Rules: quarter = 90 days, half = 180, year = 365 (from today, Tashkent). A part's daily demand = `max(history monthly average / 30, planned demand of the next 90 days / 90)`.
Planned demand = open plan rows (`scheduled`, `blocked`, `in_progress`) x `nomenclature_norms` of the department that serves the unit
(diesel -> Участок ПТОЛ, locomotive -> Электровозное депо, wagons -> Участок ПТОВ, wagon work types ДР/КРВ -> Участок ВРП). Overdue plan rows count in every horizon.
`include_cycles=true` (default) also projects the repeats of an interval after its planned date (interval days, else interval km / average daily km of the section+type, else
`DAILY_KM_ESTIMATE`); a repeat next to a higher-rank repair of the same unit is dropped. Counts are split `planned` (real plan rows) / `projected` (repeats).
Age cohort: age = current year - commissioning year (else year built); `new` <= 10, `old` >= 25, `middle` between, `unknown` without a year.
Intervals without a work type (e.g. the `test` interval of the demo copy) have no norms: they appear in `norm_gaps`.

## GET /analytics/repair-forecast?horizon=quarter|half|year&section_id=&include_cycles=true
```json
{"horizon":"year","horizon_days":365,"today":"2026-11-26","date_to":"2027-11-26","section_id":null,"include_cycles":true,"age_rule":"...",
 "summary":{"planned":581,"projected":6923,"overdue":17,"total":7504,"by_asset_type":{"locomotive":1876,"diesel":495,"wagon":5133},"by_age":{"new":1436,"middle":2201,"old":3867,"unknown":0}},
 "items":[{"interval_code":"ТО-1","interval_name":"ТО-1","work_type_code":"ТО-1","rank":1,"planned":70,"projected":270,"total":340,
           "by_asset_type":{"locomotive":190,"diesel":150,"wagon":0},"by_age":{"new":58,"middle":63,"old":219,"unknown":0}}],
 "upcoming":[{"asset_id":"...","inv_number":"37045","asset_type":"diesel","interval_code":"КР","interval_name":"КР","scheduled_date":"2026-12-20","days_left":24,"overdue":false,"status":"scheduled","age_cohort":"old"}]}
```
`upcoming` = the 20 biggest real plan rows (highest interval rank first, then date).

## GET /analytics/parts-demand?horizon=quarter|half|year|all&section_id=&include_cycles=true&limit=100&offset=0
```json
{"horizon":"all","today":"2026-11-26","section_id":null,"include_cycles":true,"total":83,"limit":100,"offset":0,
 "items":[{"nomenclature_id":"...","name":"Корпус автосцепки СА-3","code":"ДЕМО-0010","unit":"шт","department":"Участок ПТОВ",
           "qty_quarter":393.3,"qty_half":798.0,"qty_year":1464.9,"cost_quarter":1533870000.0,"cost_half":3112200000.0,"cost_year":5713110000.0,
           "history_monthly_avg":31.75,"history_monthly_cost":123825000.0,"note":null}],
 "summary":{"cost_quarter":0.0,"cost_half":0.0,"cost_year":0.0,"items_without_norm":14},
 "norm_gaps":[{"interval_code":"test","department":"Участок ПТОВ","repairs_year":4831,"reason":"interval is not linked to a work type"}]}
```
`note` is set (text, Russian) when the part has history but no norm for the planned repairs. A single horizon drops parts that are not needed in it and sorts by that horizon's cost; `all` sorts by year cost.

## GET /analytics/parts-consumption?months=8&section_id=&limit=30
Source: issued TMC documents (`issued`/`closed`). Overuse = quantity above the repair norm of that work type (money = over qty x line price).
```json
{"months":8,"today":"2026-11-26","date_from":"2026-04-01","section_id":null,"note":"...",
 "totals":{"items":83,"cost":4817530900.0,"overuse_cost":415151350.0},
 "monthly_cost":[{"month":"2026-04-01","cost":510346660.0}],
 "items":[{"nomenclature_id":"...","name":"...","code":"...","unit":"шт","rank":1,"total_qty":226.9,"total_cost":884910000.0,"monthly_avg":28.776,
           "series":[{"month":"2026-04-01","qty":26.6}],"trend_pct":8.5,"trend":"flat","over_qty":25.0,"over_cost":97500000.0,
           "top_work_types":[{"work_type":"ТО-2В","qty":226.9}],"top_asset_types":[{"asset_type":"wagon","qty":226.9}]}],
 "fastest_growing":["<nomenclature_id>"],
 "saving_potential":[{"nomenclature_id":"...","name":"...","unit":"шт","over_qty":25.0,"over_cost":97500000.0}]}
```
`items` are ranked by cost (`rank`). `trend` = last 3 complete months vs the 3 before (`up` >+10%, `down` <-10%, else `flat`); `null` when `months` < 7. The last `series` point is the current (partial) month.

## GET /analytics/stock-risk?section_id=&status=critical|order_now|ok|no_data&sort_by=&sort_dir=asc|desc&limit=50&offset=0&include_cycles=true
`sort_by` whitelist: `status` (default: critical first, then by days left), `name`, `stock`, `runs_out_in_days`, `need_by_days`, `shortfall_cost_year`, `daily_demand`.
```json
{"items":[{"nomenclature_id":"...","name":"Болт М20х80","code":"ДЕМО-0071","unit":"шт","department":"Участок ВРП","stock":6.0,"stock_as_of":"2026-11-24","stock_age_days":2,
           "supplier":"ООО «ТехСнаб»","price":4200.0,"history_monthly_avg":26.733,"daily_demand":1.0667,
           "lead_time_days":14,"lead_time_unknown":false,"safety_days":21,
           "runs_out_in_days":5,"runs_out_with_orders_in_days":5,"order_arrives_in_days":null,"need_by_days":-16,"order_by_in_days":-30,"open_orders_qty":0,
           "status":"critical","message":"Остаток 6 шт хватит на 5 дн.; открытых заказов нет; срок поставки 14 дн.; запас закончится раньше, чем придёт поставка.",
           "coverage":{"quarter":{"demand":96.0,"covers":false,"shortfall_qty":90.0,"shortfall_cost":378000.0},"half":{},"year":{}},
           "shortfall_cost_quarter":378000.0,"shortfall_cost_half":1184400.0,"shortfall_cost_year":2877840.0}],
 "total":84,"limit":50,"offset":0,
 "summary":{"critical":9,"order_now":6,"ok":61,"no_data":8,"shortfall_cost_quarter":0.0,"shortfall_cost_half":0.0,"shortfall_cost_year":0.0},
 "today":"2026-11-26","section_id":null,"rule":"daily demand = max(...)"}
```
Verdicts: `runs_out_in_days` = stock / daily demand. An open order (`ordered`/`in_transit`/`partial`, qty - received) that arrives (`expected_on`; no date = after the lead time) before the stock is gone extends the cover
(`runs_out_with_orders_in_days`). `critical` = stock ends before the lead time and no order arrives in time. `order_now` = `need_by_days` (= cover with orders - safety days) <= lead time.
`ok` otherwise; `no_data` = no 1C balance. Lead time missing -> 30 days, `lead_time_unknown=true`; safety missing -> 14. `order_by_in_days` <= 0 means "order now".
`shortfall_*` = max(0, demand of the horizon - stock - open orders) x price (planned norm price, else history price). A master sees only parts his section planned or issued (stock itself is a shared figure).

## Stock import and small CRUD
* `POST /stock/import` (admin only), multipart field `file` (.xlsx or .csv, max 10 MB), query `apply=false` (dry run, default), `as_of=YYYY-MM-DD` (balance date, default today), `kind=stock|orders|lead_times` (default: detected from the header).
  Response: `{"applied":false,"batch_id":null,"as_of":"...","sheets":[{"sheet":"...","kind":"stock","rows_read":3,"matched":2,"skipped":1,"invalid":[{"row":5,"name":"","code":"","reason":""}],"not_found":[{"row":6,"name":"","code":""}],"ambiguous":[],"not_found_count":1,"ambiguous_count":0,"invalid_count":0,"would_write":2}]}`;
  with `apply=true`: `written` (and `inserted`/`updated` for orders) instead of `would_write`. Not found / ambiguous / invalid rows are never written. Every sheet of an .xlsx is read (the sheet kind is detected from its header).
* `GET /supplier-terms?nomenclature_id=` / `PUT /supplier-terms/{nomenclature_id}` body `{"supplier","lead_time_days","min_order_qty","safety_days","note"}` (upsert).
* `GET /purchase-orders?nomenclature_id=&status=&open_only=&sort_by=expected_on|ordered_on|status|created_at&sort_dir=` / `POST /purchase-orders` / `PUT /purchase-orders/{id}`
  body `{"nomenclature_id" (POST only),"supplier","doc_no","qty","qty_received","ordered_on","expected_on","status","note"}`; status in `ordered|in_transit|partial|received|cancelled`.
  Reads need `inventory.view` (a master only sees parts his section issued); writes need `inventory.update` (admin, operator). Lists are `{items,total,limit,offset}`.

CLI (dry run by default): `python -m app.cli stock-import --file path.xlsx|csv [--apply] [--as-of YYYY-MM-DD] [--kind stock|orders|lead_times]`.
Files: see `docs/templates/` and `docs/templates/README_1C.md`.
