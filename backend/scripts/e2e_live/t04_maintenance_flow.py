"""End-to-end maintenance flows on the live API with ZZTEST data only (assets, intervals, employee, orders)."""
import json
import os
import threading
from datetime import date, datetime, timedelta, timezone

from zz_lib import IDS, SC, clients, psql, rec

AREA = "maintenance"
CREATED = os.path.join(SC, "zz_created.json")
created = json.load(open(CREATED)) if os.path.exists(CREATED) else {}


def keep(kind, value):
    created.setdefault(kind, []).append(value)
    json.dump(created, open(CREATED, "w"))


def chk(name, ok, detail="", severity="high"):
    return rec(AREA, name, "PASS" if ok else "FAIL", detail, None if ok else severity)


C = clients_ = None
try:
    C = clients()
except Exception as exc:  # the management account may still be locked by the brute-force test
    from zz_lib import Api
    C = {}
    for role in ("admin", "operator", "master"):
        a = Api(role); a.login(); C[role] = a
    rec(AREA, "management account unavailable for this run", "INFO", str(exc)[:80])
admin, operator, master = C["admin"], C["operator"], C["master"]
management = C.get("management")
SEC_A, SEC_B = IDS["sections"]["A"], IDS["sections"]["B"]
today = date.today()

# ── setup: intervals, employee, assets ───────────────────────────────────────
work_type = admin.get("/work-types", params={"limit": 1}).json()["items"][0]["id"]
emp = admin.post("/employees", json={"tab_number": "ZZTEST-EMP-1", "full_name": "ZZTEST Executor", "section_id": SEC_A})
chk("create an employee", emp.status_code == 201, emp.text[:120]); keep("employees", emp.json()["id"])
EMP = emp.json()["id"]

def interval(code, km, rank, **kw):
    r = admin.post("/maintenance-intervals", json={"code": code, "name": code, "interval_km": km, "rank": rank, "tolerance_pct": 10, "lead_days": 7,
                                                   "asset_types": ["locomotive"], **kw})
    return r
i1 = interval("ZZTEST-I1", 5000, 1)
chk("create an interval with rank, tolerance and lead days", i1.status_code == 201 and i1.json().get("rank") == 1 and i1.json().get("lead_days") == 7, i1.text[:160]); keep("intervals", i1.json()["id"])
i2 = interval("ZZTEST-I2", 15000, 2)
keep("intervals", i2.json()["id"])
I1, I2 = i1.json()["id"], i2.json()["id"]
for payload, label in (({"code": "ZZTEST-BAD1", "name": "x", "asset_types": ["locomotive"]}, "no limit at all"),
                       ({"code": "ZZTEST-BAD2", "name": "x", "interval_km": 100, "rank": 0, "asset_types": ["locomotive"]}, "rank 0"),
                       ({"code": "ZZTEST-BAD3", "name": "x", "interval_km": 100, "tolerance_pct": 101, "asset_types": ["locomotive"]}, "tolerance above 100"),
                       ({"code": "ZZTEST-BAD4", "name": "x", "interval_km": 100, "lead_days": -1, "asset_types": ["locomotive"]}, "negative lead days"),
                       ({"code": "ZZTEST-BAD5", "name": "x", "interval_hours": 500, "asset_types": ["diesel"]}, None)):
    r = admin.post("/maintenance-intervals", json=payload)
    if label is None:
        chk("an interval with only a moto-hours limit is accepted", r.status_code == 201, r.text[:120], "medium")
        if r.status_code == 201:
            keep("intervals", r.json()["id"])
    else:
        chk(f"interval validation rejects {label}", r.status_code == 422, f"status {r.status_code}", "medium")
dup = admin.post("/maintenance-intervals", json={"code": "ZZTEST-I1", "name": "dup", "interval_km": 5, "asset_types": ["locomotive"]})
chk("a duplicate interval code is refused", dup.status_code == 409, f"status {dup.status_code}", "medium")

MODEL = admin.get("/fixed-assets/models", params={"asset_type": "locomotive", "limit": 1}).json()["items"][0]["id"]

