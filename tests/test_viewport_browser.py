"""The tests that watch a real browser, because a string cannot answer them.

Two questions live here. Both are invisible to every other test in this suite,
and both fail silently rather than loudly.

**Does a browser ever fetch the probe?** Every other viewport test parses
strings: it can prove the stylesheet names a band and that the route counts
one, and it cannot prove a browser ever asks. That gap matters because the
failure is silent and permanent -- `content: none` on `body::after`, a later
rule overriding `content`, a `display: none`, or an extension's filter list
would leave the whole string-parsing suite green while the counter sat at zero
for ever.

**How tall does a card actually render?** Nothing outside a layout engine can
say. Card height is the sum of line boxes, and a line box depends on the
measure, the face and the script -- so it is a browser question or it is a
guess. It was a guess for three weeks: `docs/PLAN-gates.md` recorded the Today
grid's two narrow cards as 51px apart at 1120px and prescribed a remedy from
that one number. Measured across the whole two-column band the gap runs from
-115px to +51px and changes sign, so the remedy would have doubled the worst
case. The two guards below are what that measurement left behind.

This drives headless Chrome over the DevTools protocol, which is what
`websocket-client` is in requirements.txt for. It is honest about its own
limits: with no Chrome on the machine it SKIPS, and a skipped test guards
nothing, so `SAAFSAANS_REQUIRE_BROWSER=1` turns the skip into a failure for a
run that means to depend on it.
"""
import contextlib
import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request

import pytest

# No `allow_network` marker, deliberately. tests/conftest.py already permits
# loopback, which is every connection this test makes: the DevTools socket is
# 127.0.0.1, and the app's own port is only ever ACCEPTED, never dialled. The
# marker would instead switch real upstream calls back on -- config reads .env
# directly, so a live CPCB key is present even with the environment blanked --
# and this test would start making paid, non-deterministic requests to fetch a
# reading it does not look at.

CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
)
# The three widths, and the band each must report. 400 and 1200 sit inside the
# outer bands; 700 is in the middle one, which no media query names -- it is
# the top-level rule, so a missing override would show up here as the wrong
# band rather than as no request.
CASES = (
    (320, "narrow"),
    # Both boundaries, in the browser rather than in prose. `max-width: 560px`
    # is inclusive, so 560 belongs to narrow and 561 to mid; `min-width: 900px`
    # is inclusive, so 899 is mid and 900 is wide. Changing either media query
    # by one pixel without changing VIEWPORT_BREAKPOINTS turns these red.
    (560, "narrow"),
    (561, "mid"),
    (700, "mid"),
    (899, "mid"),
    (900, "wide"),
    (1200, "wide"),
)


def _required():
    return os.environ.get("SAAFSAANS_REQUIRE_BROWSER") == "1"


def _absent(reason):
    """Skip, or fail when the run declared it depends on this guard.

    Both prerequisites go through here. An earlier version guarded only Chrome
    and reached `pytest.importorskip` afterwards, so a machine with Chrome and
    without websocket-client skipped SILENTLY even under the env var -- the one
    case the variable exists to prevent.
    """
    if _required():
        pytest.fail(f"SAAFSAANS_REQUIRE_BROWSER=1 but {reason}")
    pytest.skip(f"{reason} -- this guard did NOT run")


