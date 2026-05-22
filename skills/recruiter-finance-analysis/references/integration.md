# Integration Notes

## What a Lobe Skill Can Do

A Lobe skill bundle can teach an agent:

- which Recruiter Finance Tool views and metrics to use,
- how to interpret stage logic and cashflow,
- how to turn management requests into OKR/KR structure,
- how to diagnose data discrepancies and ask for the right evidence.

A skill bundle alone does not automatically create live database access.

## Current Tool Surface

- Streamlit app entrypoint: `app_v2.py`.
- Streamlit Cloud uses the GitHub repository and runtime secrets.
- Local/database configuration includes Gllue database and optional SSH access.
- Salary values can come from upload or Streamlit secrets when no new upload is supplied.
- LLM keys and database secrets must remain outside the skill bundle.

## Lobe Installation Paths

Lobe supports importing a skill from:

- a `SKILL.md` URL,
- a GitHub repository URL,
- a ZIP skill package URL.

Use a ZIP or repository skill bundle when references are needed.
Use a single `SKILL.md` only for a small instruction-only skill.

## Live Data Options

Choose one live integration path only after confirming runtime constraints:

1. Read-only API layer:
   - Expose narrowly scoped endpoints for summary metrics, consultant review, cashflow, task review, and evidence.
   - Keep database credentials and LLM keys server-side.
   - Prefer explicit date range and consultant filters.
2. MCP/tool server:
   - Wrap the same read-only queries as tools callable by the Lobe agent.
   - Keep write actions separate and permissioned.
3. Browser interaction:
   - Let an agent operate the Streamlit app through an approved browser tool when API work is not ready.

## Recommended Capability Split

Phase 1: skill bundle

- Field口径.
- Management diagnosis rules.
- OKR follow-up rules.
- Deployment and configuration guardrails.

Phase 2: read-only tool surface

- `get_company_snapshot(period)`
- `get_consultant_review(consultant, period)`
- `get_cashflow_projection(days)`
- `get_receivable_aging(client_or_period)`
- `get_execution_review(owner, period)`

Phase 3: controlled write surface

- Save Objective and KR indicators.
- Update weekly follow-up notes.
- Add manager confirmation and audit trail.

## Safety Rules

- Never put database passwords, SSH passwords, API keys, or salary secrets into the skill bundle.
- Do not grant a Lobe agent write access to production data until write actions, audit trail, and permissions are explicit.
- Prefer current tool APIs or evidence exports over asking the model to infer numbers from screenshots alone.
