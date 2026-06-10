"""Tests for skill_curator.tools — MCP tool functions (phase 0.2.0 RED)."""
from datetime import datetime, timedelta

import pytest

from skill_curator.db import Database
from skill_curator.models import LifecycleState, Skill
from skill_curator.tools import (
    get_onboarding_guide,
    skill_archive,
    skill_feedback,
    skill_gaps,
    skill_lifecycle,
    skill_match,
    skill_promote,
    skill_reindex,
    skill_scout,
)


class MockEncoder:
    """Fixed encoder: always returns [0.1]*384."""

    def encode(self, text: str) -> list[float]:
        return [0.1] * 384


class DifferentiatingEncoder:
    """Returns different vectors based on input to test score differentiation."""

    def encode(self, text: str) -> list[float]:
        if "python" in text.lower() or "rest" in text.lower():
            return [0.9] * 384
        if "testing" in text.lower():
            return [0.8] * 192 + [0.1] * 192
        return [0.1] * 384


@pytest.fixture
def db() -> Database:
    return Database(":memory:")


@pytest.fixture
def db_with_skills(db: Database) -> Database:
    """DB with 4 skills + embeddings for tool tests."""
    encoder = MockEncoder()
    skills = [
        Skill(name="python-rest", path="/skills/python-rest.md", description="Build REST APIs in Python",
              effectiveness=0.8, total_uses=5, state=LifecycleState.ACTIVE, profile_tags='["backend"]'),
        Skill(name="testing", path="/skills/testing.md", description="Unit testing patterns",
              effectiveness=0.6, total_uses=2, state=LifecycleState.ACTIVE),
        Skill(name="old-skill", path="/skills/old.md", description="Legacy patterns",
              effectiveness=0.2, total_uses=10, state=LifecycleState.STALE,
              last_used_at=(datetime.utcnow() - timedelta(days=95)).isoformat()),
        Skill(name="archived-skill", path="/skills/archived.md", description="Deprecated tool",
              effectiveness=0.1, total_uses=1, state=LifecycleState.ARCHIVED),
    ]
    for s in skills:
        db.upsert_skill(s)
        text = f"{s.description or ''} {s.trigger_text or ''}".strip()
        db.save_embedding(s.name, encoder.encode(text))
    return db


# === skill_match ===


class TestSkillMatch:
    def test_returns_top_k_ordered_by_score_desc(self, db_with_skills: Database) -> None:
        results = skill_match("build an API", db=db_with_skills, encoder=MockEncoder(), top_k=2)
        assert len(results) <= 2
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_empty_db_returns_empty_list(self, db: Database) -> None:
        results = skill_match("anything", db=db, encoder=MockEncoder())
        assert results == []

    def test_excludes_archived_skills(self, db_with_skills: Database) -> None:
        results = skill_match("deprecated tool", db=db_with_skills, encoder=MockEncoder(), top_k=10)
        names = [r["name"] for r in results]
        assert "archived-skill" not in names

    def test_profile_boost_increases_score(self, db_with_skills: Database) -> None:
        without_profile = skill_match("REST API", db=db_with_skills, encoder=MockEncoder(), top_k=5)
        with_profile = skill_match("REST API", db=db_with_skills, encoder=MockEncoder(),
                                   top_k=5, profile=["python-rest"])
        score_without = next(r["score"] for r in without_profile if r["name"] == "python-rest")
        score_with = next(r["score"] for r in with_profile if r["name"] == "python-rest")
        assert score_with > score_without

    def test_semantically_relevant_score_above_threshold(self, db: Database) -> None:
        """When encoder returns similar vectors, score should be > 0.5."""
        encoder = DifferentiatingEncoder()
        skill = Skill(name="python-rest", path="/s/p.md", description="Python REST APIs",
                      effectiveness=0.7, state=LifecycleState.ACTIVE)
        db.upsert_skill(skill)
        db.save_embedding("python-rest", encoder.encode("Python REST APIs"))
        results = skill_match("python rest endpoint", db=db, encoder=encoder, top_k=3)
        assert len(results) >= 1
        assert results[0]["score"] > 0.5


# === skill_feedback ===


class TestSkillFeedback:
    def test_saves_feedback_and_updates_effectiveness_ema(self, db_with_skills: Database) -> None:
        old_eff = db_with_skills.get_skill("python-rest").effectiveness  # 0.8
        result = skill_feedback("python-rest", outcome="success", task_description="built API",
                                db=db_with_skills)
        new_eff = db_with_skills.get_skill("python-rest").effectiveness
        expected = 0.3 * 1.0 + 0.7 * old_eff  # EMA α=0.3
        assert new_eff == pytest.approx(expected, abs=1e-6)

    def test_increments_total_uses(self, db_with_skills: Database) -> None:
        old_uses = db_with_skills.get_skill("testing").total_uses
        skill_feedback("testing", outcome="success", task_description="wrote tests",
                       db=db_with_skills)
        new_uses = db_with_skills.get_skill("testing").total_uses
        assert new_uses == old_uses + 1

    @pytest.mark.parametrize("outcome,direction", [("success", "up"), ("failure", "down")])
    def test_effectiveness_direction(self, db_with_skills: Database, outcome: str, direction: str) -> None:
        old_eff = db_with_skills.get_skill("testing").effectiveness  # 0.6
        skill_feedback("testing", outcome=outcome, task_description="task", db=db_with_skills)
        new_eff = db_with_skills.get_skill("testing").effectiveness
        if direction == "up":
            assert new_eff > old_eff
        else:
            assert new_eff < old_eff

    def test_nonexistent_skill_returns_error(self, db: Database) -> None:
        result = skill_feedback("nonexistent", outcome="success", task_description="x", db=db)
        assert result.get("error") is not None


