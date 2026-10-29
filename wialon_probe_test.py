
#!/usr/bin/env python3
"""TOIR Wialon read-only diagnostic probe. No database writes."""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

FLAGS = 1 | 1024 | 8192
TIMEOUT = 30
MAX_ROWS = 177
STALE_DAYS = 30


def load_env(path):
    if not path.is_file():
        raise FileNotFoundError(f".env.local topilmadi: {path}")

    env = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        env[key.strip()] = value

    return env


def api_request(host, service, params, sid=None):
    form = {
        "svc": service,
        "params": json.dumps(params, separators=(",", ":")),
    }
    if sid:
        form["sid"] = sid

    request = Request(
        host.rstrip("/") + "/wialon/ajax.html",
        data=urlencode(form).encode("utf-8"),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "TOIR-ReadOnly-Probe/2.0",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        raise RuntimeError(f"HTTP xatosi: {exc.code}") from None
    except (URLError, TimeoutError) as exc:
        reason = getattr(exc, "reason", None)
        reason_name = type(reason).__name__ if reason else type(exc).__name__
        raise RuntimeError(f"Ulanish xatosi: {reason_name}") from None

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError("API javobi JSON formatida emas.") from None

    if isinstance(result, int):
        raise RuntimeError(f"Wialon API xato kodi: {result}")

    if isinstance(result, dict) and result.get("error", 0) != 0:
        raise RuntimeError(f"Wialon API xato kodi: {result['error']}")

    return result


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def utc_time(value):
    n = number(value)
    if n is None or n <= 0:
        return None
    try:
        return datetime.fromtimestamp(n, timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


def time_text(value):
    dt = utc_time(value)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC") if dt else "mavjud emas"


def age_days(value):
    dt = utc_time(value)
    if not dt:
        return None
    return (datetime.now(timezone.utc) - dt).total_seconds() / 86400


def cfl_description(value):
    """Decode documented Wialon mileage and engine-hour calculation flags."""
    try:
        flags = int(value)
    except (TypeError, ValueError):
        return "cfl mavjud emas"

    mileage_modes = {
        0: "GPS",
        1: "mileage sensor",
        2: "relative odometer",
        3: "GPS + ignition sensor",
    }
    engine_modes = {
        0x00: "manba ko‘rsatilmagan",
        0x10: "ignition sensor",
        0x20: "absolute engine-hours sensor",
        0x40: "relative engine-hours sensor",
    }

    mileage_mode = flags & 0x00F
    engine_mode = flags & 0x0F0

    mileage_text = mileage_modes.get(
        mileage_mode, f"noma’lum mileage kodi {mileage_mode}"
    )
    engine_text = engine_modes.get(
        engine_mode, f"noma’lum engine-hours kodi {engine_mode}"
    )

    extras = []
    if flags & 0x100:
        extras.append("mileage auto-calculation")
    if flags & 0x200:
        extras.append("engine-hours auto-calculation")
    if flags & 0x400:
        extras.append("GPRS auto-calculation")

    suffix = "; ".join(extras) if extras else "qo‘shimcha auto-flaglar yo‘q"
    return f"Mileage={mileage_text}; Engine={engine_text}; {suffix}"


def main():
    repo_root = Path(__file__).resolve().parent
    env_path = repo_root / ".env.local"

    try:
        env = load_env(env_path)
    except Exception as exc:
        print(f"CONFIG XATOSI: {exc}")
        return 1

    host = env.get("WIALON_HOST", "").strip().rstrip("/")
    token = env.get("WIALON_TOKEN", "").strip()

    if not host.startswith("https://"):
        print("CONFIG XATOSI: WIALON_HOST https:// manzil bo‘lishi kerak.")
        return 1

    if not token or token.startswith("**") or any(c.isspace() for c in token):
        print("CONFIG XATOSI: WIALON_TOKEN haqiqiy token emas yoki bo‘sh.")
        return 1

    sid = None
    exit_code = 0

    print("=" * 100)
    print("TOIR / WIALON — READ-ONLY DIAGNOSTIKA V2")
    print("=" * 100)
    print(f"Host: {host}")
    print(f"Flags: {FLAGS}")
    print("Database: ulanilmaydi | Sync: bajarilmaydi | Token: yashirilgan")

    try:
        print("\n[1] Token login...")
        login = api_request(host, "token/login", {"token": token})
        sid = login.get("eid") if isinstance(login, dict) else None

        if not sid:
            raise RuntimeError("Login javobida eid topilmadi.")

        user = login.get("user", {})
        user_name = user.get("nm", "noma’lum") if isinstance(user, dict) else "noma’lum"
        print(f"LOGIN OK | Foydalanuvchi: {user_name}")

        print("\n[2] 177 ta birlikni olish...")
        result = api_request(
            host,
            "core/search_items",
            {
                "spec": {
                    "itemsType": "avl_unit",
                    "propName": "sys_name",
                    "propValueMask": "*",
                    "sortType": "sys_name",
                },
                "force": 1,
                "flags": FLAGS,
                "from": 0,
                "to": 0,
            },
            sid=sid,
        )

        items = result.get("items", [])
        total = result.get("totalItemsCount", len(items))
        print(f"API total: {total} | Qaytgan obyektlar: {len(items)}")
        print(f"dataFlags: {result.get('dataFlags', 'noma’lum')}")

        if not isinstance(items, list):
            raise RuntimeError("API javobidagi items ro‘yxat emas.")

        print("\n[3] Maydonlar mavjudligi")
        for field in ("cnm", "cneh", "cfl", "mu", "pos", "lmsg"):
            count = sum(field in item for item in items)
            print(f"{field:>5}: {count}/{len(items)}")

        missing = total - len(items)
        if missing:
            print(f"OGOHLANTIRISH: total va qaytgan obyektlar farqi: {missing}")

        now = datetime.now(timezone.utc)
        stale = []
        suspicious_mileage = []
        suspicious_hours = []
        no_position_time = []
        cfl_counts = {}

        print("\n[4] Hisoblagichlar, hisoblash usuli va xabar yangiligi")
        print("-" * 145)
        print(
            f"{'ID':>6} | {'mu':>2} | {'cnm':>14} | {'cneh':>14} | "
            f"{'cfl':>7} | {'Pozitsiya UTC':<22} | {'Yosh kun':>8} | Nomi"
        )
        print("-" * 145)

        for item in items[:MAX_ROWS]:
            uid = item.get("id", "?")
            name = str(item.get("nm", "Nomsiz")).replace("\n", " ")[:36]
            mu = item.get("mu", "?")
            cnm = number(item.get("cnm"))
            cneh = number(item.get("cneh"))
            cfl = item.get("cfl")

            cfl_counts[str(cfl)] = cfl_counts.get(str(cfl), 0) + 1

            pos = item.get("pos") if isinstance(item.get("pos"), dict) else {}
            msg = item.get("lmsg") if isinstance(item.get("lmsg"), dict) else {}

            # Position timestamp and last-message timestamp are distinct.
            pos_t = pos.get("t")
            msg_t = msg.get("t")
            selected_t = pos_t if pos_t else msg_t
            age = age_days(selected_t)

            age_text = f"{age:.1f}" if age is not None else "N/A"
            cnm_text = f"{cnm:.3f}" if cnm is not None else str(item.get("cnm", "—"))
            cneh_text = f"{cneh:.3f}" if cneh is not None else str(item.get("cneh", "—"))
            cfl_text = str(cfl) if cfl is not None else "—"

            print(
                f"{str(uid):>6} | {str(mu):>2} | {cnm_text:>14} | "
                f"{cneh_text:>14} | {cfl_text:>7} | "
                f"{time_text(selected_t):<22} | {age_text:>8} | {name}"
            )

            if age is None:
                no_position_time.append((uid, name))
            elif age > STALE_DAYS:
                stale.append((uid, name, age))

            # Diagnostic thresholds only; not assertions of bad data.
            if cnm is not None and cnm > 100_000_000:
                suspicious_mileage.append((uid, name, cnm))
            if cneh is not None and cneh > 200_000:
                suspicious_hours.append((uid, name, cneh))

        print("-" * 145)

        print("\n[5] Hisoblagich konfiguratsiyasi (cfl)")
        for value, count in sorted(cfl_counts.items()):
            print(f"cfl={value}: {count} ta birlik")

        print("\n[6] Shubhali qiymatlar va eskirgan xabarlar")
        print(f"Pozitsiya/xabar vaqti yo‘q: {len(no_position_time)}")
        print(f"{STALE_DAYS} kundan eski: {len(stale)}")
        for uid, name, days in stale[:25]:
            print(f"  ESKI: ID={uid}, {name}, {days:.1f} kun")

        print(f"cnm > 100,000,000: {len(suspicious_mileage)}")
        for uid, name, value in suspicious_mileage[:25]:
            print(f"  cnm TEKSHIRILSIN: ID={uid}, {name}, raw={value:g}")

        print(f"cneh > 200,000 soat: {len(suspicious_hours)}")
        for uid, name, value in suspicious_hours[:25]:
            print(f"  cneh TEKSHIRILSIN: ID={uid}, {name}, raw={value:g}")

        print("\n[7] cfl talqini")
        for item in items[:MAX_ROWS]:
            if item.get("cfl") is not None:
                print(
                    f"ID={item.get('id')} | {item.get('nm', 'Nomsiz')} | "
                    f"cfl={item['cfl']} (0x{int(item['cfl']):X}) | "
                    f"{cfl_description(item['cfl'])}"
                )

        print("\nTEST TUGADI. Ma’lumotlar bazasiga yozuv bajarilmadi.")

    except Exception as exc:
        print(f"\nTEST XATOSI: {exc}")
        exit_code = 1

    finally:
        if sid:
            try:
                logout = api_request(host, "core/logout", {}, sid=sid)
                if isinstance(logout, dict) and logout.get("error", 0) == 0:
                    print("LOGOUT OK: Wialon sessiyasi yopildi.")
                else:
                    print("OGOHLANTIRISH: Logout javobi kutilgan formatda emas.")
            except Exception as exc:
                print(f"OGOHLANTIRISH: Logout tasdiqlanmadi ({exc}).")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
