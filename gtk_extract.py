#!/usr/bin/env python3
"""GTK: brauzersiz login + sahifa HTML'idagi JS ichiga joylangan ma'lumot (JSON massivlar)ni ajratib olish.

Faqat urllib: bitta login POST (forma) va bitta GET. Hech qanday tugma/forma/yozuvchi so'rov yuborilmaydi.
Parol chop etilmaydi. Namunalarda sim/phone/imei kabi maydonlar yashiriladi.

Login/parol: GTK_USER / GTK_PASSWORD muhit o'zgaruvchisi yoki .env.gtk fayli (git'ga tushmaydi);
bo'lmasa so'raydi.

Ishga tushirish (URL kerak emas):
    python gtk_extract.py --path=/railway/__railway_locomotive_view/
    python gtk_extract.py --path=/railway/__railway_carriage_view/
    python gtk_extract.py --path=/railway/__railway_train/
Ixtiyoriy: --host=http://172.16.252.100  --query=EnterprisesControlRB=1  (query bo'sh bo'lsa: --query=)

Natija: konsolga xulosa + gtk_page_<nom>.html (maskalangan) + gtk_data_<nom>.json (xom ma'lumot, git'ga qo'shmang).
"""
import ast
import getpass
import json
import os
import re
import sys
from collections import Counter
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener

HOST = "http://172.16.252.100"
DEFAULT_PATH = "/railway/__railway_train/"
DEFAULT_QUERY = "EnterprisesControlRB=1"
TIMEOUT = 30
MIN_BLOB = 300  # shundan kichik massiv/obyektlar e'tiborga olinmaydi
SENSITIVE_KEY = re.compile(r"sim|phone|imei|iccid|pass|token|secret|api|key", re.I)

opener = build_opener(HTTPCookieProcessor(CookieJar()))
CSRF = re.compile(
    r"""name=["']csrfmiddlewaretoken["'][^>]*value=["']([^"']+)["']|value=["']([^"']+)["'][^>]*name=["']csrfmiddlewaretoken["']"""
)
START = re.compile(r"""\[\s*\{\s*["']|[=:(,]\s*\{\s*["']""")


def arg(name, default):
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


def mask(text):
    text = re.sub(r"""(name=["']csrfmiddlewaretoken["'][^>]*value=["'])[^"']+""", r"\1<MASKED>", text)
    text = re.sub(r"""(value=["'])[^"']+(["'][^>]*name=["']csrfmiddlewaretoken["'])""", r"\1<MASKED>\2", text)
    text = re.sub(r"""(csrf[\w-]*["']?\s*[:=]\s*["'])[^"']+""", r"\1<MASKED>", text, flags=re.I)
    return re.sub(r"[0-9a-fA-F]{32,}", "<HEX>", text)


def fetch(url, data=None, referer=None):
    headers = {"User-Agent": "toir-probe/1.0"}
    if referer:
        headers["Referer"] = referer
    body = urlencode(data).encode() if data else None
    try:
        with opener.open(Request(url, data=body, headers=headers), timeout=TIMEOUT) as r:
            raw = r.read(20_000_000)
            return r.status, r.geturl(), raw.decode("utf-8", errors="replace")
    except HTTPError as e:
        return e.code, url, ""
    except (URLError, TimeoutError) as e:
        sys.exit(f"ULANISH XATOSI: {getattr(e, 'reason', e)}")


def login(url):
    _, login_url, html = fetch(url)
    m = CSRF.search(html)
    if not m or "password" not in html:
        sys.exit("Login formasi topilmadi (sahifa login so'ramadi yoki manzil noto'g'ri).")
    user, pw = credentials()
    _, _, html = fetch(
        login_url,
        {"csrfmiddlewaretoken": m.group(1) or m.group(2), "username": user, "password": pw},
        referer=login_url,
    )
    pw = ""
    if re.search(r"""type=["']password["']""", html):
        sys.exit("Kirish bo'lmadi (login sahifasi qaytdi). Login/parolni tekshiring.")
    print("Login: OK")


def balanced(text, start):
    """text[start] ('[' yoki '{') dan boshlab mos yopuvchi qavsgacha bo'lgan bo'lakni qaytaradi."""
    depth = 0
    in_str = None
    esc = False
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
        return json.loads(text), "json"
    except ValueError:
        pass
    try:
        return ast.literal_eval(text), "python"
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        return None, None


