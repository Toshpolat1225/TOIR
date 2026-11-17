"""TOIR weighing-scale collector (Windows).

Reads the two scale PCs' Access databases READ-ONLY over SMB and pushes new / changed rows to TOIR (`POST /api/v1/scales/ingest`).
Why a Windows program: the Access ODBC driver and the SMB1 share credentials (Windows Credential Manager, `cmdkey`) live on this PC,
not in the Linux containers. It never writes to a scale PC and never prints a secret.

Usage (see README.md):
  python collector.py --once                    one incremental pass (what the scheduler runs every minute)
  python collector.py --loop 60                 repeat forever, one pass per 60 s
  python collector.py --rescan-days 3 --once    re-read the last 3 days (catches an operator's later edits); daily is enough
  python collector.py --backfill-live --once    push the whole live database once (since --since)
  python collector.py --backfill-archives       push every monthly archive of both scales once
  python collector.py --check                   only test the connections (no push)

Environment: SCALES_INGEST_TOKEN (required except --check), TOIR_URL (default https://192.168.28.104), TOIR_CA_FILE (PEM; default: toir-local-root.crt in the repo root),
SCALES_POSTS (default "93=192.168.19.93,97=192.168.19.97").
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import ssl
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import date, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

try:
    import pyodbc
except ImportError:  # pragma: no cover
    sys.exit("pyodbc is not installed: py -3 -m pip install pyodbc")

DRIVER = "{Microsoft Access Driver (*.mdb, *.accdb)}"
STATE_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "toir_scales"
STATE_FILE = STATE_DIR / "state.json"
LOG_FILE = STATE_DIR / "collector.log"
MONTHS = {"январь": 1, "февраль": 2, "март": 3, "апрель": 4, "май": 5, "июнь": 6, "июль": 7, "август": 8, "сентябрь": 9, "октябрь": 10, "ноябрь": 11, "декабрь": 12}
RESCAN_IDS = 120        # trains re-read every pass (an operator edits a train just after weighing it)
RESCAN_WAGON_IDS = 1500
TRAIN_CHUNK = 500
WEIGHING_CHUNK = 3000
BS = chr(92)
DEFAULT_URL = "https://192.168.28.104"  # the proxy redirects plain HTTP to HTTPS; the local root certificate (repo root) is trusted below
ROOT_CERT = Path(__file__).resolve().parents[2] / "toir-local-root.crt"

log = logging.getLogger("scales")


def setup_logging() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handlers = [RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8"), logging.StreamHandler(sys.stdout)]
    for h in handlers:
        h.setFormatter(fmt)
        log.addHandler(h)
    log.setLevel(logging.INFO)


def posts() -> dict[str, str]:
    raw = os.environ.get("SCALES_POSTS", "93=192.168.19.93,97=192.168.19.97")
    return {pair.split("=")[0].strip(): pair.split("=")[1].strip() for pair in raw.split(",") if "=" in pair}


def unc(host: str, *parts: str) -> str:
    return BS * 2 + host + BS + "Scales$" + "".join(BS + p for p in parts)


def connect(path: str) -> pyodbc.Connection:
    return pyodbc.connect(f"DRIVER={DRIVER};DBQ={path};ReadOnly=1;", autocommit=True, timeout=30)


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1), encoding="utf-8")
    tmp.replace(STATE_FILE)


def f(value):
    return None if value is None else float(value)


def iso(value):
    return value.isoformat() if isinstance(value, (datetime, date)) else None


def clean(text, limit=40):
    return None if text is None else str(text).strip()[:limit] or None


TRAIN_SQL = (
    "SELECT [Код состава],[Регистрация],[Номер состава],[Количество вагонов],[Вес],[Вес по документам],[Начало взвешивания],"
    "[Конец взвешивания],[Код груза],[Экскаватор],[Код оператора] FROM [Составы] "
)
WEIGHING_SQL = (
    "SELECT [Код вагона],[Код состава],[Номер по порядку],[Вагон],[Брутто],[Тара],[Нетто],[Грузоподъемность],[Перегруз],[Скорость],"
    "[Осей],[Дата взвешивания] FROM [Вагоны] "
)


def train_row(r) -> dict:
    return {
        "src_id": r[0], "registered_on": iso(r[1].date() if isinstance(r[1], datetime) else r[1]), "loco_number": clean(r[2]),
        "declared_wagons": r[3], "reported_weight_t": f(r[4]), "doc_weight_t": f(r[5]), "started_at": iso(r[6]), "finished_at": iso(r[7]),
        "cargo_code": r[8], "excavator": r[9], "operator_code": r[10],
    }


def weighing_row(r) -> dict:
    return {
        "src_id": r[0], "train_src_id": r[1], "position": r[2], "unit_label": clean(r[3]), "gross_t": f(r[4]), "tare_t": f(r[5]),
        "net_t": f(r[6]), "capacity_t": f(r[7]), "overload_t": f(r[8]), "speed_kmh": f(r[9]), "axles": r[10], "weighed_at": iso(r[11]),
    }


def dictionaries(cur) -> dict:
    out: dict = {"cargo": [{"code": c, "name": clean(n, 100) or str(c)} for c, n in cur.execute("SELECT [Код груза],[Наименование] FROM [Грузы]").fetchall()]}
    row = cur.execute("SELECT [Тара по умолчанию],[Норма] FROM [Реквизиты предприятия]").fetchone()
    if row:
        out["tare_default_t"], out["capacity_norm_t"] = f(row[0]), f(row[1])
    return out


def push(payload: dict) -> dict:
    token = os.environ.get("SCALES_INGEST_TOKEN", "")
    base = os.environ.get("TOIR_URL", DEFAULT_URL).rstrip("/")
    request = urllib.request.Request(
        f"{base}/api/v1/scales/ingest", data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    ca_file = os.environ.get("TOIR_CA_FILE") or (str(ROOT_CERT) if ROOT_CERT.exists() else None)
    context = ssl.create_default_context(cafile=ca_file) if ca_file and base.startswith("https") else None
    try:
        with urllib.request.urlopen(request, timeout=120, context=context) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"TOIR answered {exc.code}: {body}") from None


def send(code: str, mode: str, period: str | None, extras: dict, trains: list[dict], weighings: list[dict]) -> dict:
    """Chunked push; raises on the first failure so the caller does not advance its watermark."""
    totals = {"trains_changed": 0, "weighings_changed": 0, "weighings_orphaned": 0, "rematched": 0}
    t_chunks = [trains[i : i + TRAIN_CHUNK] for i in range(0, len(trains), TRAIN_CHUNK)] or [[]]
    w_chunks = [weighings[i : i + WEIGHING_CHUNK] for i in range(0, len(weighings), WEIGHING_CHUNK)]
    jobs = [(t, []) for t in t_chunks] + [([], w) for w in w_chunks]  # all trains first, so every weighing finds its train
    for t, w in jobs:
        if not t and not w and (trains or weighings):
            continue
        result = push({"post": code, "mode": mode, "period": period, **extras, "trains": t, "weighings": w})
        for key in totals:
            totals[key] += result.get(key, 0)
    return totals


def read_window(cur, since_train: int, since_weighing: int, since_date: date, rescan_from: date | None) -> tuple[list[dict], list[dict]]:
    """Recent rows. The scale program deletes old rows when it archives, and Access then fails (HY109 "record deleted") on an
    id range that crosses those stale index entries, so: no watermark yet or a failed id range = scan by date instead (always safe),
    an established watermark = a short id range near the end (fast, never touches the old region)."""
    start = datetime.combine(since_date, datetime.min.time())
    if rescan_from is not None:
        start = datetime.combine(rescan_from, datetime.min.time())

    def by_date(first: datetime):
        t = cur.execute(TRAIN_SQL + "WHERE [Начало взвешивания] >= ? ORDER BY [Код состава]", first).fetchall()
        w = cur.execute(WEIGHING_SQL + "WHERE [Дата взвешивания] >= ? ORDER BY [Код вагона]", first).fetchall()
        return t, w

    if rescan_from is not None or since_train <= 0 or since_weighing <= 0:
        trains, weighings = by_date(start)
    else:
        try:
            trains = cur.execute(TRAIN_SQL + "WHERE [Код состава] > ? AND [Начало взвешивания] >= ? ORDER BY [Код состава]", since_train, start).fetchall()
            weighings = cur.execute(WEIGHING_SQL + "WHERE [Код вагона] > ? AND [Дата взвешивания] >= ? ORDER BY [Код вагона]", since_weighing, start).fetchall()
        except pyodbc.Error as exc:
            log.warning("id range failed (%s): reading the last 2 days by date instead", str(exc)[:60])
            trains, weighings = by_date(max(start, datetime.combine(date.fromordinal(date.today().toordinal() - 2), datetime.min.time())))
    return [train_row(r) for r in trains], [weighing_row(r) for r in weighings]


def incremental(code: str, host: str, state: dict, since: date, rescan_days: int) -> None:
    mine = state.setdefault(code, {})
    conn = connect(unc(host, "Bridge_Scale.mdb"))
    try:
        cur = conn.cursor()
        last_train, last_w = int(mine.get("train", 0)), int(mine.get("weighing", 0))
        rescan_from = date.fromordinal(date.today().toordinal() - rescan_days) if rescan_days > 0 else None
        trains, weighings = read_window(cur, max(0, last_train - RESCAN_IDS), max(0, last_w - RESCAN_WAGON_IDS), since, rescan_from)
        extras = dictionaries(cur)
    finally:
        conn.close()
    totals = send(code, "live", None, extras, trains, weighings)
    if trains:
        mine["train"] = max(last_train, max(t["src_id"] for t in trains))
    if weighings:
        mine["weighing"] = max(last_w, max(w["src_id"] for w in weighings))
    mine["last_ok"] = datetime.now().isoformat(timespec="seconds")
    log.info("post %s: read %d trains / %d weighings, changed %d / %d, orphaned %d, rematched %d",
             code, len(trains), len(weighings), totals["trains_changed"], totals["weighings_changed"], totals["weighings_orphaned"], totals["rematched"])


def backfill_database(code: str, path: str, mode: str, period: str | None, since: date) -> None:
    conn = connect(path)
    try:
        cur = conn.cursor()
        start = datetime.combine(since, datetime.min.time())
        trains = [train_row(r) for r in cur.execute(TRAIN_SQL + "WHERE [Начало взвешивания] >= ? ORDER BY [Код состава]", start).fetchall()]
        ids = {t["src_id"] for t in trains}
        weighings = [w for w in (weighing_row(r) for r in cur.execute(WEIGHING_SQL + "WHERE [Дата взвешивания] >= ? ORDER BY [Код вагона]", start).fetchall()) if w["train_src_id"] in ids]
        extras = dictionaries(cur)
    finally:
        conn.close()
    totals = send(code, mode, period, extras, trains, weighings)
    log.info("post %s %s: %d trains / %d weighings pushed, changed %d / %d, orphaned %d, rematched %d",
             code, period or "live", len(trains), len(weighings), totals["trains_changed"], totals["weighings_changed"], totals["weighings_orphaned"], totals["rematched"])


def archive_period(name: str) -> str | None:
    match = re.match(r"^\s*\d+\.\s*([А-Яа-яЁё]+)\s+(\d{4})", name)
    if not match or match.group(1).lower() not in MONTHS:
        return None
    return f"{match.group(2)}-{MONTHS[match.group(1).lower()]:02d}"


def backfill_archives(since: date) -> None:
    for code, host in posts().items():
        folder = unc(host, "Archives")
        for name in sorted(os.listdir(folder)):
            period = archive_period(name) if name.lower().endswith(".mdb") else None
            if period is None:
                continue
            tmp = Path(tempfile.mkdtemp(prefix="toir_arch_")) / "a.mdb"
            try:
                shutil.copyfile(folder + BS + name, tmp)  # a small read-only copy; the scale PC's file is never opened
                backfill_database(code, str(tmp), "archive", period, since)
            except Exception as exc:  # one broken archive must not stop the others
                log.warning("post %s archive %s skipped: %s", code, name, str(exc)[:200])
            finally:
                shutil.rmtree(tmp.parent, ignore_errors=True)


def check() -> int:
    bad = 0
    for code, host in posts().items():
        try:
            conn = connect(unc(host, "Bridge_Scale.mdb"))
            cur = conn.cursor()
            trains = cur.execute("SELECT MAX([Код состава]) FROM [Составы]").fetchone()[0]
            last = cur.execute("SELECT MAX([Дата взвешивания]) FROM [Вагоны]").fetchone()[0]
            conn.close()
            log.info("post %s (%s): ok, last train id %s, last weighing %s", code, host, trains, last)
        except Exception as exc:
            bad += 1
            log.error("post %s (%s): FAILED %s", code, host, str(exc)[:200])
    return 1 if bad else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="TOIR weighing-scale collector")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--loop", type=int, metavar="SECONDS")
    parser.add_argument("--rescan-days", type=int, default=0)
    parser.add_argument("--backfill-live", action="store_true")
    parser.add_argument("--backfill-archives", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--since", default="2025-01-01", help="ignore older rows (the databases keep 2009-2012 test rows)")
    args = parser.parse_args()
    setup_logging()
    since = date.fromisoformat(args.since)
    if args.check:
        return check()
    if not os.environ.get("SCALES_INGEST_TOKEN"):
        log.error("SCALES_INGEST_TOKEN is not set")
        return 2
    if args.backfill_archives:
        backfill_archives(since)
        return 0
    if args.backfill_live:
        for code, host in posts().items():
            backfill_database(code, unc(host, "Bridge_Scale.mdb"), "live", None, since)
        return 0
    while True:
        state = load_state()
        failed = False
        for code, host in posts().items():  # one scale being down must not stop the other
            try:
                incremental(code, host, state, since, args.rescan_days)
            except Exception as exc:
                failed = True
                log.error("post %s: pass failed: %s", code, str(exc)[:300])
        save_state(state)
        if not args.loop:
            return 1 if failed else 0
        time.sleep(args.loop)


if __name__ == "__main__":
    raise SystemExit(main())
