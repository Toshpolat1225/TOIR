"""Live check of the command centre (`/assistant/*`): intents in Uzbek and Russian, spoken numbers, scoping, permissions, the two-step write.

Reads real data (a live locomotive, wagon and train found through the GPS API); the only writes are ZZTEST-prefixed (an asset, an employee and one
work order created through the confirmation flow), removed by zz_cleanup_all.sql. Needs zz_lib.py's files next to it. Set TOIR_ROOT_CERT.
"""
import os
import time
from uuid import uuid4

import httpx

from zz_lib import CREDS, IDS, rec

HOST = os.environ.get("TOIR_HOST", "192.168.28.104")
ROOT_CERT = os.environ.get("TOIR_ROOT_CERT", "toir-local-root.crt")
API = f"https://{HOST}/api/v1"
AREA = "assistant"
UZ_DIGITS = {"0": "nol", "1": "bir", "2": "ikki", "3": "uch", "4": "to'rt", "5": "besh", "6": "olti", "7": "yetti", "8": "sakkiz", "9": "to'qqiz"}
RU_DIGITS = {"0": "ноль", "1": "один", "2": "два", "3": "три", "4": "четыре", "5": "пять", "6": "шесть", "7": "семь", "8": "восемь", "9": "девять"}


def login(role):
    c = httpx.Client(base_url=API, timeout=120, verify=ROOT_CERT)
    r = c.post("/auth/login", json={"email": CREDS[role]["email"], "password": CREDS[role]["password"]})
    r.raise_for_status()
    return c, {"Authorization": f"Bearer {r.json()['access_token']}"}


def ok(name, cond, detail="", sev="high"):
    rec(AREA, name, "PASS" if cond else "FAIL", str(detail)[:220], sev)


admin, ah = login("admin")
master, mh = login("master")


def say(who, text, headers, **extra):
    r = who.post("/assistant/command", json={"text": text, **extra}, headers=headers)
    return r.status_code, (r.json() if r.status_code == 200 else {})


ok("assistant: no token is refused", httpx.Client(base_url=API, timeout=30, verify=ROOT_CERT).post("/assistant/command", json={"text": "yordam"}).status_code == 401)
st = admin.get("/assistant/status", headers=ah)
ok("status: reports whether the voice service answers", st.status_code == 200 and "voice_available" in st.json(), st.text[:120])
voice = st.json().get("voice_available") if st.status_code == 200 else False
hp = admin.get("/assistant/help", headers=ah).json()
ok("help: grouped examples for the admin (>= 7 groups)", len(hp.get("groups", [])) >= 7 and all(g["examples"] for g in hp["groups"]), len(hp.get("groups", [])))
mhp = master.get("/assistant/help", headers=mh).json()
ok("help: a master sees fewer groups than the admin (no scales, no admin)", {g["module"] for g in mhp["groups"]} < {g["module"] for g in hp["groups"]}, [g["module"] for g in mhp["groups"]])

# ---- real units ----
loco = admin.get("/gps/overview", params={"limit": 200}, headers=ah).json()["items"]
loco = next(i for i in loco if i["gtk_linked"] and i["wialon_linked"])
inv = loco["inv_number"]
wag = admin.get("/gps/wagons", params={"in_train": "true", "limit": 200}, headers=ah).json()["items"]
wag = next(w for w in wag if w["asset_id"] and w["inv_number"] and w["inv_number"].isdigit() and w["train_number"])
winv, train_no = wag["inv_number"], wag["train_number"]

CASES = [
    (f"{inv} qayerda", "gps.where"), (f"где {inv}", "gps.where"), (f"{inv} GPS holati", "gps.status"), (f"{inv} bugun necha km yurdi", "gps.km"),
    (f"сколько проехал {inv} вчера", "gps.km"), (f"{inv} uchun Wialon va GTK nega farq qildi", "gps.why_diff"), ("o'lik GTK trekerlar", "gps.dead_trackers"),
    ("какие трекеры не работают", "gps.dead_trackers"), ("GPS xulosasi", "gps.summary"), (f"{inv} ni xaritada ko'rsat", "map.show"),
    (f"vagon {winv} qaysi lokomotiv bilan", "wagon.loco"), (f"с каким локомотивом вагон {winv}", "wagon.loco"), (f"sostav {train_no}", "train.info"),
    (f"{inv} probegi", "mileage.asset"), (f"пробег {winv}", "mileage.asset"), (f"{inv} haqida ma'lumot", "asset.info"), (f"{inv} ni top", "find.asset"), (inv, "find.asset"),
    ("muddati o'tgan ТО", "to.overdue"), ("график ТО на месяц", "to.schedule"), (f"{inv} keyingi ТО qachon", "to.next"),
    ("nechta naryad ochiq", "wo.count"), ("открытые наряды", "wo.list"), (f"{inv} naryadlari", "wo.by_asset"),
    ("bugun nechta sostav tortildi", "scales.today"), (f"vagon {winv} yuk tarixi", "scales.wagon"), ("Wialon oxirgi marta qachon yangilandi", "sys.sync_status"),
    ("oxirgi audit hodisalari", "admin.audit_recent"), ("xaritani och", "nav.open"), ("открой наряды", "nav.open"), ("yordam", "sys.help"),
]
for text, intent in CASES:
    code, out = say(admin, text, ah)
    good = code == 200 and out.get("intent") == intent and out.get("status") in ("ok", "needs_clarification") and (out.get("cards") or out.get("navigate"))
    ok(f"admin: «{text}» -> {intent}", good, (code, out.get("intent"), out.get("status")))
