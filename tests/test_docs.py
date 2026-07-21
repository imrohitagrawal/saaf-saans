"""Citations in the code must point at documents that exist.

A comment citing a decision record is the only thing standing between a
non-obvious choice and somebody undoing it. A citation whose file is missing --
renumbered, renamed, or never written -- is worse than no citation: it reads as
authority and leads nowhere. Three source comments now cite
docs/decisions/0005-averaging-window.md for why PREFER_TWO_PARTICULATES ships
off and why the two sources are never merged.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "saafsaans"
CITATION = re.compile(r"docs/decisions/(\d{4})[-\w.]*")


def test_no_code_cites_a_decision_record_that_does_not_exist():
    cited = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if "__pycache__" in str(path):
            continue
        for match in CITATION.finditer(path.read_text(encoding="utf-8")):
            cited.append((path, match.group(0), match.group(1)))

    assert cited, "no citations found at all; this test would pass on nothing"
    missing = []
    for path, citation, number in cited:
        matches = list((REPO / "docs" / "decisions").glob(f"{number}-*.md"))
        if not matches:
            missing.append(f"{path.name}: {citation}")
    assert not missing, f"code cites decision records that do not exist: {missing}"
