import ast
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import SecretStr

TIMEOUT_SECONDS = 60
MIN_BLOB = 300
STALE_DAYS = 30
TZ = timezone(timedelta(hours=5))
REQUIRED_BLOCKS = ("locomotives", "carriages", "trains", "carriageStates")

CSRF = re.compile(
    r"""name=["']csrfmiddlewaretoken["'][^>]*value=["']([^"']+)["']|value=["']([^"']+)["'][^>]*name=["']csrfmiddlewaretoken["']"""
)
START = re.compile(
    r"""\[\s*(?:\{\s*["']|(?=\s*\]))|[=:(,]\s*\{\s*["']"""
)
NAME_RE = re.compile(r"(\w+)\s*=\s*(?:HashList\.fromList\()?$")


class GtkClientError(Exception):
    pass


class GtkLoginError(GtkClientError):
    pass


class GtkParseError(GtkClientError):
    pass


def balanced(text: str, start: int) -> str | None:
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


def parse_blob(text: str) -> Any:
    try:
        return json.loads(text)
    except ValueError:
        pass
    try:
        return ast.literal_eval(text)
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        return None


def named_blobs(html: str) -> dict[str, Any]:
    found: dict[str, tuple[int, Any]] = {}
    covered = 0
    for match in START.finditer(html):
        if match.start() < covered:
            continue
        start = html.index("[" if html[match.start()] == "[" else "{", match.start())
        text = balanced(html, start)
        if not text:
            continue
        before = re.sub(r"\s+", " ", html[max(0, start - 90) : start]).strip()
        name_match = NAME_RE.search(before)
        if len(text) < MIN_BLOB and (
            name_match is None or name_match.group(1) not in REQUIRED_BLOCKS
        ):
            continue
        covered = start + len(text)
        data = parse_blob(text)
        if (
            name_match
            and data is not None
            and (
                name_match.group(1) not in found
                or len(text) > found[name_match.group(1)][0]
            )
        ):
            found[name_match.group(1)] = (len(text), data)
    return {name: value for name, (_, value) in found.items()}


def to_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace(" ", "T"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TZ)
    return parsed.astimezone(timezone.utc)


def norm_locomotive(row: dict[str, Any], train_id: int | None) -> dict[str, Any]:
    end = to_dt(row.get("end_expl_date"))
    return {
        "gtk_id": int(row["id"]),
        "name": row.get("name"),
        "garage_number": row.get("garage_number"),
        "inventory_number": row.get("inventory_number"),
        "model_name": row.get("model_name"),
        "vehicle_type_name": row.get("vehicle_type_name"),
        "division_name": row.get("division_name"),
        "start_expl_date": to_dt(row.get("start_expl_date")),
        "end_expl_date": end,
        "is_active": end is None,
        "in_train_id": train_id,
    }


def norm_carriage(
    row: dict[str, Any], state: dict[str, Any] | None, train_id: int | None
) -> dict[str, Any]:
    end = to_dt(row.get("end_expl_date"))
    point = (state or {}).get("point") or {}
    return {
        "gtk_id": int(row["id"]),
        "name": re.sub(r"\s+", " ", row.get("name") or "").strip(),
        "reg_number": row.get("reg_number"),
        "inventory_number": row.get("inventory_number"),
        "model_name": row.get("model_name"),
        "start_expl_date": to_dt(row.get("start_expl_date")),
        "end_expl_date": end,
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
        "is_loaded": (state or {}).get("is_loaded"),
        "is_not_serviceable": (state or {}).get("is_not_serviceable"),
        "lat": point.get("lat"),
        "lon": point.get("lon"),
        "state_duration_s": (state or {}).get("state_duration"),
    }


def norm_train(row: dict[str, Any], now: datetime) -> dict[str, Any]:
    begin = to_dt(row.get("begin_time"))
    end = to_dt(row.get("end_time"))
    age_days = (now - begin).total_seconds() / 86400 if begin else None
    locos = sorted(row.get("locomotive_list") or [], key=lambda item: item.get("order", 0))
    carriages = sorted(
        row.get("carriage_list") or [], key=lambda item: item.get("order", 0)
    )
    return {
        "gtk_id": int(row["id"]),
        "number": row.get("number"),
        "title": row.get("title"),
        "begin_time": begin,
        "begin_time_utc": begin,
        "end_time": end,
        "is_open": end is None,
        "age_days": round(age_days, 1) if age_days is not None else None,
        "_age_days": age_days,
        "locomotives": [
            {
                "gtk_id": int(item["locomotive"]),
                "name": item.get("name"),
                "is_main": bool(item.get("is_main")),
                "is_backward": item.get("is_backward"),
                "order": item.get("order"),
            }
            for item in locos
        ],
        "carriages": [
            {
                "gtk_id": int(item["carriage"]),
                "name": re.sub(r"\s+", " ", item.get("name") or "").strip(),
                "order": item.get("order"),
            }
            for item in carriages
        ],
    }


