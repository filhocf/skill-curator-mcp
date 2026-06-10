"""Profile-aware skill matching — load expected_skills from agent profiles."""
from __future__ import annotations

import json
from pathlib import Path


def load_profile(name: str, agents_dir: Path | None = None) -> list[str]:
    """Load expected_skills from an agent profile JSON.

    Args:
        name: Profile name (filename without extension).
        agents_dir: Directory containing agent JSON files.
            Defaults to ~/.kiro/agents.

    Returns:
        List of expected skill names, or [] if file/field is missing.
    """
    if agents_dir is None:
        agents_dir = Path.home() / ".kiro" / "agents"
    path = agents_dir / f"{name}.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        return data.get("expected_skills", [])
    except (json.JSONDecodeError, OSError):
        return []
