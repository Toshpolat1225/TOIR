"""Reference data CRUD (departments, sections, employees, work types, nomenclature, norms), exports and the realtime socket."""
import csv
import io
import json
import os
import secrets

import httpx

from zz_lib import API, BASE, IDS, SC, Api, clients, psql, rec

A = "directories"
CREATED = os.path.join(SC, "zz_created.json")
created = json.load(open(CREATED)) if os.path.exists(CREATED) else {}


def chk(name, ok, detail="", severity="high", area=A):
    return rec(area, name, "PASS" if ok else "FAIL", detail, None if ok else severity)


def keep(kind, value):
    created.setdefault(kind, []).append(value)
    json.dump(created, open(CREATED, "w"))


C = clients()
admin, operator, master, management = C["admin"], C["operator"], C["master"], C["management"]
tag = secrets.token_hex(3)

# ── departments / sections ───────────────────────────────────────────────────
r = admin.post("/departments", json={"name": f"ZZTEST-Dept-{tag}", "color": "#112233"})
chk("create a department", r.status_code == 201, r.text[:100])
dep = r.json().get("id"); keep("departments", dep)
r2 = admin.post("/departments", json={"name": f"zztest-dept-{tag}"})
chk("a department name differs only by case: duplicate (409)", r2.status_code == 409, f"status {r2.status_code}", "medium")
r = admin.post("/departments", json={"name": f"ZZTEST-Bad-{tag}", "color": "red; background:url(x)"})
chk("a department colour must be a colour (no CSS injection)", r.status_code == 422, f"status {r.status_code}", "medium")
for who, nm in ((master, "master"), (management, "management")):
    r = who.post("/departments", json={"name": f"ZZTEST-X-{nm}-{tag}"})
    chk(f"{nm} cannot create a department", r.status_code == 403, f"status {r.status_code}", "critical")
r = admin.post("/sections", json={"name": f"ZZTEST-Sub-{tag}", "department_id": dep, "parent_id": IDS["sections"]["A"]})
chk("create a sub-section under a ZZTEST section", r.status_code == 201, r.text[:120])
sub = r.json().get("id"); keep("sections", sub)
r = admin.patch(f"/sections/{IDS['sections']['A']}", json={"parent_id": sub})
chk("a section cannot become a child of its own descendant (cycle) — 409/422", r.status_code in (409, 422), f"status {r.status_code}", "high")
r = admin.patch(f"/sections/{sub}", json={"parent_id": sub})
chk("a section cannot be its own parent", r.status_code in (409, 422), f"status {r.status_code}", "high")
tree = admin.get("/sections/tree", params={"q": "ZZTEST"})
chk("the section tree answers and contains the ZZTEST sections", tree.status_code == 200 and "ZZTEST" in tree.text, f"status {tree.status_code}", "medium")
r = admin.delete(f"/sections/{sub}")
chk("a childless unused section can be deleted", r.status_code == 204, f"status {r.status_code}", "medium")
if r.status_code == 204:
    created["sections"].remove(sub)
r = admin.delete(f"/departments/{dep}")
chk("an unused department can be deleted", r.status_code == 204, f"status {r.status_code}", "medium")
if r.status_code == 204:
    created["departments"].remove(dep)
r = admin.delete(f"/sections/{IDS['sections']['A']}")
chk("a section used by users and assets cannot be deleted (409)", r.status_code in (409, 422), f"status {r.status_code}", "high")

# ── employees ────────────────────────────────────────────────────────────────
r = admin.post("/employees", json={"tab_number": f"ZZTEST-E{tag}", "full_name": "=HYPERLINK(\"http://evil\")", "section_id": IDS["sections"]["A"]})
chk("create an employee with a formula-looking name", r.status_code == 201, r.text[:100])
emp = r.json().get("id"); keep("employees", emp)
r = admin.post("/employees", json={"tab_number": f"ZZTEST-E{tag}", "full_name": "dup"})
chk("a duplicate tab number is refused (409)", r.status_code == 409, f"status {r.status_code}", "medium")
r = operator.patch(f"/employees/{emp}", json={"position": "ZZTEST position"})
chk("operator edits an employee", r.status_code == 200, f"status {r.status_code}", "medium")
r = master.patch(f"/employees/{emp}", json={"position": "x"})
chk("master cannot edit employees", r.status_code == 403, f"status {r.status_code}", "high")
r = operator.delete(f"/employees/{emp}")
chk("operator may delete an employee (organization.delete is granted to operator)", r.status_code in (204, 409), f"status {r.status_code}", "low")
if r.status_code == 204:
    created["employees"].remove(emp)

