"""Reproduce every measurement Gate 5's design document states.

The design document claims numbers. This script is how they were produced, so a
reader can re-derive them instead of trusting a transcription -- the first draft
of that document carried three numbers that were wrong, because the sweep
bypassed `normalize` and handed `compute_risk` keys it does not recognise
("heart_condition" instead of "heart", "fit" instead of "any"), which silently
scored those personas as if they had no condition at all.

Every sweep below therefore goes through `normalize.norm_*`, which is the path
`main.py:542-545` actually takes.

Run:

    env OPENROUTER_API_KEY= WAQI_TOKEN= ELASTIC_URL= ELASTIC_API_KEY= \
        ELASTIC_CLOUD_ID= .venv/bin/python -m scripts.measure_gate5

Two things about that command are load-bearing. `-m`, never a bare path: the
repository root has to be on `sys.path` for `import saafsaans` to resolve, which
is the same reason CI runs `python -m pytest`. And the trailing-equals form,
never `env -u NAME`: `services/config` calls `load_dotenv()` at import, which
refills an unset name from a live `.env` and produces a live-credential run.
"""
import collections
import itertools
from math import log

from saafsaans.services import i18n, normalize, risk
from saafsaans.web import presenters as pr

AGES = ["Child", "Adult", "Senior"]
CONDITIONS = ["Fit", "Asthma", "Heart condition", "Pregnancy", "COPD"]
ACTIVITIES = ["Outdoor exercise", "Commute", "School run", "Stay home"]
LUNG_CONDITIONS = {"Asthma", "COPD"}
SAMPLE_AQI = (40, 120, 180, 300)


def band_for(aqi, age, condition, activity):
    """The band a persona scores, through the same call main.py makes."""
    out = risk.compute_risk(aqi, normalize.norm_condition(condition),
                            normalize.norm_activity(activity),
                            normalize.norm_age(age))
    return out["band"] if isinstance(out, dict) else out


def personas():
    return itertools.product(AGES, CONDITIONS, ACTIVITIES)


def verdict_variety():
    """How many distinct hero verdicts the whole persona space can produce.

    Reproduces the design document's own §1.1 numbers, which is what
    ``pr.verdict_for(band)`` -- no driver argument -- still does: it is
    exactly the pre-5c call convention, and every caller used it that way
    before this package added the parameter. What it can no longer show is
    variety BY DRIVER, because that variety did not exist yet when §1.1 was
    written. See section 7 for the post-5c comparison on the current
    (post-5b) persona space.
    """
    print("1. Verdict variety (design doc section 1.1)")
    print(f"   {'AQI':>5} {'distinct':>9}  split")
    per_aqi = {}
    for aqi in SAMPLE_AQI:
        seen = collections.Counter()
        for age, cond, act in personas():
            seen[pr.verdict_for(band_for(aqi, age, cond, act))] += 1
        per_aqi[aqi] = seen
        split = " / ".join(str(n) for _, n in seen.most_common())
        print(f"   {aqi:>5} {len(seen):>9}  {split}")
    total_states = len(SAMPLE_AQI) * len(AGES) * len(CONDITIONS) * len(ACTIVITIES)
    distinct = len({s for c in per_aqi.values() for s in c})
    print(f"   -> {distinct} distinct sentences across {total_states} states")

    moved = sum(1 for age, cond, act in personas()
                if pr.verdict_for(band_for(120, age, cond, act))
                != pr.verdict_for(band_for(180, age, cond, act)))
    print(f"   -> personas whose headline differs between AQI 120 and 180: {moved}\n")


def wrong_organ(aqi=180):
    """Personas told their LUNGS are the problem who chose another organ.

    Calls ``pr.verdict_for(band)`` with no driver -- the pre-5c convention
    §1.2 measured against -- so a re-run now reports 0/0: not because no
    persona was swept, but because that call no longer ever names an organ
    (see verdict_driver_variety below, which passes the real driver and is
    where a wrong-organ regression would show up post-5c).
    """
    print(f"2. Wrong-organ headline at AQI {aqi} (design doc section 1.2)")
    hit = [(a, c, x) for a, c, x in personas()
           if "lungs like yours" in pr.verdict_for(band_for(aqi, a, c, x))]
    wrong = [t for t in hit if t[1] not in LUNG_CONDITIONS and t[1] != "Fit"]
    by_condition = collections.Counter(c for _, c, _ in wrong)
    print(f"   told 'hard on lungs like yours' : {len(hit)}")
    print(f"   of those, a non-lung condition  : {len(wrong)}")
    for cond, n in sorted(by_condition.items()):
        print(f"       {cond:<18} {n}")
    if not hit:
        print("   -> 0 is expected post-5c: verdict_for(band) alone never "
              "names an organ any more. See section 7.")
    print()


def age_bracket_gap():
    """Which ages the picker can express, and which EPA rows back them.

    Sections 1 and 2 above keep AGES at its original three -- they measure
    the historical defect exactly as the design document found it, and
    re-deriving them over five ages would silently rewrite that record. This
    section is the one about the gap itself, so it reads the picker's
    CURRENT age list rather than this module's frozen one -- closed by Gate
    5 package 5b, 2026-09-01.
    """
    from saafsaans.web import main as web_main

    print("3. Age coverage (design doc section 1.4)")
    print(f"   EPA brackets carried : {len(risk.INHALATION_RATES)}")
    print("   ages the picker offers:", ", ".join(web_main.AGES))
    if set(web_main.AGES) >= {"Teen", "Youth"}:
        print("   -> CLOSED by 5b: every EPA bracket the picker offers has an "
              "age option (11 to <16 Teen, 16 to <21 Youth).\n")
    else:
        print("   -> the Guide prints 6 to <11, 21 to <31, 61 to <71;")
        print("      ages 11 to 20 are expressible by no option\n")


