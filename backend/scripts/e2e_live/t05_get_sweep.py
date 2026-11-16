"""Every GET list endpoint as admin: latency, response shape, pagination bounds, hostile search strings, bad sort keys."""
import json
import statistics
import httpx

from zz_lib import SC, Api, rec

routes = [r for r in json.load(open(f"{SC}/routes.json")) if r["method"] == "GET" and not r["params"]]
SKIP = {"/health", "/api/v1/auth/me", "/api/v1/audit-logs/export.csv", "/api/v1/wialon/input", "/api/v1/fixed-assets/passport-report",
        "/api/v1/gtk/match-report"}  # exports / token endpoints are covered separately
admin = Api("admin"); admin.login()
REQUIRED = {"month": "2026-11", "source": "wialon", "kind": "locomotive", "work_type_id": "00000000-0000-0000-0000-000000000000",
            "department_id": "00000000-0000-0000-0000-000000000000", "asset_id": "00000000-0000-0000-0000-000000000000"}
EVIL = ["'", "\"", "%", "_", "\\", "' OR '1'='1", "'; DROP TABLE users; --", "<script>alert(1)</script>", "а" * 400, "\u0000", "💥", "%00", "${jndi:x}"]

slow, errors, bad_json, big, timings = [], [], [], [], []
tested = 0
for route in routes:
    path = route["path"].replace("/api/v1", "")
    if route["path"] in SKIP:
        continue
    params = {q["name"]: REQUIRED.get(q["name"], "x") for q in route["query"] if q["required"]}
    try:
        r = admin.get(path, params=params)
    except httpx.TimeoutException:
        slow.append((path, "timeout")); continue
    tested += 1
    timings.append((admin.last_ms, path))
    if admin.last_ms > 1500:
        slow.append((path, round(admin.last_ms)))
    if r.status_code >= 500:
        errors.append((path, "default", r.status_code))
    try:
        r.json()
    except Exception:
        if r.status_code == 200 and "csv" not in r.headers.get("content-type", ""):
            bad_json.append(path)
    if len(r.content) > 5_000_000:
        big.append((path, len(r.content)))
    names = {q["name"] for q in route["query"]}
    probes = []
    if "limit" in names:
        probes += [{"limit": 0}, {"limit": -1}, {"limit": 100000}, {"limit": "abc"}]
    if "offset" in names:
        probes += [{"offset": -1}, {"offset": 10**12}]
    if "sort_by" in names:
        probes += [{"sort_by": "nonexistent; drop"}, {"sort_by": "id", "sort_order": "sideways"}]
    for evil in EVIL if ("q" in names or "object_q" in names or "material_q" in names) else []:
        for key in ("q", "object_q", "material_q"):
            if key in names:
                probes.append({key: evil})
    for extra in probes:
        try:
            rr = admin.get(path, params={**params, **extra})
        except httpx.TimeoutException:
            slow.append((path, f"timeout with {extra}")); continue
        if rr.status_code >= 500:
            errors.append((path, json.dumps(extra, ensure_ascii=False)[:60], rr.status_code))
        if "limit" in extra and extra["limit"] == 100000 and rr.status_code == 200:
            try:
                items = rr.json().get("items", [])
                if len(items) > 5000:
                    big.append((path, f"limit=100000 returned {len(items)} rows"))
            except Exception:
                pass

timings.sort(reverse=True)
rec("api-sweep", f"{tested} GET list endpoints called (+ boundary and hostile-input probes)", "INFO", "")
rec("api-sweep", "no GET endpoint answers 5xx to any boundary or hostile input", "PASS" if not errors else "FAIL", "; ".join(f"{p} {e} -> {c}" for p, e, c in errors)[:600], "high")
rec("performance", "every list endpoint answers within 1.5 s (first page, admin)", "PASS" if not slow else "FAIL", "; ".join(f"{p}={m}" for p, m in slow)[:600], "medium")
rec("api-sweep", "list endpoints return valid JSON", "PASS" if not bad_json else "FAIL", "; ".join(bad_json)[:300], "medium")
rec("api-sweep", "a huge `limit` is capped or refused (no 100k-row responses)", "PASS" if not big else "FAIL", "; ".join(f"{p}: {n}" for p, n in big)[:400], "medium")
rec("performance", "slowest endpoints (ms)", "INFO", ", ".join(f"{p.replace('/api/v1', '')}={m:.0f}" for m, p in timings[:8]))
rec("performance", "median list latency (ms)", "INFO", f"{statistics.median(t for t, _ in timings):.0f}")
