"""External skill discovery via GitHub search — multi-source with cache."""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timedelta
from typing import Any

import httpx

from skill_curator.db import Database

_MAX_REQUESTS = 10
_CACHE_TTL_HOURS = 24
_DEFAULT_SOURCES = ["github"]


def scout_skills(
    *,
    query: str | None = None,
    gaps_only: bool = False,
    db: Database | None = None,
    sources: list[str] | None = None,
    encoder: Any = None,
) -> dict:
    """Scout external sources for skills.

    Args:
        query: Search query for repositories.
        gaps_only: If True, use skill gaps as queries.
        db: Database instance for persistence and caching.
        sources: List of source names to query (default: ["github"]).
        encoder: Optional encoder for relevance scoring (future use).

    Returns:
        Dict with "skills" list, "message" string, and optionally "warnings" list.
    """
    if not query and not gaps_only:
        return {"skills": [], "message": "Provide a query or set gaps_only=True to scout."}

    sources = sources or _DEFAULT_SOURCES
    warnings: list[str] = []

    # Check scout_cache first (new cache layer)
    if db and query and _has_scout_cache_table(db):
        cached = _get_scout_cache(db, query)
        if cached is not None:
            return {"skills": cached, "message": f"Found {len(cached)} skills (cached)"}

    # Legacy rate limit: return cached from scouted_skills if scouted in last 24h
    if db and not _has_scout_cache_table(db):
        cached = _get_cached_legacy(db)
        if cached is not None:
            return {"skills": cached, "message": f"Found {len(cached)} skills (cached)"}

    # Also check legacy cache when scout_cache table exists but has no hit
    # (for backward compat with old tests that insert into scouted_skills directly)
    if db and _has_scout_cache_table(db) and not gaps_only:
        cached = _get_cached_legacy(db)
        if cached is not None:
            return {"skills": cached, "message": f"Found {len(cached)} skills (cached)"}

    # Resolve queries
    queries: list[str] = []
    if gaps_only and db:
        # SC-01 R3: Use gap_log task_descriptions as queries first
        gap_entries = db.get_gap_log()
        if gap_entries:
            seen: set[str] = set()
            for entry in gap_entries:
                desc = entry["task_description"]
                if desc not in seen:
                    queries.append(desc)
                    seen.add(desc)
                if len(queries) >= 5:
                    break
        # Fallback: use skill names with gap_count > 0
        if not queries:
            skills = db.list_skills()
            queries = [s.name for s in skills if s.gap_count > 0]
        if not queries:
            return {"skills": [], "message": "No gaps found."}
    elif query:
        queries = [query]

    if not queries:
        return {"skills": [], "message": "No queries to scout."}

    # Fetch from sources
    all_skills: list[dict] = []
    request_count = 0

    for q in queries:
        if request_count >= _MAX_REQUESTS:
            warnings.append(f"Max requests ({_MAX_REQUESTS}) reached, stopping.")
            break

        for source_name in sources:
            if request_count >= _MAX_REQUESTS:
                break
            try:
                results = _fetch_from_source(source_name, q)
                request_count += 1
                for r in results:
                    r["source"] = source_name
                    if "relevance_score" not in r:
                        r["relevance_score"] = 0.5
                all_skills.extend(results)
            except Exception as e:
                request_count += 1
                warnings.append(f"Source '{source_name}' failed: {str(e)}")

    # Filter: repos without README are excluded
    all_skills = [s for s in all_skills if s.get("_has_readme", True)]
    # Remove internal tracking field
    for s in all_skills:
        s.pop("_has_readme", None)

    # Persist to scouted_skills (legacy) + dedup
    if db:
        for skill in all_skills:
            if not _scouted_skill_exists(db, skill.get("source_url", "")):
                _save_scouted_skill(db, skill)

    # Save to scout_cache (new)
    if db and _has_scout_cache_table(db) and all_skills and query:
        _save_scout_cache(db, query, all_skills)

    result: dict = {"skills": all_skills, "message": f"Found {len(all_skills)} skills"}
    if warnings:
        result["warnings"] = warnings
    return result


