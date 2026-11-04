#!/usr/bin/env python3
"""GTK (V12) read-only klient: bitta GET bilan lokomotivlar, vagonlar, sostavlar va vagon holatini oladi.

Manba: /railway/__railway_train/?EnterprisesControlRB=1 sahifasi. Ma'lumot HTML ichidagi JS'ga
JSON massiv sifatida joylangan ($scope.locomotives / carriages / trains, carriageStates).
Faqat urllib: bitta login POST (forma) va bitta GET. Hech qanday yozuvchi so'rov yuborilmaydi.
Parol chop etilmaydi va snapshotga yozilmaydi. TOIR bazasiga ulanmaydi.

Login/parol: GTK_USER / GTK_PASSWORD muhit o'zgaruvchisi yoki .env.gtk fayli (git'ga tushmaydi);
bo'lmasa so'raydi.

Ishga tushirish:
    python gtk_client.py                                   # login + GET + gtk_snapshot.json
    python gtk_client.py --out=gtk_snapshot.json
    python gtk_client.py --from-html=gtk_page_railway___railway_train.html   # oflayn, tarmoqsiz

Vaqt: GTK sahifasi vaqtni Asia/Tashkent (UTC+5) bo'yicha beradi (VIST.user.time_zone). Snapshotda
mahalliy vaqt ham, UTC ham bor. Lokomotiv/vagon alohida sahifalaridagi sanalar esa UTC'da beriladi:
shuning uchun faqat shu sahifa ishlatiladi.
"""
import ast
import getpass
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener

HOST = "http://172.16.252.100"
PAGE = "/railway/__railway_train/"
QUERY = "EnterprisesControlRB=1"
TIMEOUT = 60
MIN_BLOB = 300
STALE_DAYS = 30
TZ = timezone(timedelta(hours=5))  # Asia/Tashkent

CSRF = re.compile(
    r"""name=["']csrfmiddlewaretoken["'][^>]*value=["']([^"']+)["']|value=["']([^"']+)["'][^>]*name=["']csrfmiddlewaretoken["']"""
)
START = re.compile(r"""\[\s*\{\s*["']|[=:(,]\s*\{\s*["']""")
NAME_RE = re.compile(r"(\w+)\s*=\s*(?:HashList\.fromList\()?$")


# --------------------------------------------------------------------------- transport
def arg(name, default=None):
    for a in sys.argv[1:]:
        if a.startswith(f"--{name}="):
            return a.split("=", 1)[1]
    return default


def credentials():
    user, pw = os.environ.get("GTK_USER", ""), os.environ.get("GTK_PASSWORD", "")
    env_file = Path(__file__).resolve().parent / ".env.gtk"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                if k.strip() == "GTK_USER":
                    user = user or v.strip()
                elif k.strip() == "GTK_PASSWORD":
                    pw = pw or v.strip()
    return user or input("Login: ").strip(), pw or getpass.getpass("Parol (ko'rinmaydi): ")


def fetch_page(host=HOST, page=PAGE, query=QUERY):
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    url = host.rstrip("/") + page + (("?" + query) if query else "")

    def get(u, data=None, referer=None):
        headers = {"User-Agent": "toir-gtk-client/1.0"}
        if referer:
            headers["Referer"] = referer
        body = urlencode(data).encode() if data else None
        try:
            with opener.open(Request(u, data=body, headers=headers), timeout=TIMEOUT) as r:
                return r.status, r.geturl(), r.read(30_000_000).decode("utf-8", errors="replace")
        except HTTPError as e:
            return e.code, u, ""
        except (URLError, TimeoutError) as e:
            raise RuntimeError(f"Ulanish xatosi: {getattr(e, 'reason', e)}") from None

    _, login_url, html = get(url)
    m = CSRF.search(html)
    if not m or "password" not in html:
        raise RuntimeError("Login formasi topilmadi (manzil noto'g'ri yoki sessiya allaqachon ochiq).")
    user, pw = credentials()
    _, _, html = get(
        login_url,
        {"csrfmiddlewaretoken": m.group(1) or m.group(2), "username": user, "password": pw},
        referer=login_url,
    )
    pw = ""
    if re.search(r"""type=["']password["']""", html):
        raise RuntimeError("Kirish bo'lmadi (login sahifasi qaytdi). Login/parolni tekshiring.")
    status, _, html = get(url, referer=host.rstrip("/") + "/")
    if status != 200 or not html:
        raise RuntimeError(f"Sahifa 200 qaytarmadi (status={status}).")
    if re.search(r"""type=["']password["']""", html):
        raise RuntimeError("Sessiya yo'qolgan: login sahifasi qaytdi.")
    return url, html


# --------------------------------------------------------------------------- embedded JSON
def balanced(text, start):
    depth, in_str, esc = 0, None, False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == in_str:
                in_str = None
        elif c in "\"'":
            in_str = c
        elif c in "[{":
            depth += 1
        elif c in "]}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def parse_blob(text):
    try:
        return json.loads(text)
    except ValueError:
        pass
    try:
        return ast.literal_eval(text)
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        return None