code, out = say(admin, "xaritani och", ah)
ok("navigation: «xaritani och» opens the map", out.get("navigate") == "/dashboard/map", out.get("navigate"))
code, out = say(admin, f"{inv} qayerda", ah)
ok("answer: the unit's position card has rows and an entity for the follow-up", out["cards"] and out["cards"][0]["rows"] and out["entities"] and out["entities"][0]["label"] == inv, out.get("entities"))
ent = out["entities"][0]
code, out = say(admin, "bu lokomotiv GPS holati", ah, context={"last_entity": ent})
ok("context: «bu lokomotiv» continues with the last unit", out.get("intent") == "gps.status" and out["entities"][0]["label"] == inv, (out.get("intent"), out.get("status")))

# ---- spoken numbers ----
if inv.isdigit():
    uz = " ".join(UZ_DIGITS[d] for d in inv) + " qayerda"
    ru = "где " + " ".join(RU_DIGITS[d] for d in inv)
    for spoken in (uz, ru):
        code, out = say(admin, spoken, ah, source="voice", stt_confidence=0.9)
        ok(f"spoken digits: «{spoken[:40]}…» finds {inv}", out.get("intent") == "gps.where" and out.get("entities") and out["entities"][0]["label"] == inv, (out.get("heard"), out.get("status")))

# ---- unmatched, wrong input, injection-ish text ----
code, out = say(admin, "salom qalaysan", ah)
ok("unmatched: a polite non-answer with suggestions", out.get("status") == "unmatched" and len(out.get("suggestions", [])) >= 3, out.get("status"))
for text in ("'; DROP TABLE users; --", "<script>alert(1)</script>", "x" * 399):
    code, out = say(admin, text, ah)
    ok(f"hostile text is just unmatched: {text[:20]!r}", code == 200 and out.get("status") in ("unmatched", "ok", "needs_clarification"), (code, out.get("status")))
ok("validation: empty and over-long text are 422", admin.post("/assistant/command", json={"text": ""}, headers=ah).status_code == 422 and admin.post("/assistant/command", json={"text": "x" * 401}, headers=ah).status_code == 422)

# ---- scoping and permissions ----
code, out = say(master, "bugun nechta sostav tortildi", mh)
ok("master: scales are denied", out.get("status") == "denied", out.get("status"))
code, out = say(master, f"{inv} qayerda", mh)
ok("master (empty section): a live unit of another section is never revealed", out.get("status") in ("needs_clarification", "ok") and not out.get("entities"), (out.get("status"), out.get("entities")))
code, out = say(master, f"sostav {train_no}", mh)
ok("master: a train of other sections is not detailed", not any(r["label"].lower().startswith("локомотив") and inv in r["value"] for c in out.get("cards", []) for r in c.get("rows", [])), out.get("status"))

# ---- the two-step write on a ZZTEST asset ----
A = IDS["sections"]["A"]
tag = uuid4().hex[:4].upper()
num = str(int(time.time()) % 100000 + 10000)
zz_inv = f"ZZTEST-{num}"
model = admin.get("/fixed-assets/models", params={"asset_type": "locomotive", "limit": 1}, headers=ah).json()["items"][0]["id"]
ra = admin.post("/fixed-assets", json={"inv_number": zz_inv, "asset_type": "locomotive", "section_id": A, "name": zz_inv, "model_id": model, "serial_number": f"ZZ{tag}"}, headers=ah)
ok("setup: a ZZTEST locomotive", ra.status_code == 201, ra.text[:100])
re_ = admin.post("/employees", json={"tab_number": f"ZZTEST-AE{tag}", "full_name": "ZZTEST assistant executor", "section_id": A}, headers=ah)
ok("setup: a ZZTEST employee (the executor)", re_.status_code == 201, re_.text[:100])
asset_id = ra.json()["id"] if ra.status_code == 201 else None


