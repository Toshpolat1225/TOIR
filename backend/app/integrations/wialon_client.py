import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

logger = logging.getLogger(__name__)
API_PATH = "/wialon/ajax.html"
SEARCH_FLAGS = 1 | 0x800 | 0x1000
SESSION_EXPIRED_CODE = 1
MAX_ATTEMPTS = 3


class WialonClientError(Exception):
    pass


class WialonSessionExpired(WialonClientError):
    pass


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
    for key in ("mileage", "odometer", "odometr", "probeg"):
        parsed = _decimal(item.get(key))
        if parsed is not None:
            return parsed
    for key in ("counters", "cnm", "cml", "counter_values"):
        parsed = _find_counter_value(item.get(key))
        if parsed is not None:
            return parsed
    return None


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
                if isinstance(payload, dict) and "error" in payload:
                    code = payload["error"]
                    if code not in (None, False, 0, "0"):
                        if service != "token/login" and code == SESSION_EXPIRED_CODE:
                            raise WialonSessionExpired()
                        raise WialonClientError(
                            f"Wialon request was rejected (code {code})"
                        )
                if isinstance(payload, int) and payload != 0:
                    if service != "token/login" and payload == SESSION_EXPIRED_CODE:
                        raise WialonSessionExpired()
                    raise WialonClientError(
                        f"Wialon request was rejected (code {payload})"
                    )
                return payload
            except WialonSessionExpired:
                raise
            except WialonClientError:
                raise
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError):
                if attempt + 1 >= MAX_ATTEMPTS:
                    raise WialonClientError("Wialon request failed after retries") from None
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code < 500 or attempt + 1 >= MAX_ATTEMPTS:
                    raise WialonClientError(
                        f"Wialon server returned HTTP {exc.response.status_code}"
                    ) from None
            except (ValueError, json.JSONDecodeError):
                raise WialonClientError("Wialon returned an invalid response") from None
            await asyncio.sleep(0.2 * (2**attempt))
        raise WialonClientError("Wialon request failed after retries")

    async def _login(self, client: httpx.AsyncClient) -> str:
        response = await self._request(client, "token/login", {"token": self._token})
        eid = response.get("eid") if isinstance(response, dict) else None
        if not isinstance(eid, str) or not eid:
            raise WialonClientError("Wialon authentication response was invalid")
        return eid

    async def fetch_units(self) -> list[WialonUnit]:
        async with httpx.AsyncClient(
            base_url=self._host,
            timeout=httpx.Timeout(self._timeout_seconds),
            transport=self._transport,
        ) as client:
            eid = await self._login(client)
            try:
                for session_attempt in range(2):
                    try:
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
                            session_id=eid,
                        )
                        return parse_units(response)
                    except WialonSessionExpired:
                        if session_attempt:
                            raise WialonClientError("Wialon session expired after re-login")
                        eid = await self._login(client)
                raise WialonClientError("Wialon session expired")
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
