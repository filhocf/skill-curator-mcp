"""Dataclasses and type definitions for skill-curator-mcp."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
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
    """A skill indexed from the filesystem.

    Args:
        name: Unique skill identifier (derived from filename).
        path: Filesystem path to the .md file.
        description: Human-readable description.
        trigger_text: Context trigger for matching.
        effectiveness: EMA score 0.0-1.0, default 0.5.
        total_uses: Total times this skill was used.
        total_successes: Total successful uses.
        gap_count: Number of gap detections.
        state: Lifecycle state.
        profile_tags: Tags for profile matching.
        last_used_at: ISO timestamp of last use.
        last_indexed_at: ISO timestamp of last index.
        created_at: ISO timestamp of creation.
    """

    name: str
    path: str
    description: Optional[str] = None
    trigger_text: Optional[str] = None
    effectiveness: float = 0.5
    total_uses: int = 0
    total_successes: int = 0
    gap_count: int = 0
    state: LifecycleState = LifecycleState.ACTIVE
    profile_tags: list[str] = field(default_factory=list)
    last_used_at: Optional[str] = None
    last_indexed_at: Optional[str] = None
    created_at: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate and coerce state field."""
        if isinstance(self.state, str):
            try:
                self.state = LifecycleState(self.state)
            except ValueError:
                raise ValueError(f"Invalid state: {self.state}")
        if not isinstance(self.state, LifecycleState):
            raise TypeError(f"state must be LifecycleState, got {type(self.state)}")


VALID_OUTCOMES = {"success", "partial", "failure"}


@dataclass
class FeedbackEntry:
    """A feedback entry for a skill usage.

    Args:
        skill_name: Name of the skill.
        session_id: Session identifier.
        outcome: One of success, partial, failure.
        task_description: Optional task context.
        created_at: ISO timestamp.
    """

    skill_name: str
    session_id: str
    outcome: str
    task_description: Optional[str] = None
    created_at: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate outcome."""
        if self.outcome not in VALID_OUTCOMES:
            raise ValueError(
                f"Invalid outcome: {self.outcome}. Must be one of {VALID_OUTCOMES}"
            )


@dataclass
class ScoutedSkill:
    """A skill discovered from external sources.

    Args:
        source_url: URL where the skill was found.
        name: Skill name.
        description: Skill description.
        relevance_score: Relevance to current gaps (0.0-1.0).
        matched_gap: Gap this skill addresses.
        status: Discovery status (new, adopted, dismissed).
        discovered_at: ISO timestamp of discovery.
    """

    source_url: str
    name: str
    description: str
    relevance_score: float
    matched_gap: str
    status: str = "new"
    discovered_at: Optional[str] = None
