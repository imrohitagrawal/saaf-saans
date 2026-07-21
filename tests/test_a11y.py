"""Accessibility claims, measured rather than asserted.

The stylesheet makes three promises that prose in a commit message cannot keep:
that a focus ring survives every container which clips its overflow, that a
finger-sized target is offered wherever a pointing device is coarse, and that
nothing in the layout is wider than the narrowest phone the site targets.

Each test below computes its answer from `app.css` and, where the answer
depends on what is actually inside a container, from the rendered pages. None
of them restates a rule the stylesheet already contains.

What these tests CANNOT establish is anything that needs a rendering engine:
whether a focus ring is visible against the pixels behind it, what order the
tab key visits controls in, and whether two boxes overlap at 375px. Those
remain browser work.
"""
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from saafsaans.web.main import app

CSS_PATH = Path(__file__).resolve().parents[1] / "saafsaans/web/static/app.css"

PERSONA = {"locality": "Anand Vihar", "age": "Adult",
           "condition": "Asthma", "activity": "Outdoor exercise", "theme": "light"}

# The narrowest phone the site targets, and the line-height every box inherits
# from `body`. Both are inputs to the measurements, not conclusions of them.
VIEWPORT = 375
BODY_LINE_HEIGHT = 1.55
BODY_FONT_SIZE = 15.0

# WCAG 2.2: 2.5.5 (AAA) asks 44x44 for a target; 2.5.8 (AA) asks 24x24 and
# exempts targets sitting inline in a sentence, which cannot be enlarged
# without pushing the lines around them apart.
TARGET_FLOOR = 44.0
INLINE_TARGET_FLOOR = 24.0


# --- Stylesheet parsing -----------------------------------------------------
def _css():
    return CSS_PATH.read_text()


def _strip_comments(text):
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def _split_media(text):
    """Return (top_level_css, {media_query: css}). Nested at-rules are not used
    by this stylesheet; a nesting depth counter keeps the split honest anyway."""
    blocks, rest, i = {}, "", 0
    while True:
        found = re.search(r"@media([^{]*)\{", text[i:])
        if not found:
            rest += text[i:]
            return rest, blocks
        rest += text[i:i + found.start()]
        start = i + found.end()
        depth, end = 1, start
        while depth:
            depth += {"{": 1, "}": -1}.get(text[end], 0)
            end += 1
        query = " ".join(found.group(1).split())
        blocks[query] = blocks.get(query, "") + text[start:end - 1]
        i = end


def _rules(text):
    """[(selector_text, {property: value})] in source order."""
    out = []
    for block in re.finditer(r"([^{}@]+)\{([^{}]*)\}", text):
        decls = {}
        for part in block.group(2).split(";"):
            if ":" in part:
                prop, value = part.split(":", 1)
                decls[prop.strip()] = value.strip()
        out.append((" ".join(block.group(1).split()), decls))
    return out


@pytest.fixture(scope="module")
def sheet():
    """The stylesheet, split into the contexts a browser can be in.

    `media` holds EVERY `@media` block by its query, not the two the older
    assertions happened to name. Reading only "top", "(pointer: fine)" and
    "(max-width: 560px)" meant a rule written in any other block was invisible
    to every test here -- which is exactly how `(pointer: coarse)` came to hold
    the only Devanagari padding on the site with nothing measuring it.
    """
    top, media = _split_media(_strip_comments(_css()))
    return {"top": _rules(top),
            "fine": _rules(media.get("(pointer: fine)", "")),
            "narrow": _rules(media.get("(max-width: 560px)", "")),
            "media": {query: _rules(body) for query, body in media.items()},
            "raw": _css()}


def _decls(rules, key):
    """Merge, in source order, every rule whose selector list contains `key`."""
    merged = {}
    for selector, decls in rules:
        if key in [s.strip() for s in selector.split(",")]:
            merged.update(decls)
    return merged


def _px(value):
    value = (value or "").strip()
    if value == "0":
        return 0.0
    found = re.match(r"(-?\d+(?:\.\d+)?)px$", value)
    return float(found.group(1)) if found else None


def _edges(shorthand, axis):
    """Vertical or horizontal total of a padding/margin shorthand, in px."""
    if not shorthand:
        return 0.0
    parts = [(_px(p) or 0.0) for p in shorthand.split()]
    # Resolve the CSS shorthand BEFORE touching `parts`: padding the list first
    # destroys the length the rules below depend on, which silently measured a
    # three-value shorthand's left edge as its bottom.
    if len(parts) == 1:
        top = right = bottom = left = parts[0]
    elif len(parts) == 2:
        top, right = parts
        bottom, left = top, right
    elif len(parts) == 3:
        top, right, bottom = parts
        left = right
    else:
        top, right, bottom, left = parts[:4]
    return top + bottom if axis == "y" else left + right


def _border(decls, axis):
    width = _px((decls.get("border", "").split() or [""])[0])
    return 2 * width if width else 0.0


# --- Rendered markup --------------------------------------------------------
class _Tree(HTMLParser):
    """A minimal element tree: enough to ask what is inside what."""

    VOID = {"meta", "link", "input", "br", "img", "hr", "source"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = {"tag": "#root", "attrs": {}, "kids": [], "parent": None, "text": ""}
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = {"tag": tag, "attrs": dict(attrs), "kids": [], "parent": self.stack[-1],
                "text": ""}
        self.stack[-1]["kids"].append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs if tag in self.VOID else attrs)

    def handle_data(self, data):
        """Text is attributed to the element that directly contains it, so a
        size can be resolved for the box the glyphs are actually painted in."""
        self.stack[-1]["text"] += data

    def handle_endtag(self, tag):
        for depth in range(len(self.stack) - 1, 0, -1):
            if self.stack[depth]["tag"] == tag:
                del self.stack[depth:]
                return


