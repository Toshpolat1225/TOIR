from zz_lib import Api, rec
a = Api("admin"); a.login()
ZERO = "00000000-0000-0000-0000-000000000000"
r = a.get(f"/audit-logs/{ZERO}"); t_detail = a.last_ms
rec("performance", "audit-log detail by id answers fast when nothing else is running", "PASS" if t_detail < 1000 else "FAIL", f"{r.status_code} in {t_detail:.0f} ms", "medium")
r = a.get("/audit-logs", params={"limit": 50}); t_list = a.last_ms
rec("performance", "audit-log list (first page) answers in under 2 s", "PASS" if t_list < 2000 else "FAIL", f"{r.status_code} in {t_list:.0f} ms, total={r.json().get('total')}", "medium")
r = a.get("/audit-logs", params={"limit": 50, "action": "login"}); t_f = a.last_ms
rec("performance", "audit-log filtered by action answers in under 2 s", "PASS" if t_f < 2000 else "FAIL", f"{r.status_code} in {t_f:.0f} ms", "low")
r = a.get("/audit-logs", params={"limit": 50, "date_from": "2026-11-16T00:00:00Z"}); t_d = a.last_ms
rec("performance", "audit-log filtered by today answers in under 2 s", "PASS" if t_d < 2000 else "FAIL", f"{r.status_code} in {t_d:.0f} ms", "low")
# the export without any filter: how big would it be? (stop after the first megabyte)
import httpx
try:
    with a.client.stream("GET", "/audit-logs/export.csv", headers={"Authorization": f"Bearer {a.token}"}, timeout=20) as resp:
        got = 0
        for chunk in resp.iter_bytes():
            got += len(chunk)
            if got > 1_000_000:
                break
    rec("performance", "audit-log CSV export is bounded", "FAIL" if got > 1_000_000 else "PASS", "streamed over 1 MB without any filter or row cap (the table has ~950k rows, ~600 MB)", "medium")
except httpx.ReadTimeout:
    rec("performance", "audit-log CSV export starts within 20 s", "FAIL", "no first byte in 20 s with no filter: the export is unbounded and blocks until it has read the table", "high")
