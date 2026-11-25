"""Live check of the spare-part analytics endpoints and the 1C import (it only sends GET requests and an import DRY RUN: nothing is written).

Needs zz_lib.py's files next to it (zztest_creds.json, zz_ids.json). Set TOIR_ROOT_CERT to the root certificate.
With an empty stock table the stock-risk rows are `no_data`: that is reported as INFO, load a 1C file first (python -m app.cli stock-import).
NOT RUN by the author: run it on the server and read the output.
"""
import io
import os

import httpx

from zz_lib import CREDS, rec

HOST = os.environ.get("TOIR_HOST", "192.168.28.104")
ROOT_CERT = os.environ.get("TOIR_ROOT_CERT", "toir-local-root.crt")
API = f"https://{HOST}/api/v1"
AREA = "parts"
HORIZONS = ("quarter", "half", "year")


def login(role):
    client = httpx.Client(base_url=API, timeout=90, verify=ROOT_CERT)
    c = CREDS[role]
    r = client.post("/auth/login", json={"email": c["email"], "password": c["password"]})
    r.raise_for_status()
    return client, {"Authorization": f"Bearer {r.json()['access_token']}"}


def ok(name, cond, detail="", sev="high"):
    rec(AREA, name, "PASS" if cond else "FAIL", str(detail)[:200], sev)


PATHS = ("/analytics/repair-forecast", "/analytics/parts-demand", "/analytics/parts-consumption", "/analytics/stock-risk", "/supplier-terms", "/purchase-orders")
anon = httpx.Client(base_url=API, timeout=30, verify=ROOT_CERT)
for path in PATHS:
    ok(f"{path}: no token is refused", anon.get(path).status_code == 401)
ok("stock import without a token is refused", anon.post("/stock/import").status_code == 401)

admin, ah = login("admin")
operator, oh = login("operator")
master, mh = login("master")
management, gh = login("management")

for h in HORIZONS:
    r = admin.get("/analytics/repair-forecast", params={"horizon": h}, headers=ah)
    d = r.json() if r.status_code == 200 else {}
    ok(f"repair-forecast {h}: 200 with summary and items", r.status_code == 200 and {"summary", "items", "upcoming"} <= set(d), r.status_code)
    s = d.get("summary", {})
    ok(f"repair-forecast {h}: total = planned + projected", s.get("total") == s.get("planned", 0) + s.get("projected", 0), s)
    ok(f"repair-forecast {h}: items add up to the total", sum(i["total"] for i in d.get("items", [])) == s.get("total"), s.get("total"))
    ok(f"repair-forecast {h}: asset types add up", sum(s.get("by_asset_type", {}).values()) == s.get("total"), s.get("by_asset_type"))
    ok(f"repair-forecast {h}: age cohorts add up", sum(s.get("by_age", {}).values()) == s.get("total"), s.get("by_age"))
ok("repair-forecast: a wider horizon never has fewer repairs", admin.get("/analytics/repair-forecast", params={"horizon": "year"}, headers=ah).json()["summary"]["total"]
   >= admin.get("/analytics/repair-forecast", params={"horizon": "quarter"}, headers=ah).json()["summary"]["total"])
ok("repair-forecast: bad horizon is 422", admin.get("/analytics/repair-forecast", params={"horizon": "week"}, headers=ah).status_code == 422)
ok("old generic block still works (route order)", admin.get("/analytics/executive-summary", params={"limit": 1}, headers=ah).status_code == 200)

dem = admin.get("/analytics/parts-demand", params={"horizon": "all", "limit": 500}, headers=ah)
d = dem.json() if dem.status_code == 200 else {}
ok("parts-demand: 200 with the paginated shape", dem.status_code == 200 and {"items", "total", "limit", "offset", "summary", "norm_gaps"} <= set(d), dem.status_code)
ok("parts-demand: quarter <= half <= year for every part", all(i["qty_quarter"] <= i["qty_half"] + 1e-6 <= i["qty_year"] + 2e-6 for i in d.get("items", [])))
ok("parts-demand: summary year cost equals the sum of the parts", abs(d.get("summary", {}).get("cost_year", 0) - sum(i["cost_year"] for i in d.get("items", []))) < 1 or d.get("total", 0) > 500)
ok("parts-demand: horizon filter keeps only parts needed in it", all(i["qty_quarter"] > 0 for i in admin.get("/analytics/parts-demand", params={"horizon": "quarter", "limit": 500}, headers=ah).json().get("items", [])))

con = admin.get("/analytics/parts-consumption", params={"months": 8}, headers=ah)
c = con.json() if con.status_code == 200 else {}
ok("parts-consumption: 200", con.status_code == 200 and {"items", "monthly_cost", "totals", "saving_potential"} <= set(c), con.status_code)
ok("parts-consumption: one monthly point per month", len(c.get("monthly_cost", [])) == 8 and all(len(i["series"]) == 8 for i in c.get("items", [])))
ok("parts-consumption: ranked by cost", [i["total_cost"] for i in c.get("items", [])] == sorted((i["total_cost"] for i in c.get("items", [])), reverse=True))
ok("parts-consumption: overuse is never negative", all(i["over_qty"] >= 0 and i["over_cost"] >= 0 for i in c.get("items", [])))
ok("parts-consumption: months out of range is 422", admin.get("/analytics/parts-consumption", params={"months": 99}, headers=ah).status_code == 422)

