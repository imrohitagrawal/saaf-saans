"""How the static assets reach the reader: self-hosted subsetted fonts,
content-hashed URLs under an immutable cache lifetime, and gzip on the wire.

These pin the render-blocking-fonts fix (the Google css2 pipeline was the whole
critical path, and it sent every reader's IP to a third party) and the caching
fix. All hermetic: the files are read from disk and the pages from the ASGI
client; nothing here touches the network.
"""
import hashlib
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from saafsaans.web import main as web_main
from saafsaans.web.main import app

STATIC = Path(web_main.__file__).parent / "static"

PERSONA = {"locality": "Anand Vihar", "age": "Adult",
           "condition": "Asthma", "activity": "Outdoor exercise"}

# Every face the stylesheets may reference, with a size cap in KB set just
# above the subsetted size measured at generation (2026-08-09: 41.9, 38.0,
# 8.8, 8.9, 246.1, 43.4). A regenerated file that lost its subsetting -- the
# whole font instead of one script's glyphs -- blows through its cap.
FACES_KB = {
    "anek-latin-600-800.woff2": 64,
    "plex-sans-400-700.woff2": 64,
    "plex-mono-400.woff2": 24,
    "plex-mono-600.woff2": 24,
    "anek-devanagari-400-800.devanagari.woff2": 300,
    "anek-devanagari-400-800.latin.woff2": 64,
}


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# --- the font files themselves ---------------------------------------------
def test_every_font_file_exists_is_woff2_and_stays_subsetted():
    """Red if a woff2 is deleted, replaced by a non-woff2, or regenerated
    without subsetting (size cap). The >1 KB floor is the partner check: a
    zero-byte placeholder must not count as a font."""
    for name, cap_kb in FACES_KB.items():
        path = STATIC / "fonts" / name
        assert path.exists(), f"{name} is missing from static/fonts"
        data = path.read_bytes()
        assert data[:4] == b"wOF2", f"{name} is not a woff2 file"
        assert 1024 < len(data) <= cap_kb * 1024, (
            f"{name} is {len(data) / 1024:.1f} KB, outside (1, {cap_kb}] KB -- "
            "if it grew, it was probably regenerated without subsetting")


def test_the_stylesheets_declare_swap_and_a_file_that_exists():
    """Red if an @font-face drops font-display: swap (text invisible while a
    face loads), names a file that is not shipped, or the sheets go empty."""
    faces = 0
    for sheet in ("fonts.css", "fonts-hi.css"):
        css = (STATIC / sheet).read_text()
        for block in re.findall(r"@font-face \{[^}]+\}", css):
            faces += 1
            if 'local(' in block:
                # The metric-matched fallback faces load no file; their whole
                # point is the measured overrides.
                assert "size-adjust" in block and "ascent-override" in block, block
                continue
            assert "font-display: swap" in block, block
            assert "unicode-range" in block, block
            m = re.search(r"url\(/static/fonts/([^)]+\.woff2)\)", block)
            assert m and m.group(1) in FACES_KB, block
            assert (STATIC / "fonts" / m.group(1)).exists(), m.group(1)
    assert faces >= len(FACES_KB), "the stylesheets declare fewer faces than ship"


def test_fallback_text_is_metric_matched_not_just_a_system_stack():
    """Red if the measured fallback faces are dropped: swap would then reflow
    the page when each woff2 lands. The stacks must actually name them, or the
    @font-face rules are dead weight."""
    fonts_css = (STATIC / "fonts.css").read_text()
    app_css = (STATIC / "app.css").read_text()
    for family in ("Anek Latin Fallback", "IBM Plex Sans Fallback",
                   "IBM Plex Mono Fallback"):
        assert f'font-family: "{family}"' in fonts_css, family
        assert f'"{family}"' in app_css, f"{family} is defined but no stack uses it"


