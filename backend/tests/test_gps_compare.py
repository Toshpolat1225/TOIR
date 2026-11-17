"""Wialon-vs-GTK comparison rules. The numbers are real measurements from the live system (2026-11-16/17)."""
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from pydantic import SecretStr

from app.integrations import gtk_gps_client as gc
from app.services import gps_compare as cmp

UTC = timezone.utc
NOW = datetime(2026, 11, 17, 17, 40, tzinfo=UTC)


def fix(lat, lon, minutes_ago, speed=None):
    return cmp.SourceFix(lat, lon, NOW - timedelta(minutes=minutes_ago), speed)


# ---- positions ---------------------------------------------------------------------------------------------
def test_a_parked_unit_seen_by_both_is_confirmed():
    # live: 37077 -> 10 m apart, both fresh, both parked
    c = cmp.position_check(fix(40.8500, 69.5700, 2.3, 0), fix(40.85009, 69.5700, 0.7, 0), NOW)
    assert c.verdict == "confirmed" and c.diff_m < 15 and c.best == "gtk"  # the newer fix is drawn


def test_a_moving_unit_gets_a_tolerance_for_the_time_lag():
    # live: 37070 moved at ~17 km/h; fixes 108 s apart gave 646 m between them: that is NOT an error
    w = fix(40.8500, 69.5700, 2.6, 16)
    g = cmp.SourceFix(40.8500 + 646 / 111_195, 69.5700, NOW - timedelta(minutes=0.8), 17)
    c = cmp.position_check(w, g, NOW)
    assert c.verdict == "confirmed" and c.tolerance_m > 646


def test_the_same_distance_for_a_parked_unit_is_a_divergence():
    w, g = fix(40.8500, 69.5700, 1, 0), cmp.SourceFix(40.8500 + 646 / 111_195, 69.5700, NOW - timedelta(minutes=1), 0)
    assert cmp.position_check(w, g, NOW).verdict == "diverged"


def test_a_silent_gtk_tracker_is_reported_with_the_distance():
    # live: 37923 -> GTK last fix 6703 min ago, Wialon 2 min ago, 6 km apart
    c = cmp.position_check(fix(40.85, 69.57, 2.1, 0), fix(40.904, 69.57, 6703, 0), NOW)
    assert c.verdict == "gtk_stale" and c.best == "wialon" and 5000 < c.diff_m < 7000


def test_a_silent_wialon_unit_is_reported():
    assert cmp.position_check(fix(40.85, 69.57, 900, 0), fix(40.85, 69.57, 0.5, 0), NOW).verdict == "wialon_stale"


def test_two_silent_trackers_at_one_spot_agree_and_apart_do_not():
    # live: 37083 -> both silent for 230 days, 63 m apart
    assert cmp.position_check(fix(40.85, 69.57, 333550), fix(40.85 + 63 / 111_195, 69.57, 330243), NOW).verdict == "both_stale_agree"
    assert cmp.position_check(fix(40.85, 69.57, 333550), fix(40.86, 69.57, 330243), NOW).verdict == "both_stale_apart"


def test_one_source_only_and_nothing():
    assert cmp.position_check(fix(40.85, 69.57, 1), None, NOW).verdict == "wialon_only"
    assert cmp.position_check(None, fix(40.85, 69.57, 1), NOW).verdict == "gtk_only"
    assert cmp.position_check(cmp.SourceFix(0, 0, NOW), cmp.SourceFix(None, None), NOW).verdict == "no_position"


def test_a_fix_without_a_time_is_never_called_fresh():
    assert cmp.position_check(cmp.SourceFix(40.85, 69.57, None), fix(40.85, 69.57, 0.5), NOW).verdict == "wialon_stale"


def test_naive_datetimes_are_treated_as_utc():
    c = cmp.position_check(cmp.SourceFix(40.85, 69.57, datetime(2026, 11, 17, 17, 39)), fix(40.85, 69.57, 1), NOW)
    assert c.verdict == "confirmed"


# ---- distances ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "gtk_m,gtk_pts,wialon_m,wialon_pts,verdict",
    [
        (108886, 2388, 115412, 646, "match"),  # 37896 on 11-15: ratio 0.94
        (88078, 2468, 88030, 502, "match"),  # 38781 on 11-16: 1.00
        (84670, 1733, 120835, 684, "minor_diff"),  # 38911 on 11-15: 0.70
        (19013, 409, 123540, 703, "gtk_gap"),  # 38911 on 11-16: GTK stopped midway
        (0, 0, 106519, 620, "gtk_gap"),  # 37919 on 11-15: GTK has no points at all
        (10248, 204, 112631, 752, "gtk_gap"),
        (0, 0, 0, 0, "no_data"),
        (159, 17, 21497, 162, "gtk_gap"),
        (200, 3, 300, 5, "idle"),
        (90000, 2000, 400, 3, "wialon_gap"),
    ],
)
def test_daily_distance_verdicts_on_live_measurements(gtk_m, gtk_pts, wialon_m, wialon_pts, verdict):
    assert cmp.distance_check(gtk_m, gtk_pts, wialon_m, wialon_pts).verdict == verdict


def test_the_unified_distance_trusts_the_fuller_tracker():
    assert cmp.distance_check(100_000, 2000, 108_000, 600).unified_m == 104_000  # agree -> mean
    assert cmp.distance_check(0, 0, 106_519, 620).unified_m == 106_519  # GTK gap -> Wialon
    assert cmp.distance_check(84_670, 1733, 120_835, 684).unified_m == 120_835  # minor diff -> the larger
    assert cmp.distance_check(None, 0, None, 0).unified_m is None


