"""Regenerates the self-hosted font files and their stylesheets.

    .venv/bin/python scripts/build_fonts.py

Needs network. fonttools and brotli come from requirements.txt, where they are
test dependencies: tests/test_static_delivery.py and tests/test_viewport_probe.py
open the shipped woff2 with fontTools, and brotli is what decodes one. Nothing
under saafsaans/ imports either, and no test runs this script. Output, all under
saafsaans/web/static/:

    fonts/*.woff2   subsetted faces
    fonts.css       @font-face for the Latin faces + metric-matched fallbacks
    fonts-hi.css    @font-face for Anek Devanagari (linked on Hindi pages only)

Pipeline, per family:

1. Ask fonts.googleapis.com/css2 for the weights the stylesheet actually uses
   (app.css audit 2026-08-09: Anek Latin 600/700/800, IBM Plex Sans
   400/500/600/700, IBM Plex Mono 400/600, Anek Devanagari 400-800 for the
   Hindi overrides -- the Anek Latin 500 and Plex Mono 500 the old css2 URL
   requested appear on no rule and are not requested). Anek Latin, Anek
   Devanagari and IBM Plex Sans are served variable, so a weight RANGE returns
   ONE file per script subset (discrete Plex Sans weights returned four
   byte-identical files, verified by md5 2026-08-09); IBM Plex Mono is still
   static -- a range request 400s -- so it stays one file per weight.
2. Download only the script subsets a page can render: `latin` for the three
   Latin faces, `devanagari` + `latin` for Anek Devanagari (Hindi pages set
   --body/--mono to it and still print English words, section 'hi' overrides
   in app.css).
3. Re-subset each file with pyftsubset to exactly the unicode-range Google
   declared for it, `--layout-features='*'` so no Devanagari shaping rule
   (half forms, reph, conjuncts) is dropped -- the Devanagari Floor rule dies
   with those features.
4. Clip each variable face's wght axis to the range its @font-face declares.
   Google serves the family's whole axis whatever the query asked for, so the
   files arrived carrying weights down to 100 that no rule can select: 43.7 KB
   across the four of them.
5. Measure the custom fonts' vertical metrics and frequency-weighted average
   character width with fontTools, measure the same for the local fallback
   (Arial / Courier New), and emit metric-override fallback @font-face blocks
   so swapped-in fallback text occupies the same lines. Formulas as used by
   fontaine / next-font:

       size-adjust     = avgWidth(custom)/upem  ÷  avgWidth(fallback)/upem
       ascent-override = ascent/upem / size-adjust   (descent, line-gap same)

   ascent/descent come from OS/2 sTypo* when fsSelection bit 7 (USE_TYPO_METRICS)
   is set, else hhea -- the same choice browsers make. Every number in the
   emitted CSS is measured from a font file; nothing is typed in by hand.

Font files carry no cache-busting version: their names encode family, weight
and script, the referencing stylesheets are versioned by ?v=<content hash>
(main.py `asset`), and a regenerated face must get a new name if its content
changes meaning.
"""
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "saafsaans" / "web" / "static"
FONTS = STATIC / "fonts"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# family -> (css2 query, wanted script subsets, output stem)
FAMILIES = {
    "Anek Latin": ("family=Anek+Latin:wght@600..800", ["latin"], "anek-latin"),
    "IBM Plex Sans": ("family=IBM+Plex+Sans:wght@400..700", ["latin"],
                      "plex-sans"),
    "IBM Plex Mono": ("family=IBM+Plex+Mono:wght@400;600", ["latin"],
                      "plex-mono"),
    "Anek Devanagari": ("family=Anek+Devanagari:wght@400..800",
                        ["devanagari", "latin"], "anek-devanagari"),
}

# Fallback face measured for each Latin family: a font present on every
# platform this app's readers use. The Devanagari face gets no metric-matched
# fallback on purpose -- there is no cross-platform Devanagari font whose
# metrics can be honestly measured here, so Hindi falls back to the plain
# system stack in app.css.
FALLBACKS = {
    "Anek Latin": ("Arial", "Anek Latin Fallback"),
    "IBM Plex Sans": ("Arial", "IBM Plex Sans Fallback"),
    "IBM Plex Mono": ("Courier New", "IBM Plex Mono Fallback"),
}
# /static is served immutable for a year and font files carry no ?v=, so a face
# whose rendering changes has to arrive under a new name or returning readers
# keep the old one. Rendering, not bytes: the 2026-08-31 axis clip rewrote all
# four variable faces and kept their names, because it moves no glyph more than
# 0.008 px at 16 px and a returning reader on the old file therefore keeps a
# correct, merely larger font -- where renaming would have cost every returning
# Hindi reader a 272 KB re-download to save 24 KB. tests/test_static_delivery.py
# pins each face's sha256 so that judgement has to be made rather than skipped.
# Generated name -> shipped name.
RENAMED = {"anek-devanagari-400-800.latin.woff2":
           "anek-devanagari-400-800.latin.r2.woff2"}

