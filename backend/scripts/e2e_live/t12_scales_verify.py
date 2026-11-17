"""Live check of the weighing-scale endpoints, incl. the wagon ledger (read-only: it only sends GET requests).

Needs zz_lib.py's files next to it (zztest_creds.json, zz_ids.json). Set TOIR_ROOT_CERT to the root certificate.
Run it after the collector has loaded data; with an empty database the data checks are reported as INFO.
"""
import os
import sys
from datetime import date, timedelta

import httpx

from zz_lib import CREDS, rec

HOST = os.environ.get("TOIR_HOST", "192.168.28.104")
ROOT_CERT = os.environ.get("TOIR_ROOT_CERT", "toir-local-root.crt")
API = f"https://{HOST}/api/v1"
AREA = "scales"


def login(role):
    client = httpx.Client(base_url=API, timeout=90, verify=ROOT_CERT)
    c = CREDS[role]
    r = client.post("/auth/login", json={"email": c["email"], "password": c["password"]})
    r.raise_for_status()
    return client, {"Authorization": f"Bearer {r.json()['access_token']}"}


def ok(name, cond, detail="", sev="high"):
    rec(AREA, name, "PASS" if cond else "FAIL", str(detail)[:200], sev)


anon = httpx.Client(base_url=API, timeout=30, verify=ROOT_CERT)
for path in ("/scales/status", "/scales/trains", "/scales/wagons", "/scales/wagon-trips", "/scales/wagon-trips/export.csv"):
    ok(f"{path}: no token is refused", anon.get(path).status_code == 401, anon.get(path).status_code)
ok("ingest without the token is refused", anon.post("/scales/ingest", json={"post": "93"}).status_code == 401)

admin, ah = login("admin")
status = admin.get("/scales/status", headers=ah)
ok("status: 200 with posts", status.status_code == 200 and "posts" in status.json(), status.status_code)
data = status.json() if status.status_code == 200 else {}
posts = {p["code"]: p for p in data.get("posts", [])}
ok("status: both scales (93, 97) are known", {"93", "97"} <= set(posts), sorted(posts), "high")
for code, p in posts.items():
    ok(f"status {code}: collector is alive (pulled < 10 min ago)", p["collector"] == "ok", p["collector"], "medium")
print("status:", {k: data.get(k) for k in ("trains_total", "unmatched_total", "first_train_at", "last_train_at")})

today = date.today()
f = {"date_from": (today - timedelta(days=30)).isoformat(), "date_to": today.isoformat()}
totals = admin.get("/scales/wagons", params={**f, "limit": 5}, headers=ah)
ok("wagons: 200 with items and totals", totals.status_code == 200 and {"items", "total", "trips_total", "tonnes_total"} <= set(totals.json()), totals.status_code)
body = totals.json() if totals.status_code == 200 else {}
items = body.get("items", [])
if items:
    first = items[0]
    ok("wagons: ranked by tonnes (descending)", all(float(a["tonnes"]) >= float(b["tonnes"]) for a, b in zip(items, items[1:])), [i["tonnes"] for i in items])
    ok("wagons: the first wagon has trips > 0 and tonnes >= 0", first["trips"] > 0 and float(first["tonnes"]) >= 0, first)
    params = {**f, "limit": 100}
    if first["asset_id"]:
        params["asset_id"] = first["asset_id"]
    else:
        params["q"] = first["gtk_name"] or first["gtk_inventory_number"] or ""
    trips = admin.get("/scales/wagon-trips", params=params, headers=ah)
    tb = trips.json() if trips.status_code == 200 else {}
    ok("wagon-trips: 200", trips.status_code == 200, trips.status_code)
    ok("wagon-trips: trip count equals the wagon's total", tb.get("total") == first["trips"], (tb.get("total"), first["trips"]))
    ok("wagon-trips: tonnes add up to the wagon's total (±0.05)", abs(float(tb.get("tonnes_total", 0)) - float(first["tonnes"])) < 0.05, (tb.get("tonnes_total"), first["tonnes"]))
    ok("wagon-trips: every row carries a basis", all(t["basis"] in {"own", "train_avg", "estimated", "unknown"} for t in tb.get("items", [])))
    ok("wagon-trips: newest first", all((a["started_at"] or "") >= (b["started_at"] or "") for a, b in zip(tb.get("items", []), tb.get("items", [])[1:])))
    csv = admin.get("/scales/wagon-trips/export.csv", params=params, headers=ah)
    ok("export.csv: 200, text/csv, UTF-8 BOM, header", csv.status_code == 200 and "text/csv" in csv.headers.get("content-type", "") and csv.content.startswith(b"\xef\xbb\xbf") and "Дата и время" in csv.text, csv.status_code)
    ok("export.csv: one data line per trip", len(csv.text.strip().splitlines()) - 1 == tb.get("total"), len(csv.text.strip().splitlines()))
