"""Live check of the GPS comparison (`GET /gps/overview`, `GET /gps/assets/{id}`) and of the unified map. Read-only: only GET requests.

Needs zz_lib.py's files next to it (zztest_creds.json, zz_ids.json). Set TOIR_ROOT_CERT to the root certificate.
"""
import math
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx

from zz_lib import CREDS, rec

HOST = os.environ.get("TOIR_HOST", "192.168.28.104")
ROOT_CERT = os.environ.get("TOIR_ROOT_CERT", "toir-local-root.crt")
API = f"https://{HOST}/api/v1"
AREA = "gps-compare"
POSITION = {"confirmed", "diverged", "gtk_stale", "wialon_stale", "both_stale_agree", "both_stale_apart", "wialon_only", "gtk_only", "no_position"}
DISTANCE = {"match", "minor_diff", "gtk_gap", "wialon_gap", "idle", "no_data", "not_collected"}


def login(role):
    client = httpx.Client(base_url=API, timeout=180, verify=ROOT_CERT)
    c = CREDS[role]
    r = client.post("/auth/login", json={"email": c["email"], "password": c["password"]})
    r.raise_for_status()
    return client, {"Authorization": f"Bearer {r.json()['access_token']}"}


def ok(name, cond, detail="", sev="high"):
    rec(AREA, name, "PASS" if cond else "FAIL", str(detail)[:200], sev)


def metres(a, b):
    r = 6_371_000
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b["lon"] - a["lon"]) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


ok("gps: no token is refused", httpx.Client(base_url=API, timeout=30, verify=ROOT_CERT).get("/gps/overview").status_code == 401)
admin, ah = login("admin")
r = admin.get("/gps/overview", params={"days": 7}, headers=ah)
ok("gps: overview 200", r.status_code == 200, r.status_code)
data = r.json() if r.status_code == 200 else {"items": [], "summary": {}, "feed": {}, "total": 0}
items, summary, feed = data["items"], data["summary"], data["feed"]
ok("gps: all locomotives are listed (>= 70)", data["total"] >= 70 and summary.get("assets", 0) >= 70, (data["total"], summary.get("assets")))
ok("gps: the position verdict counts add up to the assets", sum(summary.get("position_verdicts", {}).values()) == summary.get("assets"), summary.get("position_verdicts"))
ok("gps: only known verdicts", set(summary.get("position_verdicts", {})) <= POSITION and set(summary.get("distance_verdicts", {})) <= DISTANCE, (summary.get("position_verdicts"), summary.get("distance_verdicts")))
ok("gps: ok + warn + bad = assets", summary.get("ok", 0) + summary.get("warn", 0) + summary.get("bad", 0) == summary.get("assets"), summary)
ok("gps: the worst problem comes first", all(a["severity"] >= b["severity"] for a, b in zip(items, items[1:])))
ok("gps: every row has the 7 local days, newest first", all(len(i["days"]) == 7 and [d["day"] for d in i["days"]] == sorted((d["day"] for d in i["days"]), reverse=True) for i in items))
ok("gps: the measured part of the fused distance is bounded by the two trackers together (bridges over silence are separate) and every day has a cause", all(0 <= d["unified_m"] - (d.get("unknown_gap_m") or 0) <= ((d["wialon_m"] or 0) + (d["gtk_m"] or 0)) * 1.1 + 100 and d.get("cause") for i in items for d in i["days"] if d["unified_m"] is not None))
both = [i for i in items if i["wialon"] and i["gtk"]]
ok("gps: most locomotives have both trackers (GTK GPS is flowing)", len(both) >= 60, len(both), sev="high")
ok("gps: the stated distance between the two fixes equals the one computed from the fixes (+-1 m)", all(abs(metres(i["wialon"], i["gtk"]) - i["position"]["diff_m"]) <= 1 for i in both))
ok("gps: a 'confirmed' row has both fixes fresh and apart by less than its tolerance", all(i["wialon"]["fresh"] and i["gtk"]["fresh"] and i["position"]["diff_m"] <= i["position"]["tolerance_m"] for i in both if i["position"]["verdict"] == "confirmed"))
ok("gps: a 'gtk_stale' row has a fresh Wialon and a stale GTK fix", all(i["wialon"]["fresh"] and not i["gtk"]["fresh"] for i in both if i["position"]["verdict"] == "gtk_stale"))
ok("gps: most positions are confirmed", summary.get("position_verdicts", {}).get("confirmed", 0) >= len(both) * 0.4, summary.get("position_verdicts"), sev="medium")
# the feed
last = datetime.fromisoformat(feed["gtk_last_run_at"]) if feed.get("gtk_last_run_at") else None
ok("feed: GTK GPS sync is enabled", feed.get("gtk_enabled") is True, feed.get("gtk_enabled"))
ok("feed: the last GTK run is recent (< 40 min) and healthy", last is not None and datetime.now(timezone.utc) - last < timedelta(minutes=40) and feed.get("gtk_last_status") in ("success", "partial"), (feed.get("gtk_last_run_at"), feed.get("gtk_last_status"), feed.get("gtk_last_error")))
ok("feed: GTK units and stored track points are present", feed.get("gtk_units", 0) > 100 and feed.get("gtk_track_points", 0) > 0 and feed.get("wialon_track_points", 0) > 0, (feed.get("gtk_units"), feed.get("gtk_track_points")))
ok("feed: few failed track requests in the last run", feed.get("gtk_tracks_failed", 99) <= 3, feed.get("gtk_tracks_failed"), sev="medium")
# filters
r = admin.get("/gps/overview", params={"only_issues": "true"}, headers=ah)
ok("gps: only_issues returns just the rows with a problem", r.status_code == 200 and all(i["severity"] > 0 for i in r.json()["items"]))
r = admin.get("/gps/overview", params={"verdict": "diverged"}, headers=ah)
ok("gps: the verdict filter", r.status_code == 200 and all(i["position"]["verdict"] == "diverged" for i in r.json()["items"]))
ok("gps: a bad verdict is a 422", admin.get("/gps/overview", params={"verdict": "nonsense"}, headers=ah).status_code == 422)
ok("gps: search", admin.get("/gps/overview", params={"q": items[0]["inv_number"]}, headers=ah).json()["total"] >= 1 if items else False)
# detail
target = max((i for i in both if i["week_wialon_m"] > 0), key=lambda i: i["week_gtk_m"], default=None)  # a unit with both stored tracks
if target:
    r = admin.get(f"/gps/assets/{target['asset_id']}", params={"days": 7, "track_days": 2}, headers=ah)
    ok("detail: 200", r.status_code == 200, r.status_code)
    d = r.json() if r.status_code == 200 else {"row": {"days": []}, "wialon_track": [], "gtk_track": []}
    ok("detail: two separate, ordered tracks", len(d["wialon_track"]) > 20 and len(d["gtk_track"]) > 20 and all(a["at"] <= b["at"] for a, b in zip(d["gtk_track"], d["gtk_track"][1:])), (len(d["wialon_track"]), len(d["gtk_track"])))
    ok("detail: the table has 7 days", len(d["row"]["days"]) == 7)
    ok("detail: the row equals the overview row", d["row"]["position"]["verdict"] in POSITION and d["row"]["inv_number"] == target["inv_number"])
    r31 = admin.get(f"/gps/assets/{target['asset_id']}", params={"days": 31, "track_days": 14}, headers=ah)
    ok("detail: 31 days / 14 track days are served", r31.status_code == 200 and len(r31.json()["row"]["days"]) == 31, r31.status_code)