def _fetch_from_source(source: str, query: str) -> list[dict]:
    """Dispatch to the appropriate source fetcher."""
    if source == "github":
        return _fetch_github(query)
    elif source == "awesome":
        return _fetch_awesome(query)
    elif source == "pypi":
        return _fetch_pypi(query)
    elif source == "web":
        return _fetch_web(query)
    else:
        raise ValueError(f"Unknown source: {source}")


def _fetch_github(query: str) -> list[dict]:
    """Search GitHub for skill repositories."""
    resp = httpx.get(
        "https://api.github.com/search/repositories",
        params={"q": f"{query} topic:claude-code-skills OR topic:agent-skills"},
        timeout=10.0,
    )
    resp.raise_for_status()
    items = resp.json().get("items", [])
    return [_repo_to_skill(repo) for repo in items]


def _fetch_awesome(query: str) -> list[dict]:
    """Placeholder for awesome-list search."""
    return []


def _fetch_pypi(query: str) -> list[dict]:
    """Placeholder for PyPI search."""
    return []


def _fetch_web(query: str) -> list[dict]:
    """Placeholder for web search."""
    return []


def _repo_to_skill(repo: dict) -> dict:
    """Convert a GitHub repo to a scouted skill dict."""
    desc = repo.get("description", "")
    has_readme = repo.get("has_readme", False)
    return {
        "name": repo["full_name"].split("/")[-1],
        "source_url": repo["html_url"],
        "description": desc,
        "relevance_score": 0.7 if len(desc) > 50 else 0.3,
        "_has_readme": has_readme,
    }


# --- Scout Cache (new) ---


def _has_scout_cache_table(db: Database) -> bool:
    """Check if scout_cache table exists."""
    cur = db.conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='scout_cache'"
    )
    return cur.fetchone() is not None


def _get_scout_cache(db: Database, query: str) -> list[dict] | None:
    """Return cached results if valid (not expired)."""
    query_hash = hashlib.sha256(query.encode()).hexdigest()
    cur = db.conn.execute(
        "SELECT results_json, expires_at FROM scout_cache WHERE query_hash = ?",
        (query_hash,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    results_json, expires_at = row
    if time.time() > expires_at:
        # Expired — delete and return None
        db.conn.execute("DELETE FROM scout_cache WHERE query_hash = ?", (query_hash,))
        db.conn.commit()
        return None
    return json.loads(results_json)


def _save_scout_cache(db: Database, query: str, results: list[dict]) -> None:
    """Cache scout results with TTL."""
    query_hash = hashlib.sha256(query.encode()).hexdigest()
    now = time.time()
    expires_at = now + (_CACHE_TTL_HOURS * 3600)
    db.conn.execute(
        """INSERT OR REPLACE INTO scout_cache (query_hash, query, results_json, source, fetched_at, expires_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (query_hash, query, json.dumps(results), "multi", now, expires_at),
    )
    db.conn.commit()


# --- Legacy cache (scouted_skills table) ---


def _get_cached_legacy(db: Database) -> list[dict] | None:
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
    if not source_url:
        return False
    cur = db.conn.execute("SELECT 1 FROM scouted_skills WHERE source_url = ?", (source_url,))
    return cur.fetchone() is not None


def _save_scouted_skill(db: Database, skill: dict) -> None:
    """Persist a scouted skill to the database."""
    db.conn.execute(
        "INSERT INTO scouted_skills (source_url, name, description, relevance_score, discovered_at) VALUES (?, ?, ?, ?, ?)",
        (skill.get("source_url", ""), skill.get("name", ""), skill.get("description", ""),
         skill.get("relevance_score", 0.5), datetime.utcnow().isoformat()),
    )
    db.conn.commit()
