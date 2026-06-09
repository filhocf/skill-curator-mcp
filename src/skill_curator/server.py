"""FastMCP server for skill-curator-mcp."""

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from skill_curator.db import Database
from skill_curator.tools import (
    skill_archive as _skill_archive,
    skill_feedback as _skill_feedback,
    skill_gaps as _skill_gaps,
    skill_lifecycle as _skill_lifecycle,
    skill_match as _skill_match,
    skill_promote as _skill_promote,
    skill_reindex as _skill_reindex,
    skill_scout as _skill_scout,
)

mcp = FastMCP("skill-curator")

_db: Database | None = None
_encoder = None
_skills_dir: Path = Path(os.environ.get("SKILL_CURATOR_SKILLS_DIR", str(Path.home() / ".kiro" / "skills")))


def _get_db() -> Database:
    """Lazy init database."""
    global _db
    if _db is None:
        db_dir = Path(os.environ.get("SKILL_CURATOR_DB_DIR", str(Path.home() / ".local" / "share" / "skill-curator")))
        db_dir.mkdir(parents=True, exist_ok=True)
        _db = Database(str(db_dir / "curator.db"))
    return _db


def _get_encoder():
    """Lazy load sentence-transformers model."""
    global _encoder
    if _encoder is None:
        from sentence_transformers import SentenceTransformer
        _encoder = SentenceTransformer("all-MiniLM-L6-v2")
    return _encoder


@mcp.tool()
def skill_match(task: str, profile: list[str] | None = None, top_k: int = 3) -> list[dict]:
    """Match skills to a task description using semantic similarity."""
    return _skill_match(_get_db(), task, _get_encoder(), profile=profile, top_k=top_k)


@mcp.tool()
def skill_feedback(name: str, outcome: str, session_id: str | None = None, task_description: str = "") -> dict:
    """Record feedback for a skill usage and update effectiveness."""
    return _skill_feedback(_get_db(), name, outcome, session_id=session_id, task_description=task_description)


@mcp.tool()
def skill_gaps(session_id: str | None = None) -> list[dict]:
    """Detect skill gaps — skills with gap_count > 0 or no recent use."""
    return _skill_gaps(_get_db(), session_id=session_id)


@mcp.tool()
def skill_lifecycle() -> dict:
    """Get lifecycle status overview with promotion/archive candidates."""
    return _skill_lifecycle(_get_db())


@mcp.tool()
def skill_promote(name: str) -> dict:
    """Promote a skill to active state."""
    return _skill_promote(_get_db(), name)


@mcp.tool()
def skill_archive(name: str, reason: str | None = None) -> dict:
    """Archive a skill."""
    return _skill_archive(_get_db(), name, reason=reason)


@mcp.tool()
def skill_reindex() -> dict:
    """Reindex all skills from the configured skills directory."""
    return _skill_reindex(_get_db(), _skills_dir, _get_encoder())


@mcp.tool()
def skill_scout(query: str | None = None, gaps_only: bool = False) -> list[dict]:
    """Scout for new skills from external sources (not yet implemented)."""
    return _skill_scout(query=query, gaps_only=gaps_only)


def main() -> None:
    """Start the MCP server."""
    port = int(os.environ.get("SKILL_CURATOR_PORT", "3204"))
    mcp.run(transport="streamable-http", host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
