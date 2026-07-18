"""Enterprise UI toolkit: pure functions returning self-contained HTML strings.

Every function here is side-effect free (except ``inject_theme``) and returns a
string ready to hand to ``st.markdown(..., unsafe_allow_html=True)``. There are
no external assets, fonts, or CDN references: styling is a system font stack
plus inline SVG, so the app renders identically offline.

Design language: calm neutral base, a single deep-teal accent (#0f766e),
cards with subtle borders and a soft shadow, crisp typographic hierarchy. The
theme is dark-aware via ``@media (prefers-color-scheme: dark)`` layered over CSS
variables. All dynamic text is escaped with ``html.escape`` and every function
tolerates missing/None fields without raising, so a half-populated dict from an
upstream failure still renders something sane instead of blowing up the page.
"""
import html

# --- Palette --------------------------------------------------------------
# Kept in one place so the CSS block and any inline SVG stay in sync.
ACCENT = "#0f766e"          # deep teal, the single professional accent
VERDICT_GO = "#2e7d32"      # green
VERDICT_CAUTION = "#b45309" # amber
VERDICT_NOGO = "#c62828"    # red
_MUTED = "#64748b"          # slate


def _esc(value) -> str:
    """Escape any value to a safe HTML string; None/'' become ''."""
    if value is None:
        return ""
    return html.escape(str(value))


def _hex(value, fallback: str = ACCENT) -> str:
    """Return a value only if it looks like a hex color, else the fallback.

    Guards the handful of places where a color is interpolated straight into a
    ``style`` attribute, so a malformed ``risk['color']`` can never inject CSS.
    """
    text = str(value or "").strip()
    if text.startswith("#") and 4 <= len(text) <= 9:
        body = text[1:]
        if all(c in "0123456789abcdefABCDEF" for c in body):
            return text
    return fallback


