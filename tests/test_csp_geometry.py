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
from tests.test_viewport_browser import browser, served  # noqa: F401 -- fixtures

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
    from saafsaans.services import metrics, viewport

    monkeypatch.setattr(metrics, "telemetry_kpis", lambda c: {
        "total": 40, "latency_p50": 900, "latency_p95": 2100,
        "waqi_fallback_rate": 0.1, "llm_fallback_rate": 0.2, "total_tokens": 5000,
        "by_event": {"chat_completed": 20, "page_view": 10, "chat_blocked": 5},
        "by_locality": [{"locality": "Anand Vihar", "count": 20},
                        {"locality": "Dwarka", "count": 5}]})
    # The viewport panel is a third `.fill` list on this page. Stubbed empty ON
    # PURPOSE: the list below is exact, and without this the test would pass
    # only because the default client happens to make that panel empty -- a
    # reason no reader of the assertion could see.
    monkeypatch.setattr(viewport, "bands", lambda: [])
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


def test_a_nonzero_day_never_draws_shorter_than_the_zero_baseline():
    """`.col .b` rounds a count's percentage of the day's max to a whole-percent
    step class (p0..p100). A count as small as 1 against a large day max rounds
    to p0, drawing `height:0%` -- shorter than `.b-nil`'s 2px zero baseline, so
    the day with SOME pollution drew a shorter bar than the day with none.
    `.col .b:not(.b-nil)` needs a floor above 2px so no real count can ever
    round to a bar this short; `.b-nil` itself must stay untouched, or the
    zero baseline stops being the shortest thing on the chart."""
    assert _declares(".col .b-nil", "height") == "2px", (
        "the zero-day baseline height changed; the floor below is sized against it")
    floor = _declares(".col .b:not(.b-nil)", "min-height")
    assert floor is not None, "no floor keeps a rounded-to-p0 real count above the baseline"
    assert float(floor.rstrip("px")) > 2.0, (
        floor, "the floor must clear the 2px baseline, not just match it")


def test_the_system_day_columns_render_a_real_pixel_taller_than_the_baseline(served, browser):
    """The assertion above reads declarations; a declaration can be shadowed,
    overridden, or never resolve the way the cascade suggests. This renders
    both classes for real, off the page's own loaded stylesheet, and measures
    the boxes a browser actually paints -- the only check nothing else in the
    suite performs. Deleting `.col .b-nil{height:2px}` collapses the baseline
    to 0px and turns `nil_h == 2` red; reintroducing the old flat percentage
    height (no floor) turns `p1_h > nil_h` red the moment day_max is large
    enough to round a real count to p0."""
    session = browser
    session.load(f"{served}/?probe=geometry", 400)
    heights = session.evaluate("""
        (function () {
          return document.fonts.ready.then(function () {
            var cols = document.createElement('div'); cols.className = 'cols';
            var mk = function (cls) {
              var col = document.createElement('div'); col.className = 'col';
              var b = document.createElement('span'); b.className = 'b ' + cls;
              col.appendChild(b);
              return {col: col, b: b};
            };
            var nil = mk('b-nil'), p1 = mk('p1'), p50 = mk('p50');
            cols.appendChild(nil.col); cols.appendChild(p1.col); cols.appendChild(p50.col);
            document.body.appendChild(cols);
            var out = [nil.b.getBoundingClientRect().height,
                       p1.b.getBoundingClientRect().height,
                       p50.b.getBoundingClientRect().height];
            document.body.removeChild(cols);
            return out;
          });
        })();
    """)
    nil_h, p1_h, p50_h = heights
    assert nil_h == 2, (heights, "the zero baseline itself moved")
    assert p1_h > nil_h, (heights, "a day rounded to p0 still drew no taller than zero")
    assert p50_h > p1_h, (heights, "the floor must not flatten every nonzero step to one height")


