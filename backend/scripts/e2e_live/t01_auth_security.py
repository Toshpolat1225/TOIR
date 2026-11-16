"""Authentication and transport security of the live system (uses only the ZZTEST accounts)."""
import base64
import json
import time

import httpx

from zz_lib import API, BASE, CREDS, Api, clients, rec

A = "auth"
S = "security"

# ── login / me ───────────────────────────────────────────────────────────────
api = Api("operator")
r = api.login()
rec(A, "login returns an access token and sets a refresh cookie", "PASS" if r.status_code == 200 and "access_token" in r.json() and "set-cookie" in r.headers else "FAIL", f"status {r.status_code}", "high")
cookie = r.headers.get("set-cookie", "")
flags = cookie.lower()
rec(S, "refresh cookie is HttpOnly", "PASS" if "httponly" in flags else "FAIL", cookie.split(";")[0][:20] + "...", "high")
rec(S, "refresh cookie has SameSite", "PASS" if "samesite" in flags else "FAIL", "", "medium")
rec(S, "refresh cookie is Secure (only meaningful over HTTPS)", "PASS" if "secure" in flags else "INFO", "cookie is not Secure: the site is served over plain HTTP", None)

me = api.get("/auth/me")
body = me.json()
rec(A, "/auth/me returns the right user and no secret fields", "PASS" if me.status_code == 200 and body.get("role") == "operator" and not any(k in body for k in ("hashed_password", "password", "ad_object_guid")) else "FAIL", f"keys={sorted(body)}", "high")

# ── bad credentials ──────────────────────────────────────────────────────────
anon = Api()
wrong = anon.post("/auth/login", json={"email": CREDS["operator"]["email"], "password": "definitely-wrong"})
unknown = anon.post("/auth/login", json={"email": "zztest-nobody@example.test", "password": "definitely-wrong"})
rec(A, "wrong password and unknown user give the same answer (no user enumeration)", "PASS" if wrong.status_code == unknown.status_code == 401 and wrong.json() == unknown.json() else "FAIL", f"{wrong.status_code} {wrong.text[:80]} | {unknown.status_code} {unknown.text[:80]}", "medium")
t = []
for email in (CREDS["operator"]["email"], "zztest-nobody@example.test") * 3:
    s = time.perf_counter()
    anon.post("/auth/login", json={"email": email, "password": "definitely-wrong"})
    t.append((email.startswith("zztest-operator"), (time.perf_counter() - s) * 1000))
known = sum(x for k, x in t if k) / 3
nobody = sum(x for k, x in t if not k) / 3
rec(S, "login timing does not reveal whether the user exists", "PASS" if abs(known - nobody) < max(60, 0.5 * max(known, nobody)) else "FAIL", f"known {known:.0f} ms vs unknown {nobody:.0f} ms", "low")
for payload, label in (({"email": "a", "password": ""}, "empty password"), ({"email": "x" * 400, "password": "p"}, "oversized login"), ({"email": "' OR 1=1 --", "password": "p"}, "SQL-ish login"), ({}, "empty body")):
    rr = anon.post("/auth/login", json=payload)
    rec(A, f"login rejects {label} cleanly", "PASS" if rr.status_code in (401, 422) else "FAIL", f"status {rr.status_code}", "medium")

# ── brute force ──────────────────────────────────────────────────────────────
codes = [anon.post("/auth/login", json={"email": CREDS["management"]["email"], "password": f"wrong-{i}"}).status_code for i in range(14)]
rec(S, "repeated wrong passwords are throttled or locked (429/423/403)", "PASS" if any(c in (429, 423, 403) for c in codes) else "FAIL", f"14 wrong attempts -> {sorted(set(codes))}", "high")
ok_after = Api("management")
try:
    ok_after.login()
    rec(S, "a locked account recovers or the correct password still works", "PASS", "")
except httpx.HTTPStatusError as exc:
    rec(S, "the correct password works right after failed attempts", "INFO", f"login refused with {exc.response.status_code} (lockout active)")

# ── tokens ───────────────────────────────────────────────────────────────────
def b64(d):
    return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()

good = api.token
head, payload, sig = good.split(".")
tampered = f"{head}.{payload[:-2]}AA.{sig}"
none_alg = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{payload}."
for label, tok in (("tampered payload", tampered), ("alg=none", none_alg), ("garbage", "not-a-jwt")):
    rr = anon.client.get("/auth/me", headers={"Authorization": f"Bearer {tok}"})
    rec(S, f"{label} token is rejected", "PASS" if rr.status_code == 401 else "FAIL", f"status {rr.status_code}", "critical")