else:
    rec(AREA, "wagons: no data in the last 30 days (run the collector first)", "INFO", str(body)[:120])

ok("wagons: an unknown sort field is a 422", admin.get("/scales/wagons", params={"sort_by": "nope"}, headers=ah).status_code == 422)
ok("wagon-trips: an unknown sort field is a 422", admin.get("/scales/wagon-trips", params={"sort_by": "nope"}, headers=ah).status_code == 422)
ok("wagons: a future-only period is empty", admin.get("/scales/wagons", params={"date_from": (today + timedelta(days=2)).isoformat()}, headers=ah).json().get("total") == 0)
ok("wagons: limit above 500 is a 422", admin.get("/scales/wagons", params={"limit": 501}, headers=ah).status_code == 422, sev="medium")
ok("trains: 200", admin.get("/scales/trains", params={"limit": 3}, headers=ah).status_code == 200)
ok("unmatched: 200", admin.get("/scales/unmatched", params={"limit": 3}, headers=ah).status_code == 200)
ok("corrections: 200", admin.get("/scales/corrections", headers=ah).status_code == 200)

for role in ("operator", "management"):
    c, h = login(role)
    ok(f"{role}: reads the wagon ledger", c.get("/scales/wagons", params={"limit": 1}, headers=h).status_code == 200)
master, mh = login("master")
for path in ("/scales/wagons", "/scales/wagon-trips", "/scales/status"):
    ok(f"master: {path} is forbidden (403)", master.get(path, headers=mh).status_code == 403, master.get(path, headers=mh).status_code)
mgmt, gh = login("management")
ok("management: cannot create a correction (403)", mgmt.post("/scales/corrections", json={"kind": "train_exclude"}, headers=gh).status_code in (403, 422) and mgmt.post("/scales/corrections", json={"kind": "train_exclude"}, headers=gh).status_code == 403)
print("done")

