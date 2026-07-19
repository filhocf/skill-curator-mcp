"""Tests for skill_curator.db — SQLite storage layer."""

from datetime import datetime, timedelta

import pytest

from skill_curator.db import Database
from skill_curator.models import FeedbackEntry, LifecycleState, Skill


@pytest.fixture
def db() -> Database:
    """In-memory database for isolated tests."""
    return Database(":memory:")


@pytest.fixture
def sample_skill() -> Skill:
    return Skill(
        name="python-rest",
        path="/skills/python-rest.md",
        description="REST APIs in Python",
    )


class TestDatabaseInit:
    def test_initializes_without_error(self, db: Database) -> None:
        assert db is not None


class TestSkillCRUD:
    def test_upsert_and_get_roundtrip(self, db: Database, sample_skill: Skill) -> None:
        db.upsert_skill(sample_skill)
        result = db.get_skill("python-rest")
        assert result is not None
        assert result.name == "python-rest"
        assert result.description == "REST APIs in Python"

    def test_get_nonexistent_returns_none(self, db: Database) -> None:
        assert db.get_skill("nonexistent") is None

    def test_list_skills_no_filter(self, db: Database, sample_skill: Skill) -> None:
        db.upsert_skill(sample_skill)
        db.upsert_skill(Skill(name="other", path="/other.md"))
        results = db.list_skills()
        assert len(results) == 2

    def test_list_skills_filter_by_state(self, db: Database) -> None:
        db.upsert_skill(Skill(name="a", path="/a.md", state=LifecycleState.ACTIVE))
        db.upsert_skill(Skill(name="b", path="/b.md", state=LifecycleState.STALE))
        results = db.list_skills(state=LifecycleState.ACTIVE)
        assert len(results) == 1
        assert results[0].name == "a"


class TestFeedback:
    def test_add_feedback_and_retrieve(self, db: Database, sample_skill: Skill) -> None:
        db.upsert_skill(sample_skill)
        entry = FeedbackEntry(
            skill_name="python-rest", outcome="success", task_description="build API"
        )
        db.add_feedback(entry)
        feedbacks = db.get_feedback("python-rest")
        assert len(feedbacks) == 1
        assert feedbacks[0].outcome == "success"

    def test_update_effectiveness(self, db: Database, sample_skill: Skill) -> None:
        db.upsert_skill(sample_skill)
        db.update_effectiveness("python-rest", 0.8)
        skill = db.get_skill("python-rest")
        assert skill.effectiveness == pytest.approx(0.8)


class TestLifecycle:
    def test_transition_state(self, db: Database, sample_skill: Skill) -> None:
        db.upsert_skill(sample_skill)
        db.transition_state("python-rest", LifecycleState.STALE)
        skill = db.get_skill("python-rest")
        assert skill.state == LifecycleState.STALE

    def test_get_stale_skills(self, db: Database) -> None:
        """Skills not used in 30+ days should appear as stale candidates."""
        old_date = (datetime.utcnow() - timedelta(days=45)).isoformat()
        skill = Skill(name="old-skill", path="/old.md", last_used_at=old_date)
        db.upsert_skill(skill)
        stale = db.get_stale_skills(days=30)
        assert any(s.name == "old-skill" for s in stale)


class TestEmbeddings:
    def test_save_and_search_similar(self, db: Database, sample_skill: Skill) -> None:
        db.upsert_skill(sample_skill)
        embedding = [0.1] * 384
        db.save_embedding("python-rest", embedding)
        query_vec = [0.1] * 384
        results = db.search_similar(query_vec, limit=5)
        assert len(results) >= 1
        assert results[0][0] == "python-rest"

    def test_search_similar_empty_db(self, db: Database) -> None:
        results = db.search_similar([0.1] * 384, limit=5)
        assert results == []
