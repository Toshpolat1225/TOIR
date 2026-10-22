import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import IntFlag
from typing import Any

import httpx

logger = logging.getLogger(__name__)
API_PATH = "/wialon/ajax.html"


class UnitSearchFlags(IntFlag):
    # Unit general fields (name, id, and measurement system).
    # https://sdk.wialon.com/wiki/en/sidebar/remoteapi/apiref/format/unit
    BASE = 0x00000001
    # Last message and position (UTC time, latitude, longitude, speed).
    # https://sdk.wialon.com/wiki/en/sidebar/remoteapi/apiref/format/unit
    LAST_MESSAGE_AND_POSITION = 0x00000400
    # Mileage and engine-hours counters.
    # https://sdk.wialon.com/wiki/en/sidebar/remoteapi/apiref/format/unit
    COUNTERS = 0x00002000


SEARCH_FLAGS = int(
    UnitSearchFlags.BASE
    | UnitSearchFlags.LAST_MESSAGE_AND_POSITION
    | UnitSearchFlags.COUNTERS
)
SESSION_EXPIRED_CODE = 1
MAX_ATTEMPTS = 3


class WialonClientError(Exception):
    def __init__(self, message: str, *, status_message: str | None = None) -> None:
        super().__init__(message)
        self.status_message = status_message or message


class WialonSessionExpired(WialonClientError):
    def __init__(self) -> None:
        super().__init__(
            "Wialon session expired",
            status_message="Wialon: sessiya eskirdi; qayta avtorizatsiya kerak",
        )


@dataclass(frozen=True)
class WialonUnit:
    unit_id: str
    name: str
    last_message_at: datetime | None
    speed: Decimal | None
    mileage: Decimal | None


def _decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() and parsed >= 0 else None


def _message(item: dict[str, Any]) -> dict[str, Any]:
    value = item.get("lmsg")
    return value if isinstance(value, dict) else {}


def _last_message_at(item: dict[str, Any]) -> datetime | None:
    message = _message(item)
    position = message.get("pos")
    position = position if isinstance(position, dict) else {}
    raw = message.get("t") or message.get("tp") or position.get("t")
    try:
        timestamp = int(raw)
    except (TypeError, ValueError):
        return None
    if timestamp <= 0:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


def _speed(item: dict[str, Any]) -> Decimal | None:
    message = _message(item)
    position = message.get("pos")
    if not isinstance(position, dict):
        position = item.get("pos")
    if not isinstance(position, dict):
        return None
    return _decimal(position.get("s") if "s" in position else position.get("speed"))


def _find_counter_value(value: object, path: tuple[str, ...] = ()) -> Decimal | None:
    if not isinstance(value, dict):
        return None
    for key, entry in value.items():
        normalized_key = str(key).casefold().replace("-", "_").replace(" ", "_")
        if any(word in normalized_key for word in ("mileage", "odometer", "odometr", "probeg")):
            if isinstance(entry, dict):
                for value_key in ("act", "value", "val", "current", "v"):
                    parsed = _decimal(entry.get(value_key))
                    if parsed is not None:
                        return parsed
            parsed = _decimal(entry)
            if parsed is not None:
                return parsed
            nested = _find_counter_value(entry, (*path, normalized_key))
            if nested is not None:
                return nested
        elif isinstance(entry, dict):
            nested = _find_counter_value(entry, (*path, normalized_key))
            if nested is not None:
                return nested
    return None


def _mileage(item: dict[str, Any]) -> Decimal | None:
    for key in ("cnm", "mileage", "odometer", "odometr", "probeg"):
        parsed = _decimal(item.get(key))
        if parsed is not None:
            return parsed
    for key in ("counters", "cnm", "cml", "counter_values"):
        parsed = _find_counter_value(item.get(key))
        if parsed is not None:
            return parsed
    return None


def item_field_names(item: object, *, max_names: int = 250) -> list[str]:
    names: set[str] = set()

    def visit(value: object, prefix: str = "", depth: int = 0) -> None:
        if depth >= 8 or len(names) >= max_names:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                path = f"{prefix}.{key}" if prefix else str(key)
                names.add(path)
                visit(child, path, depth + 1)
                if len(names) >= max_names:
                    return
        elif isinstance(value, list):
            for child in value[:5]:
                visit(child, prefix, depth + 1)
                if len(names) >= max_names:
                    return

    visit(item)
    return sorted(names)


