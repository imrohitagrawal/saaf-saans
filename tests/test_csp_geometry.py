"""Geometry has to survive the Content-Security-Policy that ships with it.

`main.py` sends `style-src 'self'` with no `'unsafe-inline'`, and CSP Level 3
makes `style-src` the fallback for `style-src-attr`, so the browser refuses to
PARSE a `style` attribute at all. Measured in Chrome 151 against the running
app, with the caret's own markup intact:

    .scale-mark getAttribute('style') -> "left:65.0%"
    .scale-mark style.cssText         -> ""
    getComputedStyle(.scale-mark).left -> "0px"

A reading of 325 therefore painted its "325 v" caret at the extreme left of a
0-500 bar, over the "0 good" end -- the position half of the Never-Colour-Alone
rule present in the HTML and absent on screen.

Neither existing test could see it: `test_presenters` asserts
`scale_position()` returns 65.0, and `test_web` asserts the header contains
`style-src 'self'`. Both were green while the number never reached a pixel. So
these assertions run the whole chain the pixel actually depends on -- rendered
class, stylesheet step, declared property -- and never the presenter alone.
"""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from saafsaans.web import presenters as pr
from saafsaans.web.main import app

CSS_PATH = Path(__file__).resolve().parents[1] / "saafsaans/web/static/app.css"
TEMPLATES = Path(__file__).resolve().parents[1] / "saafsaans/web/templates"

# One percent of the widest bar the shell allows is about 3px; a caret placed
# by a rounded step lands within half of that.
STEP_TOLERANCE = 0.5


def _css():
    return re.sub(r"/\*.*?\*/", "", CSS_PATH.read_text(), flags=re.S)


def _steps():
    """{class name: percentage} for every geometry step app.css defines."""
    return {f"p{m.group(1)}": float(m.group(2)) for m in
            re.finditer(r"\.p(\d+)\s*\{\s*--p:\s*([\d.]+)%\s*;?\s*\}", _css())}


def _declares(selector, prop):
    """The value `selector` gives `prop` at the top level, or None."""
    for block in re.finditer(r"([^{}@]+)\{([^{}]*)\}", _css()):
        if selector not in [s.strip() for s in block.group(1).split(",")]:
            continue
        for part in block.group(2).split(";"):
            if ":" in part and part.split(":", 1)[0].strip() == prop:
                return part.split(":", 1)[1].strip()
    return None


@pytest.fixture(scope="module")
def today_page():
    from saafsaans.services import waqi
    from tests.conftest import LIVE_READING

    real = waqi.get_aqi
    waqi.get_aqi = lambda loc, es_client=None: ({**LIVE_READING, "station": loc}, "ok")
    try:
        with TestClient(app) as client:
            return client.get("/", params={"locality": "Anand Vihar", "age": "Adult",
                                           "condition": "Asthma",
                                           "activity": "Outdoor exercise"}).text
    finally:
        waqi.get_aqi = real


def test_no_template_writes_a_style_attribute():
    """Under this policy a style attribute is not weak styling, it is no
    styling: the declaration is discarded before the cascade ever sees it. The
    set is exact and empty so it bites on the next one written, anywhere."""
    found = set()
    for path in sorted(TEMPLATES.glob("*.html")):
        for match in re.finditer(r'\sstyle="([^"]*)"', path.read_text()):
            found.add((path.name, match.group(1)))
    assert found == set(), (
        "a style attribute in a template; style-src 'self' means the browser "
        f"never parses it:\n  {sorted(found)}")


def test_the_geometry_the_style_attributes_carried_is_still_expressed():
    """Partner to the empty set above: deleting the attributes rather than
    replacing them would pass that assertion and leave every bar at zero."""
    steps = _steps()
    assert len(steps) >= 101, f"app.css defines only {len(steps)} geometry steps"
    assert steps["p0"] == 0.0 and steps["p100"] == 100.0, (steps.get("p0"), steps.get("p100"))
    for selector, prop in ((".scale-mark", "left"), (".fill", "width"), (".col .b", "height")):
        value = _declares(selector, prop)
        assert value and value.startswith("var(--p"), (
            f"{selector} no longer takes its {prop} from the step class", value)


