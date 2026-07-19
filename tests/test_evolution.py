"""Tests for skill_curator.evolution — evolution module unit tests."""

from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from skill_curator.db import Database
from skill_curator.evolution import (
    apply_evolution,
    check_evolve_eligibility,
    get_latest_version,
    log_evolution,
    save_version,
    write_evolved_skill,
)


@pytest.fixture
def db() -> Database:
    return Database(":memory:")


@pytest.fixture
def skill_file(tmp_path: Path) -> Path:
    """Create a sample skill markdown file."""
    p = tmp_path / "sample-skill.md"
    p.write_text(
        "# Sample Skill\n\n## Steps\nold step content\n\n## Notes\nsome notes here\n",
        encoding="utf-8",
    )
    return p


def _seed_failures(db: Database, name: str, count: int) -> None:
    """Insert N failure feedback entries for a skill."""
    for i in range(count):
        db.conn.execute(
            "INSERT INTO feedback_log (skill_name, outcome, task_description, created_at) VALUES (?, 'failure', 'task', ?)",
            (name, datetime.now(timezone.utc).isoformat()),
        )
    db.conn.commit()


def _seed_evolution(db: Database, name: str, hours_ago: float) -> None:
    """Insert an evolution record N hours ago."""
    evolved_at = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    db.conn.execute(
        "INSERT INTO skill_evolutions (skill_name, evolved_at, correction) VALUES (?, ?, 'fix')",
        (name, evolved_at),
    )
    db.conn.commit()


# === check_evolve_eligibility ===


class TestCheckEvolveEligibility:
    def test_eligible_when_enough_failures(self, db: Database) -> None:
        _seed_failures(db, "my-skill", 3)
        result = check_evolve_eligibility("my-skill", db, min_failures=2)
        assert result is None

    def test_ineligible_too_few_failures(self, db: Database) -> None:
        _seed_failures(db, "my-skill", 1)
        result = check_evolve_eligibility("my-skill", db, min_failures=2)
        assert result is not None
        assert "1" in result
        assert "Need" in result

    def test_ineligible_cooldown_active(self, db: Database) -> None:
        _seed_failures(db, "my-skill", 3)
        _seed_evolution(db, "my-skill", hours_ago=0.5)
        result = check_evolve_eligibility(
            "my-skill", db, min_failures=2, cooldown_hours=1.0
        )
        assert result is not None
        assert "Cooldown" in result or "cooldown" in result.lower()

    def test_eligible_after_cooldown(self, db: Database) -> None:
        _seed_failures(db, "my-skill", 3)
        _seed_evolution(db, "my-skill", hours_ago=2.0)
        result = check_evolve_eligibility(
            "my-skill", db, min_failures=2, cooldown_hours=1.0
        )
        assert result is None


# === apply_evolution ===


class TestApplyEvolution:
    def test_apply_section_replacement(self, skill_file: Path) -> None:
        original, new_content = apply_evolution(
            skill_file, "new step content", section="Steps"
        )
        assert "old step content" in original
        assert "new step content" in new_content
        assert "old step content" not in new_content

    def test_apply_section_not_found(self, skill_file: Path) -> None:
        with pytest.raises(ValueError, match="NonExistent"):
            apply_evolution(skill_file, "correction", section="NonExistent")

    def test_apply_append_when_no_section(self, skill_file: Path) -> None:
        original, new_content = apply_evolution(
            skill_file, "appended correction", section=None
        )
        assert "## Corrections" in new_content
        assert "appended correction" in new_content

    def test_preserves_other_sections(self, skill_file: Path) -> None:
        original, new_content = apply_evolution(
            skill_file, "replaced steps", section="Steps"
        )
        assert "## Notes" in new_content
        assert "some notes here" in new_content


# === save_version ===


