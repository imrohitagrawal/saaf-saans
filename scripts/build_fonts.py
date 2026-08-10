"""Regenerates the self-hosted font files and their stylesheets.

    .venv/bin/python scripts/build_fonts.py

Needs network and `pip install fonttools brotli` (build-time only; neither is a
runtime dependency and tests never run this). Output, all under
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
4. Measure the custom fonts' vertical metrics and frequency-weighted average
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
# keep the old one. Generated name -> shipped name.
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
    from fontTools import subset as ftsubset
    ftsubset.main([str(raw), f"--unicodes={unicodes}", "--flavor=woff2",
                   "--layout-features=*", f"--output-file={out}"])


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
    font = TTFont(str(out))
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
