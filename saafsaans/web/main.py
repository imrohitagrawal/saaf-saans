"""FastAPI + Jinja2 front end for SaafSaans.

Recreates the approved design in design_handoff_saafsaans/ (v4). The service
layer (waqi / es / llm / guard / risk / forecast / metrics / normalize) is
framework-independent and untouched; this module orchestrates it, and
``presenters`` turns the results into copy and geometry.

Everything is server-rendered and every control is a link or a form, so the
whole app works with JavaScript disabled. Disclosure state (persona editor,
term definitions, provenance panel) rides in the query string rather than in
client state -- which also gives the design's "opening one term closes another"
behaviour for free.

Persona travels in the query string too, so any view is shareable. Only the
chat transcript needs continuity; it is held per session id in memory and never
persisted, because the persona is sensitive and must not reach an index.
"""
import hashlib
import time
import uuid
from collections import OrderedDict, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, Form, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from saafsaans.attack_demo import ATTACKS
from saafsaans.data.advisories import ADVISORIES
from saafsaans.services import (
    aqi_scale, clock, config, cpcb, es, forecast, guard, i18n, llm, metrics,
    normalize, ratelimit, risk, waqi,
)
from saafsaans.web import presenters as pr

BASE = Path(__file__).parent
app = FastAPI(title="SaafSaans")
# Compress responses a client asks to have compressed. The pages are
# server-rendered HTML of 30-60 KB and app.css is ~35 KB, served to phones on
# Delhi mobile networks; gzip takes them to roughly a fifth. woff2 is already
# brotli inside, so the floor spares the tiny responses and gzip merely wastes
# a few cycles on fonts -- correct either way, since the middleware only acts
# on Accept-Encoding.
app.add_middleware(GZipMiddleware, minimum_size=500)


class _ImmutableStatic(StaticFiles):
    """/static with far-future caching.

    Safe because nothing under /static is referenced by a bare name: every URL
    a template emits goes through ``_asset`` below and carries ``?v=<content
    hash>``, so a changed file is a new URL and the year-long lifetime can
    never pin a stale copy. The font files are referenced from inside
    fonts.css without a version, deliberately: their names encode family,
    weight and script, and scripts/build_fonts.py renames on any change of
    meaning, while the referencing stylesheet's hash changes with its content.
    """
    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


