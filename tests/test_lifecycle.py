"""Tests for skill_curator.lifecycle — auto-evolution of skills."""

from datetime import datetime, timedelta

import pytest

from skill_curator.db import Database
from skill_curator.lifecycle import (
    auto_archive,
    auto_stale,
    detect_promotion_candidates,
    generate_draft_skill,
)
from skill_curator.models import LifecycleState, Skill


@pytest.fixture
def db() -> Database:
    return Database(":memory:")


def _days_ago(n: int) -> str:
    return (datetime.utcnow() - timedelta(days=n)).isoformat()


# --- auto_stale ---


class TestAutoStale:
    def test_marks_active_unused_over_30d_as_stale(self, db: Database) -> None:
        db.upsert_skill(
            Skill(
                name="old-skill",
                path="/s.md",
                state=LifecycleState.ACTIVE,
                last_used_at=_days_ago(40),
            )
        )
        result = auto_stale(db, days=30)
        assert "old-skill" in result
        assert db.get_skill("old-skill").state == LifecycleState.STALE

    def test_does_not_mark_recently_used(self, db: Database) -> None:
        db.upsert_skill(
            Skill(
                name="fresh",
                path="/f.md",
                state=LifecycleState.ACTIVE,
                last_used_at=_days_ago(10),
            )
        )
        result = auto_stale(db, days=30)
        assert result == []
        assert db.get_skill("fresh").state == LifecycleState.ACTIVE

    def test_returns_list_of_names(self, db: Database) -> None:
        db.upsert_skill(
            Skill(
                name="a",
                path="/a.md",
                state=LifecycleState.ACTIVE,
                last_used_at=_days_ago(35),
            )
        )
        db.upsert_skill(
            Skill(
                name="b",
                path="/b.md",
                state=LifecycleState.ACTIVE,
                last_used_at=_days_ago(50),
            )
        )
        result = auto_stale(db, days=30)
        assert set(result) == {"a", "b"}

    def test_skips_already_stale(self, db: Database) -> None:
        db.upsert_skill(
            Skill(
                name="already",
                path="/x.md",
                state=LifecycleState.STALE,
                last_used_at=_days_ago(60),
            )
        )
        result = auto_stale(db, days=30)
        assert result == []


# --- auto_archive ---


class TestAutoArchive:
    def test_archives_stale_over_90d(self, db: Database) -> None:
        db.upsert_skill(
            Skill(
                name="ancient",
                path="/a.md",
                state=LifecycleState.STALE,
                last_used_at=_days_ago(100),
            )
        )
        result = auto_archive(db, stale_days=90, min_effectiveness=0.3)
        assert "ancient" in result
        assert db.get_skill("ancient").state == LifecycleState.ARCHIVED

    def test_archives_low_effectiveness_with_enough_uses(self, db: Database) -> None:
        db.upsert_skill(
            Skill(
                name="bad-skill",
                path="/b.md",
                state=LifecycleState.STALE,
                effectiveness=0.2,
                total_uses=5,
                last_used_at=_days_ago(50),
            )
        )
        result = auto_archive(db, stale_days=90, min_effectiveness=0.3)
        assert "bad-skill" in result
        assert db.get_skill("bad-skill").state == LifecycleState.ARCHIVED

    def test_does_not_archive_stale_with_good_effectiveness_under_90d(
        self, db: Database
    ) -> None:
        db.upsert_skill(
            Skill(
                name="decent",
                path="/d.md",
                state=LifecycleState.STALE,
                effectiveness=0.6,
                total_uses=3,
                last_used_at=_days_ago(50),
            )
        )
        result = auto_archive(db, stale_days=90, min_effectiveness=0.3)
        assert result == []
        assert db.get_skill("decent").state == LifecycleState.STALE

    def test_returns_list_of_archived_names(self, db: Database) -> None:
        db.upsert_skill(
            Skill(
                name="x",
                path="/x.md",
                state=LifecycleState.STALE,
                last_used_at=_days_ago(100),
            )
        )
        db.upsert_skill(
            Skill(
                name="y",
                path="/y.md",
                state=LifecycleState.STALE,
                effectiveness=0.1,
                total_uses=10,
                last_used_at=_days_ago(40),
            )
        )
        result = auto_archive(db, stale_days=90, min_effectiveness=0.3)
        assert set(result) == {"x", "y"}


# --- detect_promotion_candidates ---


class TestDetectPromotionCandidates:
    def test_draft_with_high_effectiveness_and_uses(self, db: Database) -> None:
        db.upsert_skill(
            Skill(
                name="good-draft",
                path="/g.md",
                state=LifecycleState.DRAFT,
                effectiveness=0.8,
                total_uses=5,
            )
        )
        candidates = detect_promotion_candidates(db)
        assert len(candidates) == 1
        assert candidates[0].name == "good-draft"

    def test_draft_with_low_effectiveness_not_candidate(self, db: Database) -> None:
        db.upsert_skill(
            Skill(
                name="weak-draft",
                path="/w.md",
                state=LifecycleState.DRAFT,
                effectiveness=0.4,
                total_uses=5,
            )
        )
        candidates = detect_promotion_candidates(db)
        assert candidates == []

    def test_active_skills_not_included(self, db: Database) -> None:
        db.upsert_skill(
            Skill(
                name="active-one",
                path="/a.md",
                state=LifecycleState.ACTIVE,
                effectiveness=0.9,
                total_uses=10,
            )
        )
        candidates = detect_promotion_candidates(db)
        assert candidates == []

    def test_returns_skill_objects(self, db: Database) -> None:
        db.upsert_skill(
            Skill(
                name="promo",
                path="/p.md",
                state=LifecycleState.DRAFT,
                effectiveness=0.75,
                total_uses=4,
            )
        )
        candidates = detect_promotion_candidates(db)
        assert all(isinstance(c, Skill) for c in candidates)


# --- generate_draft_skill ---


class TestGenerateDraftSkill:
    def test_generates_when_gap_count_gte_3(self, db: Database) -> None:
        result = generate_draft_skill("Docker Compose Setup", 3, db)
        assert result is not None
        assert result["name"] == "docker-compose-setup"
        assert "description" in result
        assert "trigger" in result
        assert result["path"] == "~/.kiro/skills/auto-generated/docker-compose-setup.md"

    def test_returns_none_when_gap_count_lt_3(self, db: Database) -> None:
        result = generate_draft_skill("Rare Gap", 2, db)
        assert result is None

    def test_persists_as_draft_in_db(self, db: Database) -> None:
        generate_draft_skill("Kubernetes Debugging", 5, db)
        skill = db.get_skill("kubernetes-debugging")
        assert skill is not None
        assert skill.state == LifecycleState.DRAFT

    def test_does_not_duplicate_existing_skill(self, db: Database) -> None:
        db.upsert_skill(
            Skill(name="existing-skill", path="/e.md", state=LifecycleState.ACTIVE)
        )
        result = generate_draft_skill("Existing Skill", 5, db)
        assert result is None
