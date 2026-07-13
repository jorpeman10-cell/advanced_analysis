---
name: talent-mapping-llm
description: "Use this skill for headhunting Talent Mapping, Gllue candidate and company organization Mapping data, Obsidian-style LLM Wiki export, talent relationship graphs, shared employer/school/role/region/performance signals, and candidate mapping workflows."
---

# Talent Mapping LLM

## Purpose

Use this skill when the user wants to build, refresh, or analyze a headhunting Talent Mapping knowledge base.
The core output is an Obsidian-style Markdown vault that turns Gllue candidate records and organization Mapping trees into linked pages.

## MCP Tool

When live tools are available, prefer the standalone MCP server named `talent-mapping-llm`.

Use:

```text
export_talent_mapping_obsidian_vault
```

for requests such as:

- 刷新 Obsidian 猎头 Mapping 知识库
- 生成 Talent Mapping LLM Wiki
- 从谷露导出候选人和 Mapping 到 Obsidian
- 候选人导出 300 条，Mapping 导出 80 张

Do not search Lobe knowledge bases for this task. The vault is created by calling the MCP tool.

For graph view requests, use:

```text
get_talent_mapping_graph
export_talent_mapping_graph_view
```

Use `get_talent_mapping_graph` when the user wants structured graph data for analysis.
Use `export_talent_mapping_graph_view` when the user wants an Obsidian-like interactive relationship view in HTML.
Do not start `lobe-cloud-sandbox` for these graph tasks.

## Operating Rules

- Treat Gllue as the source of facts.
- Keep the export read-only for Gllue; never modify candidate, Mapping, job, invoice, or client records.
- Separate facts, inferred relationships, and assessment notes.
- Use Obsidian links to connect people, companies, schools, roles, regions, consultants, teams, Mapping nodes, and performance signals.
- When the user gives candidate limits or Mapping limits, pass them to `candidate_limit` and `mapping_limit`.
- If the tool returns `output_vault_path`, tell the user that this is the vault folder to open or retrieve.

## Talent Mapping Logic

Key relationship dimensions:

- Person: candidate, manager, mentor, consultant
- Company: current employer, former employer, client, target company
- Education: school, major
- Role: title, function, seniority
- Region: city, area, market
- Performance: referral, interview, offer, onboard, collection, high-growth signal
- Mapping: company organization tree, department node, role node, person node, notes

When interpreting a Talent Mapping page, look for hidden links:

- shared employer
- shared school
- shared region
- shared consultant/team
- same role family
- same Mapping node or org tree
- different period performance under similar market pressure

## Output Style

For refresh tasks, be direct:

1. State that the standalone `talent-mapping-llm` tool should be called.
2. Mention candidate and Mapping limits.
3. Return the generated `output_vault_path`.
4. Tell the user the next action: open or retrieve the vault.

For graph view tasks:

1. Call `export_talent_mapping_graph_view`.
2. If the vault should be refreshed first, pass `refresh_vault=true`.
3. Return `graph_html_path` and the node/edge counts.
4. Explain that this is an Obsidian-like graph view, not Obsidian's native renderer.

For analysis tasks, answer with:

1. Direct mapping insight.
2. Evidence from linked dimensions.
3. Risks or missing information.
4. Next validation questions for recruiters.
