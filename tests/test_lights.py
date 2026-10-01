from keshiki.library import light_score


def test_a_warm_window_in_the_dark_is_a_light():
    assert light_score(0.95, 0.75, 0.4, local=0.15) > 0.8


def test_a_pale_moonlit_cloud_is_not():
    # Bright-ish and bluish, and about as bright as what's around it.
    assert light_score(0.55, 0.6, 0.75, local=0.5) < 0.05


def test_a_star_is_a_light_but_the_sky_around_it_is_not():
    assert light_score(0.7, 0.72, 0.78, local=0.12) > 0.5
    assert light_score(0.1, 0.12, 0.3, local=0.12) == 0