def diagnostic_counter(
    item: dict[str, Any], *, counter: str
) -> tuple[str | None, Decimal | None]:
    if counter == "mileage":
        keys = ("cnm", "mileage", "odometer", "odometr", "probeg")
        nested_keys = ("counters", "counter_values", "cml")
    elif counter == "engine_hours":
        keys = ("cneh", "engine_hours", "engineHours", "moto_hours", "motoHours")
        nested_keys = ("counters", "counter_values", "cml")
    else:
        raise ValueError("Unsupported Wialon counter")

    for key in keys:
        parsed = _decimal(item.get(key))
        if parsed is not None:
            return key, parsed

    def search(value: object, prefix: str = "") -> tuple[str | None, Decimal | None]:
        if not isinstance(value, dict):
            return None, None
        for key, entry in value.items():
            name = str(key)
            path = f"{prefix}.{name}" if prefix else name
            normalized = name.casefold().replace("-", "_").replace(" ", "_")
            if any(term in normalized for term in keys[1:]):
                if isinstance(entry, dict):
                    for value_key in ("act", "value", "val", "current", "v"):
                        parsed = _decimal(entry.get(value_key))
                        if parsed is not None:
                            return f"{path}.{value_key}", parsed
                parsed = _decimal(entry)
                if parsed is not None:
                    return path, parsed
            if isinstance(entry, dict):
                found_key, found_value = search(entry, path)
                if found_key is not None:
                    return found_key, found_value
        return None, None

    for key in nested_keys:
        field_name, value = search(item.get(key), key)
        if field_name is not None:
            return field_name, value
    return None, None


def parse_units(payload: object) -> list[WialonUnit]:
    if not isinstance(payload, dict):
        raise WialonClientError("Wialon returned an invalid unit list")
    items = payload.get("items")
    if not isinstance(items, list):
        raise WialonClientError("Wialon returned an invalid unit list")

    units: list[WialonUnit] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        unit_id = item.get("id")
        name = item.get("nm") or item.get("name")
        if unit_id is None or not isinstance(name, str) or not name.strip():
            continue
        units.append(
            WialonUnit(
                unit_id=str(unit_id),
                name=name.strip(),
                last_message_at=_last_message_at(item),
                speed=_speed(item),
                mileage=_mileage(item),
            )
        )
    return units


