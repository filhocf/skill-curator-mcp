"""Tests for skill_curator.models — domain dataclasses and enums."""
import pytest

from skill_curator.models import FeedbackEntry, LifecycleState, ScoutedSkill, Skill


class TestLifecycleState:
    """LifecycleState enum validation."""

    def test_has_active(self) -> None:
        assert LifecycleState.ACTIVE.value == "active"

    def test_has_stale(self) -> None:
        assert LifecycleState.STALE.value == "stale"

    def test_has_archived(self) -> None:
        assert LifecycleState.ARCHIVED.value == "archived"

    def test_has_draft(self) -> None:
        assert LifecycleState.DRAFT.value == "draft"

    def test_exactly_four_members(self) -> None:
        assert len(LifecycleState) == 4


class TestSkill:
    """Skill dataclass creation and validation."""

    def test_create_with_defaults(self) -> None:
        skill = Skill(name="test-skill", path="/tmp/test.md")
        assert skill.name == "test-skill"
        assert skill.effectiveness == 0.5
        assert skill.state == LifecycleState.ACTIVE
        assert skill.total_uses == 0

    def test_state_coerce_from_string(self) -> None:
        """String 'draft' should coerce to LifecycleState.DRAFT."""
        skill = Skill(name="s", path="/p", state="draft")
        assert skill.state == LifecycleState.DRAFT

    def test_state_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            Skill(name="s", path="/p", state="invalid_state")


class TestFeedbackEntry:
    """FeedbackEntry outcome validation."""

    @pytest.mark.parametrize("outcome", ["success", "partial", "failure"])
    def test_valid_outcomes(self, outcome: str) -> None:
        entry = FeedbackEntry(skill_name="s", outcome=outcome, task_description="t")
        assert entry.outcome == outcome

    def test_invalid_outcome_raises(self) -> None:
        with pytest.raises(ValueError):
            FeedbackEntry(skill_name="s", outcome="unknown", task_description="t")

    def test_session_id_optional(self) -> None:
        entry = FeedbackEntry(skill_name="s", outcome="success", task_description="t")
        assert entry.session_id is None


class TestScoutedSkill:
    """ScoutedSkill defaults."""

    def test_create_with_defaults(self) -> None:
        scouted = ScoutedSkill(source_url="https://example.com", name="ext-skill")
        assert scouted.status == "new"
        assert scouted.relevance_score is None
