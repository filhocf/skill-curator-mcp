"""Tests for skill_curator.tools — MCP tool functions (phase 0.2.0 RED)."""
from datetime import datetime, timedelta

import pytest

from skill_curator.db import Database
from skill_curator.models import LifecycleState, Skill
from skill_curator.tools import (
    get_onboarding_guide,
    skill_archive,
    skill_feedback,
    skill_gaps,
    skill_lifecycle,
    skill_match,
    skill_promote,
    skill_reindex,
    skill_scout,
)


class MockEncoder:
    """Fixed encoder: always returns [0.1]*384."""

    def encode(self, text: str) -> list[float]:
        return [0.1] * 384


class DifferentiatingEncoder:
    """Returns different vectors based on input to test score differentiation."""

    def encode(self, text: str) -> list[float]:
        if "python" in text.lower() or "rest" in text.lower():
            return [0.9] * 384
        if "testing" in text.lower():
            return [0.8] * 192 + [0.1] * 192
        return [0.1] * 384


@pytest.fixture
def db() -> Database:
    return Database(":memory:")


@pytest.fixture
def db_with_skills(db: Database) -> Database:
    """DB with 4 skills + embeddings for tool tests."""
    encoder = MockEncoder()
    skills = [
        Skill(name="python-rest", path="/skills/python-rest.md", description="Build REST APIs in Python",
              effectiveness=0.8, total_uses=5, state=LifecycleState.ACTIVE, profile_tags='["backend"]'),
        Skill(name="testing", path="/skills/testing.md", description="Unit testing patterns",
              effectiveness=0.6, total_uses=2, state=LifecycleState.ACTIVE),
        Skill(name="old-skill", path="/skills/old.md", description="Legacy patterns",
              effectiveness=0.2, total_uses=10, state=LifecycleState.STALE,
              last_used_at=(datetime.utcnow() - timedelta(days=95)).isoformat()),
        Skill(name="archived-skill", path="/skills/archived.md", description="Deprecated tool",
              effectiveness=0.1, total_uses=1, state=LifecycleState.ARCHIVED),
    ]
    for s in skills:
        db.upsert_skill(s)
        text = f"{s.description or ''} {s.trigger_text or ''}".strip()
        db.save_embedding(s.name, encoder.encode(text))
    return db


# === skill_match ===


class TestSkillMatch:
    def test_returns_top_k_ordered_by_score_desc(self, db_with_skills: Database) -> None:
        results = skill_match("build an API", db=db_with_skills, encoder=MockEncoder(), top_k=2)
        assert len(results) <= 2
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_empty_db_returns_empty_list(self, db: Database) -> None:
        results = skill_match("anything", db=db, encoder=MockEncoder())
        assert results == []

    def test_excludes_archived_skills(self, db_with_skills: Database) -> None:
        results = skill_match("deprecated tool", db=db_with_skills, encoder=MockEncoder(), top_k=10)
        names = [r["name"] for r in results]
        assert "archived-skill" not in names

    def test_profile_boost_increases_score(self, db_with_skills: Database) -> None:
        without_profile = skill_match("REST API", db=db_with_skills, encoder=MockEncoder(), top_k=5)
        with_profile = skill_match("REST API", db=db_with_skills, encoder=MockEncoder(),
                                   top_k=5, profile=["python-rest"])
        score_without = next(r["score"] for r in without_profile if r["name"] == "python-rest")
        score_with = next(r["score"] for r in with_profile if r["name"] == "python-rest")
        assert score_with > score_without

    def test_semantically_relevant_score_above_threshold(self, db: Database) -> None:
        """When encoder returns similar vectors, score should be > 0.5."""
        encoder = DifferentiatingEncoder()
        skill = Skill(name="python-rest", path="/s/p.md", description="Python REST APIs",
                      effectiveness=0.7, state=LifecycleState.ACTIVE)
        db.upsert_skill(skill)
        db.save_embedding("python-rest", encoder.encode("Python REST APIs"))
        results = skill_match("python rest endpoint", db=db, encoder=encoder, top_k=3)
        assert len(results) >= 1
        assert results[0]["score"] > 0.5


# === skill_feedback ===