def _chrome():
    try:
        import websocket  # noqa: F401
    except ImportError:
        _absent("websocket-client is not installed")
    for path in CHROME_CANDIDATES:
        if os.path.exists(path):
            return path
    _absent(f"no Chrome found in {CHROME_CANDIDATES}")


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _Devtools:
    """A CDP session that buffers events instead of discarding them.

    Reading until a command's reply arrives and dropping everything else loses
    the very requests this test exists to see -- the subresource events arrive
    while the navigate reply is in flight.
    """

    def __init__(self, url):
        import websocket
        self.ws = websocket.create_connection(url, timeout=20)
        self.n = 0
        self.events = []
        self.reply = None

    def _pump(self, seconds, wait_id=None):
        deadline = time.time() + seconds
        self.reply = None
        self.ws.settimeout(0.25)
        while True:
            try:
                message = json.loads(self.ws.recv())
            except Exception:
                message = None
            if message and "method" in message:
                self.events.append(message)
            elif message and wait_id is not None and message.get("id") == wait_id:
                self.reply = message
                wait_id = None
            if wait_id is None and time.time() >= deadline:
                break
            if time.time() > deadline + 20:
                raise AssertionError("devtools did not answer")
        self.ws.settimeout(20)

    def send(self, method, settle=0.05, **params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        self._pump(settle, wait_id=self.n)
        return self.reply

    def call(self, method, settle=0.05, **params):
        """The command's own reply, matched by id.

        `send` keeps every event and drops the reply, which is all the probe
        test needs -- it reads Network events and never a return value. A
        `Runtime.evaluate` result arrives the other way round: it is the reply,
        and the id is the only thing separating it from the events streaming in
        alongside it, so matching on the id is the whole of this method.
        """
        reply = self.send(method, settle=settle, **params)
        assert reply is not None, f"{method}: devtools sent no reply"
        assert "error" not in reply, f"{method}: {reply['error']}"
        return reply.get("result", {})

    def evaluate(self, expression, settle=0.05):
        """A page expression's value, with a page exception raised as one here.

        `awaitPromise` because every expression below waits on
        `document.fonts.ready`: measured before the faces land, a card is a
        stack of fallback line boxes and the number means nothing.
        """
        result = self.call("Runtime.evaluate", settle=settle,
                           expression=expression, returnByValue=True,
                           awaitPromise=True)
        assert not result.get("exceptionDetails"), result["exceptionDetails"]
        return result["result"].get("value")

    def load(self, url, width, seconds=3.0):
        """Probes issued by ONE page load at ``width``.

        The width is changed on about:blank, never on a loaded page. Resizing a
        live document across a band boundary makes the browser fetch the new
        band there and then -- real behaviour, measured, and the reason the
        System view says a resized window is counted twice -- but it is not a
        page load, and counting it here would let a resize stand in for the
        thing this test exists to prove.
        """
        self.send("Page.navigate", settle=0.4, url="about:blank")
        self.send("Emulation.setDeviceMetricsOverride", settle=0.4, width=width,
                  height=800, deviceScaleFactor=1, mobile=False)
        self.probes()
        self.send("Page.navigate", url=url)
        self._pump(seconds)
        return self.probes()

    def probes(self):
        found = [event["params"]["request"]["url"]
                 for event in self.events
                 if event.get("method") == "Network.requestWillBeSent"
                 and "/probe/" in event["params"]["request"]["url"]]
        self.events.clear()
        return found


def _devtools_url(port):
    """The websocket for the BROWSER TAB, not for whatever is listed first.

    Chrome ships component extensions, so a fresh profile lists five targets
    and the first two are `background_page`s. Attaching to one of those gives a
    session where `Page.navigate` succeeds and no page ever loads, so the test
    sees zero requests and reads that as "the probe never fired" -- which is
    the whole flakiness this test had. Only `type == "page"` is ours.
    """
    for _ in range(120):
        try:
            raw = urllib.request.urlopen(
                f"http://127.0.0.1:{port}/json/list", timeout=1).read()
            pages = [t for t in json.loads(raw)
                     if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
            if pages:
                return pages[0]["webSocketDebuggerUrl"]
        except Exception:
            pass
        time.sleep(0.25)
    raise AssertionError("Chrome exposed no page target over DevTools")


@pytest.fixture(scope="module")
def served():
    """The real app on a loopback port -- not a TestClient.

    A TestClient speaks ASGI in process and never opens a socket, so a browser
    cannot reach it. This is the app a browser actually loads.
    """
    import uvicorn
    from saafsaans.services import cpcb, es, waqi
    from saafsaans.web import main as web_main
    from saafsaans.web.main import app

    # Hermetic, and it has to be said out loud: the uvicorn thread runs in THIS
    # process against the developer's real .env -- config reads that file
    # directly, so conftest blanking the environment does not stop it. Left
    # alone, a page render here dials CPCB, WAQI and Elasticsearch Cloud for
    # real, on every load, three loads per run. The probe fires from the
    # stylesheet and does not care what any of them say, so all three are
    # stubbed rather than reached.
    upstreams = (cpcb._fetch_city, waqi._fetch_feed, es.get_client, web_main._client)
    cpcb._fetch_city = lambda city: []
    waqi._fetch_feed = lambda feed, token: None
    es.get_client = lambda: None
    web_main._client = None
    waqi.cache_clear()

    # try/finally around EVERYTHING, not just around the yield. Two assertions
    # run during setup, and without this a failed one leaves es.get_client
    # stubbed to None for the rest of the session -- one legible failure here
    # becoming a cascade of misleading ones in the files that collect after
    # this one.
    server = thread = None
    try:
        port = _free_port()
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        for _ in range(200):
            if server.started:
                break
            time.sleep(0.05)
        assert server.started, "the app did not start"
        # Proof the app answers before a browser is blamed for not asking.
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=10) as page:
            markup = page.read().decode()
        assert "app.css" in markup, "the served page links no stylesheet to probe from"

        yield f"http://127.0.0.1:{port}"
    finally:
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(timeout=10)
        (cpcb._fetch_city, waqi._fetch_feed,
         es.get_client, web_main._client) = upstreams
        waqi.cache_clear()


@contextlib.contextmanager
def _chrome_session():
    """One headless Chrome, and a CDP session attached to its page target.

    A fresh port and a fresh profile per run. A fixed pair made this flaky in
    exactly the way R5 warns about: a Chrome left behind by an earlier run
    still held the port, so the next run attached to the STALE browser -- a
    green suite one minute and a red one the next, with no change to the code
    under test.

    `--remote-allow-origins=*` is not decoration. Without it Chrome answers the
    websocket handshake with a 403 and nothing in this file connects at all.
    """
    chrome = _chrome()
    port = _free_port()
    profile = tempfile.mkdtemp(prefix="saafsaans-probe-")
    process = subprocess.Popen(
        [chrome, "--headless=new", f"--remote-debugging-port={port}",
         "--no-first-run", "--no-default-browser-check",
         "--remote-allow-origins=*",
         # macOS draws overlay scrollbars and Linux draws a classic one 15px
         # wide INSIDE the layout viewport, and `setDeviceMetricsOverride` does
         # not sit above it. So a 720px window laid 680px of content here and
         # 665px on the CI runner, where `.grid-duo`'s 330px floor then beats
         # `50% - 8px` and the row falls to a single 665px column: the same
         # stylesheet, a different layout, and a height measurement that means
         # something different on each machine. This makes the two agree.
         "--hide-scrollbars",
         f"--user-data-dir={profile}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        session = _Devtools(_devtools_url(port))
        session.send("Network.enable")
        session.send("Page.enable")
        session.send("Runtime.enable")
        session.probes()
        yield session
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            # Decisive, so nothing is left holding a port or a profile for the
            # next run to attach to by accident.
            process.kill()
            process.wait(timeout=10)
        shutil.rmtree(profile, ignore_errors=True)


@pytest.fixture(scope="module")
def browser():
    """One Chrome for the whole file.

    A second launch costs about a second of wall clock and a second profile to
    clean up, and buys nothing: every measurement below navigates to
    about:blank before it sets a width, so no test can see the previous one's
    document.
    """
    with _chrome_session() as session:
        yield session


def test_a_real_browser_fetches_exactly_one_probe_per_page_load(served, browser):
    session = browser
    # The warm-up is load-bearing, not politeness. A CDP session that has not
    # settled delivers no Network events at all, and a run that measured zero
    # requests reads exactly like a probe that never fired. Retried rather than
    # assumed, then asserted: a dead session fails loudly instead of passing as
    # a green absence.
    warm = []
    for attempt in range(6):
        warm = session.load(f"{served}/?warmup={attempt}", 1200)
        if warm:
            break
    assert warm == [f"{served}/probe/wide.gif"], (
        "the devtools session never reported the warm-up probe -- this run "
        f"measured nothing and proves nothing (saw {warm})")

    for width, expected in CASES:
        found = session.load(f"{served}/?w={width}", width)
        assert len(found) == 1, (width, found, "expected exactly one probe")
        assert found[0].endswith(f"/probe/{expected}.gif"), (width, found)


# The Today grid's two narrow cards, measured in Chrome 151 with a persona
# applied, a live reading, and no five-day outlook -- the state a CPCB reading
# produces, and so almost every reader's. Signed reading-minus-persona, so the
# sign says which card ends lower.
#
#     viewport   tracks        en         hi
#          720   332px    -15.17    -115.47
#          900   422px    +34.78      -0.11
#         1120   532px    +51.31     +45.43
#
# The foot is a step function of track width AND IT CHANGES SIGN. Between 332px
# and 532px tracks the persona card sheds 147px (en) and 216px (hi) while the
# reading card sheds 81px and 55px, so the two curves cross near 840px in
# English and 940px in Hindi. docs/PLAN-gates.md read the 1120px end alone,
# called the reading card the taller one, and prescribed moving a block out of
# it; a constant subtraction shifts the whole curve down, which fixes the
# 1120px end and takes the worst foot from 115px to 168px. Measured, both ways,
# before this file existed.
RAGGED_FOOT = {
    (720, "en"): 15.17, (900, "en"): 34.78, (1000, "en"): 51.31, (1120, "en"): 51.31,
    (720, "hi"): 115.47, (900, "hi"): 0.11, (1000, "hi"): 10.22, (1120, "hi"): 45.43,
}
# The track width each viewport lays, so a page that fell to one column or lost
# its grid fails on the premise instead of reporting a meaningless height.
#
# Four of the twenty-one distinct track widths the band lays between 716px and
# the 1120px shell cap, chosen for shape rather than for spacing: 332px is the
# widest foot, 422px is where English has already crossed and Hindi has not,
# 472px is where Hindi crosses BACK to -10.22, and 532px is the plateau every
# viewport from 1120px up renders. A regression confined to one of the other
# seventeen passes this silently -- the price of four page loads per language
# instead of twenty-one.
TRACK = {720: 332.0, 900: 422.0, 1000: 472.0, 1120: 532.0}
# A wrapped line of .caveat is 18.75px in English and 22.27px in Devanagari, so
# this tolerates one line breaking differently on another Chrome build and
# refuses the 52.53px that moving a block out of the reading card would add.
# The 900px Hindi cell is the tight one: 26px of headroom over a 0.11px foot,
# because that is a crossing point rather than a structural gap.
FOOT_HEADROOM = 26.0

_PERSONA_QS = ("locality=Anand+Vihar&age=Adult&condition=Asthma"
               "&activity=Outdoor+exercise&theme=light")

_CARDS_JS = """
(function () {
  return document.fonts.ready.then(function () {
    function box(el) {
      if (!el) { return null; }
      var r = el.getBoundingClientRect();
      // What the card would be if nothing but its own contents set its height.
      // align-self alone is not enough: it undoes `align-items: stretch` and
      // leaves `min-height` standing, and a min-height levels two feet with the
      // same empty surface stretch would have added.
      var was = {a: el.style.alignSelf, m: el.style.minHeight, h: el.style.height};
      el.style.alignSelf = 'start';
      el.style.minHeight = '0';
      el.style.height = 'auto';
      var natural = el.getBoundingClientRect().height;
      el.style.alignSelf = was.a;
      el.style.minHeight = was.m;
      el.style.height = was.h;
      return {top: Math.round(r.top * 100) / 100,
              width: Math.round(r.width * 100) / 100,
              height: Math.round(r.height * 100) / 100,
              padding: Math.round((r.height - natural) * 100) / 100};
    }
    var grid = document.querySelector('div.grid');
    var reading = document.querySelector('#reading');
    var aqi = reading ? reading.querySelector('.aqi-num') : null;
    // `document.fonts.ready` resolves, and `document.fonts.status` reads
    // "loaded", while a face sits in `error`. Measured with the woff2 files
    // moved aside: every height became fallback metrics and both guards still
    // passed, inside the headroom. Only an error status distinguishes the two.
    //
    // The metric-matched fallback faces are exempt, and must be. fonts.css
    // gives each one `src: local("Arial")` or `local("Courier New")`, so it
    // resolves only where that font is installed -- present on this machine,
    // absent on the Ubuntu CI runner, which reported exactly
    // ['IBM Plex Sans Fallback', 'IBM Plex Mono Fallback'] in error while every
    // self-hosted woff2 had loaded. Their job is to hold the line while a real
    // face is in flight; whether the machine has Arial is not a fact about this
    // deploy.
    var broken = [];
    document.fonts.forEach(function (face) {
      if (face.status === 'error' && !/ Fallback$/.test(face.family)) {
        broken.push(face.family);
      }
    });
    return {innerWidth: window.innerWidth,
            gridClass: grid ? grid.className : null,
            persona: box(document.querySelector('#persona')),
            reading: box(reading),
            brokenFaces: broken,
            // The number itself, not a block that might legitimately move: the
            // premise is that a reading rendered, and "--" is the page saying
            // it has none.
            aqi: aqi ? aqi.textContent.trim() : null};
  });
})()
"""


@pytest.fixture(scope="module")
def today_cards(served, browser):
    """Both narrow cards, measured once at four widths in both languages.

    One fixture rather than one per test: eight page loads is the cost, and two
    tests asking the same eight questions would pay it twice for nothing.

    The feed is stubbed live for the duration of the measurement and restored
    before any test body runs. `served` deliberately renders a page with NO
    reading -- it stubs the fetchers, not `get_aqi` -- which is right for the
    probe test and useless here: with no AQI the reading card loses its scale
    bar and its WHO comparison, and its height stops being the height under
    discussion.
    """
    from saafsaans.services import waqi
    from tests.conftest import LIVE_READING

    real = waqi.get_aqi
    waqi.get_aqi = lambda loc, es_client=None: ({**LIVE_READING, "station": loc}, "ok")
    measured = {}
    try:
        for lang in ("en", "hi"):
            url = f"{served}/?{_PERSONA_QS}&lang={lang}"
            for width in sorted(TRACK):
                browser.load(url, width, seconds=1.2)
                measured[(width, lang)] = browser.evaluate(_CARDS_JS)
    finally:
        waqi.get_aqi = real
        waqi.cache_clear()
    return measured


def _premise(cell, width, lang):
    """Everything that must be true before a height means anything.

    Layout and rendering only. Nothing here asks WHICH blocks the cards
    contain: an inventory check would turn both guards red for a change that
    moves a paragraph and improves the foot, which is the defect they exist to
    let through. The ratchet catches a bad move on its own -- moving the WHO
    comparison out of the reading card reads 168.00px against a 141.47px
    ceiling at 720px in Hindi, unaided.
    """
    where = f"{lang} at {width}px"
    assert cell["innerWidth"] == width, (where, cell["innerWidth"])
    assert cell["persona"] and cell["reading"], (where, "a card is missing")
    assert not cell["brokenFaces"], (
        f"{where}: {cell['brokenFaces']} failed to load, so every height below "
        "is fallback metrics and none of it is comparable")
    assert cell["aqi"] not in (None, "--"), (
        f"{where}: no reading rendered ({cell['aqi']!r}), so this is not the "
        "reading card these figures were measured on")
    assert "grid-duo" in (cell["gridClass"] or ""), (where, cell["gridClass"])
    assert cell["reading"]["width"] == TRACK[width], (
        where, cell["reading"]["width"], "not the track this row should lay")
    assert abs(cell["persona"]["top"] - cell["reading"]["top"]) < 0.5, (
        where, "the two cards are not on one row, so there is no foot to read")


@pytest.mark.parametrize("lang", ("en", "hi"))
def test_the_ragged_foot_between_the_two_narrow_cards_is_no_worse_than_measured(
        today_cards, lang):
    """A ratchet, not a pin: it refuses a change that spreads the two cards
    further apart and stays green for one that closes them.

    Pinning the foot instead would be a check that goes red when the defect is
    fixed. Recording nothing would let the defect grow: the remedy this file's
    header describes reaches 168.00px at 720px in Hindi against a 141.47px
    ceiling, and 52.64px at 900px against 26.11px.
    """
    worse = []
    for width in sorted(TRACK):
        cell = today_cards[(width, lang)]
        _premise(cell, width, lang)
        foot = abs(cell["reading"]["height"] - cell["persona"]["height"])
        ceiling = RAGGED_FOOT[(width, lang)] + FOOT_HEADROOM
        if foot > ceiling:
            worse.append(f"{width}px: {foot:.2f}px against {ceiling:.2f}px "
                         f"(measured {RAGGED_FOOT[(width, lang)]:.2f})")
    assert not worse, (
        f"the {lang} cards end further apart than they were measured to:\n  "
        + "\n  ".join(worse))


@pytest.mark.parametrize("lang", ("en", "hi"))
def test_no_card_in_the_today_grid_is_padded_out_to_its_neighbour(today_cards, lang):
    """`align-items: start` on `.grid`, proved by its effect rather than by
    reading the declaration back.

    This is the guard on the obvious wrong fix, and on the next one after it.
    `stretch` levels the two feet in one word and pays for it in empty surface
    inside the shorter card -- 115.47px of it at 720px in Hindi, measured. It
    turns this red at five of the eight cells; the sixth, Hindi at 900px, is a
    crossing point where the two cards already agree to 0.11px, so there is
    nothing for stretch to add. `min-height` on the two cards buys the same
    levelling by the same means, which is why the probe neutralises that too.
    """
    padded = []
    for width in sorted(TRACK):
        cell = today_cards[(width, lang)]
        _premise(cell, width, lang)
        for name in ("persona", "reading"):
            # A card laid by its own contents reports the same box either way.
            if cell[name]["padding"] > 0.5:
                padded.append(f"{width}px: the {name} card carries "
                              f"{cell[name]['padding']:.2f}px of empty surface")
    assert not padded, (
        f"a {lang} card is sized by its neighbour rather than by its "
        "contents:\n  " + "\n  ".join(padded))
