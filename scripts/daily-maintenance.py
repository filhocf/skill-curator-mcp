#!/usr/bin/env python3
"""Daily maintenance script for skill-curator."""

from pathlib import Path
from skill_curator.db import Database
from skill_curator.maintenance import run_maintenance
import json
import os

db_dir = Path(
    os.environ.get(
        "SKILL_CURATOR_DB_DIR", str(Path.home() / ".local/share/skill-curator")
    )
)
skills_dir = Path(
    os.environ.get("SKILL_CURATOR_SKILLS_DIR", str(Path.home() / ".kiro/skills"))
)

db = Database(str(db_dir / "curator.db"))
result = run_maintenance(db, skills_dir)
print(json.dumps(result, indent=2))
db.close()