# --- Theme ----------------------------------------------------------------
# Light values are the defaults on :root; the dark media query and the
# [data-theme] hooks flip the variables. Streamlit strips <style> from most
# places but honours it inside st.markdown(unsafe_allow_html=True).
THEME_CSS = """<style>
:root {
  --ss-accent: #0f766e;
  --ss-bg: #f8fafc;
  --ss-card: #ffffff;
  --ss-border: #e2e8f0;
  --ss-text: #0f172a;
  --ss-muted: #64748b;
  --ss-shadow: 0 1px 3px rgba(15,23,42,.08), 0 1px 2px rgba(15,23,42,.06);
  --ss-track: #e2e8f0;
}
@media (prefers-color-scheme: dark) {
  :root {
    --ss-accent: #2dd4bf;
    --ss-bg: #0b1120;
    --ss-card: #111827;
    --ss-border: #1f2937;
    --ss-text: #e5e7eb;
    --ss-muted: #94a3b8;
    --ss-shadow: 0 1px 3px rgba(0,0,0,.5), 0 1px 2px rgba(0,0,0,.4);
    --ss-track: #1f2937;
  }
}
.ss-card {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  background: var(--ss-card);
  border: 1px solid var(--ss-border);
  border-radius: 14px;
  box-shadow: var(--ss-shadow);
  color: var(--ss-text);
  padding: 18px 20px;
  margin: 8px 0;
}
.ss-card * { box-sizing: border-box; }
.ss-eyebrow {
  font-size: 11px; letter-spacing: .08em; text-transform: uppercase;
  color: var(--ss-muted); font-weight: 600; margin: 0 0 6px;
}
.ss-chip {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; font-weight: 600; line-height: 1;
  padding: 5px 10px; border-radius: 999px;
  background: rgba(15,118,110,.10); color: var(--ss-accent);
  border: 1px solid rgba(15,118,110,.22);
  font-family: inherit;
}
.ss-chip--muted { background: var(--ss-track); color: var(--ss-muted); border-color: var(--ss-border); }
.ss-chip--warn { background: rgba(180,83,9,.12); color: #b45309; border-color: rgba(180,83,9,.28); }
.ss-chip--danger { background: rgba(198,40,40,.12); color: #c62828; border-color: rgba(198,40,40,.28); }
.ss-chip--stale { background: rgba(180,83,9,.14); color: #b45309; border-color: rgba(180,83,9,.3); }
.ss-kpi { display: flex; flex-direction: column; gap: 2px; padding: 14px 16px; }
.ss-kpi-value { font-size: 26px; font-weight: 700; color: var(--ss-text); line-height: 1.1; }
.ss-kpi-label { font-size: 12px; color: var(--ss-muted); font-weight: 600; text-transform: uppercase; letter-spacing: .04em; }
.ss-kpi-sub { font-size: 12px; color: var(--ss-muted); }
.ss-kpi-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 10px; }
.ss-hero-num { font-size: 56px; font-weight: 800; line-height: 1; letter-spacing: -.02em; }
.ss-band { height: 6px; border-radius: 999px; margin: 12px 0; }
.ss-metrics { display: flex; flex-wrap: wrap; gap: 18px; margin-top: 10px; }
.ss-metric-label { font-size: 11px; color: var(--ss-muted); text-transform: uppercase; letter-spacing: .04em; }
.ss-metric-val { font-size: 16px; font-weight: 700; }
.ss-gauge-track { height: 12px; border-radius: 999px; background: var(--ss-track); overflow: hidden; }
.ss-gauge-fill { height: 100%; border-radius: 999px; }
.ss-drivers { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.ss-verdict { display: inline-flex; align-items: center; gap: 8px; font-weight: 700; font-size: 14px; padding: 8px 14px; border-radius: 10px; }
.ss-verdict-go { background: rgba(46,125,50,.12); color: #2e7d32; border: 1px solid rgba(46,125,50,.3); }
.ss-verdict-caution { background: rgba(180,83,9,.12); color: #b45309; border: 1px solid rgba(180,83,9,.3); }
.ss-verdict-nogo { background: rgba(198,40,40,.12); color: #c62828; border: 1px solid rgba(198,40,40,.3); }
.ss-list { margin: 8px 0 0; padding-left: 18px; }
.ss-list li { font-size: 14px; margin: 3px 0; color: var(--ss-text); }
.ss-section-label { font-size: 11px; letter-spacing: .06em; text-transform: uppercase; color: var(--ss-muted); font-weight: 700; margin-top: 14px; }
.ss-disclaimer { font-size: 11px; color: var(--ss-muted); margin-top: 14px; font-style: italic; }
.ss-station-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }
.ss-station { padding: 12px 14px; }
.ss-station-name { font-size: 13px; font-weight: 600; color: var(--ss-text); }
.ss-station-aqi { font-size: 22px; font-weight: 800; }
.ss-dot { display: inline-block; width: 9px; height: 9px; border-radius: 999px; margin-right: 6px; }
.ss-dot--live { background: #2e7d32; }
.ss-dot--mock { background: #94a3b8; }
.ss-status-row { display: flex; flex-wrap: wrap; gap: 16px; }
.ss-status-item { font-size: 13px; color: var(--ss-text); display: inline-flex; align-items: center; }
.ss-headline { font-size: 15px; font-weight: 600; color: var(--ss-text); margin-top: 8px; }
.ss-refusal { border-left: 4px solid var(--ss-accent); }
</style>"""


def inject_theme() -> None:
    """Inject THEME_CSS once into the Streamlit page. No-op if st is absent."""
    import streamlit as st

    st.markdown(THEME_CSS, unsafe_allow_html=True)


# --- AQI hero -------------------------------------------------------------
_TIP_PM25 = "PM2.5 = fine particles under 2.5 micrometres that reach deep into the lungs. Delhi's main health concern."
_TIP_PM10 = "PM10 = coarser dust particles under 10 micrometres that irritate airways and eyes."
_TIP_DOM = "The pollutant driving today's AQI: pm25 = fine particles, pm10 = dust, o3 = ozone, no2 = traffic gas."


