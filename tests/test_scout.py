"""Tests for skill_curator.scout — external skill discovery (RED phase)."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from skill_curator.db import Database
from skill_curator.models import Skill, LifecycleState
from skill_curator.scout import scout_skills


@pytest.fixture
def db() -> Database:
    return Database(":memory:")


@pytest.fixture
def db_with_gaps(db: Database) -> Database:
    """DB with skills that have gap_count > 0."""
    db.upsert_skill(Skill(name="k8s-deploy", path="/s/k8s.md", description="Deploy to Kubernetes", gap_count=3))
    db.upsert_skill(Skill(name="terraform", path="/s/tf.md", description="Terraform IaC", gap_count=1))
    db.upsert_skill(Skill(name="python-rest", path="/s/py.md", description="REST APIs", gap_count=0))
    return db


def _github_search_response(repos: list[dict]) -> MagicMock:
    """Build a mock httpx response for GitHub search API."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "total_count": len(repos),
        "items": repos,
    }
    resp.raise_for_status = MagicMock()
    return resp


def _make_repo(name: str, url: str, description: str, has_readme: bool = True) -> dict:
    """Create a GitHub repo dict for mocking."""
    repo = {
        "full_name": f"owner/{name}",
        "html_url": url,
        "description": description,
        "topics": ["claude-code-skills"],
        "stargazers_count": 10,
    }
    if has_readme:
        repo["has_readme"] = True
    return repo


SAMPLE_REPOS = [
    _make_repo("k8s-skills", "https://github.com/owner/k8s-skills", "Kubernetes deployment skills"),
    _make_repo("docker-skills", "https://github.com/owner/docker-skills", "Docker container skills"),
    _make_repo("ci-cd-skills", "https://github.com/owner/ci-cd-skills", "CI/CD pipeline skills"),
]


class TestScoutWithQuery:
    """Test scout_skills with a direct query."""

    @patch("skill_curator.scout.httpx")
    def test_scout_with_query_returns_results(self, mock_httpx, db: Database) -> None:
        """Mock GitHub API returns 3 repos → scout returns 3 results."""
        mock_httpx.get.return_value = _github_search_response(SAMPLE_REPOS)
        result = scout_skills(query="deploy kubernetes", db=db)
        assert len(result["skills"]) == 3

    @patch("skill_curator.scout.httpx")
    def test_scout_results_are_scouted_skills(self, mock_httpx, db: Database) -> None:
        """Each result has name, source_url, description fields."""
        mock_httpx.get.return_value = _github_search_response(SAMPLE_REPOS)
        result = scout_skills(query="deploy kubernetes", db=db)
        for skill in result["skills"]:
            assert "name" in skill
            assert "source_url" in skill
            assert "description" in skill
            assert skill["source_url"].startswith("https://")

    @patch("skill_curator.scout.httpx")
    def test_scout_persists_to_db(self, mock_httpx, db: Database) -> None:
        """After scout, scouted_skills table has records."""
        mock_httpx.get.return_value = _github_search_response(SAMPLE_REPOS)
        scout_skills(query="deploy kubernetes", db=db)
        cur = db.conn.execute("SELECT COUNT(*) FROM scouted_skills")
        count = cur.fetchone()[0]
        assert count == 3

    @patch("skill_curator.scout.httpx")
    def test_scout_dedup(self, mock_httpx, db: Database) -> None:
        """Same URL not duplicated on repeated scout calls."""
        mock_httpx.get.return_value = _github_search_response(SAMPLE_REPOS)
        scout_skills(query="deploy kubernetes", db=db)
        scout_skills(query="deploy kubernetes", db=db)
        cur = db.conn.execute("SELECT COUNT(*) FROM scouted_skills")
        count = cur.fetchone()[0]
        assert count == 3  # Not 6

    @patch("skill_curator.scout.httpx")
    def test_scout_relevance_score(self, mock_httpx, db: Database) -> None:
        """Results have a relevance_score field with numeric value."""
        mock_httpx.get.return_value = _github_search_response(SAMPLE_REPOS)
        result = scout_skills(query="deploy kubernetes", db=db)
        for skill in result["skills"]:
            assert "relevance_score" in skill
            assert isinstance(skill["relevance_score"], float)
            assert 0.0 <= skill["relevance_score"] <= 1.0


