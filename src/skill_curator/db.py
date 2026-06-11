"""SQLite storage layer with sqlite-vec for embeddings."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

import sqlite_vec

from skill_curator.models import FeedbackEntry, LifecycleState, Skill

_SCHEMA = """
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
"""

_VEC_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS skill_embeddings USING vec0(
    name TEXT PRIMARY KEY,
    embedding float[384] distance_metric=cosine
);
"""


class Database:
    """SQLite database with vector search support."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self.conn = sqlite3.connect(db_path)
        self.conn.enable_load_extension(True)
        sqlite_vec.load(self.conn)
        self.conn.enable_load_extension(False)
        if db_path != ":memory:":
            self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(_SCHEMA)
        self.conn.execute(_VEC_SCHEMA)
        self.conn.commit()

    def upsert_skill(self, skill: Skill) -> None:
        """Insert or update a skill."""
        self.conn.execute(
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
               last_indexed_at=excluded.last_indexed_at""",
            (
                skill.name, skill.path, skill.description, skill.trigger_text,
                skill.effectiveness, skill.total_uses, skill.total_successes,
                skill.gap_count, skill.state.value, skill.profile_tags,
                skill.last_used_at, skill.last_indexed_at, skill.created_at,
            ),
        )
        self.conn.commit()

    def get_skill(self, name: str) -> Optional[Skill]:
        """Get a skill by name."""
        cur = self.conn.execute("SELECT * FROM skills WHERE name = ?", (name,))
        row = cur.fetchone()
        if row is None:
            return None
        return self._row_to_skill(row)

    def list_skills(self, state: Optional[LifecycleState] = None) -> list[Skill]:
        """List skills, optionally filtered by state."""
        if state:
            cur = self.conn.execute("SELECT * FROM skills WHERE state = ?", (state.value,))
        else:
            cur = self.conn.execute("SELECT * FROM skills")
        return [self._row_to_skill(row) for row in cur.fetchall()]

    def add_feedback(self, entry: FeedbackEntry) -> None:
        """Record feedback for a skill."""
        self.conn.execute(
            """INSERT INTO feedback_log (skill_name, session_id, outcome, task_description, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (entry.skill_name, entry.session_id, entry.outcome,
             entry.task_description, entry.created_at or datetime.utcnow().isoformat()),
        )
        self.conn.commit()

    def get_feedback(self, skill_name: str) -> list[FeedbackEntry]:
        """Get all feedback entries for a skill."""
        cur = self.conn.execute(
            "SELECT skill_name, outcome, task_description, session_id, created_at FROM feedback_log WHERE skill_name = ?",
            (skill_name,),
        )
        return [
            FeedbackEntry(skill_name=r[0], outcome=r[1], task_description=r[2],
                          session_id=r[3], created_at=r[4])
            for r in cur.fetchall()
        ]

    def update_effectiveness(self, name: str, value: float) -> None:
        """Update a skill's effectiveness score."""
        self.conn.execute("UPDATE skills SET effectiveness = ? WHERE name = ?", (value, name))
        self.conn.commit()

    def transition_state(self, name: str, new_state: LifecycleState) -> None:
        """Transition a skill to a new lifecycle state."""
        self.conn.execute("UPDATE skills SET state = ? WHERE name = ?", (new_state.value, name))
        self.conn.commit()

    def get_stale_skills(self, days: int = 30) -> list[Skill]:
        """Get skills not used in the given number of days."""
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        cur = self.conn.execute(
            "SELECT * FROM skills WHERE last_used_at IS NOT NULL AND last_used_at < ?",
            (cutoff,),
        )
        return [self._row_to_skill(row) for row in cur.fetchall()]

    def save_embedding(self, name: str, embedding: list[float]) -> None:
        """Save or replace an embedding for a skill."""
        import struct
        blob = struct.pack(f"{len(embedding)}f", *embedding)
        # sqlite-vec virtual tables don't support INSERT OR REPLACE
        self.conn.execute("DELETE FROM skill_embeddings WHERE name = ?", (name,))
        self.conn.execute(
            "INSERT INTO skill_embeddings (name, embedding) VALUES (?, ?)",
            (name, blob),
        )
        self.conn.commit()

    def search_similar(self, query_vec: list[float], limit: int = 5) -> list[tuple[str, float]]:
        """Search for similar skills by embedding distance."""
        import struct
        blob = struct.pack(f"{len(query_vec)}f", *query_vec)
        cur = self.conn.execute(
            "SELECT name, distance FROM skill_embeddings WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
            (blob, limit),
        )
        return [(row[0], row[1]) for row in cur.fetchall()]

    def _row_to_skill(self, row: tuple) -> Skill:
        """Convert a DB row to a Skill dataclass."""
        return Skill(
            name=row[0], path=row[1], description=row[2], trigger_text=row[3],
            effectiveness=row[4], total_uses=row[5], total_successes=row[6],
            gap_count=row[7], state=row[8], profile_tags=row[9],
            last_used_at=row[10], last_indexed_at=row[11], created_at=row[12],
        )
