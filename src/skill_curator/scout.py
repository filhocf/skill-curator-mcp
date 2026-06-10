"""External skill discovery via GitHub search."""
from __future__ import annotations

from datetime import datetime, timedelta

import httpx

from skill_curator.db import Database


def scout_skills(*, query: str | None = None, gaps_only: bool = False, db: Database | None = None) -> dict:
    """Scout external sources for skills.

    Args:
        query: Search query for GitHub repositories.
        gaps_only: If True, use skill gaps as queries.
        db: Database instance for persistence and caching.

    Returns:
        Dict with "skills" list and "message" string.
    """
    if not query and not gaps_only:
        return {"skills": [], "message": "Provide a query or set gaps_only=True to scout."}

    # Rate limit: return cached if scouted in last 24h
    if db:
        cached = _get_cached(db)
        if cached is not None:
            return {"skills": cached, "message": f"Found {len(cached)} skills (cached)"}

    # Resolve queries from gaps
    queries = []
    if gaps_only and db:
        skills = db.list_skills()
        queries = [s.name for s in skills if s.gap_count > 0]
        if not queries:
            return {"skills": [], "message": "No gaps found."}
    elif query:
        queries = [query]

    # Fetch from GitHub
    all_skills: list[dict] = []
    for q in queries:
        repos = _fetch_repos(q)
        for repo in repos:
            if not repo.get("description") or not repo.get("has_readme", False):
                continue
            skill = _repo_to_skill(repo)
            if db and _scouted_skill_exists(db, skill["source_url"]):
                continue
            all_skills.append(skill)
            if db:
                _save_scouted_skill(db, skill)

    return {"skills": all_skills, "message": f"Found {len(all_skills)} skills"}


def _fetch_repos(query: str) -> list[dict]:
    """Search GitHub for skill repositories."""
    try:
        resp = httpx.get(
            "https://api.github.com/search/repositories",
            params={"q": f"{query} topic:claude-code-skills OR topic:agent-skills"},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json().get("items", [])
    except Exception:
        return []


def _repo_to_skill(repo: dict) -> dict:
    """Convert a GitHub repo to a scouted skill dict."""
    desc = repo.get("description", "")
    return {
        "name": repo["full_name"].split("/")[-1],
        "source_url": repo["html_url"],
        "description": desc,
        "relevance_score": 0.7 if len(desc) > 50 else 0.3,
    }


def _get_cached(db: Database) -> list[dict] | None:
    """Return cached skills if any were discovered in the last 24h."""
    cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
    cur = db.conn.execute(
        "SELECT source_url, name, description, relevance_score FROM scouted_skills WHERE discovered_at > ?",
        (cutoff,),
    )
    rows = cur.fetchall()
    if not rows:
        return None
    return [{"source_url": r[0], "name": r[1], "description": r[2], "relevance_score": r[3]} for r in rows]


def _scouted_skill_exists(db: Database, source_url: str) -> bool:
    """Check if a scouted skill URL already exists in the DB."""
    cur = db.conn.execute("SELECT 1 FROM scouted_skills WHERE source_url = ?", (source_url,))
    return cur.fetchone() is not None


def _save_scouted_skill(db: Database, skill: dict) -> None:
    """Persist a scouted skill to the database."""
    db.conn.execute(
        "INSERT INTO scouted_skills (source_url, name, description, relevance_score, discovered_at) VALUES (?, ?, ?, ?, ?)",
        (skill["source_url"], skill["name"], skill["description"], skill["relevance_score"], datetime.utcnow().isoformat()),
    )
    db.conn.commit()
