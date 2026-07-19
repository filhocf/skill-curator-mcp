"""Tests for skill_curator.maintenance — daily maintenance script."""

from datetime import datetime, timedelta

import pytest

from skill_curator.db import Database
from skill_curator.maintenance import run_maintenance
from skill_curator.models import LifecycleState, Skill


def _days_ago(n: int) -> str:
    return (datetime.utcnow() - timedelta(days=n)).isoformat()


@pytest.fixture
def db() -> Database:
    return Database(":memory:")


@pytest.fixture
def skills_dir(tmp_path):
    """Create a mix of skill files: good (with frontmatter) and bad (without)."""
    good = tmp_path / "good-skill.md"
    good.write_text(
        "---\ndescription: A well-documented skill\ntrigger: when needed\n---\n\n"
        "## Quando usar\n\n" + "Detailed body content. " * 20 + "\n"
    )
    bad = tmp_path / "bad-skill.md"
    bad.write_text("Just some text without frontmatter.\n")
    return tmp_path


@pytest.fixture
def populated_db(db, skills_dir):
    """DB with mix: active recent, active 40d inactive, stale 100d."""
    db.upsert_skill(
        Skill(
            name="fresh-skill",
            path=str(skills_dir / "good-skill.md"),
            state=LifecycleState.ACTIVE,
            last_used_at=_days_ago(2),
        )
    )
    db.upsert_skill(
        Skill(
            name="inactive-skill",
            path=str(skills_dir / "good-skill.md"),
            state=LifecycleState.ACTIVE,
            last_used_at=_days_ago(40),
        )
    )
    db.upsert_skill(
        Skill(
            name="old-stale",
            path=str(skills_dir / "bad-skill.md"),
            state=LifecycleState.STALE,
            last_used_at=_days_ago(100),
        )
    )
    return db


class TestRunMaintenance:
    def test_maintenance_returns_complete_report(self, populated_db, skills_dir):
        report = run_maintenance(populated_db, skills_dir)
        assert set(report.keys()) == {
            "staled",
            "archived",
            "low_quality_count",
            "total_skills",
        }

    def test_maintenance_stales_inactive(self, populated_db, skills_dir):
        report = run_maintenance(populated_db, skills_dir)
        assert "inactive-skill" in report["staled"]
        assert populated_db.get_skill("inactive-skill").state == LifecycleState.STALE

    def test_maintenance_archives_old_stale(self, populated_db, skills_dir):
        report = run_maintenance(populated_db, skills_dir)
        assert "old-stale" in report["archived"]
        assert populated_db.get_skill("old-stale").state == LifecycleState.ARCHIVED

    def test_maintenance_reports_low_quality(self, populated_db, skills_dir):
        report = run_maintenance(populated_db, skills_dir)
        assert report["low_quality_count"] >= 1  # bad-skill.md has no frontmatter

    def test_maintenance_idempotent(self, populated_db, skills_dir):
        run_maintenance(populated_db, skills_dir)
        second = run_maintenance(populated_db, skills_dir)
        assert second["staled"] == []
        assert second["archived"] == []

    def test_maintenance_preserves_good_skills(self, populated_db, skills_dir):
        run_maintenance(populated_db, skills_dir)
        fresh = populated_db.get_skill("fresh-skill")
        assert fresh.state == LifecycleState.ACTIVE
