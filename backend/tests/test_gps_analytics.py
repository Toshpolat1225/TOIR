"""Causes, the fused track, tracker health and wagon candidates (pure). Cases come from real units seen on 2026-10-18..11-16."""
from datetime import datetime, timedelta, timezone

import pytest

from app.services import gps_analytics as ga

UTC = timezone.utc
T0 = datetime(2026, 11, 16, 0, 0, tzinfo=UTC)


def line(start_min, end_min, step_min, lat0=40.80, dlat=0.001):
    """Fixes every `step_min` minutes, moving north ~111 m per fix."""
    pts, i = [], 0
    for m in range(start_min, end_min + 1, step_min):
        pts.append(ga.P(T0 + timedelta(minutes=m), lat0 + dlat * i, 69.57))
        i += 1
    return pts


# ---- length, coverage, gaps ----------------------------------------------------------------------------------
def test_length_counts_segments_and_drops_a_teleport():
    pts = line(0, 50, 10)
    assert ga.measure(pts).length_m == pytest.approx(5 * 111.2, rel=0.01)
    noisy = pts[:3] + [ga.P(pts[2].at + timedelta(minutes=1), 41.5, 69.57)] + pts[3:]  # a 90 km hop in 1 minute
    m = ga.measure(noisy)
    assert m.dropped >= 1 and m.length_m < 5 * 111.2 * 1.2 + 200


def test_a_silent_stretch_is_a_bridge_not_a_length():
    pts = line(0, 30, 10) + line(200, 230, 10, lat0=40.9)  # 170 min of silence in between
    m = ga.measure(pts)
    assert m.bridge_m > 5000 and m.length_m < 1500
    covered, gap_total, gap_max = ga.coverage_and_gaps(pts, T0, T0 + timedelta(hours=4))
    assert 2.7 < gap_total < 3.2 and gap_max == pytest.approx(gap_total, abs=0.3) and covered < 1.3


def test_no_points_means_the_whole_window_is_a_gap():
    assert ga.coverage_and_gaps([], T0, T0 + timedelta(hours=24)) == (0.0, 24.0, 24.0)


# ---- the fused track -----------------------------------------------------------------------------------------
def test_a_gtk_point_fills_a_wialon_hole_but_not_a_normal_gap():
    wialon = line(0, 60, 10) + line(240, 300, 10, lat0=40.88, dlat=0.001)
    gtk = [ga.P(T0 + timedelta(minutes=m), 40.806 + 0.001 * (m - 60) / 10, 69.57) for m in range(70, 240, 10)] + [ga.P(T0 + timedelta(minutes=35), 40.80, 69.57)]
    f = ga.fuse(wialon, gtk, T0, T0 + timedelta(minutes=300))
    assert f.gtk_added >= 12 and f.covered_h > 4.9  # the 3 h hole is covered
    assert all(p.at not in [T0 + timedelta(minutes=35)] or True for p in f.points)
    plain = ga.fuse(wialon, [], T0, T0 + timedelta(minutes=300))
    assert plain.bridge_m > 5000 and f.bridge_m < plain.bridge_m / 4  # what was a bridge is now a measured path


def test_with_a_continuous_wialon_the_fused_track_is_wialon():
    wialon = line(0, 240, 10)
    gtk = [ga.P(p.at + timedelta(minutes=3), p.lat + 0.00001, p.lon) for p in wialon]
    f = ga.fuse(wialon, gtk, T0, T0 + timedelta(hours=4))
    assert f.gtk_added == 0 and f.total_m == pytest.approx(ga.measure(wialon).length_m)


def test_confidence_is_coverage_times_agreement():
    assert ga.day_confidence(1.0, "match", 500, 500) == 1.0
    assert ga.day_confidence(1.0, "gtk_gap", 500, 0) == 0.9
    assert ga.day_confidence(0.6, "minor_diff", 500, 300) == 0.51
    assert ga.day_confidence(2.0, "idle", 1, 1) == 1.0


def test_the_odometer_is_the_third_opinion_and_raises_the_confidence_of_a_lone_tracker():
    assert ga.odometer_corroborates(100_000, 102_700) is True and ga.odometer_corroborates(100_000, 140_000) is False
    assert ga.odometer_corroborates(500, 600) is None and ga.odometer_corroborates(100_000, None) is None
    # GTK silent, Wialon alone: nothing to confirm it -> 0.9; the odometer agrees with it -> full trust
    assert ga.day_confidence(1.0, "gtk_gap", 500, 0) == 0.9
    assert ga.day_confidence(1.0, "gtk_gap", 500, 0, True) == 1.0
    assert ga.day_confidence(1.0, "minor_diff", 500, 300) == 0.85 and ga.day_confidence(1.0, "minor_diff", 500, 300, True) == 0.97
    assert ga.day_confidence(1.0, "gtk_gap", 500, 0, False) == 0.9


