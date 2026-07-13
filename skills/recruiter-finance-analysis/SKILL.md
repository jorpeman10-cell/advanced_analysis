---
name: recruiter-finance-analysis
description: "Use this skill for Recruiter Finance Tool analysis, metric definitions, cashflow, forecast, consultant performance, Offer Invoice Collection stage review, OKR execution follow-up, data anomaly review, Talent Mapping Obsidian wiki export, and Lobe integration planning."
---

# Recruiter Finance Analysis

## Purpose

Use the Recruiter Finance Tool as a management analysis system, not a generic finance dashboard.
Keep answers grounded in the tool's field definitions, business stage logic, cashflow timing, consultant maturity, and OKR follow-up workflow.

## Workflow

1. Classify the request before answering:
   - Metric explanation or口径 review.
   - Data anomaly review or reconciliation.
   - Management diagnosis for cashflow, client structure, pipeline, consultant cost, or conversion.
   - OKR / execution follow-up design.
   - Talent Mapping / Obsidian wiki export from Gllue candidate and Mapping data.
   - Deployment, configuration, or Lobe integration.
2. Read only the reference needed for that request:
   - Read [references/tool-map.md](references/tool-map.md) for dashboard areas, business logic, metrics, and review guardrails.
   - Read [references/okr-followup.md](references/okr-followup.md) for Objective, KR, weekly follow-up, and completion review behavior.
   - Read [references/integration.md](references/integration.md) for Streamlit, secrets, GitHub, Lobe skill, API, and MCP boundaries.
3. Separate evidence from interpretation:
   - State which tool metric, data stage, period, and consultant/customer scope supports a conclusion.
   - Flag missing data, suspected duplicated stages, canceled records, overdue Forecast items, or salary/config gaps before making a firm judgment.
4. Prefer actionable management output:
   - For diagnosis, give the direct judgment, why, risks, and next checks/actions.
   - For OKR work, define Objective first, then measurable KR or behavior/result indicators with owner and period.
   - For data discrepancies, identify the likely field or stage mismatch and the validation path.

## Operating Rules

- Treat Offer, Invoice, and Collection as dynamic business stages. Do not silently double-count the same business value across stages.
- Distinguish unpaid Offer reserve from invoiced-uncollected balance when the metric name or user question requires it.
- Include historical carryover when it remains part of the analysis period's active business reality, especially prior-year unpaid Offer, unpaid Invoice, and received payment that affect current-year management analysis.
- Treat active Forecast as current in-progress opportunity evidence. Do not exclude still-active items only because an expected date is overdue.
- Judge consultant results with time context. For consultants with less than roughly six months of tenure, emphasize pipeline, Forecast, referral/interview process quality, and ramp evidence before over-weighting realized collection.
- Do not call slow collection an Offer conversion problem when reserve is healthy and the risk is payment timing or receivables follow-up.
- Do not invent consultant, customer, or cashflow facts when the tool data or user evidence is absent.

## Gllue Data Digest

Use this compact map when bundled references are not available:

| Domain | Tables | Main Keys | Core Use |
|---|---|---|---|
| Consultant organization | `user`, `team` | `user.team_id -> team.id` | Consultant name, team, active status, join and leave dates. |
| Client and terms | `client`, `clientcontract` | `clientcontract.client_id -> client.id` | Client name and contract payment terms. |
| Project | `joborder` | `joborder.client_id -> client.id` | New project count, live jobs, role/client structure. |
| Referral process | `jobsubmission`, `cvsent`, `clientinterview` | Process tables link through `jobsubmission_id`; jobsubmission links to joborder | Referral count, interview count, referral-to-interview ratio, average referrals. |
| Business stage | `offersign`, `invoice`, `invoiceassignment` | Offer and invoice facts link to jobsubmission/joborder; allocations link through `invoiceassignment.invoice_id` | Offer checks, Invoice stage, Collection stage, consultant revenue splits. |
| Pipeline | `forecast`, `forecastassignment` | `forecast.job_order_id -> joborder.id`; `forecastassignment.forecast_id -> forecast.id` | Forecast amount, stage, expected close date, consultant pipeline split. |

For consultant-level revenue or reserve, prefer `invoiceassignment.revenue` when a split exists.
For company invoice amount, use `invoice.invoiceAmount`.
For company collection, use `invoice.paymentReceived` and `invoice.paymentReceivedDate`.
For actual consultant collection contribution, use received invoices plus assignment revenue.

Build unpaid-invoice due dates in this order:
1. `invoice.estimatepaymentReceivedDate`.
2. `invoice.sentDate + invoice.payment_days`.
3. `invoice.sentDate + clientcontract.payment_terms`.
4. `invoice.dateAdded + 35 days` for `Invoice Added` fallback.

When a number conflicts with a Gllue export, check period, business stage, prior-year carryover, inactive/void records, collaboration split, and join grain before changing a formula.

## OKR Follow-up Digest

Execution follow-up should use four product steps:
1. Objective target.
2. KR indicator entry.
3. Weekly follow-up.
4. Completion review and evidence.

Keep Objective qualitative. Keep KR checkable with owner, period, metric, operator, and target.
Prefer system-supported metrics such as:

- `BD新增客户数`.
- `新增岗位/项目数`.
- `平均推荐量`.
- `推面比`.
- `新增Offer数`.
- `回款金额`.
- `Offer储备金额`.

Treat `task` as the manager-facing sentence, `metric` as the structured review measure, and `target_value` as the machine-checkable number.
For percentages, clarify whether the stored value is decimal form such as `0.5` or display form such as `50%`.

## Output Patterns

For a metric explanation, answer in this order:
1. What the metric means.
2. Its unit and denominator/numerator if it is a ratio.
3. Which period and stage scope matter.
4. Common misreadings.

For a management review, answer in this order:
1. Direct judgment.
2. Evidence by cashflow, pipeline, consultant, client, or execution dimension.
3. Risks or data caveats.
4. Recommended management action and next check.

For OKR work, answer in this order:
1. Objective.
2. Owner and assessment period.
3. KR / metric list with target values.
4. Weekly progress reminders and evidence path.
5. Items that still need manager confirmation.

## Integration Boundary

This skill captures the tool's operating knowledge and analysis workflow.
It does not by itself grant a Lobe agent live access to the Streamlit app or database.
When the user requests live querying from Lobe, follow [references/integration.md](references/integration.md) and propose a read-only API, MCP server, or an approved browser/tool path.

When the user asks to create or refresh an Obsidian-style headhunting Talent Mapping knowledge base, use the MCP tool `export_talent_mapping_obsidian_vault` if available. Treat it as a one-way local export: it reads Gllue data, writes Markdown notes into the local vault directory, and does not update Gllue records. After the export, tell the user to open the returned `output_vault_path` in Obsidian with `Open folder as vault`.
