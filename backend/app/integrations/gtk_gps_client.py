"""GTK (gtk.agmk.uz) GPS: live unit positions and tracks. Read-only (GET only).

`GET /core/core_vehicles_plugin/?&action=get_vehicles` -> every unit with its last GPS state;
`GET /core/core_tracks_plugin/?action=get_track&time_from&time_to&vehicle&coordinates_filter` -> track points + `distance` (metres,
computed by GTK). Both need the `X-Requested-With: XMLHttpRequest` header (without it GTK answers with HTML) and a logged-in
session. GTK times are LOCAL (UTC+5 at AGMK); they are converted to UTC here and nowhere else.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import SecretStr

from app.integrations.gtk_client import CSRF, GtkClientError, GtkLoginError

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 90
_AJAX = {"X-Requested-With": "XMLHttpRequest"}
_STATE_TIME = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})[ T](\d{2}):(\d{2})(?::(\d{2}))?$")


@dataclass(frozen=True)
class GpsPoint:
    at: datetime  # UTC
    lat: float
    lon: float
    speed: float | None = None
    height: float | None = None


@dataclass(frozen=True)
class GtkTrack:
    points: list[GpsPoint]
    distance_m: int | None  # GTK's own figure for the requested window
    events: dict[str, int] = field(default_factory=dict)  # kind -> count (idle events etc.)


def _local_to_utc(naive: datetime, offset_hours: int) -> datetime:
    return (naive - timedelta(hours=offset_hours)).replace(tzinfo=timezone.utc)


def parse_state_time(value: Any, offset_hours: int) -> datetime | None:
    """«17.11.2026 22:38:14» / «17.11.2026 08:00» (local) -> UTC."""
    if not isinstance(value, str):
        return None
    match = _STATE_TIME.match(value.strip())
    if not match:
        return None
    d, mo, y, h, mi, s = match.groups()
    try:
        return _local_to_utc(datetime(int(y), int(mo), int(d), int(h), int(mi), int(s or 0)), offset_hours)
    except ValueError:
        return None


def parse_track_time(value: Any, offset_hours: int) -> datetime | None:
    """«2026-11-16T00:00:05» (local, naive ISO) -> UTC."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc)
    return _local_to_utc(parsed, offset_hours)


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def parse_vehicles(data: Any, offset_hours: int) -> list[dict[str, Any]]:
    """Normalise `get_vehicles`: one dict per unit (id, name, garage number, model, last GPS state with a UTC time)."""
    if not isinstance(data, list):
        raise GtkClientError("GTK vehicles response is not a list")
    units: list[dict[str, Any]] = []
    for row in data:
        if not isinstance(row, dict) or not isinstance(row.get("id"), int):
            continue
        state = {s.get("key"): s.get("value") for s in (row.get("state") or []) if isinstance(s, dict)}
        lat, lon = _float(state.get("lat")), _float(state.get("lon"))
        units.append(
            {
                "gtk_id": row["id"],
                "name": str(state.get("name") or "").strip() or None,
                "garage_number": str(state.get("garage_number") or "").strip() or None,
                "model_name": str(state.get("model__name") or "").strip() or None,
                "vehicle_type_id": row.get("vehicle_type_id") if isinstance(row.get("vehicle_type_id"), int) else None,
                "enterprise_id": row.get("enterprise_id") if isinstance(row.get("enterprise_id"), int) else None,
                "lat": lat,
                "lon": lon,
                "speed": _float(state.get("speed")),
                "course": _float(state.get("course")),
                "height": _float(state.get("height")),
                "position_at": parse_state_time(state.get("time"), offset_hours),
            }
        )
    return units


