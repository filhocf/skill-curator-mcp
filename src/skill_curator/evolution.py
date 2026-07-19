"""Skill evolution — auto-correction loop for skills."""

from __future__ import annotations

import re
import fcntl
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from skill_curator.db import Database


def check_evolve_eligibility(
    name: str, db: "Database", min_failures: int = 2, cooldown_hours: float = 1.0
) -> str | None:
    """Check if a skill is eligible for evolution.

    Returns error message if ineligible, None if OK.
    """
    # Check recent failures (last 7 days)
    rows = db.conn.execute(
        """SELECT COUNT(*) FROM feedback_log
           WHERE skill_name = ? AND outcome = 'failure'
           AND created_at > datetime('now', '-7 days')""",
        (name,),
    ).fetchone()
    failure_count = rows[0] if rows else 0

    if failure_count < min_failures:
        return f"Skill '{name}' has only {failure_count} recent failure(s). Need ≥{min_failures} to evolve."

    # Check cooldown (last evolution <1h ago)
    rows = db.conn.execute(
        """SELECT evolved_at FROM skill_evolutions
           WHERE skill_name = ? ORDER BY evolved_at DESC LIMIT 1""",
        (name,),
    ).fetchone()
    if rows:
        last_evolved = datetime.fromisoformat(rows[0])
        now = datetime.now(timezone.utc)
        hours_since = (now - last_evolved).total_seconds() / 3600
        if hours_since < cooldown_hours:
            return f"Skill '{name}' was evolved {hours_since:.1f}h ago. Cooldown: {cooldown_hours}h."

    return None


def apply_evolution(
    skill_path: Path, correction: str, section: str | None = None
) -> tuple[str, str]:
    """Apply correction to a skill file.

    If section is specified, replaces that section's content.
    If section is None, appends correction as a new section.

    Returns (original_content, new_content).
    """
    original = skill_path.read_text(encoding="utf-8")

    if section:
        # Find the section (## Section Name) and replace its content until next ## or EOF
        pattern = rf"(## {re.escape(section)}\s*\n)(.*?)(?=\n## |\Z)"
        match = re.search(pattern, original, re.DOTALL)
        if not match:
            raise ValueError(f"Section '## {section}' not found in {skill_path.name}")

        header = match.group(1)
        new_content = (
            original[: match.start()]
            + header
            + correction.strip()
            + "\n"
            + original[match.end() :]
        )
    else:
        # Append correction as update note
        new_content = (
            original.rstrip() + "\n\n## Corrections\n\n" + correction.strip() + "\n"
        )

    return original, new_content


def save_version(skill_path: Path, content: str) -> str:
    """Save a version of the skill file before overwriting.

    Returns the path to the version file.
    """
    versions_dir = skill_path.parent / ".versions"
    versions_dir.mkdir(exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    version_name = f"{skill_path.stem}.{timestamp}.md"
    version_path = versions_dir / version_name

    version_path.write_text(content, encoding="utf-8")
    return str(version_path)


def write_evolved_skill(skill_path: Path, new_content: str) -> None:
    """Write evolved skill with file lock to prevent race conditions."""
    with open(skill_path, "w", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        f.write(new_content)
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def log_evolution(
    db: "Database",
    skill_name: str,
    correction: str,
    task_description: str,
    section: str | None,
    diff_summary: str,
    previous_version: str,
    triggered_by: str = "agent",
) -> None:
    """Record evolution event in the database."""
    db.conn.execute(
        """INSERT INTO skill_evolutions
           (skill_name, evolved_at, correction, task_description, section_modified, diff_summary, previous_version, triggered_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            skill_name,
            datetime.now(timezone.utc).isoformat(),
            correction,
            task_description,
            section,
            diff_summary,
            previous_version,
            triggered_by,
        ),
    )
    db.conn.commit()


def get_latest_version(skill_path: Path) -> str | None:
    """Get path to the latest version file for a skill."""
    versions_dir = skill_path.parent / ".versions"
    if not versions_dir.exists():
        return None

    stem = skill_path.stem
    versions = sorted(versions_dir.glob(f"{stem}.*.md"), reverse=True)
    return str(versions[0]) if versions else None