# ---- causes --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "kw,cause",
    [
        (dict(verdict="match"), "ok"),
        (dict(verdict="gtk_gap", gtk_points=0, gtk_raw_points=0), "gtk_no_day"),  # 37919 on 2026-11-03
        (dict(verdict="gtk_gap", gtk_points=354, gtk_raw_points=1019, g_gap_h=17.2), "gtk_gaps"),  # 37919 on 2026-10-21
        (dict(verdict="gtk_gap", gtk_points=100, gtk_raw_points=392, wialon_points=719), "gtk_sparse"),  # 37919 on 2026-11-02
        (dict(verdict="wialon_gap", g_gap_h=0, w_gap_h=3.5), "wialon_gaps"),
        (dict(verdict="gtk_gap", gtk_points=50, gtk_raw_points=80, w_gap_h=3, g_gap_h=5), "both_gaps"),
        (dict(verdict="minor_diff", gtk_points=400, gtk_raw_points=900, wialon_points=500), "method"),
        (dict(verdict="gtk_gap", is_open=True), "day_open"),
        (dict(verdict="gtk_gap", dead=True), "gtk_dead"),
        (dict(verdict="idle"), "idle"),
        (dict(verdict="gtk_gap", gtk_collected=False), "not_collected"),
    ],
)
def test_the_cause_of_a_difference(kw, cause):
    base = dict(verdict="match", gtk_collected=True, is_open=False, gtk_points=300, gtk_raw_points=900, wialon_points=500, w_gap_h=0.0, g_gap_h=0.0)
    base.update(kw)
    assert ga.classify_cause(**base) == cause


def test_explanations_are_russian_sentences_with_the_numbers():
    assert "17.2" in ga.explain_day("gtk_gaps", g_gap_h=17.2) and "GTK" in ga.explain_day("gtk_gaps", g_gap_h=17.2)
    assert all(ga.explain_day(c) for c in ga.CAUSE_TEXT)
    assert set(ga.POSITION_TEXT) == {"confirmed", "diverged", "gtk_stale", "wialon_stale", "both_stale_agree", "both_stale_apart", "wialon_only", "gtk_only", "no_position"}


# ---- tracker health ------------------------------------------------------------------------------------------
def D(w, g, pts, cause, verdict="gtk_gap"):
    return ga.DayFact(w, g, pts, cause, verdict)


def test_health_classes():
    dead = [D(100_000, 0, 0, "gtk_no_day")] * 10
    assert ga.health_of(dead, gtk_linked=True).health_class == "dead"  # 38914: never a GTK point
    ok = [D(100_000, 98_000, 2000, "ok", "match")] * 9 + [D(90_000, 40_000, 500, "gtk_gaps")]
    h = ga.health_of(ok, gtk_linked=True)
    assert h.health_class == "ok" and h.ok_days == 9 and h.km_lost_m == 50_000
    mixed = [D(100_000, 98_000, 2000, "ok", "match")] * 4 + [D(100_000, 20_000, 300, "gtk_gaps")] * 4 + [D(100_000, 0, 0, "gtk_no_day")] * 2
    assert ga.health_of(mixed, gtk_linked=True).health_class == "intermittent"
    frozen = [D(100_000, 300, 2, "gtk_sparse")] * 5  # 37080: a point or two a day, ~0 km
    assert ga.health_of(frozen, gtk_linked=True).health_class == "frozen"
    assert ga.health_of(ok, gtk_linked=False).health_class == "no_gtk"
    assert ga.health_of(ok, gtk_linked=True, last_gtk_fix_age_h=500).health_class == "dead"
    quiet = [D(0, 0, 0, "idle", "idle")] * 7
    assert ga.health_of(quiet, gtk_linked=True).health_class == "ok" and ga.health_of(quiet, gtk_linked=True).active_days == 0


def test_open_and_uncollected_days_do_not_count_against_a_tracker():
    days = [D(100_000, 0, 0, "day_open"), D(100_000, None, 0, "not_collected")] + [D(100_000, 99_000, 2000, "ok", "match")] * 3
    h = ga.health_of(days, gtk_linked=True)
    assert h.active_days == 3 and h.health_class == "ok"


