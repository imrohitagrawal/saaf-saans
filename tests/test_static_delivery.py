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

# Every face the stylesheets may reference: name -> (size cap in KB, sha256 of
# the bytes this name was chosen for).
#
# The cap sits above the subsetted size measured at generation (2026-08-31:
# 31.2, 28.7, 8.8, 8.9, 224.8, 40.8). A regenerated file that lost its
# subsetting -- the whole font instead of one script's glyphs -- blows through
# it, and says so in a sentence rather than as a changed hash.
#
# The hash is the stricter half, and it exists because /static is served
# immutable for a year while font URLs carry no ?v=. See
# test_no_face_changed_its_bytes_under_an_unchanged_name.
FACES = {
    "anek-latin-600-800.woff2":
        (40, "be2d8bcdae9637321d224559862de6bb492c61ac5ced52ddf95cfc9f57340240"),
    "plex-sans-400-700.woff2":
        (36, "64d353cb8f067294d848ed719d1dbb507949f70195b47c828e652118c3ef0bdb"),
    "plex-mono-400.woff2":
        (24, "a27d5c10a629d4dff0295088973394881e036e94b0d5bee8688f7449c154ff8d"),
    "plex-mono-600.woff2":
        (24, "0684322301b0525ed566876e4f23dae656346886100df23b91e33f7d028f5758"),
    "anek-devanagari-400-800.devanagari.woff2":
        (264, "20857b3700499c16385fb5feac54d4214298d74389e9b7f4b3fe88fbc9ce50af"),
    "anek-devanagari-400-800.latin.r2.woff2":
        (48, "021513f9d48f1e25a471c2a5b0a32b816275adeb6a1e8d3ec918c26752ebbc5a"),
}
FACES_KB = {name: cap for name, (cap, _) in FACES.items()}


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


def test_no_shipped_face_calls_the_middot_a_combining_mark():
    """U+00B7 separates the meta lines on every view. A face that files it
    under GDEF glyph class 3 (mark) makes HarfBuzz zero its advance, and on
    Hindi pages -- where Anek Devanagari carries the Latin punctuation too --
    the dot then lands on the following word: "AQI 325 ·बहुत ख़राब".

    The dieresis assertion is the partner check: it proves the GDEF class
    table was really read, so a green here cannot mean "found no table".
    """
    from fontTools.ttLib import TTFont

    MARK = 3
    carriers = []
    for name in FACES_KB:
        font = TTFont(STATIC / "fonts" / name)
        cmap = font.getBestCmap()
        gdef = font.get("GDEF")
        classes = ({} if gdef is None or gdef.table.GlyphClassDef is None
                   else gdef.table.GlyphClassDef.classDefs)
        dot = cmap.get(0x00B7)
        if dot is None:
            continue
        carriers.append(name)
        assert classes.get(dot) != MARK, (
            f"{name} classifies U+00B7 as a mark -- its advance renders as 0")
        assert font["hmtx"][dot][0] > 0, f"{name} gives U+00B7 a zero advance"
        if name.startswith("anek-devanagari") and ".latin" in name:
            assert classes.get(cmap[0x00A8]) == MARK, (
                f"{name} lost its real accent marks -- the GDEF check above "
                "is passing on an empty class table")
    assert len(carriers) >= 5, f"only {carriers} carry U+00B7"


def test_the_open_font_licence_ships_beside_the_faces_it_covers():
    """The six faces are subsetted, axis-clipped copies of two Google Fonts
    families under the SIL Open Font License 1.1. Clause 2 permits exactly that
    modification and this redistribution, and requires the licence travel with
    the files. pyftsubset's default name-ID set drops the licence records (13
    and 14) out of the binaries, so before 2026-08-31 the repository carried no
    copy of the OFL at all.

    Red if OFL.txt is deleted, emptied, or stops naming either originator.
    The clause-2 assertion is the partner: it proves the file is the licence
    rather than any text that happens to sit at that path.
    """
    licence = (STATIC / "fonts" / "OFL.txt").read_text()
    assert "SIL OPEN FONT LICENSE Version 1.1" in licence
    assert "PERMISSION & CONDITIONS" in licence, (
        "OFL.txt does not contain the licence body it is named for")
    for originator in ("The Anek Project Authors", "IBM Corp"):
        assert originator in licence, f"{originator} is not credited in OFL.txt"