def named_blobs(html):
    """HTML ichidagi katta JSON massiv/obyektlarni {o'zgaruvchi_nomi: ma'lumot} ko'rinishida qaytaradi."""
    found, covered = {}, 0
    for m in START.finditer(html):
        if m.start() < covered:
            continue
        s = html.index("[" if html[m.start()] == "[" else "{", m.start())
        text = balanced(html, s)
        if not text or len(text) < MIN_BLOB:
            continue
        covered = s + len(text)
        before = re.sub(r"\s+", " ", html[max(0, s - 90) : s]).strip()
        nm = NAME_RE.search(before)
        data = parse_blob(text)
        if nm and data is not None and (nm.group(1) not in found or len(text) > found[nm.group(1)][0]):
            found[nm.group(1)] = (len(text), data)
    return {k: v[1] for k, v in found.items()}


# --------------------------------------------------------------------------- normalization
def to_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace(" ", "T")).replace(tzinfo=TZ)
    except ValueError:
        return None


def iso_local(dt):
    return dt.isoformat() if dt else None


def iso_utc(dt):
    return dt.astimezone(timezone.utc).isoformat() if dt else None


def norm_locomotive(row, train_id):
    end = to_dt(row.get("end_expl_date"))
    return {
        "gtk_id": row["id"],
        "name": row.get("name"),
        "garage_number": row.get("garage_number"),
        "inventory_number": row.get("inventory_number"),
        "model_name": row.get("model_name"),
        "vehicle_type_name": row.get("vehicle_type_name"),
        "division_name": row.get("division_name"),
        "start_expl_date": iso_local(to_dt(row.get("start_expl_date"))),
        "end_expl_date": iso_local(end),
        "is_active": end is None,
        "in_train_id": train_id,
    }


def norm_carriage(row, state, train_id):
    end = to_dt(row.get("end_expl_date"))
    point = (state or {}).get("point") or {}
    return {
        "gtk_id": row["id"],
        "name": re.sub(r"\s+", " ", row.get("name") or "").strip(),
        "reg_number": row.get("reg_number"),
        "inventory_number": row.get("inventory_number"),
        "model_name": row.get("model_name"),
        "start_expl_date": iso_local(to_dt(row.get("start_expl_date"))),
        "end_expl_date": iso_local(end),
        "is_active": end is None,
        "in_train_id": train_id,
        "state": None
        if not state
        else {
            "is_loaded": state.get("is_loaded"),
            "is_not_serviceable": state.get("is_not_serviceable"),
            "lat": point.get("lat"),
            "lon": point.get("lon"),
            "state_duration_s": state.get("state_duration"),
        },
    }


def norm_train(row, now):
    begin = to_dt(row.get("begin_time"))
    end = to_dt(row.get("end_time"))
    locos = sorted(row.get("locomotive_list") or [], key=lambda x: x.get("order", 0))
    cars = sorted(row.get("carriage_list") or [], key=lambda x: x.get("order", 0))
    return {
        "gtk_id": row["id"],
        "number": row.get("number"),
        "title": row.get("title"),
        "begin_time": iso_local(begin),
        "begin_time_utc": iso_utc(begin),
        "end_time": iso_local(end),
        "is_open": end is None,
        "age_days": round((now - begin).total_seconds() / 86400, 1) if begin else None,
        "locomotives": [
            {"gtk_id": x["locomotive"], "name": x.get("name"), "is_main": x.get("is_main"),
             "is_backward": x.get("is_backward"), "order": x.get("order")}
            for x in locos
        ],
        "carriages": [
            {"gtk_id": x["carriage"], "name": re.sub(r"\s+", " ", x.get("name") or "").strip(), "order": x.get("order")}
            for x in cars
        ],
    }


