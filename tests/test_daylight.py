from keshiki.daylight import glow, grey_seen, light_at, matrix


def test_high_sun_is_close_to_plain_light():
    m = matrix(45)
    assert all(0.9 < m[i][i] < 1.1 for i in range(3))
    assert all(m[i][j] == 0 for i in range(3) for j in range(3) if i != j)


def test_low_sun_is_warm_and_twilight_is_blue():
    horizon, twilight = matrix(1), matrix(-6)
    assert horizon[0][0] > horizon[2][2]                      # more red than blue
    assert sum(twilight[2]) > sum(twilight[0])                # more blue than red


def test_night_is_dim_and_low_in_colour():
    night = light_at(-25)
    assert night["brightness"] == 0.25 and night["colour"] == 0.4
    day = light_at(30)
    assert (day["brightness"], day["colour"]) == (1.0, 1.0)
    assert matrix(-25)[0][1] != 0                             # colours mix: rods see them as one


def test_strength_zero_changes_nothing():
    assert matrix(-25, 0) == [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    assert grey_seen(45, 0) == "#999999"


def test_a_picture_that_already_shows_night_is_not_darkened_again():
    day_photo, night_photo = matrix(-25, 1, luma=0.5), matrix(-25, 1, luma=0.08)
    assert day_photo[1][1] < 0.3                      # a day scene at night: dim
    assert night_photo == [[1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]]   # white balance is neutral then too


def test_lights_are_kept_only_as_night_falls():
    assert glow(45) == 0 and glow(-25) == 1 and glow(-25, 0.5) == 0.5
    assert 0 < glow(-5) < 1
