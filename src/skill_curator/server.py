"""FastMCP server setup for skill-curator-mcp."""

import logging

from mcp.server.fastmcp import FastMCP

from skill_curator.db import Database
from skill_curator.tools import (
    skill_archive,
    skill_feedback,
    skill_gaps,
    skill_lifecycle,
    skill_match,
    skill_promote,
    skill_reindex,
    skill_scout,
)

logger = logging.getLogger(__name__)

mcp = FastMCP("skill-curator")
_db: Database | None = None


async def get_db() -> Database:
    """Get or initialize the database singleton."""
    global _db
    if _db is None:
        _db = Database()
        await _db.initialize()
    return _db


@mcp.tool()
async def tool_skill_match(task: str) -> list:
    """Match skills to a task description."""
    db = await get_db()
    return await skill_match(db, task)


@mcp.tool()
async def tool_skill_feedback(skill_name: str, outcome: str, session_id: str, task_description: str = "") -> dict:
    """Record feedback for a skill usage."""
    db = await get_db()
    return await skill_feedback(db, skill_name, outcome, session_id, task_description)


@mcp.tool()
async def tool_skill_gaps() -> list:
    """Detect skill gaps."""
    db = await get_db()
    return await skill_gaps(db)


@mcp.tool()
async def tool_skill_lifecycle() -> dict:
    """Get lifecycle status overview."""
    db = await get_db()
    return await skill_lifecycle(db)


@mcp.tool()
async def tool_skill_promote(skill_name: str) -> dict:
    """Promote a skill to active."""
    db = await get_db()
    return await skill_promote(db, skill_name)


@mcp.tool()
async def tool_skill_archive(skill_name: str) -> dict:
    """Archive a skill."""
    db = await get_db()
    return await skill_archive(db, skill_name)


@mcp.tool()
async def tool_skill_reindex(skills_dir: str = "~/.kiro/skills") -> dict:
    """Reindex all skills from filesystem."""
    db = await get_db()
    return await skill_reindex(db, skills_dir)


@mcp.tool()
async def tool_skill_scout() -> dict:
    """Scout for new skills from external sources."""
    db = await get_db()
    return await skill_scout(db)


def main() -> None:
    """Start the MCP server on port 3204."""
    mcp.run(transport="streamable-http", host="127.0.0.1", port=3204)


if __name__ == "__main__":
    main()