rr = anon.client.get("/auth/me")
rec(S, "no token is rejected", "PASS" if rr.status_code in (401, 403) else "FAIL", f"status {rr.status_code}", "critical")

# refresh rotation + reuse detection + logout
fresh = Api("operator")
fresh.login()
ck = dict(fresh.client.cookies)
r1 = fresh.client.post("/auth/refresh")
rec(A, "refresh issues a new access token", "PASS" if r1.status_code == 200 and "access_token" in r1.json() else "FAIL", f"status {r1.status_code}", "high")
old_cookie_jar = httpx.Cookies(ck)
replay = httpx.Client(base_url=API, cookies=old_cookie_jar)
r2 = replay.post("/auth/refresh")
rec(S, "an already-used refresh token cannot be replayed", "PASS" if r2.status_code == 401 else "FAIL", f"replay status {r2.status_code}", "high")
r3 = fresh.client.post("/auth/refresh")
rec(S, "replaying a rotated token revokes the whole token family", "PASS" if r3.status_code == 401 else "INFO", f"after replay the current token gives {r3.status_code}")
lo = Api("operator")
lo.login()
lo.client.post("/auth/logout")
r4 = lo.client.post("/auth/refresh")
rec(A, "logout revokes the refresh token", "PASS" if r4.status_code == 401 else "FAIL", f"status {r4.status_code}", "high")

# ── transport / headers / disclosure ─────────────────────────────────────────
resp = httpx.get(f"{BASE}/auth/login", follow_redirects=True, timeout=20)
h = {k.lower(): v for k, v in resp.headers.items()}
for header, sev in (("x-content-type-options", "medium"), ("x-frame-options", "medium"), ("referrer-policy", "low"), ("content-security-policy", "medium"), ("strict-transport-security", "low")):
    present = header in h or (header == "x-frame-options" and "frame-ancestors" in h.get("content-security-policy", ""))
    rec(S, f"frontend sends {header}", "PASS" if present else "FAIL", f"missing on {BASE}/auth/login", sev)
rec(S, "frontend does not advertise its framework (X-Powered-By)", "PASS" if "x-powered-by" not in h else "FAIL", h.get("x-powered-by", ""), "low")
rec(S, "server banner does not expose a version", "PASS" if not any(c.isdigit() for c in h.get("server", "")) else "FAIL", h.get("server", ""), "low")
ah = {k.lower(): v for k, v in httpx.get(f"{API}/auth/me", timeout=20).headers.items()}
for header, sev in (("x-content-type-options", "low"), ("cache-control", "low")):
    rec(S, f"API sends {header}", "PASS" if header in ah else "FAIL", "", sev)
rec(S, "interactive API docs are off in production", "PASS" if all(httpx.get(f"{BASE}{p}", timeout=20).status_code in (404, 307, 401) for p in ("/docs", "/redoc", "/openapi.json", "/api/v1/docs", "/api/v1/openapi.json")) else "FAIL", "", "medium")
pre = httpx.options(f"{API}/auth/login", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"}, timeout=20)
rec(S, "CORS: a foreign origin is not allowed", "PASS" if pre.headers.get("access-control-allow-origin") not in ("*", "http://evil.example") else "FAIL", pre.headers.get("access-control-allow-origin", ""), "high")
bad = httpx.post(f"{API}/maintenance-plan/not-a-uuid/block", headers={"Authorization": f"Bearer {good}"}, json={}, timeout=20)
rec(S, "validation errors do not leak internals", "PASS" if "Traceback" not in bad.text and "sqlalchemy" not in bad.text.lower() else "FAIL", bad.text[:120], "medium")
big = httpx.post(f"{API}/auth/login", content=b"x" * 5_000_000, headers={"Content-Type": "application/json"}, timeout=30)
rec(S, "an oversized request body is refused quickly", "PASS" if big.status_code in (400, 413, 422) else "FAIL", f"status {big.status_code}", "low")
rec(S, "plain HTTP: is HTTPS available?", "INFO", "port 80 only is published; tokens and the refresh cookie travel unencrypted on the LAN")
try:
    httpx.get("https://192.168.28.104/", timeout=5, verify=False)
    rec(S, "HTTPS answers on 443", "PASS")
except Exception as exc:
    rec(S, "HTTPS answers on 443", "FAIL", f"{type(exc).__name__}", "medium")
