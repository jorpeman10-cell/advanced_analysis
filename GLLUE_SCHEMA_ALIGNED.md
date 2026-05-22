# Gllue Schema Aligned for Advanced Analysis

This document records the Gllue database structures that have been aligned with the
`advanced_analysis` v2 analysis logic. It is intentionally limited to the tables,
relationships, fields, and metric definitions used by this tool.

## 1. Core Business Tables

| Business Domain | Gllue Table | Primary / Relation Keys | Aligned Fields | Tool Usage | Notes |
|---|---|---|---|---|---|
| Consultant | `user` | `id` | `englishName`, `chineseName`, `team_id`, `status`, `joinInDate`, `leaveDate` | Consultant list, team mapping, active status, tenure-aware review | Consultant display name is English name plus Chinese name. |
| Team | `team` | `id`, `parent_id` | `name` | Team aggregation | `user.team_id -> team.id`. |
| Client | `client` | `id` | `name` | Client dimension | Joined from joborders and invoices. |
| Client Contract | `clientcontract` | `id`, `client_id` | `payment_terms`, `startDate`, `expireDate`, `is_deleted`, `invalid` | Contract payment terms | Contract terms are one due-date source, not the only due-date source. |
| Project / Position | `joborder` | `id` | `client_id`, `addedBy_id`, `jobTitle`, `jobStatus`, `dateAdded`, `openDate`, `closeDate`, `function_normal`, `is_deleted` | New projects, live projects, project mix, project-to-offer review | New project period is based on `dateAdded`. |
| Process Spine | `jobsubmission` | `id`, `joborder_id`, `candidate_id` | `onboardDate`, `estimate_onboardDate`, `active` | Recommendation-to-offer/onboard linkage | Many process tables connect through `jobsubmission_id`. |
| Referral | `cvsent` | `id`, `jobsubmission_id` | `user_id`, `client_id`, `joborder_id`, `dateAdded`, `active` | Referrals, average referrals, referral-to-interview process | Use active referrals. |
| Client Interview | `clientinterview` | `id`, `jobsubmission_id` | `round`, `status`, `date`, `active` | Interview count, first interview, referral-to-interview ratio | Linked to referral flow through `jobsubmission_id`. |
| Offer Record | `offersign` | `id`, `jobsubmission_id` | `user_id`, `signDate`, `revenue`, `offerStatus`, `annualSalary`, `active`, `onboardDate` | Offer process detail and historical offer checks | Canceled, void, or inactive Offer facts must not be treated as valid reserve. |
| Invoice Master | `invoice` | `id`, `joborder_id`, `jobsubmission_id`, `client_id` | `invoiceAmount`, `paymentReceived`, `status`, `dateAdded`, `sentDate`, `paymentReceivedDate`, `estimatepaymentReceivedDate`, `payment_days`, `active` | Offer/Invoice/Collection stage facts, receivables, cashflow | Business stage alignment relies heavily on Invoice status. |
| Invoice Performance Allocation | `invoiceassignment` | `id`, `invoice_id`, `user_id` | `revenue`, `assignment_role` | Consultant performance split, collaboration split, consultant collection contribution | Consultant amount must prefer assignment revenue. |
| Forecast Master | `forecast` | `id`, `job_order_id` | `forecast_fee`, `forecast_fee_after_tax`, `close_date`, `last_stage`, `addedBy_id`, `lastUpdateBy_id` | Pipeline and weighted forecast | Active pipeline remains relevant when expected close dates are overdue. |
| Forecast Allocation | `forecastassignment` | `id`, `forecast_id`, `user_id` | `ratio`, `amount_after_tax`, `amount_before_tax` | Consultant forecast split | Use assignment-level amounts for consultant forecast. |
| Onboard Record | `onboard` | `id`, `jobsubmission_id` | `user_id`, `onboardDate`, `active` | Onboard verification | The tool also reads onboard facts from `jobsubmission`. |

## 2. Core Relationship Map

```text
client
  -> joborder
      -> jobsubmission
          -> cvsent
          -> clientinterview
          -> offersign
          -> invoice
              -> invoiceassignment
```

Forecast follows the project pipeline branch:

```text
joborder
  -> forecast
      -> forecastassignment
```

The main key paths currently used by the tool are:

| Relationship | Key Path |
|---|---|
| Consultant to team | `user.team_id = team.id` |
| Project to client | `joborder.client_id = client.id` |
| Contract to client | `clientcontract.client_id = client.id` |
| Referral to process | `cvsent.jobsubmission_id = jobsubmission.id` |
| Interview to process | `clientinterview.jobsubmission_id = jobsubmission.id` |
| Offer to process | `offersign.jobsubmission_id = jobsubmission.id` |
| Process to project | `jobsubmission.joborder_id = joborder.id` |
| Invoice to allocation | `invoiceassignment.invoice_id = invoice.id` |
| Forecast to project | `forecast.job_order_id = joborder.id` |
| Forecast to allocation | `forecastassignment.forecast_id = forecast.id` |

## 3. Aligned Stage Logic

