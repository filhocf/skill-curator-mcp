"""Tests for skill_curator.db — SQLite database layer."""

import pytest

from skill_curator.db import Database
from skill_curator.models import FeedbackEntry, LifecycleState, Skill


@pytest.fixture
def db() -> Database:
    """In-memory database for testing."""
    return Database(":memory:")


class TestDatabaseInit:
    """Tests for database initialization and schema."""

    def test_creates_tables(self, db: Database) -> None:
        """Database.__init__ creates all expected tables."""
        cur = db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        tables = {row["name"] for row in cur.fetchall()}
        assert "skills" in tables
        assert "feedback_log" in tables
        assert "scouted_skills" in tables
        assert "skill_embeddings" in tables

    def test_idempotent_init(self) -> None:
        """Creating Database twice on same path doesn't raise."""
        db1 = Database(":memory:")
        # Simulate re-init by calling _create_tables again
        db1._create_tables()
        cur = db1._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='skills'"
        )
        assert cur.fetchone() is not None


class TestUpsertAndGet:
    """Tests for skill upsert and retrieval."""

    def test_upsert_and_get(self, db: Database) -> None:
        """Can insert a skill and retrieve it by name."""
        skill = Skill(name="test-skill", path="/skills/test.md", description="A test")
        db.upsert_skill(skill)
        result = db.get_skill("test-skill")
        assert result is not None
        assert result.name == "test-skill"
        assert result.description == "A test"

    def test_get_nonexistent_returns_none(self, db: Database) -> None:
        """Getting a non-existent skill returns None."""
        assert db.get_skill("no-such-skill") is None

    def test_upsert_updates_existing(self, db: Database) -> None:
        """Upserting with same name updates fields."""
        db.upsert_skill(Skill(name="s", path="/a.md", description="v1"))
        db.upsert_skill(Skill(name="s", path="/b.md", description="v2"))
        result = db.get_skill("s")
        assert result is not None
        assert result.path == "/b.md"
        assert result.description == "v2"


class TestListSkills:
    """Tests for listing skills with optional filter."""

    def test_list_all(self, db: Database) -> None:
        """list_skills without filter returns all skills."""
        db.upsert_skill(Skill(name="a", path="/a.md"))
        db.upsert_skill(Skill(name="b", path="/b.md"))
        assert len(db.list_skills()) == 2

    def test_list_by_state(self, db: Database) -> None:
        """list_skills filters by state string."""
        db.upsert_skill(Skill(name="a", path="/a.md", state=LifecycleState.ACTIVE))
        db.upsert_skill(Skill(name="b", path="/b.md", state=LifecycleState.STALE))
        db.upsert_skill(Skill(name="c", path="/c.md", state=LifecycleState.ACTIVE))
        active = db.list_skills(state="active")
        assert len(active) == 2
        assert all(s.state == LifecycleState.ACTIVE for s in active)


class TestFeedback:
    """Tests for feedback recording."""

    def test_add_feedback(self, db: Database) -> None:
        """add_feedback inserts into feedback_log."""
        db.upsert_skill(Skill(name="s1", path="/s1.md"))
        entry = FeedbackEntry(skill_name="s1", session_id="sess-1", outcome="success")
        db.add_feedback(entry)
        cur = db._conn.execute("SELECT * FROM feedback_log WHERE skill_name='s1'")
        row = cur.fetchone()
        assert row is not None
        assert row["outcome"] == "success"


class TestUpdateEffectiveness:
    """Tests for effectiveness update."""

    def test_update_effectiveness(self, db: Database) -> None:
        """update_effectiveness changes the stored value."""
        db.upsert_skill(Skill(name="s1", path="/s1.md", effectiveness=0.5))
        db.update_effectiveness("s1", 0.8)
        result = db.get_skill("s1")
        assert result is not None
        assert abs(result.effectiveness - 0.8) < 0.01


class TestTransitionState:
    """Tests for state transitions."""

    def test_transition_state(self, db: Database) -> None:
        """transition_state changes the skill's lifecycle state."""
        db.upsert_skill(Skill(name="s1", path="/s1.md", state=LifecycleState.ACTIVE))
        db.transition_state("s1", LifecycleState.STALE)
        result = db.get_skill("s1")
        assert result is not None
        assert result.state == LifecycleState.STALE


class TestGetStaleSkills:
    """Tests for stale skill detection."""

    def test_gets_stale_candidates(self, db: Database) -> None:
        """Skills unused for 30+ days are returned."""
        skill = Skill(
            name="old",
            path="/old.md",
            state=LifecycleState.ACTIVE,
            last_used_at="2026-01-01T00:00:00",
        )
        db.upsert_skill(skill)
        stale = db.get_stale_skills(days=30)
        assert any(s.name == "old" for s in stale)

    def test_recent_skill_not_stale(self, db: Database) -> None:
        """Recently used skills are not returned as stale."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        skill = Skill(name="fresh", path="/f.md", state=LifecycleState.ACTIVE, last_used_at=now)
        db.upsert_skill(skill)
        stale = db.get_stale_skills(days=30)
        assert not any(s.name == "fresh" for s in stale)
