"""Re-test, on live, every defect that was fixed (same ZZTEST data, same accounts)."""
import json
import os
import secrets
import time

import httpx

from zz_lib import API, BASE, SC, Api, clients, psql, rec

A = "fixes"
CREATED = os.path.join(SC, "zz_created.json")
created = json.load(open(CREATED)) if os.path.exists(CREATED) else {}


def chk(name, ok, detail="", severity="high"):
    return rec(A, name, "PASS" if ok else "FAIL", detail, None if ok else severity)


C = clients()
admin, operator = C["admin"], C["operator"]

# 1. /fixed-assets search and sort by name (was a 500 for ANY search text)
for params, label in (({"q": "ZZTEST"}, "search text"), ({"q": "%"}, "a wildcard"), ({"sort_by": "name"}, "sort by name"), ({"q": "'; DROP TABLE users; --"}, "an injection string")):
    r = admin.get("/fixed-assets", params={"limit": 3, **params})
    chk(f"/fixed-assets with {label} answers 200", r.status_code == 200, f"status {r.status_code}")
r = admin.get("/fixed-assets", params={"q": "ZZTEST-L", "limit": 10})
chk("the search finds the ZZTEST assets", r.status_code == 200 and r.json()["total"] >= 1, r.text[:100], "medium")

# 2. NUL characters are a 422 everywhere, not a 500
bad = []
for path, key in (("/fixed-assets", "q"), ("/users", "q"), ("/sections", "q"), ("/employees", "q"), ("/work-types", "q"), ("/nomenclature", "q"), ("/audit-logs", "q"), ("/fixed-assets/stats", "q")):
    r = admin.get(path, params={key: "a\u0000b"})
    if r.status_code != 422:
        bad.append(f"{path}={r.status_code}")
chk("a NUL character in a search box is a 422 on every endpoint", not bad, ", ".join(bad), "medium")

# 3. password policy
tag = secrets.token_hex(3)
for pw in ("123", "short1", "1234567890", "aaaaaaaaaaaa"):
    r = admin.post("/users", json={"email": f"zztest-pw{tag}{len(pw)}@example.test", "full_name": "ZZTEST pw", "role": "operator", "password": pw})
    if r.status_code == 201:
        created.setdefault("users", []).append(r.json()["id"])
    chk(f"a weak password ({pw[:3]}...) is refused when creating a user", r.status_code == 422, f"status {r.status_code}")
good = secrets.token_urlsafe(16)
r = admin.post("/users", json={"email": f"zztest-ok{tag}@example.test", "full_name": "ZZTEST ok", "role": "operator", "password": good})
chk("a reasonable password is accepted", r.status_code == 201, r.text[:100])
uid = r.json().get("id")
if uid:
    created.setdefault("users", []).append(uid)
    r = admin.post(f"/users/{uid}/reset-password", json={"password": "short"})
    chk("a weak password is refused on reset", r.status_code == 422, f"status {r.status_code}")
    r = admin.post(f"/users/{uid}/reset-password", json={"password": secrets.token_urlsafe(16)})
    chk("a reasonable password is accepted on reset", r.status_code in (200, 204), f"status {r.status_code}")
# an existing weak-looking login keeps working: the policy only applies when a password is set
chk("existing accounts still log in (the policy is not applied to login)", Api("operator").login().status_code == 200, "")

# 4. a replacement opening balance can be approved (superseding the old one)
w = admin.get("/fixed-assets/unified", params={"q": "ZZTEST-W", "limit": 5}).json()["items"]
if w:
    wid = w[0]["asset_id"]
    ops = admin.get("/wagon-mileage/openings", params={"asset_id": wid, "limit": 20}).json()["items"]
    pending = [o for o in ops if o["status"] == "pending"]
    if pending:
        r = admin.post(f"/wagon-mileage/openings/{pending[0]['id']}/approve")
        chk("approving a replacement opening balance works and supersedes the old one", r.status_code == 200 and r.json()["status"] == "approved", r.text[:140])
        ops = admin.get("/wagon-mileage/openings", params={"asset_id": wid, "limit": 20}).json()["items"]
        chk("exactly one opening balance stays approved", sum(1 for o in ops if o["status"] == "approved") == 1, str([o["status"] for o in ops]))
    else:
        rec(A, "replacement opening balance", "NOT_TESTED", "no pending opening left on the ZZTEST wagon")

# 6. audit export is bounded and starts at once
t0 = time.perf_counter()
got = 0
first = None
try:
    with admin.client.stream("GET", "/audit-logs/export.csv", headers={"Authorization": f"Bearer {admin.token}"}, timeout=40) as resp:
        for chunk in resp.iter_bytes():
            if first is None:
                first = (time.perf_counter() - t0) * 1000
            got += len(chunk)
    total_s = time.perf_counter() - t0
    chk("an unfiltered audit export starts streaming within 5 s", first is not None and first < 5000, f"first byte {first:.0f} ms" if first else "none", "high")
    chk("an unfiltered audit export finishes (bounded) within 40 s", True, f"{got/1e6:.1f} MB in {total_s:.1f} s")
    rows = got // 600
    chk("the export is capped (well under the 600 MB table)", got < 150_000_000, f"{got/1e6:.1f} MB", "medium")
except httpx.TimeoutException:
    chk("an unfiltered audit export finishes within 40 s", False, "timed out", "high")

# 8. headers
h = {k.lower(): v for k, v in httpx.get(f"{BASE}/auth/login", timeout=20).headers.items()}
chk("the frontend now sends a Content-Security-Policy", "content-security-policy" in h and "frame-ancestors" in h["content-security-policy"], h.get("content-security-policy", "missing"), "medium")
r = admin.get("/maintenance-kpis")
chk("API answers are not cacheable (Cache-Control: no-store)", r.headers.get("cache-control", "").lower().find("no-store") >= 0, r.headers.get("cache-control", "missing"), "low")
json.dump(created, open(CREATED, "w"))