def test_no_face_changed_its_bytes_under_an_unchanged_name():
    """/static is served immutable for a year and font URLs carry no ?v=, so a
    face whose bytes change under an unchanged name is pinned stale on every
    returning reader until their own cache expires -- a reload does not clear
    it. The rename discipline that prevents this lived only in two comments,
    and the rest of this file could not see a font's bytes change at all: a
    face swapped for another under its own name passed every other test here.

    Updating a hash is the deliberate act the discipline asks for, and it is
    correct only when the rendering is unchanged -- so a stale copy stays right
    -- or the file arrived under a new name. Red the moment bytes move without
    that judgement being made.

    The set comparison is the partner check: it proves the loop ran over real
    files, so a green cannot mean "the manifest was empty", and it forces a new
    face to be registered rather than silently skipped.
    """
    shipped = {p.name: p.read_bytes() for p in (STATIC / "fonts").glob("*.woff2")}
    assert set(shipped) == set(FACES), (
        "the shipped faces and the manifest disagree -- a new or removed face "
        "must be recorded here, and a regenerated one must arrive under a new "
        "name unless its rendering is unchanged")
    for name, data in sorted(shipped.items()):
        assert hashlib.sha256(data).hexdigest() == FACES[name][1], (
            f"{name} changed its bytes under an unchanged name")


def test_each_variable_face_carries_only_the_weights_its_stylesheet_selects():
    """A variable file ships every weight on its wght axis, and the Google css2
    API returns the family's whole axis whatever range the query asked for.
    Measured 2026-08-31: all four variable faces arrived carrying wght from
    100 -- a weight no rule in app.css can reach, because a variable
    @font-face clamps the request into its own declared range before setting
    the axis -- at a cost of 43.7 KB across them.

    Red if scripts/build_fonts.py stops clipping and an unclipped file ships.
    Min and max only: Anek Devanagari's default instance stays at 500 while it
    declares 400 800, so pinning the default would go red after the fix rather
    than before it.

    The static-face half is the partner check. IBM Plex Mono is one file per
    weight and must carry no fvar at all, so a green here cannot mean "found
    no axis to look at".
    """
    from fontTools.ttLib import TTFont

    ranged = 0
    for sheet in ("fonts.css", "fonts-hi.css"):
        for block in re.findall(r"@font-face \{[^}]+\}", (STATIC / sheet).read_text()):
            weight = re.search(r"font-weight: (\d+) (\d+);", block)
            url = re.search(r"url\(/static/fonts/([^)]+\.woff2)\)", block)
            if not (weight and url):
                continue
            ranged += 1
            declared = (float(weight.group(1)), float(weight.group(2)))
            axes = TTFont(STATIC / "fonts" / url.group(1)).get("fvar").axes
            assert [a.axisTag for a in axes] == ["wght"], (
                f"{url.group(1)} carries axes {[a.axisTag for a in axes]}")
            assert (axes[0].minValue, axes[0].maxValue) == declared, (
                f"{url.group(1)} carries wght {axes[0].minValue}-{axes[0].maxValue} "
                f"while its @font-face selects only {declared[0]}-{declared[1]}")
    assert ranged == 4, f"expected four faces declaring a weight range, found {ranged}"
    for static_face in ("plex-mono-400.woff2", "plex-mono-600.woff2"):
        assert TTFont(STATIC / "fonts" / static_face).get("fvar") is None, (
            f"{static_face} grew a variable axis -- the assertions above look for "
            "fvar tables and must not be finding one in every file")


