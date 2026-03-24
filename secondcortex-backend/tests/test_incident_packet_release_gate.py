from pathlib import Path


def test_release_docs_require_contradiction_and_disproof_sections() -> None:
    checklist = Path("docs/hax/HAX_RELEASE_CHECKLIST.md").read_text(encoding="utf-8").lower()
    assert "contradiction" in checklist
    assert "disproof" in checklist
