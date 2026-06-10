"""Filesystem scan and embedding generation for skills."""

import logging
from pathlib import Path
from typing import Any, Callable, Optional, Protocol

import yaml

from skill_curator.db import Database
from skill_curator.models import Skill

logger = logging.getLogger(__name__)


def parse_skill_md(path: Path) -> Skill:
    """Parse a skill markdown file extracting frontmatter metadata.

    Args:
        path: Path to the .md file.

    Returns:
        Skill dataclass with extracted fields.

    Raises:
        FileNotFoundError: If path does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"Skill file not found: {path}")

    content = path.read_text(encoding="utf-8")
    name = path.stem
    description: Optional[str] = None
    trigger_text: Optional[str] = None

    # Parse YAML frontmatter (between --- delimiters)
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                meta = yaml.safe_load(parts[1])
                if isinstance(meta, dict):
                    description = meta.get("description")
                    trigger_text = meta.get("trigger")
            except yaml.YAMLError:
                pass
            # Use body after frontmatter as description fallback
            body = parts[2].strip()
            if not description and body:
                description = body.split("\n")[0].lstrip("# ").strip()

    return Skill(
        name=name,
        path=str(path),
        description=description,
        trigger_text=trigger_text,
    )


_EXCLUDED_FILENAMES = {
    "README.md", "CHANGELOG.md", "MEMORY.md", "AGENTS.md",
    "ARCHITECTURE.md", "PRD.md",
}


def scan_skills_dir(base_dir: Path) -> list[Path]:
    """Find all *.md files recursively under base_dir, excluding irrelevant docs.

    Args:
        base_dir: Root directory to scan.

    Returns:
        Sorted list of Path objects for each .md file found.
    """
    return sorted(
        p for p in base_dir.rglob("*.md") if p.name not in _EXCLUDED_FILENAMES
    )


def reindex_all(db: Database, skills_dir: Path, encoder: Any) -> int:
    """Scan directory, parse skills, encode embeddings, and upsert into DB.

    Args:
        db: Database instance.
        skills_dir: Directory containing skill .md files.
        encoder: Object with an `encode(text: str) -> list[float]` method.

    Returns:
        Number of skills indexed.
    """
    paths = scan_skills_dir(skills_dir)
    count = 0
    for md_file in paths:
        skill = parse_skill_md(md_file)
        embed_text = f"{skill.description or ''} {skill.trigger_text or ''}".strip()
        if not embed_text:
            # Fallback: use filename + first line of body
            content = md_file.read_text(encoding="utf-8")
            body = content.split("---", 2)[-1].strip() if "---" in content else content.strip()
            first_line = body.split("\n")[0].lstrip("# ").strip() if body else ""
            embed_text = f"{md_file.stem} {first_line}".strip()
        if encoder and embed_text:
            embedding = encoder.encode(embed_text)
            db.save_embedding(skill.name, embedding)
        db.upsert_skill(skill)
        count += 1
        logger.debug("Indexed skill: %s", skill.name)
    return count