# --- what each language's page loads ----------------------------------------
def test_hindi_pages_load_the_devanagari_face_and_english_pages_do_not(client):
    """The Devanagari Floor rule needs the face on Hindi pages; an English
    reader never downloads it (the wordmark's साफ़ साँस falls back to the
    system stack there, exactly as it did when the face was a conditional
    Google link). Red if the fonts-hi.css link stops being conditional in
    either direction."""
    en = client.get("/", params={**PERSONA, "lang": "en"}).text
    hi = client.get("/", params={**PERSONA, "lang": "hi"}).text
    assert "fonts-hi.css" not in en and "anek-devanagari" not in en
    assert "fonts-hi.css" in hi
    hi_css = (STATIC / "fonts-hi.css").read_text()
    assert "U+0900-097F" in hi_css, "the Hindi sheet no longer covers Devanagari"
    assert "anek-devanagari-400-800.devanagari.woff2" in hi_css


def test_each_language_preloads_the_faces_its_first_paint_is_set_in(client):
    """Red if the preloads vanish (fonts drop out of the critical path's head
    start) or lose `crossorigin`, without which the browser fetches every font
    twice -- preload once, CSS once.

    And red if a preload URL stops matching the src URL in the served fonts
    CSS BYTE FOR BYTE: preload matching is exact-URL, so a preload that adds
    ?v=<hash> to a URL fonts.css declares bare (or vice versa) downloads every
    preloaded font twice, ~90 KB wasted on an English first paint and ~250 KB
    on a Hindi one. The Hindi page preloads the latin subset too, because the
    AQI numerals are digits and digits live in the latin file."""
    css_srcs = set()
    for sheet in ("fonts.css", "fonts-hi.css"):
        css_srcs |= set(re.findall(r"url\((/static/fonts/[^)]+)\)",
                                   client.get(f"/static/{sheet}").text))
    assert css_srcs, "no src URLs found in the served fonts CSS"

    en = client.get("/", params={**PERSONA, "lang": "en"}).text
    hi = client.get("/", params={**PERSONA, "lang": "hi"}).text
    en_preloads = re.findall(r'<link rel="preload"[^>]+>', en)
    hi_preloads = re.findall(r'<link rel="preload"[^>]+>', hi)
    assert any("plex-sans-400-700" in p for p in en_preloads), en_preloads
    assert any("anek-latin-600-800" in p for p in en_preloads), en_preloads
    assert any("anek-devanagari-400-800.devanagari" in p for p in hi_preloads), hi_preloads
    assert any("anek-devanagari-400-800.latin" in p for p in hi_preloads), hi_preloads
    for p in en_preloads + hi_preloads:
        assert 'as="font"' in p and "crossorigin" in p, p
        url = re.search(r'href="([^"]+)"', p).group(1)
        assert url in css_srcs, (
            f"preload {url} matches no src URL in the fonts CSS -- the browser "
            "will download this font twice")


# --- caching ----------------------------------------------------------------
def test_static_responses_are_immutable_and_their_urls_carry_the_content_hash(client):
    """Immutable caching is only safe because the URL changes with the file:
    the template emits ?v=<sha256 prefix of the bytes>. Red if either half is
    removed alone -- versioned URLs without the header cost the revalidation
    round trip; the header without versioning pins a stale stylesheet for a
    year."""
    body = client.get("/", params=PERSONA).text
    m = re.search(r'href="(/static/app\.css\?v=([0-9a-f]{12}))"', body)
    assert m, "app.css is referenced without a content-hash version"
    expected = hashlib.sha256((STATIC / "app.css").read_bytes()).hexdigest()[:12]
    assert m.group(2) == expected, "the version is not the file's own hash"
    response = client.get(m.group(1))
    assert response.status_code == 200
    assert response.headers.get("Cache-Control") == (
        "public, max-age=31536000, immutable"), response.headers.get("Cache-Control")


# --- compression ------------------------------------------------------------
def test_html_is_gzipped_exactly_when_the_client_asks(client):
    """Red without GZipMiddleware. The identity-encoding partner proves the
    header follows the request rather than being stamped on everything -- a
    client that cannot decompress must get plain bytes."""
    gz = client.get("/", params=PERSONA, headers={"Accept-Encoding": "gzip"})
    assert gz.headers.get("Content-Encoding") == "gzip"
    plain = client.get("/", params=PERSONA, headers={"Accept-Encoding": "identity"})
    assert plain.headers.get("Content-Encoding") is None
    assert "SaafSaans" in plain.text