def test_the_generator_still_clips_the_axis_it_is_asked_to_clip(tmp_path):
    """Red if clip_wght stops clipping -- it is called with a range narrower
    than the face already carries, so a no-op body cannot pass.

    It does NOT guard the call site. Nothing in tests/ runs build_fonts.py, so
    deleting the clip_wght(...) line from main() leaves the whole suite green;
    what catches that is the shipped-artifact test above, which goes red as
    soon as an unclipped file is committed. This test covers the other half:
    the call surviving while the function stops working.

    The static face is the partner check: IBM Plex Mono has no fvar, and
    clip_wght must leave such a file byte for byte alone rather than rewriting
    it and churning its hash on every build.
    """
    import shutil
    import sys

    sys.path.insert(0, str(Path(web_main.__file__).parents[2] / "scripts"))
    try:
        import build_fonts
    finally:
        sys.path.pop(0)
    from fontTools.ttLib import TTFont

    variable = tmp_path / "anek.woff2"
    shutil.copy(STATIC / "fonts" / "anek-latin-600-800.woff2", variable)
    build_fonts.clip_wght(variable, 700, 800)
    axes = TTFont(variable)["fvar"].axes
    assert (axes[0].minValue, axes[0].maxValue) == (700.0, 800.0), (
        f"clip_wght left the axis at {axes[0].minValue}-{axes[0].maxValue}")

    static = tmp_path / "mono.woff2"
    shutil.copy(STATIC / "fonts" / "plex-mono-400.woff2", static)
    before = static.read_bytes()
    build_fonts.clip_wght(static, 400, 400)
    assert static.read_bytes() == before, (
        "clip_wght rewrote a static face -- it must return before saving when "
        "there is no fvar, or every build would churn the Plex Mono bytes")


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
    # The mono face carries the 46px AQI numeral, the largest measurement on
    # the site, and is otherwise discovered only after app.css parses -- a
    # round trip late. English only: Hindi redirects --mono to Anek Devanagari,
    # which is preloaded already, and fetches no Latin face at all.
    assert any("plex-mono-600" in p for p in en_preloads), en_preloads
    assert not any("plex-mono" in p for p in hi_preloads), hi_preloads
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


def test_already_compressed_media_is_not_gzipped_but_text_still_is(client):
    """woff2 carries brotli inside and PNG/ICO carry deflate, so gzipping them
    spends CPU to move almost no bytes. Measured 2026-08-31 at compresslevel 9
    against the faces this repository actually ships: four of the six came back
    BIGGER (plex-mono-600 by 23 bytes, anek-latin by 21), and the 230 KB
    Devanagari face saved 0.37% for 8.4 ms of CPU while losing its
    Content-Length to chunked streaming -- on a 256 MB machine that serves
    every first paint.

    /favicon.ico is here as well as under /static because it is a second code
    path: a route returning its own FileResponse, not the StaticFiles mount.

    Red if the bypass in _GZipTextOnly.__call__ is removed. The app.css partner
    is what stops a vacuous green: it asserts text is still compressed, so
    deleting the gzip middleware outright turns this test red rather than green.
    """
    for path, raw_file in (("/static/fonts/plex-mono-600.woff2", "fonts/plex-mono-600.woff2"),
                           ("/static/fonts/anek-devanagari-400-800.devanagari.woff2",
                            "fonts/anek-devanagari-400-800.devanagari.woff2"),
                           ("/static/apple-touch-icon.png", "apple-touch-icon.png"),
                           ("/static/favicon.ico", "favicon.ico"),
                           ("/favicon.ico", "favicon.ico")):
        response = client.get(path, headers={"Accept-Encoding": "gzip"})
        assert response.status_code == 200, path
        assert response.headers.get("Content-Encoding") is None, (
            f"{path} came back gzipped -- it is already compressed")
        # Content-Length, never len(response.content): the test client decodes
        # gzip transparently, so the body length reads the same either way and
        # would stay green with the bypass gone.
        raw = (STATIC / raw_file).stat().st_size
        assert response.headers.get("Content-Length") == str(raw), (
            f"{path} sent Content-Length {response.headers.get('Content-Length')} "
            f"for {raw} raw bytes -- an absent value means it streamed chunked "
            "through gzip")
    css = client.get("/static/app.css", headers={"Accept-Encoding": "gzip"})
    assert css.headers.get("Content-Encoding") == "gzip", (
        "app.css is no longer compressed -- the assertions above are passing "
        "because nothing compresses anything")
    assert int(css.headers["Content-Length"]) * 2 < (STATIC / "app.css").stat().st_size