def test_the_scale_tick_carries_the_same_position_as_its_label():
    """The caret used to be the last character of the label string, centred
    with it via one `translateX(-50%)` -- so the marker's true position
    drifted by up to half the label's own width. Splitting them only fixes
    anything if both still ride the identical step class; if the tick fell
    out of sync with `pos(scale_pos)` it would mark a position the label
    does not."""
    steps = _steps()
    with TestClient(app) as client:
        from saafsaans.services import waqi
        from tests.conftest import LIVE_READING
        real = waqi.get_aqi
        waqi.get_aqi = lambda loc, es_client=None: ({**LIVE_READING, "station": loc}, "ok")
        try:
            body = client.get("/", params={"locality": "Anand Vihar", "age": "Adult",
                                           "condition": "Asthma",
                                           "activity": "Outdoor exercise"}).text
        finally:
            waqi.get_aqi = real

    mark = re.search(r'<div class="scale-mark ([^"]+)"', body)
    tick = re.search(r'<div class="scale-tick ([^"]+)"', body)
    assert mark and tick, "both the label and the tick must render"
    assert mark.group(1).strip() == tick.group(1).strip(), (
        mark.group(1), tick.group(1), "the tick drifted from the label it marks")
    assert tick.group(1).strip() in steps


def test_the_scale_tick_is_centred_on_its_own_position_in_a_real_browser(served, browser):
    """A shared class only proves both ride the same `--p`; it does not prove
    the rendered pixel is where `--p` says, because the pre-split bug also
    shared one class and still centred the wrong box. This measures the
    tick's own rendered centre-x against the scale bar's own left edge plus
    `--p` percent of its width, at the low, middle and high end of the scale
    -- where a whole-string centring bug shows up worst."""
    from saafsaans.services import waqi
    from tests.conftest import LIVE_READING

    session = browser
    real = waqi.get_aqi
    waqi.get_aqi = lambda loc, es_client=None: ({**LIVE_READING, "station": loc}, "ok")
    waqi.cache_clear()
    try:
        session.load(f"{served}/?locality=Anand+Vihar&age=Adult&condition=Asthma"
                     f"&activity=Outdoor+exercise", 400)
    finally:
        waqi.get_aqi = real
        waqi.cache_clear()
    result = session.evaluate("""
        (function () {
          return document.fonts.ready.then(function () {
            var scale = document.querySelector('.scale');
            var tick = document.querySelector('.scale-tick');
            if (!scale || !tick) { return null; }
            var sr = scale.getBoundingClientRect();
            var tr = tick.getBoundingClientRect();
            var pct = parseFloat(getComputedStyle(tick).getPropertyValue('--p')) || 0;
            var wanted = sr.left + sr.width * pct / 100;
            var got = tr.left + tr.width / 2;
            return {wanted: wanted, got: got, drift: Math.abs(wanted - got)};
          });
        })();
    """)
    assert result is not None, "no tick rendered on the live reading, so this proved nothing"
    assert result["drift"] <= 2.0, (
        result, "the tick centre drifted more than 2px from the position it marks")


def test_the_caret_label_holds_one_line_at_the_top_of_the_scale():
    """`left` reaching the caret is what makes wrapping possible: an absolutely
    positioned box with `left` and no `right` shrinks to fit the space that
    remains to its container's edge, and near the top of the bar there is less
    of that than the label's 33.03px. Measured in Chrome 151 on the reading
    card, fonts loaded:

        AQI 420 -> p84  17.05px tall at 1200px and at 320px
        AQI 440 -> p88  17.05px at 1200px, 34.09px at 320px
        AQI 500 -> p100 34.09px at both, box collapsed to 19.81px

    Two lines drop the pointer below the digits it belongs to, so the caret no
    longer marks a position -- the half of Never-Colour-Alone this whole
    surface exists to carry, lost exactly on the Severe+ readings Delhi prints
    every November."""
    assert _declares(".scale-mark", "white-space") == "nowrap", (
        "the caret label wraps once left: pushes it near the end of the bar")
    # nowrap alone would hang a full label width past a p100 position; the
    # centring is what keeps its right edge inside the card (296.91px measured
    # against a 304px card edge at the 320px reflow width).
    assert _declares(".scale-mark", "transform") == "translateX(-50%)", (
        "the caret is no longer centred on the position it marks")


