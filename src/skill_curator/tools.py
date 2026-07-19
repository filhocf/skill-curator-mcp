"""MCP tool functions for skill-curator."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from skill_curator.db import Database
from skill_curator.indexer import reindex_all
from skill_curator.models import FeedbackEntry, LifecycleState
from skill_curator.scoring import (
    composite_score,
    cosine_similarity as _cosine_similarity,
)

_EMA_ALPHA = 0.3
_OUTCOME_VALUES = {"success": 1.0, "partial": 0.5, "failure": 0.0, "irrelevant": 0.5}
_STALE_DAYS = 30
_ARCHIVE_DAYS = 90


def skill_match(
    task: str,
    *,
    db: Database,
    encoder: Any,
    profile: list[str] | None = None,
    top_k: int = 3,
    session_id: str | None = None,
) -> list[dict]:
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
        scored.append(
            {"name": name, "score": round(score, 4), "description": skill.description}
        )

    scored.sort(key=lambda x: x["score"], reverse=True)
    scored = scored[:top_k]

    HIGH_THRESHOLD = 0.7
    LOW_THRESHOLD = 0.5

    best_score = scored[0]["score"] if scored else 0.0
    best_name = scored[0]["name"] if scored else None

    if best_score < LOW_THRESHOLD:
        # Gap detected
        suggested_name = re.sub(r"[^a-z0-9]+", "-", task.lower()).strip("-")[:50]
        suggestion = {
            "gap_detected": True,
            "improvement_opportunity": False,
            "closest_match": {"name": best_name, "score": best_score}
            if best_name
            else None,
            "suggested_action": "create_new",
            "suggested_name": suggested_name,
        }
        # Increment gap_count on closest match
        if best_name:
            db.conn.execute(
                "UPDATE skills SET gap_count = gap_count + 1 WHERE name = ?",
                (best_name,),
            )
            db.conn.commit()
        # Log to gap_log
        db.add_gap_log(
            task_description=task,
            best_match_name=best_name,
            best_match_score=best_score,
            session_id=session_id,
        )
        # Attach suggestion to first result or as standalone
        if scored:
            scored[0]["suggestion"] = suggestion
        else:
            scored = [{"name": None, "score": 0.0, "suggestion": suggestion}]

    elif best_score < HIGH_THRESHOLD:
        # Improvement opportunity
        suggestion = {
            "gap_detected": False,
            "improvement_opportunity": True,
            "closest_match": {"name": best_name, "score": best_score},
            "suggested_action": "evolve_existing",
        }
        scored[0]["suggestion"] = suggestion
    # else: score >= HIGH_THRESHOLD, no suggestion

    return scored


def skill_feedback(
    name: str,
    *,
    outcome: str,
    task_description: str = "",
    db: Database,
    session_id: str | None = None,
) -> dict:
    """Record feedback and update effectiveness via EMA."""
    skill = db.get_skill(name)
    if skill is None:
        return {"error": f"Skill '{name}' not found"}

    outcome_value = _OUTCOME_VALUES.get(outcome, 0.0)
    new_eff = _EMA_ALPHA * outcome_value + (1 - _EMA_ALPHA) * skill.effectiveness
    db.update_effectiveness(name, new_eff)

    # Increment total_uses
    db.conn.execute(
        "UPDATE skills SET total_uses = total_uses + 1, last_used_at = ? WHERE name = ?",
        (datetime.utcnow().isoformat(), name),
    )
    db.conn.commit()

    entry = FeedbackEntry(
        skill_name=name,
        outcome=outcome,
        task_description=task_description,
        session_id=session_id,
    )
    db.add_feedback(entry)

    return {
        "name": name,
        "new_effectiveness": round(new_eff, 6),
        "total_uses": skill.total_uses + 1,
    }


def skill_gaps(
    *,
    db: Database,
    correlate: bool = False,
    encoder: Any = None,
    session_id: str | None = None,
) -> list[dict] | dict:
    """Return skills with gap_count > 0 or no recent use. With correlate=True, cluster gap_log patterns."""
    cutoff = (datetime.utcnow() - timedelta(days=_STALE_DAYS)).isoformat()
    all_skills = db.list_skills()
    known_gaps = []
    for s in all_skills:
        if s.state == LifecycleState.ARCHIVED:
            continue
        has_gap = s.gap_count > 0
        stale_use = s.last_used_at is not None and s.last_used_at < cutoff
        if has_gap or stale_use:
            known_gaps.append(
                {
                    "name": s.name,
                    "gap_count": s.gap_count,
                    "last_used_at": s.last_used_at,
                }
            )

    if not correlate:
        return known_gaps  # backward compatible

    # Correlation: cluster gap_log entries by semantic similarity
    entries = [
        e for e in db.get_gap_log(session_id=session_id) if not e.get("resolved", 0)
    ]
    detected_patterns = []

    if entries and encoder is not None:
        clusters = _cluster_gap_entries(entries, encoder, threshold=0.8)
        for cluster in clusters:
            if len(cluster) >= 3:
                avg_score = sum(e["best_match_score"] or 0 for e in cluster) / len(
                    cluster
                )
                detected_patterns.append(
                    {
                        "theme": cluster[0]["task_description"],  # representative
                        "occurrences": len(cluster),
                        "first_seen": cluster[-1]["timestamp"],  # oldest (ordered DESC)
                        "last_seen": cluster[0]["timestamp"],  # newest
                        "sample_tasks": [e["task_description"] for e in cluster[:3]],
                        "closest_existing_skill": cluster[0].get("best_match_name"),
                        "recommended_action": _determine_action(avg_score),
                        "actionable": True,
                    }
                )

    recommendations = [p for p in detected_patterns if p["actionable"]]

    return {
        "known_gaps": known_gaps,
        "detected_patterns": detected_patterns,
        "recommendations": recommendations,
    }


def _determine_action(avg_score: float) -> str:
    """Determine recommended action based on average match score."""
    if avg_score < 0.3:
        return "create_skill"
    elif avg_score < 0.6:
        return "evolve_skill"
    else:
        return "scout_external"


def _cluster_gap_entries(
    entries: list[dict], encoder: Any, threshold: float = 0.8
) -> list[list[dict]]:
    """Cluster gap_log entries by semantic similarity using greedy approach."""
    if not entries:
        return []

    # Generate embeddings for all entries (batch)
    texts = [e["task_description"] for e in entries]
    try:
        embeddings = encoder.encode(texts)
    except (TypeError, AttributeError):
        # Fallback for encoders that only accept single strings
        embeddings = [encoder.encode(t) for t in texts]

    # Greedy clustering: assign each entry to first cluster with similarity >= threshold
    clusters: list[list[int]] = []  # list of lists of indices

    for i, emb in enumerate(embeddings):
        assigned = False
        for cluster in clusters:
            # Compare with first entry in cluster (representative)
            rep_emb = embeddings[cluster[0]]
            sim = _cosine_similarity(emb, rep_emb)
            if sim >= threshold:
                cluster.append(i)
                assigned = True
                break
        if not assigned:
            clusters.append([i])

    # Convert indices back to entries
    return [[entries[i] for i in cluster] for cluster in clusters]


def skill_lifecycle(*, db: Database) -> dict:
    """Get lifecycle status overview with promotion/archive candidates."""
    all_skills = db.list_skills()
    active = []
    stale = []
    candidates_promote = []
    candidates_archive = []

    for s in all_skills:
        entry = {
            "name": s.name,
            "effectiveness": s.effectiveness,
            "state": s.state.value,
        }
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


def skill_scout(
    *, db: Database | None = None, query: str | None = None, gaps_only: bool = False
) -> dict:
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


def get_onboarding_guide(
    verbosity: str = "full", *, db: "Database | None" = None
) -> dict:
    """Get integration guide for using the skill-curator MCP.

    Args:
        verbosity: "full" (default) or "compact"
        db: Optional database reference (not currently used but accepted for future)
    """
    guide = {
        "version": "2.0",
        "lifecycle": "match → use → feedback → gaps → scout → evolve",
        "integration_protocol": {
            "startup": {
                "action": "skill_gaps(correlate=true)",
                "purpose": "Load pending gaps, present actionable patterns to user",
                "frequency": "every session",
            },
            "pre_task": {
                "action": "skill_match(task='...')",
                "purpose": "Find relevant skill before acting",
                "interpret": {
                    "score >= 0.7": "Strong match. Read skill file and follow it.",
                    "0.5 <= score < 0.7": "Partial match. Follow but note improvement opportunity.",
                    "score < 0.5": "No match. Gap detected and logged. Proceed without skill.",
                },
            },
            "post_task": {
                "action": "skill_feedback(name='...', outcome='success|failure', task_description='...')",
                "purpose": "Update skill effectiveness score via EMA",
                "frequency": "after each skill use",
            },
            "shutdown": {
                "actions": [
                    "skill_feedback (batch from session log)",
                    "skill_gaps(correlate=true) — present patterns to user",
                    "suggest scout/evolve if actionable pattern >= 3 occurrences",
                ]
            },
            "weekly": {
                "action": "skill_audit()",
                "purpose": "Full health check: stale (>30d), unused, low-effectiveness (<0.3)",
            },
        },
        "thresholds": {
            "SKILL_MATCH_HIGH_THRESHOLD": {
                "default": 0.7,
                "meaning": "Above = strong match, no suggestion",
            },
            "SKILL_MATCH_LOW_THRESHOLD": {
                "default": 0.5,
                "meaning": "Below = gap detected and logged",
            },
            "GAP_ACTIONABLE_COUNT": {
                "default": 3,
                "meaning": "Gap occurrences to flag as actionable",
            },
            "SCOUT_AUTO_TRIGGER": {
                "default": 5,
                "meaning": "Gap occurrences to auto-trigger scout",
            },
            "STALE_DAYS": {"default": 30, "meaning": "Days without use to mark stale"},
            "ARCHIVE_DAYS": {
                "default": 90,
                "meaning": "Days stale before auto-archive candidate",
            },
        },
        "scoring_formula": "0.6*similarity + 0.2*effectiveness + 0.2*profile_match; EMA α=0.3",
    }

    if verbosity == "full":
        guide["tools"] = {
            "skill_match": {
                "when": "Before every significant task",
                "params": {
                    "task": "string",
                    "top_k": "int (default 3)",
                    "profile": "list[str] optional",
                },
                "returns": "Top skills with score + suggestion field",
            },
            "skill_feedback": {
                "when": "After using a skill (or at shutdown batch)",
                "params": {
                    "name": "skill name",
                    "outcome": "success|failure|partial",
                    "task_description": "context",
                },
                "returns": "Updated effectiveness score",
            },
            "skill_gaps": {
                "when": "Startup + shutdown",
                "params": {
                    "correlate": "bool (default false)",
                    "encoder": "embedding encoder",
                },
                "returns": "known_gaps + detected_patterns (if correlate=true)",
            },
            "skill_scout": {
                "when": "When gap is recurrent (>=5) or on demand",
                "params": {"query": "search terms", "gaps_only": "bool"},
                "returns": "External skill references with relevance score",
            },
            "skill_evolve": {
                "when": "User explicitly approves skill evolution",
                "params": {
                    "name": "skill to evolve",
                    "context": "what needs improvement",
                },
                "returns": "New version of the skill",
            },
            "skill_lifecycle": {
                "when": "On demand — lifecycle overview",
                "params": {},
                "returns": "Status overview with promotion/archive candidates",
            },
            "skill_audit": {
                "when": "Weekly (first session of the week)",
                "params": {},
                "returns": "Health report: stale, unused, low-effectiveness, pending gaps",
            },
            "skill_reindex": {
                "when": "After adding/modifying skill files on disk",
                "params": {"skills_dir": "path (optional)"},
                "returns": "Count of indexed skills",
            },
            "get_onboarding_guide": {
                "when": "First interaction or when needing protocol reference",
                "params": {"verbosity": "full|compact"},
                "returns": "This guide",
            },
        }

    return guide


def skill_audit(*, skills_dir: str | None = None) -> list[dict]:
    """Audit all skills for quality issues."""
    from skill_curator.audit import audit_all
    import dataclasses
    import os

    if skills_dir is None:
        skills_dir = os.environ.get(
            "SKILL_CURATOR_SKILLS_DIR", os.path.expanduser("~/.kiro/skills")
        )
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
        return {
            "error": eligibility_error,
            "hint": "Use dry_run=True to preview without eligibility check.",
        }

    # Apply evolution
    try:
        original, new_content = apply_evolution(skill_path, correction, section)
    except ValueError as e:
        return {"error": str(e)}

    # Generate diff summary
    orig_lines = original.splitlines()
    new_lines = new_content.splitlines()
    added = len([line for line in new_lines if line not in orig_lines])
    removed = len([line for line in orig_lines if line not in new_lines])
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
    log_evolution(
        db, name, correction, task_description, section, diff_summary, version_path
    )
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


def skill_rollback(
    name: str,
    *,
    version: str | None = None,
    db: "Database",
    skills_dir: str,
    encoder: Any = None,
) -> dict:
    """Rollback a skill to a previous version.

    If version is None, restores the latest version.
    """
    from skill_curator.evolution import get_latest_version

    import os

    if skills_dir is None:
        skills_dir = os.environ.get(
            "SKILL_CURATOR_SKILLS_DIR", os.path.expanduser("~/.kiro/skills")
        )

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