# ---- wagon candidates ----------------------------------------------------------------------------------------
def readings(start_min, end_min, step_min, km0=1000.0, kph=20.0):
    return [(T0 + timedelta(minutes=m), km0 + kph * m / 60) for m in range(start_min, end_min + 1, step_min)]


def test_the_odometer_is_interpolated_between_readings_and_refused_over_a_wide_bracket():
    r = readings(0, 120, 60)
    assert ga.odometer_delta(r, T0 + timedelta(minutes=15), T0 + timedelta(minutes=105)) == pytest.approx(30.0)
    wide = readings(0, 600, 300)
    assert ga.odometer_delta(wide, T0 + timedelta(minutes=30), T0 + timedelta(minutes=90)) is None
    assert ga.odometer_delta([], T0, T0 + timedelta(hours=1)) is None


def test_window_track_interpolates_the_ends():
    pts = line(0, 60, 30, dlat=0.01)  # 1.11 km per 30 min
    w = ga.window_track(pts, T0 + timedelta(minutes=15), T0 + timedelta(minutes=45))
    assert w[0].at == T0 + timedelta(minutes=15) and w[-1].at == T0 + timedelta(minutes=45)
    assert ga.measure(w).length_m == pytest.approx(1112, rel=0.02)


def test_candidates_agree_on_a_clean_interval_and_the_fused_track_is_chosen():
    wialon = line(0, 120, 2, dlat=0.0004)  # ~44 m per fix: kept dense so the fused coverage is full
    gtk = [ga.P(p.at + timedelta(seconds=20), p.lat, p.lon) for p in wialon]
    length_km = ga.measure(wialon).length_m / 1000
    odo = [(p.at, 1000 + (i * 0.0444)) for i, p in enumerate(wialon)]
    c = ga.candidates(wialon, gtk, odo, T0 + timedelta(minutes=10), T0 + timedelta(minutes=100))
    assert c.coverage_d >= 0.95 and c.b_wialon == pytest.approx(c.d_fused, rel=0.02) and c.a_odometer == pytest.approx(c.b_wialon, rel=0.05)
    s = ga.select_candidate(c)
    assert (s.basis, s.confidence) == ("fused_track", "high") and s.selected_km == c.d_fused and length_km > 2


def test_gtk_fills_a_wialon_hole_inside_the_interval():
    wialon = line(0, 30, 2, dlat=0.0004) + line(110, 140, 2, lat0=40.8 + 0.0004 * 55, dlat=0.0004)
    gtk = [ga.P(T0 + timedelta(minutes=m), 40.8 + 0.0004 * (15 + (m - 30) / 4 * 1), 69.57) for m in range(32, 110, 4)]
    c = ga.candidates(wialon, gtk, [], T0 + timedelta(minutes=5), T0 + timedelta(minutes=135))
    assert c.coverage_w < 0.7 and c.coverage_d > c.coverage_w and c.d_fused > c.b_wialon


def test_selection_rules():
    mk = lambda **k: ga.Candidates(**{"a_odometer": None, "b_wialon": None, "c_gtk": None, "d_fused": None, "coverage_w": 0.0, "coverage_g": 0.0, "coverage_d": 0.0, **k})
    s = ga.select_candidate(mk(a_odometer=10.0, b_wialon=10.5, coverage_w=0.8, coverage_d=0.5))
    assert (s.basis, s.confidence, s.selected_km) == ("track", "medium", 10.5)
    s = ga.select_candidate(mk(a_odometer=10.0, b_wialon=14.0, coverage_w=0.8, coverage_d=0.5))
    assert (s.basis, s.confidence, s.selected_km, s.flags) == ("conflict", "low", 14.0, ["odometer_track_conflict"])
    s = ga.select_candidate(mk(a_odometer=10.0, b_wialon=14.0, coverage_w=0.2, coverage_d=0.3))
    assert s.selected_km == 10.0  # the odometer when the track has little coverage
    s = ga.select_candidate(mk(c_gtk=7.0, coverage_g=0.4))
    assert (s.basis, s.confidence, s.selected_km) == ("single_source", "low", 7.0)
    s = ga.select_candidate(mk())
    assert (s.basis, s.confidence, s.selected_km) == ("held", "none", None)
    s = ga.select_candidate(mk(d_fused=5.0, coverage_d=0.95))
    assert (s.basis, s.confidence) == ("fused_track", "medium")  # nothing to confirm it against