class TestSkillFeedback:
    def test_saves_feedback_and_updates_effectiveness_ema(self, db_with_skills: Database) -> None:
        old_eff = db_with_skills.get_skill("python-rest").effectiveness  # 0.8
        result = skill_feedback("python-rest", outcome="success", task_description="built API",
                                db=db_with_skills)
        new_eff = db_with_skills.get_skill("python-rest").effectiveness
        expected = 0.3 * 1.0 + 0.7 * old_eff  # EMA α=0.3
        assert new_eff == pytest.approx(expected, abs=1e-6)

    def test_increments_total_uses(self, db_with_skills: Database) -> None:
        old_uses = db_with_skills.get_skill("testing").total_uses
        skill_feedback("testing", outcome="success", task_description="wrote tests",
                       db=db_with_skills)
        new_uses = db_with_skills.get_skill("testing").total_uses
        assert new_uses == old_uses + 1

    @pytest.mark.parametrize("outcome,direction", [("success", "up"), ("failure", "down")])
    def test_effectiveness_direction(self, db_with_skills: Database, outcome: str, direction: str) -> None:
        old_eff = db_with_skills.get_skill("testing").effectiveness  # 0.6
        skill_feedback("testing", outcome=outcome, task_description="task", db=db_with_skills)
        new_eff = db_with_skills.get_skill("testing").effectiveness
        if direction == "up":
            assert new_eff > old_eff
        else:
            assert new_eff < old_eff

    def test_nonexistent_skill_returns_error(self, db: Database) -> None:
        result = skill_feedback("nonexistent", outcome="success", task_description="x", db=db)
        assert result.get("error") is not None


# === skill_gaps ===


class TestSkillGaps:
    def test_returns_skills_with_gap_count_gt_zero(self, db: Database) -> None:
        db.upsert_skill(Skill(name="gapped", path="/g.md", gap_count=3, state=LifecycleState.ACTIVE))
        db.upsert_skill(Skill(name="ok", path="/ok.md", gap_count=0, state=LifecycleState.ACTIVE))
        results = skill_gaps(db=db)
        names = [r["name"] for r in results]
        assert "gapped" in names
        assert "ok" not in names

    def test_returns_skills_without_recent_use(self, db: Database) -> None:
        old_date = (datetime.utcnow() - timedelta(days=45)).isoformat()
        db.upsert_skill(Skill(name="stale-use", path="/s.md", last_used_at=old_date,
                              state=LifecycleState.ACTIVE))
        db.upsert_skill(Skill(name="recent", path="/r.md", last_used_at=datetime.utcnow().isoformat(),
                              state=LifecycleState.ACTIVE))
        results = skill_gaps(db=db)
        names = [r["name"] for r in results]
        assert "stale-use" in names
        assert "recent" not in names


# === skill_lifecycle ===


class TestSkillLifecycle:
    def test_categorizes_active_stale_promote_archive(self, db_with_skills: Database) -> None:
        result = skill_lifecycle(db=db_with_skills)
        assert "active" in result
        assert "stale" in result
        assert "candidates_promote" in result
        assert "candidates_archive" in result

    def test_candidate_promote_high_effectiveness_and_uses(self, db: Database) -> None:
        db.upsert_skill(Skill(name="star", path="/s.md", effectiveness=0.8, total_uses=5,
                              state=LifecycleState.DRAFT))
        result = skill_lifecycle(db=db)
        names = [s["name"] for s in result["candidates_promote"]]
        assert "star" in names

    def test_candidate_archive_low_effectiveness(self, db: Database) -> None:
        db.upsert_skill(Skill(name="bad", path="/b.md", effectiveness=0.2, total_uses=10,
                              state=LifecycleState.ACTIVE))
        result = skill_lifecycle(db=db)
        names = [s["name"] for s in result["candidates_archive"]]
        assert "bad" in names

    def test_candidate_archive_stale_over_90d(self, db: Database) -> None:
        old = (datetime.utcnow() - timedelta(days=100)).isoformat()
        db.upsert_skill(Skill(name="ancient", path="/a.md", effectiveness=0.5, total_uses=2,
                              state=LifecycleState.STALE, last_used_at=old))
        result = skill_lifecycle(db=db)
        names = [s["name"] for s in result["candidates_archive"]]
        assert "ancient" in names


# === skill_promote / skill_archive ===


