"""User administration, permission matrix endpoints and the wagon opening-balance workflow (ZZTEST data only)."""
import json
import os
import secrets
from datetime import datetime, timedelta, timezone

import httpx

from zz_lib import API, IDS, SC, Api, clients, psql, rec

A = "users"
M = "mileage"
CREATED = os.path.join(SC, "zz_created.json")
created = json.load(open(CREATED)) if os.path.exists(CREATED) else {}


def chk(area, name, ok, detail="", severity="high"):
    return rec(area, name, "PASS" if ok else "FAIL", detail, None if ok else severity)


C = clients()
admin, operator, master, management = C["admin"], C["operator"], C["master"], C["management"]
SEC_A = IDS["sections"]["A"]
tag = secrets.token_hex(3)
strong = secrets.token_urlsafe(18)

# ── create / validation ──────────────────────────────────────────────────────
base = {"email": f"zztest-u{tag}@example.test", "full_name": f"ZZTEST user {tag}", "role": "operator", "password": strong}
for label, patch_, codes in (("a weak password", {"password": "123"}, (422,)), ("an unknown role", {"role": "superadmin"}, (422,)),
                             ("a master without a section", {"role": "master"}, (409, 422)), ("an invalid email", {"email": "not-an-email"}, (422,)),
                             ("an empty full name", {"full_name": "  "}, (422,))):
    probe_email = f"zztest-p{abs(hash(label)) % 10000}{tag}@example.test"
    r = admin.post("/users", json={**base, "email": probe_email, **patch_})
    if r.status_code == 201:
        created.setdefault("users", []).append(r.json()["id"])  # it was created although it should not have been
    chk(A, f"create user rejects {label}", r.status_code in codes, f"status {r.status_code}", "high" if "password" in label else "medium")
r = admin.post("/users", json=base)
chk(A, "admin creates a local user", r.status_code == 201 and "hashed_password" not in r.text and "password" not in r.json(), r.text[:160])
uid = r.json().get("id")
if uid:
    created.setdefault("users", []).append(uid)
r = admin.post("/users", json={**base, "email": base["email"].upper()})
chk(A, "an email differing only by case is a duplicate (409)", r.status_code == 409, f"status {r.status_code}", "medium")
for who, name in ((operator, "operator"), (master, "master"), (management, "management")):
    r = who.post("/users", json={**base, "email": f"zztest-x{tag}{name}@example.test"})
    chk(A, f"{name} cannot create users", r.status_code == 403, f"status {r.status_code}", "critical")
    r = who.get("/users")
    chk(A, f"{name} cannot list users", r.status_code == 403, f"status {r.status_code}", "high")

# ── the new user can log in; escalation attempts; deactivation ───────────────
newu = Api();
lr = newu.client.post("/auth/login", json={"email": base["email"], "password": strong})
chk(A, "the new user can log in", lr.status_code == 200, f"status {lr.status_code}")
if lr.status_code == 200:
    newu.token = lr.json()["access_token"]
    me = newu.get("/auth/me").json()
    r = newu.patch(f"/users/{uid}", json={"role": "admin"})
    chk(A, "a user cannot raise his own role to admin", r.status_code == 403, f"status {r.status_code}", "critical")
    r = newu.post(f"/users/{uid}/reset-password", json={"password": secrets.token_urlsafe(16)})
    chk(A, "a user cannot reset a password through the admin endpoint", r.status_code == 403, f"status {r.status_code}", "critical")
    r = admin.patch(f"/users/{uid}", json={"role": "master", "section_id": SEC_A})
    chk(A, "admin changes the role (master needs a section)", r.status_code == 200 and r.json()["role"] == "master", r.text[:120])
    r = admin.patch(f"/users/{uid}", json={"role": "master", "section_id": None})
    chk(A, "a master cannot be left without a section", r.status_code in (409, 422), f"status {r.status_code}", "medium")
    admin.patch(f"/users/{uid}", json={"role": "operator", "section_id": None})
    r = admin.patch(f"/users/{uid}", json={"is_active": False})
    chk(A, "admin deactivates the user", r.status_code == 200 and r.json()["is_active"] is False, r.text[:100])
    r = newu.get("/auth/me")
    chk(A, "a deactivated user's existing access token stops working at once", r.status_code in (401, 403), f"status {r.status_code}", "high")
    lr2 = httpx.post(f"{API}/auth/login", json={"email": base["email"], "password": strong}, timeout=30)
    chk(A, "a deactivated user cannot log in", lr2.status_code in (401, 403), f"status {lr2.status_code}", "high")
    admin.patch(f"/users/{uid}", json={"is_active": True})
    newpw = secrets.token_urlsafe(18)
    r = admin.post(f"/users/{uid}/reset-password", json={"password": "short"})
    chk(A, "password reset enforces the password policy", r.status_code == 422, f"status {r.status_code}", "medium")
    r = admin.post(f"/users/{uid}/reset-password", json={"password": newpw})
    chk(A, "admin resets the password", r.status_code in (200, 204), f"status {r.status_code}")
    old = httpx.post(f"{API}/auth/login", json={"email": base["email"], "password": strong}, timeout=30)
    new = httpx.post(f"{API}/auth/login", json={"email": base["email"], "password": newpw}, timeout=30)
    chk(A, "after a reset the old password fails and the new one works", old.status_code == 401 and new.status_code == 200, f"{old.status_code}/{new.status_code}")
    chk(A, "resetting a password revokes the user's other sessions", newu.get("/auth/refresh").status_code != 200, "", "medium")

