"""
Atlassian Confluence Cloud MCP Server — entry point.

Creates the FastMCP instance and starts the server using stdio transport.
Tool definitions live in tools.py; the HTTP client layer lives in client.py.

Authentication:
    Basic Auth  — set CONFLUENCE_EMAIL + CONFLUENCE_API_TOKEN
    Bearer token — set CONFLUENCE_BEARER_TOKEN

Required environment variable:
    CONFLUENCE_BASE_URL  e.g. https://your-domain.atlassian.net
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from confluence_mcp.client import validate_config

mcp = FastMCP(
    "Confluence Cloud",
    instructions=(
        "Tools for administering Atlassian Confluence Cloud wiki pages. "
        "Supports creating, reading, updating, moving (reparenting), restoring, "
        "and deleting pages; navigating the page tree; listing and reading spaces; "
        "reading labels; reading version history; managing footer and inline comments; "
        "reading attachments; managing page content properties; and managing tasks. "
        "Set CONFLUENCE_BASE_URL plus either (CONFLUENCE_EMAIL + CONFLUENCE_API_TOKEN) "
        "or CONFLUENCE_BEARER_TOKEN before starting the server."
    ),
)

# Import tools module so all @mcp.tool() decorators are executed and the tools
# are registered on the mcp instance above. This import must come after mcp is
# defined to avoid a circular import.
import confluence_mcp.tools  # noqa: E402, F401


def main() -> None:
    """Run the Confluence MCP server using stdio transport."""
    validate_config()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
