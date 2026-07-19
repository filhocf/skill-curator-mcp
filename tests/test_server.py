"""Tests for skill_curator.server — FastMCP server registration (phase 0.2.0 RED)."""

from skill_curator.server import main, mcp


class TestServerSetup:
    def test_fastmcp_instantiates_without_error(self) -> None:
        assert mcp is not None

    def test_tools_registered(self) -> None:
        tools = mcp.list_tools()
        assert (
            len(tools) == 13
        )  # 10 original + skill_evolve + skill_rollback + skill_scout_ingest

    def test_instructions_not_none(self) -> None:
        assert mcp.instructions is not None

    def test_main_is_callable(self) -> None:
        assert callable(main)
