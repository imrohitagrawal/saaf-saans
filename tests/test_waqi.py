"""WAQI fetch: live parse, 404->city retry, timeout/bad-data -> stale sample."""
import pytest

from saafsaans.services import waqi, config


class Resp:
    def __init__(self, status_code=200, payload=None, raise_json=False):
        self.status_code = status_code
        self._payload = payload or {}
        self._raise_json = raise_json

    def json(self):
        if self._raise_json:
            raise ValueError("no json")
        return self._payload


OK_PAYLOAD = {"status": "ok", "data": {
    "aqi": 312,
    "iaqi": {"pm25": {"v": 250.5}, "pm10": {"v": 400.0}},
    "dominentpol": "pm25",
    "city": {"name": "Anand Vihar, Delhi"},
}}


def test_no_token_returns_stale_no_http(monkeypatch):
    monkeypatch.setattr(config, "waqi_token", lambda: "")
    calls = []
    monkeypatch.setattr(waqi.requests, "get", lambda *a, **k: calls.append(1))
    reading, status = waqi.get_aqi("ITO")
    assert status == "fallback"
    assert reading["stale"] is True
    assert reading["aqi"] == waqi.SAMPLES["ITO"]["aqi"]  # per-locality sample
    assert calls == []  # no network call attempted


def test_fallback_varies_by_locality(monkeypatch):
    monkeypatch.setattr(config, "waqi_token", lambda: "")
    aqis = {loc: waqi.get_aqi(loc)[0]["aqi"] for loc in waqi.SAMPLES}
    assert aqis["Anand Vihar"] == 410
    assert aqis["Rohini"] == 180
    assert len(set(aqis.values())) >= 4  # localities are visibly distinct
    # Unknown locality falls back to the Delhi default sample.
    assert waqi.get_aqi("Nowhere")[0]["aqi"] == 287


def test_all_localities_have_feed_and_sample():
    # Every UI locality must resolve to both a feed and a mock sample.
    for loc in waqi.LOCALITIES:
        assert loc in waqi.FEED_MAP, f"{loc} missing feed"
        assert loc in waqi.SAMPLES, f"{loc} missing sample"
    # Regions partition LOCALITIES with no overlaps.
    assert set(waqi.LOCALITIES) == set(waqi.REGIONS["Delhi"]) | set(waqi.REGIONS["NCR"])
    assert len(waqi.LOCALITIES) >= 20


def test_fallback_carries_sample_dominant_pollutant(monkeypatch):
    monkeypatch.setattr(config, "waqi_token", lambda: "")
    # Gurugram's sample declares an ozone driver -> best-window can vary.
    assert waqi.get_aqi("Gurugram")[0]["dominant_pollutant"] == "o3"
    assert waqi.get_aqi("Rohini")[0]["dominant_pollutant"] == "pm25"


def test_live_ok(monkeypatch):
    monkeypatch.setattr(config, "waqi_token", lambda: "tok")
    monkeypatch.setattr(waqi.requests, "get", lambda *a, **k: Resp(200, OK_PAYLOAD))
    reading, status = waqi.get_aqi("Anand Vihar")
    assert status == "ok"
    assert reading["aqi"] == 312
    assert reading["pm25"] == 250.5
    assert reading["dominant_pollutant"] == "pm25"
    assert reading["stale"] is False


def test_station_404_then_city(monkeypatch):
    monkeypatch.setattr(config, "waqi_token", lambda: "tok")
    urls = []

    def fake_get(url, timeout):
        urls.append(url)
        if "anand-vihar" in url:
            return Resp(404)
        return Resp(200, OK_PAYLOAD)

    monkeypatch.setattr(waqi.requests, "get", fake_get)
    reading, status = waqi.get_aqi("Anand Vihar")
    assert status == "ok"
    assert len(urls) == 2
    assert "anand-vihar" in urls[0]
    assert "feed/delhi/?token" in urls[1]  # retried the city feed


def test_ncr_feed_failure_does_not_borrow_delhi(monkeypatch):
    monkeypatch.setattr(config, "waqi_token", lambda: "tok")
    urls = []

    def fake_get(url, timeout):
        urls.append(url)
        if "gurugram" in url:
            return Resp(404)          # NCR feed down
        return Resp(200, OK_PAYLOAD)  # Delhi city feed would succeed

    monkeypatch.setattr(waqi.requests, "get", fake_get)
    reading, status = waqi.get_aqi("Gurugram")
    # Must NOT fall back to the Delhi city feed for an NCR city.
    assert status == "fallback"
    assert reading["stale"] is True
    assert all("feed/delhi/?token" not in u for u in urls)


def test_timeout_returns_stale(monkeypatch):
    monkeypatch.setattr(config, "waqi_token", lambda: "tok")

    def boom(*a, **k):
        raise TimeoutError("timed out")

    monkeypatch.setattr(waqi.requests, "get", boom)
    reading, status = waqi.get_aqi("ITO")
    assert status == "fallback"
    assert reading["stale"] is True


def test_non_numeric_aqi_falls_back(monkeypatch):
    monkeypatch.setattr(config, "waqi_token", lambda: "tok")
    payload = {"status": "ok", "data": {"aqi": "-", "iaqi": {}, "city": {"name": "Delhi"}}}
    # station feed returns "-", city feed also "-" -> fallback
    monkeypatch.setattr(waqi.requests, "get", lambda *a, **k: Resp(200, payload))
    reading, status = waqi.get_aqi("ITO")
    assert status == "fallback"
    assert reading["stale"] is True


def test_missing_pm25_no_crash(monkeypatch):
    monkeypatch.setattr(config, "waqi_token", lambda: "tok")
    payload = {"status": "ok", "data": {"aqi": 150, "iaqi": {}, "dominentpol": "o3",
                                        "city": {"name": "Delhi"}}}
    monkeypatch.setattr(waqi.requests, "get", lambda *a, **k: Resp(200, payload))
    reading, status = waqi.get_aqi("Delhi (city)")
    assert status == "ok"
    assert reading["pm25"] is None
    assert reading["aqi"] == 150
