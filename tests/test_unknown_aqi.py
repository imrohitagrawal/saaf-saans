"""No reading is not clean air, and one page may hold only one verdict.

Every path that turns a missing AQI into guidance is pinned here, because the
belief that ``None`` means zero has now been written into this codebase twice --
once in ``risk.compute_risk`` (fixed, see ``risk.AQI_BASE_UNKNOWN``) and once on
the retrieval path (fixed here). The tests are gathered in one file so the next
person adding a code path that reads ``reading["aqi"]`` has a single place that
says what absence of a reading is allowed to produce.
"""
import pytest
from fastapi.testclient import TestClient

from saafsaans.data.advisories import ADVISORIES
from saafsaans.services import es, forecast, llm
from saafsaans.web.main import app

PERSONA = {"locality": "Anand Vihar", "age": "Senior",
           "condition": "COPD", "activity": "Outdoor exercise", "theme": "light"}

# The row a `None` AQI used to retrieve: the cleanest band in the corpus.
GOOD_ROW = ADVISORIES[0]
GOOD_TEXT = GOOD_ROW["advice"]


def _no_reading(locality, es_client=None):
    """A feed that carried an AQI but no usable particulate.

    Reachable in production: ``waqi._reading`` deliberately leaves ``aqi`` None
    when neither PM value can be inverted, while ``feed_aqi`` survives, so
    ``waqi.get_aqi`` does not reject the reading.
    """
    return ({"aqi": None, "aqi_beyond_scale": False, "pm25": None, "pm10": None,
             "dominant_pollutant": None, "feed_aqi": 412, "feed_dominant": "pm25",
             "station": locality, "city": "Delhi", "stale": False,
             "forecast": None, "obs_time": "2026-07-21T10:00:00+05:30"}, "ok")


@pytest.fixture
def unknown(monkeypatch):
    from saafsaans.services import waqi
    monkeypatch.setattr(waqi, "get_aqi", _no_reading)


# --- Retrieval -------------------------------------------------------------
def test_search_returns_nothing_for_an_unknown_aqi():
    """No band applies, because no band is known. Not the nearest band, and
    not the never-empty guarantee: that exists so a KNOWN reading always has
    guidance, not so an unknown one gets guidance invented for it."""
    assert es.search_advisories(None, "copd", "outdoor_exercise", "senior",
                                client=None) == []
    assert es.rank_advisories(ADVISORIES, None, "copd", "outdoor_exercise",
                              "senior", 4) == []


def test_no_persona_reaches_a_band_from_an_unknown_aqi():
    """The sweep: nothing in the reachable persona space may retrieve advice
    when there is no reading."""
    for condition in ("any", "asthma", "copd", "heart", "pregnancy"):
        for activity in ("any", "outdoor_exercise", "school_run", "commute",
                         "stay_home"):
            for age in ("any", "child", "adult", "senior"):
                got = es.search_advisories(None, condition, activity, age,
                                           client=None)
                assert got == [], (condition, activity, age)


def test_a_known_reading_still_always_gets_guidance():
    """The empty result is about the unknown case only."""
    for aqi in (0, 50, 150, 250, 350, 450, 999):
        assert es.search_advisories(aqi, "copd", "outdoor_exercise", "senior",
                                    client=None), aqi


# --- The answer the reader is handed ---------------------------------------
def test_rule_based_answer_never_quotes_the_good_band_without_a_reading():
    reading = _no_reading("Anand Vihar")[0]
    text = llm._rule_based(reading, [], question="Can I go for a run?")
    assert GOOD_TEXT not in text
    assert "data is limited right now" in text


def test_the_prompt_says_no_advisory_was_found():
    msg = llm.build_user_message(_no_reading("Anand Vihar")[0],
                                 {"age_group": "Senior", "condition": "COPD",
                                  "activity": "Outdoor exercise"},
                                 [], "Can I go for a run?", "Anand Vihar", "now")
    assert "(none found)" in msg
    assert GOOD_TEXT not in msg


def test_ask_with_no_reading_never_says_outdoor_activity_is_fine(unknown):
    """End-to-end: not in the model prompt, not in the stored sources, not on
    the page."""
    captured = {}
    real_answer = llm.answer

    def spy(reading, persona, advisories, question, **kw):
        captured["advisories"] = advisories
        captured["prompt"] = llm.build_user_message(
            reading, persona, advisories, question,
            kw.get("locality", ""), kw.get("timestamp", ""), kw.get("best_window"))
        return real_answer(reading, persona, advisories, question, **kw)

    from saafsaans.web import main as web_main
    web_main.llm.answer = spy
    try:
        with TestClient(app) as c:
            c.post("/ask", params=PERSONA, data={"question": "Can I go for a run?"})
            body = c.get("/", params={**PERSONA, "prov": "turn-0"}).text
    finally:
        web_main.llm.answer = real_answer

    assert captured["advisories"] == []
    assert "outdoor activity is fine" not in captured["prompt"]
    assert "outdoor activity is fine" not in body
    assert GOOD_ROW["source"] not in body


# --- The window ------------------------------------------------------------
def test_unknown_aqi_is_not_a_friendlier_window_than_severe_air():
    unknown_w = forecast.best_window(None, dominant_pollutant="pm25")
    severe = forecast.best_window(450, dominant_pollutant="pm25")
    assert unknown_w["window"] == severe["window"]
    assert "9 AM" not in unknown_w["window"]


def test_the_unknown_window_says_why_rather_than_naming_a_band():
    """It must not borrow the severe rationale, which asserts a reading."""
    out = forecast.best_window(None)
    assert "unavailable" in out["rationale"]
    assert "Very Poor/Severe range" not in out["rationale"]


# --- One page, one verdict -------------------------------------------------
def _fixed_aqi(value):
    def reading(locality, es_client=None):
        return ({"aqi": value, "aqi_beyond_scale": False, "pm25": 100.0,
                 "pm10": 180.0, "dominant_pollutant": "pm25", "feed_aqi": value,
                 "feed_dominant": "pm25", "station": locality, "city": "Delhi",
                 "stale": False, "forecast": None,
                 "obs_time": "2026-07-21T10:00:00+05:30"}, "ok")
    return reading


@pytest.mark.parametrize("persona, aqi", [
    ({"age": "Adult", "condition": "Asthma", "activity": "Outdoor exercise"}, 150),
    ({"age": "Senior", "condition": "COPD", "activity": "Outdoor exercise"}, 250),
])
def test_the_answer_card_verdict_agrees_with_the_hero(monkeypatch, persona, aqi):
    """The hero is persona-aware and the answer card was not, so at AQI 150 an
    asthma reader was told the air was "acceptable" underneath a hero telling
    them to skip outdoor exercise. Two verdicts, one page, opposite advice."""
    from saafsaans.services import risk, waqi
    monkeypatch.setattr(waqi, "get_aqi", _fixed_aqi(aqi))

    params = {**PERSONA, **persona}
    with TestClient(app) as c:
        c.post("/ask", params=params, data={"question": "Should I go for a walk?"})
        body = c.get("/", params=params).text

    band = risk.compute_risk(aqi, {"Asthma": "asthma", "COPD": "copd"}[persona["condition"]],
                             "outdoor_exercise",
                             persona["age"].lower())["band"]
    assert band in ("High", "Very High", "Extreme")
    # The hero's own "what to do" line, now quoted by the card as well.
    assert body.count(risk.BAND_ADVICE[band]) >= 2
    assert "is acceptable" not in body
    assert "is reasonable" not in body