def find_blobs(html):
    blobs = []
    covered_until = 0
    for m in START.finditer(html):
        if m.start() < covered_until:
            continue
        opener_char = "[" if html[m.start()] == "[" else "{"
        s = html.index(opener_char, m.start())
        text = balanced(html, s)
        if not text or len(text) < MIN_BLOB:
            continue
        covered_until = s + len(text)
        data, kind = parse_blob(text)
        before = re.sub(r"\s+", " ", html[max(0, s - 90) : s]).strip()[-60:]
        blobs.append({"pos": s, "length": len(text), "context": before, "kind": kind, "data": data})
    return blobs


def safe(value):
    if isinstance(value, dict):
        return {k: ("<MASKED>" if SENSITIVE_KEY.search(str(k)) and v not in (None, "") else safe(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [safe(v) for v in value[:5]]
    return value


def clip(text, limit):
    return text if len(text) <= limit else text[:limit] + " …"


def summarize(i, blob):
    data = blob["data"]
    print(f"\n=== Massiv #{i}: pos={blob['pos']} uzunlik={blob['length']} format={blob['kind'] or 'PARSE BO`LMADI'}")
    print(f"    oldidan: {blob['context']}")
    if data is None:
        return
    if isinstance(data, list) and data and all(isinstance(x, dict) for x in data[:50]):
        n = len(data)
        fill = {}
        for row in data:
            for k, v in row.items():
                fill.setdefault(k, 0)
                if v not in (None, "", [], {}):
                    fill[k] += 1
        print(f"    qatorlar: {n} | maydonlar: {len(fill)}")
        print("    to'ldirilganlik:", ", ".join(f"{k}={c}/{n}" for k, c in fill.items()))
        shown = 0
        for k in fill:
            if SENSITIVE_KEY.search(k):
                continue
            vals = [row.get(k) for row in data if isinstance(row.get(k), str)]
            if len(vals) >= max(5, n // 2):
                cnt = Counter(vals)
                if 1 < len(cnt) <= min(30, max(2, n // 2)) and shown < 6:
                    print(f"    {k}: {dict(cnt.most_common(8))}")
                    shown += 1
        for row in data[:2]:
            print("    namuna:", clip(json.dumps(safe(row), ensure_ascii=False), 800))
    elif isinstance(data, dict):
        desc = {k: (f"list[{len(v)}]" if isinstance(v, list) else type(v).__name__) for k, v in data.items()}
        print("    obyekt kalitlari:", clip(json.dumps(desc, ensure_ascii=False), 600))
    elif isinstance(data, list):
        print(f"    ro'yxat: {len(data)} ta element; dastlabki 5:", clip(json.dumps(safe(data), ensure_ascii=False), 400))


def main():
    path = arg("path", DEFAULT_PATH)
    host = arg("host", HOST).rstrip("/")
    query = arg("query", DEFAULT_QUERY)
    url = host + path + (("?" + query) if query else "")
    slug = path.strip("/").replace("/", "_") or "root"

    login(url)
    status, _, html = fetch(url, referer=host + "/")
    print(f"Sahifa: {path} | status={status} | bayt={len(html)}")
    if status != 200 or not html:
        sys.exit("Sahifa 200 qaytarmadi (yo'l mavjud emas yoki ruxsat yo'q).")
    if re.search(r"""type=["']password["']""", html):
        sys.exit("Sessiya yo'qolgan: login sahifasi qaytdi.")

    page_file = Path(f"gtk_page_{slug}.html")
    page_file.write_text(mask(html), encoding="utf-8")
    print(f"HTML saqlandi: {page_file.name} (maskalangan)")

    blobs = find_blobs(html)
    parsed = [b for b in blobs if b["data"] is not None]
    failed = [b for b in blobs if b["data"] is None and b["length"] >= 3000]
    print(f"Topilgan ma'lumot bloklari: {len(blobs)} (parse bo'ldi: {len(parsed)}; katta, lekin parse bo'lmadi: {len(failed)})")

    top = sorted(blobs, key=lambda b: -b["length"])[:8]
    for i, b in enumerate(top, 1):
        summarize(i, b)

    data_file = Path(f"gtk_data_{slug}.json")
    data_file.write_text(
        json.dumps(
            [{"pos": b["pos"], "length": b["length"], "context": b["context"], "data": b["data"]} for b in parsed],
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"\nXom ma'lumot saqlandi: {data_file.name} (git'ga qo'shmang)")


if __name__ == "__main__":
    main()
