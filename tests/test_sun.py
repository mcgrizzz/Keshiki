from datetime import date

from keshiki.sun import crossing, elevation_at, elevation_curve, sun_times, synthetic_curve


def hhmm(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def test_london_midsummer():
    # timeanddate.com: 04:43 / 21:21 BST
    rise, set_ = sun_times(date(2026, 6, 21), 51.5074, -0.1278, 60)
    assert abs(rise - (4 * 60 + 43)) <= 3 and abs(set_ - (21 * 60 + 21)) <= 3, (hhmm(rise), hhmm(set_))


def test_tokyo_winter():
    # timeanddate.com: 06:47 / 16:32 JST
    rise, set_ = sun_times(date(2026, 12, 21), 35.6762, 139.6503, 540)
    assert abs(rise - (6 * 60 + 47)) <= 3 and abs(set_ - (16 * 60 + 32)) <= 3, (hhmm(rise), hhmm(set_))


def test_polar_night_has_no_sunrise():
    assert sun_times(date(2026, 12, 21), 78.2, 15.6, 60) is None


def test_elevation_curve_matches_sunrise_and_noon():
    # Somerville, NJ, 1 Oct 2026 (EDT): the sun is highest at 12:48 (solar noon) at about 46.5°.
    day, lat, lon, offset = date(2026, 10, 1), 40.57, -74.61, -240
    curve = elevation_curve(day, lat, lon, offset)
    rise, set_ = sun_times(day, lat, lon, offset)
    assert abs(crossing(curve, -0.833, rising=True) - rise) <= 2
    assert abs(crossing(curve, -0.833, rising=False) - set_) <= 2
    assert 46 < max(curve) < 47 and abs(curve.index(max(curve)) - (12 * 60 + 48)) <= 2


def test_synthetic_curve_rises_and_sets_at_the_typed_times():
    curve = synthetic_curve(9 * 60, 21 * 60)
    assert abs(crossing(curve, -0.833, rising=True) - 9 * 60) <= 2
    assert abs(crossing(curve, -0.833, rising=False) - 21 * 60) <= 2
    assert abs(curve.index(max(curve)) - 15 * 60) <= 1 and elevation_at(curve, 3 * 60) < -18


def test_crossing_a_height_the_sun_never_reaches_lands_on_its_closest_point():
    curve = synthetic_curve(6 * 60, 18 * 60)
    assert crossing(curve, 89, rising=True) == curve.index(max(curve))
