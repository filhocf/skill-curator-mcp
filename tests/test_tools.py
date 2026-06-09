"""Tests for skill_curator.tools — tool implementations."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from skill_curator.db import Database
from skill_curator.models import LifecycleState, Skill
from skill_curator.tools import (
    skill_archive,
    skill_feedback,
    skill_gaps,
    skill_lifecycle,
    skill_match,
    skill_promote,
    skill_reindex,
    skill_scout,
)


@pytest.fixture
def db() -> Database:
    """In-memory database for testing."""
    return Database(":memory:")


@pytest.fixture
def mock_encoder() -> MagicMock:
    """Mock encoder returning fixed 384-dim vector."""
    encoder = MagicMock()
    encoder.encode.return_value = [0.1] * 384
    return encoder


def _insert_skill(db: Database, name: str, **kwargs) -> None:
    """Helper to insert a skill with defaults."""
    defaults = {"path": f"/skills/{name}.md", "description": f"Skill {name}"}
    defaults.update(kwargs)
    db.upsert_skill(Skill(name=name, **defaults))


class TestSkillMatch:
    """Tests for skill_match."""

    def test_returns_ordered_by_score(self, db: Database, mock_encoder: MagicMock) -> None:
        """skill_match returns results ordered by descending score."""
        _insert_skill(db, "high-eff", effectiveness=0.9)
        _insert_skill(db, "low-eff", effectiveness=0.1)
        # Save embeddings
        db.save_embedding("high-eff", [0.1] * 384)
        db.save_embedding("low-eff", [0.1] * 384)
        results = skill_match(db, "test task", mock_encoder, top_k=5)
        assert len(results) == 2
        assert results[0]["score"] >= results[1]["score"]

    def test_empty_db_returns_empty(self, db: Database, mock_encoder: MagicMock) -> None:
        """skill_match with no skills returns empty list."""
        results = skill_match(db, "any task", mock_encoder)
        assert results == []

    def test_respects_top_k(self, db: Database, mock_encoder: MagicMock) -> None:
        """skill_match returns at most top_k results."""
        for i in range(5):
            _insert_skill(db, f"skill-{i}")
            db.save_embedding(f"skill-{i}", [0.1] * 384)
        results = skill_match(db, "task", mock_encoder, top_k=2)
        assert len(results) <= 2

    def test_profile_boost(self, db: Database, mock_encoder: MagicMock) -> None:
        """skill_match gives higher score to profile-matching skills."""
        _insert_skill(db, "profiled", effectiveness=0.5)
        _insert_skill(db, "generic", effectiveness=0.5)
        db.save_embedding("profiled", [0.1] * 384)
        db.save_embedding("generic", [0.1] * 384)
        results = skill_match(db, "task", mock_encoder, profile=["profiled"], top_k=5)
        profiled = next(r for r in results if r["name"] == "profiled")
        generic = next(r for r in results if r["name"] == "generic")
        assert profiled["score"] > generic["score"]

    def test_excludes_archived(self, db: Database, mock_encoder: MagicMock) -> None:
        """skill_match excludes archived skills."""
        _insert_skill(db, "archived-one", state=LifecycleState.ARCHIVED)
        db.save_embedding("archived-one", [0.1] * 384)
        results = skill_match(db, "task", mock_encoder)
        assert all(r["name"] != "archived-one" for r in results)


class TestSkillFeedback:
    """Tests for skill_feedback."""

    def test_updates_effectiveness(self, db: Database) -> None:
        """skill_feedback updates effectiveness via EMA."""
        _insert_skill(db, "s1", effectiveness=0.5)
        result = skill_feedback(db, "s1", "success")
        # EMA: 0.7*0.5 + 0.3*1.0 = 0.65
        expected = 0.7 * 0.5 + 0.3 * 1.0
        assert abs(result["new_effectiveness"] - expected) < 0.001

    def test_increments_total_uses(self, db: Database) -> None:
        """skill_feedback increments total_uses."""
        _insert_skill(db, "s1", effectiveness=0.5)
        skill_feedback(db, "s1", "success")
        skill = db.get_skill("s1")
        assert skill.total_uses == 1
        assert skill.total_successes == 1

    def test_failure_decreases_effectiveness(self, db: Database) -> None:
        """skill_feedback with failure decreases effectiveness."""
        _insert_skill(db, "s1", effectiveness=0.5)
        result = skill_feedback(db, "s1", "failure")
        # EMA: 0.7*0.5 + 0.3*0.0 = 0.35
        assert result["new_effectiveness"] < 0.5

    def test_nonexistent_skill_returns_error(self, db: Database) -> None:
        """skill_feedback on missing skill returns error."""
        result = skill_feedback(db, "nonexistent", "success")
        assert result["status"] == "error"


class TestSkillGaps:
    """Tests for skill_gaps."""

    def test_returns_gaps(self, db: Database) -> None:
        """skill_gaps returns skills with gap_count > 0."""
        _insert_skill(db, "gappy", gap_count=3)
        gaps = skill_gaps(db)
        assert any(g["name"] == "gappy" for g in gaps)


class TestSkillLifecycle:
    """Tests for skill_lifecycle."""

    def test_categorizes_correctly(self, db: Database) -> None:
        """skill_lifecycle returns correct counts and candidates."""
        _insert_skill(db, "active1", state=LifecycleState.ACTIVE)
        _insert_skill(db, "draft-good", state=LifecycleState.DRAFT, effectiveness=0.8, total_uses=5)
        _insert_skill(db, "bad", state=LifecycleState.ACTIVE, effectiveness=0.1)
        result = skill_lifecycle(db)
        assert result["active"] >= 1
        assert "draft-good" in result["candidates_promote"]
        assert "bad" in result["candidates_archive"]


class TestSkillPromote:
    """Tests for skill_promote."""

    def test_changes_state(self, db: Database) -> None:
        """skill_promote transitions to ACTIVE."""
        _insert_skill(db, "draft1", state=LifecycleState.DRAFT)
        result = skill_promote(db, "draft1")
        assert result["status"] == "promoted"
        assert db.get_skill("draft1").state == LifecycleState.ACTIVE

    def test_nonexistent_returns_error(self, db: Database) -> None:
        """skill_promote on missing skill returns error."""
        result = skill_promote(db, "nope")
        assert result["status"] == "error"


class TestSkillArchive:
    """Tests for skill_archive."""

    def test_changes_state(self, db: Database) -> None:
        """skill_archive transitions to ARCHIVED."""
        _insert_skill(db, "old", state=LifecycleState.ACTIVE)
        result = skill_archive(db, "old", reason="outdated")
        assert result["status"] == "archived"
        assert db.get_skill("old").state == LifecycleState.ARCHIVED

    def test_nonexistent_returns_error(self, db: Database) -> None:
        """skill_archive on missing skill returns error."""
        result = skill_archive(db, "nope")
        assert result["status"] == "error"


class TestSkillReindex:
    """Tests for skill_reindex."""

    def test_returns_correct_count(self, db: Database, mock_encoder: MagicMock, tmp_path: Path) -> None:
        """skill_reindex returns the number of indexed skills."""
        (tmp_path / "a.md").write_text("---\ndescription: A\n---\n")
        (tmp_path / "b.md").write_text("---\ndescription: B\n---\n")
        result = skill_reindex(db, tmp_path, mock_encoder)
        assert result["indexed"] == 2

    def test_empty_dir_returns_zero(self, db: Database, mock_encoder: MagicMock, tmp_path: Path) -> None:
        """skill_reindex with empty dir returns 0."""
        result = skill_reindex(db, tmp_path, mock_encoder)
        assert result["indexed"] == 0


class TestSkillScout:
    """Tests for skill_scout stub."""

    def test_returns_stub_message(self) -> None:
        """skill_scout returns stub message."""
        result = skill_scout()
        assert len(result) == 1
        assert "not yet implemented" in result[0]["message"]

    def test_accepts_params(self) -> None:
        """skill_scout accepts query and gaps_only params."""
        result = skill_scout(query="python", gaps_only=True)
        assert isinstance(result, list)