def quality_report(
    locomotives: list[dict[str, Any]],
    carriages: list[dict[str, Any]],
    trains: list[dict[str, Any]],
    states_raw: list[dict[str, Any]],
) -> dict[str, Any]:
    quality: dict[str, Any] = {
        "locomotives_total": len(locomotives),
        "locomotives_without_inventory": [
            locomotive["name"]
            for locomotive in locomotives
            if not locomotive["inventory_number"]
        ],
        "locomotives_odd_inventory_format": [
            {
                "name": locomotive["name"],
                "inventory_number": locomotive["inventory_number"],
            }
            for locomotive in locomotives
            if locomotive["inventory_number"]
            and not (
                str(locomotive["inventory_number"]).isdigit()
                and len(str(locomotive["inventory_number"])) == 5
            )
        ],
        "locomotives_inactive": [
            locomotive["name"]
            for locomotive in locomotives
            if not locomotive["is_active"]
        ],
        "carriages_total": len(carriages),
        "carriages_without_inventory": [
            carriage["name"]
            for carriage in carriages
            if not carriage["inventory_number"]
        ],
        "carriages_inactive": [
            carriage["name"] for carriage in carriages if not carriage["is_active"]
        ],
    }
    by_inventory: dict[str, list[int]] = defaultdict(list)
    by_reg: dict[str, list[int]] = defaultdict(list)
    for carriage in carriages:
        if carriage["inventory_number"]:
            by_inventory[str(carriage["inventory_number"])].append(
                carriage["gtk_id"]
            )
        if carriage["reg_number"]:
            by_reg[str(carriage["reg_number"])].append(carriage["gtk_id"])
    quality["carriages_inventory_duplicate_groups"] = {
        key: ids for key, ids in by_inventory.items() if len(ids) > 1
    }
    quality["carriages_reg_number_duplicate_groups"] = {
        key: ids for key, ids in by_reg.items() if len(ids) > 1
    }
    quality["carriages_unique_reg_numbers"] = len(by_reg)
    quality["trains_open"] = sum(1 for train in trains if train["is_open"])
    quality["trains_older_than_days"] = {
        "days": STALE_DAYS,
        "items": [
            {
                "number": train["number"],
                "title": train["title"],
                "age_days": train["age_days"],
            }
            for train in trains
            if train["is_open"] and (train["_age_days"] or 0) > STALE_DAYS
        ],
    }

    carriage_by_id = {carriage["gtk_id"]: carriage for carriage in carriages}
    locomotive_by_id = {
        locomotive["gtk_id"]: locomotive for locomotive in locomotives
    }
    inactive_carriages_in_open_trains = []
    train_number_mismatches = []
    for train in trains:
        if train["is_open"]:
            for member in train["carriages"]:
                carriage = carriage_by_id.get(member["gtk_id"])
                if carriage is not None and not carriage["is_active"]:
                    inactive_carriages_in_open_trains.append(
                        {"train_id": train["gtk_id"], "carriage_id": member["gtk_id"]}
                    )
        main_locomotive = next(
            (member for member in train["locomotives"] if member["is_main"]), None
        )
        locomotive = (
            locomotive_by_id.get(main_locomotive["gtk_id"])
            if main_locomotive
            else None
        )
        if (
            locomotive
            and train["number"] is not None
            and locomotive["garage_number"] is not None
            and str(train["number"]).strip()
            != str(locomotive["garage_number"]).strip()
        ):
            train_number_mismatches.append(
                {
                    "train_id": train["gtk_id"],
                    "number": train["number"],
                    "locomotive_id": locomotive["gtk_id"],
                    "garage_number": locomotive["garage_number"],
                }
            )
    quality["inactive_carriages_in_open_trains"] = inactive_carriages_in_open_trains
    quality["open_trains_older_than_days"] = [
        {"train_id": train["gtk_id"], "number": train["number"], "age_days": train["age_days"]}
        for train in trains
        if train["is_open"] and (train["_age_days"] or 0) > STALE_DAYS
    ]
    quality["train_number_locomotive_mismatches"] = train_number_mismatches

    loads = Counter(state.get("is_loaded") for state in states_raw)
    serviceability = Counter(state.get("is_not_serviceable") for state in states_raw)
    quality["wagon_state_fields_uninformative"] = (
        len(loads) <= 1 and len(serviceability) <= 1
    )
    quality["wagon_state_counts"] = {
        "is_loaded": {str(key): value for key, value in loads.items()},
        "is_not_serviceable": {
            str(key): value for key, value in serviceability.items()
        },
    }
    return quality