LOCAL_FONT_PATHS = {
    "Arial": "/System/Library/Fonts/Supplemental/Arial.ttf",
    "Courier New": "/System/Library/Fonts/Supplemental/Courier New.ttf",
}

# English letter frequencies (Lewand, "Cryptological Mathematics", the table
# fontaine and next-font weight with), space weighted as the most common glyph.
FREQ = {
    " ": 0.18, "a": 0.0668, "b": 0.0122, "c": 0.0228, "d": 0.0348, "e": 0.1039,
    "f": 0.0182, "g": 0.0165, "h": 0.0499, "i": 0.0570, "j": 0.0013,
    "k": 0.0063, "l": 0.0329, "m": 0.0197, "n": 0.0552, "o": 0.0614,
    "p": 0.0158, "q": 0.0008, "r": 0.0490, "s": 0.0518, "t": 0.0741,
    "u": 0.0226, "v": 0.0080, "w": 0.0193, "x": 0.0012, "y": 0.0161,
    "z": 0.0006,
}

BLOCK = re.compile(
    r"/\* (?P<subset>[\w-]+) \*/\s*@font-face \{[^}]*?"
    r"font-weight: (?P<weight>[\d ]+);[^}]*?"
    r"src: url\((?P<url>[^)]+)\)[^}]*?"
    r"unicode-range: (?P<range>[^;]+);", re.S)


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def subset(raw: Path, out: Path, unicodes: str) -> None:
    # name IDs 13 and 14 are the OFL licence description and its URL. pyftsubset
    # keeps only 0-6 by default, which strips the licence out of a font whose
    # licence requires it to travel with the file; the six faces shipped before
    # 2026-08-31 carry 0-6 only. OFL.txt beside them covers the distribution
    # either way.
    from fontTools import subset as ftsubset
    ftsubset.main([str(raw), f"--unicodes={unicodes}", "--flavor=woff2",
                   "--layout-features=*", "--name-IDs+=13,14",
                   f"--output-file={out}"])


def clip_wght(out: Path, lo: int, hi: int) -> None:
    """Cut the wght axis down to the range the stylesheet can select.

    Google returns the family's whole axis whatever range the css2 query asks
    for: all four variable faces here arrived carrying wght from 100, which no
    rule in app.css can reach -- a variable @font-face clamps the request into
    its own declared range before setting the axis. Measured 2026-08-31,
    clipping to the declared range saves 10,952 B on Anek Latin, 9,472 on Plex
    Sans, 21,800 on the Devanagari face and 2,580 on its Latin sibling. No
    outline moves more than 0.96 units of 2000 upem and no advance more than 1
    unit -- 0.008 px at 16 px -- at any weight the CSS selects.

    Runs last, on a freshly subsetted full-axis file. It is NOT a fixpoint: a
    second pass over an already-clipped face re-solves gvar and the head bbox
    against the narrowed range and shifts the bytes again without changing the
    rendering, which would turn the sha256 pins in tests/test_static_delivery.py
    red for nothing. Clip once, from the download.
    """
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer
    font = TTFont(str(out), recalcTimestamp=False)
    if font.get("fvar") is None:     # IBM Plex Mono is static: one file per weight
        return
    clipped = instancer.instantiateVariableFont(font, {"wght": (lo, None, hi)})
    clipped.flavor = "woff2"
    clipped.save(str(out))


def unmark_middot(out: Path) -> None:
    """Take U+00B7 out of GDEF glyph class 3 (mark).

    Upstream Anek Devanagari files periodcentered alongside the real accents
    -- grave, acute, dieresis, cedilla -- which do belong there. HarfBuzz
    zeroes a mark's advance, so the separator that carries every meta line on
    the site rendered on top of the word after it on Hindi pages, where this
    face carries the Latin punctuation too. Measured 2026-08-10: advance 0.00px
    against 3.75px in every other loaded face. No other upstream file here
    classifies it.
    """
    from fontTools.ttLib import TTFont
    # recalcTimestamp=False, here and in clip_wght: TTFont otherwise stamps
    # head.modified with the wall clock on save, so three runs over identical
    # input produced three different files (measured 2026-08-31: the Devanagari
    # face varied across 230,464-231,316 B, every hash different). With it off
    # the same input gives the same bytes every time, which is what lets the
    # suite pin each shipped face by content hash.
    #
    # That is reproducibility of this script against a fixed download, not of
    # the six faces in the tree: they were subsetted before --name-IDs+=13,14
    # was added above and carry name IDs 0-6 only, so the next rebuild will
    # change all six hashes for a licence-metadata reason. Rendering will be
    # identical, so that rebuild updates the manifest and keeps the filenames.
    font = TTFont(str(out), recalcTimestamp=False)
    dot = font.getBestCmap().get(0x00B7)
    gdef = font.get("GDEF")
    if dot is None or gdef is None or gdef.table.GlyphClassDef is None:
        return
    if gdef.table.GlyphClassDef.classDefs.pop(dot, None) is not None:
        font.save(str(out))


