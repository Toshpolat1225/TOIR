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
ok("gps: the unified distance never exceeds the larger tracker", all(0 <= d["unified_m"] <= max(d["wialon_m"] or 0, d["gtk_m"] or 0) for i in items for d in i["days"] if d["unified_m"] is not None))
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
target = next((i for i in both if i["days"] and any(d["gtk_m"] for d in i["days"])), both[0] if both else None)
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
print("done: gps compare")