def dose_rescale_exposure():
    """What adding a higher rate row would do to every EXISTING persona.

    _MAX_RATIO is derived from INHALATION_RATES itself, so a new maximum
    rescales dose_points for personas Gate 5 never touches.
    """
    print("4. Dose rescaling exposure from a new maximum rate (5b)")
    base = risk.BASELINE_RATE
    cur_max = max(r for by_age in risk.INHALATION_RATES.values()
                  for r in by_age.values())
    print(f"   current max rate {cur_max:.4g} = {cur_max / base:.2f}x baseline"
          f", _DOSE_SCALE {risk._DOSE_SCALE:.4f}")
    print(f"   {'new max':>8} {'scale':>8} {'adult/high':>11} {'child/moderate':>15}")
    for pct in (0, 5, 10, 15, 20, 30):
        scale = risk.DOSE_MAX_PTS / log(cur_max * (1 + pct / 100) / base)
        ah = round(scale * log(risk.INHALATION_RATES["adult"]["high"] / base))
        cm = round(scale * log(risk.INHALATION_RATES["child"]["moderate"] / base))
        print(f"   {'+' + str(pct) + '%':>8} {scale:>8.4f} {ah:>11} {cm:>15}")
    print()


def hindi_corpus_size():
    """Leaf strings in the Hindi corpus -- what a reviewer must get through."""
    def leaves(node):
        if isinstance(node, dict):
            return sum(leaves(v) for v in node.values())
        return 1 if isinstance(node, str) else 0

    print("5. Hindi corpus (5a)")
    print(f"   leaf strings in i18n.HI : {leaves(i18n.HI)}")
    print("   (distinct from the health-claims corpus, which spans both "
          "languages)\n")


_AGES_5B = ["Child", "Teen", "Youth", "Adult", "Senior"]
_PREGNANCY_BLOCKED_ON = ["Child", "Teen", "Senior"]
_PREGNANCY_ALLOWED = {"Youth", "Adult"}


def _reachable_88():
    """The persona space 5c sweeps: 5 ages x 5 conditions x 4 activities,
    minus the twelve (age, activity) pairs D5 blocks Pregnancy on."""
    for age in _AGES_5B:
        for cond in CONDITIONS:
            if cond == "Pregnancy" and age not in _PREGNANCY_ALLOWED:
                continue
            for act in ACTIVITIES:
                yield age, cond, act


def persona_space_after_5b():
    """The space 5c must sweep once Teen and Youth exist."""
    total = len(_AGES_5B) * len(CONDITIONS) * len(ACTIVITIES)
    blocked = len(_PREGNANCY_BLOCKED_ON) * len(ACTIVITIES)
    reachable = list(_reachable_88())
    print("6. Persona space after 5b (design doc section 2)")
    print(f"   {len(_AGES_5B)} ages x {len(CONDITIONS)} conditions x "
          f"{len(ACTIVITIES)} activities = {total}")
    print(f"   pregnancy blocked on {'/'.join(_PREGNANCY_BLOCKED_ON)} = {blocked}")
    print(f"   reachable = {total - blocked} (measured: {len(reachable)})\n")


def verdict_driver_variety():
    """Distinct verdicts before and after 5c, on the post-5b persona space.

    "Before" calls ``verdict_for(band)`` with no driver -- exactly what
    every caller did prior to this package, since the parameter did not
    exist. "After" resolves the real driver from each persona, the same way
    main.today() now does. Both walk the identical 88 x 4 = 352 states, so
    the only thing that can move the count is the driver argument itself.

    Its own AQI sample, not ``SAMPLE_AQI``: section 1's four values (40, 120,
    180, 300) were chosen for the original bug report and never reach
    Extreme for any of the 88 personas (measured), which would silently cap
    "after" at 11 -- one below the exit criterion's floor of 12. These four
    are chosen instead to cross every band boundary the 88-persona space can
    reach, Low through Extreme.
    """
    print("7. Verdict driver variety after 5c (design doc section 4)")
    driver_sample_aqi = (40, 150, 220, 350)
    reachable = list(_reachable_88())
    before, after = set(), set()
    wrong_organ_hits = []
    organ_words = {"lungs": "lungs like yours", "heart": "a heart like yours",
                   "pregnancy": "you and your pregnancy"}
    for aqi in driver_sample_aqi:
        for age, cond, act in reachable:
            band = band_for(aqi, age, cond, act)
            before.add(pr.verdict_for(band))
            condition_kw = normalize.norm_condition(cond)
            age_kw = normalize.norm_age(age)
            driver = pr.verdict_driver(condition_kw, age_kw)
            text = pr.verdict_for(band, driver)
            after.add(text)
            for organ, phrase in organ_words.items():
                if phrase in text and driver != organ:
                    wrong_organ_hits.append((age, cond, act, driver, organ))
    states = len(driver_sample_aqi) * len(reachable)
    print(f"   states swept: {len(driver_sample_aqi)} AQI x {len(reachable)} "
          f"personas = {states}")
    print(f"   distinct verdicts before (band only)    : {len(before)}")
    print(f"   distinct verdicts after (band + driver) : {len(after)}")
    print(f"   organ claims contradicting the driver   : {len(wrong_organ_hits)}")
    for hit in wrong_organ_hits[:10]:
        print(f"       {hit}")
    print()


if __name__ == "__main__":
    verdict_variety()
    wrong_organ()
    age_bracket_gap()
    dose_rescale_exposure()
    hindi_corpus_size()
    persona_space_after_5b()
    verdict_driver_variety()