# ── command center: overview and the three cards, cross-checked against the ledger ──
ov = admin.get("/scales/overview", params={"days": 30}, headers=ah)
ok("overview: 200 with kpi, previous, charts", ov.status_code == 200 and {"kpi", "previous", "daily", "hourly", "by_cargo", "top_locomotives", "top_wagons", "today", "quality"} <= set(ov.json()), ov.status_code)
if ov.status_code == 200:
    o = ov.json()
    ok("overview: days=30 spans 30 local days", o["days"] == 30 and (date.fromisoformat(o["date_to"]) - date.fromisoformat(o["date_from"])).days == 29)
    ok("overview: daily tonnes add up to the KPI tonnes (+-1 t)", abs(sum(float(d["tonnes"]) for d in o["daily"]) - float(o["kpi"]["tonnes"])) < 1, o["kpi"]["tonnes"])
    ok("overview: daily trains add up to the KPI trains", sum(d["trains"] for d in o["daily"]) == o["kpi"]["trains"])
    ok("overview: hourly trains add up to the KPI trains", sum(h["trains"] for h in o["hourly"]) == o["kpi"]["trains"])
    ledger_total = admin.get("/scales/wagon-trips", params={"date_from": o["date_from"], "date_to": o["date_to"], "limit": 1}, headers=ah).json()["total"]
    ok("overview: wagon trips of the KPI equal the ledger total for the same days (+-2)", abs(o["kpi"]["wagon_trips"] - ledger_total) <= 2, (o["kpi"]["wagon_trips"], ledger_total))
    ok("overview: shares are within 0..1", all(o["kpi"][k] is None or 0 <= o["kpi"][k] <= 1 for k in ("overload_share", "matched_share", "estimated_share")))
    ok("overview: top locomotives are ranked by tonnes", all(float(a["tonnes"]) >= float(b["tonnes"]) for a, b in zip(o["top_locomotives"], o["top_locomotives"][1:])))
    ok("overview: a 7-day window is not larger than the 30-day one", admin.get("/scales/overview", params={"days": 7}, headers=ah).json()["kpi"]["trains"] <= o["kpi"]["trains"])
    ok("overview: days=0 and days=999 are 422", admin.get("/scales/overview", params={"days": 0}, headers=ah).status_code == 422 and admin.get("/scales/overview", params={"days": 999}, headers=ah).status_code == 422, sev="medium")

    page = admin.get("/scales/trains", params={"match_status": "ok", "limit": 1}, headers=ah).json()
    if page["items"]:
        tid = page["items"][0]["id"]
        tc = admin.get(f"/scales/trains/{tid}", headers=ah)
        ok("train card: 200", tc.status_code == 200, tc.status_code)
        t = tc.json() if tc.status_code == 200 else {}
        ok("train card: units are the weighed units (traction + dump)", len(t.get("units", [])) == t.get("wagon_rows") and sum(1 for u in t["units"] if u["kind"] == "dump") == t["dump_count"])
        ok("train card: carriages come from GTK and are ordered", [c["ord"] for c in t.get("carriages", [])] == sorted(c["ord"] for c in t.get("carriages", [])))
        ok("train card: cargo equals the sum of the dump cars' net (+-0.1 t) when it was weighed", t.get("net_source") != "weighings" or abs(sum(float(u["net_t"] or 0) for u in t["units"] if u["kind"] == "dump") - float(t["net_total_t"])) < 0.1)
        ok("train card: an unknown train is 404", admin.get("/scales/trains/00000000-0000-0000-0000-000000000000", headers=ah).status_code == 404)
        if t.get("prev_id"):
            ok("train card: the previous train exists", admin.get(f"/scales/trains/{t['prev_id']}", headers=ah).status_code == 200)

    if o["top_locomotives"] and o["top_locomotives"][0]["asset_id"]:
        lid = o["top_locomotives"][0]["asset_id"]
        lc = admin.get(f"/scales/loco-card/{lid}", params={"days": 30}, headers=ah)
        ok("loco card: 200", lc.status_code == 200, lc.status_code)
        l = lc.json() if lc.status_code == 200 else {}
        ok("loco card: period trains equal the overview's number for that locomotive", l.get("period", {}).get("trips") == o["top_locomotives"][0]["trains"], (l.get("period", {}).get("trips"), o["top_locomotives"][0]["trains"]))
        ok("loco card: maintenance block is present", "maintenance" in l and "plans" in l["maintenance"] and "work_orders" in l["maintenance"])

    if items:
        w0 = items[0]
        q = {"asset_id": w0["asset_id"]} if w0["asset_id"] else {"carriage_gtk_id": w0["carriage_gtk_id"]}
        wc = admin.get("/scales/wagon-card", params={**q, "days": 30}, headers=ah)
        ok("wagon card: 200", wc.status_code == 200, wc.status_code)
        w = wc.json() if wc.status_code == 200 else {}
        ok("wagon card: period trips equal the ledger total for the same wagon", w.get("period", {}).get("trips") == first["trips"], (w.get("period", {}).get("trips"), first["trips"]))
        ok("wagon card: daily trips add up to the period trips", sum(d["trips"] for d in w.get("daily", [])) == w.get("period", {}).get("trips"))
        ok("wagon card: all-time is not less than the period", w.get("all_time", {}).get("trips", 0) >= w.get("period", {}).get("trips", 0))
        ok("wagon card: linked wagons carry the maintenance block, unlinked ones do not", (w.get("maintenance") is not None) == (w0["asset_id"] is not None))
    ok("wagon card: no key is 422", admin.get("/scales/wagon-card", headers=ah).status_code == 422)
    ok("cards: master is forbidden", all(master.get(p, headers=mh).status_code == 403 for p in ("/scales/overview", "/scales/wagon-card", "/scales/loco-card/00000000-0000-0000-0000-000000000000", "/scales/trains/00000000-0000-0000-0000-000000000000")))
print("done: command center")