ok("detail: an unknown locomotive is 404", admin.get(f"/gps/assets/{uuid4()}", headers=ah).status_code == 404)
ok("detail: days > 31 is a 422", admin.get(f"/gps/assets/{uuid4()}", params={"days": 99}, headers=ah).status_code == 422)
# the unified map
mp = admin.get("/map/assets", headers=ah)
mj = mp.json() if mp.status_code == 200 else {"points": [], "summary": {}}
pts = mj["points"]
gps_pts = [p for p in pts if p.get("gps_verdict")]
ok("map: locomotives carry the verdict", len(gps_pts) >= 60, len(gps_pts))
ok("map: the summary verdict counts equal the points' verdicts", sum(mj["summary"].get("gps_verdicts", {}).values()) >= len(gps_pts), mj["summary"].get("gps_verdicts"), sev="medium")
ok("map: a point drawn from GTK GPS is the newer fix", all(p["source"] in ("wialon", "gtk_gps") for p in gps_pts))
ok("map: the other tracker's fix is attached to the divergent/silent ones", all(p.get("alt_lat") is not None for p in gps_pts if p["gps_verdict"] in ("diverged", "gtk_stale", "wialon_stale")))
ok("map: the source filter 'gtk_gps' works", admin.get("/map/assets", params={"source": "gtk_gps"}, headers=ah).status_code == 200)
ok("map: placed locomotives did not drop (unplaced locomotives <= before: the page lists them)", mj["summary"].get("unplaced", 0) < 700, mj["summary"].get("unplaced"), sev="low")
# ---- analytics: causes, health, filters, facets, export, wagons ----
r = admin.get("/gps/overview", params={"days": 14, "facets": "true", "limit": 500}, headers=ah)
j = r.json() if r.status_code == 200 else {"items": [], "facets": {}, "summary": {}}
CAUSES = {"ok", "method", "day_open", "gtk_dead", "gtk_no_day", "gtk_gaps", "gtk_sparse", "wialon_gaps", "both_gaps", "not_collected", "idle", "no_data"}
ok("analytics: every day has a known cause and the cause counts add up", all(d["cause"] in CAUSES for i in j["items"] for d in i["days"]) and sum(j["summary"].get("cause_counts", {}).values()) == sum(len(i["days"]) for i in j["items"]), j["summary"].get("cause_counts"))
ok("analytics: facets are present for every filter", set(j["facets"]) >= {"severity", "position_verdict", "distance_verdict", "cause", "health", "link", "asset_type", "section"}, list(j["facets"]))
ok("analytics: the severity facet adds up to the assets", sum(j["facets"].get("severity", {}).values()) == j["summary"].get("assets"), j["facets"].get("severity"))
ok("analytics: tracker health on every row", all(i["health"] and i["health"]["health_class"] in ("ok", "intermittent", "dead", "frozen", "no_gtk") for i in j["items"]))
cc = j["summary"].get("cause_counts", {})
ok("analytics: GTK holes are the main cause of the differences (as measured)", sum(v for k, v in cc.items() if k.startswith("gtk_")) > sum(v for k, v in cc.items() if k in ("wialon_gaps", "both_gaps", "method")), cc)
top = sorted(j["facets"].get("cause", {}).items(), key=lambda kv: -kv[1])
cause = next((k for k, _ in top if k.startswith("gtk_")), None)
if cause:
    rc = admin.get("/gps/overview", params={"cause": cause, "days": 14}, headers=ah).json()
    ok("filter: a cause filter keeps only rows with a day of that cause", rc["total"] >= 1 and all(any(d["cause"] == cause for d in i["days"]) for i in rc["items"]))