def test_a_day_never_fetched_from_gtk_is_not_a_gtk_gap():
    c = cmp.distance_check(None, 0, 100_000, 600, gtk_collected=False)
    assert c.verdict == "not_collected" and c.unified_m == 100_000


def test_every_verdict_has_a_severity():
    import typing

    assert set(typing.get_args(cmp.PositionVerdict)) == set(cmp.POSITION_SEVERITY)
    assert set(typing.get_args(cmp.DistanceVerdict)) == set(cmp.DISTANCE_SEVERITY)


# ---- the GTK reader ----------------------------------------------------------------------------------------
def test_gtk_times_are_local_and_converted_to_utc():
    assert gc.parse_state_time("17.11.2026 22:38:14", 5) == datetime(2026, 11, 17, 17, 38, 14, tzinfo=UTC)
    assert gc.parse_state_time("17.11.2026 08:00", 5) == datetime(2026, 11, 17, 3, 0, tzinfo=UTC)
    assert gc.parse_state_time("17.11.2026 02:00", 5) == datetime(2026, 11, 16, 21, 0, tzinfo=UTC)  # across midnight
    assert gc.parse_state_time("garbage", 5) is None and gc.parse_state_time(None, 5) is None
    assert gc.parse_track_time("2026-11-16T00:00:05", 5) == datetime(2026, 11, 15, 19, 0, 5, tzinfo=UTC)


VEHICLES = [
    {"id": 1262, "enterprise_id": 1, "vehicle_type_id": 2, "state": [
        {"key": "lat", "value": 40.870841}, {"key": "lon", "value": 69.5}, {"key": "speed", "value": 13.5}, {"key": "time", "value": "17.11.2026 22:36:54"},
        {"key": "name", "value": "3204"}, {"key": "garage_number", "value": "3204"}, {"key": "model__name", "value": "Тепловзо ТЭМ18ДМ"}]},
    {"id": 7, "state": []},
    {"nonsense": True},
]
TRACK = {"track": [
    {"lat": 40.85, "lon": 69.57, "speed": 0, "height": 519, "time": "2026-11-02T02:13:59"},
    {"lat": 40.84, "lon": 69.56, "speed": 5, "height": 519, "time": "2026-11-02T02:10:00"},
    {"lat": None, "lon": 69.56, "time": "2026-11-02T02:11:00"},
], "distance": 27747, "events": {"noreasonidle": [{"a": 1}, {"a": 2}]}}


def test_parse_vehicles_and_track():
    units = gc.parse_vehicles(VEHICLES, 5)
    assert [u["gtk_id"] for u in units] == [1262, 7]
    assert units[0]["garage_number"] == "3204" and units[0]["position_at"] == datetime(2026, 11, 17, 17, 36, 54, tzinfo=UTC)
    assert units[1]["lat"] is None and units[1]["position_at"] is None
    track = gc.parse_track(TRACK, 5)
    assert track.distance_m == 27747 and len(track.points) == 2 and track.points[0].at < track.points[1].at  # sorted, the bad row dropped
    assert track.events == {"noreasonidle": 2}
    with pytest.raises(gc.GtkClientError):
        gc.parse_vehicles({"x": 1}, 5)


@pytest.mark.asyncio
async def test_the_client_logs_in_once_and_sends_the_ajax_header():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, request.headers.get("x-requested-with")))
        if request.url.path == "/" and request.method == "GET":
            return httpx.Response(200, text='<form><input name="csrfmiddlewaretoken" value="tok"><input type="password"></form>')
        if request.method == "POST":
            return httpx.Response(200, text="<html>welcome</html>")
        if request.url.path == "/core/core_vehicles_plugin/":
            return httpx.Response(200, json=VEHICLES)
        if request.url.path == "/core/core_tracks_plugin/":
            assert request.url.params["vehicle"] == "1262" and request.url.params["time_from"] == "2026-11-16 00:00:00"
            return httpx.Response(200, json=TRACK)
        return httpx.Response(404)

    async with gc.GtkGpsClient("https://gtk.test", "u", SecretStr("p"), transport=httpx.MockTransport(handler)) as client:
        assert len(await client.vehicles()) == 2
        track = await client.track(1262, datetime(2026, 11, 16), datetime(2026, 11, 16, 23, 59, 59))
        assert track.distance_m == 27747
    assert [m for m, *_ in seen].count("POST") == 1
    assert all(h == "XMLHttpRequest" for _, path, h in seen if path.startswith("/core/"))


@pytest.mark.asyncio
async def test_an_html_answer_means_the_session_is_gone():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/" and request.method == "GET":
            return httpx.Response(200, text='<input name="csrfmiddlewaretoken" value="t"><input type="password">')
        if request.method == "POST":
            return httpx.Response(200, text="ok")
        return httpx.Response(200, text="<html>login</html>", headers={"content-type": "text/html"})

    async with gc.GtkGpsClient("https://gtk.test", "u", SecretStr("p"), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(gc.GtkLoginError):
            await client.vehicles()


@pytest.mark.asyncio
async def test_a_failed_login_raises_and_never_leaks_the_password():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text='<input name="csrfmiddlewaretoken" value="t"><input type="password">')

    with pytest.raises(gc.GtkLoginError) as info:
        async with gc.GtkGpsClient("https://gtk.test", "u", SecretStr("topsecret"), transport=httpx.MockTransport(handler)):
            pass
    assert "topsecret" not in str(info.value)