class TestSkillPromote:
    def test_changes_state_to_active(self, db_with_skills: Database) -> None:
        result = skill_promote("old-skill", db=db_with_skills)
        skill = db_with_skills.get_skill("old-skill")
        assert skill.state == LifecycleState.ACTIVE

    def test_nonexistent_returns_error(self, db: Database) -> None:
        result = skill_promote("ghost", db=db)
        assert result.get("error") is not None


class TestSkillArchive:
    def test_changes_state_to_archived(self, db_with_skills: Database) -> None:
        result = skill_archive("testing", db=db_with_skills)
        skill = db_with_skills.get_skill("testing")
        assert skill.state == LifecycleState.ARCHIVED

    def test_nonexistent_returns_error(self, db: Database) -> None:
        result = skill_archive("ghost", db=db)
        assert result.get("error") is not None


# === skill_reindex ===


class TestSkillReindex:
    def test_returns_correct_count(self, tmp_path) -> None:
        (tmp_path / "a.md").write_text("---\ndescription: Skill A\n---\n# A")
        (tmp_path / "b.md").write_text("# Skill B\nContent.")
        db = Database(":memory:")
        result = skill_reindex(skills_dir=str(tmp_path), db=db, encoder=MockEncoder())
        assert result["indexed"] == 2

    def test_empty_dir_returns_zero(self, tmp_path) -> None:
        db = Database(":memory:")
        result = skill_reindex(skills_dir=str(tmp_path), db=db, encoder=MockEncoder())
        assert result["indexed"] == 0


# === skill_scout ===


class TestSkillScout:
    def test_returns_stub_message(self, db: Database) -> None:
        result = skill_scout(db=db)
        assert "message" in result or "stub" in str(result).lower()


# === get_onboarding_guide (SC-05 RED) ===


class TestOnboardingGuide:
    """Tests for enhanced get_onboarding_guide(verbosity) — SC-05 RED."""

    def test_full_guide_has_lifecycle(self, db: Database) -> None:
        """get_onboarding_guide(verbosity='full') returns dict with 'lifecycle' as non-empty string."""
        result = get_onboarding_guide(verbosity="full", db=db)
        assert "lifecycle" in result, f"Missing 'lifecycle' key. Keys: {list(result.keys())}"
        assert isinstance(result["lifecycle"], str)
        assert len(result["lifecycle"]) > 0

    def test_full_guide_has_integration_protocol(self, db: Database) -> None:
        """Result has 'integration_protocol' dict with required phase keys."""
        result = get_onboarding_guide(verbosity="full", db=db)
        assert "integration_protocol" in result, f"Missing 'integration_protocol'. Keys: {list(result.keys())}"
        proto = result["integration_protocol"]
        assert isinstance(proto, dict)
        for key in ("startup", "pre_task", "post_task", "shutdown", "weekly"):
            assert key in proto, f"Missing '{key}' in integration_protocol. Keys: {list(proto.keys())}"

    def test_full_guide_has_tools_section(self, db: Database) -> None:
        """Result has 'tools' dict where each value has 'when' and 'params'/'parameters' and 'returns'."""
        result = get_onboarding_guide(verbosity="full", db=db)
        assert "tools" in result, f"Missing 'tools'. Keys: {list(result.keys())}"
        tools = result["tools"]
        assert isinstance(tools, dict), f"Expected tools to be dict, got {type(tools)}"
        for tool_name, tool_info in tools.items():
            assert "when" in tool_info, f"Tool '{tool_name}' missing 'when'"
            assert "params" in tool_info or "parameters" in tool_info, \
                f"Tool '{tool_name}' missing 'params'/'parameters'"
            assert "returns" in tool_info, f"Tool '{tool_name}' missing 'returns'"

    def test_full_guide_has_thresholds(self, db: Database) -> None:
        """Result has 'thresholds' dict with at least the two score thresholds."""
        result = get_onboarding_guide(verbosity="full", db=db)
        assert "thresholds" in result, f"Missing 'thresholds'. Keys: {list(result.keys())}"
        thresholds = result["thresholds"]
        assert isinstance(thresholds, dict)
        assert "SKILL_MATCH_HIGH_THRESHOLD" in thresholds
        assert "SKILL_MATCH_LOW_THRESHOLD" in thresholds

    def test_compact_guide_smaller_than_full(self, db: Database) -> None:
        """Compact guide serialized JSON is smaller than full guide."""
        import json
        full = get_onboarding_guide(verbosity="full", db=db)
        compact = get_onboarding_guide(verbosity="compact", db=db)
        assert isinstance(compact, dict)
        assert len(json.dumps(compact)) < len(json.dumps(full))

    def test_compact_has_lifecycle_and_protocol(self, db: Database) -> None:
        """Compact guide retains 'lifecycle' and 'integration_protocol' keys."""
        result = get_onboarding_guide(verbosity="compact", db=db)
        assert "lifecycle" in result, f"Compact missing 'lifecycle'. Keys: {list(result.keys())}"
        assert "integration_protocol" in result, \
            f"Compact missing 'integration_protocol'. Keys: {list(result.keys())}"

    def test_compact_omits_detailed_tools(self, db: Database) -> None:
        """Compact guide does NOT have 'tools' key with full descriptions."""
        result = get_onboarding_guide(verbosity="compact", db=db)
        if "tools" in result:
            # If tools key exists, it should be a simple list of names, not detailed dicts
            tools = result["tools"]
            if isinstance(tools, dict):
                # Full guide has dict with 'when'/'params'/'returns' per tool — compact must NOT
                for tool_info in tools.values():
                    assert not isinstance(tool_info, dict) or "when" not in tool_info, \
                        "Compact guide should not have detailed tool descriptions"

    def test_default_verbosity_is_full(self, db: Database) -> None:
        """get_onboarding_guide(db=db) without verbosity returns same structure as full."""
        default_result = get_onboarding_guide(db=db)
        full_result = get_onboarding_guide(verbosity="full", db=db)
        assert set(default_result.keys()) == set(full_result.keys()), \
            f"Default keys {set(default_result.keys())} != full keys {set(full_result.keys())}"

    def test_tools_list_includes_skill_match(self, db: Database) -> None:
        """result['tools'] includes 'skill_match' as a key."""
        result = get_onboarding_guide(verbosity="full", db=db)
        tools = result["tools"]
        assert "skill_match" in tools, f"'skill_match' not in tools. Keys: {list(tools.keys())}"

    def test_version_field_present(self, db: Database) -> None:
        """Result has 'version' key matching pattern r'\\d+\\.\\d+'."""
        import re
        result = get_onboarding_guide(verbosity="full", db=db)
        assert "version" in result, f"Missing 'version'. Keys: {list(result.keys())}"
        assert isinstance(result["version"], str)
        assert re.match(r"\d+\.\d+", result["version"]), \
            f"Version '{result['version']}' doesn't match pattern \\d+\\.\\d+"