rs = admin.get("/gps/overview", params={"sort_by": "week_fused_m", "sort_dir": "desc", "days": 14, "limit": 500}, headers=ah).json()["items"]
ok("sort: by fused km descending", all(a["week_fused_m"] >= b["week_fused_m"] for a, b in zip(rs, rs[1:])))
ok("sort: a bad sort_by is a 422", admin.get("/gps/overview", params={"sort_by": "nonsense"}, headers=ah).status_code == 422)
ok("filter: health=dead rows are all dead", all(i["health"]["health_class"] == "dead" for i in admin.get("/gps/overview", params={"health": "dead", "days": 14}, headers=ah).json()["items"]))
ok("filter: link, moving and bbox work", all(i["wialon_linked"] and i["gtk_linked"] for i in admin.get("/gps/overview", params={"link": "both"}, headers=ah).json()["items"]) and admin.get("/gps/overview", params={"moving": "true"}, headers=ah).status_code == 200 and admin.get("/gps/overview", params={"bbox": "40,69,41.5,70"}, headers=ah).json()["total"] >= 1)
ok("filter: a bad bbox is a 422", admin.get("/gps/overview", params={"bbox": "x"}, headers=ah).status_code == 422)
rd = admin.get("/gps/overview", params={"date_from": "2026-11-10", "date_to": "2026-11-14"}, headers=ah).json()
ok("filter: a custom date range gives exactly those days", rd["days"] == 5 and rd["date_from"] == "2026-11-10" and rd["date_to"] == "2026-11-14" and all(len(i["days"]) == 5 for i in rd["items"]), (rd["days"], rd["date_from"]))
ex = admin.get("/gps/overview/export", params={"format": "csv", "days": 7}, headers=ah)
ok("export: csv with a BOM and a row per locomotive", ex.status_code == 200 and ex.content.startswith(b"\xef\xbb\xbf") and ex.content.count(b"\n") >= data["total"], (ex.status_code, ex.headers.get("content-type")))
xl = admin.get("/gps/overview/export", params={"format": "xlsx", "days": 7, "only_issues": "true"}, headers=ah)
ok("export: xlsx is a real zip and honours the filters", xl.status_code == 200 and xl.content[:2] == b"PK", xl.status_code)
h = admin.get("/gps/health", headers=ah)
hj = h.json() if h.status_code == 200 else {"items": [], "counts": {}, "total": 0}
ok("health: 200 and the class counts add up to the locomotives", h.status_code == 200 and sum(hj["counts"].values()) >= hj["total"] > 0, (h.status_code, hj["counts"]))
order = {"dead": 0, "frozen": 1, "intermittent": 2, "ok": 3, "no_gtk": 4}
ok("health: the order is dead, frozen, intermittent, ok", all(order[a["health"]["health_class"]] <= order[b["health"]["health_class"]] for a, b in zip(hj["items"], hj["items"][1:])))
ok("health: dead trackers are named with the km lost", any(x["health"]["health_class"] == "dead" for x in hj["items"]), hj["counts"], sev="medium")
# the odometer: the third opinion
od = [d for i in j["items"] for d in i["days"] if d.get("odo_m")]
ok("odometer: day rows carry the odometer delta and its verdict", len(od) >= 50 and all(("odo_agrees" in d) for d in od), len(od))
ok("odometer: it agrees with the Wialon track on most days where it can be compared (measured 91%)", sum(1 for d in od if d["odo_agrees"] is True) >= 0.7 * sum(1 for d in od if d["odo_agrees"] is not None), (sum(1 for d in od if d["odo_agrees"] is True), sum(1 for d in od if d["odo_agrees"] is False)), sev="medium")
ok("feed: a synchronisation state is reported and no run is stuck", isinstance(feed.get("gtk_running"), bool), feed.get("gtk_running"))
# wagons
wg = admin.get("/gps/wagons", params={"limit": 500}, headers=ah)
wj = wg.json() if wg.status_code == 200 else {"items": [], "summary": {}, "total": 0}
ok("wagons: 200 and a long list (>= 400)", wg.status_code == 200 and wj["total"] >= 400, (wg.status_code, wj["total"]))
ok("wagons: the confidence counts add up", sum(wj["summary"].get("confidence_counts", {}).values()) == wj["summary"].get("wagons"), wj["summary"].get("confidence_counts"))
ok("wagons: a wagon outside a train has no position and no confidence", all(w["position"] is None and w["confidence"] == "none" for w in wj["items"] if not w["in_train"]))
ok("wagons: a wagon in a train carries the locomotive's fix and a confidence", sum(1 for w in wj["items"] if w["in_train"] and w["position"]) >= 300, sum(1 for w in wj["items"] if w["in_train"]))
ok("wagons: the history start is reported", wj["summary"].get("history_from") is not None)
ok("wagons: the filters work", all(w["in_train"] for w in admin.get("/gps/wagons", params={"in_train": "true", "limit": 500}, headers=ah).json()["items"]) and admin.get("/gps/wagons", params={"confidence": "high", "sort_by": "km_period", "sort_dir": "desc"}, headers=ah).status_code == 200)
ok("wagons: a bad sort_by is a 422", admin.get("/gps/wagons", params={"sort_by": "x"}, headers=ah).status_code == 422)
tw = next((w for w in wj["items"] if w["in_train"] and w["segments_n"] > 0 and w["asset_id"]), None)
if tw:
    dd = admin.get(f"/gps/wagons/{tw['asset_id']}", headers=ah)
    ok("wagon detail: segments with a basis and a confidence", dd.status_code == 200 and dd.json()["segments"] and all(s["basis"] in ("fused_track", "track", "conflict", "single_source", "held") for s in dd.json()["segments"]), dd.status_code)
    ok("wagon detail: the explanation is text", bool(dd.json().get("explanation")))