def parse_track(data: Any, offset_hours: int) -> GtkTrack:
    if not isinstance(data, dict):
        raise GtkClientError("GTK track response is not an object")
    points: list[GpsPoint] = []
    for row in data.get("track") or []:
        if not isinstance(row, dict):
            continue
        at, lat, lon = parse_track_time(row.get("time"), offset_hours), _float(row.get("lat")), _float(row.get("lon"))
        if at is None or lat is None or lon is None:
            continue
        points.append(GpsPoint(at, lat, lon, _float(row.get("speed")), _float(row.get("height"))))
    points.sort(key=lambda p: p.at)
    distance = data.get("distance")
    events = {k: len(v) for k, v in (data.get("events") or {}).items() if isinstance(v, list)}
    return GtkTrack(points, int(distance) if isinstance(distance, (int, float)) else None, events)


class GtkGpsClient:
    """One logged-in session; use as `async with GtkGpsClient(...) as gtk`."""

    def __init__(
        self,
        host: str | None,
        username: str | None,
        password: SecretStr | None,
        *,
        offset_hours: int = 5,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.host = host.rstrip("/") if host else None
        self.username = username.strip() if username else None
        self.password = password
        self.offset_hours = offset_hours
        self._transport = transport
        self._http: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "GtkGpsClient":
        if not self.host or not self.username or not self.password:
            raise GtkLoginError("GTK credentials or host are not configured")
        parts = urlsplit(self.host)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise GtkClientError("GTK host is invalid")
        self._http = httpx.AsyncClient(timeout=TIMEOUT_SECONDS, transport=self._transport)
        try:
            await self._login()
        except BaseException:
            await self._http.aclose()
            self._http = None
            raise
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def _login(self) -> None:
        assert self._http is not None and self.host and self.username and self.password
        try:
            page = await self._http.get(self.host + "/", follow_redirects=True)
            match = CSRF.search(page.text)
            if not match or "password" not in page.text.lower():
                raise GtkLoginError("GTK login form was not found")
            url = str(page.url)
            response = await self._http.post(
                url,
                data={"csrfmiddlewaretoken": match.group(1) or match.group(2), "username": self.username, "password": self.password.get_secret_value()},
                headers={"Referer": url},
                follow_redirects=True,
            )
        except httpx.TimeoutException as exc:
            raise GtkClientError("GTK request timed out") from exc
        except httpx.HTTPError as exc:
            raise GtkClientError("GTK network request failed") from exc
        if response.status_code >= 400 or re.search(r"""type=["']password["']""", response.text, re.I):
            raise GtkLoginError("GTK login failed")

    async def _get_json(self, path: str) -> Any:
        assert self._http is not None and self.host
        try:
            response = await self._http.get(self.host + path, headers=_AJAX)
        except httpx.TimeoutException as exc:
            raise GtkClientError("GTK request timed out") from exc
        except httpx.HTTPError as exc:
            raise GtkClientError("GTK network request failed") from exc
        if response.status_code in {401, 403}:
            raise GtkLoginError("GTK session is not authenticated")
        if response.status_code != 200:
            raise GtkClientError(f"GTK returned HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:  # HTML = the session expired / the header was dropped
            raise GtkLoginError("GTK returned a non-JSON answer (session expired?)") from exc

    async def vehicles(self) -> list[dict[str, Any]]:
        return parse_vehicles(await self._get_json("/core/core_vehicles_plugin/?&action=get_vehicles"), self.offset_hours)

    async def track(self, vehicle_id: int, local_from: datetime, local_to: datetime, *, coordinates_filter: bool = True) -> GtkTrack:
        """Track of one unit between two LOCAL (naive) times."""
        fmt = "%Y-%m-%d %H:%M:%S"
        path = (
            "/core/core_tracks_plugin/?action=get_track"
            f"&time_from={local_from.strftime(fmt).replace(' ', '%20')}&time_to={local_to.strftime(fmt).replace(' ', '%20')}"
            f"&vehicle={int(vehicle_id)}&coordinates_filter={'true' if coordinates_filter else 'false'}"
        )
        return parse_track(await self._get_json(path), self.offset_hours)
