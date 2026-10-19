"""Lifecycle automation for skill evolution."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from skill_curator.db import Database
from skill_curator.models import LifecycleState, Skill


def auto_stale(db: Database, days: int = 30) -> list[str]:
    """Mark active skills as stale if unused for more than `days` days.

    Args:
        db: Database instance.
        days: Number of days of inactivity before marking stale.

    Returns:
        List of skill names that were transitioned to STALE.
    """
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    skills = db.list_skills(state=LifecycleState.ACTIVE)
    staled: list[str] = []
    for s in skills:
        if s.last_used_at and s.last_used_at < cutoff:
            db.transition_state(s.name, LifecycleState.STALE)
            staled.append(s.name)
    return staled


def auto_archive(
    db: Database, stale_days: int = 90, min_effectiveness: float = 0.3
) -> list[str]:
    """Archive stale skills that exceed stale_days or have low effectiveness.

    Args:
        db: Database instance.
        stale_days: Days since last use to auto-archive.
        min_effectiveness: Threshold below which skills with >=5 uses are archived.

    Returns:
        List of skill names that were transitioned to ARCHIVED.
    """
    cutoff = (datetime.now(UTC) - timedelta(days=stale_days)).isoformat()
    skills = db.list_skills(state=LifecycleState.STALE)
    archived: list[str] = []
    for s in skills:
        should_archive = False
        if s.last_used_at and s.last_used_at < cutoff:
            should_archive = True
        if s.effectiveness < min_effectiveness and s.total_uses >= 5:
            should_archive = True
        if should_archive:
            db.transition_state(s.name, LifecycleState.ARCHIVED)
            archived.append(s.name)
    return archived


def detect_promotion_candidates(db: Database) -> list[Skill]:
    """Find draft skills eligible for promotion.

    Args:
        db: Database instance.

    Returns:
        List of Skill objects that are drafts with effectiveness > 0.7 and total_uses >= 3.
    """
    drafts = db.list_skills(state=LifecycleState.DRAFT)
    return [s for s in drafts if s.effectiveness > 0.7 and s.total_uses >= 3]


def generate_draft_skill(gap_name: str, gap_count: int, db: Database) -> dict | None:
    """Generate a draft skill from a detected gap.

    Args:
        gap_name: Human-readable gap name.
        gap_count: Number of times the gap was detected.
        db: Database instance.

    Returns:
        Dict with skill metadata if generated, None otherwise.
    """
    if gap_count < 3:
        return None

    slug = gap_name.lower().replace(" ", "-")
    existing = db.get_skill(slug)
    if existing is not None:
        return None

    path = f"~/.kiro/skills/auto-generated/{slug}.md"
    description = f"Auto-generated skill for: {gap_name}"
    trigger = gap_name.lower()

    skill = Skill(
        name=slug,
        path=path,
        description=description,
        trigger_text=trigger,
        state=LifecycleState.DRAFT,
        gap_count=gap_count,
        created_at=datetime.now(UTC).isoformat(),
    )
    db.upsert_skill(skill)

    return {"name": slug, "path": path, "description": description, "trigger": trigger}
