"""Daily maintenance automation."""
from __future__ import annotations

from pathlib import Path

from skill_curator.audit import audit_all
from skill_curator.db import Database
from skill_curator.lifecycle import auto_archive, auto_stale


def run_maintenance(db: Database, skills_dir: Path) -> dict:
    """Run daily maintenance: stale transitions + archive + quality audit."""
    staled = auto_stale(db)
    archived = auto_archive(db)
    reports = audit_all(skills_dir)
    low_quality = [r for r in reports if r.score < 0.5]
    return {
        "staled": staled,
        "archived": archived,
        "low_quality_count": len(low_quality),
        "total_skills": len(reports),
    }
