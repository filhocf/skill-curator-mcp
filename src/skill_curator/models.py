"""Domain dataclasses and enums for skill-curator."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


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
    description: Optional[str] = None
    trigger_text: Optional[str] = None
    effectiveness: float = 0.5
    total_uses: int = 0
    total_successes: int = 0
    gap_count: int = 0
    state: LifecycleState | str = LifecycleState.ACTIVE
    profile_tags: Optional[str] = None
    last_used_at: Optional[str] = None
    last_indexed_at: Optional[str] = None
    created_at: Optional[str] = None

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
    session_id: Optional[str] = None
    created_at: Optional[str] = None

    def __post_init__(self) -> None:
        valid = {"success", "partial", "failure"}
        if self.outcome not in valid:
            raise ValueError(f"Invalid outcome: {self.outcome}. Must be one of {valid}")


@dataclass
class ScoutedSkill:
    """An externally discovered skill."""

    source_url: str
    name: str
    description: Optional[str] = None
    relevance_score: Optional[float] = None
    matched_gap: Optional[str] = None
    status: str = "new"
    discovered_at: Optional[str] = None
