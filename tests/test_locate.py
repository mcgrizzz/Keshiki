import pytest

from keshiki.locate import approximate_location


def test_first_service_answers():
    def get(url):
        assert "ipapi.co" in url
        return {"latitude": 40.5712, "longitude": -74.6099, "city": "Somerville", "region": "New Jersey",
                "country_name": "United States"}
    assert approximate_location(get) == {"latitude": 40.57, "longitude": -74.61,
                                         "place": "Somerville, New Jersey, United States"}


def test_falls_back_when_the_first_refuses():
    def get(url):
        if "ipapi.co" in url:
            return {"error": True, "reason": "RateLimited"}
        return {"success": True, "latitude": 35.6895, "longitude": 139.6917, "city": "Tokyo", "country": "Japan"}
    assert approximate_location(get) == {"latitude": 35.69, "longitude": 139.69, "place": "Tokyo, Japan"}


def test_says_why_when_nothing_answers():
    def get(url):
        raise OSError("offline")
    with pytest.raises(OSError, match="offline"):
        approximate_location(get)