risk = admin.get("/analytics/stock-risk", params={"limit": 1000}, headers=ah)
r = risk.json() if risk.status_code == 200 else {}
ok("stock-risk: 200 with items and summary", risk.status_code == 200 and {"items", "total", "limit", "offset", "summary"} <= set(r), risk.status_code)
summary = r.get("summary", {})
ok("stock-risk: summary counts add up to the total", sum(summary.get(k, 0) for k in ("critical", "order_now", "ok", "no_data")) == r.get("total"), summary)
ok("stock-risk: every item has a verdict and a Russian message", all(i["status"] in ("critical", "order_now", "ok", "no_data") and i["message"] for i in r.get("items", [])))
ok("stock-risk: critical items really run out before the lead time", all(i["runs_out_in_days"] < i["lead_time_days"] for i in r.get("items", []) if i["status"] == "critical"))
if r.get("total") and summary.get("no_data") == r.get("total"):
    rec(AREA, "stock-risk: no stock balances loaded yet (all no_data)", "INFO", "load a 1C file with: python -m app.cli stock-import --file ... --apply")
for st in ("critical", "order_now", "ok", "no_data"):
    only = admin.get("/analytics/stock-risk", params={"status": st, "limit": 1000}, headers=ah).json()
    ok(f"stock-risk status={st}: only that status, count matches summary", all(i["status"] == st for i in only["items"]) and only["total"] == summary.get(st), (only["total"], summary.get(st)))
ok("stock-risk: bad sort_by is 422", admin.get("/analytics/stock-risk", params={"sort_by": "password"}, headers=ah).status_code == 422)
ok("stock-risk: sort by runs_out_in_days asc", [i["runs_out_in_days"] for i in admin.get("/analytics/stock-risk", params={"sort_by": "runs_out_in_days", "limit": 1000}, headers=ah).json()["items"] if i["runs_out_in_days"] is not None]
   == sorted(i["runs_out_in_days"] for i in r.get("items", []) if i["runs_out_in_days"] is not None))

# roles: everybody with analytics.view reads; the master only sees his section; writes need admin/operator
for name, cl, h in (("operator", operator, oh), ("management", management, gh), ("master", master, mh)):
    ok(f"{name}: can read all four cards", all(cl.get(p, headers=h).status_code == 200 for p in PATHS[:4]))
sections = admin.get("/sections", params={"limit": 200}, headers=ah).json()
sec_items = sections["items"] if isinstance(sections, dict) else sections
me = master.get("/auth/me", headers=mh).json()
mine = me.get("section_id")
other = next((s["id"] for s in sec_items if s["id"] != mine), None)
if mine and other:
    for p in PATHS[:4]:
        ok(f"master: {p} of another section is 404", master.get(p, params={"section_id": other}, headers=mh).status_code == 404)
    ok("master: parts-demand totals are not above the admin's", master.get("/analytics/parts-demand", headers=mh).json()["total"] <= admin.get("/analytics/parts-demand", params={"limit": 1000}, headers=ah).json()["total"])
else:
    rec(AREA, "master section isolation", "NOT_TESTED", "the master has no section or there is only one section")
ok("master: cannot import 1C files", master.post("/stock/import", headers=mh).status_code in (403, 422))
ok("operator: cannot import 1C files (admin only)", operator.post("/stock/import", headers=oh).status_code in (403, 422))
ok("management: cannot write supplier terms", management.put("/supplier-terms/00000000-0000-0000-0000-000000000000", json={"lead_time_days": 5}, headers=gh).status_code == 403)
ok("master: cannot write supplier terms", master.put("/supplier-terms/00000000-0000-0000-0000-000000000000", json={"lead_time_days": 5}, headers=mh).status_code == 403)
ok("operator: unknown nomenclature is 404 (nothing is written)", operator.put("/supplier-terms/00000000-0000-0000-0000-000000000000", json={"lead_time_days": 5}, headers=oh).status_code == 404)
ok("operator: bad order body is 422", operator.post("/purchase-orders", json={"nomenclature_id": "00000000-0000-0000-0000-000000000000", "qty": -1}, headers=oh).status_code == 422)
for p in ("/supplier-terms", "/purchase-orders"):
    page = admin.get(p, params={"limit": 5}, headers=ah).json()
    ok(f"{p}: paginated shape", {"items", "total", "limit", "offset"} <= set(page))
ok("purchase-orders: bad sort_by is 422", admin.get("/purchase-orders", params={"sort_by": "x"}, headers=ah).status_code == 422)

# import DRY RUN only (apply=false never writes)
csv = "Номенклатура;Код;Склад;Единица;Количество\nНет такой позиции ZZTEST;ZZTEST-000;Склад;шт;1\n".encode("utf-8")
dry = admin.post("/stock/import", params={"apply": "false"}, files={"file": ("zztest.csv", io.BytesIO(csv), "text/csv")}, headers=ah)
j = dry.json() if dry.status_code == 200 else {}
ok("import dry run: 200, nothing applied, the unknown row is reported not_found", dry.status_code == 200 and j.get("applied") is False and j["sheets"][0]["not_found_count"] == 1, dry.status_code)
bad = admin.post("/stock/import", files={"file": ("x.pdf", io.BytesIO(b"x"), "application/pdf")}, headers=ah)
ok("import: a non-spreadsheet file is 422", bad.status_code == 422, bad.status_code)
print("done: parts analytics")
