"""Verify outcome ↔ test pairing per the W2 spec §"Pairing rule" (CI-checked).

Every `specs/outcomes/<slug>.md` has a corresponding `tests/test_<slug>.py`,
and every `tests/test_<slug>.py` has a corresponding `specs/outcomes/<slug>.md`.
Exit 1 on any mismatch; exit 0 when both sides agree.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTCOMES_DIR = REPO_ROOT / "specs" / "outcomes"
TESTS_DIR = REPO_ROOT / "tests"


def outcome_slugs() -> set[str]:
    return {p.stem for p in OUTCOMES_DIR.glob("*.md") if not p.name.startswith(".")}


def test_slugs() -> set[str]:
    return {p.stem[len("test_"):] for p in TESTS_DIR.glob("test_*.py")}


def main() -> int:
    outcomes = outcome_slugs()
    tests = test_slugs()

    missing_tests = sorted(outcomes - tests)
    missing_outcomes = sorted(tests - outcomes)

    if not missing_tests and not missing_outcomes:
        print(f"OK: {len(outcomes)} outcome(s) ↔ {len(tests)} test(s) paired.")
        return 0

    if missing_tests:
        print("Outcomes without a matching test:")
        for slug in missing_tests:
            print(f"  - specs/outcomes/{slug}.md (expected tests/test_{slug}.py)")
    if missing_outcomes:
        print("Tests without a matching outcome:")
        for slug in missing_outcomes:
            print(f"  - tests/test_{slug}.py (expected specs/outcomes/{slug}.md)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