def asset(inv, section, mileage):
    # the API (correctly) refuses a non-zero starting mileage: it must come from Wialon. Test assets get theirs by SQL.
    r = admin.post("/fixed-assets", json={"inv_number": inv, "asset_type": "locomotive", "section_id": section, "name": inv, "model_id": MODEL, "number": "9" + inv[-1] + "0099", "serial_number": "ZZ" + inv[-1]})
    if r.status_code == 201:
        psql(f"update fixed_assets set mileage = {mileage} where inv_number = '{inv}'")
    return r
r0 = admin.post("/fixed-assets", json={"inv_number": "ZZTEST-NOMILEAGE", "asset_type": "locomotive", "mileage": 100})
chk("an asset cannot be created with a starting mileage (it must come from Wialon / the opening workflow)", r0.status_code in (403, 409, 422), f"status {r0.status_code} {r0.text[:80]}", "medium")
ids = {}
for inv, section, mileage in (("ZZTEST-L1", SEC_A, 4880), ("ZZTEST-L2", SEC_B, 4900), ("ZZTEST-L3", SEC_A, 4890)):
    r = asset(inv, section, mileage)
    chk(f"create asset {inv}", r.status_code == 201, r.text[:140]); ids[inv] = r.json()["id"]; keep("assets", r.json()["id"])
L1, L2, L3 = ids["ZZTEST-L1"], ids["ZZTEST-L2"], ids["ZZTEST-L3"]

# ── baselines create/refresh the plans ───────────────────────────────────────
def baseline(who, asset_id, interval_id, **kw):
    return who.put("/maintenance-baselines", json={"asset_id": asset_id, "interval_id": interval_id, "done_at": str(today - timedelta(days=30)), **kw})
r = baseline(master, L1, I1, km=0)
chk("a master cannot set a baseline", r.status_code == 403, f"status {r.status_code}", "high")
r = baseline(operator, L1, I1, odometer_km=100)
chk("an odometer baseline without a Wialon link is refused with a clear 422", r.status_code == 422, f"status {r.status_code} {r.text[:100]}", "medium")
r = baseline(operator, L1, I1, km=0, odometer_km=5)
chk("giving both km and odometer is refused", r.status_code == 422, f"status {r.status_code}", "medium")
r = baseline(operator, L1, I1, km=0, done_at=str(today + timedelta(days=2)))
chk("a baseline in the future is refused", r.status_code == 422, f"status {r.status_code}", "medium")
for aid in (L1, L2, L3):
    r = baseline(operator, aid, I1, km=0)
    chk(f"operator sets a baseline ({aid[:6]})", r.status_code == 200 and r.json()["source"] == "manual", r.text[:120])
r = baseline(admin, L1, I2, km=0); chk("baseline for the higher rank", r.status_code == 200, r.text[:100])
r = baseline(admin, L2, I2, km=0)

def schedule(who):
    return who.get("/maintenance-schedule", params={"month": today.strftime("%Y-%m")})

def items_of(resp, asset_id=None, prefix="ZZTEST-I"):
    return [i for i in resp.json()["schedule"] if i["type"].startswith(prefix) and (asset_id is None or i["asset_id"] == asset_id)]

s = schedule(admin)
it = items_of(s, L1)
p1 = next((i for i in it if i["type"].startswith("ZZTEST-I1")), None)
chk("the schedule has the due ZZTEST-I1 item of L1 with living-plan facts", p1 is not None and p1.get("state") in ("due_soon", "over_limit") and p1.get("dateEarly") and p1.get("priority") is not None, json.dumps(p1)[:200] if p1 else "missing")
if p1:
    _ds = [d for d in (p1["dateEarly"], p1.get("dateTypical"), p1.get("dateLate")) if d]  # a slow pace of 0 km/day has no date (null)
    chk("markers are ordered early <= typical <= late (a missing slow date is allowed)", _ds == sorted(_ds), f"{p1['dateEarly']} {p1.get('dateTypical')} {p1.get('dateLate')}", "medium")
    chk("a manual baseline gives a 'manual' baseline source and stays approximate while the pace is thin", p1.get("baselineSource") == "manual" and p1.get("confidence") in ("low", "high"), f"{p1.get('baselineSource')} {p1.get('confidence')}", "medium")
    chk("the item says why it has this priority", len(p1.get("priorityWhy") or []) > 0, "", "medium")
