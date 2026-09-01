"""Generate `docs/hindi-review/unreviewed.json` -- Gate 5a Deliverable 4.

No Hindi reviewer exists yet (Deliverable 2 is not started), so every current
leaf string in `i18n.HI` sits on the unreviewed list, each with an explicit
reason. Auto-generated from the same walk `scripts/build_hindi_review_corpus`
uses, so this list cannot drift from the corpus by hand-editing -- the failure
class `docs/PLAN-gates.md` Gate 2a already records for a hand-maintained list.

Run:
    .venv/bin/python -m scripts.generate_hindi_unreviewed_list

Rewrites `docs/hindi-review/unreviewed.json` in place. Commit the result.
"""
import json
import pathlib

from saafsaans.services import i18n

from scripts.build_hindi_review_corpus import _walk

REASON = "no reviewer assigned yet -- Gate 5a Deliverable 2 not started"

OUT_PATH = (pathlib.Path(__file__).resolve().parent.parent
            / "docs" / "hindi-review" / "unreviewed.json")


def build_unreviewed_list() -> list:
    keys = sorted(".".join(path) for path, _hindi in _walk(i18n.HI))
    return [{"key": key, "reason": REASON} for key in keys]


def main() -> None:
    rows = build_unreviewed_list()
    OUT_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {OUT_PATH}: {len(rows)} keys")


if __name__ == "__main__":
    main()
