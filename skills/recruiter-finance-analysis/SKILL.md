---
name: recruiter-finance-analysis
description: "Use this skill for Recruiter Finance Tool analysis, metric definitions, cashflow, forecast, consultant performance, Offer Invoice Collection stage review, OKR execution follow-up, data anomaly review, and Lobe integration planning."
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
