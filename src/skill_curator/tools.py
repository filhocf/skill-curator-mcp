"""MCP tool implementations for skill-curator."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from skill_curator.db import Database
from skill_curator.indexer import reindex_all
from skill_curator.models import FeedbackEntry, LifecycleState
from skill_curator.scorer import composite_score

EMA_ALPHA = 0.3
OUTCOME_VALUES = {"success": 1.0, "partial": 0.5, "failure": 0.0}


def skill_match(
    db: Database, task: str, encoder: Any, profile: list[str] | None = None, top_k: int = 3
) -> list[dict]:
    """Encode task, query sqlite-vec KNN, apply composite_score, return top_k."""
    query_embedding = encoder.encode(task)
    if not isinstance(query_embedding, list):
        query_embedding = query_embedding.tolist()
    results = db.search_similar(query_embedding, top_k=top_k * 2)
    if not results:
        return []
    ranked = []
    for name, distance in results:
        skill = db.get_skill(name)
        if skill is None or skill.state != LifecycleState.ACTIVE:
            continue
        similarity = max(0.0, 1.0 - distance)
        profile_match = name in profile if profile else False
        score = composite_score(similarity, skill.effectiveness, profile_match)
        ranked.append({
            "name": skill.name,
            "score": round(score, 4),
            "description": skill.description,
            "path": skill.path,
        })
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked[:top_k]


def skill_feedback(
    db: Database, name: str, outcome: str, session_id: str | None = None, task_description: str = ""
) -> dict:
    """Save feedback + update effectiveness via EMA (α=0.3)."""
    skill = db.get_skill(name)
    if skill is None:
        return {"status": "error", "message": f"Skill '{name}' not found"}
    entry = FeedbackEntry(
        skill_name=name, outcome=outcome, session_id=session_id, task_description=task_description
    )
    db.add_feedback(entry)
    outcome_value = OUTCOME_VALUES[outcome]
    new_eff = (1 - EMA_ALPHA) * skill.effectiveness + EMA_ALPHA * outcome_value
    db.update_effectiveness(name, new_eff)
    # Update usage counters
    skill.total_uses += 1
    if outcome == "success":
        skill.total_successes += 1
    skill.last_used_at = datetime.now(timezone.utc).isoformat()
    skill.effectiveness = new_eff
    db.upsert_skill(skill)
    return {"status": "recorded", "new_effectiveness": round(new_eff, 4)}


def skill_gaps(db: Database, session_id: str | None = None) -> list[dict]:
    """Return active skills with gap_count > 0 or no recent use (30d)."""
    stale = db.get_stale_skills(days=30)
    active = db.list_skills(state="active")
    gaps = []
    for s in active:
        if s.gap_count > 0:
            gaps.append({"name": s.name, "gap_count": s.gap_count, "reason": "gap_detected"})
    for s in stale:
        if not any(g["name"] == s.name for g in gaps):
            gaps.append({"name": s.name, "gap_count": s.gap_count, "reason": "no_recent_use"})
    return gaps


def skill_lifecycle(db: Database) -> dict:
    """Return lifecycle overview with promotion/archive candidates."""
    active = db.list_skills(state="active")
    stale = db.get_stale_skills(days=30)
    all_skills = db.list_skills()
    candidates_promote = [
        s.name for s in all_skills
        if s.state != LifecycleState.ACTIVE and s.effectiveness > 0.7 and s.total_uses >= 3
    ]
    cutoff_90d = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    candidates_archive = [
        s.name for s in all_skills
        if s.state != LifecycleState.ARCHIVED and (
            s.effectiveness < 0.3
            or (s.last_used_at is not None and s.last_used_at < cutoff_90d)
            or (s.last_used_at is None and s.state == LifecycleState.STALE)
        )
    ]
    return {
        "active": len(active),
        "stale": len(stale),
        "candidates_promote": candidates_promote,
        "candidates_archive": candidates_archive,
    }


def skill_promote(db: Database, name: str) -> dict:
    """Transition skill to ACTIVE."""
    skill = db.get_skill(name)
    if skill is None:
        return {"status": "error", "message": f"Skill '{name}' not found"}
    db.transition_state(name, LifecycleState.ACTIVE)
    return {"status": "promoted", "name": name}


def skill_archive(db: Database, name: str, reason: str | None = None) -> dict:
    """Transition skill to ARCHIVED."""
    skill = db.get_skill(name)
    if skill is None:
        return {"status": "error", "message": f"Skill '{name}' not found"}
    db.transition_state(name, LifecycleState.ARCHIVED)
    return {"status": "archived", "name": name, "reason": reason}


def skill_reindex(db: Database, skills_dir: Path, encoder: Any) -> dict:
    """Call reindex_all, return count."""
    count = reindex_all(db, skills_dir, encoder)
    return {"indexed": count}


def skill_scout(query: str | None = None, gaps_only: bool = False) -> list[dict]:
    """Stub: scout not yet implemented."""
    return [{"message": "scout not yet implemented"}]