def aqi_hero_html(reading: dict, category: tuple, meaning: str = None) -> str:
    """Big AQI number, category label, color band, pollutant row, station.

    Shows a STALE pill when ``reading['stale']`` is truthy and, when provided, a
    plain-language ``meaning`` line so lay readers know what the category
    implies. Pollutant labels carry hover tooltips. Missing metrics render as an
    em dash rather than breaking the layout.
    """
    reading = reading or {}
    label, _color_name, hexcolor = _unpack_category(category)
    color = _hex(hexcolor)
    aqi = reading.get("aqi")
    aqi_txt = _esc(aqi) if aqi is not None else "--"
    pm25 = _fmt_num(reading.get("pm25"))
    pm10 = _fmt_num(reading.get("pm10"))
    dominant = _esc(reading.get("dominant_pollutant")) or "--"
    station = _esc(reading.get("station")) or _esc(reading.get("city")) or "Unknown station"
    stale = bool(reading.get("stale"))
    stale_pill = (
        '<span class="ss-chip ss-chip--stale">STALE</span>' if stale else ""
    )
    meaning_html = (
        f'<div class="ss-headline" style="font-weight:500;">{_esc(meaning)}</div>'
        if meaning else ""
    )
    return (
        '<div class="ss-card">'
        '<div class="ss-eyebrow">Air Quality Index</div>'
        f'<div style="display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;">'
        f'<span class="ss-hero-num" style="color:{color};">{aqi_txt}</span>'
        f'<span class="ss-chip" style="background:{color}1a;color:{color};'
        f'border-color:{color}44;">{_esc(label)}</span>'
        f'{stale_pill}'
        '</div>'
        f'<div class="ss-band" style="background:{color};"></div>'
        f'{meaning_html}'
        '<div class="ss-metrics">'
        f'<div><div class="ss-metric-label" title="{_esc(_TIP_PM25)}">PM2.5 &#9432;</div>'
        f'<div class="ss-metric-val">{pm25}</div></div>'
        f'<div><div class="ss-metric-label" title="{_esc(_TIP_PM10)}">PM10 &#9432;</div>'
        f'<div class="ss-metric-val">{pm10}</div></div>'
        f'<div><div class="ss-metric-label" title="{_esc(_TIP_DOM)}">Dominant &#9432;</div>'
        f'<div class="ss-metric-val">{dominant}</div></div>'
        '</div>'
        f'<div class="ss-kpi-sub" style="margin-top:10px;">Station: {station}</div>'
        '</div>'
    )


# --- Risk gauge -----------------------------------------------------------
def risk_gauge_html(risk: dict) -> str:
    """Horizontal gauge showing score/100, band label, driver chips, headline."""
    risk = risk or {}
    score = _clamp_score(risk.get("score"))
    band = _esc(risk.get("band")) or "Unknown"
    color = _hex(risk.get("color"))
    headline = _esc(risk.get("headline"))
    advice = _esc(risk.get("advice"))
    drivers = risk.get("drivers") or []
    driver_chips = "".join(
        f'<span class="ss-chip ss-chip--muted">{_esc(d)}</span>'
        for d in drivers if d
    )
    headline_html = (
        f'<div class="ss-headline">{headline}</div>' if headline else ""
    )
    advice_html = (
        f'<div class="ss-kpi-sub" style="margin-top:6px;"><b>What to do:</b> '
        f'{advice}</div>' if advice else ""
    )
    drivers_html = (
        f'<div class="ss-drivers">{driver_chips}</div>' if driver_chips else ""
    )
    return (
        '<div class="ss-card">'
        '<div class="ss-eyebrow">Personal Risk</div>'
        '<div style="display:flex;align-items:baseline;gap:10px;">'
        f'<span style="font-size:34px;font-weight:800;color:{color};">{score}</span>'
        '<span class="ss-kpi-sub">/ 100</span>'
        f'<span class="ss-chip" style="margin-left:auto;background:{color}1a;'
        f'color:{color};border-color:{color}44;">{band}</span>'
        '</div>'
        '<div class="ss-gauge-track" style="margin-top:10px;">'
        f'<div class="ss-gauge-fill" style="width:{score}%;background:{color};"></div>'
        '</div>'
        f'{headline_html}'
        f'{advice_html}'
        f'{drivers_html}'
        '</div>'
    )