class WialonClient:
    def __init__(
        self,
        host: str,
        token: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self._host = host.rstrip("/")
        self._token = token
        self._transport = transport
        self._timeout_seconds = timeout_seconds

    async def _request(
        self,
        client: httpx.AsyncClient,
        service: str,
        params: dict[str, Any],
        *,
        session_id: str | None = None,
    ) -> Any:
        for attempt in range(MAX_ATTEMPTS):
            try:
                response = await client.post(
                    API_PATH,
                    params={"sid": session_id} if session_id is not None else None,
                    data={"svc": service, "params": json.dumps(params, separators=(",", ":"))},
                )
                response.raise_for_status()
                payload = response.json()
                error = _error_message(service, payload)
                if error is not None:
                    raise error
                return payload
            except WialonSessionExpired:
                raise
            except WialonClientError:
                raise
            except httpx.TimeoutException:
                if attempt + 1 >= MAX_ATTEMPTS:
                    raise WialonClientError(
                        "Wialon request timed out",
                        status_message="Wialon: javob kutish vaqti tugadi (timeout)",
                    ) from None
            except (httpx.NetworkError, httpx.RemoteProtocolError):
                if attempt + 1 >= MAX_ATTEMPTS:
                    raise WialonClientError(
                        "Wialon network request failed",
                        status_message="Wialon: tarmoq xatosi; ulanishni tekshiring",
                    ) from None
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code < 500 or attempt + 1 >= MAX_ATTEMPTS:
                    raise WialonClientError(
                        f"Wialon server returned HTTP {exc.response.status_code}",
                        status_message=(
                            f"Wialon: server HTTP {exc.response.status_code} qaytardi"
                        ),
                    ) from None
            except (ValueError, json.JSONDecodeError):
                raise WialonClientError(
                    "Wialon returned an invalid response",
                    status_message="Wialon: server javobi noto‘g‘ri formatda",
                ) from None
            await asyncio.sleep(0.2 * (2**attempt))
        raise WialonClientError("Wialon request failed after retries")

    async def _login(self, client: httpx.AsyncClient) -> str:
        response = await self._request(client, "token/login", {"token": self._token})
        eid = response.get("eid") if isinstance(response, dict) else None
        if not isinstance(eid, str) or not eid:
            raise WialonClientError(
                "Wialon authentication response was invalid",
                status_message="Wialon: avtorizatsiya javobi noto‘g‘ri",
            )
        return eid

    async def _search_items(
        self,
        client: httpx.AsyncClient,
        session_id: str,
    ) -> list[dict[str, Any]]:
        response = await self._request(
            client,
            "core/search_items",
            {
                "spec": {
                    "itemsType": "avl_unit",
                    "propName": "sys_name",
                    "propValueMask": "*",
                    "sortType": "sys_name",
                    "propType": "property",
                },
                "force": 1,
                "flags": SEARCH_FLAGS,
                "from": 0,
                "to": 0,
            },
            session_id=session_id,
        )
        if not isinstance(response, dict) or not isinstance(response.get("items"), list):
            raise WialonClientError(
                "Wialon returned an invalid unit list",
                status_message="Wialon: birliklar ro‘yxati noto‘g‘ri formatda",
            )
        return [item for item in response["items"] if isinstance(item, dict)]

    async def _fetch_items(self, *, retry_expired_session: bool) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(
            base_url=self._host,
            timeout=httpx.Timeout(self._timeout_seconds),
            transport=self._transport,
        ) as client:
            eid = await self._login(client)
            try:
                attempts = 2 if retry_expired_session else 1
                for session_attempt in range(attempts):
                    try:
                        return await self._search_items(client, eid)
                    except WialonSessionExpired:
                        if not retry_expired_session or session_attempt:
                            raise WialonClientError(
                                "Wialon session expired after re-login",
                                status_message=(
                                    "Wialon: sessiya eskirdi; qayta avtorizatsiya kerak"
                                ),
                            )
                        eid = await self._login(client)
                raise WialonClientError(
                    "Wialon session expired",
                    status_message="Wialon: sessiya eskirdi; qayta avtorizatsiya kerak",
                )
            finally:
                try:
                    await self._request(
                        client,
                        "core/logout",
                        {},
                        session_id=eid,
                    )
                except WialonClientError:
                    logger.warning("Wialon logout failed")

    async def fetch_units(self) -> list[WialonUnit]:
        return parse_units({"items": await self._fetch_items(retry_expired_session=True)})

    async def fetch_diagnostic_items(self) -> list[dict[str, Any]]:
        return await self._fetch_items(retry_expired_session=False)


def _error_message(service: str, payload: object) -> WialonClientError | None:
    if isinstance(payload, dict):
        code = payload.get("error")
        reason = payload.get("reason")
    elif isinstance(payload, int):
        code = payload
        reason = None
    else:
        return None

    if code in (None, False, 0, "0"):
        return None

    if service != "token/login" and str(code) == str(SESSION_EXPIRED_CODE):
        return WialonSessionExpired()
    if service == "token/login" and str(code) in {"4", "8"}:
        return WialonClientError(
            f"Wialon token login rejected (code {code})",
            status_message=(
                "Wialon: token yo‘q yoki noto‘g‘ri; token sozlamasini tekshiring"
            ),
        )
    if str(code) == "7" and reason == "ACCESS_DENIED_BY_HOST_MASK":
        return WialonClientError(
            "Wialon access denied by host mask",
            status_message=(
                "Wialon: host mask rad etdi; administratorga murojaat qiling"
            ),
        )
    if str(code) == "7":
        return WialonClientError(
            "Wialon access denied",
            status_message="Wialon: ruxsat rad etildi (xato 7)",
        )
    return WialonClientError(
        f"Wialon request rejected (code {code})",
        status_message=f"Wialon: so‘rov rad etildi (xato {code})",
    )