def test_the_day_count_sits_near_its_own_bar_at_every_height(served, browser):
    """`.col`'s count used to sit in its own fixed row at the top of the 74px
    band regardless of the bar beneath it -- up to 35.6px above a short bar.
    Nesting the count inside the bar (`bottom: 100%` of `.b`) makes it track
    the bar's OWN rendered top, for a short bar and a full-height one alike --
    and a reserved spacer row keeps even a p100 bar's count from escaping the
    band above `.cols` entirely, which an unbounded float would do on every
    render (the tallest of seven days is always p100 by construction)."""
    session = browser
    session.load(f"{served}/?probe=geometry2", 400)
    result = session.evaluate("""
        (function () {
          return document.fonts.ready.then(function () {
            var cols = document.createElement('div'); cols.className = 'cols';
            var mk = function (cls) {
              var col = document.createElement('div'); col.className = 'col';
              var n = document.createElement('span'); n.className = 'n'; n.textContent = '4';
              var b = document.createElement('span'); b.className = 'b ' + cls;
              b.appendChild(n);
              var d = document.createElement('span'); d.className = 'd'; d.textContent = 'Mon';
              col.appendChild(b); col.appendChild(d);
              return {col: col, b: b, n: n};
            };
            var short = mk('p5'), tall = mk('p100');
            cols.appendChild(short.col); cols.appendChild(tall.col);
            document.body.appendChild(cols);
            var colsTop = cols.getBoundingClientRect().top;
            var out = {
              short_gap: short.b.getBoundingClientRect().top -
                         short.n.getBoundingClientRect().bottom,
              tall_gap: tall.b.getBoundingClientRect().top -
                        tall.n.getBoundingClientRect().bottom,
              tall_n_top: tall.n.getBoundingClientRect().top,
              cols_top: colsTop
            };
            document.body.removeChild(cols);
            return out;
          });
        })();
    """)
    assert abs(result["short_gap"]) <= 3.0, (
        result, "the count no longer sits immediately above its own short bar")
    assert abs(result["tall_gap"]) <= 3.0, (
        result, "the count no longer sits immediately above the tallest bar")
    assert result["tall_n_top"] >= result["cols_top"] - 1.0, (
        result, "the tallest bar's count escaped above the .cols band entirely")


def test_the_security_kpi_grid_keeps_its_own_max_width():
    """The CSP migration deleted `style="max-width:640px"` from the Security
    KPI grid rather than moving it to a class, so a two-or-three-tile row
    stretched to fill the full 1120px shell -- 353px tiles measured against
    the System view's 172px. `.kpis` itself must stay uncapped (the System
    grid legitimately fills its row with many tiles); only the Security
    grid's own class takes the cap back."""
    assert _declares(".kpis-narrow", "max-width") == "640px", (
        "no class restores the width the inline style used to carry")
    assert _declares(".kpis", "max-width") is None, (
        "the cap leaked onto the System grid, which never had one")

    from saafsaans.services import metrics
    with TestClient(app) as client:
        body = client.get("/system", params={"view": "security"}).text
    assert re.search(r'<div class="kpis kpis-narrow">', body), (
        "the Security KPI grid does not carry the class that caps its width")

    body = client.get("/system").text
    assert 'class="kpis"' in body and "kpis-narrow" not in body, (
        "the System KPI grid must not carry the Security-only cap")


def test_the_guides_closing_paragraph_keeps_its_16px_gap():
    """The CSP migration deleted `style="margin-top:16px"` from the Guide's
    closing paragraph without moving the value anywhere, so it fell back to
    `.caveat`'s base 8px -- half the gap it shipped with, right where the
    page hands the reader off after the last citation on it."""
    assert _declares(".caveat-wide-gap", "margin-top") == "16px", (
        "no class restores the 16px the inline style used to carry")

    with TestClient(app) as client:
        body = client.get("/guide").text
    assert re.search(r'<p class="caveat caveat-wide-gap">', body), (
        "the Guide's closing paragraph does not carry the wider gap")
