"""Tests for skill_curator.audit — skill quality auditing."""
from pathlib import Path

import pytest

from skill_curator.audit import QualityReport, audit_all, audit_skill

PERFECT_SKILL = """\
---
description: Build production-ready REST APIs with FastAPI
trigger: when user needs to create a new API endpoint
---
# FastAPI REST API

## Quando usar

Use this skill when you need to scaffold a new REST API endpoint with proper
validation, error handling, and documentation.

## Steps

1. Define the Pydantic model for request/response
2. Create the route handler with proper type hints
3. Add error handling and validation
4. Write integration tests

## Limites

- Only for REST APIs, not GraphQL
- Assumes FastAPI framework
"""

MINIMAL_SKILL = """\
# Minimal
Two lines only.
"""


@pytest.fixture
def perfect_skill_path(tmp_path: Path) -> Path:
    p = tmp_path / "perfect.md"
    p.write_text(PERFECT_SKILL)
    return p


@pytest.fixture
def minimal_skill_path(tmp_path: Path) -> Path:
    p = tmp_path / "minimal.md"
    p.write_text(MINIMAL_SKILL)
    return p


class TestAuditSkill:
    def test_perfect_skill_scores_high(self, perfect_skill_path: Path) -> None:
        report = audit_skill(perfect_skill_path)
        assert isinstance(report, QualityReport)
        assert report.score > 0.8

    def test_minimal_skill_scores_low(self, minimal_skill_path: Path) -> None:
        report = audit_skill(minimal_skill_path)
        assert report.score < 0.4

    def test_no_frontmatter_penalizes(self, tmp_path: Path) -> None:
        p = tmp_path / "no-fm.md"
        p.write_text("# No frontmatter\n\nJust a body with enough content to not trigger too_short." * 5)
        report = audit_skill(p)
        assert "no_frontmatter" in report.issues

    def test_no_description_penalizes(self, tmp_path: Path) -> None:
        p = tmp_path / "no-desc.md"
        p.write_text("---\ntrigger: when X happens\n---\n# Title\n\nBody content here." * 5)
        report = audit_skill(p)
        assert "no_description" in report.issues

    def test_no_trigger_penalizes(self, tmp_path: Path) -> None:
        p = tmp_path / "no-trigger.md"
        p.write_text("---\ndescription: A valid description\n---\n# Title\n\nBody content." * 5)
        report = audit_skill(p)
        assert "no_trigger" in report.issues

    def test_generic_description_penalizes(self, tmp_path: Path) -> None:
        p = tmp_path / "generic.md"
        p.write_text("---\ndescription: \"Skill: does something\"\ntrigger: when X\n---\n# Title\n\nBody." * 5)
        report = audit_skill(p)
        assert "generic_description" in report.issues

    def test_too_short_penalizes(self, tmp_path: Path) -> None:
        p = tmp_path / "short.md"
        p.write_text("---\ndescription: Valid\ntrigger: when X\n---\n# Short\nTiny.")
        report = audit_skill(p)
        assert "too_short" in report.issues

    def test_too_long_penalizes(self, tmp_path: Path) -> None:
        p = tmp_path / "long.md"
        p.write_text("---\ndescription: Valid\ntrigger: when X\n---\n# Long\n" + "x" * 5001)
        report = audit_skill(p)
        assert "too_long" in report.issues

    def test_has_when_to_use_section_bonus(self, tmp_path: Path) -> None:
        base = "---\ndescription: Valid\ntrigger: when X\n---\n# Skill\n\nFiller content.\n" * 3
        p_with = tmp_path / "with-when.md"
        p_with.write_text(base + "\n## Quando usar\n\nUse when you need Y.\n")
        p_without = tmp_path / "without-when.md"
        p_without.write_text(base + "\n## Other section\n\nSomething else.\n")
        report_with = audit_skill(p_with)
        report_without = audit_skill(p_without)
        assert report_with.score > report_without.score

    def test_has_steps_section_bonus(self, tmp_path: Path) -> None:
        base = "---\ndescription: Valid\ntrigger: when X\n---\n# Skill\n\nFiller content.\n" * 3
        p_with = tmp_path / "with-steps.md"
        p_with.write_text(base + "\n## Steps\n\n1. Do A\n2. Do B\n")
        p_without = tmp_path / "without-steps.md"
        p_without.write_text(base + "\n## Other section\n\nSomething else.\n")
        report_with = audit_skill(p_with)
        report_without = audit_skill(p_without)
        assert report_with.score > report_without.score


class TestAuditAll:
    def test_audit_all_returns_list(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("---\ndescription: A\ntrigger: t\n---\n# A\nContent." * 5)
        (tmp_path / "b.md").write_text("# B\nMinimal.")
        results = audit_all(tmp_path)
        assert isinstance(results, list)
        assert len(results) == 2
        assert all(isinstance(r, QualityReport) for r in results)

    def test_audit_all_sorted_by_score(self, tmp_path: Path) -> None:
        (tmp_path / "good.md").write_text(PERFECT_SKILL)
        (tmp_path / "bad.md").write_text(MINIMAL_SKILL)
        results = audit_all(tmp_path)
        scores = [r.score for r in results]
        assert scores == sorted(scores)


class TestQualityReport:
    def test_report_fields(self, perfect_skill_path: Path) -> None:
        report = audit_skill(perfect_skill_path)
        assert isinstance(report.name, str)
        assert isinstance(report.path, str)
        assert 0.0 <= report.score <= 1.0
        assert isinstance(report.issues, list)
        assert isinstance(report.suggestions, list)
