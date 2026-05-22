# Recruiter Finance Tool Map

## Scope

The Advanced Analysis Streamlit tool is a management cockpit for a headhunter business.
Its v2 entrypoint is `app_v2.py`.
It combines business stage data, consultant salary/cost data, cashflow projections, consultant performance, client receivables behavior, management diagnosis, and execution follow-up.

## Main Analysis Areas

- Full dashboard: summary of company operating state.
- Management review: risk themes, revenue/cost/cashflow judgment, and consultant-level interpretation.
- Current-year data: Offer, Invoice, Collection, Forecast, carryover, and stage audit views.
- Project recommendation efficiency: project/referral/interview/Offer process metrics.
- Consultant cost efficiency: cost, collection profit, reserve, process and result metrics.
- Cashflow pressure: confirmed receivables, Forecast weighted inflow, consultant cost, runway, aging and account-term risk.
- Execution follow-up: Objectives, KR indicators, weekly progress, evidence review.
- Business decision Agent: LLM answer layer over extracted evidence and data tools.

## Stage Logic

Treat Offer, Invoice, and Collection as moving stages:

1. A business item can appear as Offer before it is invoiced.
2. Once it moves into Invoice, Offer reserve may reduce while Invoice increases.
3. Once payment is collected, invoiced-uncollected amount reduces while Collection increases.
4. Reconciliation must state whether it is checking:
   - current stage balance,
   - period additions,
   - total business value across stage flow,
   - or consultant performance attribution.

Do not assume `Offer + Invoice + Collection` is one universal KPI without defining stage scope.
Canceled or rejected Offer records must be excluded when the source stage marks them void.
Performance attribution should respect split allocations when a record has multiple contributors.

## Period Logic

- Prior-year carryover can remain part of current-year analysis when unpaid Offer, unpaid Invoice, or received payment still affects current-year cash and consultant performance.
- Forecast should represent active in-progress opportunity state. Still-active Forecast items with overdue expected dates remain management evidence until business status says otherwise.
- Cashflow projection must distinguish confirmed receivables from weighted Forecast and cost through the forecast horizon.
- When comparing user-exported system numbers with tool numbers, check period basis, stage state, canceled status, split attribution, and whether carryover was included.

## Metric Guardrails

### Offer reserve and unpaid balance

- `Offer储备金额` means still-unrealized Offer-stage reserve when the view defines it that way.
- A management unpaid exposure view may need `Offer未回 + 开票未回` if the question is total not-yet-collected value.
- Keep the label explicit to avoid mixing reserve and receivable balance.

### Invoice and Collection

- Invoice amount is invoiced value within its defined period/stage logic.
- Collection amount is received payment amount, not invoice amount repeated.
- If Invoice looks materially higher than system export, inspect duplicate joins, stage transitions, carryover filters, and allocation grain.

### Conversion ratios

- A conversion rate cannot exceed 100% when numerator and denominator describe the same cohort and stage flow.
- If a displayed ratio exceeds 100%, check time windows, legacy records entering later stages, duplicated denominator rows, and mismatched cohorts.

### Cashflow

- Cashflow safety diagnosis should use cash balance, receivables timing, weighted Forecast, consultant cost, runway, and overdue/aging evidence together.
- Slow collection is a receivables and customer-payment risk even when Offer reserve is healthy.

## Consultant Review Rules

- Evaluate consultants by both result and process.
- Use collection and profit evidence for mature consultants with sufficient conversion time.
- For consultants with less than roughly six months of tenure, weight pipeline, Forecast, average referrals, referral-to-interview quality, active positions, and early Offer evidence more heavily.
- A consultant with abundant reserve but slow collection should not be labeled as an Offer conversion problem without evidence.
- Review at consultant scope when the user asks about a named consultant. Do not answer only with company-wide risk.

## Data Validation Checklist

When a number disagrees with the user's system export:

1. Identify the source metric name and field grain.
2. Compare stage state and stage transition timing.
3. Check carryover inclusion.
4. Check canceled/void/refused rows.
5. Check split consultant allocation.
6. Check join duplication by entity ID.
7. Compare current balance against period additions before changing the table.
