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
    """How many distinct hero verdicts the whole persona space can produce."""
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
    """Personas told their LUNGS are the problem who chose another organ."""
    print(f"2. Wrong-organ headline at AQI {aqi} (design doc section 1.2)")
    hit = [(a, c, x) for a, c, x in personas()
           if "lungs like yours" in pr.verdict_for(band_for(aqi, a, c, x))]
    wrong = [t for t in hit if t[1] not in LUNG_CONDITIONS and t[1] != "Fit"]
    by_condition = collections.Counter(c for _, c, _ in wrong)
    print(f"   told 'hard on lungs like yours' : {len(hit)}")
    print(f"   of those, a non-lung condition  : {len(wrong)}")
    for cond, n in sorted(by_condition.items()):
        print(f"       {cond:<18} {n}")
    print()


def age_bracket_gap():
    """Which ages the picker can express, and which EPA rows back them."""
    print("3. Age coverage (design doc section 1.4)")
    print(f"   EPA brackets carried : {len(risk.INHALATION_RATES)}")
    print("   ages the picker offers:", ", ".join(AGES))
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


def persona_space_after_5b():
    """The space 5c must sweep once Teen and Youth exist."""
    ages = ["Child", "Teen", "Youth", "Adult", "Senior"]
    pregnancy_blocked_on = ["Child", "Teen", "Senior"]
    total = len(ages) * len(CONDITIONS) * len(ACTIVITIES)
    blocked = len(pregnancy_blocked_on) * len(ACTIVITIES)
    print("6. Persona space after 5b (design doc section 2)")
    print(f"   {len(ages)} ages x {len(CONDITIONS)} conditions x "
          f"{len(ACTIVITIES)} activities = {total}")
    print(f"   pregnancy blocked on {'/'.join(pregnancy_blocked_on)} = {blocked}")
    print(f"   reachable = {total - blocked}\n")


if __name__ == "__main__":
    verdict_variety()
    wrong_organ()
    age_bracket_gap()
    dose_rescale_exposure()
    hindi_corpus_size()
    persona_space_after_5b()