def _walk(node):
    for kid in node["kids"]:
        yield kid
        yield from _walk(kid)


def _classes(node):
    return set(node["attrs"].get("class", "").split())


def _ancestors(node):
    node = node["parent"]
    while node is not None:
        yield node
        node = node["parent"]


FOCUSABLE_TAGS = {"a", "button", "select", "input", "textarea", "summary"}


def _is_focusable(node):
    if node["tag"] == "a":
        return "href" in node["attrs"]
    return node["tag"] in FOCUSABLE_TAGS


@pytest.fixture(scope="module")
def pages():
    """Every disclosure state the site can be in, parsed into trees.

    The provenance panel and the answer card only exist once a question has
    been asked, so the fixture asks one.
    """
    rendered = {}
    with TestClient(app) as client:
        client.post("/ask", params=PERSONA, data={"question": "Can I go for a run this evening?"},
                    follow_redirects=True)
        views = {
            "today": ("/", PERSONA),
            "today-persona-open": ("/", {**PERSONA, "edit": "1"}),
            "today-term-open": ("/", {**PERSONA, "term": "PM2.5"}),
            "city": ("/city", PERSONA),
            "system": ("/system", PERSONA),
            "system-security": ("/system", {**PERSONA, "view": "security"}),
            "guide": ("/guide", PERSONA),
        }
        for name, (path, params) in views.items():
            rendered[name] = client.get(path, params=params).text
        # The provenance link keys off the turn id, so read it back off the page.
        turn = re.search(r'id="turn-([^"]+)"', rendered["today"])
        if turn:
            rendered["today-prov-open"] = client.get(
                "/", params={**PERSONA, "prov": turn.group(1)}).text

    trees = {}
    for name, html in rendered.items():
        parser = _Tree()
        parser.feed(html)
        trees[name] = parser.root
    return trees


# --- 1. Keyboard: every control is a real control ---------------------------
# Each disclosure named in the brief, and the class its control carries.
CONTROL_CLASSES = {
    "skip": "skip link",
    "wordmark": "wordmark",
    "nav": "main navigation",            # applied to the <nav>, links inside
    "pill-btn": "persona editor toggle / red-team simulation",
    "term": "term definition disclosure",
    "prov-btn": "provenance panel",
    "station": "station row",
    "btn": "form submit",
}


def test_every_disclosure_control_is_natively_focusable(pages):
    """Zero JavaScript means every control must already be a link or a form
    control. That is a structural claim about the templates, so check it
    against what they actually render rather than assuming it."""
    seen = set()
    for name, root in pages.items():
        for node in _walk(root):
            for css_class in _classes(node) & set(CONTROL_CLASSES):
                if css_class == "nav":
                    continue                      # the <nav> wraps links, is not one
                seen.add(css_class)
                assert _is_focusable(node), (
                    f"{name}: .{css_class} ({CONTROL_CLASSES[css_class]}) rendered as "
                    f"<{node['tag']}>, which the keyboard cannot reach")
        for node in _walk(root):
            assert node["attrs"].get("tabindex") not in ("-1",), (
                f"{name}: <{node['tag']}> is removed from the tab order")
            assert not any(a.startswith("on") for a in node["attrs"]), (
                f"{name}: <{node['tag']}> carries an inline event handler")
    # The segments are anchors inside a container class, so check them by tag.
    for name, root in pages.items():
        for node in _walk(root):
            if "seg" in _classes(node):
                kids = [k for k in node["kids"] if k["tag"] != "#text"]
                assert kids and all(_is_focusable(k) for k in kids), (
                    f"{name}: a .seg option is not focusable")
                seen.add("seg")
    missing = (set(CONTROL_CLASSES) | {"seg"}) - seen - {"nav"}
    assert not missing, f"never rendered, so never checked: {sorted(missing)}"


# --- 2. Focus rings survive every clipping container ------------------------
def test_clipping_containers_holding_controls_pull_the_focus_ring_inside(sheet, pages):
    """`overflow: hidden` crops a ring drawn outside its child (the global rule
    uses `outline-offset: 2px`). Any such container that holds a focusable
    descendant therefore needs a matching negative-offset remedy."""
    clipping = []
    for selector, decls in sheet["top"]:
        if decls.get("overflow") in ("hidden", "clip"):
            for part in selector.split(","):
                part = part.strip()
                assert re.fullmatch(r"\.[A-Za-z0-9_-]+", part), (
                    f"overflow clipping on {part!r}, which this audit cannot resolve "
                    "to elements -- extend the test rather than skipping it")
                clipping.append(part[1:])
    assert clipping, "no clipping containers found -- the parser is broken"

    # Which of them actually contain something the keyboard can land on.
    holds_control = set()
    for name, root in pages.items():
        for node in _walk(root):
            for css_class in _classes(node) & set(clipping):
                if any(_is_focusable(kid) for kid in _walk(node)):
                    holds_control.add(css_class)

    assert holds_control, ("no clipping container was found holding a control -- the "
                           "markup scan found nothing, so this test proved nothing")

    remedied = {}
    for selector, decls in sheet["top"]:
        found = re.fullmatch(r"\.([A-Za-z0-9_-]+) :focus-visible", selector.strip())
        if found and "outline-offset" in decls:
            remedied[found.group(1)] = _px(decls["outline-offset"])
    # A remedy in a comma-separated list counts too.
    for selector, decls in sheet["top"]:
        if ":focus-visible" not in selector or "outline-offset" not in decls:
            continue
        for part in selector.split(","):
            found = re.fullmatch(r"\.([A-Za-z0-9_-]+) :focus-visible", part.strip())
            if found:
                remedied[found.group(1)] = _px(decls["outline-offset"])

    for css_class in sorted(holds_control):
        assert css_class in remedied, (
            f".{css_class} clips its overflow and contains a focusable element, but no "
            f"'.{css_class} :focus-visible' rule pulls the ring inside it")
        assert remedied[css_class] < 0, (
            f".{css_class} :focus-visible has outline-offset {remedied[css_class]}px; a "
            "ring drawn outside the child is cropped by the clip")


