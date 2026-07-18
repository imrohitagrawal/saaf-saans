"""Search query shape + in-process fallback behaviour."""
from saafsaans.services import es


def test_query_shape_with_should():
    q = es.build_query(310, "asthma", "outdoor_exercise", "adult", k=4, with_should=True)
    assert q["size"] == 4
    filt = q["query"]["bool"]["filter"]
    assert {"range": {"aqi_min": {"lte": 310}}} in filt
    assert {"range": {"aqi_max": {"gte": 310}}} in filt
    terms = q["query"]["bool"]["should"]
    assert {"term": {"condition": "asthma"}} in terms
    assert {"term": {"activity": "outdoor_exercise"}} in terms
    assert {"term": {"age_group": "adult"}} in terms


def test_query_filter_only_retry():
    q = es.build_query(310, "asthma", "any", "any", k=4, with_should=False)
    assert "should" not in q["query"]["bool"]
    assert len(q["query"]["bool"]["filter"]) == 2


def test_in_process_search_returns_band():
    # AQI 310 with asthma should surface >= 2 advisories (spec acceptance check).
    docs = es.search_advisories(310, "asthma", "any", "any", client=None)
    assert len(docs) >= 2
    for d in docs:
        assert d["aqi_min"] <= 310 <= d["aqi_max"]


def test_in_process_search_never_empty():
    # An AQI with no exact band still returns nearest-band content.
    docs = es.search_advisories(10000, "any", "any", "any", client=None)
    assert len(docs) >= 1


def test_persona_boost_orders_matches_first():
    docs = es.search_advisories(250, "heart", "any", "any", client=None)
    assert any(d["condition"] == "heart" for d in docs)
    # the heart-specific advisory should rank ahead of generic ones
    assert docs[0]["condition"] == "heart"
