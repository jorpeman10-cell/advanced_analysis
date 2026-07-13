# Lobe MCP Data Connector

## Purpose

`mcp_server.py` exposes the aligned v2 analysis logic as read-only MCP tools.
The installed Lobe Skill defines analysis behavior; this MCP server supplies
live Gllue evidence. It does not write tasks or change database records.

## Tools

| Tool | Use |
| --- | --- |
| `get_metric_definitions` | Target units and supported execution metrics |
| `get_company_stage_metrics` | Fiscal-year Offer / Invoice / Collection / Forecast totals |
| `get_consultant_review` | One consultant's process, collection, reserve, forecast and available cost scorecard |
| `get_forecast_pipeline` | Live and overdue Forecast review |
| `get_receivables_cashflow` | Open invoices, overdue evidence and client payment terms |
| `review_execution_metric` | Read-only completion check for one consultant target |
| `export_talent_mapping_obsidian_vault` | Export Gllue candidates and Mapping data into a local Obsidian Markdown vault |

## Conversation Performance

- Identical data loads are cached for 10 minutes so one Lobe conversation does not repeatedly open SSH/database sessions.
- When `use_ssh=true`, the MCP process maintains one reusable SSH port forward plus a pooled MySQL connection across adjacent tool calls; the legacy remote-command path remains an automatic fallback if forwarding is blocked.
- Consultant, forecast, and receivable tools return summary data by default. Use `include_evidence=true` only for record-level checking.
- `get_consultant_review` accepts one named consultant only. Use `get_company_stage_metrics` for company totals.
- For an initial management answer, prefer no more than three targeted calls and expand evidence only if the user requests verification.
- `export_talent_mapping_obsidian_vault` writes only to the local project vault directory and does not modify Gllue data. Use smaller limits for quick previews and larger limits for periodic refreshes.

## Local Setup

Install the added dependency in the Python environment used to run the app:

```powershell
python -m pip install -r requirements.txt
```

Set a private bearer token for Lobe and start the service:

```powershell
$env:RECRUITER_FINANCE_MCP_TOKEN = "<generate-a-private-token>"
$env:RECRUITER_FINANCE_MCP_HOST = "0.0.0.0"
$env:RECRUITER_FINANCE_MCP_PORT = "8765"
python mcp_server.py
```

On this Windows workspace, the helper script starts the same service in a
hidden background process and reads a user-scoped token if one is configured:

```powershell
.\start_mcp_server.ps1
```

The service loads the same `config/db_config.json` or Streamlit database
configuration used by the v2 app. Do not place database passwords in the
Skill or in Lobe prompts.

## Lobe Configuration

For Lobe running in the local Docker deployment, create a custom MCP tool:

| Field | Value |
| --- | --- |
| Type | `HTTP` |
| Identifier | `recruiter-finance-data` |
| URL | `http://host.docker.internal:8765/mcp` |
| Authentication | `Bearer Token` |
| Token | value of `RECRUITER_FINANCE_MCP_TOKEN` |

For a non-Docker Lobe client on the same machine, use
`http://localhost:8765/mcp`.

Keep the endpoint local or place it behind HTTPS and access controls before
using it outside the local computer.

## Talent Mapping Obsidian Export

After Lobe has the MCP connector enabled, ask it to call:

```text
export_talent_mapping_obsidian_vault
```

Typical prompt:

```text
请刷新 Obsidian 猎头 Mapping 知识库，候选人导出 300 条，Mapping 导出 80 张。
```

The tool returns `output_vault_path`. Open that folder in Obsidian with:

```text
Obsidian -> Open folder as vault
```

The default Lobe export path is:

```text
C:\Users\EDY\.kimi\advanced_analysis_publish\talent_mapping_vault_lobe
```