# === skill_match — suggestion field (SC-02 RED) ===


class ScoreControlEncoder:
    """Encoder that produces specific cosine similarities based on keyword pairs.

    Strategy: use orthogonal basis vectors to control cosine distance precisely.
    - "high-match" pair: identical vectors → similarity=1.0 → composite score > 0.7
    - "mid-match" pair: partially overlapping → similarity ~0.5 → composite score ~0.5-0.7
    - "low-match" pair: orthogonal vectors → similarity ~0 → composite score < 0.5
    """

    def encode(self, text: str) -> list[float]:
        vec = [0.0] * 384
        lowered = text.lower()
        if "python" in lowered or "rest" in lowered or "api" in lowered:
            # Dimension 0-191 active
            for i in range(192):
                vec[i] = 1.0
        elif "testing" in lowered or "partial" in lowered:
            # Overlap with python/rest: dimensions 96-287 active → ~50% overlap
            for i in range(96, 288):
                vec[i] = 1.0
        else:
            # Completely orthogonal: dimensions 192-383 active
            for i in range(192, 384):
                vec[i] = 1.0
        return vec


class TestSkillMatchSuggestion:
    """Tests for proactive suggestion field in skill_match results."""

    def test_high_score_no_suggestion(self, db: Database) -> None:
        """Score >= 0.7 → result has NO 'suggestion' key."""
        encoder = ScoreControlEncoder()
        skill = Skill(name="python-rest", path="/s/p.md", description="Python REST APIs",
                      effectiveness=0.9, state=LifecycleState.ACTIVE)
        db.upsert_skill(skill)
        db.save_embedding("python-rest", encoder.encode("Python REST APIs"))
        results = skill_match("python rest endpoint", db=db, encoder=encoder, top_k=3)
        assert len(results) >= 1
        assert results[0]["score"] >= 0.7, f"Expected score >= 0.7, got {results[0]['score']}"
        assert "suggestion" not in results[0]

    def test_mid_score_improvement_opportunity(self, db: Database) -> None:
        """0.5 <= score < 0.7 → suggestion with improvement_opportunity."""
        encoder = ScoreControlEncoder()
        # "testing" yields partially overlapping vector → mid-range cosine ~0.5
        skill = Skill(name="testing-patterns", path="/s/t.md", description="Testing strategies partial",
                      effectiveness=0.5, state=LifecycleState.ACTIVE)
        db.upsert_skill(skill)
        db.save_embedding("testing-patterns", encoder.encode("Testing strategies partial"))
        results = skill_match("python rest endpoint", db=db, encoder=encoder, top_k=3)
        # Find a result with mid-range score
        mid_results = [r for r in results if 0.5 <= r["score"] < 0.7]
        assert len(mid_results) >= 1, f"Expected mid-score result, got scores: {[r['score'] for r in results]}"
        suggestion = mid_results[0]["suggestion"]
        assert suggestion["improvement_opportunity"] is True
        assert suggestion["suggested_action"] == "evolve_existing"

    def test_low_score_gap_detected(self, db: Database) -> None:
        """Score < 0.5 → suggestion with gap_detected."""
        encoder = ScoreControlEncoder()
        # Skill with completely orthogonal vector → low cosine similarity
        skill = Skill(name="deploy-k8s", path="/s/d.md", description="Kubernetes deployment",
                      effectiveness=0.3, state=LifecycleState.ACTIVE)
        db.upsert_skill(skill)
        db.save_embedding("deploy-k8s", encoder.encode("Kubernetes deployment"))
        # Query yields python/rest vector which is orthogonal to deployment vector
        results = skill_match("python rest endpoint", db=db, encoder=encoder, top_k=3)
        assert len(results) >= 1
        assert results[0]["score"] < 0.5, f"Expected score < 0.5, got {results[0]['score']}"
        suggestion = results[0]["suggestion"]
        assert suggestion["gap_detected"] is True
        assert suggestion["suggested_action"] == "create_new"
        assert isinstance(suggestion["suggested_name"], str)
        assert len(suggestion["suggested_name"]) > 0

    def test_gap_detected_increments_gap_count(self, db: Database) -> None:
        """When gap detected, closest_match skill's gap_count increments by 1."""
        encoder = ScoreControlEncoder()
        skill = Skill(name="deploy-k8s", path="/s/d.md", description="Kubernetes deployment",
                      effectiveness=0.3, gap_count=2, state=LifecycleState.ACTIVE)
        db.upsert_skill(skill)
        db.save_embedding("deploy-k8s", encoder.encode("Kubernetes deployment"))
        old_gap_count = db.get_skill("deploy-k8s").gap_count
        # Query producing low score → gap detected
        results = skill_match("python rest endpoint", db=db, encoder=encoder, top_k=3)
        assert len(results) >= 1
        assert results[0]["score"] < 0.5, f"Expected score < 0.5, got {results[0]['score']}"
        new_gap_count = db.get_skill("deploy-k8s").gap_count
        assert new_gap_count == old_gap_count + 1

    def test_gap_detected_logs_to_gap_log(self, db: Database) -> None:
        """When gap detected, gap_log table gets a new entry."""
        encoder = ScoreControlEncoder()
        skill = Skill(name="deploy-k8s", path="/s/d.md", description="Kubernetes deployment",
                      effectiveness=0.3, state=LifecycleState.ACTIVE)
        db.upsert_skill(skill)
        db.save_embedding("deploy-k8s", encoder.encode("Kubernetes deployment"))
        skill_match("python rest endpoint", db=db, encoder=encoder, top_k=3)
        # Check gap_log table has entry
        cur = db.conn.execute("SELECT task_description, best_match_name, best_match_score FROM gap_log")
        rows = cur.fetchall()
        assert len(rows) >= 1
        row = rows[-1]
        assert row[0] == "python rest endpoint"  # task_description
        assert row[1] == "deploy-k8s"  # best_match_name
        assert isinstance(row[2], float)  # best_match_score
        assert row[2] < 0.5


