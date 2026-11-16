"""Live check of the 2026-11-16 "fix everything" batch: HTTPS, refresh-token reuse, settings range, departments,
section archive guard, hidden AD guid, the schedule's `unforecasted` summary.

Only ZZTEST data is written (a ZZTEST department). Every probe that could change real data is built so that it is
REFUSED when the fix works and is harmless when it does not (invalid body, or an object that is ZZTEST's own).
Needs zz_lib.py's files next to it (zztest_creds.json, zz_ids.json). Set TOIR_ROOT_CERT to the root certificate.
"""
import os
import sys
import time

import httpx

import zz_lib
from zz_lib import CREDS, IDS, rec

HOST = os.environ.get("TOIR_HOST", "192.168.28.104")
ROOT_CERT = os.environ.get("TOIR_ROOT_CERT", "toir-local-root.crt")
HTTP_API = f"http://{HOST}/api/v1"
HTTPS_API = f"https://{HOST}/api/v1"
COOKIE = "toir_refresh_token"
AREA = "fixall"


def login(base, role, verify=True):
    client = httpx.Client(base_url=base, timeout=60, verify=ROOT_CERT if verify else False)
    c = CREDS[role]
    r = client.post("/auth/login", json={"email": c["email"], "password": c["password"]})
    r.raise_for_status()
    return client, r


def auth(client, response):
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def set_cookie_of(response):
    return [v for k, v in response.headers.multi_items() if k.lower() == "set-cookie" and v.startswith(COOKIE)]


def token_of(response):
    cookie = set_cookie_of(response)[0]
    return cookie.split(";", 1)[0].split("=", 1)[1]


def refresh(client, token):
    # explicit Cookie header: the test controls exactly which token is presented
    return client.post("/auth/refresh", headers={"Cookie": f"{COOKIE}={token}"})


# ── HTTPS, verified against the repo's root certificate ───────────────────────────────────────────────────
try:
    https, resp = login(HTTPS_API, "operator", verify=True)
    ok = resp.status_code == 200
    rec(AREA, "https: login works and the certificate verifies against toir-local-root.crt", "PASS" if ok else "FAIL", f"{resp.status_code}", "high")
    cookies = set_cookie_of(resp)
    rec(AREA, "https: the refresh cookie is Secure + HttpOnly + SameSite", "PASS" if cookies and "Secure" in cookies[0] and "HttpOnly" in cookies[0] and "samesite" in cookies[0].lower() else "FAIL", cookies[0].split(";", 1)[1][:120] if cookies else "no cookie", "high")
    me = https.get("/auth/me", headers=auth(https, resp))
    rec(AREA, "https: API answers carry Cache-Control: no-store and a CSP, and no HSTS (decision: HTTP stays)",
        "PASS" if me.headers.get("cache-control") == "no-store" and "frame-ancestors" in me.headers.get("content-security-policy", "") and "strict-transport-security" not in me.headers else "FAIL",
        f"cc={me.headers.get('cache-control')} hsts={me.headers.get('strict-transport-security')}", "medium")
except Exception as exc:  # noqa: BLE001
    rec(AREA, "https login", "FAIL", repr(exc)[:200], "high")
    sys.exit(1)

plain, plain_resp = login(HTTP_API, "operator", verify=False)
plain_cookie = set_cookie_of(plain_resp)
rec(AREA, "http still works and its cookie is NOT Secure (it could not be stored otherwise)", "PASS" if plain_resp.status_code == 200 and plain_cookie and "Secure" not in plain_cookie[0] else "FAIL", "", "high")
redirect = httpx.get(f"http://{HOST}/auth/login", follow_redirects=False, timeout=30)
rec(AREA, "http is not redirected to https", "PASS" if redirect.status_code == 200 else "FAIL", str(redirect.status_code), "medium")

# ── refresh-token reuse ──────────────────────────────────────────────────────────────────────────────
t0 = token_of(resp)
r1 = refresh(https, t0)
rec(AREA, "refresh: a normal rotation works", "PASS" if r1.status_code == 200 and set_cookie_of(r1) else "FAIL", str(r1.status_code), "high")
t1 = token_of(r1)
grace = refresh(https, t0)
rec(AREA, "refresh: the same old token again within seconds is refused", "PASS" if grace.status_code == 401 else "FAIL", str(grace.status_code), "high")
r2 = refresh(https, t1)
rec(AREA, "refresh: the racing second tab's session survives the grace period", "PASS" if r2.status_code == 200 else "FAIL", str(r2.status_code), "high")
t2 = token_of(r2)
print("waiting 33 s so the old token is outside the grace period ...", flush=True)
time.sleep(33)
stolen = refresh(https, t0)
rec(AREA, "refresh: a rotated token replayed after the grace period is refused", "PASS" if stolen.status_code == 401 else "FAIL", str(stolen.status_code), "high")
after = refresh(https, t2)
rec(AREA, "refresh: ... and the user's other (current) session was cut too", "PASS" if after.status_code == 401 else "FAIL", str(after.status_code), "high")

# ── maintenance settings: range (the role guard is covered by a unit test; only refused values are sent) ─────
mgmt, mresp = login(HTTPS_API, "management")
oper, oresp = login(HTTPS_API, "operator")
admin, aresp = login(HTTPS_API, "admin")
before = oper.get("/maintenance-settings", headers=auth(oper, oresp)).json()
for who, client, rsp in (("operator", oper, oresp), ("management", mgmt, mresp)):
    for bad in (1, 4, 1001, 0):
        r = client.patch("/maintenance-settings", json={"daily_average_km": bad}, headers=auth(client, rsp))
        rec(AREA, f"settings: {who} sending {bad} km/day is refused", "PASS" if r.status_code in (403, 422) else "FAIL", str(r.status_code), "high")
