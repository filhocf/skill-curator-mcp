"""Tests for skill_curator.models — dataclasses and type definitions."""

import pytest

from skill_curator.models import (
    FeedbackEntry,
    LifecycleState,
    ScoutedSkill,
    Skill,
    VALID_OUTCOMES,
)


class TestLifecycleState:
    """Tests for LifecycleState enum."""

    def test_all_states_exist(self) -> None:
        """All 4 lifecycle states are defined."""
        assert LifecycleState.ACTIVE.value == "active"
        assert LifecycleState.STALE.value == "stale"
        assert LifecycleState.ARCHIVED.value == "archived"
        assert LifecycleState.DRAFT.value == "draft"

    def test_state_from_string(self) -> None:
        """LifecycleState can be created from string value."""
        assert LifecycleState("active") == LifecycleState.ACTIVE


class TestSkill:
    """Tests for the Skill dataclass."""

    def test_creation_with_defaults(self) -> None:
        """Skill created with only required fields has sane defaults."""
        skill = Skill(name="test-skill", path="/skills/test.md")
        assert skill.effectiveness == 0.5
        assert skill.total_uses == 0
        assert skill.total_successes == 0
        assert skill.gap_count == 0
        assert skill.state == LifecycleState.ACTIVE
        assert skill.profile_tags == []

    def test_creation_full(self) -> None:
        """Skill accepts all optional fields."""
        skill = Skill(
            name="full",
            path="/full.md",
            description="desc",
            trigger_text="trigger",
            effectiveness=0.8,
            total_uses=10,
            total_successes=7,
            gap_count=2,
            state=LifecycleState.STALE,
            profile_tags=["python"],
            last_used_at="2026-01-01T00:00:00",
            created_at="2025-01-01T00:00:00",
        )
        assert skill.effectiveness == 0.8
        assert skill.profile_tags == ["python"]

    def test_state_coercion_from_string(self) -> None:
        """Skill coerces string state to LifecycleState enum."""
        skill = Skill(name="s", path="/s.md", state="draft")  # type: ignore
        assert skill.state == LifecycleState.DRAFT

    def test_invalid_state_raises(self) -> None:
        """Skill rejects invalid state values."""
        with pytest.raises(ValueError):
            Skill(name="bad", path="/x.md", state="invalid_state")  # type: ignore

    def test_invalid_state_type_raises(self) -> None:
        """Skill rejects non-string, non-enum state."""
        with pytest.raises(TypeError):
            Skill(name="bad", path="/x.md", state=123)  # type: ignore


class TestFeedbackEntry:
    """Tests for the FeedbackEntry dataclass."""

    def test_creation(self) -> None:
        """FeedbackEntry stores all fields correctly."""
        entry = FeedbackEntry(
            skill_name="my-skill",
            session_id="sess-1",
            outcome="success",
            task_description="build API",
        )
        assert entry.skill_name == "my-skill"
        assert entry.outcome == "success"

    def test_valid_outcomes(self) -> None:
        """All valid outcomes are accepted."""
        for outcome in VALID_OUTCOMES:
            entry = FeedbackEntry(skill_name="x", session_id="s", outcome=outcome)
            assert entry.outcome == outcome

    def test_invalid_outcome_raises(self) -> None:
        """Invalid outcome raises ValueError."""
        with pytest.raises(ValueError):
            FeedbackEntry(skill_name="x", session_id="s", outcome="invalid")


class TestScoutedSkill:
    """Tests for the ScoutedSkill dataclass."""

    def test_creation(self) -> None:
        """ScoutedSkill records external discovery metadata."""
        scouted = ScoutedSkill(
            source_url="https://github.com/org/skill",
            name="ext-skill",
            description="Does X",
            relevance_score=0.75,
            matched_gap="testing",
        )
        assert scouted.status == "new"
        assert scouted.relevance_score == 0.75

    def test_custom_status(self) -> None:
        """ScoutedSkill accepts custom status."""
        scouted = ScoutedSkill(
            source_url="http://x",
            name="s",
            description="d",
            relevance_score=0.5,
            matched_gap="g",
            status="adopted",
        )
        assert scouted.status == "adopted"