# === gap_log table (SC-02 RED) ===


class TestGapLog:
    """Tests for the gap_log table and access methods."""

    def test_gap_log_table_exists(self, db: Database) -> None:
        """DB should have gap_log table after init."""
        cur = db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='gap_log'"
        )
        assert cur.fetchone() is not None, "gap_log table does not exist"

    def test_gap_log_entry_fields(self, db: Database) -> None:
        """gap_log entry should have all required fields."""
        # Insert a test entry directly to verify schema
        db.conn.execute(
            """INSERT INTO gap_log (timestamp, task_description, best_match_name,
               best_match_score, session_id, resolved)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (datetime.utcnow().isoformat(), "test task", "some-skill", 0.35, "sess-1", False),
        )
        db.conn.commit()
        cur = db.conn.execute("SELECT * FROM gap_log LIMIT 1")
        row = cur.fetchone()
        assert row is not None
        # Verify columns: id, timestamp, task_description, best_match_name, best_match_score, session_id, resolved
        col_names = [desc[0] for desc in cur.description]
        assert "id" in col_names
        assert "timestamp" in col_names
        assert "task_description" in col_names
        assert "best_match_name" in col_names
        assert "best_match_score" in col_names
        assert "session_id" in col_names
        assert "resolved" in col_names

    def test_gap_log_get_entries(self, db: Database) -> None:
        """db.get_gap_log() returns entries ordered by timestamp desc."""
        now = datetime.utcnow()
        db.conn.execute(
            """INSERT INTO gap_log (timestamp, task_description, best_match_name,
               best_match_score, session_id, resolved) VALUES (?, ?, ?, ?, ?, ?)""",
            ((now - timedelta(minutes=10)).isoformat(), "older task", "skill-a", 0.3, "s1", False),
        )
        db.conn.execute(
            """INSERT INTO gap_log (timestamp, task_description, best_match_name,
               best_match_score, session_id, resolved) VALUES (?, ?, ?, ?, ?, ?)""",
            (now.isoformat(), "newer task", "skill-b", 0.4, "s1", False),
        )
        db.conn.commit()
        entries = db.get_gap_log()
        assert len(entries) >= 2
        # Most recent first
        assert entries[0]["task_description"] == "newer task"
        assert entries[1]["task_description"] == "older task"

    def test_gap_log_get_entries_by_session(self, db: Database) -> None:
        """db.get_gap_log(session_id='X') filters by session."""
        now = datetime.utcnow()
        db.conn.execute(
            """INSERT INTO gap_log (timestamp, task_description, best_match_name,
               best_match_score, session_id, resolved) VALUES (?, ?, ?, ?, ?, ?)""",
            (now.isoformat(), "task session A", "skill-x", 0.2, "session-A", False),
        )
        db.conn.execute(
            """INSERT INTO gap_log (timestamp, task_description, best_match_name,
               best_match_score, session_id, resolved) VALUES (?, ?, ?, ?, ?, ?)""",
            (now.isoformat(), "task session B", "skill-y", 0.3, "session-B", False),
        )
        db.conn.commit()
        entries = db.get_gap_log(session_id="session-A")
        assert len(entries) == 1
        assert entries[0]["task_description"] == "task session A"
        assert entries[0]["session_id"] == "session-A"


# === skill_gaps correlation (SC-03 RED) ===


class ClusteringEncoder:
    """Encoder that returns similar vectors for semantically similar texts.

    Uses keyword overlap to simulate real embedding clustering behavior.
    Texts about 'linkedin/social media' get vectors in one region,
    texts about other topics get vectors in different regions.
    """

    def encode(self, text: str) -> list[float]:
        lowered = text.lower()
        if any(w in lowered for w in ["linkedin", "social media", "publish", "post", "share"]):
            # Social media cluster: dimensions 0-191 active
            vec = [0.8] * 192 + [0.1] * 192
        elif any(w in lowered for w in ["kubernetes", "deploy", "k8s"]):
            # DevOps cluster: dimensions 192-383 active
            vec = [0.1] * 192 + [0.8] * 192
        elif any(w in lowered for w in ["test", "unit", "pytest"]):
            # Testing cluster: alternating pattern
            vec = [0.8 if i % 2 == 0 else 0.1 for i in range(384)]
        elif any(w in lowered for w in ["nginx", "configure", "proxy"]):
            # Infra cluster: reverse alternating
            vec = [0.1 if i % 2 == 0 else 0.8 for i in range(384)]
        else:
            # Unique/unclustered
            import hashlib
            h = hashlib.md5(lowered.encode()).hexdigest()
            vec = [int(c, 16) / 15.0 for c in h] * 24  # 384 dims
        return vec


@pytest.fixture
def db_with_gap_log(db: Database) -> Database:
    """DB with gap_log entries for clustering tests."""
    import time

    # Similar tasks (should cluster) — social media theme
    for desc in ["post on linkedin", "publish linkedin content", "create linkedin post", "share on social media"]:
        db.add_gap_log(task_description=desc, best_match_name="personal-branding", best_match_score=0.45, session_id="test")
        time.sleep(0.01)  # ensure different timestamps
    # Dissimilar task
    db.add_gap_log(task_description="deploy to kubernetes", best_match_name="k8s-deploy", best_match_score=0.2, session_id="test")
    return db


@pytest.fixture
def db_with_diverse_gaps(db: Database) -> Database:
    """DB with gap_log entries that have DIFFERENT topics (should NOT cluster)."""
    import time

    for desc in ["deploy kubernetes cluster", "write unit tests for parser", "configure nginx reverse proxy"]:
        db.add_gap_log(task_description=desc, best_match_name="generic-skill", best_match_score=0.3, session_id="test")
        time.sleep(0.01)
    return db


@pytest.fixture
def db_with_low_score_cluster(db: Database) -> Database:
    """DB with gap_log entries that cluster AND have avg best_match_score < 0.3."""
    import time

    for desc in ["post on linkedin", "publish linkedin content", "create linkedin post"]:
        db.add_gap_log(task_description=desc, best_match_name="personal-branding", best_match_score=0.15, session_id="test")
        time.sleep(0.01)
    return db


@pytest.fixture
def db_with_mid_score_cluster(db: Database) -> Database:
    """DB with gap_log entries that cluster AND have avg best_match_score 0.3-0.6."""
    import time

    for desc in ["post on linkedin", "publish linkedin content", "create linkedin post"]:
        db.add_gap_log(task_description=desc, best_match_name="personal-branding", best_match_score=0.45, session_id="test")
        time.sleep(0.01)
    return db


@pytest.fixture
def db_with_high_score_cluster(db: Database) -> Database:
    """DB with gap_log entries that cluster AND have avg best_match_score >= 0.6."""
    import time

    for desc in ["post on linkedin", "publish linkedin content", "create linkedin post"]:
        db.add_gap_log(task_description=desc, best_match_name="personal-branding", best_match_score=0.65, session_id="test")
        time.sleep(0.01)
    return db


class TestSkillGapsCorrelation:
    """Tests for skill_gaps(correlate=True) — correlated gap detection (SC-03)."""

    def test_correlate_false_returns_current_behavior(self, db_with_gap_log: Database) -> None:
        """skill_gaps(correlate=False) returns same shape as before (list of dicts)."""
        # Add a skill with gap_count > 0 to ensure results
        db_with_gap_log.upsert_skill(
            Skill(name="personal-branding", path="/s/pb.md", gap_count=4, state=LifecycleState.ACTIVE)
        )
        result = skill_gaps(correlate=False, db=db_with_gap_log)
        # Should return a list (backward compatible)
        assert isinstance(result, list)
        assert len(result) >= 1
        # Each item should have the traditional keys
        assert "name" in result[0]
        assert "gap_count" in result[0]
        assert "last_used_at" in result[0]
        # Should NOT have correlation keys
        assert not isinstance(result, dict)

    def test_correlate_true_returns_detected_patterns(self, db_with_gap_log: Database) -> None:
        """skill_gaps(correlate=True) returns a dict with known_gaps, detected_patterns, recommendations."""
        encoder = ClusteringEncoder()
        result = skill_gaps(correlate=True, db=db_with_gap_log, encoder=encoder)
        # Should return a dict (new behavior)
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        assert "known_gaps" in result
        assert "detected_patterns" in result
        assert "recommendations" in result
        # known_gaps should be a list
        assert isinstance(result["known_gaps"], list)
        # detected_patterns should be a list
        assert isinstance(result["detected_patterns"], list)
        # recommendations should be a list
        assert isinstance(result["recommendations"], list)

    def test_clusters_similar_tasks(self, db_with_gap_log: Database) -> None:
        """Similar tasks ('linkedin', 'social media') should cluster into 1 pattern with occurrences >= 3."""
        encoder = ClusteringEncoder()
        result = skill_gaps(correlate=True, db=db_with_gap_log, encoder=encoder)
        patterns = result["detected_patterns"]
        assert len(patterns) >= 1, f"Expected at least 1 pattern, got {len(patterns)}"
        # At least one cluster should have 3+ occurrences (4 similar tasks inserted)
        large_clusters = [p for p in patterns if p["occurrences"] >= 3]
        assert len(large_clusters) >= 1, f"Expected cluster with >=3 occurrences, got: {patterns}"

    def test_dissimilar_tasks_not_clustered(self, db_with_diverse_gaps: Database) -> None:
        """Dissimilar tasks should NOT form a cluster with occurrences >= 3."""
        encoder = ClusteringEncoder()
        result = skill_gaps(correlate=True, db=db_with_diverse_gaps, encoder=encoder)
        patterns = result["detected_patterns"]
        # No cluster should have 3+ occurrences since all tasks are different topics
        large_clusters = [p for p in patterns if p["occurrences"] >= 3]
        assert len(large_clusters) == 0, f"Expected no large clusters, got: {large_clusters}"

    def test_actionable_flag_when_gte_3(self, db_with_gap_log: Database) -> None:
        """Cluster with 3+ entries should have 'actionable': True."""
        encoder = ClusteringEncoder()
        result = skill_gaps(correlate=True, db=db_with_gap_log, encoder=encoder)
        patterns = result["detected_patterns"]
        large_clusters = [p for p in patterns if p["occurrences"] >= 3]
        assert len(large_clusters) >= 1, "Need at least 1 cluster with >=3 occurrences"
        for cluster in large_clusters:
            assert cluster["actionable"] is True, f"Expected actionable=True, got {cluster}"

    def test_recommended_action_create_when_low_score(self, db_with_low_score_cluster: Database) -> None:
        """Cluster where avg best_match_score < 0.3 → recommended_action = 'create_skill'."""
        encoder = ClusteringEncoder()
        result = skill_gaps(correlate=True, db=db_with_low_score_cluster, encoder=encoder)
        patterns = result["detected_patterns"]
        assert len(patterns) >= 1, "Expected at least 1 pattern"
        actionable = [p for p in patterns if p.get("actionable")]
        assert len(actionable) >= 1, "Expected at least 1 actionable pattern"
        assert actionable[0]["recommended_action"] == "create_skill"

    def test_recommended_action_evolve_when_mid_score(self, db_with_mid_score_cluster: Database) -> None:
        """Cluster where avg best_match_score 0.3-0.6 → recommended_action = 'evolve_skill'."""
        encoder = ClusteringEncoder()
        result = skill_gaps(correlate=True, db=db_with_mid_score_cluster, encoder=encoder)
        patterns = result["detected_patterns"]
        assert len(patterns) >= 1, "Expected at least 1 pattern"
        actionable = [p for p in patterns if p.get("actionable")]
        assert len(actionable) >= 1, "Expected at least 1 actionable pattern"
        assert actionable[0]["recommended_action"] == "evolve_skill"

    def test_recommended_action_scout_when_high_score(self, db_with_high_score_cluster: Database) -> None:
        """Cluster where avg best_match_score >= 0.6 → recommended_action = 'scout_external'."""
        encoder = ClusteringEncoder()
        result = skill_gaps(correlate=True, db=db_with_high_score_cluster, encoder=encoder)
        patterns = result["detected_patterns"]
        assert len(patterns) >= 1, "Expected at least 1 pattern"
        actionable = [p for p in patterns if p.get("actionable")]
        assert len(actionable) >= 1, "Expected at least 1 actionable pattern"
        assert actionable[0]["recommended_action"] == "scout_external"

    def test_empty_gap_log_returns_empty_patterns(self, db: Database) -> None:
        """No gap_log entries → detected_patterns = []."""
        encoder = ClusteringEncoder()
        result = skill_gaps(correlate=True, db=db, encoder=encoder)
        assert isinstance(result, dict)
        assert result["detected_patterns"] == []