# === skill_gaps ===


class TestSkillGaps:
    def test_returns_skills_with_gap_count_gt_zero(self, db: Database) -> None:
        db.upsert_skill(Skill(name="gapped", path="/g.md", gap_count=3, state=LifecycleState.ACTIVE))
        db.upsert_skill(Skill(name="ok", path="/ok.md", gap_count=0, state=LifecycleState.ACTIVE))
        results = skill_gaps(db=db)
        names = [r["name"] for r in results]
        assert "gapped" in names
        assert "ok" not in names

    def test_returns_skills_without_recent_use(self, db: Database) -> None:
        old_date = (datetime.utcnow() - timedelta(days=45)).isoformat()
        db.upsert_skill(Skill(name="stale-use", path="/s.md", last_used_at=old_date,
                              state=LifecycleState.ACTIVE))
        db.upsert_skill(Skill(name="recent", path="/r.md", last_used_at=datetime.utcnow().isoformat(),
                              state=LifecycleState.ACTIVE))
        results = skill_gaps(db=db)
        names = [r["name"] for r in results]
        assert "stale-use" in names
        assert "recent" not in names


# === skill_lifecycle ===


class TestSkillLifecycle:
    def test_categorizes_active_stale_promote_archive(self, db_with_skills: Database) -> None:
        result = skill_lifecycle(db=db_with_skills)
        assert "active" in result
        assert "stale" in result
        assert "candidates_promote" in result
        assert "candidates_archive" in result

    def test_candidate_promote_high_effectiveness_and_uses(self, db: Database) -> None:
        db.upsert_skill(Skill(name="star", path="/s.md", effectiveness=0.8, total_uses=5,
                              state=LifecycleState.DRAFT))
        result = skill_lifecycle(db=db)
        names = [s["name"] for s in result["candidates_promote"]]
        assert "star" in names

    def test_candidate_archive_low_effectiveness(self, db: Database) -> None:
        db.upsert_skill(Skill(name="bad", path="/b.md", effectiveness=0.2, total_uses=10,
                              state=LifecycleState.ACTIVE))
        result = skill_lifecycle(db=db)
        names = [s["name"] for s in result["candidates_archive"]]
        assert "bad" in names

    def test_candidate_archive_stale_over_90d(self, db: Database) -> None:
        old = (datetime.utcnow() - timedelta(days=100)).isoformat()
        db.upsert_skill(Skill(name="ancient", path="/a.md", effectiveness=0.5, total_uses=2,
                              state=LifecycleState.STALE, last_used_at=old))
        result = skill_lifecycle(db=db)
        names = [s["name"] for s in result["candidates_archive"]]
        assert "ancient" in names


# === skill_promote / skill_archive ===


class TestSkillPromote:
    def test_changes_state_to_active(self, db_with_skills: Database) -> None:
        result = skill_promote("old-skill", db=db_with_skills)
        skill = db_with_skills.get_skill("old-skill")
        assert skill.state == LifecycleState.ACTIVE

    def test_nonexistent_returns_error(self, db: Database) -> None:
        result = skill_promote("ghost", db=db)
        assert result.get("error") is not None


class TestSkillArchive:
    def test_changes_state_to_archived(self, db_with_skills: Database) -> None:
        result = skill_archive("testing", db=db_with_skills)
        skill = db_with_skills.get_skill("testing")
        assert skill.state == LifecycleState.ARCHIVED

    def test_nonexistent_returns_error(self, db: Database) -> None:
        result = skill_archive("ghost", db=db)
        assert result.get("error") is not None


# === skill_reindex ===


class TestSkillReindex:
    def test_returns_correct_count(self, tmp_path) -> None:
        (tmp_path / "a.md").write_text("---\ndescription: Skill A\n---\n# A")
        (tmp_path / "b.md").write_text("# Skill B\nContent.")
        db = Database(":memory:")
        result = skill_reindex(skills_dir=str(tmp_path), db=db, encoder=MockEncoder())
        assert result["indexed"] == 2

    def test_empty_dir_returns_zero(self, tmp_path) -> None:
        db = Database(":memory:")
        result = skill_reindex(skills_dir=str(tmp_path), db=db, encoder=MockEncoder())
        assert result["indexed"] == 0


# === skill_scout ===


class TestSkillScout:
    def test_returns_stub_message(self, db: Database) -> None:
        result = skill_scout(db=db)
        assert "message" in result or "stub" in str(result).lower()


# === get_onboarding_guide ===


class TestGetOnboardingGuide:
    def test_returns_expected_keys(self) -> None:
        result = get_onboarding_guide()
        assert "quick_start" in result
        assert "tools" in result
        assert "protocol" in result
        assert "scoring" in result
        assert "notes" in result

    def test_tools_has_nine_entries(self) -> None:
        result = get_onboarding_guide()
        assert len(result["tools"]) == 9
