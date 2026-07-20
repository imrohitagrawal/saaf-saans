"""Live AQI fetch from the WAQI feed API, with a demo-safe fallback.

``get_aqi`` never raises and (in practice) always returns a reading: on any
failure — no token, station 404, timeout, bad JSON, non-numeric AQI — it
returns a clearly-labelled cached sample so the demo cannot die. The WAQI
status ("ok" / "fallback") is returned *separately* from the reading so it is
never written into the aqi-readings index.
"""
import requests

from . import aqi_scale, config, es

TIMEOUT = 5

# UI locality -> WAQI feed slug. Named-station feeds use the ``delhi/<name>``
# path form (the ``@<id>`` form is for numeric station UIDs). If any station
# feed 404s, get_aqi retries the ``delhi`` city feed, so a wrong slug degrades
# gracefully rather than breaking the demo.
# WAQI feed slugs. Delhi stations use the ``delhi/<station>`` path form; NCR
# cities use their own city feed. Any feed that 404s falls back to the Delhi
# city feed, so a wrong slug degrades gracefully rather than breaking the demo.
FEED_MAP = {
    # --- Delhi stations ---
    "Anand Vihar": "delhi/anand-vihar",
    "ITO": "delhi/ito",
    "Rohini": "delhi/rohini",
    "RK Puram": "delhi/r.k.-puram",
    "Punjabi Bagh": "delhi/punjabi-bagh",
    "Mandir Marg": "delhi/mandir-marg",
    "Dwarka": "delhi/dwarka-sector-8",
    "Najafgarh": "delhi/najafgarh",
    "Wazirpur": "delhi/wazirpur",
    "Jahangirpuri": "delhi/jahangirpuri",
    "Okhla": "delhi/okhla-phase-2",
    "Ashok Vihar": "delhi/ashok-vihar",
    "Nehru Nagar": "delhi/nehru-nagar",
    "Patparganj": "delhi/patparganj",
    "DTU": "delhi/dtu",
    "Delhi (city)": "delhi",
    # --- NCR cities ---
    "Noida": "noida",
    "Greater Noida": "greater-noida",
    "Gurugram": "gurugram",
    "Ghaziabad": "ghaziabad",
    "Faridabad": "faridabad",
}
CITY_FEED = "delhi"

# Region grouping for the UI (picker + City Pulse grid subheaders). The last
# entry of each list is kept in the same order as FEED_MAP.
REGIONS = {
    "Delhi": ["Anand Vihar", "ITO", "Rohini", "RK Puram", "Punjabi Bagh",
              "Mandir Marg", "Dwarka", "Najafgarh", "Wazirpur", "Jahangirpuri",
              "Okhla", "Ashok Vihar", "Nehru Nagar", "Patparganj", "DTU",
              "Delhi (city)"],
    "NCR": ["Noida", "Greater Noida", "Gurugram", "Ghaziabad", "Faridabad"],
}
LOCALITIES = REGIONS["Delhi"] + REGIONS["NCR"]

# Labelled per-locality fallback samples used whenever live data is unavailable
# (no token, or a failed fetch). Distinct values per locality so the UI visibly
# reacts to the picker even in mock mode; a few carry a non-PM dominant
# pollutant so the best-time-window advice also varies. All are stale=True.
#
# These are CONCENTRATIONS in micrograms per cubic metre, and always were --
# pm10 exceeds pm25 in every row, which is what makes them physically coherent
# and is exactly what the live feed's sub-indices were not. The AQI is derived
# from them through the CPCB scale rather than stored, so a sample can never
# drift away from the scale it is supposed to sit on.
SAMPLES = {
    "Anand Vihar": {"pm25": 380.0, "pm10": 520.0},
    "ITO": {"pm25": 250.0, "pm10": 410.0, "dom": "no2"},
    "Rohini": {"pm25": 110.0, "pm10": 210.0},
    "RK Puram": {"pm25": 190.0, "pm10": 330.0},
    "Punjabi Bagh": {"pm25": 220.0, "pm10": 360.0},
    "Mandir Marg": {"pm25": 150.0, "pm10": 260.0},
    "Dwarka": {"pm25": 175.0, "pm10": 300.0},
    "Najafgarh": {"pm25": 130.0, "pm10": 240.0},
    "Wazirpur": {"pm25": 300.0, "pm10": 460.0},
    "Jahangirpuri": {"pm25": 350.0, "pm10": 500.0},
    "Okhla": {"pm25": 200.0, "pm10": 340.0},
    "Ashok Vihar": {"pm25": 260.0, "pm10": 420.0},
    "Nehru Nagar": {"pm25": 270.0, "pm10": 430.0},
    "Patparganj": {"pm25": 185.0, "pm10": 320.0},
    "DTU": {"pm25": 140.0, "pm10": 250.0},
    "Delhi (city)": {"pm25": 210.0, "pm10": 320.0},
    "Noida": {"pm25": 165.0, "pm10": 290.0, "dom": "no2"},
    "Greater Noida": {"pm25": 180.0, "pm10": 310.0},
    "Gurugram": {"pm25": 120.0, "pm10": 220.0, "dom": "o3"},
    "Ghaziabad": {"pm25": 230.0, "pm10": 380.0},
    "Faridabad": {"pm25": 195.0, "pm10": 335.0},
}
_DEFAULT_SAMPLE = SAMPLES["Delhi (city)"]


