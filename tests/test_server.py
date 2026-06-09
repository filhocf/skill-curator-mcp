"""Tests for skill_curator.server — FastMCP server setup."""

from skill_curator.server import main, mcp


class TestServerSetup:
    """Tests for MCP server configuration."""

    def test_server_instantiates(self) -> None:
        """FastMCP server instantiates without error."""
        assert mcp is not None
        assert mcp.name == "skill-curator"

    def test_all_tools_registered(self) -> None:
        """All 8 tools are registered in the MCP server."""
        tool_names = list(mcp._tool_manager._tools.keys())
        expected = [
            "skill_match",
            "skill_feedback",
            "skill_gaps",
            "skill_lifecycle",
            "skill_promote",
            "skill_archive",
            "skill_reindex",
            "skill_scout",
        ]
        for name in expected:
            assert name in tool_names, f"Tool '{name}' not registered. Found: {tool_names}"

    def test_main_is_callable(self) -> None:
        """main() function exists and is callable."""
        assert callable(main)