# --- 3. Touch targets on coarse pointers ------------------------------------
# Each interactive control, as the chain of selectors that decides its box, in
# ascending specificity. The chain is the cascade this stylesheet actually
# builds -- `.pill-btn.strong` outranks `.pill-btn` wherever it appears, so a
# floor set on the latter alone does not reach the persona toggle.
CONTROLS = {
    "skip link": ([".skip"], "block"),
    "wordmark": ([".wordmark", ".wordmark b"], "block"),
    "nav link": ([".nav a"], "block"),
    "segment option": ([".seg a"], "block"),
    "pill button": ([".pill-btn"], "block"),
    "persona editor toggle": ([".pill-btn", ".pill-btn.strong"], "block"),
    "provenance button": ([".prov-btn"], "block"),
    "station row": ([".station"], "block"),
    "primary button": ([".btn"], "block"),
    "persona form submit": ([".btn", ".fields .btn"], "block"),
    "persona picker": (["select"], "block"),
    "ask input": (['input[type="text"]', ".ask-form input"], "block"),
    "glossary term": ([".term"], "inline"),
}


def _measured_height(rules, chain, inherited_font):
    decls = {}
    for key in chain:
        decls.update(_decls(rules, key))
    font = _px(decls.get("font-size", "")) or inherited_font
    content = round(font * BODY_LINE_HEIGHT, 2)
    box = content + _edges(decls.get("padding"), "y") + _border(decls, "y")
    return max(box, _px(decls.get("min-height", "")) or 0.0)


def _smallest_inherited_font(sheet, pages, chain):
    """The font-size a control inherits, from the contexts it is rendered in.

    Resolves inline ``style`` attributes and single-class ``font-size`` rules
    only. A descendant selector (``.pollutants .lbl``) can set a smaller size
    than the ancestor's own class does, and this will not see it -- so the
    figure is a reasonable estimate of the worst case, not a proven bound.
    Stated rather than implied, because a test that overstates its own reach
    is the kind of reassurance this project exists to avoid."""
    target = chain[-1].split()[-1].lstrip(".").split(".")[0]
    sizes = []
    for root in pages.values():
        for node in _walk(root):
            if target not in _classes(node) and node["tag"] != target:
                continue
            for ancestor in _ancestors(node):
                inline = re.search(r"font-size:\s*([\d.]+)px", ancestor["attrs"].get("style", ""))
                if inline:
                    sizes.append(float(inline.group(1)))
                    break
                found = [_px(_decls(sheet["top"], f".{c}").get("font-size", ""))
                         for c in _classes(ancestor)]
                found = [f for f in found if f]
                if found:
                    sizes.append(min(found))
                    break
            else:
                sizes.append(BODY_FONT_SIZE)
    return min(sizes) if sizes else BODY_FONT_SIZE


def test_coarse_pointer_touch_targets_clear_the_floor(sheet, pages):
    """Outside `@media (pointer: fine)` the stylesheet is the touch stylesheet.
    Every control it paints there has to be big enough for a fingertip."""
    too_small = []
    for label, (chain, flow) in CONTROLS.items():
        height = _measured_height(sheet["top"], chain,
                                  _smallest_inherited_font(sheet, pages, chain))
        floor = TARGET_FLOOR if flow == "block" else INLINE_TARGET_FLOOR
        if height + 0.05 < floor:
            too_small.append(f"{label} ({' -> '.join(chain)}): {height:.1f}px < {floor}px")
    assert not too_small, "coarse-pointer targets below the floor:\n  " + "\n  ".join(too_small)


def test_pointer_fine_only_ever_reduces_a_target(sheet, pages):
    """`@media (pointer: fine)` exists to give back the designed density on a
    mouse. Every selector in it must therefore be strictly shorter than the
    same selector at top level -- an entry that is equal is dead weight, and an
    entry that is taller means the raise and the restore have been swapped, so
    the floor would apply to the mouse and not to the finger.

    This also catches a restore written at a specificity the raise does not
    reach: the top-level lookup would find no padding to reduce.
    """
    for selector, decls in sheet["fine"]:
        if "padding" not in decls:
            continue
        for part in [s.strip() for s in selector.split(",")]:
            touch = _edges(_decls(sheet["top"], part).get("padding"), "y")
            fine = _edges(decls["padding"], "y")
            assert fine < touch, (
                f"@media (pointer: fine) sets {part} padding to {fine}px against "
                f"{touch}px at top level -- the touch floor is the one that must be larger")