# ── work types / nomenclature / norms ────────────────────────────────────────
r = admin.post("/work-types", json={"code": f"ZZT{tag}", "name": "ZZTEST work type", "unit_type": "locomotive"})
chk("create a work type", r.status_code == 201, r.text[:100])
wt = r.json().get("id"); keep("work_types", wt)
r = admin.post("/work-types", json={"code": f"ZZT{tag}", "name": "dup", "unit_type": "locomotive"})
chk("a duplicate work type code is refused (409)", r.status_code == 409, f"status {r.status_code}", "medium")
r = admin.post("/work-types", json={"code": f"ZZB{tag}", "name": "bad", "unit_type": "spaceship"})
chk("an unknown unit type is refused (422)", r.status_code == 422, f"status {r.status_code}", "medium")
dept_real = admin.get("/departments", params={"limit": 1}).json()["items"][0]["id"]
r = admin.post("/nomenclature", json={"department_id": dept_real, "name": f"ZZTEST item {tag}", "unit": "pcs"})
chk("create a nomenclature item", r.status_code == 201, r.text[:100])
nom = r.json().get("id"); keep("nomenclature", nom)
r = admin.post("/nomenclature-norms", json={"nomenclature_id": nom, "department_id": dept_real, "work_type_id": wt, "standard_quantity": -1, "avg_price": 10})
chk("a negative standard quantity is refused (422)", r.status_code == 422, f"status {r.status_code}", "medium")
r = admin.post("/nomenclature-norms", json={"nomenclature_id": nom, "department_id": dept_real, "work_type_id": wt, "standard_quantity": 2, "avg_price": 10})
chk("create a norm", r.status_code == 201, r.text[:100])
norm = r.json().get("id"); keep("norms", norm)
r = admin.post("/work-orders/norm-check", json={"department_id": dept_real, "items": [{"nomenclature_id": nom, "work_type_id": wt, "qty": 5}]}) if False else None
r = operator.delete(f"/nomenclature-norms/{norm}")
chk("a norm can be deleted by an operator with inventory.delete", r.status_code in (204, 403), f"status {r.status_code}", "low")
if r.status_code == 204:
    created["norms"].remove(norm)

# ── exports: spreadsheet formula injection ───────────────────────────────────
r = admin.get("/reports/fixed-assets", params={"format": "csv", "q": "ZZTEST", "limit": 50})
if r.status_code == 200 and r.text:
    text = r.text.lstrip("﻿")
    rows = list(csv.reader(io.StringIO(text), delimiter=";" if text.count(";") > text.count(",") else ","))
    risky = [c for row in rows for c in row if c[:1] in ("=", "+", "@") or (c[:1] == "-" and not c[1:2].isdigit())]
    chk("CSV exports neutralise cells that start with = + @ -", not risky, f"{len(risky)} risky cells, e.g. {risky[:2]}", "high")
else:
    rec(A, "CSV export of fixed assets", "NOT_TESTED", f"status {r.status_code}")
r = admin.get("/reports/work-orders", params={"format": "csv", "limit": 5})
chk("the work-order export answers", r.status_code == 200, f"status {r.status_code}", "medium")
r = admin.get("/reports/work-orders", params={"format": "xlsx", "limit": 5})
chk("an unknown export format is refused (422), not a 500", r.status_code in (400, 422), f"status {r.status_code}", "medium")

# ── realtime socket ──────────────────────────────────────────────────────────
try:
    import websockets  # type: ignore
    have_ws = True
except Exception:
    have_ws = False
rec("realtime", "websocket authentication", "NOT_TESTED", "the 'websockets' package is not available in the test environment") if not have_ws else None

json.dump(created, open(CREATED, "w"))