unchanged = oper.get("/maintenance-settings", headers=auth(oper, oresp)).json()
rec(AREA, "settings: the live value did not change", "PASS" if unchanged == before else "FAIL", f"{before} -> {unchanged}", "critical")

# ── departments (a ZZTEST one) ───────────────────────────────────────────────────────────────────────────
name = f"ZZTEST-Dept-{int(time.time()) % 100000}"
created = admin.post("/departments", json={"name": name, "color": "#112233"}, headers=auth(admin, aresp))
rec(AREA, "departments: a valid department is created", "PASS" if created.status_code == 201 else "FAIL", f"{created.status_code} {created.text[:120]}", "medium")
dept_id = created.json().get("id") if created.status_code == 201 else None
dup = admin.post("/departments", json={"name": name.lower()}, headers=auth(admin, aresp))
rec(AREA, "departments: the same name in another letter case is refused (409)", "PASS" if dup.status_code == 409 else "FAIL", str(dup.status_code), "medium")
bad_color = admin.post("/departments", json={"name": name + "-c", "color": "red"}, headers=auth(admin, aresp))
rec(AREA, "departments: a colour that is not #RRGGBB is refused (422)", "PASS" if bad_color.status_code == 422 else "FAIL", str(bad_color.status_code), "medium")
if dept_id:
    patch_bad = admin.patch(f"/departments/{dept_id}", json={"color": "javascript:alert(1)"}, headers=auth(admin, aresp))
    rec(AREA, "departments: patching a bad colour is refused (422)", "PASS" if patch_bad.status_code == 422 else "FAIL", str(patch_bad.status_code), "medium")
    patch_ok = admin.patch(f"/departments/{dept_id}", json={"color": "#abcdef"}, headers=auth(admin, aresp))
    rec(AREA, "departments: patching a good colour works", "PASS" if patch_ok.status_code == 200 and patch_ok.json()["color"] == "#abcdef" else "FAIL", str(patch_ok.status_code), "low")

# ── a section with people cannot be archived ────────────────────────────────────────────────────────────
section_a = IDS["sections"]["A"]  # holds the ZZTEST master
r = admin.delete(f"/sections/{section_a}", headers=auth(admin, aresp))
rec(AREA, "sections: archiving a unit that still has an active user is refused with the count (409)", "PASS" if r.status_code == 409 and "active users" in r.text else "FAIL", f"{r.status_code} {r.text[:160]}", "medium")
state = admin.get(f"/sections/{section_a}", headers=auth(admin, aresp)).json()
rec(AREA, "sections: ... and it stayed active", "PASS" if state.get("is_archived") is False else "FAIL", str(state.get("is_archived")), "medium")

# ── the AD guid stays on the server ─────────────────────────────────────────────────────────────────────
users = admin.get("/users", params={"limit": 200}, headers=auth(admin, aresp)).json()
items = users["items"] if isinstance(users, dict) else users
rec(AREA, "users: no `ad_object_guid` in any user, `ad_confirmed` is a boolean everywhere",
    "PASS" if items and all("ad_object_guid" not in u and isinstance(u.get("ad_confirmed"), bool) for u in items) else "FAIL", f"{len(items)} users", "medium")
mine = oper.get("/auth/me", headers=auth(oper, oresp)).json()
rec(AREA, "/auth/me does not return the guid either", "PASS" if "ad_object_guid" not in mine and "ad_confirmed" in mine else "FAIL", "", "medium")

# ── the schedule explains its gaps ──────────────────────────────────────────────────────────────────────
month = time.strftime("%Y-%m")
sched = admin.get("/maintenance-schedule", params={"month": month}, headers=auth(admin, aresp))
body = sched.json() if sched.status_code == 200 else {}
fields = {"unforecasted", "unforecasted_total", "unforecasted_counts"} <= set(body)
rec(AREA, "schedule: carries unforecasted / unforecasted_total / unforecasted_counts", "PASS" if fields else "FAIL", f"{sched.status_code} keys={sorted(body)[:6]}", "medium")
if fields:
    rows = body["unforecasted"]
    consistent = body["unforecasted_total"] >= len(rows) and sum(body["unforecasted_counts"].values()) == body["unforecasted_total"] and len(rows) <= 300
    allowed = {"no_movement", "no_mileage_baseline", "no_mileage", "no_data"}
    rec(AREA, "schedule: the summary is consistent (counts add up, capped, known reasons)", "PASS" if consistent and all(x["reason"] in allowed for x in rows) else "FAIL", f"total={body['unforecasted_total']} counts={body['unforecasted_counts']}", "medium")
    master, mrsp = login(HTTPS_API, "master")
    scoped = master.get("/maintenance-schedule", params={"month": month}, headers=auth(master, mrsp)).json()
    rec(AREA, "schedule: a master (empty ZZTEST section) sees no unforecasted units of other sections", "PASS" if scoped.get("unforecasted_total") == 0 else "FAIL", str(scoped.get("unforecasted_total")), "high")
    print("unforecasted now:", body["unforecasted_total"], body["unforecasted_counts"])

print("done")