def test_every_raised_control_is_given_its_density_back_on_a_mouse(sheet):
    """The converse. A selector whose padding is written twice at top level is
    a design rule plus a floor rule; unless the fine-pointer block names it,
    the floor silently becomes the desktop design too."""
    fine = {part.strip() for selector, decls in sheet["fine"] if "padding" in decls
            for part in selector.split(",")}
    counts = {}
    for selector, decls in sheet["top"]:
        if "padding" in decls:
            for part in [s.strip() for s in selector.split(",")]:
                counts[part] = counts.get(part, 0) + 1
    for selector, count in sorted(counts.items()):
        if count > 1:
            assert selector in fine, (
                f"{selector} has its padding set {count} times at top level -- a floor "
                "over a design -- but @media (pointer: fine) never puts it back")


# --- 4. Nothing forces the layout past 375px --------------------------------
def _horizontal_padding(sheet, css_class):
    """A class's horizontal padding at 375px: the narrow media query wins."""
    decls = _decls(sheet["top"], f".{css_class}")
    decls.update(_decls(sheet["narrow"], f".{css_class}"))
    return _edges(decls.get("padding"), "x")


def _budget(sheet, pages, css_class):
    """Width available to an element of this class at 375px: the viewport less
    the horizontal padding of every ancestor it is actually rendered inside.
    The worst case across all pages is the one that has to fit."""
    widths = []
    for root in pages.values():
        for node in _walk(root):
            if css_class not in _classes(node):
                continue
            spent = sum(_horizontal_padding(sheet, c)
                        for ancestor in _ancestors(node) for c in _classes(ancestor))
            widths.append(VIEWPORT - spent)
    return min(widths) if widths else float(VIEWPORT)


def test_no_track_or_fixed_width_forces_the_layout_past_375px(sheet, pages):
    """Grid tracks, `minmax` minimums and fixed widths cannot shrink. Summed
    against the space their container actually has at 375px, they must fit."""
    problems = []
    for selector, decls in sheet["top"]:
        classes = [p.strip()[1:] for p in selector.split(",")
                   if re.fullmatch(r"\.[A-Za-z0-9_-]+", p.strip())]
        if not classes:
            continue
        budget = min(_budget(sheet, pages, c) for c in classes)
        gap = _px((decls.get("gap", "0") or "0").split()[-1]) or 0.0

        tracks = decls.get("grid-template-columns", "")
        if tracks:
            fixed = [_px(t) or 0.0 for t in re.findall(r"(?<![(,])\s(\d+(?:\.\d+)?px)", " " + tracks)]
            minimums = [float(m) for m in re.findall(r"minmax\(\s*(\d+(?:\.\d+)?)px", tracks)]
            columns = len(re.findall(r"\S+px|1fr|minmax\([^)]*\)|repeat\([^)]*\)", tracks))
            needed = sum(fixed) + sum(minimums) + gap * max(columns - 1, 0)
            if needed > budget:
                problems.append(f"{selector}: tracks need {needed:.0f}px, "
                                f"{budget:.0f}px available at {VIEWPORT}px")

        for prop in ("width", "min-width"):
            value = _px(decls.get(prop, ""))
            if value and decls.get("position") != "absolute" and value > budget:
                problems.append(f"{selector}: {prop} {value:.0f}px > {budget:.0f}px available")
    assert not problems, "horizontal overflow at 375px:\n  " + "\n  ".join(problems)


def test_flex_items_sized_past_their_container_are_allowed_to_shrink(sheet, pages):
    """`flex-shrink` is capped by `min-width: auto`, which for a replaced
    element like a <select> is its intrinsic width. An item given a basis wider
    than its container therefore needs an explicit `min-width: 0` before it can
    honour the shrink factor at all."""
    problems = []
    for selector, decls in sheet["top"]:
        basis = re.fullmatch(r"(\d+)\s+(\d+)\s+(\d+(?:\.\d+)?)px", decls.get("flex", "").strip())
        if not basis:
            continue
        classes = [p.strip()[1:] for p in selector.split(",")
                   if re.fullmatch(r"\.[A-Za-z0-9_-]+", p.strip())]
        target = selector.split()[-1].lstrip(".")
        budget = min([_budget(sheet, pages, c) for c in classes] or
                     [_budget(sheet, pages, target)])
        wider = float(basis.group(3)) > budget
        shrinks = int(basis.group(2)) > 0
        if wider and (not shrinks or _px(decls.get("min-width", "")) != 0.0):
            problems.append(f"{selector}: basis {basis.group(3)}px exceeds the "
                            f"{budget:.0f}px available and cannot shrink to fit")
    assert not problems, "flex items that cannot shrink at 375px:\n  " + "\n  ".join(problems)


def test_no_inline_style_undercuts_the_touch_target_floor():
    """The stylesheet's 44px floor is only a floor if nothing outranks it. An
    inline style attribute does, at a specificity no media query can reach --
    which is how the System toggle stayed a 31px target while every measured
    test passed. This reads the templates rather than the stylesheet, because
    that is where the override lived."""
    import pathlib
    import re
    offenders = []
    for path in sorted(pathlib.Path("saafsaans/web/templates").glob("*.html")):
        for match in re.finditer(r'<a\b[^>]*style="([^"]*)"', path.read_text()):
            style = match.group(1)
            if re.search(r"\b(padding|font-size)\s*:", style):
                offenders.append(f"{path.name}: {style}")
    assert not offenders, (
        "inline padding/font-size on a link overrides the touch floor: %s" % offenders)


# --- 5. The caveat palette --------------------------------------------------
# Demoting a sentence means making it quieter, and the floor under "quieter" is
# a measured contrast ratio, not an opinion about how grey is too grey. Every
# figure below is computed from the tokens in this stylesheet.

