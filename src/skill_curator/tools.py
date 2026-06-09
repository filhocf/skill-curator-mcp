"""MCP tool definitions for skill-curator."""

from pathlib import Path
from typing import Any

from skill_curator.db import Database
from skill_curator.indexer import Indexer
from skill_curator.models import FeedbackEntry, LifecycleState


async def skill_match(db: Database, task: str) -> list[dict[str, Any]]:
    """Match skills to a task description."""
    skills = await db.list_skills(state=LifecycleState.ACTIVE)
    return [{"name": s.name, "description": s.description} for s in skills]


async def skill_feedback(db: Database, skill_name: str, outcome: str, session_id: str, task_description: str = "") -> dict[str, str]:
    """Record feedback for a skill usage."""
    entry = FeedbackEntry(skill_name=skill_name, outcome=outcome, session_id=session_id, task_description=task_description)
    await db.add_feedback(entry)
    return {"status": "recorded"}


async def skill_gaps(db: Database) -> list[dict[str, Any]]:
    """Detect skill gaps from recent sessions."""
    return []


async def skill_lifecycle(db: Database) -> dict[str, Any]:
    """Get lifecycle status overview."""
    active = await db.list_skills(state=LifecycleState.ACTIVE)
    stale = await db.get_stale_candidates()
    return {"active": len(active), "stale_candidates": len(stale)}


async def skill_promote(db: Database, skill_name: str) -> dict[str, str]:
    """Promote a skill to active state."""
    skill = await db.get_skill(skill_name)
    if skill:
        skill.state = LifecycleState.ACTIVE
        await db.upsert_skill(skill)
    return {"status": "promoted", "skill": skill_name}


async def skill_archive(db: Database, skill_name: str) -> dict[str, str]:
    """Archive a skill."""
    skill = await db.get_skill(skill_name)
    if skill:
        skill.state = LifecycleState.ARCHIVED
        await db.upsert_skill(skill)
    return {"status": "archived", "skill": skill_name}


async def skill_reindex(db: Database, skills_dir: str = "~/.kiro/skills") -> dict[str, int]:
    """Reindex all skills from filesystem."""
    path = Path(skills_dir).expanduser()
    indexer = Indexer(db=db)
    count = await indexer.reindex_all(skills_dir=path)
    return {"indexed": count}


async def skill_scout(db: Database) -> list[dict[str, Any]]:
    """Scout for new skills from external sources."""
    return []
