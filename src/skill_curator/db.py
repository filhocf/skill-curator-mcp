"""SQLite database layer for skill-curator-mcp (sync)."""

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import sqlite_vec

from skill_curator.models import FeedbackEntry, LifecycleState, Skill

logger = logging.getLogger(__name__)


class Database:
    """Sync SQLite database for skill-curator.

    Args:
        db_path: Database file path or ':memory:' for in-memory.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.enable_load_extension(True)
        sqlite_vec.load(self._conn)
        self._conn.enable_load_extension(False)
        if db_path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

    def _create_tables(self) -> None:
        """Create schema tables if they don't exist."""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS skills (
                name TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                description TEXT,
                trigger_text TEXT,
                effectiveness REAL DEFAULT 0.5,
                total_uses INTEGER DEFAULT 0,
                total_successes INTEGER DEFAULT 0,
                gap_count INTEGER DEFAULT 0,
                state TEXT DEFAULT 'active',
                profile_tags TEXT,
                last_used_at TEXT,
                last_indexed_at TEXT,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS feedback_log (
                id INTEGER PRIMARY KEY,
                skill_name TEXT REFERENCES skills(name),
                session_id TEXT,
                outcome TEXT,
                task_description TEXT,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS scouted_skills (
                id INTEGER PRIMARY KEY,
                source_url TEXT NOT NULL,
                name TEXT,
                description TEXT,
                relevance_score REAL,
                matched_gap TEXT,
                status TEXT DEFAULT 'new',
                discovered_at TEXT
            );

        """)
        # Check if existing vec0 table lacks cosine metric — drop and recreate
        cur = self._conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='skill_embeddings'"
        )
        row = cur.fetchone()
        if row and "distance_metric=cosine" not in (row[0] or ""):
            self._conn.execute("DROP TABLE IF EXISTS skill_embeddings")
            logger.info("Dropped skill_embeddings (missing cosine metric), will recreate.")

        self._conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS skill_embeddings USING vec0(
                name TEXT PRIMARY KEY,
                embedding float[384] distance_metric=cosine
            );
        """)
        self._conn.commit()

    def upsert_skill(self, skill: Skill) -> None:
        """Insert or update a skill."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT INTO skills (name, path, description, trigger_text, effectiveness,
               total_uses, total_successes, gap_count, state, profile_tags,
               last_used_at, last_indexed_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                   path=excluded.path, description=excluded.description,
                   trigger_text=excluded.trigger_text, effectiveness=excluded.effectiveness,
                   total_uses=excluded.total_uses, total_successes=excluded.total_successes,
                   gap_count=excluded.gap_count, state=excluded.state,
                   profile_tags=excluded.profile_tags, last_used_at=excluded.last_used_at,
                   last_indexed_at=excluded.last_indexed_at
            """,
            (
                skill.name, skill.path, skill.description, skill.trigger_text,
                skill.effectiveness, skill.total_uses, skill.total_successes,
                skill.gap_count, skill.state.value,
                json.dumps(skill.profile_tags) if skill.profile_tags else None,
                skill.last_used_at, now, skill.created_at or now,
            ),
        )
        self._conn.commit()

    def get_skill(self, name: str) -> Optional[Skill]:
        """Get a skill by name, or None if not found."""
        cur = self._conn.execute("SELECT * FROM skills WHERE name = ?", (name,))
        row = cur.fetchone()
        if row is None:
            return None
        return self._row_to_skill(row)

    def list_skills(self, state: Optional[str] = None) -> list[Skill]:
        """List skills, optionally filtered by state string."""
        if state:
            cur = self._conn.execute(
                "SELECT * FROM skills WHERE state = ?", (state,)
            )
        else:
            cur = self._conn.execute("SELECT * FROM skills")
        return [self._row_to_skill(row) for row in cur.fetchall()]

    def add_feedback(self, entry: FeedbackEntry) -> None:
        """Record feedback for a skill usage."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT INTO feedback_log (skill_name, session_id, outcome, task_description, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (entry.skill_name, entry.session_id, entry.outcome,
             entry.task_description, entry.created_at or now),
        )
        self._conn.commit()

    def update_effectiveness(self, name: str, new_value: float) -> None:
        """Update the effectiveness score for a skill.

        Args:
            name: Skill name.
            new_value: New effectiveness value (0.0-1.0).
        """
        self._conn.execute(
            "UPDATE skills SET effectiveness = ? WHERE name = ?",
            (new_value, name),
        )
        self._conn.commit()

    def transition_state(self, name: str, new_state: LifecycleState) -> None:
        """Transition a skill to a new lifecycle state.

        Args:
            name: Skill name.
            new_state: Target LifecycleState.
        """
        self._conn.execute(
            "UPDATE skills SET state = ? WHERE name = ?",
            (new_state.value, name),
        )
        self._conn.commit()

    def get_stale_skills(self, days: int = 30) -> list[Skill]:
        """Get active skills not used in the given number of days.

        Args:
            days: Number of days threshold.

        Returns:
            List of stale skill candidates.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        cur = self._conn.execute(
            """SELECT * FROM skills
               WHERE state = 'active' AND (last_used_at IS NULL OR last_used_at < ?)""",
            (cutoff,),
        )
        return [self._row_to_skill(row) for row in cur.fetchall()]

    def _row_to_skill(self, row: sqlite3.Row) -> Skill:
        """Convert a database row to a Skill dataclass."""
        tags = json.loads(row["profile_tags"]) if row["profile_tags"] else []
        return Skill(
            name=row["name"],
            path=row["path"],
            description=row["description"],
            trigger_text=row["trigger_text"],
            effectiveness=row["effectiveness"],
            total_uses=row["total_uses"],
            total_successes=row["total_successes"],
            gap_count=row["gap_count"],
            state=LifecycleState(row["state"]),
            profile_tags=tags,
            last_used_at=row["last_used_at"],
            last_indexed_at=row["last_indexed_at"],
            created_at=row["created_at"],
        )

    def save_embedding(self, name: str, embedding: list[float]) -> None:
        """Save or replace an embedding for a skill."""
        import struct
        blob = struct.pack(f"{len(embedding)}f", *embedding)
        self._conn.execute(
            "INSERT OR REPLACE INTO skill_embeddings (name, embedding) VALUES (?, ?)",
            (name, blob),
        )
        self._conn.commit()

    def search_similar(self, query_embedding: list[float], top_k: int = 5) -> list[tuple[str, float]]:
        """Find the top_k most similar skills by KNN distance."""
        import struct
        blob = struct.pack(f"{len(query_embedding)}f", *query_embedding)
        cur = self._conn.execute(
            """SELECT name, distance FROM skill_embeddings
               WHERE embedding MATCH ? ORDER BY distance LIMIT ?""",
            (blob, top_k),
        )
        return [(row[0], row[1]) for row in cur.fetchall()]

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
