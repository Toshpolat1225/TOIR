"""Light concurrency check on the heaviest read endpoints (a dozen simultaneous users, read-only)."""
import statistics
import threading
import time

from zz_lib import Api, rec

CASES = [("/maintenance-schedule", {"month": "2026-11"}), ("/maintenance-kpis", {}), ("/fixed-assets/unified", {"limit": 50}),
         ("/maintenance-plan", {"limit": 1000}), ("/dashboard/summary", {}), ("/work-orders", {"limit": 50})]
USERS = 12
ROUNDS = 3

for path, params in CASES:
    clients = []
    for _ in range(USERS):
        a = Api("admin")
        a.token = None
        clients.append(a)
    # one login, tokens are shared (login is rate limited per key, not what is measured here)
    base = Api("admin")
    base.login()
    for c in clients:
        c.token = base.token
    times, codes = [], []
    lock = threading.Lock()

    def worker(c):
        for _ in range(ROUNDS):
            s = time.perf_counter()
            r = c.get(path, params=params)
            with lock:
                times.append((time.perf_counter() - s) * 1000)
                codes.append(r.status_code)

    threads = [threading.Thread(target=worker, args=(c,)) for c in clients]
    started = time.perf_counter()
    [t.start() for t in threads]
    [t.join() for t in threads]
    wall = time.perf_counter() - started
    times.sort()
    p50, p95 = statistics.median(times), times[int(len(times) * 0.95) - 1]
    ok = all(c == 200 for c in codes)
    rec("performance", f"{USERS} parallel users x {ROUNDS} on {path}", "PASS" if ok and p95 < 5000 else "FAIL",
        f"p50 {p50:.0f} ms, p95 {p95:.0f} ms, {len(times)} requests in {wall:.1f} s, codes {sorted(set(codes))}", "medium")