# ── AD users ─────────────────────────────────────────────────────────────────
ad = f"zztest.ad{tag}"
for label, payload, codes in (("a bad directory login", {"ad_username": "a b;c", "full_name": "x", "role": "operator"}, (422,)),
                              ("an admin role without ...", {"ad_username": ad, "full_name": "x", "role": "nonsense"}, (422,))):
    r = admin.post("/users/ad", json=payload)
    chk(A, f"AD user creation rejects {label}", r.status_code in codes, f"status {r.status_code}", "medium")
r = admin.post("/users/ad", json={"ad_username": ad, "full_name": f"ZZTEST AD {tag}", "role": "operator"})
chk(A, "admin grants domain access without a password", r.status_code == 201 and r.json()["auth_source"] == "ad" and r.json().get("ad_username") == ad, r.text[:160])
if r.status_code == 201:
    created.setdefault("users", []).append(r.json()["id"])
r2 = admin.post("/users/ad", json={"ad_username": ad.upper(), "full_name": "dup", "role": "operator"})
chk(A, "a duplicate directory login is refused (case-insensitive)", r2.status_code == 409, f"status {r2.status_code}", "medium")
r3 = admin.post(f"/users/{r.json()['id']}/reset-password", json={"password": strong}) if r.status_code == 201 else None
chk(A, "a domain user has no local password to reset (409)", r3 is not None and r3.status_code == 409, f"status {r3.status_code if r3 else '-'}", "medium")
lr = httpx.post(f"{API}/auth/login", json={"email": ad, "password": "whatever"}, timeout=60)
chk(A, "a domain login with a wrong password is refused and does not hang", lr.status_code in (401, 429, 503), f"status {lr.status_code}", "medium")
if uid:
    r = operator.post(f"/users/{uid}/convert-to-ad", json={"ad_username": f"zztest.cv{tag}"})
    chk(A, "operator cannot convert an account to a domain account", r.status_code == 403, f"status {r.status_code}", "critical")

# ── permission matrix endpoints (read + validation only: never rewrite a live role) ──
r = admin.get("/permissions/operator")
chk(A, "admin reads the operator permission set", r.status_code == 200, r.text[:100])
r = operator.get("/permissions/operator")
chk(A, "operator cannot read other roles' permission sets", r.status_code == 403, f"status {r.status_code}", "medium")
r = operator.put("/permissions/operator", json={"permissions": {}})
chk(A, "operator cannot rewrite permissions (even his own)", r.status_code == 403, f"status {r.status_code}", "critical")
r = admin.put("/permissions/nonexistent-role", json={"permissions": {}})
chk(A, "an unknown role is refused", r.status_code in (404, 422), f"status {r.status_code}", "medium")
mine = operator.get("/permissions/me").json()
names = {(x.get("code") or x.get("permission_code")) for x in mine if (x.get("granted", True))} if isinstance(mine, list) else set()
chk(A, "/permissions/me reflects the matrix (operator: maintenance.update yes, users.manage_users no)", "maintenance.update" in names and "users.manage_users" not in names, json.dumps(mine)[:120], "medium")

