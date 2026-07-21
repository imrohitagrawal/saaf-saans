"""The condition gloss must name the condition exactly once.

`today.html` composes the gloss as "{option_label} — {condition_help}", in the
collapsed persona card and again as `<dt>`/`<dd>` in the open editor. A help
string that opens with its own name therefore renders it twice. Two of the
Hindi values did, and the result -- "अस्थमा — अस्थमा — एक लंबी चलने वाली
बीमारी..." -- was visible only on the rendered Hindi page. Every code-level
check passed it, because neither half is wrong on its own.

The English COPD gloss opens with the expansion of the acronym, not with the
acronym, which is why it reads correctly and must keep doing so.
"""
import pytest
from fastapi.testclient import TestClient

from saafsaans.services import i18n, normalize
from saafsaans.web.main import app

CONDITIONS = ("Fit", "Asthma", "Heart condition", "Pregnancy", "COPD")


@pytest.mark.parametrize("condition", CONDITIONS)
@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_the_gloss_does_not_open_with_the_name_the_template_prepends(condition, lang):
    gloss = i18n.t(lang, "condition_help", condition,
                   normalize.condition_help(condition))
    label = i18n.t(lang, "option_label", condition, condition)
    assert not gloss.startswith(label), (
        f"{lang}/{condition}: the gloss opens with {label!r}, which the template "
        f"already prints in front of it, so the reader sees it twice."
    )


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_the_rendered_card_names_the_condition_once(lang):
    """The property that actually matters, asserted against the HTML rather
    than against the corpus, so a future template change cannot reintroduce it
    while the corpus stays clean."""
    with TestClient(app) as client:
        body = client.get("/", params={"condition": "Asthma", "lang": lang}).text
    label = i18n.t(lang, "option_label", "Asthma", "Asthma")
    assert f"{label} — {label}" not in body
    assert f"{label} — {label} —" not in body


@pytest.mark.parametrize("condition", CONDITIONS)
@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_every_condition_still_has_a_gloss(condition, lang):
    """Guards the guard: the fix above is a deletion, and a deletion that went
    too far would leave a reader with a label and no explanation."""
    gloss = i18n.t(lang, "condition_help", condition,
                   normalize.condition_help(condition))
    assert len(gloss) > 40
