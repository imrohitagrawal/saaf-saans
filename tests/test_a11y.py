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
    top, media = _split_media(_strip_comments(_css()))
    return {"top": _rules(top),
            "fine": _rules(media.get("(pointer: fine)", "")),
            "narrow": _rules(media.get("(max-width: 560px)", "")),
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
        self.root = {"tag": "#root", "attrs": {}, "kids": [], "parent": None}
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = {"tag": tag, "attrs": dict(attrs), "kids": [], "parent": self.stack[-1]}
        self.stack[-1]["kids"].append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs if tag in self.VOID else attrs)

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
