"""Domain dataclasses and enums for skill-curator."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LifecycleState(Enum):
    """Skill lifecycle states."""

    ACTIVE = "active"
    STALE = "stale"
    ARCHIVED = "archived"
    DRAFT = "draft"


@dataclass
class Skill:
    """A curated skill entry."""

    name: str
    path: str
    description: str | None = None
    trigger_text: str | None = None
    effectiveness: float = 0.5
    total_uses: int = 0
    total_successes: int = 0
    gap_count: int = 0
    state: LifecycleState | str = LifecycleState.ACTIVE
    profile_tags: str | None = None
    last_used_at: str | None = None
    last_indexed_at: str | None = None
    created_at: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.state, str):
            try:
                self.state = LifecycleState(self.state)
            except ValueError:
                raise ValueError(f"Invalid state: {self.state}")


@dataclass
class FeedbackEntry:
    """A feedback log entry."""

    skill_name: str
    outcome: str
    task_description: str
    session_id: str | None = None
    created_at: str | None = None

    def __post_init__(self) -> None:
        valid = {"success", "partial", "failure", "irrelevant"}
        if self.outcome not in valid:
            raise ValueError(f"Invalid outcome: {self.outcome}. Must be one of {valid}")


@dataclass
class ScoutedSkill:
    """An externally discovered skill."""

    source_url: str
    name: str
    description: str | None = None
    relevance_score: float | None = None
    matched_gap: str | None = None
    status: str = "new"
    discovered_at: str | None = None