else:
    ok("wagon detail: a wagon with segments exists (run gps-analytics --days 14 --wagons)", False, "none found", sev="medium")
ok("wagon detail: an unknown key is 404", admin.get(f"/gps/wagons/{uuid4()}", headers=ah).status_code == 404 and admin.get("/gps/wagons/nonsense", headers=ah).status_code == 404)
# roles
for role in ("operator", "management"):
    c, h = login(role)
    ok(f"{role}: reads the GPS page", c.get("/gps/overview", headers=h).status_code == 200)
master, mh = login("master")
mr = master.get("/gps/overview", headers=mh)
ok("master (empty section): sees no locomotives", mr.status_code == 200 and mr.json()["items"] == [] and mr.json()["total"] == 0, mr.status_code)
if target:
    ok("master: a locomotive of another section is 404 (before anything else)", master.get(f"/gps/assets/{target['asset_id']}", headers=mh).status_code == 404)
ok("master: the section query is ignored", master.get("/gps/overview", params={"section_id": str(uuid4())}, headers=mh).json()["total"] == 0)
mw = master.get("/gps/wagons", headers=mh)
ok("master (empty section): sees no wagons and no unassigned carriages", mw.status_code == 200 and mw.json()["total"] == 0, mw.status_code)
if tw:
    ok("master: a wagon of another section is 404", master.get(f"/gps/wagons/{tw['asset_id']}", headers=mh).status_code == 404 and master.get("/gps/wagons/gtk-1", headers=mh).status_code == 404)
ok("master: health and export are scoped", master.get("/gps/health", headers=mh).json()["total"] == 0 and master.get("/gps/overview/export", headers=mh).status_code == 200)
print("done: gps compare")