def metrics(path: Path) -> dict:
    """upem, ascent, descent, line gap and weighted average advance width."""
    from fontTools.ttLib import TTFont
    font = TTFont(str(path))
    os2, hhea, upem = font["OS/2"], font["hhea"], font["head"].unitsPerEm
    if os2.fsSelection & (1 << 7):     # USE_TYPO_METRICS
        ascent, descent, gap = (os2.sTypoAscender, os2.sTypoDescender,
                                os2.sTypoLineGap)
    else:
        ascent, descent, gap = hhea.ascent, hhea.descent, hhea.lineGap
    cmap = font.getBestCmap()
    hmtx = font["hmtx"]
    avg = sum(w * hmtx[cmap[ord(ch)]][0] for ch, w in FREQ.items()
              if ord(ch) in cmap) / sum(w for ch, w in FREQ.items()
                                        if ord(ch) in cmap)
    return {"upem": upem, "ascent": ascent, "descent": descent, "gap": gap,
            "avg": avg}


def fallback_face(family: str, custom_file: Path) -> str:
    local, name = FALLBACKS[family]
    custom = metrics(custom_file)
    fb = metrics(Path(LOCAL_FONT_PATHS[local]))
    size_adjust = (custom["avg"] / custom["upem"]) / (fb["avg"] / fb["upem"])
    pct = lambda units: f"{units / custom['upem'] / size_adjust * 100:.2f}%"
    return (f"@font-face {{\n  font-family: \"{name}\";\n"
            f"  src: local(\"{local}\");\n"
            f"  size-adjust: {size_adjust * 100:.2f}%;\n"
            f"  ascent-override: {pct(custom['ascent'])};\n"
            f"  descent-override: {pct(abs(custom['descent']))};\n"
            f"  line-gap-override: {pct(custom['gap'])};\n}}\n")


def face(family: str, weight: str, stem: str, subset_name: str,
         unicodes: str) -> str:
    return (f"@font-face {{\n  font-family: \"{family}\";\n"
            f"  font-style: normal;\n  font-weight: {weight};\n"
            f"  font-display: swap;\n"
            f"  src: url(/static/fonts/{stem}) format(\"woff2\");\n"
            f"  unicode-range: {unicodes};\n}}\n")


def main() -> int:
    FONTS.mkdir(exist_ok=True)
    latin_css, hindi_css = [], []
    for family, (query, subsets, stem) in FAMILIES.items():
        css = fetch(f"https://fonts.googleapis.com/css2?{query}&display=swap"
                    ).decode()
        for m in BLOCK.finditer(css):
            if m["subset"] not in subsets:
                continue
            weight = m["weight"].strip()
            wtag = weight.replace(" ", "-")
            name = (f"{stem}-{wtag}.woff2" if len(subsets) == 1
                    else f"{stem}-{wtag}.{m['subset']}.woff2")
            name = RENAMED.get(name, name)
            raw = FONTS / f"raw-{name}"
            raw.write_bytes(fetch(m["url"]))
            subset(raw, FONTS / name, m["range"].replace(" ", ""))
            unmark_middot(FONTS / name)
            # "600 800" for a variable face, "400" for a static one. The range
            # the stylesheet is about to declare is the range the file should
            # carry, so it is read from the same string rather than a second
            # table that could drift out of step with it.
            bounds = [int(w) for w in weight.split()]
            if len(bounds) == 2:
                clip_wght(FONTS / name, *bounds)
            raw.unlink()
            block = face(family, weight, name, m["subset"], m["range"].strip())
            (hindi_css if family == "Anek Devanagari" else latin_css).append(block)
            print(f"{name}: {(FONTS / name).stat().st_size / 1024:.1f} KB")

    header = ("/* GENERATED by scripts/build_fonts.py -- edit that script, "
              "not this file. */\n")
    fallbacks = [fallback_face(f, sorted(FONTS.glob(f"{FAMILIES[f][2]}-*"))[0])
                 for f in FALLBACKS]
    (STATIC / "fonts.css").write_text(header + "".join(latin_css + fallbacks))
    (STATIC / "fonts-hi.css").write_text(header + "".join(hindi_css))
    return 0


if __name__ == "__main__":
    sys.exit(main())