def test_the_blocked_day_bars_stay_proportional_to_each_other():
    """A percentage height needs a definite box to be a percentage OF. In the
    flex column `.col` used to be, the bar resolved 100% against the full 74px
    and was then shrunk to fit around the count above it and the day label
    below: measured in Chrome 151, 75% and 100% both drew 31.91px, so two
    different days were the same bar. The `1fr` track IS the bar area, which
    makes the step linear across it -- 0/3.19/7.97/15.95/23.92/31.91px for
    0/10/25/50/75/100%."""
    assert _declares(".col", "display") == "grid", (
        "the bar is back in a flex column, where its percentage is shrunk to fit")
    assert "1fr" in (_declares(".col", "grid-template-rows") or ""), (
        "no flexible track for the bar to be a percentage of")
    assert _declares(".col .b", "align-self") == "end", (
        "the bar grows from the top of its track instead of standing on the axis")


def test_the_caret_lands_where_scale_position_says(today_page):
    """The chain the pixel depends on, end to end: the class the template
    rendered, the percentage app.css binds to it, and the property that reads
    it. Every CPCB boundary is probed, because that is where a rounding step
    first puts the caret in a neighbouring band."""
    steps = _steps()
    marker = re.search(r'<div class="scale-mark ([^"]+)"', today_page)
    assert marker, "the caret is not rendered, so this proved nothing"

    from tests.conftest import LIVE_READING
    rendered = marker.group(1).strip()
    assert rendered in steps, (rendered, "is not a step app.css defines")
    assert abs(steps[rendered] - pr.scale_position(LIVE_READING["aqi"])) <= STEP_TOLERANCE

    drift = []
    for aqi in (0, 25, 49, 50, 51, 75, 99, 100, 101, 150, 168, 199, 200,
                201, 250, 299, 300, 301, 325, 350, 399, 400, 401, 450, 499, 500):
        wanted = pr.scale_position(aqi)
        placed = steps.get(pr.pos_class(wanted))
        if placed is None or abs(placed - wanted) > STEP_TOLERANCE:
            drift.append(f"AQI {aqi}: scale_position {wanted}%, caret placed at {placed}")
    assert not drift, "the caret does not track the reading:\n  " + "\n  ".join(drift)


def test_every_bar_on_the_site_is_placed_from_a_percentage_string():
    """`scale_pos` is the only float `pos` is ever handed. Every bar -- the
    Today outlook, both System bar charts, the seven day columns -- is handed
    `pct`'s "45.5%" instead, so the string branch IS the bar path, and it was
    the branch nothing asserted. Narrowing the parse to `float(percent)` sends
    all four surfaces to the `except` and draws them at zero width with the
    rest of the suite green."""
    assert pr.pos_class(pr.pct(110, 220)) == "p50"
    assert pr.pos_class(pr.pct(150, 220)) == "p68"
    assert pr.pos_class(pr.pct(0, 220)) == "p0"
    assert pr.pos_class(pr.pct(400, 220)) == "p100"      # clamped by pct
    assert pr.pos_class("45.5%") == "p46"
    assert pr.pos_class("100.0%") == "p100"
    # The fallback stays a fallback: only what cannot be read at all is p0.
    assert pr.pos_class(None) == "p0" and pr.pos_class("--") == "p0"


def _fills(body):
    """Every `.fill` bar in a rendered page, as its step class."""
    return [m.group(1) for m in
            re.finditer(r'class="fill(?: fill-accent)? (p\d+)"', body)]