class TestScoutGapsOnly:
    """Test scout_skills with gaps_only=True."""

    @patch("skill_curator.scout.httpx")
    def test_scout_gaps_only(self, mock_httpx, db_with_gaps: Database) -> None:
        """Searches based on gaps from DB (skills with gap_count > 0)."""
        mock_httpx.get.return_value = _github_search_response(SAMPLE_REPOS[:2])
        result = scout_skills(gaps_only=True, db=db_with_gaps)
        # Should have searched for gaps (k8s-deploy and terraform have gap_count > 0)
        assert mock_httpx.get.call_count >= 1
        assert len(result["skills"]) > 0


class TestScoutEdgeCases:
    """Test edge cases and error handling."""

    def test_scout_no_query_no_gaps_returns_empty(self, db: Database) -> None:
        """No query and no gaps → informative message, empty list."""
        result = scout_skills(db=db)
        assert result["skills"] == []
        assert "message" in result

    @patch("skill_curator.scout.httpx")
    def test_scout_rate_limit_returns_cached(self, mock_httpx, db: Database) -> None:
        """If last scout was <24h ago, return cached results from DB."""
        # Pre-populate scouted_skills with recent entry
        db.conn.execute(
            "INSERT INTO scouted_skills (source_url, name, description, relevance_score, discovered_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("https://github.com/owner/cached", "cached-skill", "A cached skill", 0.8,
             datetime.utcnow().isoformat()),
        )
        db.conn.commit()
        result = scout_skills(query="anything", db=db)
        # Should NOT call httpx — returns cached
        mock_httpx.get.assert_not_called()
        assert len(result["skills"]) == 1
        assert result["skills"][0]["name"] == "cached-skill"

    @patch("skill_curator.scout.httpx")
    def test_scout_github_error_returns_empty(self, mock_httpx, db: Database) -> None:
        """httpx timeout/error → graceful empty result."""
        import httpx as real_httpx
        mock_httpx.get.side_effect = real_httpx.TimeoutException("timeout")
        result = scout_skills(query="deploy", db=db)
        assert result["skills"] == []
        assert "error" in result or "message" in result

    @patch("skill_curator.scout.httpx")
    def test_scout_filters_irrelevant(self, mock_httpx, db: Database) -> None:
        """Repos without README/SKILL.md are filtered out."""
        repos = [
            _make_repo("good-repo", "https://github.com/o/good", "Has skills", has_readme=True),
            _make_repo("bad-repo", "https://github.com/o/bad", "No skill files", has_readme=False),
        ]
        mock_httpx.get.return_value = _github_search_response(repos)
        result = scout_skills(query="skills", db=db)
        urls = [s["source_url"] for s in result["skills"]]
        assert "https://github.com/o/good" in urls
        assert "https://github.com/o/bad" not in urls


class TestScoutRateLimitExpired:
    """Test that scout fetches fresh data when cache is expired."""

    @patch("skill_curator.scout.httpx")
    def test_scout_fetches_when_cache_expired(self, mock_httpx, db: Database) -> None:
        """If last scout was >24h ago, fetch fresh from GitHub."""
        old_time = (datetime.utcnow() - timedelta(hours=25)).isoformat()
        db.conn.execute(
            "INSERT INTO scouted_skills (source_url, name, description, relevance_score, discovered_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("https://github.com/owner/old", "old-skill", "Old skill", 0.5, old_time),
        )
        db.conn.commit()
        mock_httpx.get.return_value = _github_search_response(SAMPLE_REPOS)
        result = scout_skills(query="deploy", db=db)
        mock_httpx.get.assert_called()
        assert len(result["skills"]) >= 1