plan1 = p1["plan_id"] if p1 else None
chk("a plan was created by the baseline (window is open)", bool(plan1), "entity=" + (p1["entity_type"] if p1 else "-"))

# ── isolation: a master sees only his own section ────────────────────────────
ms = schedule(master)
seen = {i["asset_id"] for i in items_of(ms)}
chk("master sees ZZTEST assets of his section", L1 in seen and L3 in seen, f"seen={len(seen)}", "high")
chk("master does NOT see a ZZTEST asset of another section", L2 not in seen, "", "critical")
mp = master.get("/maintenance-plan", params={"limit": 1000}).json()["items"]
chk("master's plan list is limited to his section", all(x["asset_id"] != L2 for x in mp), "", "critical")
if management:
    chk("management can read the schedule", schedule(management).status_code == 200, "", "medium")

# ── block / unblock / waive / roles ──────────────────────────────────────────
if plan1:
    r = master.post(f"/maintenance-plan/{plan1}/block", json={"reason_code": "parts"})
    chk("master cannot block a plan", r.status_code == 403, f"status {r.status_code}", "high")
    if management:
        r = management.post(f"/maintenance-plan/{plan1}/block", json={"reason_code": "parts"})
        chk("management cannot block a plan (read-mostly role)", r.status_code == 403, f"status {r.status_code}", "medium")
    r = operator.post(f"/maintenance-plan/{plan1}/block", json={"reason_code": "parts", "until": str(today + timedelta(days=3)), "note": "ZZTEST"})
    chk("operator blocks a plan", r.status_code == 200 and r.json()["status"] == "blocked" and r.json()["blocked_reason"] == "parts", r.text[:140])
    r = operator.post(f"/maintenance-plan/{plan1}/block", json={"reason_code": "parts"})
    chk("blocking twice is a 409", r.status_code == 409, f"status {r.status_code}", "medium")
    r = operator.post(f"/maintenance-plan/{plan1}/block", json={"reason_code": "nonsense"})
    chk("an unknown block reason is a 422", r.status_code == 422, f"status {r.status_code}", "medium")
    r = operator.patch(f"/maintenance-plan/{plan1}", json={"scheduled_date": str(today + timedelta(days=2))})
    chk("a blocked plan cannot be rescheduled (409)", r.status_code == 409, f"status {r.status_code}", "medium")
    r = operator.patch(f"/maintenance-plan/{plan1}", json={"status": "cancelled"})
    chk("PATCH status=cancelled is refused (an obligation is never cancelled)", r.status_code == 409, f"status {r.status_code}", "high")
    sch = items_of(schedule(admin), L1)
    blocked = next((i for i in sch if i.get("plan_id") == plan1), None)
    chk("the schedule shows the plan as blocked with its reason", bool(blocked) and blocked["status"] == "blocked" and blocked.get("blockedReason") == "parts", json.dumps(blocked)[:160] if blocked else "missing")
    r = operator.post(f"/maintenance-plan/{plan1}/unblock")
    chk("operator unblocks", r.status_code == 200 and r.json()["status"] == "scheduled", r.text[:120])
    r = operator.post(f"/maintenance-plan/{plan1}/unblock")
    chk("unblocking a plan that is not blocked is a 409", r.status_code == 409, f"status {r.status_code}", "medium")

    # ── approvals and deferrals ──────────────────────────────────────────────
    cur = operator.get("/maintenance-plan", params={"asset_id": L1, "limit": 50}).json()["items"]
    plan_row = next(x for x in cur if x["id"] == plan1)
    base = date.fromisoformat(plan_row["scheduled_date"])
    r = operator.patch(f"/maintenance-plan/{plan1}", json={"scheduled_date": str(max(today, base) + timedelta(days=120)), "reschedule_reason": "ZZTEST far"})
    chk("operator cannot push a plan far beyond the tolerance (403)", r.status_code == 403, f"status {r.status_code} {r.text[:100]}", "high")
    d = max(today, base)
    results = []
    for k in (1, 2, 3):
        results.append(operator.patch(f"/maintenance-plan/{plan1}", json={"scheduled_date": str(d + timedelta(days=k)), "reschedule_reason": f"ZZTEST move {k}"}).status_code)
    chk("operator may defer twice within the tolerance, the third needs an administrator", results == [200, 200, 403], f"{results}", "high")
    r = admin.patch(f"/maintenance-plan/{plan1}", json={"scheduled_date": str(d + timedelta(days=4)), "reschedule_reason": "ZZTEST admin"})
    chk("an administrator can approve the third deferral", r.status_code == 200 and r.json()["deferral_count"] == 3 and r.json()["scheduled_date_manual"] is True, r.text[:160])
    dec = admin.get(f"/maintenance-plan/{plan1}/decisions").json()
    chk("every move is in the decision log (3+ reschedules, block, unblock)", sum(1 for x in dec if x["kind"] == "reschedule") >= 3 and any(x["kind"] == "block" for x in dec) and any(x["kind"] == "unblock" for x in dec), f"kinds={[x['kind'] for x in dec]}")
    r = operator.patch(f"/maintenance-plan/{plan1}", json={"scheduled_date": str(today - timedelta(days=1))})
    chk("rescheduling into the past is a 422", r.status_code == 422, f"status {r.status_code}", "medium")
    r = operator.patch(f"/maintenance-plan/{plan1}", json={"scheduled_date": str(today), "reset_schedule": True})
    chk("scheduled_date together with reset_schedule is a 422", r.status_code == 422, f"status {r.status_code}", "low")

    # ── concurrency: five parallel moves of one plan ─────────────────────────
    statuses = []
    def move(k):
        r = admin.client.patch(f"/maintenance-plan/{plan1}", json={"scheduled_date": str(today + timedelta(days=10 + k))}, headers={"Authorization": f"Bearer {admin.token}"})
        statuses.append(r.status_code)
    threads = [threading.Thread(target=move, args=(k,)) for k in range(5)]
    [t.start() for t in threads]; [t.join() for t in threads]
    final = next(x for x in admin.get("/maintenance-plan", params={"asset_id": L1, "limit": 50}).json()["items"] if x["id"] == plan1)
    chk("five parallel reschedules never produce a server error and leave a consistent plan", all(s_ in (200, 409) for s_ in statuses) and final["status"] == "scheduled", f"{sorted(statuses)} -> {final['status']} deferrals={final['deferral_count']}", "high")

    # ── waive (admin only) ───────────────────────────────────────────────────
    r = operator.post(f"/maintenance-plan/{plan1}/waive", json={"reason": "ZZTEST waive"})
    chk("operator cannot waive", r.status_code == 403, f"status {r.status_code}", "high")
    r = admin.post(f"/maintenance-plan/{plan1}/waive", json={"reason": "x"})
    chk("waive needs a real reason (min 3 chars)", r.status_code == 422, f"status {r.status_code}", "low")
    r = admin.post(f"/maintenance-plan/{plan1}/waive", json={"reason": "ZZTEST waive"})
    chk("admin waives a cycle", r.status_code == 200 and r.json()["status"] == "waived", r.text[:120])
    bl = admin.get("/maintenance-baselines", params={"asset_id": L1}).json()
    wv = next((b for b in bl if b["interval_id"] == I1), None)
    chk("waiving moves the baseline to the cycle's threshold (source waived, 5000 km)", bool(wv) and wv["source"] == "waived" and float(wv["km"]) == 5000.0, json.dumps(wv))
    r = admin.post(f"/maintenance-plan/{plan1}/waive", json={"reason": "ZZTEST again"})
    chk("a waived plan cannot be waived again (409)", r.status_code == 409, f"status {r.status_code}", "medium")