def test_the_outlook_fills_land_where_their_printed_averages_say(monkeypatch):
    """The caret above proves one float; this proves the string path reaches a
    pixel too. The bar is read against the µg/m3 number printed in its own row,
    not against the AQI sub-index fed in -- the WAQI forecast carries
    sub-indices and `forecast.pm25_rows` inverts them, so comparing to the
    input would assert the wrong scale. Deleting `{{ pos(pct(row.avg, 220)) }}`
    from today.html leaves the rest of the suite green and draws every outlook
    bar at zero."""
    from datetime import timedelta

    from saafsaans.services import clock, waqi
    from tests.conftest import LIVE_READING

    # Sub-indices spread across the CPCB breakpoints so no two rows invert to
    # the same concentration, and the last clears the 220 ceiling.
    feed = [40, 110, 190, 260, 400]
    days = [clock.today_ist() + timedelta(days=n) for n in range(len(feed))]
    forecast = {"daily": {"pm25": [{"day": d.isoformat(), "avg": a, "min": 5, "max": a}
                                   for d, a in zip(days, feed)]}}
    monkeypatch.setattr(waqi, "get_aqi", lambda loc, es_client=None:
                        ({**LIVE_READING, "forecast": forecast, "station": loc}, "ok"))
    with TestClient(app) as client:
        body = client.get("/", params={"locality": "Anand Vihar", "age": "Adult",
                                       "condition": "Asthma",
                                       "activity": "Outdoor exercise"}).text

    assert 'aria-label="Five-day outlook"' in body, "no outlook rendered, so this proved nothing"
    rows = re.findall(r'<span class="v">(\d+)</span>\s*'
                      r'<span class="track"><span class="fill (p\d+)"></span>', body)
    assert len(rows) == len(feed), (rows, "one printed average and one fill per day")

    steps = _steps()
    for shown, cls in rows:
        wanted = float(pr.pct(int(shown), 220).rstrip("%"))
        assert cls in steps, (cls, "is not a step app.css defines")
        assert abs(steps[cls] - wanted) <= STEP_TOLERANCE, (shown, cls, steps[cls], wanted)
    # A zeroed path would print five different numbers over five identical
    # bars, and the over-ceiling day must still be full rather than clipped.
    assert len({cls for _, cls in rows}) == len(feed), rows
    assert rows[-1][1] == "p100", rows[-1]


def test_the_system_bars_and_day_columns_carry_their_own_geometry(monkeypatch):
    """Both bar charts and the security columns, from seeded telemetry rather
    than a live index. Removing `{{ pos(r.w) }}` or `{{ pos(d.h) }}` from
    system.html turns each of these red; nothing else in the suite renders
    these surfaces at all."""
    from saafsaans.services import metrics

    monkeypatch.setattr(metrics, "telemetry_kpis", lambda c: {
        "total": 40, "latency_p50": 900, "latency_p95": 2100,
        "waqi_fallback_rate": 0.1, "llm_fallback_rate": 0.2, "total_tokens": 5000,
        "by_event": {"chat_completed": 20, "page_view": 10, "chat_blocked": 5},
        "by_locality": [{"locality": "Anand Vihar", "count": 20},
                        {"locality": "Dwarka", "count": 5}]})
    with TestClient(app) as client:
        body = client.get("/system").text

    steps = _steps()
    # 20/10/5 of a 20 max, then 20/5 of a 20 max: events then localities.
    assert _fills(body) == ["p100", "p50", "p25", "p100", "p25"], _fills(body)

    counts = [4, 0, 2, 8, 1, 0, 3]
    monkeypatch.setattr(metrics, "security_stats", lambda c: {"block_rate": 0.5, "by_pattern": []})
    monkeypatch.setattr(metrics, "security_daily", lambda c, days=7: [
        {"date": f"2026-08-0{n + 1}", "count": n_} for n, n_ in enumerate(counts)])
    monkeypatch.setattr(metrics, "recent_security_events", lambda c, limit=40: [])
    with TestClient(app) as client:
        body = client.get("/system", params={"view": "security"}).text

    bars = [m.group(1) for m in re.finditer(r'class="b (p\d+|b-nil)"', body)]
    assert len(bars) == len(counts), (bars, "one column per day")
    for cls, n in zip(bars, counts):
        if not n:
            assert cls == "b-nil", (n, cls)   # a zero day is a rule, not a bar
            continue
        assert abs(steps[cls] - n / max(counts) * 100) <= STEP_TOLERANCE, (n, cls)
    assert len({b for b in bars if b != "b-nil"}) == 5, bars