def count_orders():
    r = admin.get("/work-orders", params={"fixed_asset_id": asset_id, "limit": 50}, headers=ah)
    return r.json().get("total", len(r.json().get("items", []))) if r.status_code == 200 else -1


if asset_id:
    before = count_orders()
    code, out = say(admin, f"{num} uchun naryad och", ah)
    ok("write: «naryad och» only asks (status needs_confirm, a summary, a token)", out.get("status") == "needs_confirm" and out.get("confirm") and out["confirm"]["summary"], (out.get("status"), out.get("cards")))
    ok("write: nothing was written before the confirmation", count_orders() == before, (before, count_orders()))
    token = (out.get("confirm") or {}).get("token", "x" * 12)
    r = master.post("/assistant/confirm", json={"token": token}, headers=mh)
    ok("write: another user cannot use the token", r.status_code == 200 and r.json().get("status") == "error" and count_orders() == before, r.text[:100])
    r = admin.post("/assistant/confirm", json={"token": token}, headers=ah)
    ok("write: the owner confirms -> the order is created", r.status_code == 200 and r.json().get("status") == "ok" and count_orders() == before + 1, r.text[:160])
    r = admin.post("/assistant/confirm", json={"token": token}, headers=ah)
    ok("write: the token works once (a second tap creates nothing)", r.json().get("status") == "error" and count_orders() == before + 1, r.text[:100])
    code, out = say(admin, f"{num} uchun naryad och", ah)
    r = admin.post("/assistant/confirm", json={"token": out["confirm"]["token"], "approve": False}, headers=ah)
    ok("write: cancel creates nothing", r.json().get("status") == "ok" and count_orders() == before + 1, r.text[:100])
    code, out = say(master, f"{inv} uchun naryad och", mh)  # a LIVE unit of another section (the master belongs to the ZZTEST section)
    ok("write: a master cannot even draft an order for a unit of another section", out.get("status") != "needs_confirm" and not out.get("confirm"), out.get("status"))
    code, out = say(master, f"{num} uchun naryad och", mh)
    ok("write: a master CAN draft for a unit of his own section (and cancels it)", out.get("status") == "needs_confirm", out.get("status"))
    if out.get("confirm"):
        master.post("/assistant/confirm", json={"token": out["confirm"]["token"], "approve": False}, headers=mh)
    orders = admin.get("/work-orders", params={"fixed_asset_id": asset_id, "limit": 5}, headers=ah).json().get("items", [])
    if orders:
        no = orders[0].get("order_number") or orders[0].get("number") or ""
        tail = "".join(ch for ch in str(no) if ch.isdigit())[-4:]
        if len(tail) >= 3:
            code, out = say(admin, f"naryad {tail} jarayonda", ah)
            ok("write: «naryad N jarayonda» drafts a status change", out.get("status") in ("needs_confirm", "needs_clarification"), (out.get("status"), out.get("cards")))

# ---- the log and the admin list ----
um = admin.get("/assistant/unmatched", headers=ah)
ok("admin: the unmatched list shows the sentence nobody understood", um.status_code == 200 and any("salom" in i["text"] for i in um.json()["items"]), um.status_code)
ok("master: the unmatched list is admin only", master.get("/assistant/unmatched", headers=mh).status_code == 403)
time.sleep(61)  # a fresh window
codes = [admin.post("/assistant/command", json={"text": "yordam"}, headers=ah).status_code for _ in range(70)]
ok("rate limit: 429 appears after the 60th command of a minute", 429 in codes and codes.count(200) <= 60, (codes.count(200), codes.count(429)), sev="medium")
# ---- voice endpoint contracts (no real audio needed) ----
r = admin.post("/assistant/transcribe", files={"audio": ("a.txt", b"hello", "text/plain")}, headers=ah)
ok("transcribe: a non-audio file is 415", r.status_code == 415, r.status_code)
r = admin.post("/assistant/transcribe", files={"audio": ("a.webm", b"", "audio/webm")}, headers=ah)
ok("transcribe: an empty file is 422", r.status_code == 422, r.status_code)
r = admin.post("/assistant/transcribe", files={"audio": ("a.webm", b"x" * (2 * 1024 * 1024 + 10), "audio/webm")}, headers=ah)
ok("transcribe: over 2 MB is 413", r.status_code == 413, r.status_code)
if voice:
    r = admin.post("/assistant/transcribe", files={"audio": ("a.webm", b"not really audio", "audio/webm")}, headers=ah)
    ok("transcribe: broken audio is a clean 4xx/5xx, not a crash", r.status_code in (415, 422, 503), r.status_code)
print("done: assistant")