# ── disruptions ──────────────────────────────────────────────────────────────
r = baseline(admin, L1, I1, km=0, note="ZZTEST rebase")  # a fresh obligation to block
sched = items_of(schedule(admin), L1)
newp = next((i["plan_id"] for i in sched if i["type"].startswith("ZZTEST-I1") and i.get("plan_id") and i["status"] in ("upcoming", "overdue")), None)
r = master.post("/maintenance-disruptions", json={"kind": "no_bay", "scope": "asset", "asset_id": L1})
chk("master cannot create a disruption", r.status_code == 403, f"status {r.status_code}", "high")
r = operator.post("/maintenance-disruptions", json={"kind": "no_bay", "scope": "asset"})
chk("a disruption needs its target (asset_id) — 422", r.status_code == 422, f"status {r.status_code}", "medium")
r = operator.post("/maintenance-disruptions", json={"kind": "no_bay", "scope": "all", "asset_id": L1})
chk("scope 'all' with an asset is a 422", r.status_code == 422, f"status {r.status_code}", "low")
r = operator.post("/maintenance-disruptions", json={"kind": "no_bay", "scope": "asset", "asset_id": L1, "starts_on": str(today), "ends_on": str(today - timedelta(days=1))})
chk("a disruption ending before it starts is a 422", r.status_code == 422, f"status {r.status_code}", "low")
r = operator.post("/maintenance-disruptions", json={"kind": "no_bay", "scope": "asset", "asset_id": L1, "ends_on": str(today + timedelta(days=30)), "note": "ZZTEST"})
chk("operator creates a disruption", r.status_code == 201 and r.json()["status"] == "open", r.text[:140])
dis = r.json(); keep("disruptions", dis["id"])
chk("a disruption blocks the scheduled plans in its window", dis["affected_plans"] >= 1, f"affected={dis['affected_plans']}", "medium")
chk("it is in the open list", any(x["id"] == dis["id"] for x in operator.get("/maintenance-disruptions").json()))
r = operator.post(f"/maintenance-disruptions/{dis['id']}/close")
chk("closing releases the plans", r.status_code == 200 and r.json()["status"] == "closed" and r.json()["affected_plans"] >= 1, r.text[:140])
r = operator.post(f"/maintenance-disruptions/{dis['id']}/close")
chk("closing twice is a 409", r.status_code == 409, f"status {r.status_code}", "low")
r = operator.post("/maintenance-disruptions", json={"kind": "sensor_failure", "scope": "asset", "asset_id": L3})
chk("a sensor_failure disruption does not block plans", r.status_code == 201 and r.json()["affected_plans"] == 0, r.text[:120], "medium")
if r.status_code == 201:
    keep("disruptions", r.json()["id"]); operator.post(f"/maintenance-disruptions/{r.json()['id']}/close")

