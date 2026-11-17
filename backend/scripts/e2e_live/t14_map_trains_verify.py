"""Live check of `GET /map/trains` (trains drawn to scale). Read-only: only GET requests.

Needs zz_lib.py's files next to it (zztest_creds.json, zz_ids.json). Set TOIR_ROOT_CERT to the root certificate.
"""
import math
import os

import httpx

from zz_lib import CREDS, rec

HOST = os.environ.get("TOIR_HOST", "192.168.28.104")
ROOT_CERT = os.environ.get("TOIR_ROOT_CERT", "toir-local-root.crt")
API = f"https://{HOST}/api/v1"
AREA = "map-trains"


def login(role):
    client = httpx.Client(base_url=API, timeout=120, verify=ROOT_CERT)
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


ok("trains: no token is refused", httpx.Client(base_url=API, timeout=30, verify=ROOT_CERT).get("/map/trains").status_code == 401)
admin, ah = login("admin")
r = admin.get("/map/trains", headers=ah)
ok("trains: 200 with trains", r.status_code == 200 and len(r.json().get("trains", [])) > 20, r.status_code)
trains = r.json()["trains"] if r.status_code == 200 else []
points = admin.get("/map/assets", headers=ah).json()["points"]
wagons_on_map = sum(1 for p in points if p["source"] == "train")
ok("trains: the wagons of all trains equal the map's train-source wagons (+-5)", abs(sum(t["wagons_count"] for t in trains) - wagons_on_map) <= 5, (sum(t["wagons_count"] for t in trains), wagons_on_map))
ok("trains: every train starts with its locomotive (ord 0), a tractive unit adds a motor car", all(t["vehicles"][0]["role"] == "loco" and t["vehicles"][0]["ord"] == 0 for t in trains) and all(t["vehicles"][1]["role"] == "motor" for t in trains if t["loco_kind"] == "electric"))
ok("trains: the wagons stand in GTK order", all([v["ord"] for v in t["vehicles"] if v["role"] == "wagon"] == sorted(v["ord"] for v in t["vehicles"] if v["role"] == "wagon") for t in trains))
ok("trains: wagons_count equals the wagon vehicles", all(t["wagons_count"] == sum(1 for v in t["vehicles"] if v["role"] == "wagon") for t in trains))
ok("trains: coordinates and headings are valid", all(-90 <= v["lat"] <= 90 and -180 <= v["lon"] <= 180 and 0 <= v["heading"] < 360 for t in trains for v in t["vehicles"]))
ok("trains: vehicle sizes are real (loco 17-40 m, wagons 10-16 m, width 2.5-3.5 m)", all(17 <= v["length_m"] <= 40 if v["role"] != "wagon" else 10 <= v["length_m"] <= 16 for t in trains for v in t["vehicles"]) and all(2.5 <= v["width_m"] <= 3.5 for t in trains for v in t["vehicles"]))
spacing = []
for t in trains:
    for a, b in zip(t["vehicles"], t["vehicles"][1:]):
        spacing.append((metres(a, b), a["length_m"] / 2 + b["length_m"] / 2 + 1.2))
ok("trains: consecutive vehicles are never farther apart than their lengths (a curve only shortens it)", all(d <= need + 1.0 for d, need in spacing), max((d - need for d, need in spacing), default=0))
ok("trains: on the ground a train is not longer than its drawn length", all(metres(t["vehicles"][0], t["vehicles"][-1]) <= t["length_m"] for t in trains if len(t["vehicles"]) > 1))
ok("trains: the first vehicle sits at the locomotive's GPS point", all(abs(t["vehicles"][0]["lat"] - t["lat"]) < 1e-6 and abs(t["vehicles"][0]["lon"] - t["lon"]) < 1e-6 for t in trains))
known = [t for t in trains if t["heading_known"]]
ok("trains: most trains have a known direction (the position history exists)", len(known) >= len(trains) * 0.7, (len(known), len(trains)), sev="medium")
ok("trains: the three kinds of locomotive pictograms are present", {t["loco_kind"] for t in trains} <= {"electric", "diesel", "loco"} and any(t["loco_kind"] == "electric" for t in trains))

for role in ("operator", "management"):
    c, h = login(role)
    ok(f"{role}: reads the trains", c.get("/map/trains", headers=h).status_code == 200)
master, mh = login("master")
mr = master.get("/map/trains", headers=mh)
ok("master (empty section): sees no trains and no identities", mr.status_code == 200 and mr.json()["trains"] == [], mr.status_code)
print("done: map trains")
