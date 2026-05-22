# OKR Execution Follow-up

## Product Intent

Execution follow-up turns monthly management actions into trackable Objectives and measurable KR indicators, then checks completion from system data during the selected review period.

The preferred product structure is:

1. Objective target.
2. KR indicator entry.
3. Weekly follow-up.
4. Review and evidence check.

## Objective Rules

- Record direction and management intent first.
- Keep Objective qualitative and meaningful.
- Examples:
  - Improve one consultant's ramp quality.
  - Shift client structure toward target accounts.
  - Strengthen cash collection discipline for overdue receivables.
  - Build a new project source in a target therapeutic area.

## KR and Indicator Rules

- Use selected system-supported metrics when possible to reduce parsing mistakes.
- A KR must include owner, assessment period, metric, operator, and target value.
- Distinguish behavior quantity from result quantity.
- Examples:
  - `BD新增客户数 >= 2`
  - `新增岗位/项目数 >= 3`
  - `平均推荐量 >= 3`
  - `推面比 >= 50%`
  - `新增Offer数 >= 1`
  - `回款金额 >= 100000`

`task` is the human-readable management statement.
`metric` is the structured measure used for review.
`target_value` is the machine-checkable number:

- Store ratios as normalized numeric values when the system uses decimal form, for example `50%` as `0.5`.
- Store money and count targets as numeric values, for example `100000` or `3`.
- Display formatting can render percent, currency, or count for managers.

## Weekly Follow-up

- Weekly reminders are for progress visibility before month-end.
- Weekly notes may track:
  - current progress,
  - blockers,
  - next step,
  - manager intervention,
  - evidence still missing.
- Management goals can include qualitative direction such as target client, target role, target therapeutic field, or account structure change.
- Keep qualitative goal context linked to the measurable KR where possible.

## Review Behavior

- Review one consultant or one owner scope at a time when managers need actionable accountability.
- Let the manager filter owners for review.
- Show Objective/KR grouping before raw line-item detail.
- Evidence detail should remain available but should not overwhelm the task library view.
- If system data cannot verify a management goal directly, mark it as manual evidence or pending schema support.

## Agent Behavior

- The OKR assistant should clarify ambiguous owner, period, metric, or target rather than inventing them.
- The assistant may use system context to suggest targets and highlight consultant maturity or past performance baseline.
- The assistant should not collapse Objective and KR into one flat task list.
- The assistant should summarize confirmed task details before saving indicators.