class TestSaveVersion:
    def test_creates_versions_dir(self, tmp_path: Path) -> None:
        skill_path = tmp_path / "skill.md"
        skill_path.write_text("content", encoding="utf-8")
        versions_dir = tmp_path / ".versions"
        assert not versions_dir.exists()
        save_version(skill_path, "content")
        assert versions_dir.exists()

    def test_saves_content_with_timestamp(self, tmp_path: Path) -> None:
        skill_path = tmp_path / "skill.md"
        skill_path.write_text("original", encoding="utf-8")
        result_path = save_version(skill_path, "original")
        saved = Path(result_path).read_text(encoding="utf-8")
        assert saved == "original"
        # Filename should contain the stem and a timestamp pattern
        assert "skill." in Path(result_path).name
        assert ".md" in Path(result_path).name

    def test_returns_path_to_version(self, tmp_path: Path) -> None:
        skill_path = tmp_path / "my-skill.md"
        skill_path.write_text("data", encoding="utf-8")
        result_path = save_version(skill_path, "data")
        assert Path(result_path).exists()
        assert Path(result_path).is_file()


# === write_evolved_skill ===


class TestWriteEvolvedSkill:
    def test_writes_content(self, tmp_path: Path) -> None:
        skill_path = tmp_path / "skill.md"
        skill_path.write_text("old", encoding="utf-8")
        write_evolved_skill(skill_path, "new content here")
        assert skill_path.read_text(encoding="utf-8") == "new content here"

    def test_overwrites_existing(self, tmp_path: Path) -> None:
        skill_path = tmp_path / "skill.md"
        skill_path.write_text("first version", encoding="utf-8")
        write_evolved_skill(skill_path, "second version")
        assert skill_path.read_text(encoding="utf-8") == "second version"


# === log_evolution ===


class TestLogEvolution:
    def test_inserts_row(self, db: Database) -> None:
        log_evolution(
            db,
            skill_name="test-skill",
            correction="fix step 2",
            task_description="improve accuracy",
            section="Steps",
            diff_summary="+2/-1 lines",
            previous_version="/versions/v1.md",
            triggered_by="agent",
        )
        row = db.conn.execute(
            "SELECT * FROM skill_evolutions WHERE skill_name = 'test-skill'"
        ).fetchone()
        assert row is not None

    def test_all_fields_stored(self, db: Database) -> None:
        log_evolution(
            db,
            skill_name="my-skill",
            correction="updated section",
            task_description="fix bug in steps",
            section="Steps",
            diff_summary="+5/-3",
            previous_version="/tmp/v.md",
            triggered_by="user",
        )
        row = db.conn.execute(
            "SELECT skill_name, correction, task_description, section_modified, diff_summary, previous_version, triggered_by FROM skill_evolutions WHERE skill_name = 'my-skill'"
        ).fetchone()
        assert row[0] == "my-skill"
        assert row[1] == "updated section"
        assert row[2] == "fix bug in steps"
        assert row[3] == "Steps"
        assert row[4] == "+5/-3"
        assert row[5] == "/tmp/v.md"
        assert row[6] == "user"


# === get_latest_version ===


class TestGetLatestVersion:
    def test_returns_none_when_no_versions(self, tmp_path: Path) -> None:
        skill_path = tmp_path / "skill.md"
        skill_path.write_text("content", encoding="utf-8")
        result = get_latest_version(skill_path)
        assert result is None

    def test_returns_latest_by_sort(self, tmp_path: Path) -> None:
        skill_path = tmp_path / "skill.md"
        skill_path.write_text("current", encoding="utf-8")

        versions_dir = tmp_path / ".versions"
        versions_dir.mkdir()
        (versions_dir / "skill.2025-01-01T10-00-00.md").write_text(
            "old", encoding="utf-8"
        )
        (versions_dir / "skill.2025-06-15T12-00-00.md").write_text(
            "newer", encoding="utf-8"
        )
        (versions_dir / "skill.2025-03-10T08-00-00.md").write_text(
            "middle", encoding="utf-8"
        )

        result = get_latest_version(skill_path)
        assert result is not None
        assert "2025-06-15" in result
