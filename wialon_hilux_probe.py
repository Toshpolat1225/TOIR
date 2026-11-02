#!/usr/bin/env python3
"""TOIR Wialon READ-ONLY: HILUX sensorlari, sozlamalar, report katalogi. DB/yozuv yo'q."""
import json, sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

UNITS = [366] + [int(a) for a in sys.argv[1:]]   # ixtiyoriy: nazorat birlik ID'lari
FLAGS = 1 | 1024 | 4096 | 8192 | 131072 | 1048576 | 2097152  # 3290113

def env(path):
    d = {}
    for l in path.read_text(encoding="utf-8-sig").splitlines():
        l = l.strip()
        if l and not l.startswith("#") and "=" in l:
            k, v = l.split("=", 1); d[k.strip()] = v.strip().strip("'\"")
    return d

def call(host, svc, params, sid=None):
    form = {"svc": svc, "params": json.dumps(params, separators=(",", ":"))}
    if sid: form["sid"] = sid
    req = Request(host + "/wialon/ajax.html", urlencode(form).encode(),
                  {"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    try:
        with urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except (HTTPError, URLError, TimeoutError) as e:
        return {"error": f"transport:{type(e).__name__}"}

def safe(host, sid, svc, params):
    r = call(host, svc, params, sid)
    ok = not (isinstance(r, dict) and r.get("error"))
    return {"ok": ok, "data": r}          # xato bo'lsa data={"error": kod}

def main():
    e = env(Path(__file__).resolve().parent / ".env.local")
    host, token = e["WIALON_HOST"].rstrip("/"), e["WIALON_TOKEN"]
    out, sid = {}, None
    try:
        login = call(host, "token/login", {"token": token})
        sid = login.get("eid")
        if not sid:
            print("LOGIN XATO:", login.get("error")); return 1
        print("LOGIN OK")
        out["server"] = {"version": login.get("host") and "bor", "user_acl_note": "token huquqlari: pastdagi ok/error ga qarang"}

        for uid in UNITS:
            u = {}
            u["unit"] = safe(host, sid, "core/search_items", {
                "spec": {"itemsType": "avl_unit", "propName": "sys_id",
                         "propValueMask": str(uid), "sortType": "sys_name", "propType": "property"},
                "force": 1, "flags": FLAGS, "from": 0, "to": 0})
            u["calc_last_message"] = safe(host, sid, "unit/calc_last_message",
                                          {"unitId": uid, "sensors": [], "flags": 1})
            u["report_settings"] = safe(host, sid, "unit/get_report_settings", {"itemId": uid})
            u["fuel_settings"] = safe(host, sid, "unit/get_fuel_settings", {"itemId": uid})
            u["trip_detector"] = safe(host, sid, "unit/get_trip_detector", {"itemId": uid})
            out[f"unit_{uid}"] = u
            print(f"unit {uid}:", {k: v["ok"] for k, v in u.items()})

        res = safe(host, sid, "core/search_items", {
            "spec": {"itemsType": "avl_resource", "propName": "sys_name",
                     "propValueMask": "*", "sortType": "sys_name", "propType": "property"},
            "force": 1, "flags": 1 | 8192, "from": 0, "to": 0})
        cat = []
        if res["ok"]:
            for r in res["data"].get("items", []):
                for tid, t in (r.get("rep") or {}).items():
                    cat.append({"resource_id": r.get("id"), "resource": r.get("nm"),
                                "template_id": t.get("id"), "name": t.get("n"), "type": t.get("ct"),
                                "tables": [{"n": x.get("n"), "l": x.get("l"), "cols": x.get("c"), "col_labels": x.get("cl")}
                                           for x in t.get("tbl", [])]})
        out["report_templates"] = {"ok": res["ok"], "count": len(cat), "items": cat,
                                   "error": None if res["ok"] else res["data"]}
        print("report shablonlari:", len(cat))
    finally:
        if sid: call(host, "core/logout", {}, sid)
    Path("wialon_hilux_probe.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("JSON yozildi: wialon_hilux_probe.json (hisobot bajarilmadi, hech narsa o'zgartirilmadi)")
    return 0

if __name__ == "__main__":
    sys.exit(main())