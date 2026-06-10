"""Tests for profile-aware matching (v1.0.0 RED).

The skill_match tool accepts a profile param (list of skill names).
Skills in the profile receive a +0.2 score boost.
load_profile reads ~/.kiro/agents/{name}.json for expected_skills.
"""
import json

import pytest

from skill_curator.profile import load_profile
from skill_curator.db import Database
from skill_curator.models import LifecycleState, Skill
from skill_curator.tools import skill_match


class MockEncoder:
    """Returns different vectors to create distinguishable similarities."""

    def encode(self, text: str) -> list[float]:
        if "kubernetes" in text.lower():
            return [0.9] * 384
        if "docker" in text.lower():
            return [0.7] * 192 + [0.3] * 192
        return [0.1] * 384


@pytest.fixture
def db() -> Database:
    d = Database(":memory:")
    # Skill A: high similarity to "kubernetes" query
    skill_a = Skill(name="k8s-deploy", path="/skills/k8s.md", description="deploy to kubernetes",
                    effectiveness=0.5, state=LifecycleState.ACTIVE)
    # Skill B: lower similarity
    skill_b = Skill(name="docker-build", path="/skills/docker.md", description="build docker images",
                    effectiveness=0.5, state=LifecycleState.ACTIVE)
    d.upsert_skill(skill_a)
    d.upsert_skill(skill_b)
    encoder = MockEncoder()
    d.save_embedding("k8s-deploy", encoder.encode(skill_a.description))
    d.save_embedding("docker-build", encoder.encode(skill_b.description))
    return d


class TestProfileBoost:
    def test_profile_boost_increases_score(self, db: Database) -> None:
        encoder = MockEncoder()
        results_no_profile = skill_match("kubernetes deploy", db=db, encoder=encoder, profile=None)
        results_with_profile = skill_match("kubernetes deploy", db=db, encoder=encoder, profile=["k8s-deploy"])

        score_no = next(r["score"] for r in results_no_profile if r["name"] == "k8s-deploy")
        score_with = next(r["score"] for r in results_with_profile if r["name"] == "k8s-deploy")
        assert score_with > score_no

    def test_profile_none_no_boost(self, db: Database) -> None:
        encoder = MockEncoder()
        results = skill_match("kubernetes deploy", db=db, encoder=encoder, profile=None)
        # Without profile, profile_match component is 0
        for r in results:
            # Max possible without profile boost: 0.6*sim + 0.2*eff + 0.0
            assert r["score"] <= 0.6 * 1.0 + 0.2 * 1.0

    def test_profile_empty_list_no_boost(self, db: Database) -> None:
        encoder = MockEncoder()
        results_none = skill_match("kubernetes deploy", db=db, encoder=encoder, profile=None)
        results_empty = skill_match("kubernetes deploy", db=db, encoder=encoder, profile=[])
        # Empty list should behave same as None
        for rn, re in zip(results_none, results_empty):
            assert rn["score"] == re["score"]

    def test_profile_reorders_results(self, db: Database) -> None:
        encoder = MockEncoder()
        # docker-build has lower similarity but is in profile → should overtake k8s-deploy
        results = skill_match("kubernetes deploy", db=db, encoder=encoder, profile=["docker-build"], top_k=2)
        # With +0.2 boost, docker-build should rank first despite lower similarity
        assert results[0]["name"] == "docker-build"


class TestLoadProfile:
    def test_get_profile_from_file(self, tmp_path, monkeypatch) -> None:
        agents_dir = tmp_path / ".kiro" / "agents"
        agents_dir.mkdir(parents=True)
        profile_data = {"expected_skills": ["k8s-deploy", "docker-build", "python-rest"]}
        (agents_dir / "backend-dev.json").write_text(json.dumps(profile_data))

        monkeypatch.setenv("HOME", str(tmp_path))
        result = load_profile("backend-dev")
        assert result == ["k8s-deploy", "docker-build", "python-rest"]

    def test_profile_file_missing_returns_empty(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        result = load_profile("nonexistent-profile")
        assert result == []

    def test_profile_file_no_expected_skills_returns_empty(self, tmp_path, monkeypatch) -> None:
        agents_dir = tmp_path / ".kiro" / "agents"
        agents_dir.mkdir(parents=True)
        profile_data = {"name": "backend-dev", "description": "A profile without skills"}
        (agents_dir / "backend-dev.json").write_text(json.dumps(profile_data))

        monkeypatch.setenv("HOME", str(tmp_path))
        result = load_profile("backend-dev")
        assert result == []