app.mount("/static", _ImmutableStatic(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")

# name -> short content hash, filled lazily and held for the process life.
# Static files only change with a deploy, and a deploy restarts the process.
_ASSET_VERSIONS: dict = {}


def _asset(name: str) -> str:
    """``/static/app.css?v=1a2b3c...`` -- the cache key IS the content."""
    version = _ASSET_VERSIONS.get(name)
    if version is None:
        digest = hashlib.sha256((BASE / "static" / name).read_bytes())
        version = _ASSET_VERSIONS[name] = digest.hexdigest()[:12]
    return f"/static/{name}?v={version}"

AGES = ["Child", "Adult", "Senior"]
CONDITIONS = ["Fit", "Asthma", "Heart condition", "Pregnancy", "COPD"]
ACTIVITIES = ["Outdoor exercise", "Commute", "School run", "Stay home"]
TERMS = ["AQI", "PM2.5", "PM10"]
# Derived from the seeded data rather than hand-typed, so a new advisory
# source is glossable the moment it is added here -- not a second edit a
# future author has to remember to make in this file too.
SOURCE_TERMS = sorted({a["source"] for a in ADVISORIES})
# The four suggested-question chips above the ask input. A closed whitelist,
# not free text: /ask is POST-only (a GET that asked a question would spend
# rate-limit budget and call the model on a request meant to be safe and
# bookmarkable), so a chip can only seed the input's value, never submit it,
# and the value it seeds must never be built from anything a reader typed.
ASK_CHIPS = ("outside_now", "mask_today", "best_time", "symptoms")
IST = clock.IST   # one definition, in services/clock.py

# The transcript store holds raw user questions, so leaving it unbounded is a
# privacy exposure as much as a memory leak: every question ever asked of this
# process stays in RAM until the process dies. Both dimensions are capped --
# how many sessions are held, and how many turns each session keeps.
MAX_SESSIONS = 500
MAX_TURNS_PER_SESSION = 20

# sid -> {"turns": deque, "next_id": int}, used as an LRU: reading or writing a
# session moves it to the end, so eviction always drops the session that has
# been idle longest.
_TRANSCRIPTS: "OrderedDict[str, dict]" = OrderedDict()
_client = None


def _session_store(sid: str) -> dict:
    """The transcript record for a session, created on first use.

    ``next_id`` is a monotonic per-session counter rather than ``len(turns)``,
    because the turn deque now drops its oldest entries: with a length-derived
    id, turn 0 would be evicted and the next turn would be numbered 0 again,
    and the provenance links -- which key off the id -- would open the wrong
    turn, or two turns at once.
    """
    store = _TRANSCRIPTS.get(sid)
    if store is None:
        store = {"turns": deque(maxlen=MAX_TURNS_PER_SESSION), "next_id": 0}
        _TRANSCRIPTS[sid] = store
        while len(_TRANSCRIPTS) > MAX_SESSIONS:
            _TRANSCRIPTS.popitem(last=False)
        return store
    _TRANSCRIPTS.move_to_end(sid)
    return store


def read_turns(sid: str) -> list:
    """Turns held for a session, oldest first; empty for an unknown session.

    Reading does not create a session -- otherwise every hit on Today from a
    forged or expired cookie would allocate a store entry, which is the growth
    this cap exists to stop.
    """
    store = _TRANSCRIPTS.get(sid)
    if store is None:
        return []
    _TRANSCRIPTS.move_to_end(sid)
    return list(store["turns"])


def add_turn(sid: str, turn: dict) -> dict:
    """Append a turn, stamping it with an id unique for the life of the session."""
    store = _session_store(sid)
    turn["id"] = str(store["next_id"])
    store["next_id"] += 1
    store["turns"].append(turn)
    return turn


def get_client():
    """One Elasticsearch client per process (or None in mock mode)."""
    global _client
    if _client is None:
        _client = es.get_client()
    return _client


# --- request state ---------------------------------------------------------
def read_persona(request: Request) -> dict:
    q = request.query_params

    def pick(key, options, default):
        value = q.get(key)
        return value if value in options else default

    return {
        "locality": pick("locality", waqi.LOCALITIES, "Anand Vihar"),
        "age": pick("age", AGES, "Adult"),
        "condition": pick("condition", CONDITIONS, "Asthma"),
        "activity": pick("activity", ACTIVITIES, "Outdoor exercise"),
    }


def persona_applied(request: Request) -> bool:
    """True once the visitor has chosen a persona; False on a first visit.

    The persona travels in the query string and nowhere else, so "chosen" is
    detectable without any client state: a first visit arrives with no persona
    parameter at all, and every link the first-visit page emits keeps it that
    way (``base_context`` builds its query strings from an empty persona until
    this is True). The first Apply -- the persona form, which submits all four
    fields -- is what flips it.

    ALL FOUR fields, each with a VALUE THE FORM COULD HAVE SUBMITTED.
    ``read_persona`` silently swaps a missing or invalid value for its
    default, so anything less re-opens the claim this predicate exists to
    prevent: ``any(...)`` meant a hand-truncated ``/?age=Child`` -- one valid
    field, the other three defaulting, Asthma included -- still earned "YOUR
    RISK". ``all`` costs no legitimate state: the form submits all four fields
    and every link the site emits carries all four or none.
    """
    q = request.query_params
    checks = {"locality": waqi.LOCALITIES, "age": AGES,
              "condition": CONDITIONS, "activity": ACTIVITIES}
    return all(q.get(key) in options for key, options in checks.items())


def read_theme(request: Request) -> str:
    value = request.query_params.get("theme") or request.cookies.get("theme")
    return "dark" if value == "dark" else "light"


def read_lang(request: Request) -> str:
    """The language for this request: ``?lang=`` first, then the cookie.

    Same shape as ``read_theme`` deliberately -- language is page state exactly
    as theme is, so it travels in the query string (every view stays
    shareable in the language it was read in) and is remembered in a cookie
    (so a reader who switched once does not switch again on every visit).
    ``i18n.normalise`` turns anything unrecognised into English rather than
    into a half-rendered page.
    """
    value = request.query_params.get("lang") or request.cookies.get("lang") or ""
    return i18n.normalise(value)


def _translator(lang: str):
    """``T(group, key, english)`` bound to this request's language.

    Handed to the templates so the copy stays where a reader of the template
    can see it: the English is written inline as the fallback argument, and the
    Hindi -- when there is one -- replaces it. A missing translation therefore
    renders the English that is right there in the markup.
    """
    def T(group: str, key: str, english: str) -> str:
        return i18n.t(lang, group, key, english)
    return T


def _option_labels(lang: str) -> dict:
    """Display text for every persona option, keyed by the value it submits.

    The keys stay English because they are the wire format: ``read_persona``
    validates against AGES / CONDITIONS / ACTIVITIES, the query string carries
    them, and ``normalize`` maps them to scoring keywords. Only what the reader
    sees is translated, so a Hindi page's persona editor still round-trips.

    Written out one literal key at a time rather than composed from the option
    name, because tests/test_i18n.py reads the requested keys back out of this
    file: a key built by concatenation is invisible to that parser, and an
    invisible key is one nobody notices is missing.
    """
    return {
        "Child": i18n.t(lang, "ui", "age_child", "Child"),
        "Adult": i18n.t(lang, "ui", "age_adult", "Adult"),
        "Senior": i18n.t(lang, "ui", "age_senior", "Senior"),
        "Fit": i18n.t(lang, "ui", "cond_fit", "Fit"),
        "Asthma": i18n.t(lang, "ui", "cond_asthma", "Asthma"),
        "Heart condition": i18n.t(lang, "ui", "cond_heart", "Heart condition"),
        "Pregnancy": i18n.t(lang, "ui", "cond_pregnancy", "Pregnancy"),
        "COPD": i18n.t(lang, "ui", "cond_copd", "COPD"),
        "Outdoor exercise": i18n.t(lang, "ui", "act_outdoor_exercise",
                                   "Outdoor exercise"),
        "Commute": i18n.t(lang, "ui", "act_commute", "Commute"),
        "School run": i18n.t(lang, "ui", "act_school_run", "School run"),
        "Stay home": i18n.t(lang, "ui", "act_stay_home", "Stay home"),
    }


def _advisory_translator(lang: str):
    """``advisory_text(doc)`` for a seeded advisory, translated when possible.

    The seeded advisories carry no id, so the key is composed from the five
    fields that together identify one: source, AQI band, and the persona triple.
    The persona fields are not optional. Source plus band alone collides --
    "WHO-AQG-2021:201-300" and "AHA-airpollution:201-300" each match two
    different seeded rows -- and a colliding key would serve one persona's
    health instruction under another persona's name, which is the worst
    available failure for this particular string. i18n.py documents the same
    rule and a test there fails the build if a future row collides.

    Any key with no translation falls back to the English on the document.
    """
    def advisory_text(doc: dict) -> str:
        key = (f"{doc.get('source')}:{doc.get('aqi_min')}-{doc.get('aqi_max')}"
               f":{doc.get('condition')}:{doc.get('activity')}:{doc.get('age_group')}")
        return i18n.t(lang, "advisory", key, doc.get("advice") or "")
    return advisory_text


def session_id(request: Request) -> str:
    """The chat-transcript key: the client's ``sid`` cookie when it is in the
    exact form this server issues, otherwise a fresh id.

    The cookie is deliberately NOT signed. Signing would mean owning a secret
    (generated, stored, rotated, and shared across processes) to protect a key
    that unlocks nothing but an in-memory chat transcript which is never
    persisted and is evicted within MAX_SESSIONS sessions. The cheaper check
    below removes the concrete defect -- an attacker choosing the key -- at no
    operational cost.

    What this DOES prevent: an arbitrary client-chosen key. The value must
    parse as a UUID, be version 4, and render back byte-for-byte in canonical
    lowercase form, so 'admin', a 10 MB string, and the brace/URN spellings of
    the same uuid are all rejected in favour of a new id. That bounds the key
    space to values the server could have issued and stops one client inflating
    the store with keys of its choosing.

    What this does NOT prevent: anyone who guesses or steals a real issued
    uuid4 still reads that session's transcript. Guessing is not a practical
    attack (122 random bits), but theft -- a shared device, a copied cookie --
    is not defended against here at all. Signing would not defend against theft
    either; only server-side authentication would.
    """
    raw = request.cookies.get("sid") or ""
    try:
        parsed = uuid.UUID(raw)
    except (ValueError, AttributeError, TypeError):
        return str(uuid.uuid4())
    if parsed.version != 4 or str(parsed) != raw:
        return str(uuid.uuid4())
    return raw


def _share_card(lang: str = "en") -> dict:
    """Default Open Graph / Twitter card text, for views with no reading.

    City Pulse, System and the Guide show no single reading, so their card
    describes the site and claims nothing about the air. Today overrides this
    with text built from the reading it is rendering.
    """
    return {
        "title": i18n.t(lang, "ui", "share_site_title",
                        "SaafSaans — Delhi air, explained for your body"),
        "description": i18n.t(lang, "ui", "share_site_desc",
                              "See what the air in your area of Delhi means for "
                              "you today, in plain language."),
    }


def today_share_card(persona: dict, data: dict, verdict: str,
                     label: str = None, lang: str = "en") -> dict:
    """Card text for Today, built from the very values the page renders.

    ``data`` and ``verdict`` are the same objects passed to the template, so
    the forwarded card and the opened page cannot disagree -- which is the
    whole reason this is not composed from a second lookup.

    Plain language only: no index number, no micrograms. When the feed carries
    no particulate the reading is None; the card then says the reading is
    missing and repeats the page's own advice for that case, rather than
    naming a band it does not have.

    Fully translated, scaffolding included. It was not: the verdict arrived in
    Hindi and the sentence around it stayed English, so a forwarded Hindi link
    previewed as half a sentence in each language. That mattered more than its
    size -- the research in this repository found distribution in Indian
    households runs through forwards, so this card is the first thing most
    readers would ever see, and it lives in <head> where the completeness scan
    was not looking.
    """
    label_en = data["category"][0]
    label = label or label_en
    # The forwarded card is read by the same person as the page.
    place = i18n.place(lang, persona["locality"])
    # Checked BEFORE the no-reading branch, which the neutralised category
    # would otherwise capture: "no air reading right now" is false when a
    # number is printed on the page the card links to. The card names no band
    # for the same reason the hero does not -- it is not the air now -- and
    # this is the surface that mattered most, because a forwarded card is the
    # first thing most readers ever see and it used to preview a held reading
    # as "{place} air right now: Very Poor".
    if (data["reading"].get("aqi") is not None
            and data["reading"].get("retained")):
        return {"title": i18n.t(lang, "ui", "share_held",
                                "{place}: we are holding an earlier air "
                                "reading").replace("{place}", place),
                "description": data["meaning"]}
    if data["reading"].get("aqi") is None or label_en == "Unknown":
        return {"title": i18n.t(lang, "ui", "share_no_reading",
                                "{place}: no air reading right now").replace("{place}", place),
                "description": data["meaning"]}
    who = pr.persona_sentence(persona, with_place=False, lang=lang)
    # There is no longer a "(sample)" variant of this card, and that is a
    # strengthening rather than a removal. The variant existed because a
    # fallback used to arrive carrying a band derived from a hardcoded
    # concentration, so the card had to hedge a severity word it should never
    # have been given. A fallback now carries no AQI at all, so it is caught by
    # the no-reading branch above and the card names no band -- the hedge is
    # unreachable because the thing it hedged cannot be built.
    # "today", not "right now": ADR 0005 measured CPCB's avg_value to be a
    # rolling 24-hour mean, and this card names the band worked out from it.
    title = i18n.t(lang, "ui", "share_title", "{place} air today: {band}")
    return {
        "title": title.replace("{place}", place).replace("{band}", label),
        # The place is already in the title, so the persona phrase drops it.
        "description": verdict + " " + i18n.t(lang, "ui", "share_for",
                                              "This is for {who}.").replace("{who}", who),
    }


def _qs(persona: dict, theme: str, lang: str, **extra) -> str:
    """Query string carrying persona + theme + language, plus disclosure state.

    ``lang`` is positional and required rather than defaulted, so a new link
    cannot silently omit it: a link without the language returns a Hindi reader
    to English the moment they click anything.

    Keys with a None value are dropped, which is how a disclosure link closes
    what is currently open.
    """
    params = {**persona, "theme": theme, "lang": lang}
    params.update(extra)
    return urlencode({k: v for k, v in params.items() if v is not None})


def base_context(request: Request, persona: dict, theme: str, lang: str,
                 active: str) -> dict:
    # Until the visitor applies a persona, every link the page emits carries
    # theme and language ONLY. The alternative -- building links from the
    # default persona -- meant the very first click (the theme toggle, the
    # Hindi toggle, any nav link) wrote Adult/Asthma into the query string and
    # turned the example into "YOUR" without the visitor ever choosing it.
    applied = persona_applied(request)
    qp = persona if applied else {}
    return {
        "request": request, "persona": persona, "theme": theme, "active": active,
        "lang": lang,
        "asset": _asset,
        "persona_applied": applied,
        # Opens the persona editor from ANY page: the Hindi banner's path in
        # base.html points here, and /city, /system and /guide render that
        # banner too.
        "q_edit": _qs(qp, theme, lang, edit="1"),
        "path": request.url.path,
        "ages": AGES, "conditions": CONDITIONS, "activities": ACTIVITIES,
        # value -> what the reader sees. The values above stay English because
        # they are what the form submits and what read_persona validates.
        "option_label": _option_labels(lang),
        # The picker's option VALUE stays English (it is the FEED_MAP key and
        # the query parameter); only what the reader sees is translated.
        "place": lambda name: i18n.place(lang, name),
        "regions": waqi.REGIONS,
        "share": _share_card(lang),
        "q": _qs(qp, theme, lang),
        "q_light": _qs(qp, "light", lang),
        "q_dark": _qs(qp, "dark", lang),
        # The toggle keeps everything else about the page identical, so a
        # reader switching language does not also lose their persona or theme.
        "q_en": _qs(qp, theme, "en"),
        "q_hi": _qs(qp, theme, "hi"),
        # Shown on every Hindi page. Not a template literal: the wording of a
        # caveat about unreviewed health copy belongs beside the copy it is
        # about.
        "review_banner": i18n.REVIEW_BANNER,
        "review_banner_en": i18n.REVIEW_BANNER_EN,
        "T": _translator(lang),
        "advisory_text": _advisory_translator(lang),
        "pct": pr.pct,
        "pos": pr.pos_class,
        "pollutant": pr.pollutant_label,
        # The footer names the primary source on every page, so the host comes
        # from the module that owns it rather than from a template literal.
        "cpcb_host": cpcb.SOURCE_HOST,
        # The footer names the sources on EVERY page, so it must name the ones
        # this deployment actually has. Read from the same predicates /health
        # reports, not from a second pair, so the page and the health endpoint
        # cannot disagree about which sources exist.
        "source_cpcb": config.cpcb_available(),
        "source_waqi": config.waqi_available(),
    }


def _fmt_time(iso: str = None, lang: str = "en") -> str:
    """'2:00 PM' in IST, or a phrase saying there is no observation time.

    It used to fall back to ``now``, which printed the page-load clock in the
    slot where a reading's own timestamp goes -- so a sample with no
    observation time looked like a measurement taken this minute, and the
    number changed on every refresh. The fallback reading has no observation
    time by definition (``waqi._fallback`` sets it to None), which is the
    configuration the app ships in, so this was the normal case rather than
    the edge one.
    """
    dt = None
    if iso:
        try:
            dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        except ValueError:
            dt = None
    if dt is None:
        return i18n.t(lang, "ui", "no_obs_time", "no reading time")
    return dt.astimezone(IST).strftime("%-I:%M %p")


# --- Today -----------------------------------------------------------------
def advisor_data(persona: dict, lang: str = "en") -> dict:
    """The reading and everything derived from it, in the reader's language.

    ``lang`` defaults to English so the signature stays compatible with every
    existing caller; the services it calls carry the same default, so a missing
    translation degrades to English one string at a time rather than raising.
    """
    reading, waqi_status = waqi.get_aqi(persona["locality"], es_client=get_client())
    aqi = reading.get("aqi")
    return {
        "reading": reading, "waqi_status": waqi_status,
        "category": normalize.aqi_category(aqi),
        "band": normalize.band_slug(aqi),
        "meaning": normalize.aqi_meaning(normalize.aqi_category(aqi)[0]),
        "risk": risk.compute_risk(
            aqi, normalize.norm_condition(persona["condition"]),
            normalize.norm_activity(persona["activity"]),
            normalize.norm_age(persona["age"]), lang=lang),
        # Same air, same plans, healthy adult body -- the gap is the whole point.
        # The baseline is a bare number, so it needs no language.
        "baseline": risk.compute_risk(
            aqi, "any", normalize.norm_activity(persona["activity"]), "adult")["score"],
        "window": forecast.best_window(
            # The feed's own dominant pollutant, which may be a gas the app's
            # particulate-only index does not model. The window advice differs
            # for ozone, so it must not be told "pm25" merely because PM drove
            # our number.
            aqi, dominant_pollutant=(reading.get("feed_dominant")
                                     or reading.get("dominant_pollutant")),
            forecast=reading.get("forecast"), lang=lang),
        "outlook": pr.outlook_rows(
            forecast.daily_outlook(reading.get("forecast"), lang=lang), lang=lang),
    }


@app.get("/")
def today(request: Request):
    persona = read_persona(request)
    theme = read_theme(request)
    lang = read_lang(request)
    sid = session_id(request)
    q = request.query_params

    ctx = base_context(request, persona, theme, lang, "today")
    data = advisor_data(persona, lang)

    # THREE STATES, not two, and the same three /city has shown since 88ef869.
    #
    # `has_reading` is "there is a number". `is_current` is "that number is the
    # air now", which is what every severity claim on this page rests on: the
    # band word, the colour ramp, the risk score, the band advice, the scale
    # marker and the forwarded card. A HELD reading -- real numbers we already
    # fetched, re-served because the upstream stopped answering -- has the
    # first and not the second.
    #
    # It was rendered with the full hero: band-g5, "AQI 369 - VERY POOR",
    # "YOUR RISK - 91/100 - EXTREME" and "Do not go outdoors", beside a chip
    # reading CACHED -- while /city gave the identical reading in the same
    # minute a grey band-less tile with no band word, and the Guide told the
    # reader that nothing is worked out from a held reading. Two pages of one
    # app disagreeing about a measurement is the defect /city was rewritten to
    # remove; it survived here because this route never consulted freshness.
    fresh = pr.freshness(data["waqi_status"], data["reading"])
    has_reading = data["reading"].get("aqi") is not None
    is_current = has_reading and fresh == "live"
    if has_reading and not is_current:
        # Neutralised at the source, so every consumer of `band` and
        # `category` -- hero, reading card, share card -- is corrected once
        # rather than each branching for itself, which is how the collapsed
        # provenance label and the expanded line came to disagree already.
        # `reading` is untouched: the number and its observation time are
        # facts, and they still render.
        data["band"] = normalize.band_slug(None)
        data["category"] = normalize.aqi_category(None)
    ctx.update(data)

    applied = ctx["persona_applied"]
    # The disclosure links must not smuggle the default persona into the query
    # string before the visitor has chosen one; same rule as base_context.
    qp = persona if applied else {}
    term = q.get("term") if q.get("term") in TERMS + SOURCE_TERMS else None
    ask = q.get("ask") if q.get("ask") in ASK_CHIPS else None
    # Four literal calls, not a key built from `ask`: the i18n coverage tests
    # scan call sites by AST, so a dynamically-assembled key would be both
    # unreadable to that scan and untranslatable to Hindi.
    if ask == "outside_now":
        ask_seed = i18n.t(lang, "ui", "ask_chip_outside_now",
                          "Is it safe to go outside right now?")
    elif ask == "mask_today":
        ask_seed = i18n.t(lang, "ui", "ask_chip_mask_today",
                          "Should I wear a mask today?")
    elif ask == "best_time":
        ask_seed = i18n.t(lang, "ui", "ask_chip_best_time",
                          "What is the best time to go out today?")
    elif ask == "symptoms":
        ask_seed = i18n.t(lang, "ui", "ask_chip_symptoms",
                          "What symptoms mean I should go back inside?")
    else:
        ask_seed = ""
    # Open by DEFAULT on a first visit: until the visitor has applied a
    # persona, the editor is the page's primary element -- the advice above it
    # is an example's, and the form is how it becomes theirs. ``edit=0`` is the
    # explicit close for that state (a bare ``edit`` absent means "default",
    # which is open only while no persona is applied).
    persona_open = q.get("edit") == "1" or (not applied and q.get("edit") != "0")
    obs_time = _fmt_time(data["reading"].get("obs_time"), lang)
    # What the provenance chip prints after the state word. A live reading is
    # dated by its clock time; a HELD one has to be dated by its AGE, because the
    # clock time alone is what let three weeks read as minutes. See the chip's
    # entry in the context below.
    _held_age = _age_label(data["reading"].get("obs_time"), lang) if fresh == "held" else ""
    _chip_when = (f"{_held_age} " + i18n.t(lang, "ui", "tag_old", "OLD")
                  if _held_age else obs_time)

    # Newest first, and the whole history: a user tracking a decision needs to
    # re-read what they already asked, not have it replaced by the next answer.
    turns = list(reversed(read_turns(sid)))
    open_prov = q.get("prov")
    band = data["risk"]["band"]
    # The verdict is the single largest health directive on the site, and every
    # one of the five band verdicts is a claim about the air ("this air is
    # dangerous for you"). With no reading there is no air to make a claim
    # about, so the headline names the absence instead. It used to inherit the
    # verdict for whatever band the unknown-AQI base score happened to land in,
    # which is how a place the app had never measured got told its lungs needed
    # it indoors today.
    verdict = (i18n.t(lang, "verdict", band, pr.verdict_for(band)) if is_current
               else (pr.held_verdict(persona["locality"], lang=lang) if has_reading
                     else pr.no_reading_verdict(persona["locality"], lang=lang)))
    ctx["has_reading"] = has_reading
    ctx["is_current"] = is_current
    # With no live reading, say what we DID last see and when -- the owner
    # decision, and the only honest thing left to put in that space. It is a
    # real measurement with its own date attached, so it is a fact rather than
    # a stand-in. It is printed as a number and a date and nothing else: no
    # band word, no colour, no advice. A reading from three weeks ago must not
    # tell anybody what to do today.
    ctx["last_real"] = (None if has_reading
                        else _last_real_reading(persona["locality"], lang))
    # The band label and the meaning are translated here rather than in the
    # template because the share card is built from them too, and the card must
    # not name a band in a language the page does not use.
    band_label = i18n.t(lang, "band_label", data["category"][0], data["category"][0])
    # `meaning` is the one severity claim the neutralise block above cannot
    # correct at its source: it is prose, so it is translated here, and
    # `aqi_meaning` is keyed by CATEGORY. Neutralising the category alone left a
    # held reading broken in ENGLISH ONLY -- i18n.t returns its fallback for any
    # lang != "hi", and that fallback is the meaning computed from the REAL aqi
    # at _page_data. A three-hour-held reading of 40 printed "Air is clean.
    # Outdoor activity is fine for everyone." four elements below a hero
    # promising no band, no colour, no risk score and no window. Hindi has a
    # real aqi_meaning["Unknown"] and took the safe branch, so the reviewed
    # language was the unsafe one, and the error direction was UNDER-warning on
    # a page an asthmatic reader is using to decide whether to go out.
    #
    # Not recomputed as aqi_meaning("Unknown") either: that says the reading is
    # "unavailable right now" directly beside a printed number, which is the
    # self-contradiction hero.held exists to avoid. It gets its own string, the
    # way advice_held and risk_held do.
    if has_reading and not is_current:
        data["meaning"] = i18n.t(
            lang, "ui", "meaning_held",
            "This is what the air was when it was last measured here, not what "
            "it is now. Nothing about how safe it is has been worked out from "
            "it.")
    else:
        data["meaning"] = i18n.t(lang, "aqi_meaning", data["category"][0],
                                 data["meaning"])
    ctx["meaning"] = data["meaning"]

    ctx.update({
        "verdict": verdict,
        "band_label": band_label,
        # Built from `data` and `verdict` themselves, so a forwarded link's
        # preview cannot say something the page does not.
        "share": today_share_card(persona, data, verdict, band_label, lang=lang),
        "kicker": pr.persona_kicker(persona, lang=lang),
        "persona_line": pr.persona_line(persona, lang=lang),
        "compare": pr.comparison_line(data["risk"]["score"], data["baseline"],
                                      persona, lang=lang),
        "scale_pos": pr.scale_position(data["reading"].get("aqi")),
        # A held reading's chip carried _fmt_time alone -- a bare clock time --
        # so a measurement 21 days old rendered "◌ CACHED · 5:26 PM" at 5:26 PM
        # and read as minutes old. The one surface whose whole job is to date the
        # number was the one that did not. guide.html promises "we tell you what
        # it was AND when it was taken", and City Pulse already prints
        # "CACHED · 13 H OLD" for this exact state -- so the reader has learnt
        # that vocabulary on the other page and must not meet a different one
        # here. Same argument provenance_chip's own docstring makes about the
        # word CACHED.
        #
        # _age_label and ui.tag_old are both already translated, so no new copy.
        # Falls back to the clock time when the age cannot be established:
        # "· OLD" with nothing in front of it says less than a time does.
        "prov_chip": pr.provenance_chip(
            data["waqi_status"], _chip_when, lang=lang, state=fresh),
        # The templates call this per stored turn, so a turn indexed before the
        # field existed answers "live"/"none" exactly as it did before.
        "freshness": pr.freshness,
        # A turn stores the persona FACTS and this composes the "Answered for"
        # sentence in the page's language at render time -- the sentence is
        # chrome, not stored copy, so it must not be frozen in the language the
        # question happened to be asked in. A turn from before the facts were
        # stored has only its rendered persona_line; that renders unchanged,
        # and the template still marks it with the turn's own language.
        "turn_persona_line": lambda t: (pr.persona_line(t["persona"], lang=lang)
                                        if t.get("persona")
                                        else t.get("persona_line", "")),
        # Says which particulates the index was actually worked out from. The
        # caption used to claim both, unconditionally, over a reading that can
        # be built from one.
        "scale_note": pr.scale_note(data["reading"], lang),
        "prov_scale_note": lambda reading: pr.prov_scale_note(reading, lang),
        "obs_time": obs_time,
        "glossary": normalize.GLOSSARY,
        "term": term, "persona_open": persona_open,
        "transcript": turns, "open_prov": open_prov,
        "condition_help": normalize.condition_help(persona["condition"]),
        "conditions_help": normalize.CONDITION_HELP,
        # The score is half published figure and half the author's judgement.
        # Saying so next to the number is the point; saying it only in the
        # README would repeat the mistake this project exists to record.
        "risk_notice": i18n.t(lang, "ui", "risk_notice", risk.HEURISTIC_NOTICE),
        # has_index keys off the INDEX, not off a reading dict existing:
        # waqi._fallback always returns a full dict, so "a reading exists"
        # would print the explanation on every NO READING page in both
        # languages.
        # Suppressed entirely on a held reading, not reworded. Every surviving
        # branch is present tense about the air ("The air here is about at...",
        # and the PM10-only branch says a station "is not reporting them right
        # now"), which is a live claim over a measurement taken hours ago. The
        # hero already withholds band, colour, score and window from a held
        # reading; this was the one severity-adjacent sentence still speaking in
        # the present. `has_index` alone does not do it: it gates only the
        # PM10-only branch, so the main comparison printed regardless.
        "who_line": (pr.who_line(data["reading"].get("pm25"), lang=lang,
                                 has_index=True) if is_current else ""),
        # Each link toggles its own disclosure and clears the others. Closing
        # needs an explicit edit=0 on a first visit, where absence means open.
        "q_persona_toggle": _qs(qp, theme, lang,
                                edit=(("0" if not applied else None)
                                      if persona_open else "1")),
        # Provenance opens per turn, so history stays independently inspectable.
        "q_prov": lambda tid: _qs(qp, theme, lang,
                                  prov=None if open_prov == tid else tid),
        "q_term_aqi": _qs(qp, theme, lang, term=None if term == "AQI" else "AQI"),
        "q_term_pm25": _qs(qp, theme, lang, term=None if term == "PM2.5" else "PM2.5"),
        "q_term_pm10": _qs(qp, theme, lang, term=None if term == "PM10" else "PM10"),
        # One parameterized helper for all eleven source codes, matching
        # q_prov(tid) above, rather than eleven more fixed q_term_* keys.
        # Takes tid too, and always sends prov=tid: the pill lives inside the
        # provenance panel, and a link that dropped prov closed that panel out
        # from under the def-slot it was meant to open.
        "q_term_source": lambda src, tid: _qs(qp, theme, lang,
                                              term=None if term == src else src,
                                              prov=tid),
        "ask": ask, "ask_seed": ask_seed,
        "q_ask_outside_now": _qs(qp, theme, lang, ask="outside_now"),
        "q_ask_mask_today": _qs(qp, theme, lang, ask="mask_today"),
        "q_ask_best_time": _qs(qp, theme, lang, ask="best_time"),
        "q_ask_symptoms": _qs(qp, theme, lang, ask="symptoms"),
    })
    return _render(request, "today.html", ctx, sid, theme, lang)


@app.post("/ask")
def ask(request: Request, question: str = Form(...)):
    """Guard -> retrieve -> answer, then redirect so a refresh cannot resubmit."""
    persona = read_persona(request)
    theme = read_theme(request)
    lang = read_lang(request)
    sid = session_id(request)
    client = get_client()

    hashed = normalize.session_hash(sid)

    # Before any work is done. This endpoint writes telemetry, may write a
    # security event, and calls a paid model when a key is configured, and it
    # is unauthenticated by design -- asking someone to register before they
    # may ask whether the air is safe would defeat the point of the app. The
    # limit is sized to stop a loop, not to ration a person.
    allowed, retry_after = ratelimit.check(
        f"ask:{ratelimit.client_key(request)}",
        ratelimit.ASK_LIMIT, ratelimit.ASK_WINDOW)
    if not allowed:
        # Shown as a turn in the thread, like a refusal, so the answer appears
        # where the reader was already looking. Nothing is logged: a
        # rate-limit trip is not a security event, and writing one per blocked
        # request would hand the flooder the very index this protects.
        # Every stored turn is stamped with the language it was composed in.
        # The transcript outlives the page state that made it: a reader who
        # asked in English and then switched to Hindi replays English turns on
        # a page whose <html lang="hi"> claims them as Hindi -- wrong for a
        # screen reader's phonetics and for the :lang(hi) floors alike -- so
        # the template marks a turn whose stamp differs from the page.
        # The persona FACTS, not the rendered sentence. The "Answered for" line
        # is composed from these at display time in the page's own language, so
        # a turn asked in English reads in Hindi on the Hindi page -- unlike the
        # answer body, which is stored copy and keeps its lang stamp. A turn
        # stored before this field existed carries only its old persona_line,
        # and the template renders that, marked, exactly as it did.
        add_turn(sid, {"kind": "throttled", "lang": lang,
                       "question": normalize.excerpt(question),
                       "minutes": max(1, (retry_after + 59) // 60),
                       "persona": dict(persona)})
        return _back(request, sid, theme, lang)

    data = advisor_data(persona, lang)
    reading, waqi_status = data["reading"], data["waqi_status"]
    start = time.time()

    ok, pattern = guard.check(question)
    if not ok:
        es.log_security(client, {
            "@timestamp": es.now_iso(), "session_hash": hashed,
            "event_type": "prompt_injection", "pattern_matched": pattern,
            "prompt_excerpt": normalize.excerpt(question), "action_taken": "blocked"})
        es.log_telemetry(client, {
            "@timestamp": es.now_iso(), "session_hash": hashed, "event": "blocked",
            "latency_ms": int((time.time() - start) * 1000),
            "waqi_status": waqi_status, "llm_status": "skipped", "llm_tokens": 0,
            "aqi_value": reading.get("aqi"), "locality": persona["locality"], "error": ""})
        # The excerpt, not the raw string: guard.check rejects oversized input,
        # and storing what it rejected would let a client pin an arbitrarily
        # large question in server memory -- through the one path that exists
        # precisely to refuse it. It is also raw user text, which the transcript
        # cap is meant to bound rather than accumulate.
        add_turn(sid, {"kind": "refusal", "lang": lang,
                       "question": normalize.excerpt(question),
                       "pattern": pattern,
                       "persona": dict(persona)})
        return _back(request, sid, theme, lang)

    try:
        # The AQI, or None when the feed carried no usable particulate --
        # never `or 0`. Zero is the cleanest possible air, so coercing the
        # missing value here retrieved the "outdoor activity is fine for
        # everyone" row and handed it to the model as verified context, on a
        # page whose own verdict said to treat the outing as unsafe.
        # search_advisories returns [] for None, and the answer path already
        # copes with an empty list.
        advisories = es.search_advisories(
            reading.get("aqi"),
            normalize.norm_condition(persona["condition"]),
            normalize.norm_activity(persona["activity"]),
            normalize.norm_age(persona["age"]), client=client)
        text, tokens, llm_status = llm.answer(
            reading,
            {"age_group": persona["age"], "condition": persona["condition"],
             "activity": persona["activity"]},
            advisories, question, locality=persona["locality"],
            timestamp=es.now_iso(), best_window=data["window"], lang=lang,
            # The hero's own band, so the card cannot be more permissive than
            # the verdict printed above it on the same page -- but ONLY when
            # the hero actually prints one. With no reading `compute_risk`
            # still returns a band, computed from an assumed AQI, which the
            # hero suppresses; passing it here re-published the suppressed
            # severity through the answer card, and through the system prompt
            # on the paid path (llm.py:133). No measurement, no band.
            #
            # Freshness too, not just existence. A HELD reading has an aqi, so
            # the aqi-only test passed the suppressed band into the answer card
            # AND into the system prompt, under the line "This is what the page
            # already tells them above your answer, so do not be more permissive
            # than it" -- which was false: the page had withdrawn it. On the
            # shipped path OPENROUTER_API_KEY is unset, so llm._rule_based runs
            # and states the band in prose with no freshness awareness at all.
            risk_band=(data["risk"]["band"]
                       if reading.get("aqi") is not None
                       and pr.freshness(waqi_status, reading) == "live"
                       else None))
        parsed = llm.parse_advice(text)
        add_turn(sid, {
            "kind": "answer", "lang": lang, "question": question,
            "persona": dict(persona),
            "blocks": pr.answer_sections(parsed, lang=lang),
            "disclaimer": parsed.get("disclaimer"),
            "sources": advisories,
            "reading": reading, "waqi_status": waqi_status})
        degraded = [n for n, bad in (("waqi_fallback", waqi_status == "fallback"),
                                     ("llm_fallback", llm_status == "llm_fallback")) if bad]
        es.log_telemetry(client, {
            "@timestamp": es.now_iso(), "session_hash": hashed, "event": "chat_completed",
            "latency_ms": int((time.time() - start) * 1000),
            "waqi_status": waqi_status, "llm_status": llm_status, "llm_tokens": tokens,
            "aqi_value": reading.get("aqi"), "locality": persona["locality"],
            "error": "; ".join(degraded)})
    except Exception as exc:  # pragma: no cover - top-level safety net
        add_turn(sid, {
            "kind": "answer", "lang": lang, "question": question,
            "persona": dict(persona),
            "blocks": [{"heading": i18n.t(lang, "ui", "heading_verdict", "Verdict"),
                        "lead": True,
                        "text": i18n.t(
                            lang, "ui", "answer_error",
                            "Something went wrong preparing your advice. When in "
                            "doubt, minimise outdoor exposure and wear an N95 "
                            "outside.")}],
            "disclaimer": None, "sources": [],
            "reading": reading, "waqi_status": waqi_status})
        es.log_telemetry(client, {
            "@timestamp": es.now_iso(), "session_hash": hashed, "event": "error",
            "latency_ms": int((time.time() - start) * 1000),
            "waqi_status": waqi_status, "llm_status": "error", "llm_tokens": 0,
            "aqi_value": reading.get("aqi"), "locality": persona["locality"],
            "error": normalize.sanitize_error(exc)})
    return _back(request, sid, theme, lang)


# --- City Pulse ------------------------------------------------------------
# There is no `_sample_aqi` here any more. It derived an AQI from the hardcoded
# winter concentration table and handed it to `normalize.band_for`, the "worst
# first" sort, `count` and `median`. With no stored row for any station -- the
# production state -- all 21 tiles took that branch, so the page printed
# "median AQI 358" and sorted an invented 401 to the top while the same app's
# home page showed the same station at AQI 86. A station with no reading now
# has no number, and a tile with no number is counted in nothing.


# How many localities to ask WAQI about at once. The page needs 21 answers and
# a serial loop would be 21 round trips on one 256MB machine that scales to
# zero. It is bounded rather than unbounded because the point is to overlap the
# waiting, not to open 21 sockets at a stranger's API in one burst.
#
# In the common case this costs no HTTP at all: get_aqi is memoised per locality
# for 600s and shared between every visitor, so only the entries that actually
# expired are fetched, and its per-locality fetch lock collapses a thundering
# herd on a cold cache into one request each.
_CITY_FETCH_WORKERS = 8
# Seconds the whole 21-locality sweep may spend before /city renders with
# whatever answered. Sized a little above waqi.TIMEOUT so a single slow feed
# does not cost the page, while a dead upstream costs one timeout rather than
# ceil(21/8) of them.
_CITY_FETCH_BUDGET = 6.0

# ONE pool for the process, not one per request.
#
# This was built inside _live_grid and shut down with wait=False, which does not
# cancel queued work. Under a SLOW upstream -- the case that matters, and the
# production steady state on a machine that scales to zero -- the eight workers
# are still occupied when the budget expires and the response is sent, so N
# concurrent /city renders meant 8N live threads, each holding its own TLS
# session, on a 256MB shared-cpu-1x machine. Nothing bounded N: /city is not
# rate-limited, on the reasoning that the 600s memo caps upstream CALLS. It does,
# and calls were never the resource that runs out first -- that memo is exactly
# what makes the warm case free and leaves the cold case unbounded.
#
# (With FAST tasks there is no difference: the workers finish, the per-request
# executor is collected, and its threads are joined. Measured 7 threads either
# way. So the invariant only shows up under a slow upstream, which is how the
# test below is written.)
#
# Deliberately never shut down: it lives as long as the process.
_CITY_POOL = ThreadPoolExecutor(max_workers=_CITY_FETCH_WORKERS,
                                thread_name_prefix="city-fetch")


def _live_grid(es_client) -> dict:
    """``{locality: (reading, status)}`` from the SAME source the Today page uses.

    This is the fix for City Pulse's central defect. /city had no live path at
    all: its only data call was ``metrics.station_grid``, which reads the
    Elasticsearch aqi-readings index, and that index is written from exactly one
    place -- ``waqi._fetch_uncached`` -- when a visitor loads the HOME page for
    one locality on a cache miss. Nothing ever back-filled the other twenty. In
    production the index answered with nothing, so every tile fell through to
    the hardcoded sample, and the same app served "Rohini LIVE AQI 86" on / and
    "Rohini SAMPLE AQI 267" on /city in the same minute. It was never a cache,
    timeout or freshness bug: it was a second data path with a fabricated
    fallback.

    Asking ``waqi.get_aqi`` here means the two pages cannot disagree, because
    there is no longer a second source for them to disagree from. It also
    repairs the index asymmetry for free: all 21 stations get refreshed and
    indexed, instead of only the one the visitor happened to pick.
    """
    def one(loc):
        # "get_aqi never raises by contract" was ASSERTED here, not enforced:
        # _fetch_uncached does not wrap config.waqi_token() or _corroborates, so
        # a raise inside either became a 500 on /city instead of the ("fallback",
        # no numbers) the contract promises. The contract is now enforced at the
        # boundary that depends on it.
        try:
            return waqi.get_aqi(loc, es_client)
        except Exception:
            return waqi._fallback(loc), "fallback"

    futures = {loc: _CITY_POOL.submit(one, loc) for loc in waqi.LOCALITIES}
    # A WALL-CLOCK budget for the whole sweep, not per call. This machine is one
    # 256MB instance that scales to zero, so the first /city request after a wake
    # has an empty cache and does all 21 fetches on the request thread. With
    # waqi.TIMEOUT per call and 8 workers, an unresponsive upstream blocked the
    # response for ceil(21/8) x TIMEOUT before a byte of HTML was written, and the
    # 60s failure TTL made that repeat every minute. Whatever has not answered by
    # the deadline is treated as a locality with no live reading -- which the page
    # already renders honestly, as CACHED with an age or NO READING. The
    # in-flight calls are not cancelled: they finish in the background and
    # populate the cache for the next render, so the budget costs freshness once,
    # not repeatedly.
    #
    # Nothing is shut down here now: the pool is process-wide, so shutting it
    # down would break every later request. That is also what bounds the
    # stragglers this budget abandons -- they queue inside a pool of eight
    # instead of every render opening eight more.
    deadline = time.monotonic() + _CITY_FETCH_BUDGET
    out = {}
    for loc, fut in futures.items():
        remaining = max(0.0, deadline - time.monotonic())
        try:
            out[loc] = fut.result(timeout=remaining)
        except Exception:
            out[loc] = (waqi._fallback(loc), "fallback")
    return out


def _partial(reading) -> bool:
    """True when the index came from ONE particulate rather than two.

    Not "a value is missing": a reading with neither particulate has no index
    at all and never reaches a tile, so the interesting case is exactly one.
    """
    if not reading or reading.get("aqi") is None:
        return False
    return (reading.get("pm25") is None) != (reading.get("pm10") is None)


@app.get("/city")
def city(request: Request):
    persona = read_persona(request)
    theme = read_theme(request)
    lang = read_lang(request)
    client = get_client()
    selected = request.query_params.get("station")
    if selected not in waqi.LOCALITIES:
        selected = persona["locality"]

    live = _live_grid(client)
    grid = {r.get("station"): r for r in metrics.station_grid(client, waqi.LOCALITIES)}
    stations = []
    for loc in waqi.LOCALITIES:
        row = grid.get(loc)
        reading, status = live.get(loc, (None, "fallback"))
        state = pr.freshness(status, reading)
        live_aqi = reading.get("aqi") if state == "live" else None
        # A held reading brings BOTH its number and its age. Taking the number
        # from one source and the age from another -- an Elasticsearch row's
        # timestamp under a CPCB payload's figure -- would be a new false claim
        # in place of the old one.
        held_aqi = reading.get("aqi") if state == "held" else None
        # A stored reading is only "cached" if we hold one at all. Treating a
        # week-old document as current would present stale air as the air
        # outside now -- the one thing this product promises never to do -- so
        # the stored branch always carries its age.
        # A row we hold but which carries no aqi tells the reader nothing, so it
        # is worth exactly as much as no row at all: the branch keys off the
        # VALUE, not off the row's existence.
        stored = row.get("aqi") if row else None
        # Live first, because it is the measurement. Then what we stored last,
        # WITH ITS AGE, because a real reading from six hours ago is worth
        # something and the reader can price it once they know when it was.
        # A station we hold nothing for gets no number and no band; there is
        # nothing to stand in for it with.
        aqi = live_aqi if live_aqi is not None else (
            held_aqi if held_aqi is not None else stored)
        # A stored row is NEVER "live". It used to become live when it was
        # under three hours old, which meant a tile could carry the band word,
        # the severity colour, no tag and no age off a row measured 2h50m ago --
        # while /?locality=<same station> said NO READING for it in the same
        # minute, because the home page has no such three-hour grace. Two pages
        # of one app disagreeing about whether a measurement exists is the
        # defect this whole surface was rewritten to remove. Live means the feed
        # answered just now; everything else is dated.
        if live_aqi is not None:
            source = "live"
        elif held_aqi is not None:
            # Held, not live: real numbers we already fetched, being re-served
            # because the upstream failed. It is tagged and dated exactly as a
            # stored reading is, and earns no band word for the same reason.
            source = "held"
        elif stored is not None:
            source = "cached"
        else:
            source = "none"
        label, _c, _h, slug = normalize.band_for(aqi)
        # The band word, and the colour ramp that carries the same meaning
        # without words, belong to a CURRENT measurement only. A stored reading
        # keeps its number and gains its age -- both facts -- but saying
        # "Severe" beside a figure from nine hours ago states today's air from
        # yesterday's evidence, which is the same error as the sample in a
        # slower form.
        stations.append({"name": loc, "aqi": aqi,
                         "band": i18n.t(lang, "band_label", label, label)
                                 if source == "live" else None,
                         # The Unknown slug, taken from normalize rather than
                         # written out, so the two cannot drift apart.
                         "slug": slug if source == "live"
                                 else normalize.band_for(None)[3],
                         "source": source,
                         # Each dated by its OWN measurement: the stored row by
                         # the row's timestamp, the held reading by the
                         # observation time CPCB published with it.
                         "age": _age_label(row.get("ts"), lang) if source == "cached"
                                else (_age_label(reading.get("obs_time"), lang)
                                      if source == "held" else None),
                         # This grid sorts worst-first and so invites the reader
                         # to compare tiles against each other. A figure worked
                         # out from one particulate is not comparable with one
                         # worked out from two -- Wazirpur's PM2.5 instrument
                         # was down and its index came from PM10 alone -- and
                         # /?locality=<the same station> now says so while this
                         # tile showed a bare number beside its neighbours.
                         #
                         # Marked in PLAIN LANGUAGE: naming the particulate
                         # here would put PM2.5/PM10 outside the Guide, the
                         # System views and the provenance panel, which is the
                         # one place the reading card is allowed to name them.
                         # Only for readings we hold the dict for; a row
                         # rebuilt from Elasticsearch cannot be asked.
                         "partial": _partial(reading) if source in ("live", "held")
                                    else False,
                         "selected": loc == selected})

    def group(region):
        rows = [s for s in stations if s["name"] in waqi.REGIONS[region]]
        # Worst first: the station in trouble is the one you scan for.
        return sorted(rows, key=lambda s: (s["aqi"] is None, -(s["aqi"] or 0)))

    # Two different counts, because they answer two different questions. `held`
    # is how many stations we can show a number for at all -- a stored figure
    # from this morning is still a number we hold. `live_n` is how many are
    # reporting NOW, and the median is computed over those alone: a median is a
    # claim about the city's air at this moment, and one stale figure is not a
    # central tendency. The page used to print "median AQI 401" off a single
    # stored row, one line above twenty tiles saying NO READING.
    live_rows = [s for s in stations if s["source"] == "live"]
    held = sum(1 for s in stations if s["aqi"] is not None)
    live_n = len(live_rows)
    live_median = pr.median_aqi(live_rows)

    trend = metrics.aqi_trend(client, locality=selected, hours=24)
    ctx = base_context(request, persona, theme, lang, "city")
    ctx.update({
        "delhi": group("Delhi"), "ncr": group("NCR"),
        "count": held,
        "total": len(stations),
        "median": live_median,
        "summary": pr.city_summary(held, live_n, len(stations), live_median,
                                   _fmt_stamp(lang), lang=lang),
        "now": _fmt_stamp(lang),
        "selected": selected,
        # The whole row, not just the number. The trend header printed
        # `LAST 24 H · AQI 312` bare while the tile ten lines below dated the
        # identical 312 as `CACHED · 13 H OLD` -- one page saying two different
        # things about one figure, which is the defect City Pulse was rewritten
        # to remove, reappearing on the header instead of the tile. The header
        # now carries the same tag the tile does, from the same row, so the two
        # cannot disagree.
        "selected_row": next((s for s in stations if s["name"] == selected), None),
        "selected_aqi": next((s["aqi"] for s in stations if s["name"] == selected), None),
        "spark": pr.sparkline_svg(trend.get("points"), lang=lang),
        # Built from the same persona-or-empty dict as every other link: a
        # station tile is not a persona choice, so it must not apply one.
        "q_station": lambda name: _qs(
            persona if ctx["persona_applied"] else {}, theme, lang, station=name),
    })
    return _render(request, "city.html", ctx, session_id(request), theme, lang)


def _kpi_stat(value, factor: float, spec: str, suffix: str) -> str:
    """A KPI tile value, or City Pulse's no-figure mark when None was measured.

    ``metrics`` returns None -- not 0.0 -- for a percentile over nothing timed
    and for a rate over an empty denominator. Formatting those printed
    "0.0 s median response" and "0.0% feed misses" one card above the page's
    own "No telemetry yet", so the view asserted a measured statistic and the
    absence of any measurement at once. No observations, no figure and no unit.
    """
    if value is None:
        return "--"
    return f"{value * factor:{spec}}{suffix}"


# --- System ----------------------------------------------------------------
@app.get("/system")
def system(request: Request):
    persona = read_persona(request)
    theme = read_theme(request)
    lang = read_lang(request)
    client = get_client()
    view = "security" if request.query_params.get("view") == "security" else "observability"

    ctx = base_context(request, persona, theme, lang, "system")
    ctx.update({
        "view": view,
        # The empty states must name the real cause. With no index configured,
        # asking questions on Today can never populate this view, so telling a
        # reader to go and ask one is a wrong remedy for a misdiagnosed fault.
        "has_index": get_client() is not None,
        "q_obs": _qs(persona if ctx["persona_applied"] else {}, theme, lang,
                     view="observability"),
        "q_sec": _qs(persona if ctx["persona_applied"] else {}, theme, lang,
                     view="security"),
        "simulated": request.query_params.get("sim") == "1",
        "attack_count": len(ATTACKS),
    })

    if view == "observability":
        k = metrics.telemetry_kpis(client)
        by_event = k.get("by_event") or {}
        ev_max = max(by_event.values()) if by_event else 0
        loc_rows = k.get("by_locality") or []
        loc_max = max((r["count"] for r in loc_rows), default=0)
        # `total` counts every logged event, including blocked prompts and
        # errors. Only completed answers belong under "questions answered".
        answered = (by_event or {}).get("chat_completed", 0)
        ctx.update({
            "kpis": [
                {"v": answered,
                 "l": i18n.t(lang, "ui", "sys_kpi_answered", "questions answered")},
                {"v": k.get("total", 0),
                 "l": i18n.t(lang, "ui", "sys_kpi_events", "events logged")},
                {"v": _kpi_stat(k.get("latency_p50"), 0.001, ".1f", " s"),
                 "l": i18n.t(lang, "ui", "sys_kpi_p50", "median response")},
                {"v": _kpi_stat(k.get("latency_p95"), 0.001, ".1f", " s"),
                 "l": i18n.t(lang, "ui", "sys_kpi_p95", "p95 response")},
                {"v": _kpi_stat(k.get("waqi_fallback_rate"), 100, ".1f", "%"),
                 # NOT "feed misses -> cached". A feed miss routes to waqi._fallback,
                 # which returns a reading with every numeric field None: nothing
                 # is cached and nothing is served. The old label told an operator
                 # that 42% of requests were answered from cache when in fact they
                 # were answered with no number at all, and it collided with
                 # city.html's CACHED, which means something else again.
                 "l": i18n.t(lang, "ui", "sys_kpi_feed_fallback",
                             "feed misses → no reading")},
                {"v": _kpi_stat(k.get("llm_fallback_rate"), 100, ".1f", "%"),
                 "l": i18n.t(lang, "ui", "sys_kpi_rule_fallback", "rule-based fallbacks")},
                {"v": f'{k.get("total_tokens", 0) / 1000:.1f}k',
                 "l": i18n.t(lang, "ui", "sys_kpi_tokens", "tokens spent")},
            ],
            # The event name is the literal value stored in the telemetry
            # index and is shown unchanged in both languages -- this row is a
            # view of the data, not a description of it.
            "ev_rows": [{"l": n, "v": c, "w": pr.pct(c, ev_max)}
                        for n, c in sorted(by_event.items(), key=lambda x: -x[1])],
            # The locality, by contrast, is a place a reader recognises, so the
            # label follows the page while the stored value does not change.
            "loc_rows": [{"l": i18n.place(lang, r["locality"]), "v": r["count"],
                          "w": pr.pct(r["count"], loc_max)}
                         for r in loc_rows[:6]],
        })
    else:
        stats = metrics.security_stats(client)
        daily = metrics.security_daily(client, days=7)
        day_max = max((d["count"] for d in daily), default=0)
        # security_stats aggregates the whole index, so the KPI has to come from
        # the same seven-day buckets the chart uses or the label is a lie.
        last_7 = sum(d["count"] for d in daily)
        ctx.update({
            "sec_kpis": [
                {"v": last_7,
                 "l": i18n.t(lang, "ui", "sys_kpi_blocked_7d", "blocked, last 7 days")},
                {"v": _kpi_stat(stats.get("block_rate"), 100, ".0f", "%"),
                 "l": i18n.t(lang, "ui", "sys_kpi_premodel", "stopped pre-model")},
                {"v": len(stats.get("by_pattern") or []),
                 "l": i18n.t(lang, "ui", "sys_kpi_patterns", "distinct patterns")},
            ],
            # _day_label returns strftime's English abbreviation, which the
            # 'day' group already has Hindi for -- the same three-letter
            # weekdays the Today outlook uses, so the two charts agree.
            "days": [{"n": d["count"],
                      "d": i18n.t(lang, "day", _day_label(d["date"]).lower(),
                                  _day_label(d["date"])),
                      "h": pr.pct(d["count"], day_max)} for d in daily],
            # Whose blocked prompt may be shown. /system is public and
            # unauthenticated, and the excerpt is a verbatim fragment of what
            # somebody typed -- publishing a stranger's is not made acceptable
            # by the fact that the guard stopped it. The red-team demo's own
            # attempts are ours to display, and a visitor may see their own.
            "attempts": pr.group_attempts(
                [{**a, "when": _fmt_time(a["ts"])}
                 for a in metrics.recent_security_events(client, limit=40)
                 if a.get("session_hash") in _displayable_sessions(request)])[:6],
        })
    return _render(request, "system.html", ctx, session_id(request), theme, lang)


@app.post("/system/simulate")
def simulate(request: Request):
    """Fire the known attack prompts at the live guard and audit every block."""
    persona = read_persona(request)
    theme = read_theme(request)
    lang = read_lang(request)
    client = get_client()

    # Writes one security-event per attack in the demo set, on demand, with no
    # authentication. Left open it is a document generator pointed at the very
    # index the Security view reads -- a flooder could bury the real blocked
    # prompts under demo rows and make that page useless, which is worse than
    # the write cost. A tighter limit than /ask because nobody needs to run the
    # red-team demo twenty times in five minutes.
    allowed, _retry = ratelimit.check(
        f"simulate:{ratelimit.client_key(request)}",
        ratelimit.SIMULATE_LIMIT, ratelimit.SIMULATE_WINDOW)
    if not allowed:
        # Straight back to the view. The Security page already renders what the
        # previous run wrote, so there is nothing to explain and nothing new
        # to show.
        return RedirectResponse(
            "/system?view=security&"
            + _qs(persona if persona_applied(request) else {}, theme, lang)
            + "#security",
            status_code=303)

    hashed = normalize.session_hash("red-team-demo")
    for _name, prompt in ATTACKS:
        ok, pattern = guard.check(prompt)
        if ok:
            continue
        es.log_security(client, {
            "@timestamp": es.now_iso(), "session_hash": hashed,
            "event_type": "prompt_injection", "pattern_matched": pattern,
            "prompt_excerpt": normalize.excerpt(prompt), "action_taken": "blocked"})
    try:
        if client is not None:
            client.indices.refresh(index=es.INDEX_SECURITY)
    except Exception:
        pass
    url = "/system?" + _qs(persona if persona_applied(request) else {},
                           theme, lang, view="security", sim="1")
    return RedirectResponse(url, status_code=303)


# The Guide renders three of risk.py's tables, whose keys are scoring keywords
# ("copd", "outdoor_exercise", "sedentary") rather than copy. Capitalising a
# keyword in the template produced "Copd" in English and left it in English on
# a Hindi page; these builders name each row instead. The persona words reuse
# the picker's own labels, so a condition cannot be called one thing in the
# editor and another in the Guide.
_EPA_AGE_ORDER = ("child", "adult", "senior")
# risk.py's scoring keyword -> the persona option it stands for.
_FACTOR_OPTION = {
    "copd": "COPD", "heart": "Heart condition", "pregnancy": "Pregnancy",
    "asthma": "Asthma", "senior": "Senior", "child": "Child",
}


def _intensity_labels(lang: str) -> dict:
    """The four effort levels, named the way the table above them names them.

    Two of the four English names appeared on no column. This page shows the EPA
    breathing-rate table with the columns `At rest | Light | Moderate | Hard`, and
    then a second table saying which planned activity is which effort level -- and
    that one said "sedentary" and "high". A reader told "Outdoor exercise - high"
    had no `High` column to look up; the hardest one is `Hard`.

    English defaults only. i18n.t returns the Hindi entry when there is one, so
    Hindi is untouched here -- its own mismatch (level_sedentary is
    बैठे-बैठे against the आराम में column) is one word of new copy and belongs to
    the pending Hindi review, not to this change.
    """
    return {
        "sedentary": i18n.t(lang, "guide", "level_sedentary", "at rest"),
        "light": i18n.t(lang, "guide", "level_light", "light"),
        "moderate": i18n.t(lang, "guide", "level_moderate", "moderate"),
        "high": i18n.t(lang, "guide", "level_high", "hard"),
    }


def _epa_rows(lang: str) -> list:
    """EPA's inhalation table, one row per age group this site offers.

    The age band ("6 to <11 years") is EPA's own bracket, restated rather than
    quoted, so it is translated -- unlike the citation under the table.
    """
    labels = _option_labels(lang)
    bands = {
        "child": i18n.t(lang, "guide", "age_band_child", "6 to <11 years"),
        "adult": i18n.t(lang, "guide", "age_band_adult", "21 to <31 years"),
        "senior": i18n.t(lang, "guide", "age_band_senior", "61 to <71 years"),
    }
    return [{"label": labels[age.capitalize()], "band": bands[age],
             "rates": [risk.INHALATION_RATES[age][level]
                       for level in risk.INTENSITY_ORDER]}
            for age in _EPA_AGE_ORDER]


def _intensity_rows(lang: str) -> list:
    """Which planned activity this site treats as which EPA effort level.

    "any" is the unknown-plans fallback and is never a thing a reader picked,
    so it is not shown.
    """
    labels, levels = _option_labels(lang), _intensity_labels(lang)
    activity_option = {"outdoor_exercise": "Outdoor exercise",
                       "school_run": "School run", "commute": "Commute",
                       "stay_home": "Stay home"}
    return [{"activity": labels[activity_option[keyword]], "level": levels[level]}
            for keyword, level in risk.ACTIVITY_INTENSITY.items()
            if keyword in activity_option]


def _factor_rows(lang: str) -> list:
    """The ungrounded weights: condition and age, named as the picker names them."""
    labels = _option_labels(lang)
    return [{"label": labels[_FACTOR_OPTION[w["key"]]], "value": w["value"]}
            for w in risk.weight_table()
            if w["table"] in ("condition_pts", "age_susceptibility_pts")
            and w["value"] and w["key"] in _FACTOR_OPTION]


@app.get("/guide")
def guide(request: Request):
    """Plain-language explanation of every number and term the site shows.

    Lives at its own URL rather than as a collapsed block on Today, so it can be
    linked to directly from the term that confused someone.
    """
    persona = read_persona(request)
    theme = read_theme(request)
    lang = read_lang(request)
    ctx = base_context(request, persona, theme, lang, "guide")
    ranges = ["0-50", "51-100", "101-200", "201-300", "301-400", "401-500"]
    labels = [b[1] for b in normalize.AQI_BANDS] + ["Severe"]
    slugs = [b[4] for b in normalize.AQI_BANDS] + ["g6"]
    ctx.update({
        # The eleven citation-source entries (GINA-guidance, CPCB-AQI-scale...)
        # live in this same dict for the provenance panel's def-slot, but the
        # Guide's list assumes every unmapped key is a term a Delhi reader says
        # out loud (see the comment in guide.html) -- a hyphenated index slug
        # is not that, so it is excluded here rather than given a made-up
        # spoken name. Its definition still exists; it opens beside the pill
        # that names it, on the page that shows the pill.
        "glossary": {k: v for k, v in normalize.GLOSSARY.items()
                     if k not in SOURCE_TERMS},
        "conditions_help": normalize.CONDITION_HELP,
        "bands": [{"label": i18n.t(lang, "band_label", l, l), "range": r, "slug": g,
                   "meaning": i18n.t(lang, "aqi_meaning", l, normalize.aqi_meaning(l))}
                  for l, r, g in zip(labels, ranges, slugs)],
        # Only the two glossary terms that are ordinary English. AQI, PM2.5,
        # PM10, CPCB, N95 and µg/m³ are how a Delhi reader says them out loud,
        # so the template falls back to the term itself for those.
        "glossary_terms": {
            "Dominant pollutant": i18n.t(lang, "guide", "term_dominant",
                                         "Dominant pollutant"),
            "Risk score": i18n.t(lang, "guide", "term_risk_score", "Risk score"),
        },
        # A reader told "44/100 · HIGH" cannot check that without the cut-offs.
        "risk_bands": [{"label": n, "upper": u} for n, u, _c in risk._BAND_TABLE],
        "risk_notice": i18n.t(lang, "ui", "risk_notice", risk.HEURISTIC_NOTICE),
        # Citations, not copy: an identifier a reader is meant to look up. Left
        # in Latin on purpose -- translating it would make the source harder to
        # find, which is the opposite of why it is printed.
        "source_epa": risk.SOURCE_EPA,
        "who_guideline": pr.WHO_PM25_24H,
        # Not a citation. It is this site's own statement about its own numbers,
        # and a reader must be able to read it in the language they chose.
        "source_unvalidated": i18n.t(lang, "guide", "source_unvalidated",
                                     risk.SOURCE_UNVALIDATED),
        "epa_rows": _epa_rows(lang),
        "intensity_rows": _intensity_rows(lang),
        "factor_rows": _factor_rows(lang),
    })
    return _render(request, "guide.html", ctx, session_id(request), theme, lang)


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Browsers probe the site root for this whatever the link tags say.

    Without it every page view logged a 404, which is noise in the one view
    this project uses to check its own behaviour.
    """
    return FileResponse(BASE / "static" / "favicon.ico",
                        media_type="image/x-icon",
                        headers={"Cache-Control": "public, max-age=86400"})


@app.get("/health")
def health():
    # Primary source first. This reported only "waqi", so a deploy with no
    # CPCB_API_KEY looked green while the PRIMARY source was off.
    return {"ok": True, "es": config.es_mode(),
            "cpcb": config.cpcb_available(),
            "waqi": config.waqi_available(), "llm": config.llm_available()}


# --- helpers ---------------------------------------------------------------
def _last_real_reading(locality: str, lang: str = "en"):
    """``{"aqi": n, "when": "23 June"}`` for a locality, or None.

    The last measurement this app actually stored for the place, dated by when
    the AIR was measured rather than by when we fetched it. Returns None -- and
    the page then says only that it has no reading -- when there is no
    Elasticsearch client, no stored row, or no usable value in it. Nothing is
    substituted in that case; the empty state IS the answer.

    Note for anyone reading production behaviour off this: with no ELASTIC_*
    credentials there is no client, so this always returns None and every
    locality shows the plain empty state.
    """
    client = get_client()
    if client is None:
        return None
    try:
        rows = metrics.station_grid(client, [locality])
    except Exception:
        return None
    row = next((r for r in rows if r.get("station") == locality), None)
    if not row or row.get("aqi") is None or not row.get("ts"):
        return None
    when = _fmt_date(row["ts"], lang)
    if not when:
        return None
    return {"aqi": row["aqi"], "when": when}


def _fmt_date(iso, lang: str = "en") -> str:
    """'23 Jun' in IST -- '23 Jun 2025' in another year -- or "" if unparseable.

    Empty rather than a placeholder: this date is the entire warrant for the
    number printed beside it, so a reading whose date cannot be established has
    nothing to say and is not shown at all.

    The year is written whenever the reading is not from the current IST year.
    Day and month alone made a row from 23 June 2025 render identically to one
    from 23 June 2026, so a thirteen-month-old measurement read as four weeks
    old -- on the one line where the date is the whole warrant for the number.
    It is omitted within the current year because "23 Jun 2026" printed in July
    2026 is noise that makes the useful case harder to read.
    """
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    # IST, not UTC. A row dated by @timestamp carries UTC "Z" -- the
    # compatibility path metrics.station_grid falls back to -- and 20 Jul
    # 01:30 IST is 19 Jul in UTC. Without this the line names the wrong day.
    dt = dt.astimezone(IST)
    # _month_abbr, not strftime("%b"), which hands a Hindi page "Jun".
    out = f"{dt.day} {_month_abbr(lang, dt.month)}"
    if dt.year != datetime.now(IST).year:
        out = f"{out} {dt.year}"
    return out


def _displayable_sessions(request: Request) -> set:
    """Session hashes whose blocked-prompt text this page may print."""
    return {normalize.session_hash("red-team-demo"),
            normalize.session_hash(session_id(request))}


def _day_label(date_str: str) -> str:
    try:
        return datetime.fromisoformat(str(date_str)[:10]).strftime("%a")
    except ValueError:
        return str(date_str)[:3]


def _set_cookies(response, request: Request, sid: str, theme: str = None,
                 lang: str = None):
    """Attach the session and theme cookies.

    ``secure`` follows the scheme actually in use rather than being hardcoded
    True: over https the browser must never send these back in clear, and over
    the plain-http development server a Secure cookie would simply be dropped,
    silently breaking the transcript and the theme toggle.

    That is only as good as the scheme this process can see. Behind a proxy
    that terminates TLS -- which is every deployment target in docs/DEPLOY.md
    -- ``request.url.scheme`` reads "http" unless uvicorn is told to trust the
    forwarded header, because ``--forwarded-allow-ips`` defaults to 127.0.0.1
    and the proxy is not on the loopback. The Dockerfile passes that flag for
    exactly this reason. Run this app behind a proxy without it and the cookies
    will NOT be marked Secure, which is worth knowing rather than assuming.
    """
    secure = request.url.scheme == "https"
    response.set_cookie("sid", sid, httponly=True, samesite="lax", secure=secure)
    if theme is not None:
        response.set_cookie("theme", theme, samesite="lax", secure=secure)
    if lang is not None:
        response.set_cookie("lang", lang, samesite="lax", secure=secure)
    return response


# Response headers every page carries.
#
# The zero-JavaScript rule was enforced by one test grepping the rendered HTML
# for "<script". That catches a template that adds a script; it cannot stop a
# script that arrives any other way, and docs/decisions/0001-zero-javascript.md
# names exactly this as its own open falsification -- "until that is done we do
# not actually know the rule is enforced at all". `script-src 'none'` makes the
# BROWSER refuse to execute one, which is the second, runtime enforcement the
# stricter rule can have and the weaker one cannot.
#
# style-src and font-src are 'self' alone: the faces are self-hosted under
# /static/fonts (scripts/build_fonts.py), so a page that tried to reach the
# Google font hosts again would be refused by its own policy -- the runtime
# enforcement of test_privacy's no-third-party rule. No connect-src is needed
# -- nothing on these pages talks to the network after load, which is the
# whole point of the architecture.
_SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'none'; "
        "style-src 'self'; "
        "font-src 'self'; "
        "img-src 'self' data:; "
        "form-action 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'none'"
    ),
    # The persona rides in the query string, so a sniffed content type that let a
    # response render as something else would be reflecting it into a new context.
    "X-Content-Type-Options": "nosniff",
}


def _render(request, template, ctx, sid, theme, lang):
    response = templates.TemplateResponse(request, template, ctx)
    for header, value in _SECURITY_HEADERS.items():
        response.headers[header] = value
    return _set_cookies(response, request, sid, theme, lang)


def _month_abbr(lang: str, month: int) -> str:
    """The month, short. ``strftime('%b')`` would hand a Hindi page 'Jul'.

    Twelve literal keys rather than a formatted one, so tests/test_i18n.py can
    read them back out of this file and fail when one is missing.
    """
    return (
        i18n.t(lang, "ui", "month_1", "Jan"), i18n.t(lang, "ui", "month_2", "Feb"),
        i18n.t(lang, "ui", "month_3", "Mar"), i18n.t(lang, "ui", "month_4", "Apr"),
        i18n.t(lang, "ui", "month_5", "May"), i18n.t(lang, "ui", "month_6", "Jun"),
        i18n.t(lang, "ui", "month_7", "Jul"), i18n.t(lang, "ui", "month_8", "Aug"),
        i18n.t(lang, "ui", "month_9", "Sep"), i18n.t(lang, "ui", "month_10", "Oct"),
        i18n.t(lang, "ui", "month_11", "Nov"), i18n.t(lang, "ui", "month_12", "Dec"),
    )[month - 1]


def _fmt_stamp(lang: str = "en") -> str:
    """Now, as '3:05 AM IST, 20 Jul' -- placeable on a calendar.

    Comparing two pages is impossible without the date and the zone, so both
    are always spelled out. Takes no timestamp on purpose: this stamps the
    moment the page was rendered, and accepting one would invite it to be used
    for an observation time, which is what ``_fmt_time`` is for.

    The month is looked up rather than left to ``%b``, which is either English
    or at the mercy of the server's locale -- neither of which is the language
    the reader asked for.
    """
    now = datetime.now(timezone.utc).astimezone(IST)
    return f"{now.strftime('%-I:%M %p IST')}, {now.day} {_month_abbr(lang, now.month)}"


def _age_label(ts, lang: str = "en") -> str:
    """How old a stored reading is, terse enough for a tag: '40 MIN', '5 H', '3 D'.

    Empty when the timestamp is missing or unparseable -- an invented age would
    be worse than none.
    """
    if not ts:
        return ""
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    minutes = int((datetime.now(timezone.utc) - dt).total_seconds() // 60)
    if minutes < 0:
        return ""
    if minutes < 60:
        return f"{minutes} " + i18n.t(lang, "ui", "age_unit_min", "MIN")
    if minutes < 60 * 48:
        return f"{minutes // 60} " + i18n.t(lang, "ui", "age_unit_hours", "H")
    return f"{minutes // (60 * 24)} " + i18n.t(lang, "ui", "age_unit_days", "D")


def _back(request: Request, sid: str, theme: str, lang: str):
    # An empty persona when none was applied: asking a question must not turn
    # the example persona into a chosen one via the redirect's query string.
    persona = read_persona(request) if persona_applied(request) else {}
    response = RedirectResponse("/?" + _qs(persona, theme, lang) + "#ask",
                                status_code=303)
    return _set_cookies(response, request, sid)