def build_snapshot(
    html: str, source: str, *, now: datetime | None = None
) -> dict[str, Any]:
    blobs = named_blobs(html)
    required = REQUIRED_BLOCKS
    missing = [name for name in required if name not in blobs]
    if missing:
        raise GtkParseError(f"Required GTK data blocks are missing: {', '.join(missing)}")
    if any(not isinstance(blobs[name], list) for name in required):
        raise GtkParseError("Required GTK data blocks have an invalid format")
    if any(
        not isinstance(row, dict)
        for name in required
        for row in blobs[name]
    ):
        raise GtkParseError("GTK data blocks have an invalid record")

    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    try:
        trains_raw = blobs["trains"]
        states_raw = blobs["carriageStates"]
        locomotive_train = {
            int(item["locomotive"]): int(train["id"])
            for train in trains_raw
            for item in train.get("locomotive_list") or []
        }
        carriage_train = {
            int(item["carriage"]): int(train["id"])
            for train in trains_raw
            for item in train.get("carriage_list") or []
        }
        state_by_carriage = {
            int(state["carriage_id"]): state for state in states_raw
        }
        locomotives = [
            norm_locomotive(row, locomotive_train.get(int(row["id"])))
            for row in blobs["locomotives"]
        ]
        carriages = [
            norm_carriage(
                row,
                state_by_carriage.get(int(row["id"])),
                carriage_train.get(int(row["id"])),
            )
            for row in blobs["carriages"]
        ]
        trains = [norm_train(row, now) for row in trains_raw]
        quality = quality_report(locomotives, carriages, trains, states_raw)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise GtkParseError("GTK data blocks have an invalid record") from exc

    return {
        "fetched_at": now.astimezone(timezone.utc),
        "source": source,
        "locomotives": locomotives,
        "carriages": carriages,
        "trains": trains,
        "quality": quality,
    }


class GtkClient:
    def __init__(
        self,
        host: str | None,
        username: str | None,
        password: SecretStr | None,
        page_path: str,
        page_query: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.host = host.rstrip("/") if host else None
        self.username = username.strip() if username else None
        self.password = password
        self.page_path = page_path
        self.page_query = page_query
        self.transport = transport

    async def fetch_snapshot(self) -> dict[str, Any]:
        if not self.host or not self.username or not self.password:
            raise GtkLoginError("GTK credentials or host are not configured")
        parsed_host = urlsplit(self.host)
        if parsed_host.scheme not in {"http", "https"} or not parsed_host.netloc:
            raise GtkClientError("GTK host is invalid")

        page_url = self.host + "/" + self.page_path.lstrip("/")
        if self.page_query:
            page_url += "?" + self.page_query.lstrip("?")
        try:
            async with httpx.AsyncClient(
                timeout=TIMEOUT_SECONDS,
                follow_redirects=False,
                transport=self.transport,
            ) as client:
                login_page = await client.get(page_url, follow_redirects=True)
                login_url = str(login_page.url)
                csrf_match = CSRF.search(login_page.text)
                if not csrf_match or "password" not in login_page.text.lower():
                    raise GtkLoginError("GTK login form was not found")
                csrf_token = csrf_match.group(1) or csrf_match.group(2)
                login_response = await client.post(
                    login_url,
                    data={
                        "csrfmiddlewaretoken": csrf_token,
                        "username": self.username,
                        "password": self.password.get_secret_value(),
                    },
                    headers={"Referer": login_url},
                )
                if (
                    login_response.status_code >= 400
                    or re.search(
                        r"""type=["']password["']""", login_response.text, re.I
                    )
                ):
                    raise GtkLoginError("GTK login failed")
                page_response = await client.get(
                    page_url,
                    headers={"Referer": self.host + "/"},
                )
                if page_response.status_code in {401, 403, 302, 303, 307, 308}:
                    raise GtkLoginError("GTK session is not authenticated")
                if page_response.status_code != 200 or not page_response.text:
                    raise GtkClientError(
                        f"GTK page returned HTTP {page_response.status_code}"
                    )
                if re.search(r"""type=["']password["']""", page_response.text, re.I):
                    raise GtkLoginError("GTK session is not authenticated")
                return build_snapshot(page_response.text, page_url)
        except GtkClientError:
            raise
        except httpx.TimeoutException as exc:
            raise GtkClientError("GTK request timed out") from exc
        except httpx.HTTPError as exc:
            raise GtkClientError("GTK network request failed") from exc