| Tool Stage | Main Source | Key Fields | Current Aligned Meaning |
|---|---|---|---|
| New Project | `joborder` | `id`, `dateAdded`, `jobStatus` | New joborder/project created in the selected period. |
| Referral | `cvsent` | `id`, `dateAdded`, `jobsubmission_id`, `user_id` | Consultant referral behavior. |
| Interview | `clientinterview` | `id`, `date`, `jobsubmission_id` | Client interview progress after referral. |
| Offer | `invoice` plus Offer checks | `status = 'Invoice Added'`; validated `offersign` detail where needed | Current management performance Offer stage aligned to Invoice status to reduce void and duplicate Offer distortion. |
| Invoice | `invoice` | `status = 'Sent'`, `sentDate`, `invoiceAmount` | Invoiced / sent bill stage. |
| Collection | `invoice`, `invoiceassignment` | `status = 'Received'`, `paymentReceivedDate`, `paymentReceived`, `invoiceassignment.revenue` | Company cash collection plus consultant performance attribution. |
| Forecast | `forecast`, `forecastassignment` | `last_stage`, `close_date`, `forecast_fee`, `amount_after_tax` | Active pipeline forecast and consultant split. |

## 4. Metric Field Map

| Analysis Metric | Source Fields | Aligned Rule |
|---|---|---|
| Consultant display name | `user.englishName`, `user.chineseName` | Concatenate and trim names. |
| Team | `team.name` | Join from consultant user team. |
| Client name | `client.name` | Shared client dimension. |
| Position name | `joborder.jobTitle` | Position/project dimension. |
| New project count | `joborder.id`, `joborder.dateAdded` | Deduplicate joborder in assessment period. |
| Referral count | `cvsent.id` | Count valid referral rows. |
| Referred project count | `cvsent.joborder_id` | Distinct joborder count. |
| Average referrals | referral count / referred project count | Calculate inside the selected assessment period. |
| Interview count | `clientinterview.id` | Join through process linkage. |
| Referral-to-interview ratio | referral and interview facts | Numerator and denominator must use aligned owner and period scope. |
| Consultant Offer / reserve amount | `invoiceassignment.revenue` with aligned Invoice stage | Prefer assignment revenue for consultant split. |
| Company Invoice amount | `invoice.invoiceAmount` | Source-document invoice amount. |
| Company Collection amount | `invoice.paymentReceived` | Actual received payment. |
| Consultant Collection amount | `invoiceassignment.revenue` on received invoice | Consultant performance split. |
| Contract payment terms | `clientcontract.payment_terms` | Contract term source. |
| Invoice payment days | `invoice.payment_days` | Invoice due-date source when available. |
| Estimated payment date | `invoice.estimatepaymentReceivedDate` | Preferred explicit expected payment date source. |
| Actual payment date | `invoice.paymentReceivedDate` | Real collection timing. |
| Company Forecast amount | `forecast.forecast_fee` | Pipeline amount. |
| Consultant Forecast amount | `forecastassignment.amount_after_tax` or assignment fallback | Assignment-level consultant share. |

## 5. Cashflow Due Date Priority

For unpaid invoices, the v2 tool builds due dates in this order:

1. `invoice.estimatepaymentReceivedDate`
2. `invoice.sentDate + invoice.payment_days`
3. `invoice.sentDate + clientcontract.payment_terms`
4. `invoice.dateAdded + 35 days` for `Invoice Added` fallback
5. Missing due date if no source can explain it

Keep `due_date_source` visible whenever cashflow risk or overdue aging is reviewed.

## 6. Confirmed Accounting and Analysis Rules

| Rule | Aligned Interpretation |
|---|---|
| Offer, Invoice, and Collection are moving stages | Offer may move into Invoice, and Invoice may move into Collection. Stage balances change dynamically. |
| Do not double count one business value as one KPI across all stages | Distinguish stage additions, ending reserves, unpaid receivables, and actual collection. |
| Consultant collaboration must be split | Use `invoiceassignment.revenue` where performance is allocated across consultants. |
| Prior-year carryover can affect current-year analysis | Historical unpaid Offer, unpaid Invoice, and current-period collections from legacy invoices can matter for current cash and consultant performance. |
| Canceled or void items are not valid reserve | Exclude inactive, rejected, canceled, or void records according to source status and active flags. |
| Active Forecast is management evidence | A live Forecast with an overdue expected date should be flagged as overdue, not silently removed. |
| Contract term and real payment term are different | Contract `payment_terms` is planned term; real payment behavior comes from invoice and collection dates. |
| Consultant maturity affects review | Consultants with less than roughly six months of tenure should be reviewed more on pipeline, Forecast, referrals, interviews, and process indicators before result metrics dominate. |

## 7. Validation Checklist for Metric Disputes

When a tool number differs from a Gllue export or screenshot:

1. Confirm the selected period.
2. Confirm whether the metric is stage addition, ending reserve, unpaid receivable, or actual collection.
3. Check whether prior-year carryover is included.
4. Check canceled, void, rejected, or inactive facts.
5. Check consultant collaboration split.
6. Check whether company amount and consultant assignment amount are being compared incorrectly.
7. Check join grain by source entity ID before changing formulas.

## 8. Code References

The current aligned SQL and normalization logic live in:

- `modules/v2_data_service.py`
- `modules/data_audit.py`
- `gllue_db_client.py`