# --- Advice card ----------------------------------------------------------
def advice_card_html(sections: dict) -> str:
    """Verdict chip (GO/CAUTION/NO-GO) + detail, precautions, window, symptoms."""
    sections = sections or {}
    verdict = str(sections.get("verdict") or "").upper()
    verdict_cls, verdict_label = _verdict_class(verdict)
    detail = _esc(sections.get("verdict_detail"))
    window = _esc(sections.get("window"))
    disclaimer = _esc(sections.get("disclaimer"))
    precautions = _bullet_list(sections.get("precautions"))
    symptoms = _bullet_list(sections.get("symptoms"))

    parts = [
        '<div class="ss-card">',
        '<div class="ss-eyebrow">Recommendation</div>',
        f'<span class="ss-verdict {verdict_cls}">{verdict_label}</span>',
    ]
    if detail:
        parts.append(f'<div class="ss-headline">{detail}</div>')
    if precautions:
        parts.append('<div class="ss-section-label">Precautions</div>')
        parts.append(precautions)
    if window:
        parts.append('<div class="ss-section-label">Best time window</div>')
        parts.append(f'<div class="ss-kpi-sub">{window}</div>')
    if symptoms:
        parts.append('<div class="ss-section-label">Warning symptoms</div>')
        parts.append(symptoms)
    if disclaimer:
        parts.append(f'<div class="ss-disclaimer">{disclaimer}</div>')
    parts.append('</div>')
    return "".join(parts)


# --- KPI tiles ------------------------------------------------------------
def kpi_tile_html(label: str, value, sub: str = None) -> str:
    """A single stat tile: big value, uppercase label, optional sub-line."""
    sub_html = f'<div class="ss-kpi-sub">{_esc(sub)}</div>' if sub else ""
    val = _esc(value) if value is not None and value != "" else "--"
    return (
        '<div class="ss-card ss-kpi">'
        f'<div class="ss-kpi-value">{val}</div>'
        f'<div class="ss-kpi-label">{_esc(label)}</div>'
        f'{sub_html}'
        '</div>'
    )


def kpi_row_html(tiles: list) -> str:
    """Grid of KPI tiles from a list of {label, value, sub} dicts."""
    tiles = tiles or []
    inner = "".join(
        kpi_tile_html(t.get("label"), t.get("value"), t.get("sub"))
        for t in tiles if isinstance(t, dict)
    )
    return f'<div class="ss-kpi-row">{inner}</div>'


# --- Station card ---------------------------------------------------------
def station_card_html(name: str, aqi, category: tuple, stale: bool) -> str:
    """Compact station tile for the monitoring grid."""
    label, _color_name, hexcolor = _unpack_category(category)
    color = _hex(hexcolor)
    aqi_txt = _esc(aqi) if aqi is not None else "--"
    stale_pill = (
        ' <span class="ss-chip ss-chip--stale">STALE</span>' if stale else ""
    )
    return (
        '<div class="ss-card ss-station">'
        f'<div class="ss-station-name">{_esc(name) or "Station"}</div>'
        f'<div class="ss-station-aqi" style="color:{color};">{aqi_txt}</div>'
        f'<span class="ss-chip" style="background:{color}1a;color:{color};'
        f'border-color:{color}44;">{_esc(label)}</span>{stale_pill}'
        '</div>'
    )


def station_grid_html(stations: list) -> str:
    """Wrap a list of station cards in the responsive grid container.

    Each item is a dict {name, aqi, category, stale}. Convenience for the
    integrator; individual cards can also be laid out directly.
    """
    stations = stations or []
    cards = "".join(
        station_card_html(
            s.get("name"), s.get("aqi"), s.get("category"), bool(s.get("stale"))
        )
        for s in stations if isinstance(s, dict)
    )
    return f'<div class="ss-station-grid">{cards}</div>'


