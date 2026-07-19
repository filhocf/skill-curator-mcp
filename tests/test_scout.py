"""Tests for skill_curator.scout — external skill discovery (RED phase)."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from skill_curator.db import Database
from skill_curator.models import Skill
from skill_curator.scout import scout_skills


@pytest.fixture
def db() -> Database:
    return Database(":memory:")


@pytest.fixture
def db_with_gaps(db: Database) -> Database:
    """DB with skills that have gap_count > 0."""
    db.upsert_skill(
        Skill(
            name="k8s-deploy",
            path="/s/k8s.md",
            description="Deploy to Kubernetes",
            gap_count=3,
        )
    )
    db.upsert_skill(
        Skill(
            name="terraform", path="/s/tf.md", description="Terraform IaC", gap_count=1
        )
    )
    db.upsert_skill(
        Skill(name="python-rest", path="/s/py.md", description="REST APIs", gap_count=0)
    )
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
    if has_readme is not None:
        repo["has_readme"] = has_readme
    return repo


SAMPLE_REPOS = [
    _make_repo(
        "k8s-skills",
        "https://github.com/owner/k8s-skills",
        "Kubernetes deployment skills",
    ),
    _make_repo(
        "docker-skills",
        "https://github.com/owner/docker-skills",
        "Docker container skills",
    ),
    _make_repo(
        "ci-cd-skills", "https://github.com/owner/ci-cd-skills", "CI/CD pipeline skills"
    ),
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
            (
                "https://github.com/owner/cached",
                "cached-skill",
                "A cached skill",
                0.8,
                datetime.utcnow().isoformat(),
            ),
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
            _make_repo(
                "good-repo", "https://github.com/o/good", "Has skills", has_readme=True
            ),
            _make_repo(
                "bad-repo",
                "https://github.com/o/bad",
                "No skill files",
                has_readme=False,
            ),
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


# === SC-01 RED: Multi-Source + Cache ===


class MockResponse:
    """Minimal httpx.Response mock."""

    def __init__(self, json: dict | None = None, status_code: int = 200):
        self._json = json or {}
        self.status_code = status_code

    def json(self) -> dict:
        return self._json

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


@pytest.fixture
def mock_httpx(monkeypatch):
    """Mock httpx.get to return controlled responses without real HTTP."""
    call_count = {"n": 0}

    def mock_get(url, **kwargs):
        call_count["n"] += 1
        from urllib.parse import urlparse

        if urlparse(url).hostname == "api.github.com":
            return MockResponse(
                json={
                    "items": [
                        {
                            "full_name": "user/skill-test",
                            "html_url": "https://github.com/user/skill-test",
                            "description": "A test skill for deployment automation",
                            "has_readme": True,
                            "topics": ["claude-code-skills"],
                            "stargazers_count": 5,
                        }
                    ]
                }
            )
        return MockResponse(json={"items": []})

    monkeypatch.setattr("skill_curator.scout.httpx.get", mock_get)
    return call_count


@pytest.fixture
def db_with_cache(db: Database) -> Database:
    """DB with scout_cache table and entries."""
    db.conn.execute("""
        CREATE TABLE IF NOT EXISTS scout_cache (
            query_hash TEXT PRIMARY KEY,
            query TEXT NOT NULL,
            results_json TEXT NOT NULL,
            source TEXT NOT NULL,
            fetched_at REAL NOT NULL,
            expires_at REAL NOT NULL
        )
    """)
    db.conn.commit()
    return db


@pytest.fixture
def db_with_gap_log(db: Database) -> Database:
    """DB with gap_log entries for directed scouting."""
    import time

    now = time.time()
    db.conn.execute(
        "INSERT INTO gap_log (timestamp, task_description, best_match_name, best_match_score, session_id) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            now,
            "deploy FastAPI to kubernetes with helm charts",
            "k8s-deploy",
            0.4,
            "sess-1",
        ),
    )
    db.conn.execute(
        "INSERT INTO gap_log (timestamp, task_description, best_match_name, best_match_score, session_id) "
        "VALUES (?, ?, ?, ?, ?)",
        (now, "create terraform module for RDS Aurora", "terraform", 0.3, "sess-1"),
    )
    db.conn.commit()
    return db


class TestScoutMultiSource:
    """SC-01 RED: Multi-source scout with caching and source metadata."""

    def test_scout_accepts_sources_param(self, db: Database, mock_httpx) -> None:
        """scout_skills(query=..., sources=["github"], db=db) does not raise TypeError."""
        # The 'sources' parameter must exist in the function signature.
        result = scout_skills(query="test", sources=["github"], db=db)
        assert "skills" in result

    def test_scout_cache_hit_returns_cached(self, db_with_cache: Database) -> None:
        """Insert a valid scout_cache entry. Same query returns cached without HTTP call."""
        import hashlib
        import json
        import time

        query = "deploy kubernetes"
        query_hash = hashlib.sha256(query.encode()).hexdigest()
        cached_results = [
            {
                "name": "cached-k8s",
                "source_url": "https://github.com/x/cached-k8s",
                "description": "Cached skill",
                "source": "github",
                "relevance_score": 0.8,
            }
        ]
        now = time.time()
        db_with_cache.conn.execute(
            "INSERT INTO scout_cache (query_hash, query, results_json, source, fetched_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (query_hash, query, json.dumps(cached_results), "github", now, now + 3600),
        )
        db_with_cache.conn.commit()

        # Call scout — should return cached results without HTTP
        with patch("skill_curator.scout.httpx") as patched_httpx:
            result = scout_skills(query=query, sources=["github"], db=db_with_cache)
            patched_httpx.get.assert_not_called()

        assert len(result["skills"]) == 1
        assert result["skills"][0]["name"] == "cached-k8s"

    def test_scout_cache_expired_refetches(
        self, db_with_cache: Database, mock_httpx
    ) -> None:
        """Expired cache entry → refetch from source."""
        import hashlib
        import json
        import time

        query = "deploy kubernetes"
        query_hash = hashlib.sha256(query.encode()).hexdigest()
        expired_results = [
            {
                "name": "old-cached",
                "source_url": "https://github.com/x/old",
                "description": "Expired cached skill",
                "source": "github",
                "relevance_score": 0.5,
            }
        ]
        now = time.time()
        # expires_at in the past
        db_with_cache.conn.execute(
            "INSERT INTO scout_cache (query_hash, query, results_json, source, fetched_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                query_hash,
                query,
                json.dumps(expired_results),
                "github",
                now - 7200,
                now - 3600,
            ),
        )
        db_with_cache.conn.commit()

        result = scout_skills(query=query, sources=["github"], db=db_with_cache)
        # Should NOT return the expired "old-cached" entry
        names = [s["name"] for s in result["skills"]]
        assert "old-cached" not in names
        # Should have made at least one HTTP call (via mock_httpx fixture)
        assert mock_httpx["n"] >= 1

    def test_scout_uses_gap_log_when_gaps_only(
        self, db_with_gap_log: Database, mock_httpx
    ) -> None:
        """gaps_only=True uses gap_log task_descriptions as queries (not just skill names)."""
        result = scout_skills(gaps_only=True, sources=["github"], db=db_with_gap_log)
        # The mock returns results for github.com URLs, so we should get results
        assert len(result["skills"]) > 0
        # Verify queries came from gap_log task descriptions (check that HTTP was called
        # at least twice — one per gap_log entry's task_description)
        assert mock_httpx["n"] >= 2

    def test_scout_result_has_source_field(self, db: Database, mock_httpx) -> None:
        """Each result has a 'source' field indicating provenance (github/awesome/pypi/web)."""
        result = scout_skills(query="deploy", sources=["github"], db=db)
        assert len(result["skills"]) > 0
        for skill in result["skills"]:
            assert "source" in skill, (
                f"Skill {skill.get('name')} missing 'source' field"
            )
            assert skill["source"] in ("github", "awesome", "pypi", "web")

    def test_scout_result_has_relevance_score(self, db: Database, mock_httpx) -> None:
        """Each result has 'relevance_score' field that is a float."""
        result = scout_skills(query="deploy", sources=["github"], db=db)
        assert len(result["skills"]) > 0
        for skill in result["skills"]:
            assert "relevance_score" in skill
            assert isinstance(skill["relevance_score"], float)

    def test_scout_graceful_on_source_failure(self, db: Database, monkeypatch) -> None:
        """If one source raises, scout returns results from others + 'warnings' field."""
        call_count = {"n": 0}

        def mock_get(url, **kwargs):
            call_count["n"] += 1
            from urllib.parse import urlparse

            if urlparse(url).hostname == "api.github.com":
                raise ConnectionError("GitHub is down")
            # Other sources return valid data
            return MockResponse(
                json={
                    "items": [
                        {
                            "full_name": "alt/fallback-skill",
                            "html_url": "https://other.com/alt/fallback-skill",
                            "description": "A skill from alternate source",
                            "has_readme": True,
                            "topics": ["agent-skills"],
                            "stargazers_count": 3,
                        }
                    ]
                }
            )

        monkeypatch.setattr("skill_curator.scout.httpx.get", mock_get)

        result = scout_skills(query="deploy", sources=["github", "awesome"], db=db)
        # Should have a "warnings" field with the error info
        assert "warnings" in result, "Expected 'warnings' field when a source fails"
        assert len(result["warnings"]) > 0

    def test_scout_max_requests_limit(self, db: Database, mock_httpx) -> None:
        """Scout makes at most 10 HTTP requests total, regardless of query/source count."""
        # Use many sources to try to trigger >10 requests
        scout_skills(
            query="deploy kubernetes helm terraform docker ansible",
            sources=["github", "awesome", "pypi", "web"],
            db=db,
        )
        assert mock_httpx["n"] <= 10, (
            f"Made {mock_httpx['n']} HTTP requests, max allowed is 10"
        )


# === TestScoutIngest — RFC-SC-06 ===


class TestScoutIngest:
    """Tests for scout_ingest: fetch external repo, compare, propose evolution."""

    MOCK_README = (
        "# Awesome Deploy Skills\n\n"
        "## Installation\n\n"
        "Run pip install awesome-deploy to get started with deployment automation.\n"
        "This package provides a set of curated deployment skills.\n\n"
        "## Configuration\n\n"
        "Set the following environment variables before using:\n"
        "- DEPLOY_TARGET: The target environment (dev, staging, prod)\n"
        "- DEPLOY_TIMEOUT: Timeout in seconds for deployment operations\n\n"
        "## Rollback Procedures\n\n"
        "When a deployment fails, follow these rollback steps:\n"
        "1. Identify the failed component\n"
        "2. Run the rollback command for that component\n"
        "3. Verify system health after rollback\n"
    )

    LOCAL_SKILL_CONTENT = (
        "# Deploy Skill\n\n"
        "## Installation\n\n"
        "Use pip install deploy-tool for local deployment.\n"
        "Basic setup for deploying applications.\n\n"
    )

    @pytest.fixture
    def mock_encoder(self):
        """Minimal encoder mock that returns a fixed-size vector."""
        enc = MagicMock()
        enc.encode.return_value = [0.1] * 384
        return enc

    @pytest.fixture
    def db_with_skill(self, tmp_path, db: Database, mock_encoder):
        """DB with a local skill indexed and file on disk."""
        skill_file = tmp_path / "deploy.md"
        skill_file.write_text(self.LOCAL_SKILL_CONTENT, encoding="utf-8")
        db.upsert_skill(
            Skill(
                name="deploy",
                path=str(skill_file),
                description="Deploy applications",
            )
        )
        db.save_embedding("deploy", [0.1] * 384)
        return db

    def _mock_httpx_get(self, monkeypatch):
        """Set up httpx.get mock returning README with 3 H2 sections."""
        import base64

        readme_b64 = base64.b64encode(self.MOCK_README.encode()).decode()

        def mock_get(url, **kwargs):
            resp = MagicMock()
            if "/readme" in url:
                resp.status_code = 200
                resp.json.return_value = {"content": readme_b64, "encoding": "base64"}
                resp.raise_for_status = MagicMock()
            elif "/contents/skills" in url:
                resp.status_code = 404
                resp.json.return_value = {"message": "Not Found"}
            else:
                resp.status_code = 404
            return resp

        monkeypatch.setattr("skill_curator.scout.httpx.get", mock_get)

    def test_invalid_url_returns_error(self, db: Database, mock_encoder):
        """Non-GitHub URL returns error dict."""
        from skill_curator.scout import scout_ingest

        result = scout_ingest(
            source_url="https://gitlab.com/user/repo",
            db=db,
            encoder=mock_encoder,
            skills_dir="/tmp",
        )
        assert "error" in result
        assert "Invalid GitHub URL" in result["error"]

    def test_returns_target_skill(
        self, monkeypatch, tmp_path, db_with_skill, mock_encoder
    ):
        """Result has 'target_skill' key."""
        from skill_curator.scout import scout_ingest

        self._mock_httpx_get(monkeypatch)
        result = scout_ingest(
            source_url="https://github.com/user/awesome-deploy",
            target_skill="deploy",
            db=db_with_skill,
            encoder=mock_encoder,
            skills_dir=str(tmp_path),
        )
        assert "target_skill" in result
        assert result["target_skill"] == "deploy"

    def test_returns_gaps_found(
        self, monkeypatch, tmp_path, db_with_skill, mock_encoder
    ):
        """Result has 'gaps_found' as an int."""
        from skill_curator.scout import scout_ingest

        self._mock_httpx_get(monkeypatch)
        result = scout_ingest(
            source_url="https://github.com/user/awesome-deploy",
            target_skill="deploy",
            db=db_with_skill,
            encoder=mock_encoder,
            skills_dir=str(tmp_path),
        )
        assert "gaps_found" in result
        assert isinstance(result["gaps_found"], int)
        # External has 3 sections (Installation, Configuration, Rollback Procedures)
        # Local has 1 section (Installation) — expect 2 gaps
        assert result["gaps_found"] == 2

    def test_returns_sections_to_add(
        self, monkeypatch, tmp_path, db_with_skill, mock_encoder
    ):
        """Result has 'sections_to_add' as a list."""
        from skill_curator.scout import scout_ingest

        self._mock_httpx_get(monkeypatch)
        result = scout_ingest(
            source_url="https://github.com/user/awesome-deploy",
            target_skill="deploy",
            db=db_with_skill,
            encoder=mock_encoder,
            skills_dir=str(tmp_path),
        )
        assert "sections_to_add" in result
        assert isinstance(result["sections_to_add"], list)
        assert "Configuration" in result["sections_to_add"]
        assert "Rollback Procedures" in result["sections_to_add"]

    def test_returns_adapted_content(
        self, monkeypatch, tmp_path, db_with_skill, mock_encoder
    ):
        """Result has 'adapted_content' as a string."""
        from skill_curator.scout import scout_ingest

        self._mock_httpx_get(monkeypatch)
        result = scout_ingest(
            source_url="https://github.com/user/awesome-deploy",
            target_skill="deploy",
            db=db_with_skill,
            encoder=mock_encoder,
            skills_dir=str(tmp_path),
        )
        assert "adapted_content" in result
        assert isinstance(result["adapted_content"], str)
        assert len(result["adapted_content"]) > 0

    def test_never_modifies_files(
        self, monkeypatch, tmp_path, db_with_skill, mock_encoder
    ):
        """Skill file on disk is unchanged after scout_ingest call."""
        from skill_curator.scout import scout_ingest

        self._mock_httpx_get(monkeypatch)
        # Read original content
        skill = db_with_skill.get_skill("deploy")
        from pathlib import Path

        original_content = Path(skill.path).read_text(encoding="utf-8")

        scout_ingest(
            source_url="https://github.com/user/awesome-deploy",
            target_skill="deploy",
            db=db_with_skill,
            encoder=mock_encoder,
            skills_dir=str(tmp_path),
        )

        # Verify file unchanged
        after_content = Path(skill.path).read_text(encoding="utf-8")
        assert after_content == original_content
