"""MCP tool functions for skill-curator."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from skill_curator.db import Database
from skill_curator.indexer import reindex_all
from skill_curator.models import FeedbackEntry, LifecycleState
from skill_curator.scoring import composite_score

_EMA_ALPHA = 0.3
_OUTCOME_VALUES = {"success": 1.0, "partial": 0.5, "failure": 0.0}
_STALE_DAYS = 30
_ARCHIVE_DAYS = 90


def skill_match(task: str, *, db: Database, encoder: Any, profile: list[str] | None = None, top_k: int = 3) -> list[dict]:
    """Match skills to a task using semantic similarity + composite scoring."""
    query_vec = encoder.encode(task)
    results = db.search_similar(query_vec, limit=top_k * 3)
    if not results:
        return []

    scored = []
    for name, distance in results:
        skill = db.get_skill(name)
        if skill is None or skill.state == LifecycleState.ARCHIVED:
            continue
        similarity = 1.0 - distance / 2.0
        profile_match = profile is not None and name in profile
        score = composite_score(similarity, skill.effectiveness, profile_match)
        scored.append({"name": name, "score": round(score, 4), "description": skill.description})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def skill_feedback(name: str, *, outcome: str, task_description: str = "", db: Database, session_id: str | None = None) -> dict:
    """Record feedback and update effectiveness via EMA."""
    skill = db.get_skill(name)
    if skill is None:
        return {"error": f"Skill '{name}' not found"}

    outcome_value = _OUTCOME_VALUES.get(outcome, 0.0)
    new_eff = _EMA_ALPHA * outcome_value + (1 - _EMA_ALPHA) * skill.effectiveness
    db.update_effectiveness(name, new_eff)

    # Increment total_uses
    db.conn.execute("UPDATE skills SET total_uses = total_uses + 1, last_used_at = ? WHERE name = ?",
                    (datetime.utcnow().isoformat(), name))
    db.conn.commit()

    entry = FeedbackEntry(skill_name=name, outcome=outcome, task_description=task_description, session_id=session_id)
    db.add_feedback(entry)

    return {"name": name, "new_effectiveness": round(new_eff, 6), "total_uses": skill.total_uses + 1}


def skill_gaps(*, db: Database, session_id: str | None = None) -> list[dict]:
    """Return skills with gap_count > 0 or no recent use."""
    cutoff = (datetime.utcnow() - timedelta(days=_STALE_DAYS)).isoformat()
    all_skills = db.list_skills()
    gaps = []
    for s in all_skills:
        if s.state == LifecycleState.ARCHIVED:
            continue
        has_gap = s.gap_count > 0
        stale_use = s.last_used_at is not None and s.last_used_at < cutoff
        if has_gap or stale_use:
            gaps.append({"name": s.name, "gap_count": s.gap_count, "last_used_at": s.last_used_at})
    return gaps


def skill_lifecycle(*, db: Database) -> dict:
    """Get lifecycle status overview with promotion/archive candidates."""
    all_skills = db.list_skills()
    active = []
    stale = []
    candidates_promote = []
    candidates_archive = []

    for s in all_skills:
        entry = {"name": s.name, "effectiveness": s.effectiveness, "state": s.state.value}
        if s.state == LifecycleState.ACTIVE:
            active.append(entry)
            # Archive candidate: low effectiveness
            if s.effectiveness < 0.3:
                candidates_archive.append(entry)
        elif s.state == LifecycleState.STALE:
            stale.append(entry)
            # Archive candidate: stale > 90 days
            if s.last_used_at:
                cutoff = (datetime.utcnow() - timedelta(days=_ARCHIVE_DAYS)).isoformat()
                if s.last_used_at < cutoff:
                    candidates_archive.append(entry)
        elif s.state == LifecycleState.DRAFT:
            # Promote candidate: high effectiveness + uses
            if s.effectiveness >= 0.7 and s.total_uses >= 3:
                candidates_promote.append(entry)

    return {
        "active": active,
        "stale": stale,
        "candidates_promote": candidates_promote,
        "candidates_archive": candidates_archive,
    }


def skill_promote(name: str, *, db: Database) -> dict:
    """Promote a skill to active state."""
    skill = db.get_skill(name)
    if skill is None:
        return {"error": f"Skill '{name}' not found"}
    db.transition_state(name, LifecycleState.ACTIVE)
    return {"name": name, "state": "active"}


def skill_archive(name: str, *, db: Database, reason: str | None = None) -> dict:
    """Archive a skill."""
    skill = db.get_skill(name)
    if skill is None:
        return {"error": f"Skill '{name}' not found"}
    db.transition_state(name, LifecycleState.ARCHIVED)
    return {"name": name, "state": "archived", "reason": reason}


def skill_reindex(*, skills_dir: str, db: Database, encoder: Any) -> dict:
    """Reindex all skills from a directory."""
    count = reindex_all(Path(skills_dir), db, encoder)
    return {"indexed": count}


def skill_scout(*, db: Database | None = None, query: str | None = None, gaps_only: bool = False) -> dict:
    """Scout for external skills."""
    from skill_curator.scout import scout_skills
    return scout_skills(query=query, gaps_only=gaps_only, db=db)


def skill_auto_maintain(*, db: Database) -> dict:
    """Run auto-stale and auto-archive in sequence.

    Args:
        db: Database instance.

    Returns:
        Summary dict with staled and archived skill names.
    """
    from skill_curator.lifecycle import auto_archive, auto_stale

    staled = auto_stale(db)
    archived = auto_archive(db)
    return {"staled": staled, "archived": archived}


def get_onboarding_guide() -> dict:
    """Return onboarding guide for MCP clients."""
    return {
        "quick_start": "Call skill_match before each task to get relevant skills.",
        "integration_cycle": {
            "1_startup": "skill_reindex() — rescan skills dir, update embeddings",
            "2_each_task": "skill_match(task='summary') — if score > 0.5, read and follow the skill",
            "3_post_task": "skill_feedback(name='skill', outcome='success|partial|failure') — improves future matching",
            "4_shutdown": "skill_gaps() — detect tasks that had no matching skill",
            "5_weekly": "skill_lifecycle() — review promote/archive candidates",
        },
        "system_prompt_example": (
            "## Skills\n"
            "Before implementing any task, call `skill_match(task=\"summary\")`.\n"
            "If score > 0.5: read the skill and follow it.\n"
            "After using a skill: `skill_feedback(name=\"skill\", outcome=\"success|failure\")`."
        ),
        "tools": [
            {"name": "skill_match", "description": "Semantic skill matching for a task"},
            {"name": "skill_feedback", "description": "Record outcome feedback for a skill"},
            {"name": "skill_gaps", "description": "Detect skill gaps and stale skills"},
            {"name": "skill_lifecycle", "description": "Get lifecycle status overview"},
            {"name": "skill_promote", "description": "Promote a skill to active"},
            {"name": "skill_archive", "description": "Archive a skill"},
            {"name": "skill_reindex", "description": "Reindex skills from filesystem"},
            {"name": "skill_scout", "description": "Scout for external skills"},
            {"name": "get_onboarding_guide", "description": "This guide"},
        ],
        "protocol": "StreamableHTTP on localhost",
        "scoring": "0.6*similarity + 0.2*effectiveness + 0.2*profile_match; EMA α=0.3",
        "notes": "Feedback is critical: without it, effectiveness stays at 0.5 (default) and matching never improves.",
    }


def skill_audit(*, skills_dir: str | None = None) -> list[dict]:
    """Audit all skills for quality issues."""
    from skill_curator.audit import audit_all
    import dataclasses
    import os

    if skills_dir is None:
        skills_dir = os.environ.get("SKILL_CURATOR_SKILLS_DIR", os.path.expanduser("~/.kiro/skills"))
    reports = audit_all(Path(skills_dir))
    return [dataclasses.asdict(r) for r in reports]


def skill_evolve(
    name: str,
    *,
    correction: str,
    task_description: str = "",
    section: str | None = None,
    dry_run: bool = True,
    db: "Database",
    skills_dir: str,
    encoder: Any = None,
) -> dict:
    """Evolve a skill by applying a correction to its content.

    Returns diff summary. If dry_run=False, writes the change and versions the original.
    """
    from skill_curator.evolution import (
        apply_evolution,
        check_evolve_eligibility,
        log_evolution,
        save_version,
        write_evolved_skill,
    )

    skill = db.get_skill(name)
    if not skill:
        return {"error": f"Skill '{name}' not found in database."}

    skill_path = Path(skill.path)
    if not skill_path.exists():
        return {"error": f"Skill file not found: {skill_path}"}

    # Check eligibility (min failures + cooldown)
    eligibility_error = check_evolve_eligibility(name, db)
    if eligibility_error and not dry_run:
        return {"error": eligibility_error, "hint": "Use dry_run=True to preview without eligibility check."}

    # Apply evolution
    try:
        original, new_content = apply_evolution(skill_path, correction, section)
    except ValueError as e:
        return {"error": str(e)}

    # Generate diff summary
    orig_lines = original.splitlines()
    new_lines = new_content.splitlines()
    added = len([l for l in new_lines if l not in orig_lines])
    removed = len([l for l in orig_lines if l not in new_lines])
    diff_summary = f"+{added}/-{removed} lines. Section: {section or 'append'}. Correction: {correction[:100]}"

    if dry_run:
        return {
            "applied": False,
            "dry_run": True,
            "diff_summary": diff_summary,
            "preview_lines": new_content.splitlines()[-10:],
        }

    # Write version + evolve + log + reset effectiveness + reindex
    version_path = save_version(skill_path, original)
    write_evolved_skill(skill_path, new_content)
    log_evolution(db, name, correction, task_description, section, diff_summary, version_path)
    db.update_effectiveness(name, 0.5)  # Reset — skill must prove itself again

    # Reindex if encoder available
    if encoder:
        from skill_curator.tools import skill_reindex as _reindex
        _reindex(skills_dir=skills_dir, db=db, encoder=encoder)

    return {
        "applied": True,
        "diff_summary": diff_summary,
        "version_path": version_path,
        "effectiveness_reset": True,
    }


def skill_rollback(name: str, *, version: str | None = None, db: "Database", skills_dir: str, encoder: Any = None) -> dict:
    """Rollback a skill to a previous version.

    If version is None, restores the latest version.
    """
    from skill_curator.evolution import get_latest_version

    import os
    if skills_dir is None:
        skills_dir = os.environ.get("SKILL_CURATOR_SKILLS_DIR", os.path.expanduser("~/.kiro/skills"))

    skill = db.get_skill(name)
    if not skill:
        return {"error": f"Skill '{name}' not found."}

    skill_path = Path(skill.path)

    if version:
        version_path = Path(version)
    else:
        latest = get_latest_version(skill_path)
        if not latest:
            return {"error": f"No versions found for skill '{name}'."}
        version_path = Path(latest)

    if not version_path.exists():
        return {"error": f"Version file not found: {version_path}"}

    # Restore
    restored_content = version_path.read_text(encoding="utf-8")
    skill_path.write_text(restored_content, encoding="utf-8")

    # Reset effectiveness
    db.update_effectiveness(name, 0.5)

    # Reindex if encoder available
    if encoder:
        from skill_curator.tools import skill_reindex as _reindex
        _reindex(skills_dir=skills_dir, db=db, encoder=encoder)

    return {"restored": True, "from": str(version_path), "effectiveness_reset": True}
