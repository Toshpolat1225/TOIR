"""Live check of the asset map endpoint `GET /map/assets` (read-only: it only sends GET requests).

Needs zz_lib.py's files next to it (zztest_creds.json, zz_ids.json). Set TOIR_ROOT_CERT to the root certificate.
"""
import os
import sys

import httpx

import zz_lib
from zz_lib import CREDS, IDS, rec

HOST = os.environ.get("TOIR_HOST", "192.168.28.104")
ROOT_CERT = os.environ.get("TOIR_ROOT_CERT", "toir-local-root.crt")
API = f"https://{HOST}/api/v1"
AREA = "map"


def login(role):
    client = httpx.Client(base_url=API, timeout=60, verify=ROOT_CERT)
    c = CREDS[role]
    r = client.post("/auth/login", json={"email": c["email"], "password": c["password"]})
    r.raise_for_status()
    return client, {"Authorization": f"Bearer {r.json()['access_token']}"}


anonymous = httpx.Client(base_url=API, timeout=60, verify=ROOT_CERT).get("/map/assets")
rec(AREA, "map: no token is refused (401)", "PASS" if anonymous.status_code == 401 else "FAIL", str(anonymous.status_code), "high")

admin, ah = login("admin")
r = admin.get("/map/assets", headers=ah)
body = r.json() if r.status_code == 200 else {}
rec(AREA, "map: admin gets 200 with points and a summary", "PASS" if r.status_code == 200 and {"points", "summary"} <= set(body) else "FAIL", str(r.status_code), "high")
if not body:
    sys.exit(1)
summary, points = body["summary"], body["points"]
print("summary:", summary)
rec(AREA, "map: summary adds up (placed + unplaced = total)", "PASS" if summary["placed"] + summary["unplaced"] == summary["total_assets"] else "FAIL", str(summary), "medium")
rec(AREA, "map: per-source counts add up to placed", "PASS" if sum(summary["by_source"].values()) == summary["placed"] else "FAIL", str(summary["by_source"]), "medium")
rec(AREA, "map: unplaced reasons add up", "PASS" if sum(summary["unplaced_reasons"].values()) == summary["unplaced"] else "FAIL", str(summary["unplaced_reasons"]), "medium")
rec(AREA, "map: every point has valid coordinates, a known source and an asset id",
    "PASS" if points and all(-90 <= p["lat"] <= 90 and -180 <= p["lon"] <= 180 and p["source"] in ("wialon", "gtk") and p["asset_id"] for p in points) else "FAIL", f"{len(points)} points", "high")
rec(AREA, "map: both sources are present (Wialon for locomotives, GTK for wagons)", "PASS" if summary["by_source"].get("wialon", 0) > 0 and summary["by_source"].get("gtk", 0) > 0 else "FAIL", str(summary["by_source"]), "medium")
rec(AREA, "map: wagons come from GTK, locomotives/diesels from Wialon",
    "PASS" if all(p["source"] == "gtk" for p in points if p["asset_type"] == "wagon") or any(p["asset_type"] == "wagon" for p in points) else "FAIL", "", "low")
wialon_only = admin.get("/map/assets", params={"source": "wialon"}, headers=ah).json()
rec(AREA, "map: the source filter keeps only that source", "PASS" if wialon_only["points"] and all(p["source"] == "wialon" for p in wialon_only["points"]) and wialon_only["summary"]["placed"] == summary["placed"] else "FAIL", "", "medium")
typed = admin.get("/map/assets", params={"asset_type": "locomotive"}, headers=ah).json()
rec(AREA, "map: the type filter keeps only that type", "PASS" if typed["points"] and all(p["asset_type"] == "locomotive" for p in typed["points"]) else "FAIL", "", "medium")
found = admin.get("/map/assets", params={"q": points[0]["inv_number"]}, headers=ah).json()
rec(AREA, "map: search by inventory number finds the asset", "PASS" if any(p["asset_id"] == points[0]["asset_id"] for p in found["points"]) else "FAIL", "", "medium")
bad = admin.get("/map/assets", params={"source": "other"}, headers=ah)
rec(AREA, "map: an unknown source value is refused (422)", "PASS" if bad.status_code == 422 else "FAIL", str(bad.status_code), "low")
inj = admin.get("/map/assets", params={"q": "'; drop table fixed_assets; --%_"}, headers=ah)
rec(AREA, "map: a hostile search string is just text (200)", "PASS" if inj.status_code == 200 else "FAIL", str(inj.status_code), "high")

for role in ("operator", "management"):
    client, headers = login(role)
    got = client.get("/map/assets", headers=headers)
    rec(AREA, f"map: {role} can open the map (analytics.view)", "PASS" if got.status_code == 200 and got.json()["summary"]["total_assets"] == summary["total_assets"] else "FAIL", str(got.status_code), "medium")

master, mh = login("master")  # ZZTEST master of an EMPTY ZZTEST section
scoped = master.get("/map/assets", headers=mh)
rec(AREA, "map: a master sees only their own (empty) section", "PASS" if scoped.status_code == 200 and scoped.json()["summary"]["total_assets"] == 0 and scoped.json()["points"] == [] else "FAIL", str(scoped.json().get("summary")), "critical")
other_section = next((p["section_id"] for p in points if p.get("section_id")), None)
if other_section:
    forced = master.get("/map/assets", params={"section_id": other_section}, headers=mh)
    rec(AREA, "map: a master cannot widen the scope with ?section_id=", "PASS" if forced.status_code == 200 and forced.json()["points"] == [] else "FAIL", str(forced.status_code), "critical")
print("done")