_API = "https://api.waqi.info/feed/{feed}/?token={token}"


def _reading(pm25, pm10, *, station, city, stale, forecast, obs_time,
             feed_aqi=None, feed_dominant=None):
    """Assemble the reading contract from two particulate concentrations.

    One constructor for both the live and the fallback path, so the two cannot
    describe the same fields differently -- which is how the previous version
    ended up with hand-written sample AQIs that no longer matched the scale
    they were supposedly on.

    ``aqi`` is deliberately ``None`` when neither particulate is usable. The
    obvious alternative -- falling back to ``feed_aqi`` -- would put a US EPA
    number under Indian band names, which is the defect this whole change
    exists to remove.
    """
    scored = aqi_scale.cpcb_aqi(pm25, pm10)
    aqi, dominant, beyond = scored if scored else (None, None, False)
    return {
        "aqi": aqi,
        "aqi_beyond_scale": beyond,
        "pm25": pm25,
        "pm10": pm10,
        "dominant_pollutant": dominant,
        # WAQI's own number, on its own scale, kept for the provenance panel so
        # a sceptical reader can see both figures and that they differ.
        "feed_aqi": feed_aqi,
        "feed_dominant": feed_dominant,
        "station": station,
        "city": city,
        "stale": stale,
        "forecast": forecast,
        "obs_time": obs_time,
    }


def _fallback(locality: str = None):
    base = SAMPLES.get(locality, _DEFAULT_SAMPLE)
    return _reading(
        base["pm25"], base["pm10"],
        station=f"{locality or 'Delhi'} (cached sample)",
        city="Delhi", stale=True, forecast=None, obs_time=None,
        feed_dominant=base.get("dom"))


def _fetch_feed(feed: str, token: str):
    """GET one feed. Returns parsed reading dict or None (not usable)."""
    resp = requests.get(_API.format(feed=feed, token=token), timeout=TIMEOUT)
    if resp.status_code != 200:
        return None
    payload = resp.json()  # may raise ValueError -> handled by caller
    if payload.get("status") != "ok":
        return None
    data = payload.get("data") or {}
    aqi_raw = data.get("aqi")
    try:
        feed_aqi = int(aqi_raw)  # "-" or None from an offline station
    except (TypeError, ValueError):
        # An offline station used to make the whole reading unusable. It no
        # longer has to: the app computes its own index from the particulates,
        # so a feed that still carries pm25/pm10 is fine without a headline aqi.
        feed_aqi = None
    iaqi = data.get("iaqi") or {}

    def pollutant(name):
        node = iaqi.get(name)
        if isinstance(node, dict) and "v" in node:
            try:
                return float(node["v"])
            except (TypeError, ValueError):
                return None
        return None

    city = (data.get("city") or {}).get("name") or "Delhi"
    # Additive: WAQI also returns a multi-day pollutant forecast and an
    # observation timestamp. Captured here for the forecast module; both are
    # optional and default to None when absent so the reading shape is stable.
    forecast = data.get("forecast")
    if not isinstance(forecast, dict):
        forecast = None
    obs_time = (data.get("time") or {}).get("iso")

    # The feed's iaqi values are AQI sub-indices on the US EPA scale, not
    # concentrations -- see services/aqi_scale.py for the proof. Invert them
    # before anything downstream treats them as micrograms.
    reading = _reading(
        aqi_scale.concentration(pollutant("pm25"), "pm25"),
        aqi_scale.concentration(pollutant("pm10"), "pm10"),
        station=city, city=city, stale=False, forecast=forecast,
        obs_time=obs_time, feed_aqi=feed_aqi,
        feed_dominant=data.get("dominentpol"))
    # No usable particulate and no feed number either: nothing to show.
    if reading["aqi"] is None and feed_aqi is None:
        return None
    return reading


def get_aqi(locality: str, es_client=None):
    """Return ``(reading, status)`` where status is "ok" or "fallback".

    On a successful live fetch the reading is also indexed into aqi-readings
    when ``es_client`` is connected.
    """
    token = config.waqi_token()
    if not token:
        return _fallback(locality), "fallback"

    feed = FEED_MAP.get(locality, CITY_FEED)
    reading = None
    try:
        reading = _fetch_feed(feed, token)
        # Retry the Delhi city feed only for Delhi stations. NCR feeds must NOT
        # fall back to Delhi — that would mislabel a different city's air as a
        # live NCR reading; they degrade to the labelled stale sample instead.
        if reading is None and feed != CITY_FEED and feed.startswith("delhi"):
            reading = _fetch_feed(CITY_FEED, token)
    except Exception:
        reading = None

    if reading is None:
        return _fallback(locality), "fallback"

    try:
        # Index under the canonical UI locality label (not WAQI's verbose
        # city.name) so live readings share one key space with seed data and
        # the aqi_trend/station_grid filters match. Display keeps the real name.
        es.index_reading(es_client, {**reading, "station": locality})
    except Exception:
        pass  # indexing must never affect the returned reading
    return reading, "ok"


if __name__ == "__main__":
    r, status = get_aqi("Delhi (city)")
    print(f"[{status}] Delhi AQI = {r['aqi']} "
          f"(PM2.5={r['pm25']}, dominant={r['dominant_pollutant']}, stale={r['stale']})")
