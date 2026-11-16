"""RBAC probe: every endpoint x every role (+ anonymous) with a harmless request, compared with the permission matrix.

Harmless = random UUID in the path (-> 404 after authorisation) or an empty body (-> 422 after authorisation); the
three action triggers (wialon/sync, gtk/sync, ml/analyze) are only called for roles that must be refused.
"""
import json
import sys

import httpx

from zz_lib import API, SC, Api, rec

roles = sys.argv[1:] or ["admin", "operator", "master", "management"]
routes = json.load(open(f"{SC}/routes.json"))
matrix = {}
for line in open(f"{SC}/matrix.txt", encoding="utf-8"):
    code, *flags = line.strip().split("|")
    matrix[code] = dict(zip(("admin", "operator", "master", "management"), (f == "1" for f in flags)))

ADMIN_ONLY_PREFIXES = ("/api/v1/audit-logs", "/api/v1/wialon/pull", "/api/v1/wialon-pull")
PUBLIC = {("GET", "/health"), ("POST", "/api/v1/auth/login"), ("POST", "/api/v1/auth/refresh"), ("POST", "/api/v1/auth/logout")}
TRIGGERS = {("POST", "/api/v1/wialon/sync"), ("POST", "/api/v1/gtk/sync"), ("POST", "/api/v1/ml/analyze")}
ZERO = "00000000-0000-0000-0000-000000000000"


def expected(route, role):
    perms = [a for q in route["reqs"] if q["dep"] == "require_permission" for a in (q["args"] or [])]
    if any(q["dep"] == "require_ingest_token" for q in route["reqs"]):
        return None
    if perms:
        return all(matrix.get(code, {}).get(role, False) for code in perms)
    if any(q["dep"] == "require_role" for q in route["reqs"]) or route["path"].startswith(ADMIN_ONLY_PREFIXES):
        return role == "admin"
    return True  # any authenticated user


def url(route):
    path = route["path"].replace("/api/v1", "")
    for p in route["params"]:
        path = path.replace("{" + p + "}", ZERO if p.endswith("id") else "zz")
    return path


def probe(api, route):
    kwargs = {"json": {}} if route["method"] in ("POST", "PUT", "PATCH") and route["body"] else {}
    if route["method"] in ("POST", "PUT", "PATCH") and not route["body"]:
        kwargs = {}
    return api.request(route["method"], url(route), **kwargs)


mismatch_over, mismatch_gap, server_errors, matrix_rows = [], [], [], {}
timeouts, slow = [], []
for role in roles + ["anonymous"]:
    api = Api(None if role == "anonymous" else role)
    if role != "anonymous":
        api.login()
    for route in routes:
        key = (route["method"], route["path"])
        if key in PUBLIC:
            continue
        exp = None if role == "anonymous" else expected(route, role)
        if exp is None and role != "anonymous":
            continue
        if key in TRIGGERS and (role == "anonymous" or exp):
            if role == "anonymous":
                pass
            else:
                continue
        try:
            r = probe(api, route)
        except httpx.TimeoutException:
            timeouts.append((role, route["method"], route["path"]))
            continue
        if api.last_ms > 3000:
            slow.append((role, route["method"], route["path"], round(api.last_ms)))
        code = r.status_code
        matrix_rows.setdefault(f"{route['method']} {route['path']}", {})[role] = code
        if code >= 500:
            server_errors.append((role, route["method"], route["path"], code))
        if role == "anonymous":
            if code not in (401, 403):
                mismatch_gap.append((role, route["method"], route["path"], code))
            continue
        denied = code in (401, 403)
        if exp and denied:
            mismatch_over.append((role, route["method"], route["path"], code))
        if not exp and not denied:
            mismatch_gap.append((role, route["method"], route["path"], code))

total = sum(len(v) for v in matrix_rows.values())
rec("rbac", f"probed {len(matrix_rows)} endpoints x roles ({total} requests)", "INFO", ", ".join(roles))
rec("rbac", "anonymous callers are refused everywhere except the public endpoints", "PASS" if not any(r[0] == "anonymous" for r in mismatch_gap) else "FAIL",
    "; ".join(f"{m} {p}={c}" for ro, m, p, c in mismatch_gap if ro == "anonymous")[:400], "critical")
gaps = [g for g in mismatch_gap if g[0] != "anonymous"]
rec("rbac", "no role can reach an endpoint its permissions forbid", "PASS" if not gaps else "FAIL", "; ".join(f"{ro}:{m} {p}={c}" for ro, m, p, c in gaps)[:600], "critical")
rec("rbac", "roles are not refused where their permissions allow", "PASS" if not mismatch_over else "FAIL", "; ".join(f"{ro}:{m} {p}={c}" for ro, m, p, c in mismatch_over)[:600], "medium")
rec("rbac", "no endpoint answers 5xx to a harmless request", "PASS" if not server_errors else "FAIL", "; ".join(f"{ro}:{m} {p}={c}" for ro, m, p, c in server_errors)[:600], "high")
rec("performance", "no endpoint times out (60 s) on a harmless request", "PASS" if not timeouts else "FAIL", "; ".join(f"{ro}:{m} {p}" for ro, m, p in timeouts)[:600], "high")
rec("performance", "no endpoint needs more than 3 s for a harmless request", "PASS" if not slow else "FAIL", "; ".join(f"{ro}:{m} {p}={ms}ms" for ro, m, p, ms in slow)[:600], "medium")
json.dump(matrix_rows, open(f"{SC}/rbac_matrix_{'_'.join(roles)}.json", "w"))