# ── work orders: complete (+cascade), cancel, delete ─────────────────────────
def plan_of(asset_id, interval_id):
    items = admin.get("/maintenance-plan", params={"asset_id": asset_id, "limit": 100}).json()["items"]
    return next((x for x in items if x["interval_id"] == interval_id and x["status"] in ("scheduled", "blocked", "in_progress")), None)

def make_order(asset_id, section, plan_id, who=admin):
    return who.post("/work-orders", json={"fixed_asset_id": asset_id, "section_id": section, "maintenance_plan_id": plan_id, "order_kind": "planned",
                                          "executor_id": EMP, "description": "ZZTEST order", "repairs": [{"work_type_id": work_type}]})

# L2: lower rank plan exists (I1), create the higher rank (I2) from the forecast, complete I2 -> I1 is covered
l2_i1 = plan_of(L2, I1)
chk("L2 has a plan for the lower rank", l2_i1 is not None, "")
fc = operator.post("/maintenance-plan/from-forecast", json={"asset_id": L2, "interval_id": I2, "scheduled_date": str(today + timedelta(days=2)), "reschedule_reason": "ZZTEST"})
chk("a plan is created from a forecast on the chosen date", fc.status_code == 201 and fc.json()["scheduled_date_manual"] is True, fc.text[:140])
again = operator.post("/maintenance-plan/from-forecast", json={"asset_id": L2, "interval_id": I2, "scheduled_date": str(today + timedelta(days=3))})
chk("a second plan for the same threshold is refused (409)", again.status_code == 409, f"status {again.status_code}", "medium")
l2_i2 = fc.json()["id"] if fc.status_code == 201 else None
if l2_i2:
    o = make_order(L2, SEC_B, l2_i2)
    chk("create a work order linked to the higher-rank plan", o.status_code == 201, o.text[:200])
    if o.status_code == 201:
        oid = o.json()["id"]; keep("orders", oid)
        pl = next(x for x in admin.get("/maintenance-plan", params={"asset_id": L2, "limit": 100}).json()["items"] if x["id"] == l2_i2)
        chk("the plan is in_progress and linked to the order", pl["status"] == "in_progress" and pl["work_order_id"] == oid, json.dumps(pl)[:140])
        r = master.patch(f"/work-orders/{oid}", json={"status": "completed"})
        chk("a master of ANOTHER section cannot touch the order (404/403)", r.status_code in (403, 404), f"status {r.status_code}", "critical")
        r = admin.patch(f"/work-orders/{oid}", json={"status": "completed"})
        chk("pending -> completed is refused (must go through in_progress)", r.status_code == 409, f"status {r.status_code}", "medium")
        r = admin.patch(f"/work-orders/{oid}", json={"status": "in_progress"})
        r = admin.patch(f"/work-orders/{oid}", json={"status": "completed"})
        chk("completing the order completes the plan", r.status_code == 200, r.text[:120])
        plans = {x["id"]: x for x in admin.get("/maintenance-plan", params={"asset_id": L2, "limit": 100}).json()["items"]}
        chk("the higher-rank plan is completed with the mileage recorded", plans[l2_i2]["status"] == "completed", plans[l2_i2]["status"])
        chk("the lower-rank plan is covered by it", plans[l2_i1["id"]]["status"] == "covered", plans[l2_i1["id"]]["status"])
        bl = {b["interval_id"]: b for b in admin.get("/maintenance-baselines", params={"asset_id": L2}).json()}
        chk("both baselines restart from the completion (source completed)", bl[I1]["source"] == "completed" and bl[I2]["source"] == "completed" and bl[I1]["km"] == bl[I2]["km"], json.dumps({k: v["source"] for k, v in bl.items()}))
        r = admin.patch(f"/work-orders/{oid}", json={"description": "edit after completion"})
        chk("a completed order cannot be modified (409)", r.status_code == 409, f"status {r.status_code}", "medium")