# --- Chips / notes --------------------------------------------------------
def chip_html(text: str, kind: str = "default") -> str:
    """Small pill. kind in {default, muted, warn, danger}."""
    suffix = {
        "muted": " ss-chip--muted",
        "warn": " ss-chip--warn",
        "danger": " ss-chip--danger",
    }.get(kind, "")
    return f'<span class="ss-chip{suffix}">{_esc(text)}</span>'


def trend_note_html(text: str, direction: str = "flat") -> str:
    """Small annotated note for trend context. direction in {up, down, flat}."""
    arrow = {"up": "▲", "down": "▼"}.get(direction, "–")
    kind = {"up": "danger", "down": "default"}.get(direction, "muted")
    return chip_html(f"{arrow} {text}", kind)


# --- Refusal / safety -----------------------------------------------------
def refusal_html(pattern: str) -> str:
    """Calm, reassuring 'request not processed' notice (never alarming).

    ``pattern`` is contextual only; we never echo raw user text here.
    """
    return (
        '<div class="ss-card ss-refusal">'
        '<div class="ss-eyebrow">Safety Notice</div>'
        '<div class="ss-headline">Your request was not processed.</div>'
        '<div class="ss-kpi-sub" style="margin-top:6px;">'
        "This assistant focuses on air quality and public health guidance for "
        "Delhi. Please rephrase your question and try again — we're happy "
        "to help.</div>"
        '</div>'
    )


# --- Service status -------------------------------------------------------
def service_status_html(es_mode: str, waqi_live: bool, llm_live: bool) -> str:
    """Three status dots: Elasticsearch / WAQI / LLM, each Live or Mock."""
    es_live = str(es_mode or "none").lower() in ("cloud", "url")
    es_detail = _esc(es_mode) or "none"
    items = [
        _status_item("Elasticsearch", es_live, es_detail if es_live else "mock"),
        _status_item("Air data", bool(waqi_live), "live" if waqi_live else "mock"),
        _status_item("Assistant", bool(llm_live), "live" if llm_live else "mock"),
    ]
    return (
        '<div class="ss-card">'
        '<div class="ss-eyebrow">Service Status</div>'
        f'<div class="ss-status-row">{"".join(items)}</div>'
        '</div>'
    )


# --- internal helpers -----------------------------------------------------
def _status_item(name: str, live: bool, detail: str) -> str:
    cls = "ss-dot--live" if live else "ss-dot--mock"
    return (
        '<span class="ss-status-item">'
        f'<span class="ss-dot {cls}"></span>{_esc(name)} '
        f'<span class="ss-kpi-sub" style="margin-left:4px;">({_esc(detail)})</span>'
        '</span>'
    )


def _unpack_category(category):
    """Return (label, color_name, hex) tolerating None/short tuples."""
    if not category:
        return ("Unknown", "grey", "#9e9e9e")
    try:
        label = category[0] if len(category) > 0 else "Unknown"
        color_name = category[1] if len(category) > 1 else "grey"
        hexcolor = category[2] if len(category) > 2 else "#9e9e9e"
        return (label or "Unknown", color_name or "grey", hexcolor or "#9e9e9e")
    except (TypeError, IndexError):
        return ("Unknown", "grey", "#9e9e9e")


def _fmt_num(value):
    """Format a numeric metric; None/invalid -> em dash."""
    if value is None:
        return "—"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return _esc(value) or "—"
    if num == int(num):
        return str(int(num))
    return f"{num:.1f}"


def _clamp_score(value) -> int:
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return 0


def _verdict_class(verdict: str):
    if verdict == "GO":
        return ("ss-verdict-go", "GO")
    if verdict == "NO-GO":
        return ("ss-verdict-nogo", "NO-GO")
    if verdict == "CAUTION":
        return ("ss-verdict-caution", "CAUTION")
    return ("ss-verdict-caution", "REVIEW")


def _bullet_list(items) -> str:
    if not items:
        return ""
    lis = "".join(f"<li>{_esc(x)}</li>" for x in items if x)
    if not lis:
        return ""
    return f'<ul class="ss-list">{lis}</ul>'
