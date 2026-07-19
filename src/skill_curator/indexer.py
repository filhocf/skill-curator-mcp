"""Filesystem scanning, markdown parsing, and embedding generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from skill_curator.db import Database
from skill_curator.models import Skill

_EXCLUDED = {
    "README.md",
    "CHANGELOG.md",
    "MEMORY.md",
    "AGENTS.md",
    "ARCHITECTURE.md",
    "PRD.md",
}


def parse_skill_md(path: Path) -> dict[str, Any]:
    """Parse a skill markdown file extracting frontmatter or first-line fallback.

    Args:
        path: Path to a .md file.

    Returns:
        Dict with at least 'description' key.

    Raises:
        FileNotFoundError: If path does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    content = path.read_text(encoding="utf-8")
    result: dict[str, Any] = {"name": path.stem, "path": str(path)}

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            meta = yaml.safe_load(parts[1])
            if isinstance(meta, dict):
                result.update(meta)
                return result

    # Fallback: first line as description
    for line in content.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            result["description"] = stripped
            break
    return result


def scan_skills_dir(base_dir: Path) -> list[Path]:
    """Recursively find .md skill files, excluding special files.

    Args:
        base_dir: Root directory to scan.

    Returns:
        List of Paths to valid skill markdown files.
    """
    if not base_dir.exists():
        return []
    return [p for p in sorted(base_dir.rglob("*.md")) if p.name not in _EXCLUDED]


def reindex_all(skills_dir: Path, db: Database, encoder: Any) -> int:
    """Scan, parse, encode, and upsert all skills.

    Args:
        skills_dir: Root skills directory.
        db: Database instance.
        encoder: Object with .encode(text) -> list[float].

    Returns:
        Number of skills indexed.
    """
    paths = scan_skills_dir(skills_dir)
    count = 0
    for path in paths:
        meta = parse_skill_md(path)
        skill = Skill(
            name=meta.get("name", path.stem),
            path=str(path),
            description=meta.get("description"),
            trigger_text=meta.get("trigger"),
        )
        text = f"{skill.description or ''} {skill.trigger_text or ''}".strip()
        embedding = encoder.encode(text)
        db.upsert_skill(skill)
        db.save_embedding(skill.name, embedding)
        count += 1
    return count
