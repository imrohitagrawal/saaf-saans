"""Enterprise UI toolkit: pure functions returning self-contained HTML strings.

Every function here is side-effect free (except ``inject_theme``) and returns a
string ready to hand to ``st.markdown(..., unsafe_allow_html=True)``. The only
external asset is the IBM Plex webfont, requested with ``display=swap`` behind a
full system-font fallback — offline the app renders in system fonts rather than
breaking.

Design language ("SaafSaans" tokens): a warm-neutral canvas, a single deep-teal
accent (#0c6b62) reserved for chrome and interactive affordances, flat surfaces
separated by hairline rules rather than shadows, IBM Plex Mono for every figure,
and the five CPCB AQI category triplets (solid / tint / ink) driving every
air-quality colour. Severity always correlates with contrast-against-background,
so the category ramp inverts its lightness direction between themes. Dark mode is
driven by ``st.context.theme.type`` -- Streamlit's own setting, not the OS
preference -- because the two can disagree, and when they did the cards stayed
white on Streamlit's dark canvas. All
dynamic text is escaped with ``html.escape`` and every function tolerates
missing/None fields without raising, so a half-populated dict from an upstream
failure still renders something sane instead of blowing up the page.
"""
import html

# --- Palette --------------------------------------------------------------
# Every colour lives in the CSS custom properties below. This constant is the
# lone exception: _hex() needs a literal fallback for colours interpolated into
# inline style attributes, where a var() reference would not resolve.
ACCENT = "#0c6b62"          # deep teal — chrome and interactive affordances only


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
# dark media query flips them. Streamlit strips <style> from most
# places but honours it inside st.markdown(unsafe_allow_html=True).
THEME_CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Sans+Condensed:wght@500;600&display=swap');
:root {
  /* neutrals — warm-neutral canvas, shared with the v2 exposure ledger */
  --ss-bg: #fafaf8;
  --ss-card: #ffffff;          /* surface */
  --ss-surface-2: #f2f2ee;     /* nested/inset surface */
  --ss-border: #e2e4e1;
  --ss-border-strong: #c9ccc8;
  --ss-text: #141618;
  --ss-text-2: #5a6167;
  --ss-muted: #8b9299;         /* tertiary / captions */
  /* accent — teal. Chrome and interactive affordances ONLY: teal never means severity. */
  --ss-accent: #0c6b62;
  --ss-accent-hover: #0a564f;
  --ss-accent-tint: #e4efed;
  --ss-on-accent: #ffffff;
  /* CPCB AQI category triplets. v1 encodes CPCB *categories*, so it keeps the
     official hues; the accessibility fix is in the dark block below. */
  --ss-cat-good-solid: #2e7d32;     --ss-cat-good-tint: #e6f0e7;     --ss-cat-good-ink: #1d5220;
  --ss-cat-moderate-solid: #ef6c00; --ss-cat-moderate-tint: #fbeade; --ss-cat-moderate-ink: #8a4503;
  --ss-cat-poor-solid: #c62828;     --ss-cat-poor-tint: #f8e6e5;     --ss-cat-poor-ink: #8f1d1d;
  --ss-cat-vpoor-solid: #7f0000;    --ss-cat-vpoor-tint: #f3e2e1;    --ss-cat-vpoor-ink: #6b0f0f;
  --ss-cat-severe-solid: #4a0000;   --ss-cat-severe-tint: #eee2e1;   --ss-cat-severe-ink: #4a0e0e;
  /* status dots */
  --ss-status-live: #2e7d32;
  --ss-status-mock: #b26a00;
  /* type — IBM Plex, loaded above; system stack is the offline fallback */
  --ss-font-ui: "IBM Plex Sans", -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
  --ss-font-cond: "IBM Plex Sans Condensed", "IBM Plex Sans", -apple-system, sans-serif;
  --ss-font-mono: "IBM Plex Mono", ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  /* radii + elevation — Swiss flatness: hairline rules carry structure, not shadows */
  --ss-r-1: 0px; --ss-r-2: 2px; --ss-r-3: 2px;
  --ss-shadow: none;
  --ss-shadow-md: none;
  --ss-track: #ecece7;
}
/* --- CPCB band context: each class publishes the active triplet as --c-* --- */
.ss-cat-good     { --c-solid: var(--ss-cat-good-solid);     --c-tint: var(--ss-cat-good-tint);     --c-ink: var(--ss-cat-good-ink); }
.ss-cat-moderate { --c-solid: var(--ss-cat-moderate-solid); --c-tint: var(--ss-cat-moderate-tint); --c-ink: var(--ss-cat-moderate-ink); }
.ss-cat-poor     { --c-solid: var(--ss-cat-poor-solid);     --c-tint: var(--ss-cat-poor-tint);     --c-ink: var(--ss-cat-poor-ink); }
.ss-cat-vpoor    { --c-solid: var(--ss-cat-vpoor-solid);    --c-tint: var(--ss-cat-vpoor-tint);    --c-ink: var(--ss-cat-vpoor-ink); }
.ss-cat-severe   { --c-solid: var(--ss-cat-severe-solid);   --c-tint: var(--ss-cat-severe-tint);   --c-ink: var(--ss-cat-severe-ink); }
.ss-cat-unknown  { --c-solid: #9e9e9e; --c-tint: rgba(158,158,158,.15); --c-ink: #5f6b70; }
/* --- card / surface --- */
.ss-card {
  font-family: var(--ss-font-ui);
  background: var(--ss-card);
  border: 1px solid var(--ss-border);
  border-radius: var(--ss-r-3);
  box-shadow: var(--ss-shadow);
  color: var(--ss-text);
  padding: 20px 22px;
  margin: 8px 0;
}
.ss-card * { box-sizing: border-box; }
.ss-hero-num, .ss-kpi-value, .ss-metric-val, .ss-station-aqi, .ss-scale-marker,
.ss-mono { font-variant-numeric: tabular-nums; font-feature-settings: "tnum" 1; }
.ss-card--hero { box-shadow: var(--ss-shadow-md); }
.ss-eyebrow {
  font-size: 11px; letter-spacing: .08em; text-transform: uppercase;
  color: var(--ss-muted); font-weight: 700; margin: 0 0 6px;
}
/* --- accent pill (default chip) --- */
.ss-chip {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; font-weight: 650; line-height: 1;
  padding: 5px 10px; border-radius: 2px;
  background: var(--ss-accent-tint); color: var(--ss-accent);
  border: 1px solid var(--ss-accent-tint);
  font-family: inherit;
}
.ss-chip--muted { background: var(--ss-surface-2); color: var(--ss-text-2); border-color: var(--ss-border); }
.ss-chip--warn { background: var(--ss-cat-moderate-tint); color: var(--ss-cat-moderate-ink); border-color: transparent; }
.ss-chip--danger { background: var(--ss-cat-poor-tint); color: var(--ss-cat-poor-ink); border-color: transparent; }
.ss-chip--stale {
  background: var(--ss-cat-moderate-tint); color: var(--ss-cat-moderate-ink);
  border-color: transparent; font-size: 10px; font-weight: 700; letter-spacing: .06em;
  text-transform: uppercase; padding: 4px 9px;
}
/* --- mono metadata pill --- */
.ss-chip--meta {
  font-family: var(--ss-font-mono); font-size: 11px; font-weight: 500;
  padding: 4px 10px; background: var(--ss-surface-2); color: var(--ss-text-2);
  border: 1px solid var(--ss-border-strong); letter-spacing: 0;
}
/* --- CPCB category chip: tint bg + ink text from --c-* context --- */
.ss-cat-chip {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; font-weight: 700; line-height: 1;
  padding: 5px 10px; border-radius: 2px;
  background: var(--c-tint, var(--ss-surface-2));
  color: var(--c-ink, var(--ss-text-2));
}
/* --- KPI tile --- */
.ss-kpi { display: flex; flex-direction: column; gap: 3px; padding: 16px 18px; }
.ss-kpi-value { font-family: var(--ss-font-mono); font-size: 24px; font-weight: 600; color: var(--ss-text); line-height: 1.1; letter-spacing: -.01em; overflow-wrap: anywhere; }
/* Phrase-valued tiles: UI font, smaller, wraps on word boundaries. */
.ss-kpi-value--text { font-family: var(--ss-font-ui); font-size: 15px; font-weight: 600; line-height: 1.32; letter-spacing: 0; overflow-wrap: normal; }
/* Streamlit renders its own chrome (headings, labels, tabs, widgets) outside
   our .ss-* classes; without this they stay on the stock font and fight the
   injected type system. Icon glyphs keep their own font via higher specificity. */
.stApp, .stApp p, .stApp label, .stApp h1, .stApp h2, .stApp h3, .stApp h4 { font-family: var(--ss-font-ui); }
.stApp code, .stApp pre { font-family: var(--ss-font-mono); }
.ss-kpi-label { font-size: 11px; color: var(--ss-muted); font-weight: 600; text-transform: uppercase; letter-spacing: .07em; }
.ss-kpi-sub { font-size: 12px; color: var(--ss-text-2); }
.ss-kpi-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 10px; }
/* --- AQI hero --- */
.ss-hero-num { font-family: var(--ss-font-mono); font-size: 56px; font-weight: 750; line-height: 1; letter-spacing: -.02em; color: var(--c-solid, var(--ss-text)); }
/* full-scale CPCB bar */
.ss-scale { position: relative; padding-top: 20px; margin: 14px 0 4px; }
.ss-scale-bar { display: flex; height: 8px; overflow: hidden; }
.ss-scale-seg { flex: 1; }
.ss-scale-seg--good     { background: var(--ss-cat-good-solid); }
.ss-scale-seg--moderate { background: var(--ss-cat-moderate-solid); }
.ss-scale-seg--poor     { background: var(--ss-cat-poor-solid); }
.ss-scale-seg--vpoor    { background: var(--ss-cat-vpoor-solid); }
.ss-scale-seg--severe   { background: var(--ss-cat-severe-solid); }
.ss-scale-marker { position: absolute; top: 0; transform: translateX(-50%); font-family: var(--ss-font-mono); font-size: 10px; font-weight: 700; color: var(--ss-text); white-space: nowrap; }
/* legacy single band (kept as thin fallback) */
.ss-band { height: 6px; margin: 12px 0; }
.ss-metrics { display: flex; flex-wrap: wrap; gap: 18px; margin-top: 12px; }
.ss-metric-label { font-size: 11px; color: var(--ss-muted); text-transform: uppercase; letter-spacing: .07em; font-weight: 600; }
.ss-metric-val { font-family: var(--ss-font-mono); font-size: 16px; font-weight: 600; }
/* --- risk gauge --- */
.ss-gauge-track { height: 8px; background: var(--ss-surface-2); border: 1px solid var(--ss-border); overflow: hidden; }
.ss-gauge-fill { height: 100%; }
.ss-drivers { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }
/* --- advice verdict chip (3 states) --- */
.ss-verdict { display: inline-flex; align-items: center; gap: 7px; font-weight: 750; font-size: 12px; letter-spacing: .08em; padding: 6px 13px; border-radius: 2px; }
.ss-verdict::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: currentColor; flex: none; }
.ss-verdict-go { background: var(--ss-cat-good-tint); color: var(--ss-cat-good-ink); }
.ss-verdict-go::before { background: var(--ss-cat-good-solid); }
.ss-verdict-caution { background: var(--ss-cat-moderate-tint); color: var(--ss-cat-moderate-ink); }
.ss-verdict-caution::before { background: var(--ss-cat-moderate-solid); }
.ss-verdict-nogo { background: var(--ss-cat-severe-tint); color: var(--ss-cat-severe-ink); }
.ss-verdict-nogo::before { background: var(--ss-cat-severe-solid); }
.ss-list { margin: 8px 0 0; padding-left: 18px; }
.ss-list li { font-size: 14px; margin: 3px 0; color: var(--ss-text-2); }
.ss-section-label { font-size: 11px; letter-spacing: .07em; text-transform: uppercase; color: var(--ss-muted); font-weight: 700; margin-top: 14px; }
.ss-disclaimer { font-size: 11px; color: var(--ss-muted); margin-top: 14px; font-style: italic; }
.ss-station-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }
.ss-station { padding: 14px 16px; }
.ss-station-name { font-size: 13px; font-weight: 600; color: var(--ss-text); }
.ss-station-aqi { font-family: var(--ss-font-mono); font-size: 22px; font-weight: 750; color: var(--c-solid, var(--ss-text)); }
.ss-dot { display: inline-block; width: 8px; height: 8px; border-radius: 999px; margin-right: 6px; }
.ss-dot--live { background: var(--ss-status-live); }
.ss-dot--mock { background: var(--ss-status-mock); }
.ss-status-row { display: flex; flex-wrap: wrap; gap: 16px; }
.ss-status-item { font-size: 13px; color: var(--ss-text); display: inline-flex; align-items: center; }
.ss-headline { font-size: 15px; font-weight: 600; color: var(--ss-text); margin-top: 8px; }
/* --- calm refusal notice --- */
.ss-refusal { border: 1px solid var(--ss-border); border-radius: var(--ss-r-2); border-top-left-radius: var(--ss-r-1); background: var(--ss-surface-2); padding: 16px 18px; margin: 8px 0; display: flex; gap: 12px; font-family: var(--ss-font-ui); color: var(--ss-text); }
.ss-refusal-icon { width: 26px; height: 26px; border-radius: 50%; background: var(--ss-accent-tint); color: var(--ss-accent); display: inline-flex; align-items: center; justify-content: center; font-size: 14px; font-weight: 700; flex: none; }
.ss-refusal-title { font-size: 13.5px; font-weight: 700; color: var(--ss-text); }
.ss-refusal-body { margin: 4px 0 0; font-size: 13px; color: var(--ss-text-2); }
</style>"""

# Applied on top of THEME_CSS when Streamlit reports a dark theme. Driven by
# st.context.theme.type rather than `prefers-color-scheme`, because the OS
# preference and the theme the user picked in Streamlit can disagree -- and
# when they did, our cards stayed white on Streamlit's dark canvas.
DARK_TOKENS_CSS = """<style>
:root {
  --ss-bg: #0e1113;
  --ss-card: #171b1e;
  --ss-surface-2: #1e2327;
  --ss-border: #272c30;
  --ss-border-strong: #3a4147;
  --ss-text: #f2f4f3;
  --ss-text-2: #a8b0b5;
  --ss-muted: #6e777d;
  --ss-accent: #4fd1c0;
  --ss-accent-hover: #6fdccd;
  --ss-accent-tint: rgba(79,209,192,.14);
  --ss-on-accent: #06231f;
  /* Lightness DIRECTION INVERTS in dark mode: severity must correlate with
     contrast-against-background in BOTH themes. The old values made Severe
     (#7f1d1d on #0e1417) the *least* visible band — the exact opposite of
     what an air-quality scale must do. Mild is now dim, severe is bright. */
  --ss-cat-good-solid: #4e9153;     --ss-cat-good-tint: rgba(78,145,83,.16);   --ss-cat-good-ink: #86bd8b;
  --ss-cat-moderate-solid: #e39b3c; --ss-cat-moderate-tint: rgba(227,155,60,.15); --ss-cat-moderate-ink: #edb96f;
  --ss-cat-poor-solid: #f2685c;     --ss-cat-poor-tint: rgba(242,104,92,.15);  --ss-cat-poor-ink: #f79288;
  --ss-cat-vpoor-solid: #ff8f7a;    --ss-cat-vpoor-tint: rgba(255,143,122,.18); --ss-cat-vpoor-ink: #ffab9c;
  --ss-cat-severe-solid: #ffb4a0;   --ss-cat-severe-tint: rgba(255,180,160,.22); --ss-cat-severe-ink: #ffc8b9;
  --ss-status-live: #66bb6a;
  --ss-status-mock: #e0a04a;
  --ss-shadow: none;
  --ss-shadow-md: none;
  --ss-track: #1e2327;
}
</style>"""


def active_theme() -> str:
    """Return "dark" or "light" as reported by Streamlit, defaulting to light.

    ``st.context.theme`` is documented as possibly inaccurate on the very first
    render of a session, so any failure falls back to the light tokens rather
    than raising.
    """
    import streamlit as st

    try:
        return "dark" if st.context.theme.type == "dark" else "light"
    except Exception:
        return "light"


def inject_theme() -> None:
    """Inject the token system, matching Streamlit's own light/dark theme."""
    import streamlit as st

    st.markdown(THEME_CSS, unsafe_allow_html=True)
    if active_theme() == "dark":
        st.markdown(DARK_TOKENS_CSS, unsafe_allow_html=True)


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
    label, _color_name, _hexcolor = _unpack_category(category)
    cat_cls = _cat_class(label)
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
    pct = _scale_pct(aqi)
    marker = (
        f'<div class="ss-scale-marker" style="left:{pct:.1f}%;">{aqi_txt} &#9662;</div>'
        if pct is not None else ""
    )
    scale_html = (
        f'<div class="ss-scale">{marker}'
        f'<div class="ss-scale-bar">{_SCALE_SEGS}</div></div>'
    )
    return (
        f'<div class="ss-card ss-card--hero {cat_cls}">'
        '<div class="ss-eyebrow">Air Quality Index</div>'
        f'<div style="display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;">'
        f'<span class="ss-hero-num">{aqi_txt}</span>'
        f'<span class="ss-cat-chip">{_esc(label)}</span>'
        f'{stale_pill}'
        '</div>'
        f'{scale_html}'
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
def _is_compact(value) -> bool:
    """True when a KPI value is short enough for the large tabular-mono treatment.

    Short values ("191", "43%", "pm10", "LIVE") read well at 24px mono. Long
    phrases ("Late morning (about 9 AM-12 PM)") overflow the tile and wrap
    mid-word, so they fall back to the UI font one size down. Length is the only
    thing that matters here -- sniffing for digits mislabels "pm10" and "LIVE".
    """
    return 0 < len(str(value or "").strip()) <= 14


def kpi_tile_html(label: str, value, sub: str = None) -> str:
    """A single stat tile: big value, uppercase label, optional sub-line."""
    sub_html = f'<div class="ss-kpi-sub">{_esc(sub)}</div>' if sub else ""
    val = _esc(value) if value is not None and value != "" else "--"
    kind = "" if _is_compact(value) else " ss-kpi-value--text"
    return (
        '<div class="ss-card ss-kpi">'
        f'<div class="ss-kpi-value{kind}">{val}</div>'
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
    label, _color_name, _hexcolor = _unpack_category(category)
    cat_cls = _cat_class(label)
    aqi_txt = _esc(aqi) if aqi is not None else "--"
    stale_pill = (
        ' <span class="ss-chip ss-chip--stale">STALE</span>' if stale else ""
    )
    return (
        f'<div class="ss-card ss-station {cat_cls}">'
        f'<div class="ss-station-name">{_esc(name) or "Station"}</div>'
        f'<div class="ss-station-aqi">{aqi_txt}</div>'
        f'<span class="ss-cat-chip">{_esc(label)}</span>{stale_pill}'
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
        '<div class="ss-refusal">'
        '<div class="ss-refusal-icon" aria-hidden="true">&#10003;</div>'
        '<div>'
        '<div class="ss-refusal-title">Your request was not processed.</div>'
        '<p class="ss-refusal-body">'
        "This assistant focuses on air quality and public health guidance for "
        "Delhi. Please rephrase your question and try again — we're happy "
        "to help.</p>"
        '</div>'
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


# CPCB label -> band key used for the --c-* triplet context classes.
_CAT_KEYS = {
    "Good": "good", "Moderate": "moderate", "Poor": "poor",
    "Very Poor": "vpoor", "Severe": "severe",
}
# Five equal CPCB scale segments, rendered left-to-right.
_SCALE_SEGS = (
    '<div class="ss-scale-seg ss-scale-seg--good"></div>'
    '<div class="ss-scale-seg ss-scale-seg--moderate"></div>'
    '<div class="ss-scale-seg ss-scale-seg--poor"></div>'
    '<div class="ss-scale-seg ss-scale-seg--vpoor"></div>'
    '<div class="ss-scale-seg ss-scale-seg--severe"></div>'
)


def _cat_class(label) -> str:
    """Map a CPCB label to its band context class (falls back to unknown)."""
    key = _CAT_KEYS.get(str(label or "").strip())
    return f"ss-cat-{key}" if key else "ss-cat-unknown"


def _scale_pct(aqi):
    """Marker position on the 0-500 CPCB scale as a clamped percentage, or None."""
    try:
        val = float(aqi)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(100.0, val / 500.0 * 100.0))


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
