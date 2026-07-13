"""Standalone MCP server for Talent Mapping LLM.

This server is intentionally focused on headhunting talent mapping and
Obsidian-style Markdown wiki export. It does not expose finance-analysis tools.
"""

from __future__ import annotations

import hmac
import os
from pathlib import Path
from typing import Any

from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from pydantic import AnyHttpUrl

from talent_mapping_obsidian_exporter import build_graph_data, export_graph_html, export_vault


MCP_HOST = os.getenv("TALENT_MAPPING_MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("TALENT_MAPPING_MCP_PORT", "8770"))
MCP_PUBLIC_BASE_URL = os.getenv("TALENT_MAPPING_MCP_PUBLIC_URL", f"http://localhost:{MCP_PORT}")
AUTH_MODE = os.getenv("TALENT_MAPPING_MCP_AUTH", "bearer").strip().lower()
READ_SCOPE = "talent-mapping:read"
MAX_CANDIDATE_EXPORT = 2000
MAX_MAPPING_EXPORT = 500
DEFAULT_OUTPUT = Path(os.getenv("TALENT_MAPPING_OBSIDIAN_OUTPUT", "/app/talent_mapping_vault"))


class StaticBearerVerifier(TokenVerifier):
    """Validate the private token configured for this MCP endpoint."""

    async def verify_token(self, token: str) -> AccessToken | None:
        expected = os.getenv("TALENT_MAPPING_MCP_TOKEN") or os.getenv("RECRUITER_FINANCE_MCP_TOKEN", "")
        if expected and hmac.compare_digest(token, expected):
            return AccessToken(token=token, client_id="lobe", scopes=[READ_SCOPE])
        return None


_MCP_KWARGS = {
    "name": "Talent Mapping LLM",
    "instructions": (
        "Standalone read-only talent mapping tools. Use this server for Gllue candidate, "
        "company organization Mapping, relationship graph, and Obsidian LLM Wiki export tasks. "
        "Do not search Lobe knowledge bases when the user asks to refresh the vault; call "
        "export_talent_mapping_obsidian_vault directly."
    ),
    "host": MCP_HOST,
    "port": MCP_PORT,
    "stateless_http": True,
    "json_response": True,
}

if AUTH_MODE not in {"none", "noauth", "disabled", "off"}:
    _MCP_KWARGS["token_verifier"] = StaticBearerVerifier()
    _MCP_KWARGS["auth"] = AuthSettings(
        issuer_url=AnyHttpUrl(MCP_PUBLIC_BASE_URL),
        resource_server_url=AnyHttpUrl(MCP_PUBLIC_BASE_URL),
        required_scopes=[READ_SCOPE],
    )

mcp = FastMCP(**_MCP_KWARGS)


@mcp.tool()
def export_talent_mapping_obsidian_vault(
    candidate_limit: int = 300,
    mapping_limit: int = 80,
) -> dict[str, Any]:
    """Refresh the local Obsidian-style headhunting Talent Mapping Markdown vault."""
    safe_candidate_limit = max(1, min(int(candidate_limit or 300), MAX_CANDIDATE_EXPORT))
    safe_mapping_limit = max(1, min(int(mapping_limit or 80), MAX_MAPPING_EXPORT))
    export_vault(DEFAULT_OUTPUT, safe_candidate_limit, safe_mapping_limit)
    graph_result = export_graph_html(DEFAULT_OUTPUT, max_nodes=1200, max_edges=4000)
    return {
        "status": "success",
        "server": "talent-mapping-llm",
        "read_only_database": True,
        "output_vault_path": str(DEFAULT_OUTPUT.resolve()),
        "graph_html_path": graph_result["graph_html_path"],
        "graph_stats": graph_result["stats"],
        "obsidian_open_action": "Open the returned folder as an Obsidian vault.",
        "limits": {
            "candidate_limit": safe_candidate_limit,
            "mapping_limit": safe_mapping_limit,
            "max_candidate_limit": MAX_CANDIDATE_EXPORT,
            "max_mapping_limit": MAX_MAPPING_EXPORT,
        },
        "main_files": {
            "index": str((DEFAULT_OUTPUT / "index.md").resolve()),
            "log": str((DEFAULT_OUTPUT / "log.md").resolve()),
        },
    }


@mcp.tool()
def get_talent_mapping_llm_status() -> dict[str, Any]:
    """Return the standalone Talent Mapping LLM server status and vault location."""
    return {
        "status": "running",
        "server": "talent-mapping-llm",
        "output_vault_path": str(DEFAULT_OUTPUT.resolve()),
        "tools": ["export_talent_mapping_obsidian_vault", "get_talent_mapping_llm_status"],
        "rule": "This server reads Gllue data and writes a local Markdown vault; it does not modify Gllue records.",
    }


@mcp.tool()
def get_talent_mapping_graph(
    max_nodes: int = 800,
    max_edges: int = 2500,
) -> dict[str, Any]:
    """Return Obsidian-style graph data parsed from the current Talent Mapping vault."""
    safe_nodes = max(20, min(int(max_nodes or 800), 2000))
    safe_edges = max(20, min(int(max_edges or 2500), 8000))
    return build_graph_data(DEFAULT_OUTPUT, max_nodes=safe_nodes, max_edges=safe_edges)


@mcp.tool()
def export_talent_mapping_graph_view(
    refresh_vault: bool = False,
    candidate_limit: int = 300,
    mapping_limit: int = 80,
    max_nodes: int = 1200,
    max_edges: int = 4000,
) -> dict[str, Any]:
    """Export an interactive HTML Graph View for the current Talent Mapping vault."""
    if refresh_vault:
        export_talent_mapping_obsidian_vault(candidate_limit=candidate_limit, mapping_limit=mapping_limit)
    safe_nodes = max(20, min(int(max_nodes or 1200), 2500))
    safe_edges = max(20, min(int(max_edges or 4000), 10000))
    result = export_graph_html(DEFAULT_OUTPUT, max_nodes=safe_nodes, max_edges=safe_edges)
    result["server"] = "talent-mapping-llm"
    result["open_note"] = "Open graph_html_path in a browser, or retrieve it from the mounted server vault directory."
    return result


def main() -> None:
    if AUTH_MODE not in {"none", "noauth", "disabled", "off"} and not (
        os.getenv("TALENT_MAPPING_MCP_TOKEN") or os.getenv("RECRUITER_FINANCE_MCP_TOKEN")
    ):
        raise RuntimeError("Set TALENT_MAPPING_MCP_TOKEN or RECRUITER_FINANCE_MCP_TOKEN before starting the server.")
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
