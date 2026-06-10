"""Tests for skill_curator.indexer — filesystem scanning and embedding generation."""
from pathlib import Path

import pytest

from skill_curator.indexer import parse_skill_md, reindex_all, scan_skills_dir


class MockEncoder:
    """Deterministic encoder for testing."""

    def encode(self, text: str) -> list[float]:
        return [0.1] * 384


@pytest.fixture
def skills_dir(tmp_path: Path) -> Path:
    """Create a temp skills directory with sample .md files."""
    (tmp_path / "python-rest.md").write_text(
        "---\ndescription: Build REST APIs\ntrigger: REST endpoint\n---\n# Python REST\nContent here."
    )
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "testing.md").write_text("# Testing\nFirst line as description.")
    return tmp_path


class TestParseSkillMd:
    def test_with_frontmatter(self, tmp_path: Path) -> None:
        md = tmp_path / "skill.md"
        md.write_text("---\ndescription: My skill\ntrigger: when X\n---\n# Title\nBody.")
        result = parse_skill_md(md)
        assert result["description"] == "My skill"
        assert result["trigger"] == "when X"

    def test_without_frontmatter(self, tmp_path: Path) -> None:
        md = tmp_path / "skill.md"
        md.write_text("# First Line Title\nBody content.")
        result = parse_skill_md(md)
        assert result["description"] == "First Line Title"

    def test_nonexistent_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            parse_skill_md(Path("/nonexistent/skill.md"))


class TestScanSkillsDir:
    def test_finds_md_recursively(self, skills_dir: Path) -> None:
        found = scan_skills_dir(skills_dir)
        assert len(found) == 2

    def test_excludes_special_files(self, tmp_path: Path) -> None:
        """README.md, CHANGELOG.md, MEMORY.md, AGENTS.md, ARCHITECTURE.md, PRD.md excluded."""
        for name in ["README.md", "CHANGELOG.md", "MEMORY.md", "AGENTS.md", "ARCHITECTURE.md", "PRD.md"]:
            (tmp_path / name).write_text(f"# {name}")
        (tmp_path / "real-skill.md").write_text("# Real Skill\nContent.")
        found = scan_skills_dir(tmp_path)
        names = [p.name for p in found]
        assert "real-skill.md" in names
        assert "README.md" not in names
        assert "PRD.md" not in names

    def test_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        found = scan_skills_dir(tmp_path)
        assert found == []


class TestReindexAll:
    def test_indexes_skills_and_saves_embeddings(self, skills_dir: Path) -> None:
        from skill_curator.db import Database

        db = Database(":memory:")
        count = reindex_all(skills_dir, db, encoder=MockEncoder())
        assert count == 2
        skill = db.get_skill("python-rest")
        assert skill is not None

    def test_empty_dir_returns_zero(self, tmp_path: Path) -> None:
        from skill_curator.db import Database

        db = Database(":memory:")
        count = reindex_all(tmp_path, db, encoder=MockEncoder())
        assert count == 0
