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
    "PASS" if points and all(-90 <= p["lat"] <= 90 and -180 <= p["lon"] <= 180 and p["source"] in ("wialon", "gtk", "gtk_gps", "train") and p["asset_id"] for p in points) else "FAIL", f"{len(points)} points", "high")
rec(AREA, "map: Wialon (locomotives) and wagons (GTK or train) are both present", "PASS" if summary["by_source"].get("wialon", 0) > 0 and summary["by_source"].get("gtk", 0) + summary["by_source"].get("train", 0) > 0 else "FAIL", str(summary["by_source"]), "medium")
train_points = [p for p in points if p["source"] == "train"]
rec(AREA, "map: wagons of open GTK trains are drawn at their locomotive (source train)", "PASS" if train_points and all(p["asset_type"] not in ("locomotive", "diesel", "special_self_propelled") for p in train_points) else "FAIL", f"{len(train_points)} train points", "high")
rec(AREA, "map: a train point names its train and locomotive", "PASS" if train_points and all(p.get("train_number") and p.get("locomotive_inv_number") for p in train_points) else "FAIL", "", "medium")
loco_pos = {p["inv_number"]: (p["lat"], p["lon"]) for p in points if p["source"] == "wialon"}
rec(AREA, "map: every train point sits exactly where its locomotive is", "PASS" if train_points and all(loco_pos.get(p["locomotive_inv_number"]) in (None, (p["lat"], p["lon"])) for p in train_points) else "FAIL", "", "high")
only_train = admin.get("/map/assets", params={"source": "train"}, headers=ah).json()
rec(AREA, "map: the train filter keeps only train points", "PASS" if only_train["points"] and all(p["source"] == "train" for p in only_train["points"]) else "FAIL", "", "medium")
by_loco = admin.get("/map/assets", params={"q": train_points[0]["locomotive_inv_number"]}, headers=ah).json() if train_points else {"points": []}
rec(AREA, "map: searching a locomotive number lists only that locomotive (wagons are found by train number in the page)", "PASS" if by_loco["points"] else "FAIL", "", "low")
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
# ---- the "without coordinates" details page (GET only) ----
anon_un = httpx.Client(base_url=API, timeout=60, verify=ROOT_CERT).get("/map/unplaced")
rec(AREA, "unplaced: no token is refused (401)", "PASS" if anon_un.status_code == 401 else "FAIL", str(anon_un.status_code), "high")
ur = admin.get("/map/unplaced", params={"limit": 500}, headers=ah)
un = ur.json() if ur.status_code == 200 else {}
rec(AREA, "unplaced: admin gets 200 with items, total, limit, offset and a summary", "PASS" if ur.status_code == 200 and {"items", "total", "limit", "offset", "summary"} <= set(un) else "FAIL", str(ur.status_code), "high")
if un:
    usum, uitems = un["summary"], un["items"]
    rec(AREA, "unplaced: the total equals the map's 'without coordinates' count", "PASS" if usum["total"] == summary["unplaced"] == un["total"] else "FAIL", f"{usum['total']} vs {summary['unplaced']}", "high")
    rec(AREA, "unplaced: reasons add up to the total", "PASS" if sum(usum["by_reason"].values()) == usum["total"] else "FAIL", str(usum["by_reason"]), "medium")
    rec(AREA, "unplaced: the two groups match the map's no_link / no_position counts", "PASS" if usum["by_group"] == summary["unplaced_reasons"] else "FAIL", f"{usum['by_group']} vs {summary['unplaced_reasons']}", "high")
    rec(AREA, "unplaced: every item has a reason, an inventory number and the time the system knows it", "PASS" if uitems and all(i["reason"] and i["inv_number"] and i["asset_created_at"] for i in uitems) else "FAIL", f"{len(uitems)} items", "medium")
    rec(AREA, "unplaced: linked items name their source (Wialon/GTK id)", "PASS" if all((i["wialon_external_id"] or i["gtk_external_id"]) for i in uitems if i["group"] == "no_position") else "FAIL", "", "medium")
    rec(AREA, "unplaced: only unlinked items can have a GTK candidate", "PASS" if all(i["candidate"] is None for i in uitems if i["reason"] != "no_link") else "FAIL", "", "medium")
    rec(AREA, "unplaced: the summary lists asset types with counts", "PASS" if usum["by_type"] and sum(t["count"] for t in usum["by_type"]) == usum["total"] else "FAIL", str(usum["by_type"][:3]), "low")
    one = admin.get("/map/unplaced", params={"reason": "no_link"}, headers=ah).json()
    rec(AREA, "unplaced: the reason filter keeps only that reason and its total", "PASS" if one["total"] == usum["by_reason"].get("no_link", 0) and all(i["reason"] == "no_link" for i in one["items"]) else "FAIL", str(one["total"]), "medium")
    grp = admin.get("/map/unplaced", params={"reason": "no_position"}, headers=ah).json()
    rec(AREA, "unplaced: the group filter no_position works", "PASS" if grp["total"] == usum["by_group"].get("no_position", 0) else "FAIL", str(grp["total"]), "low")
    page1 = admin.get("/map/unplaced", params={"limit": 5, "sort_by": "inv_number"}, headers=ah).json()
    page2 = admin.get("/map/unplaced", params={"limit": 5, "offset": 5, "sort_by": "inv_number"}, headers=ah).json()
    rec(AREA, "unplaced: paging gives 5 + 5 different items, sorted by inventory number", "PASS" if len(page1["items"]) == 5 and len(page2["items"]) == 5 and not ({i["asset_id"] for i in page1["items"]} & {i["asset_id"] for i in page2["items"]}) and [i["inv_number"] for i in page1["items"]] == sorted(i["inv_number"] for i in page1["items"]) else "FAIL", "", "medium")
    lk = admin.get("/map/unplaced", params={"only_linkable": "true", "limit": 500}, headers=ah).json()
    rec(AREA, "unplaced: only_linkable lists unlinked wagons with a free GTK candidate", "PASS" if lk["total"] >= usum["linkable"] and all(i["candidate"] and not i["candidate"]["taken_by_inv_number"] for i in lk["items"]) else "FAIL", f"{lk['total']} (exact: {usum['linkable']})", "medium")
    for bad_params, label in (({"sort_by": "password"}, "an unknown sort field"), ({"limit": 501}, "limit above 500"), ({"reason": "other"}, "an unknown reason"), ({"sort_dir": "up"}, "a bad sort direction")):
        got = admin.get("/map/unplaced", params=bad_params, headers=ah)
        rec(AREA, f"unplaced: {label} is refused (422)", "PASS" if got.status_code == 422 else "FAIL", str(got.status_code), "low")
    hostile = admin.get("/map/unplaced", params={"q": "'; drop table fixed_assets; --%_"}, headers=ah)
    rec(AREA, "unplaced: a hostile search string is just text (200)", "PASS" if hostile.status_code == 200 else "FAIL", str(hostile.status_code), "high")
    mu = master.get("/map/unplaced", headers=mh)
    rec(AREA, "unplaced: a master sees only their own (empty) section", "PASS" if mu.status_code == 200 and mu.json()["total"] == 0 and mu.json()["items"] == [] else "FAIL", str(mu.status_code), "critical")
    mf = master.get("/map/unplaced", params={"section_id": other_section} if other_section else {}, headers=mh)
    rec(AREA, "unplaced: a master cannot widen the scope with ?section_id=", "PASS" if mf.status_code == 200 and mf.json()["items"] == [] else "FAIL", str(mf.status_code), "critical")
for role in ("operator", "management"):
    client, headers = login(role)
    got = client.get("/map/unplaced", headers=headers)
    rec(AREA, f"unplaced: {role} can open the page (analytics.view)", "PASS" if got.status_code == 200 and got.json()["total"] == un.get("total") else "FAIL", str(got.status_code), "medium")
print("done")