# ── wagon opening balance workflow ───────────────────────────────────────────
models = admin.get("/fixed-assets/models", params={"asset_type": "wagon", "limit": 1}).json()["items"]
model = models[0]["id"] if models else None
r = admin.post("/fixed-assets", json={"inv_number": f"ZZTEST-W{tag}", "asset_type": "wagon", "section_id": SEC_A, "model_id": model, "number": f"9{tag[:3]}0", "serial_number": f"ZZW{tag}"})
chk(M, "create a test wagon", r.status_code == 201, r.text[:140])
if r.status_code == 201:
    wid = r.json()["id"]
    created.setdefault("assets", []).append(wid)
    when = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    for label, payload in (("a negative mileage", {"mileage_km": -5}), ("a missing date", {"mileage_km": 5, "effective_at": None})):
        rr = operator.post("/wagon-mileage/openings", json={"asset_id": wid, "effective_at": when, **payload})
        chk(M, f"an opening with {label} is refused", rr.status_code == 422, f"status {rr.status_code}", "medium")
    rr = master.post("/wagon-mileage/openings", json={"asset_id": wid, "mileage_km": 10, "effective_at": when})
    chk(M, "a master cannot propose an opening balance", rr.status_code == 403, f"status {rr.status_code}", "high")
    rr = operator.post("/wagon-mileage/openings", json={"asset_id": wid, "mileage_km": 123, "effective_at": when, "note": "ZZTEST"})
    chk(M, "operator proposes an opening balance (pending)", rr.status_code == 201 and rr.json()["status"] == "pending", rr.text[:140])
    oid = rr.json().get("id")
    rr = operator.post(f"/wagon-mileage/openings/{oid}/approve")
    chk(M, "operator cannot approve (admin only)", rr.status_code == 403, f"status {rr.status_code}", "critical")
    rr = admin.post(f"/wagon-mileage/openings/{oid}/approve")
    chk(M, "admin approves it (maker != checker)", rr.status_code == 200 and rr.json()["status"] == "approved", rr.text[:160])
    rr = admin.post(f"/wagon-mileage/openings/{oid}/approve")
    chk(M, "approving twice is refused (409)", rr.status_code == 409, f"status {rr.status_code}", "medium")
    rr2 = operator.post("/wagon-mileage/openings", json={"asset_id": wid, "mileage_km": 200, "effective_at": when, "note": "ZZTEST second"})
    oid2 = rr2.json().get("id")
    admin.post(f"/wagon-mileage/openings/{oid2}/approve")
    lst = admin.get("/wagon-mileage/openings", params={"asset_id": wid, "limit": 20}).json()["items"]
    st = {x["id"]: x["status"] for x in lst}
    chk(M, "a newer approved balance supersedes the old one (exactly one approved)", sum(1 for v in st.values() if v == "approved") == 1 and st.get(oid) == "superseded", json.dumps(list(st.values())))
    summary = admin.get(f"/wagon-mileage/assets/{wid}")
    chk(M, "the wagon mileage summary answers", summary.status_code == 200, f"status {summary.status_code}", "medium")
    for who, nm in ((operator, "operator"), (master, "master")):
        rb = who.post("/wagon-mileage/openings/bulk-approve", json={"dry_run": True})
        chk(M, f"{nm} cannot bulk-approve", rb.status_code == 403, f"status {rb.status_code}", "critical")
    rb = admin.post("/wagon-mileage/openings/bulk-approve", json={"dry_run": True})
    chk(M, "bulk approval as a dry run changes nothing and reports", rb.status_code == 200 and rb.json().get("dry_run") is True and rb.json().get("approved") in (0, [], None), rb.text[:200], "high")
json.dump(created, open(CREATED, "w"))
