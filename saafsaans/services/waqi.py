"""Live AQI fetch from the WAQI feed API, with a demo-safe fallback.

``get_aqi`` never raises and (in practice) always returns a reading: on any
failure — no token, station 404, timeout, bad JSON, non-numeric AQI — it
returns a clearly-labelled cached sample so the demo cannot die. The WAQI
status ("ok" / "fallback") is returned *separately* from the reading so it is
never written into the aqi-readings index.
"""
import requests

from . import config, es

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
SAMPLES = {
    "Anand Vihar": {"aqi": 410, "pm25": 380.0, "pm10": 520.0},
    "ITO": {"aqi": 320, "pm25": 250.0, "pm10": 410.0, "dom": "no2"},
    "Rohini": {"aqi": 180, "pm25": 110.0, "pm10": 210.0},
    "RK Puram": {"aqi": 260, "pm25": 190.0, "pm10": 330.0},
    "Punjabi Bagh": {"aqi": 300, "pm25": 220.0, "pm10": 360.0},
    "Mandir Marg": {"aqi": 220, "pm25": 150.0, "pm10": 260.0},
    "Dwarka": {"aqi": 240, "pm25": 175.0, "pm10": 300.0},
    "Najafgarh": {"aqi": 200, "pm25": 130.0, "pm10": 240.0},
    "Wazirpur": {"aqi": 360, "pm25": 300.0, "pm10": 460.0},
    "Jahangirpuri": {"aqi": 390, "pm25": 350.0, "pm10": 500.0},
    "Okhla": {"aqi": 270, "pm25": 200.0, "pm10": 340.0},
    "Ashok Vihar": {"aqi": 330, "pm25": 260.0, "pm10": 420.0},
    "Nehru Nagar": {"aqi": 340, "pm25": 270.0, "pm10": 430.0},
    "Patparganj": {"aqi": 250, "pm25": 185.0, "pm10": 320.0},
    "DTU": {"aqi": 210, "pm25": 140.0, "pm10": 250.0},
    "Delhi (city)": {"aqi": 287, "pm25": 210.0, "pm10": 320.0},
    "Noida": {"aqi": 230, "pm25": 165.0, "pm10": 290.0, "dom": "no2"},
    "Greater Noida": {"aqi": 245, "pm25": 180.0, "pm10": 310.0},
    "Gurugram": {"aqi": 190, "pm25": 120.0, "pm10": 220.0, "dom": "o3"},
    "Ghaziabad": {"aqi": 300, "pm25": 230.0, "pm10": 380.0},
    "Faridabad": {"aqi": 260, "pm25": 195.0, "pm10": 335.0},
}
_DEFAULT_SAMPLE = SAMPLES["Delhi (city)"]


_API = "https://api.waqi.info/feed/{feed}/?token={token}"


def _fallback(locality: str = None):
    base = SAMPLES.get(locality, _DEFAULT_SAMPLE)
    return {
        "aqi": base["aqi"],
        "pm25": base["pm25"],
        "pm10": base["pm10"],
        "dominant_pollutant": base.get("dom", "pm25"),
        "station": f"{locality or 'Delhi'} (cached sample)",
        "city": "Delhi",
        "stale": True,
        "forecast": None,
        "obs_time": None,
    }


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
        aqi = int(aqi_raw)  # "-" or None from an offline station -> ValueError
    except (TypeError, ValueError):
        return None
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
    return {
        "aqi": aqi,
        "pm25": pollutant("pm25"),
        "pm10": pollutant("pm10"),
        "dominant_pollutant": data.get("dominentpol") or "pm25",
        "station": city,
        "city": city,
        "stale": False,
        "forecast": forecast,
        "obs_time": obs_time,
    }


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