def _lum(hex_or_rgb):
    channels = hex_or_rgb
    if isinstance(channels, str):
        h = channels.lstrip("#")
        channels = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    f = lambda c: (c / 255) / 12.92 if (c / 255) <= 0.03928 else (((c / 255) + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(channels[0]) + 0.7152 * f(channels[1]) + 0.0722 * f(channels[2])


def _ratio(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _over(fg, alpha, bg):
    """Source-over compositing, which is what `opacity` and an `rgba` fill do."""
    if isinstance(fg, str):
        h = fg.lstrip("#")
        fg = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    return [fg[i] * alpha + bg[i] * (1 - alpha) for i in range(3)]


def _token(css, block, name):
    chunk = css.split(block, 1)[1]
    return re.search(rf"{name}:\s*(#[0-9A-Fa-f]{{6}})", chunk).group(1)


THEMES = (("light", ":root {"), ("dark", '[data-theme="dark"] {'))
AA_TEXT = 4.5


def test_the_caveat_palette_clears_the_text_floor_in_both_themes(sheet):
    """`.caveat` is the quietest text on the site, so it is the one most likely
    to fall under the floor. Its colour token, its link colour and the promoted
    `.meaning` are all resolved from the stylesheet and measured against the two
    surfaces a caveat is ever painted on."""
    css = _strip_comments(sheet["raw"])
    caveat = _decls(sheet["top"], ".caveat")
    assert caveat, ".caveat has no rule -- this test would prove nothing"
    measured = {}
    for theme, block in THEMES:
        surface, bg = _token(css, block, "--surface"), _token(css, block, "--bg")
        for label, decls, backdrop in (
                ("caveat on --surface", caveat, surface),
                ("caveat on --bg", caveat, bg),
                ("caveat link", _decls(sheet["top"], ".caveat a"), surface),
                ("caveat on a tint", _decls(sheet["top"], ".caveat.on-tint"),
                 _token(css, block, "--surface-2")),
                ("meaning", _decls(sheet["top"], ".meaning"), surface)):
            token = re.fullmatch(r"var\((--[\w-]+)\)", decls["color"]).group(1)
            ratio = _ratio(_token(css, block, token), backdrop)
            measured[f"{theme} {label}"] = ratio
            assert ratio >= AA_TEXT, f"{theme} {label}: {ratio:.2f}:1"

    # The reason .on-tint exists at all, asserted rather than remembered: the
    # caveat's own colour does NOT clear the floor on a tinted panel in dark.
    dark = dict(THEMES)["dark"]
    on_tint_would_be = _ratio(_token(css, dark, "--text-3"), _token(css, dark, "--surface-2"))
    assert on_tint_would_be < AA_TEXT, (
        f"--text-3 now measures {on_tint_would_be:.2f}:1 on --surface-2 in dark. If that is "
        "genuinely above the floor, .on-tint is no longer needed -- but check the token "
        "change that did it before deleting anything")
    assert "background" not in caveat, (
        ".caveat has gained a background; --text-3 does not clear the floor on every "
        "panel colour this site uses, which is why it had none")


def test_the_hero_caveat_is_readable_over_every_sky_in_both_themes(sheet):
    """The hero caveat is white-ish text at 65% opacity, on an 85%-opaque panel,
    over a gradient that changes with the reading. Its worst case is therefore a
    composite of three layers and cannot be read off a token pair."""
    css = _strip_comments(sheet["raw"])
    hero = _decls(sheet["top"], ".hero-window .caveat")
    window = _decls(sheet["top"], ".hero-window")
    ink = hero["color"]
    alpha = float(hero["opacity"])
    panel = re.search(r"rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)", window["background"])
    panel_rgb = [int(panel.group(i)) for i in (1, 2, 3)]
    panel_alpha = float(panel.group(4))

    skies = re.findall(r"--sky1:\s*(#[0-9A-Fa-f]{6});\s*--sky2:\s*(#[0-9A-Fa-f]{6})", css)
    assert len(skies) >= 14, f"only {len(skies)} skies found -- both themes must be covered"
    worst = min(_ratio(_over(ink, alpha, backdrop), backdrop)
                for pair in skies for sky in pair
                for backdrop in [_over(panel_rgb, panel_alpha, [int(sky.lstrip('#')[i:i + 2], 16)
                                                                for i in (0, 2, 4)])])
    assert worst >= AA_TEXT, f"hero caveat bottoms out at {worst:.2f}:1 over some sky"


def test_hindi_never_renders_a_caveat_below_the_devanagari_floor(sheet):
    """12.5px was chosen against Latin. Devanagari carries its distinguishing
    detail above and below the line, so below about 12px the matras stop
    resolving -- the floor the rest of the Hindi block already applies."""
    floors = {}
    for selector, decls in sheet["top"]:
        for part in [s.strip() for s in selector.split(",")]:
            if "caveat" in part and "font-size" in decls:
                floors[part] = _px(decls["font-size"])
    assert ":lang(hi) .caveat" in floors, "the Devanagari prose floor no longer names .caveat"
    for part, size in floors.items():
        if part.startswith(":lang(hi)"):
            assert size >= 12.5, f"{part} sets {size}px, below where Devanagari resolves"
    # The hero caveat is the one set below that floor in Latin, so it is the one
    # that needs its own Hindi rule; the old `.note` never had one.
    assert floors.get(":lang(hi) .hero-window .caveat", 0) > floors[".hero-window .caveat"]


# --- 6. Devanagari never renders below the floor ----------------------------
# The three defects this section exists for were all invisible to the helpers
# above, and for the same reason: those helpers read the stylesheet as a flat
# selector -> declarations map, so they can say what `.seg a` declares but never
# what a given element on a given page ends up at. The size a reader actually
# gets is the product of the cascade plus inheritance plus any inline style, and
# nothing here measured that. What follows resolves it.

DEVANAGARI = re.compile(r"[ऀ-ॿ]")

# Devanagari carries its distinguishing detail above and below the line -- the
# matras and the shirorekha -- so at a given font-size the glyph body is smaller
# than Latin's. app.css:481 records where they stop resolving (about 12px); the
# floor the Hindi block actually applies to its labels is 12.5px, and that is
# the number asserted, because a floor the stylesheet does not keep is not one.
DEVANAGARI_FLOOR = 12.5

_SIMPLE = re.compile(r"""
    (?P<tag>^[a-zA-Z][\w-]*)
  | \.(?P<cls>[\w-]+)
  | \#(?P<id>[\w-]+)
  | \[(?P<attr>[\w-]+)(?:\s*=\s*"?(?P<val>[^"\]]*)"?)?\]
  | :lang\((?P<lang>[\w-]+)\)
  | :not\((?P<negated>[^)]*)\)
  | ::?(?P<pseudo>[\w-]+)(?:\([^)]*\))?
""", re.X)

# Pseudo-classes describing a state no static render is in. A rule carrying one
# is not part of the resting page and must not be resolved onto it.
_STATEFUL = {"hover", "focus", "focus-visible", "active", "visited", "before", "after"}


def _parse_compound(text):
    """One compound selector -> its simple parts, or None if unparseable."""
    parts, i = [], 0
    while i < len(text):
        found = _SIMPLE.match(text, i)
        if not found or found.end() == i:
            return None
        parts.append(found)
        i = found.end()
    return parts


def _computed_lang(node):
    while node is not None:
        if node["attrs"].get("lang"):
            return node["attrs"]["lang"]
        node = node["parent"]
    return None


def _matches_compound(node, parts):
    for found in parts:
        group = found.groupdict()
        if group["tag"] and node["tag"] != group["tag"]:
            return False
        if group["cls"] and group["cls"] not in _classes(node):
            return False
        if group["id"] and node["attrs"].get("id") != group["id"]:
            return False
        if group["attr"]:
            value = node["attrs"].get(group["attr"])
            if value is None or (group["val"] is not None and value != group["val"]):
                return False
        if group["lang"] and (_computed_lang(node) or "").split("-")[0] != group["lang"]:
            return False
        if group["negated"] is not None:
            inner = _parse_compound(group["negated"].strip())
            if inner and _matches_compound(node, inner):
                return False
        if group["pseudo"]:
            if group["pseudo"] in _STATEFUL:
                return False
            if group["pseudo"] == "first-child":
                siblings = node["parent"]["kids"] if node["parent"] else []
                if not siblings or siblings[0] is not node:
                    return False
    return True


def _specificity(selector):
    ids = len(re.findall(r"#[\w-]+", selector))
    classes = (len(re.findall(r"\.[\w-]+", selector))
               + len(re.findall(r"\[[^\]]*\]", selector))
               + len(re.findall(r":(?!:)(?!not\()[\w-]+", selector)))
    tags = len(re.findall(r"(?:^|[\s>+~])([a-zA-Z][\w-]*)", selector))
    return (ids, classes, tags)


def _matches(node, selector):
    """Descendant and child combinators only -- this stylesheet uses no other,
    and a child combinator is treated as a descendant, which can only ever make
    the resolver claim a rule applies when it does not. That direction is safe
    here: it would hide a too-small size, never invent one."""
    sequence = [part for part in re.split(r"\s+", selector.strip())
                if part not in (">", "+", "~")]
    compounds = [_parse_compound(part) for part in sequence]
    if any(compound is None for compound in compounds):
        return False
    if not _matches_compound(node, compounds[-1]):
        return False
    ancestor = node["parent"]
    for compound in reversed(compounds[:-1]):
        while ancestor is not None and not _matches_compound(ancestor, compound):
            ancestor = ancestor["parent"]
        if ancestor is None:
            return False
        ancestor = ancestor["parent"]
    return True


def _font_size_value(value):
    """px, or the smallest term of a clamp() -- the size at the narrow end."""
    value = (value or "").strip()
    if value.startswith("clamp("):
        value = value[len("clamp("):].split(",")[0]
    return _px(value)


def _font_size_rules(rules):
    """Every font-size declaration as (specificity, source order, selector, px)."""
    flat = []
    for order, (selector, decls) in enumerate(rules):
        size = _font_size_value(decls.get("font-size", ""))
        if size is None:
            continue
        for part in [s.strip() for s in selector.split(",") if s.strip()]:
            flat.append((_specificity(part), order, part, size))
    return flat


def _effective_font_size(node, flat, cache):
    """(px, what set it) for one element, by cascade then inheritance."""
    if id(node) in cache:
        return cache[id(node)]
    inline = re.search(r"font-size:\s*([\d.]+)px", node["attrs"].get("style", ""))
    if inline:
        result = (float(inline.group(1)), "inline style")
    else:
        winner = None
        for spec, order, selector, size in flat:
            if _matches(node, selector) and (winner is None or (spec, order) > winner[0]):
                winner = ((spec, order), size, selector)
        if winner:
            result = (winner[1], winner[2])
        elif node["parent"] is None:
            result = (BODY_FONT_SIZE, "body")
        else:
            result = _effective_font_size(node["parent"], flat, cache)
    cache[id(node)] = result
    return result


@pytest.fixture(scope="module")
def hindi_pages():
    """The same disclosure states as `pages`, served in Hindi."""
    persona = {**PERSONA, "lang": "hi"}
    rendered = {}
    with TestClient(app) as client:
        client.post("/ask", params=persona,
                    data={"question": "क्या मैं "
                                      "दौड़ सकता "
                                      "हूँ?"},
                    follow_redirects=True)
        views = {
            "today": ("/", persona),
            "today-persona-open": ("/", {**persona, "edit": "1"}),
            "today-term-open": ("/", {**persona, "term": "PM2.5"}),
            "city": ("/city", persona),
            "system": ("/system", persona),
            "system-security": ("/system", {**persona, "view": "security"}),
            "guide": ("/guide", persona),
        }
        for name, (path, params) in views.items():
            rendered[name] = client.get(path, params=params).text
        turn = re.search(r'id="turn-([^"]+)"', rendered["today"])
        if turn:
            rendered["today-prov-open"] = client.get(
                "/", params={**persona, "prov": turn.group(1)}).text

    trees = {}
    for name, html in rendered.items():
        parser = _Tree()
        parser.feed(html)
        trees[name] = parser.root
    return trees


def _devanagari_sizes(sheet, hindi_pages, context):
    """Every element on a Hindi page whose own text carries Devanagari, with the
    font-size it resolves to in the given media context."""
    flat = _font_size_rules(sheet["top"] + sheet["media"].get(context, []))
    measured = []
    for name, root in hindi_pages.items():
        cache = {}
        for node in _walk(root):
            if not DEVANAGARI.search(node["text"]):
                continue
            size, why = _effective_font_size(node, flat, cache)
            measured.append((size, why, name, " ".join(node["text"].split())[:40]))
    return measured


def test_no_devanagari_on_any_page_renders_below_the_floor(sheet, hindi_pages):
    """The one test that would have caught the toggles and the trend header.

    The Hindi block declares a size floor and then lists the classes it thought
    of; five that carry translated Devanagari on shipped pages were not on the
    list, and one more was set inline where no `:lang(hi)` rule can reach it. A
    list of class names cannot notice its own omissions, so this walks the
    rendered page instead and resolves what each element actually gets.
    """
    small = []
    for context in ["top"] + sorted(sheet["media"]):
        for size, why, page, text in _devanagari_sizes(sheet, hindi_pages, context):
            if why == "inline style":
                continue            # owned by the assertion below, not this one
            if size + 0.001 < DEVANAGARI_FLOOR:
                small.append(f"{context} {page}: {size}px via {why!r} -- {text!r}")
    assert not small, (
        "Devanagari below the %spx floor:\n  " % DEVANAGARI_FLOOR + "\n  ".join(sorted(set(small))))


def test_the_resolver_can_see_a_size_the_flat_selector_map_cannot(sheet, hindi_pages):
    """A guard on the guard. If the resolver silently stopped matching, the test
    above would pass by measuring nothing -- so prove it resolves real elements,
    and that at least one of them gets its size from a descendant selector that
    `_decls` (which matches whole selectors only) could never have found."""
    measured = _devanagari_sizes(sheet, hindi_pages, "top")
    assert len(measured) > 100, f"only {len(measured)} Devanagari elements resolved"
    assert any(" " in why for _, why, _, _ in measured), (
        "no element resolved through a descendant selector -- the resolver is matching "
        "single classes only and proves less than it appears to")


# Inline `style` attributes outrank every selector, so no `:lang(hi)` rule can
# raise them. These two are the remaining ones, both in today.html, which is not
# this change's file to edit; they are recorded rather than waived so the set can
# only shrink -- an exact match means adding one anywhere fails this suite.
INLINE_FONT_SIZE_DEBT = {
    ("today.html", "font-size:11px;color:var(--text-3)"),
    ("today.html", "font-size:12.5px;color:var(--text-3)"),
}

def test_no_template_carries_an_inline_font_size(sheet, hindi_pages):
    """An inline declaration outranks every selector, `!important` included
    (app.css has none outside the reduced-motion block). A size written there is
    therefore permanently out of reach of the Devanagari floor, whatever the
    stylesheet later says -- which is why the 24-hour trend header could not be
    fixed in CSS at all and had to move out of the template.

    Recorded as an exact set, not a threshold: the debt can only shrink.
    """
    import pathlib
    found = set()
    for path in sorted(pathlib.Path("saafsaans/web/templates").glob("*.html")):
        for match in re.finditer(r'style="([^"]*)"', path.read_text()):
            if re.search(r"\bfont-size\s*:", match.group(1)):
                found.add((path.name, match.group(1)))
    assert found == INLINE_FONT_SIZE_DEBT, (
        "inline font-size in a template, where no :lang(hi) rule can reach it.\n"
        f"  added:   {sorted(found - INLINE_FONT_SIZE_DEBT)}\n"
        f"  removed: {sorted(INLINE_FONT_SIZE_DEBT - found)} (delete it from the debt set)")
    # And the debt is not academic: each entry really does put Devanagari under
    # the floor on a shipped page, which is the reason it is being tracked.
    under = [(size, text) for size, why, _, text in _devanagari_sizes(sheet, hindi_pages, "top")
             if why == "inline style" and size + 0.001 < DEVANAGARI_FLOOR]
    assert under, ("no inline font-size puts Devanagari under the floor any more -- clear "
                   "INLINE_FONT_SIZE_DEBT rather than leaving a dead exemption")


# --- 7. The band ramp as text, not as a swatch ------------------------------
# `.dot` paints --ink as a 9px swatch, where SC 1.4.11's 3:1 is the right floor.
# `.station .bd` paints the SAME token as 11px text, where SC 1.4.3 asks 4.5:1,
# and no test measured it -- so the ramp was tuned once, for the swatch.

BANDS = ("g1", "g2", "g3", "g4", "g5", "g6")
AA_NON_TEXT = 3.0


def _band_backdrops(sheet, pages):
    """Every background a `.station .bd` is actually painted on, as tokens.

    Read off the rendered rows rather than assumed: the selected row used to
    take a fill of its own, and that fill was where the ramp failed worst.
    """
    backgrounds = {}
    for selector, decls in sheet["top"]:
        if "background" in decls and selector.startswith(".station"):
            token = re.fullmatch(r"var\((--[\w-]+)\)", decls["background"].strip())
            if token:
                backgrounds[selector] = token.group(1)
    tokens = {"--surface"}          # .station-list itself
    for root in pages.values():
        for node in _walk(root):
            if "station" not in _classes(node):
                continue
            for selector, token in backgrounds.items():
                attr = re.search(r'\[([\w-]+)="([^"]*)"\]', selector)
                if attr and node["attrs"].get(attr.group(1)) == attr.group(2):
                    tokens.add(token)
    return sorted(tokens)


def test_every_band_word_on_city_clears_the_text_floor_in_both_themes(sheet, pages):
    """The six band words on /city are the ramp used as small text. Measure all
    six, on every background a row is painted on, in both themes -- fixing one
    band by breaking another is the failure mode this guards."""
    css = _strip_comments(sheet["raw"])
    bd = _decls(sheet["top"], ".station .bd")
    assert bd.get("color") == "var(--ink)", (
        ".station .bd no longer paints the band ink -- this test measures the wrong thing")
    size = _px(bd["font-size"])
    assert size < 18.66, f"{size}px would be large text, where the floor is 3:1 not 4.5:1"

    backdrops = _band_backdrops(sheet, pages)
    failures = []
    for theme, block in THEMES:
        for backdrop in backdrops:
            behind = _token(css, block, backdrop)
            for band in BANDS:
                ratio = _ratio(_token(css, block, f"--{band}"), behind)
                if ratio < AA_TEXT:
                    failures.append(f"{theme} .band-{band} .bd on {backdrop}: {ratio:.2f}:1")
    assert not failures, ("band words below the %s:1 text floor:\n  " % AA_TEXT
                          + "\n  ".join(failures))


def test_the_band_dot_stays_above_the_non_text_floor_in_both_themes(sheet):
    """The other half of the same token: the 9px swatch is non-text, so 3:1 is
    the right floor for it -- and raising a band for the text floor must not be
    read as licence to let the swatch drift."""
    css = _strip_comments(sheet["raw"])
    for theme, block in THEMES:
        surface = _token(css, block, "--surface")
        for band in BANDS:
            ratio = _ratio(_token(css, block, f"--{band}"), surface)
            assert ratio >= AA_NON_TEXT, f"{theme} .band-{band} dot: {ratio:.2f}:1"


# --- 8. Every media block is measured ---------------------------------------
# Each block carries the obligation named here, and the set is exact: a new
# `@media` block fails this test until somebody writes down what holds inside it.
MEDIA_OBLIGATIONS = {
    "(max-width: 560px)": "narrower padding only; sizes unchanged, so section 6 applies",
    "(pointer: fine)": "shrinks a target back to the designed density (section 3)",
    "(pointer: coarse)": "raises padding; never lowers it below the top-level value",
    "(prefers-reduced-motion: reduce)": "kills motion and declares nothing else",
}


def test_every_media_block_states_what_holds_inside_it(sheet):
    assert set(sheet["media"]) == set(MEDIA_OBLIGATIONS), (
        "an @media block no assertion covers:\n"
        f"  unmeasured: {sorted(set(sheet['media']) - set(MEDIA_OBLIGATIONS))}\n"
        f"  gone:       {sorted(set(MEDIA_OBLIGATIONS) - set(sheet['media']))}")


def test_the_reduced_motion_block_declares_nothing_but_motion(sheet):
    """It is the one block allowed `!important`. Anything else smuggled in there
    would outrank the whole stylesheet for a reader who asked for less motion."""
    for selector, decls in sheet["media"]["(prefers-reduced-motion: reduce)"]:
        assert set(decls) <= {"transition", "animation"}, (
            f"{selector} declares {sorted(decls)} inside the reduced-motion block")


def test_the_coarse_pointer_block_only_ever_raises_a_target(sheet):
    """The mirror of `test_pointer_fine_only_ever_reduces_a_target`, for the
    block that block's own comment points at. It had no assertion at all."""
    for selector, decls in sheet["media"]["(pointer: coarse)"]:
        if not any(key.startswith("padding") for key in decls):
            continue
        for part in [s.strip() for s in selector.split(",")]:
            top = _decls(sheet["top"], part)
            base = (_edges(top.get("padding"), "y")
                    + (_px(top.get("padding-top", "")) or 0.0)
                    + (_px(top.get("padding-bottom", "")) or 0.0))
            coarse = (_edges(decls.get("padding"), "y")
                      + (_px(decls.get("padding-top", "")) or 0.0)
                      + (_px(decls.get("padding-bottom", "")) or 0.0))
            assert coarse >= base, (
                f"@media (pointer: coarse) gives {part} {coarse}px of vertical padding "
                f"against {base}px at top level -- coarse is the floor, not the ceiling")