def quality_report(locomotives, carriages, trains, states_raw):
    q = {}
    q["locomotives_total"] = len(locomotives)
    q["locomotives_without_inventory"] = [l["name"] for l in locomotives if not l["inventory_number"]]
    q["locomotives_odd_inventory_format"] = [
        {"name": l["name"], "inventory_number": l["inventory_number"]}
        for l in locomotives
        if l["inventory_number"] and not (str(l["inventory_number"]).isdigit() and len(str(l["inventory_number"])) == 5)
    ]
    q["locomotives_inactive"] = [l["name"] for l in locomotives if not l["is_active"]]

    q["carriages_total"] = len(carriages)
    q["carriages_without_inventory"] = [c["name"] for c in carriages if not c["inventory_number"]]
    q["carriages_inactive"] = [c["name"] for c in carriages if not c["is_active"]]
    by_inv, by_reg = defaultdict(list), defaultdict(list)
    for c in carriages:
        if c["inventory_number"]:
            by_inv[c["inventory_number"]].append(c["gtk_id"])
        if c["reg_number"]:
            by_reg[c["reg_number"]].append(c["gtk_id"])
    q["carriages_inventory_duplicate_groups"] = {k: v for k, v in by_inv.items() if len(v) > 1}
    q["carriages_reg_number_duplicate_groups"] = {k: v for k, v in by_reg.items() if len(v) > 1}
    q["carriages_unique_reg_numbers"] = len(by_reg)

    q["trains_open"] = sum(1 for t in trains if t["is_open"])
    q["trains_older_than_days"] = {
        "days": STALE_DAYS,
        "items": [{"number": t["number"], "title": t["title"], "age_days": t["age_days"]}
                  for t in trains if t["is_open"] and (t["age_days"] or 0) > STALE_DAYS],
    }
    loads = Counter(s.get("is_loaded") for s in states_raw)
    serv = Counter(s.get("is_not_serviceable") for s in states_raw)
    q["wagon_state_fields_uninformative"] = len(loads) <= 1 and len(serv) <= 1
    q["wagon_state_counts"] = {"is_loaded": dict(map(lambda kv: (str(kv[0]), kv[1]), loads.items())),
                               "is_not_serviceable": dict(map(lambda kv: (str(kv[0]), kv[1]), serv.items()))}
    return q


def build_snapshot(html, source):
    blobs = named_blobs(html)
    missing = [k for k in ("locomotives", "carriages", "trains", "carriageStates") if k not in blobs]
    if missing:
        raise RuntimeError(f"Sahifadan kerakli bloklar topilmadi: {missing}. Sahifa tuzilishi o'zgargan bo'lishi mumkin.")
    now = datetime.now(TZ)
    trains_raw, states_raw = blobs["trains"], blobs["carriageStates"]
    loc_in_train = {x["locomotive"]: t["id"] for t in trains_raw for x in t.get("locomotive_list") or []}
    car_in_train = {x["carriage"]: t["id"] for t in trains_raw for x in t.get("carriage_list") or []}
    state_by_car = {s["carriage_id"]: s for s in states_raw}

    locomotives = [norm_locomotive(r, loc_in_train.get(r["id"])) for r in blobs["locomotives"]]
    carriages = [norm_carriage(r, state_by_car.get(r["id"]), car_in_train.get(r["id"])) for r in blobs["carriages"]]
    trains = [norm_train(r, now) for r in trains_raw]
    return {
        "fetched_at_utc": now.astimezone(timezone.utc).isoformat(),
        "source": source,
        "timezone_note": "begin_time/end_time/start_expl_date: Asia/Tashkent (UTC+5); *_utc: UTC",
        "locomotives": locomotives,
        "carriages": carriages,
        "trains": trains,
        "quality": quality_report(locomotives, carriages, trains, states_raw),
    }


# --------------------------------------------------------------------------- CLI
def print_summary(snap):
    q = snap["quality"]
    print(f"Lokomotivlar: {len(snap['locomotives'])} | Vagonlar: {len(snap['carriages'])} | Sostavlar: {len(snap['trains'])}")
    print(f"  Lokomotiv inventory yo'q: {q['locomotives_without_inventory']}")
    print(f"  Lokomotiv inventory formati g'alati: {q['locomotives_odd_inventory_format']}")
    print(f"  Nofaol lokomotivlar: {q['locomotives_inactive']}")
    print(f"  Vagon inventory yo'q: {q['carriages_without_inventory']} | nofaol: {q['carriages_inactive']}")
    print(
        f"  Vagon reg_number takrorlari: {len(q['carriages_reg_number_duplicate_groups'])} guruh "
        f"(noyob reg_number: {q['carriages_unique_reg_numbers']}) | inventory takrorlari: "
        f"{len(q['carriages_inventory_duplicate_groups'])} guruh"
    )
    print(f"  Ochiq sostavlar: {q['trains_open']} | {q['trains_older_than_days']['days']} kundan eskilari: {q['trains_older_than_days']['items']}")
    print(f"  Vagon holati maydonlari ma'lumotsiz (hammasi bir xil): {q['wagon_state_fields_uninformative']} {q['wagon_state_counts']}")


def main():
    out = Path(arg("out", "gtk_snapshot.json"))
    src_file = arg("from-html")
    try:
        if src_file:
            html = Path(src_file).read_text(encoding="utf-8", errors="replace")
            source = f"file:{Path(src_file).name}"
        else:
            url, html = fetch_page(arg("host", HOST), arg("page", PAGE), arg("query", QUERY))
            source = url
            print("Login: OK | GET: OK")
        snap = build_snapshot(html, source)
    except RuntimeError as exc:
        sys.exit(f"XATO: {exc}")
    out.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    print_summary(snap)
    print(f"\nSnapshot saqlandi: {out} (ichki ma'lumot, git'ga qo'shmang)")


if __name__ == "__main__":
    main()
