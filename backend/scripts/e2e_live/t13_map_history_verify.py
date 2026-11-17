"""Live check of the asset history endpoint `GET /map/history` (read-only: it only sends GET requests).

Needs zz_lib.py's files next to it (zztest_creds.json, zz_ids.json). Set TOIR_ROOT_CERT to the root certificate.
"""
import os
from datetime import datetime

import httpx

from zz_lib import CREDS, rec

HOST = os.environ.get("TOIR_HOST", "192.168.28.104")
ROOT_CERT = os.environ.get("TOIR_ROOT_CERT", "toir-local-root.crt")
API = f"https://{HOST}/api/v1"
AREA = "map-history"
LOCO = ("locomotive", "diesel", "special_self_propelled")


def login(role):
    client = httpx.Client(base_url=API, timeout=120, verify=ROOT_CERT)
    c = CREDS[role]
    r = client.post("/auth/login", json={"email": c["email"], "password": c["password"]})
    r.raise_for_status()
    return client, {"Authorization": f"Bearer {r.json()['access_token']}"}


def ok(name, cond, detail="", sev="high"):
    rec(AREA, name, "PASS" if cond else "FAIL", str(detail)[:200], sev)


def when(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


anon = httpx.Client(base_url=API, timeout=30, verify=ROOT_CERT)
ok("history: no token is refused", anon.get("/map/history", params={"asset_id": "x"}).status_code == 401)

admin, ah = login("admin")
points = admin.get("/map/assets", headers=ah).json()["points"]
locos = [p for p in points if p["asset_type"] in LOCO and p["source"] == "wialon"]
wagons = [p for p in points if p["source"] == "train" and p.get("locomotive_asset_id")]
ok("map: there are locomotives and wagons in trains to inspect", bool(locos) and bool(wagons), (len(locos), len(wagons)))

ok("history: no id is 422", admin.get("/map/history", headers=ah).status_code == 422)
ok("history: days=0 and days=91 are 422", admin.get("/map/history", params={"asset_id": locos[0]["asset_id"], "days": 0}, headers=ah).status_code == 422 and admin.get("/map/history", params={"asset_id": locos[0]["asset_id"], "days": 91}, headers=ah).status_code == 422, sev="medium")
ok("history: an unknown asset is 404", admin.get("/map/history", params={"asset_id": "00000000-0000-0000-0000-000000000000"}, headers=ah).status_code == 404)

# the locomotive with the most wagons now
by_loco = {}
for w in wagons:
    by_loco.setdefault(w["locomotive_asset_id"], []).append(w)
loco_id, loco_wagons = max(by_loco.items(), key=lambda kv: len(kv[1]))
lr = admin.get("/map/history", params={"asset_id": loco_id, "days": 7}, headers=ah)
ok("locomotive history: 200", lr.status_code == 200, lr.status_code)
lh = lr.json() if lr.status_code == 200 else {}
ok("locomotive history: kind and identity", lh.get("kind") == "locomotive" and lh.get("asset", {}).get("asset_id") == loco_id)
ok("locomotive history: the Wialon backfill gave it a track (>20 points, time-ordered)", len(lh.get("track", [])) > 20 and all(when(a["at"]) <= when(b["at"]) for a, b in zip(lh["track"], lh["track"][1:])), len(lh.get("track", [])))
ok("locomotive history: track points are real coordinates", all(-90 <= p["lat"] <= 90 and -180 <= p["lon"] <= 180 and not (p["lat"] == 0 and p["lon"] == 0) for p in lh.get("track", [])))
ok("locomotive history: it heads an open train with the wagons the map shows (±2)", any(s["is_open"] and abs(s["cars"] - len(loco_wagons)) <= 2 for s in lh.get("segments", [])), [(s["is_open"], s["cars"]) for s in lh.get("segments", [])][:3])
ok("locomotive history: segments are newest first", all(when(a["from_at"]) >= when(b["from_at"]) for a, b in zip(lh.get("segments", []), lh.get("segments", [])[1:])))
ok("locomotive history: an open segment lists the wagons it pulls", any(s["wagons"] for s in lh.get("segments", []) if s["is_open"]))
ok("locomotive history: stats add up (segments, km >= 0)", lh.get("stats", {}).get("segments") == len(lh.get("segments", [])) and lh["stats"]["km"] >= 0)
ok("locomotive history: GTK/track start dates are reported", lh.get("gtk_history_from") is not None and lh.get("track_from") is not None)

# a wagon of that train
w0 = loco_wagons[0]
wr = admin.get("/map/history", params={"asset_id": w0["asset_id"], "days": 7}, headers=ah)
ok("wagon history: 200", wr.status_code == 200, wr.status_code)
wh = wr.json() if wr.status_code == 200 else {}
ok("wagon history: kind wagon with an open segment behind the same locomotive", wh.get("kind") == "wagon" and any(s["is_open"] and s["loco_asset_id"] == loco_id for s in wh.get("segments", [])), [(s["is_open"], s["loco_asset_id"]) for s in wh.get("segments", [])][:3])
ok("wagon history: its position comes from the locomotive's track (source loco)", any(p["source"] == "loco" for p in wh.get("track", [])), len(wh.get("track", [])))
ok("wagon history: the current position is inside a train", bool(wh.get("current")) and wh["current"]["in_train"] is True)
ok("wagon history: by_loco hours add up to the coupled hours (±0.2)", abs(sum(x["hours"] for x in wh.get("by_loco", [])) - wh.get("stats", {}).get("coupled_hours", 0)) < 0.2)
ok("wagon history: every segment says moving / standing / unknown", all(s["activity"] in {"moving", "standing", "unknown"} for s in wh.get("segments", [])))
ok("wagon history: a longer period never loses segments", len(admin.get("/map/history", params={"asset_id": w0["asset_id"], "days": 30}, headers=ah).json()["segments"]) >= len(wh.get("segments", [])))

# an unlinked wagon is reachable through its GTK carriage id
gtk_wagon = admin.get("/scales/wagons", params={"limit": 50}, headers=ah).json()["items"]
unlinked = next((w for w in gtk_wagon if w["asset_id"] is None), None)
if unlinked:
    ur = admin.get("/map/history", params={"carriage_gtk_id": unlinked["carriage_gtk_id"], "days": 7}, headers=ah)
    ok("unlinked wagon: history by GTK carriage id is 200 and has no asset", ur.status_code == 200 and ur.json()["asset"] is None and ur.json()["kind"] == "wagon", ur.status_code)
else:
    rec(AREA, "unlinked wagon: none in the ranking", "INFO", "")

for role in ("operator", "management"):
    c, h = login(role)
    ok(f"{role}: reads the history", c.get("/map/history", params={"asset_id": loco_id, "days": 1}, headers=h).status_code == 200)
master, mh = login("master")
ok("master: another section's asset is 404 (not even confirmed to exist)", master.get("/map/history", params={"asset_id": loco_id}, headers=mh).status_code == 404)
ok("master: an unlinked GTK wagon is 404", master.get("/map/history", params={"carriage_gtk_id": 1}, headers=mh).status_code == 404)
print("done: map history")
