"""Shared helpers of the live E2E run: API clients per role (credentials come from a file, never printed) and a result log."""
import json
import os
import subprocess
import time
from datetime import datetime, timezone

import httpx

SC = os.path.dirname(os.path.abspath(__file__))
BASE = "http://192.168.28.104"
API = f"{BASE}/api/v1"
CREDS = json.load(open(os.path.join(SC, "zztest_creds.json")))
IDS = json.load(open(os.path.join(SC, "zz_ids.json")))
RESULTS = os.path.join(SC, "results.jsonl")
ROLES = ("admin", "operator", "master", "management")


def rec(area, name, status, detail="", severity=None, evidence=None):
    """status: PASS | FAIL | INFO | NOT_TESTED. severity (FAIL only): critical | high | medium | low."""
    row = {"t": datetime.now(timezone.utc).isoformat(timespec="seconds"), "area": area, "name": name, "status": status,
           "severity": severity, "detail": detail, "evidence": evidence}
    with open(RESULTS, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    mark = {"PASS": "PASS", "FAIL": "FAIL", "INFO": "info", "NOT_TESTED": "n/t"}[status]
    print(f"{mark:5} [{area}] {name}" + (f" -- {detail}" if detail and status != "PASS" else ""))
    return status == "PASS"


class Api:
    def __init__(self, role=None, timeout=60):
        self.role = role
        self.client = httpx.Client(base_url=API, timeout=timeout, follow_redirects=False)
        self.token = None
        self.last_ms = 0

    def login(self):
        c = CREDS[self.role]
        r = self.client.post("/auth/login", json={"email": c["email"], "password": c["password"]})
        r.raise_for_status()
        self.token = r.json()["access_token"]
        return r

    def request(self, method, path, **kw):
        headers = kw.pop("headers", {})
        if self.token:
            headers = {"Authorization": f"Bearer {self.token}", **headers}
        started = time.perf_counter()
        r = self.client.request(method, path, headers=headers, **kw)
        self.last_ms = (time.perf_counter() - started) * 1000
        return r

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, **kw):
        return self.request("POST", path, **kw)

    def patch(self, path, **kw):
        return self.request("PATCH", path, **kw)

    def put(self, path, **kw):
        return self.request("PUT", path, **kw)

    def delete(self, path, **kw):
        return self.request("DELETE", path, **kw)


def clients():
    result = {}
    for role in ROLES:
        api = Api(role)
        api.login()
        result[role] = api
    return result


REPO = "c:/Users/okmkh/OneDrive/Documents/GitHub/TOIR"


def psql(sql=None, file=None):
    """Runs SQL on the live database through the postgres container (no password needed there). Returns stdout."""
    env = dict(os.environ, MSYS_NO_PATHCONV="1")
    cmd = ["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "toir_local", "-d", "toir_local", "-At", "-F", "|"]
    if sql is not None:
        cmd += ["-c", sql]
    result = subprocess.run(cmd, cwd=REPO, env=env, input=open(file, encoding="utf-8").read() if file else None,
                            capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(result.stderr[:400])
    return result.stdout
