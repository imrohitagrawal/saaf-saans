"""The one test that watches a real browser fetch the probe.

Every other viewport test parses strings: it can prove the stylesheet names a
band and that the route counts one, and it cannot prove a browser ever asks.
That gap matters because the failure is silent and permanent -- `content: none`
on `body::after`, a later rule overriding `content`, a `display: none`, or an
extension's filter list would leave the whole string-parsing suite green while
the counter sat at zero for ever.

This drives headless Chrome over the DevTools protocol, which is what
`websocket-client` is in requirements.txt for. It is honest about its own
limits: with no Chrome on the machine it SKIPS, and a skipped test guards
nothing, so `SAAFSAANS_REQUIRE_BROWSER=1` turns the skip into a failure for a
run that means to depend on it.
"""
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

    def _pump(self, seconds, wait_id=None):
        deadline = time.time() + seconds
        self.ws.settimeout(0.25)
        while True:
            try:
                message = json.loads(self.ws.recv())
            except Exception:
                message = None
            if message and "method" in message:
                self.events.append(message)
            elif message and wait_id is not None and message.get("id") == wait_id:
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


def test_a_real_browser_fetches_exactly_one_probe_per_page_load(served):
    chrome = _chrome()
    # A fresh port and a fresh profile per run. A fixed pair made this test
    # flaky in exactly the way R5 warns about: a Chrome left behind by an
    # earlier run still held the port, so the next run attached to the STALE
    # browser -- a green suite one minute and a red one the next, with no
    # change to the code under test.
    port = _free_port()
    profile = tempfile.mkdtemp(prefix="saafsaans-probe-")
    process = subprocess.Popen(
        [chrome, "--headless=new", f"--remote-debugging-port={port}",
         "--no-first-run", "--no-default-browser-check",
         "--remote-allow-origins=*",
         f"--user-data-dir={profile}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        session = _Devtools(_devtools_url(port))
        session.send("Network.enable")
        session.send("Page.enable")
        session.probes()

        # The warm-up is load-bearing, not politeness. A CDP session that has
        # not yet settled delivers no Network events at all, and a run that
        # measured zero requests would then read exactly like a probe that
        # never fired. Asserting the warm-up saw one makes a dead session fail
        # loudly instead of passing as a green absence.
        # A CDP session that has not settled delivers no Network events at
        # all, and a run that measured zero requests reads exactly like a probe
        # that never fired. Retried rather than assumed, then asserted: a dead
        # session fails loudly instead of passing as a green absence.
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