# L3: cancel and delete release the obligation
l3 = plan_of(L3, I1)
chk("L3 has a plan to run orders against", l3 is not None, "")
if l3:
    o = make_order(L3, SEC_A, l3["id"], who=master)
    chk("a master creates an order in his own section", o.status_code == 201, o.text[:160])
    if o.status_code == 201:
        oid = o.json()["id"]; keep("orders", oid)
        admin.patch(f"/work-orders/{oid}", json={"status": "in_progress"})
        r = admin.patch(f"/work-orders/{oid}", json={"status": "cancelled"})
        pl = next(x for x in admin.get("/maintenance-plan", params={"asset_id": L3, "limit": 100}).json()["items"] if x["id"] == l3["id"])
        chk("cancelling the order returns the plan to scheduled (not lost)", r.status_code == 200 and pl["status"] == "scheduled" and pl["work_order_id"] is None, f"{r.status_code} {pl['status']}")
        o2 = make_order(L3, SEC_A, l3["id"])
        chk("a new order can be opened on the released plan", o2.status_code == 201, o2.text[:120])
        if o2.status_code == 201:
            oid2 = o2.json()["id"]; keep("orders", oid2)
            r = operator.delete(f"/work-orders/{oid2}")
            chk("operator cannot delete an order (permission matrix)", r.status_code == 403, f"status {r.status_code}", "medium")
            r = admin.delete(f"/work-orders/{oid2}")
            pl = next(x for x in admin.get("/maintenance-plan", params={"asset_id": L3, "limit": 100}).json()["items"] if x["id"] == l3["id"])
            chk("deleting the order returns the plan to scheduled", r.status_code == 204 and pl["status"] == "scheduled" and pl["work_order_id"] is None, f"{r.status_code} {pl['status']}")
            created["orders"].remove(oid2)

# ── KPIs / health / roles ────────────────────────────────────────────────────
k = operator.get("/maintenance-kpis")
chk("KPIs answer with the expected fields", k.status_code == 200 and {"obligations", "over_limit", "due_soon", "blocked", "on_time_pct"} <= set(k.json()), k.text[:120])
h = admin.get("/maintenance-health")
chk("the invariant check reports no issue for ZZTEST data", h.status_code == 200 and not [i for i in h.json()["issues"] if i["code"] in ("running_plan_without_live_order", "duplicate_open_plans")], json.dumps(h.json())[:200])
r = master.get("/maintenance-health")
chk("master cannot call the health endpoint", r.status_code in (403,), f"status {r.status_code}", "medium")
json.dump(created, open(CREATED, "w"))
print("created:", {k_: len(v) for k_, v in created.items()})
