"""WAQI fetch: live parse, 404->city retry, timeout/bad-data -> stale sample."""
import pytest

from saafsaans.services import aqi_scale, waqi, config


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
    # The sample's AQI is derived from its concentrations, never stored, so
    # the assertion has to derive it the same way rather than read it back.
    sample = waqi.SAMPLES["ITO"]
    assert reading["pm25"] == sample["pm25"]
    assert reading["aqi"] == aqi_scale.cpcb_aqi(sample["pm25"], sample["pm10"])[0]
    assert calls == []  # no network call attempted


def test_fallback_varies_by_locality(monkeypatch):
    monkeypatch.setattr(config, "waqi_token", lambda: "")
    aqis = {loc: waqi.get_aqi(loc)[0]["aqi"] for loc in waqi.SAMPLES}
    # These moved when the samples stopped carrying a hand-written AQI and
    # started deriving it from their own concentrations on the CPCB scale.
    # Anand Vihar's PM2.5 of 380 is past CPCB's last published breakpoint, so
    # it reports the floor of Severe rather than an invented interpolation.
    assert aqis["Anand Vihar"] == 401
    assert aqis["Rohini"] == 267
    assert len(set(aqis.values())) >= 4  # localities are visibly distinct
    # Unknown locality falls back to the Delhi default sample.
    assert waqi.get_aqi("Nowhere")[0]["aqi"] == waqi.get_aqi("Delhi (city)")[0]["aqi"] == 369


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
    # Gurugram's sample declares an ozone driver -> best-window can vary. Ozone
    # is not one of the two particulates the app's own index is built from, so
    # it belongs to feed_dominant; dominant_pollutant names whichever
    # particulate actually drove our number, and can only ever be pm25 or pm10.
    gurugram = waqi.get_aqi("Gurugram")[0]
    assert gurugram["feed_dominant"] == "o3"
    assert gurugram["dominant_pollutant"] in ("pm25", "pm10")
    assert waqi.get_aqi("Rohini")[0]["feed_dominant"] is None


def test_live_ok(monkeypatch):
    monkeypatch.setattr(config, "waqi_token", lambda: "tok")
    monkeypatch.setattr(waqi.requests, "get", lambda *a, **k: Resp(200, OK_PAYLOAD))
    reading, status = waqi.get_aqi("Anand Vihar")
    assert status == "ok"
    # The payload's iaqi values are US EPA sub-indices; the reading carries the
    # concentrations behind them and an index on India's scale.
    assert reading["feed_aqi"] == 312
    assert reading["pm25"] == 200.9
    assert reading["pm10"] == 504.0
    assert reading["aqi"] == 401
    assert reading["aqi_beyond_scale"] is True
    # PM10 at 504 µg/m3 is the worse of the two on the CPCB scale, so it is
    # what drove the index -- even though the feed named pm25 as its dominant.
    assert reading["dominant_pollutant"] == "pm10"
    assert reading["feed_dominant"] == "pm25"
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
    # No particulate means no index this app can honestly compute. Falling back
    # to the feed's own number would put a US EPA figure under Indian band
    # names, which is exactly the defect the conversion exists to remove.
    assert reading["aqi"] is None
    assert reading["feed_aqi"] == 150
    assert reading["feed_dominant"] == "o3"
