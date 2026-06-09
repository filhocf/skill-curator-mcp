"""Tests for skill_curator.indexer — filesystem scan and embedding generation."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from skill_curator.db import Database
from skill_curator.indexer import parse_skill_md, reindex_all, scan_skills_dir
from skill_curator.models import Skill


@pytest.fixture
def db() -> Database:
    """In-memory database for testing."""
    return Database(":memory:")


@pytest.fixture
def mock_encoder() -> MagicMock:
    """Mock encoder with encode method."""
    encoder = MagicMock()
    encoder.encode.return_value = [0.1] * 384
    return encoder


class TestParseSkillMd:
    """Tests for parsing skill markdown files."""

    def test_extracts_frontmatter(self, tmp_path: Path) -> None:
        """parse_skill_md extracts description and trigger from YAML frontmatter."""
        skill_file = tmp_path / "test-skill.md"
        skill_file.write_text(
            "---\n"
            "description: Does testing things\n"
            "trigger: when writing tests\n"
            "---\n"
            "# Test Skill\n\nBody content here.\n"
        )
        result = parse_skill_md(skill_file)
        assert result.name == "test-skill"
        assert result.description == "Does testing things"
        assert result.trigger_text == "when writing tests"

    def test_name_from_filename(self, tmp_path: Path) -> None:
        """Skill name is derived from filename stem."""
        skill_file = tmp_path / "my-cool-skill.md"
        skill_file.write_text("# My Cool Skill\n\nNo frontmatter.\n")
        result = parse_skill_md(skill_file)
        assert result.name == "my-cool-skill"

    def test_missing_file_raises(self) -> None:
        """parse_skill_md raises FileNotFoundError for missing files."""
        with pytest.raises(FileNotFoundError):
            parse_skill_md(Path("/nonexistent/skill.md"))

    def test_no_frontmatter(self, tmp_path: Path) -> None:
        """File without frontmatter returns Skill with None description."""
        skill_file = tmp_path / "plain.md"
        skill_file.write_text("Just some text without frontmatter delimiters.\n")
        result = parse_skill_md(skill_file)
        assert result.name == "plain"
        assert result.description is None

    def test_path_stored_as_string(self, tmp_path: Path) -> None:
        """Skill.path is the string representation of the file path."""
        skill_file = tmp_path / "x.md"
        skill_file.write_text("---\ndescription: X\n---\n")
        result = parse_skill_md(skill_file)
        assert result.path == str(skill_file)


class TestScanSkillsDir:
    """Tests for directory scanning."""

    def test_finds_md_files(self, tmp_path: Path) -> None:
        """scan_skills_dir finds all .md files recursively."""
        (tmp_path / "a.md").write_text("# A\n")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "b.md").write_text("# B\n")
        (tmp_path / "ignore.txt").write_text("not md")
        paths = scan_skills_dir(tmp_path)
        names = [p.name for p in paths]
        assert "a.md" in names
        assert "b.md" in names
        assert "ignore.txt" not in names

    def test_empty_dir(self, tmp_path: Path) -> None:
        """scan_skills_dir returns empty list for empty directory."""
        assert scan_skills_dir(tmp_path) == []


class TestReindexAll:
    """Tests for full reindex operation."""

    def test_indexes_all_skills(
        self, db: Database, mock_encoder: MagicMock, tmp_path: Path
    ) -> None:
        """reindex_all finds and upserts all .md files."""
        (tmp_path / "skill-a.md").write_text("---\ndescription: Skill A\n---\n# A\n")
        (tmp_path / "skill-b.md").write_text("---\ndescription: Skill B\n---\n# B\n")
        count = reindex_all(db, tmp_path, mock_encoder)
        assert count == 2
        assert db.get_skill("skill-a") is not None
        assert db.get_skill("skill-b") is not None

    def test_encoder_called(
        self, db: Database, mock_encoder: MagicMock, tmp_path: Path
    ) -> None:
        """reindex_all calls encoder.encode for each skill."""
        (tmp_path / "s.md").write_text("---\ndescription: hello\n---\n")
        reindex_all(db, tmp_path, mock_encoder)
        mock_encoder.encode.assert_called_once()

    def test_returns_zero_for_empty_dir(
        self, db: Database, mock_encoder: MagicMock, tmp_path: Path
    ) -> None:
        """reindex_all returns 0 for empty directory."""
        assert reindex_all(db, tmp_path, mock_encoder) == 0
