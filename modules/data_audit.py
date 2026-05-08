"""
Data support audit for the three-speed v2 model.

The audit answers one question before product rebuild work starts:
can the current data support Referral Efficiency, Cost Efficiency,
Cash Flow Pressure, and Pipeline Health with enough confidence?
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional

import pandas as pd


CONFIDENCE_HIGH = "High"
CONFIDENCE_MEDIUM = "Medium"
CONFIDENCE_LOW = "Low"
CONFIDENCE_BLOCKED = "Blocked"


@dataclass
class AuditConfig:
    start_date: str
    end_date: str
    min_high: float = 0.90
    min_medium: float = 0.60

    @classmethod
    def default(cls) -> "AuditConfig":
        end = datetime.now().date()
        start = end - timedelta(days=365)
        return cls(start_date=start.isoformat(), end_date=end.isoformat())


def pct(numerator: float, denominator: float) -> float:
    if denominator in (0, None) or pd.isna(denominator):
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def pct_display(value: float) -> str:
    return f"{value * 100:.1f}%"


def confidence_from_rate(rate: float, config: AuditConfig) -> str:
    if rate >= config.min_high:
        return CONFIDENCE_HIGH
    if rate >= config.min_medium:
        return CONFIDENCE_MEDIUM
    if rate > 0:
        return CONFIDENCE_LOW
    return CONFIDENCE_BLOCKED


def readiness_from_confidence(confidence: str) -> str:
    if confidence in (CONFIDENCE_HIGH, CONFIDENCE_MEDIUM):
        return "Go"
    if confidence == CONFIDENCE_LOW:
        return "Hold - resolve gaps first"
    return "Blocked"


class DataSupportAuditor:
    """Runs read-only DB audits and produces readiness reports."""

    def __init__(self, db_client, config: Optional[AuditConfig] = None):
        self.db_client = db_client
        self.config = config or AuditConfig.default()
        self.tables: Dict[str, pd.DataFrame] = {}

    def run(self) -> Dict[str, pd.DataFrame]:
        self.load_tables()
        return {
            "table_coverage": self.table_coverage_report(),
            "relationship": self.relationship_report(),
            "cashflow_due_source": self.cashflow_due_source_report(),
            "invoice_status_due_source": self.invoice_status_due_source_report(),
            "metric_readiness": self.metric_readiness_report(),
            "gap_resolution": self.gap_resolution_plan(),
        }

    def load_tables(self) -> None:
        start = self.config.start_date
        end = self.config.end_date

        queries = {
            "users": f"""
                SELECT id, englishName, chineseName, team_id, status, joinInDate, leaveDate
                FROM user
                WHERE status = 'Active'
                   OR joinInDate <= '{end}'
                   OR leaveDate >= '{start}'
            """,
            "teams": "SELECT id, name, parent_id FROM team",
            "joborders": f"""
                SELECT id, client_id, addedBy_id, jobTitle, jobStatus, dateAdded,
                       is_deleted, totalCount, revenue
                FROM joborder
                WHERE dateAdded >= '{start}' AND dateAdded <= '{end}'
            """,
            "cvsents": f"""
                SELECT id, jobsubmission_id, user_id, client_id, joborder_id,
                       dateAdded, date, status, active
                FROM cvsent
                WHERE dateAdded >= '{start}' AND dateAdded <= '{end}' AND active = 1
            """,
            "interviews": f"""
                SELECT ci.id, ci.jobsubmission_id, ci.round, ci.status, ci.date, ci.active,
                       js.user_id, js.joborder_id
                FROM clientinterview ci
                LEFT JOIN jobsubmission js ON ci.jobsubmission_id = js.id
                WHERE ci.date >= '{start}' AND ci.date <= '{end}' AND ci.active = 1
            """,
            "offers": f"""
                SELECT os.id, os.jobsubmission_id, os.user_id, os.signDate,
                       os.revenue, os.annualSalary, os.offerStatus, os.active,
                       js.joborder_id
                FROM offersign os
                LEFT JOIN jobsubmission js ON os.jobsubmission_id = js.id
                WHERE os.signDate >= '{start}' AND os.signDate <= '{end}' AND os.active = 1
            """,
            "onboards_submission": f"""
                SELECT id, user_id, joborder_id, onboardDate, active
                FROM jobsubmission
                WHERE onboardDate >= '{start}' AND onboardDate <= '{end}' AND active = 1
            """,
            "onboards": f"""
                SELECT o.id, o.jobsubmission_id, o.user_id, o.onboardDate, o.active,
                       js.joborder_id
                FROM onboard o
                LEFT JOIN jobsubmission js ON o.jobsubmission_id = js.id
                WHERE o.onboardDate >= '{start}' AND o.onboardDate <= '{end}' AND o.active = 1
            """,
            "invoices": f"""
                SELECT id, joborder_id, client_id, user_id, invoiceAmount, paymentReceived,
                       status, sentDate, dateAdded, estimatepaymentReceivedDate,
                       paymentReceivedDate, payment_days
                FROM invoice
                WHERE dateAdded >= '{start}' OR paymentReceivedDate >= '{start}'
            """,
            "invoice_assignments": f"""
                SELECT ia.id, ia.invoice_id, ia.user_id, ia.revenue, ia.assignment_role,
                       i.joborder_id, i.status, i.paymentReceivedDate
                FROM invoiceassignment ia
                LEFT JOIN invoice i ON ia.invoice_id = i.id
                WHERE i.dateAdded >= '{start}' OR i.paymentReceivedDate >= '{start}'
            """,
            "forecasts": f"""
                SELECT fa.id AS assignment_id, fa.forecast_id, fa.user_id,
                       fa.ratio, fa.amount_after_tax, fa.amount_before_tax,
                       f.job_order_id, f.forecast_fee, f.forecast_fee_after_tax,
                       f.close_date, f.last_stage, jo.jobStatus
                FROM forecastassignment fa
                LEFT JOIN forecast f ON fa.forecast_id = f.id
                LEFT JOIN joborder jo ON f.job_order_id = jo.id
                WHERE f.close_date >= '{start}'
                  AND f.close_date <= DATE_ADD('{end}', INTERVAL 180 DAY)
            """,
            "client_contracts": """
                SELECT id, client_id, startDate, expireDate, payment_terms, is_deleted, invalid
                FROM clientcontract
                WHERE is_deleted = 0 OR is_deleted IS NULL
            """,
        }

        for name, sql in queries.items():
            self.tables[name] = self._safe_query(name, sql)

    def _safe_query(self, name: str, sql: str) -> pd.DataFrame:
        try:
            return self.db_client.query(sql)
        except Exception as exc:
            return pd.DataFrame({"_audit_error": [f"{name}: {exc}"]})

    def table_coverage_report(self) -> pd.DataFrame:
        checks = {
            "users": ["id", "englishName", "chineseName", "team_id", "status", "joinInDate", "leaveDate"],
            "joborders": ["id", "client_id", "addedBy_id", "jobTitle", "jobStatus", "dateAdded"],
            "cvsents": ["id", "jobsubmission_id", "user_id", "client_id", "joborder_id", "dateAdded"],
            "interviews": ["id", "jobsubmission_id", "round", "date", "user_id", "joborder_id"],
            "offers": ["id", "jobsubmission_id", "user_id", "signDate", "revenue", "joborder_id"],
            "onboards_submission": ["id", "user_id", "joborder_id", "onboardDate"],
            "onboards": ["id", "jobsubmission_id", "user_id", "joborder_id", "onboardDate"],
            "invoices": [
                "id",
                "joborder_id",
                "client_id",
                "invoiceAmount",
                "paymentReceived",
                "status",
                "sentDate",
                "estimatepaymentReceivedDate",
                "paymentReceivedDate",
                "payment_days",
            ],
            "invoice_assignments": ["id", "invoice_id", "user_id", "revenue", "joborder_id", "paymentReceivedDate"],
            "forecasts": [
                "assignment_id",
                "forecast_id",
                "user_id",
                "job_order_id",
                "forecast_fee",
                "close_date",
                "last_stage",
                "jobStatus",
            ],
            "client_contracts": ["id", "client_id", "startDate", "expireDate", "payment_terms"],
        }

        rows = []
        for table_name, fields in checks.items():
            df = self.tables.get(table_name, pd.DataFrame())
            if self._has_query_error(df):
                rows.append(
                    {
                        "table": table_name,
                        "rows": 0,
                        "field": "*query*",
                        "coverage": 0.0,
                        "missing": None,
                        "confidence": CONFIDENCE_BLOCKED,
                        "note": df["_audit_error"].iloc[0],
                    }
                )
                continue

            total = len(df)
            for field in fields:
                if field not in df.columns:
                    coverage = 0.0
                    missing = total
                    note = "field not returned"
                elif total == 0:
                    coverage = 0.0
                    missing = 0
                    note = "no rows"
                else:
                    non_null = int(df[field].notna().sum())
                    coverage = pct(non_null, total)
                    missing = int(total - non_null)
                    note = ""

                rows.append(
                    {
                        "table": table_name,
                        "rows": total,
                        "field": field,
                        "coverage": coverage,
                        "missing": missing,
                        "confidence": confidence_from_rate(coverage, self.config),
                        "note": note,
                    }
                )

        return pd.DataFrame(rows)

    def relationship_report(self) -> pd.DataFrame:
        rows = []

        cvs = self._valid("cvsents")
        interviews = self._valid("interviews")
        offers = self._valid("offers")
        onboards = self._valid("onboards_submission")
        invoices = self._valid("invoices")
        invoice_assignments = self._valid("invoice_assignments")
        forecasts = self._valid("forecasts")
        users = self._valid("users")
        joborders = self._valid("joborders")
        contracts = self._valid("client_contracts")

        rows.append(self._relationship("cvsent -> jobsubmission", cvs, "jobsubmission_id"))
        rows.append(self._relationship("cvsent -> joborder", cvs, "joborder_id"))
        rows.append(self._relationship("interview -> jobsubmission", interviews, "jobsubmission_id"))
        rows.append(self._relationship("interview -> joborder", interviews, "joborder_id"))
        rows.append(self._relationship("offer -> jobsubmission", offers, "jobsubmission_id"))
        rows.append(self._relationship("offer -> joborder", offers, "joborder_id"))
        rows.append(self._relationship("onboard -> joborder", onboards, "joborder_id"))
        rows.append(self._relationship("invoice -> joborder", invoices, "joborder_id"))
        rows.append(self._relationship("invoice assignment -> invoice", invoice_assignments, "invoice_id"))
        rows.append(self._relationship("forecast -> joborder", forecasts, "job_order_id"))

        rows.append(self._join_relationship("cvsent user exists", cvs, "user_id", users, "id"))
        rows.append(self._join_relationship("offer user exists", offers, "user_id", users, "id"))
        rows.append(self._join_relationship("invoice assignment user exists", invoice_assignments, "user_id", users, "id"))
        rows.append(self._join_relationship("joborder client exists", joborders, "client_id", contracts, "client_id"))

        return pd.DataFrame(rows)

    def metric_readiness_report(self) -> pd.DataFrame:
        table = self.table_coverage_report()
        rel = self.relationship_report()
        cash_due = self.cashflow_due_source_report()
        cash_due_rate = 0.0
        if not cash_due.empty:
            overall_due = cash_due[cash_due["source"] == "explainable_due_date"]
            if not overall_due.empty:
                cash_due_rate = float(overall_due.iloc[0]["coverage"])

        rows = [
            self._metric_readiness(
                "Project Referral Efficiency",
                [
                    self._field_rate(table, "cvsents", "jobsubmission_id"),
                    self._field_rate(table, "interviews", "jobsubmission_id"),
                    self._field_rate(table, "offers", "jobsubmission_id"),
                    self._field_rate(table, "onboards_submission", "onboardDate"),
                    self._relationship_rate(rel, "invoice -> joborder"),
                ],
                "Requires stable cvsent/interview/offer/onboard/payment linkage.",
            ),
            self._metric_readiness(
                "Pipeline Health",
                [
                    self._field_rate(table, "forecasts", "close_date"),
                    self._field_rate(table, "forecasts", "last_stage"),
                    self._field_rate(table, "forecasts", "forecast_fee"),
                    self._relationship_rate(rel, "forecast -> joborder"),
                ],
                "Requires active forecast rows with close date, stage, and amount.",
            ),
            self._metric_readiness(
                "Consultant Cost Efficiency",
                [
                    self._field_rate(table, "users", "id"),
                    self._field_rate(table, "users", "status"),
                    self._relationship_rate(rel, "invoice assignment user exists"),
                    self._field_rate(table, "joborders", "addedBy_id"),
                ],
                "Revenue and activity are auditable; salary/attendance need separate cost source validation.",
            ),
            self._metric_readiness(
                "Cash Flow Pressure",
                [
                    self._field_rate(table, "invoices", "invoiceAmount"),
                    self._field_rate(table, "invoices", "status"),
                    self._field_rate(table, "invoices", "sentDate"),
                    cash_due_rate,
                    self._relationship_rate(rel, "invoice -> joborder"),
                ],
                "Requires explainable due date source: estimate date, contract terms, historical average, or default.",
            ),
        ]
        return pd.DataFrame(rows)

    def cashflow_due_source_report(self) -> pd.DataFrame:
        """Audit whether unpaid invoices have an explainable due date source."""
        unpaid, source_masks, explainable = self._build_cashflow_due_source_masks()
        if unpaid.empty:
            return pd.DataFrame(
                [
                    {
                        "source": "explainable_due_date",
                        "rows": 0,
                        "covered_rows": 0,
                        "coverage": 0.0,
                        "confidence": CONFIDENCE_BLOCKED,
                        "note": "no invoice rows",
                    }
                ]
            )

        rows = []
        total = len(unpaid)
        rows.append(
            {
                "source": "explainable_due_date",
                "rows": total,
                "covered_rows": int(explainable.sum()),
                "coverage": pct(int(explainable.sum()), total),
                "confidence": confidence_from_rate(pct(int(explainable.sum()), total), self.config),
                "note": "unpaid invoices with estimate date, sent date + terms, or invoice-added fallback",
            }
        )
        for source, mask in source_masks.items():
            coverage = pct(int(mask.sum()), total)
            rows.append(
                {
                    "source": source,
                    "rows": total,
                    "covered_rows": int(mask.sum()),
                    "coverage": coverage,
                    "confidence": confidence_from_rate(coverage, self.config),
                    "note": "",
                }
            )
        return pd.DataFrame(rows)

    def invoice_status_due_source_report(self) -> pd.DataFrame:
        """Break down due-date coverage by invoice status."""
        unpaid, _source_masks, explainable = self._build_cashflow_due_source_masks()
        if unpaid.empty or "status" not in unpaid.columns:
            return pd.DataFrame()

        rows = []
        work = unpaid.copy()
        work["_explainable_due_date"] = explainable
        for status, part in work.groupby(work["status"].fillna("(missing)").astype(str)):
            total = len(part)
            covered = int(part["_explainable_due_date"].sum())
            coverage = pct(covered, total)
            rows.append(
                {
                    "status": status,
                    "rows": total,
                    "covered_rows": covered,
                    "coverage": coverage,
                    "confidence": confidence_from_rate(coverage, self.config),
                }
            )
        return pd.DataFrame(rows).sort_values(["coverage", "rows"], ascending=[True, False])

    def _build_cashflow_due_source_masks(self):
        invoices = self._valid("invoices")
        contracts = self._valid("client_contracts")
        if invoices.empty:
            empty = pd.DataFrame()
            return empty, {}, pd.Series(dtype=bool)

        df = invoices.copy()
        status = df["status"].fillna("").astype(str) if "status" in df.columns else pd.Series("", index=df.index)
        if "paymentReceived" in df.columns and "invoiceAmount" in df.columns:
            received = pd.to_numeric(df["paymentReceived"], errors="coerce").fillna(0)
            amount = pd.to_numeric(df["invoiceAmount"], errors="coerce").fillna(0)
            collectible_status = status.isin(["Sent", "Invoice Added"])
            partial_received = status.eq("Received") & (received < amount)
            unpaid = df[collectible_status | partial_received]
        else:
            unpaid = df[status.isin(["Sent", "Invoice Added"])]
        if unpaid.empty:
            unpaid = df

        contract_clients = set()
        if not contracts.empty and "client_id" in contracts.columns and "payment_terms" in contracts.columns:
            contract_clients = set(
                contracts[contracts["payment_terms"].notna()]["client_id"].dropna().astype(str)
            )

        has_estimate = self._series_notna(unpaid, "estimatepaymentReceivedDate")
        has_sent = self._series_notna(unpaid, "sentDate")
        has_date_added = self._series_notna(unpaid, "dateAdded")
        has_payment_days = self._series_notna(unpaid, "payment_days")
        has_contract_terms = (
            unpaid["client_id"].astype(str).isin(contract_clients)
            if "client_id" in unpaid.columns
            else pd.Series(False, index=unpaid.index)
        )
        status = unpaid["status"].fillna("").astype(str) if "status" in unpaid.columns else pd.Series("", index=unpaid.index)

        source_masks = {
            "estimatepaymentReceivedDate": has_estimate,
            "sentDate_plus_payment_days": has_sent & has_payment_days,
            "sentDate_plus_clientcontract": has_sent & has_contract_terms,
            "invoice_added_plus_35_days": status.eq("Invoice Added") & has_date_added,
        }
        explainable = pd.Series(False, index=unpaid.index)
        for mask in source_masks.values():
            explainable = explainable | mask
        return unpaid, source_masks, explainable

    def gap_resolution_plan(self) -> pd.DataFrame:
        readiness = self.metric_readiness_report()
        rows = []
        for _, row in readiness.iterrows():
            metric = row["metric"]
            confidence = row["confidence"]
            if confidence in (CONFIDENCE_HIGH, CONFIDENCE_MEDIUM):
                rows.append(
                    {
                        "metric": metric,
                        "priority": "P2",
                        "gap": "No blocking data gap found by the first audit.",
                        "resolution": "Proceed with module design; keep confidence labels visible.",
                        "blocks_development": "No",
                    }
                )
                continue

            if metric == "Consultant Cost Efficiency":
                rows.append(
                    {
                        "metric": metric,
                        "priority": "P0",
                        "gap": "Salary or attendance data is not guaranteed in current DB extracts.",
                        "resolution": "Use real finance salary upload first, consultant config second, default salary x 3.0 last.",
                        "blocks_development": "Blocks true-cost claims; allows assumed-cost prototype.",
                    }
                )
            elif metric == "Cash Flow Pressure":
                rows.append(
                    {
                        "metric": metric,
                        "priority": "P0",
                        "gap": "Invoice due date source coverage is insufficient.",
                        "resolution": "Validate estimatepaymentReceivedDate, payment_days, and clientcontract payment_terms; add due_date_source fallback.",
                        "blocks_development": "Yes for scoring, no for raw overdue list.",
                    }
                )
            else:
                rows.append(
                    {
                        "metric": metric,
                        "priority": "P0",
                        "gap": "Required process linkage coverage is below threshold.",
                        "resolution": "Fix SQL mapping or choose canonical process key before building charts.",
                        "blocks_development": "Yes",
                    }
                )
        return pd.DataFrame(rows)

    def _metric_readiness(self, metric: str, rates: Iterable[float], note: str) -> Dict[str, object]:
        rates_list = list(rates)
        score = min(rates_list) if rates_list else 0.0
        confidence = confidence_from_rate(score, self.config)
        return {
            "metric": metric,
            "support_score": score,
            "support_score_display": pct_display(score),
            "confidence": confidence,
            "decision": readiness_from_confidence(confidence),
            "note": note,
        }

    def _relationship(self, name: str, df: pd.DataFrame, field: str) -> Dict[str, object]:
        if df.empty:
            rate = 0.0
            total = 0
            linked = 0
        elif field not in df.columns:
            rate = 0.0
            total = len(df)
            linked = 0
        else:
            total = len(df)
            linked = int(df[field].notna().sum())
            rate = pct(linked, total)
        return {
            "relationship": name,
            "rows": total,
            "linked_rows": linked,
            "link_rate": rate,
            "confidence": confidence_from_rate(rate, self.config),
        }

    def _join_relationship(
        self,
        name: str,
        left: pd.DataFrame,
        left_key: str,
        right: pd.DataFrame,
        right_key: str,
    ) -> Dict[str, object]:
        if left.empty or right.empty or left_key not in left.columns or right_key not in right.columns:
            return {
                "relationship": name,
                "rows": len(left),
                "linked_rows": 0,
                "link_rate": 0.0,
                "confidence": CONFIDENCE_BLOCKED,
            }

        left_values = left[left_key].dropna()
        right_values = set(right[right_key].dropna().astype(str))
        if left_values.empty:
            linked = 0
            total = len(left)
        else:
            linked = int(left_values.astype(str).isin(right_values).sum())
            total = len(left)
        rate = pct(linked, total)
        return {
            "relationship": name,
            "rows": total,
            "linked_rows": linked,
            "link_rate": rate,
            "confidence": confidence_from_rate(rate, self.config),
        }

    def _field_rate(self, table: pd.DataFrame, table_name: str, field: str) -> float:
        rows = table[(table["table"] == table_name) & (table["field"] == field)]
        if rows.empty:
            return 0.0
        return float(rows.iloc[0]["coverage"])

    def _relationship_rate(self, rel: pd.DataFrame, relationship: str) -> float:
        rows = rel[rel["relationship"] == relationship]
        if rows.empty:
            return 0.0
        return float(rows.iloc[0]["link_rate"])

    def _valid(self, table_name: str) -> pd.DataFrame:
        df = self.tables.get(table_name, pd.DataFrame())
        if self._has_query_error(df):
            return pd.DataFrame()
        return df

    @staticmethod
    def _series_notna(df: pd.DataFrame, column: str) -> pd.Series:
        if column not in df.columns:
            return pd.Series(False, index=df.index)
        return df[column].notna()

    @staticmethod
    def _has_query_error(df: pd.DataFrame) -> bool:
        return "_audit_error" in df.columns


def render_markdown_report(reports: Dict[str, pd.DataFrame], config: AuditConfig) -> str:
    lines: List[str] = [
        "# Data Support Audit Report",
        "",
        f"Audit window: {config.start_date} to {config.end_date}",
        "",
        "## Metric Readiness",
        "",
    ]
    readiness = reports.get("metric_readiness", pd.DataFrame())
    if not readiness.empty:
        for _, row in readiness.iterrows():
            lines.extend(
                [
                    f"### {row['metric']}",
                    f"- Support score: {row['support_score_display']}",
                    f"- Confidence: {row['confidence']}",
                    f"- Decision: {row['decision']}",
                    f"- Note: {row['note']}",
                    "",
                ]
            )

    lines.extend(["## Gap Resolution Plan", ""])
    gaps = reports.get("gap_resolution", pd.DataFrame())
    if not gaps.empty:
        for _, row in gaps.iterrows():
            lines.extend(
                [
                    f"### {row['metric']}",
                    f"- Priority: {row['priority']}",
                    f"- Gap: {row['gap']}",
                    f"- Resolution: {row['resolution']}",
                    f"- Blocks development: {row['blocks_development']}",
                    "",
                ]
            )

    lines.extend(
        [
            "## Relationship Coverage",
            "",
            "| Relationship | Rows | Linked Rows | Link Rate | Confidence |",
            "|---|---:|---:|---:|---|",
        ]
    )
    rel = reports.get("relationship", pd.DataFrame())
    if not rel.empty:
        for _, row in rel.iterrows():
            lines.append(
                f"| {row['relationship']} | {row['rows']} | {row['linked_rows']} | "
                f"{pct_display(row['link_rate'])} | {row['confidence']} |"
            )

    lines.extend(
        [
            "",
            "## Cash Flow Due Date Sources",
            "",
            "| Source | Rows | Covered Rows | Coverage | Confidence | Note |",
            "|---|---:|---:|---:|---|---|",
        ]
    )
    cash_due = reports.get("cashflow_due_source", pd.DataFrame())
    if not cash_due.empty:
        for _, row in cash_due.iterrows():
            lines.append(
                f"| {row['source']} | {row['rows']} | {row['covered_rows']} | "
                f"{pct_display(row['coverage'])} | {row['confidence']} | {row['note']} |"
            )

    lines.extend(
        [
            "",
            "## Invoice Status Due Date Coverage",
            "",
            "| Status | Rows | Covered Rows | Coverage | Confidence |",
            "|---|---:|---:|---:|---|",
        ]
    )
    status_due = reports.get("invoice_status_due_source", pd.DataFrame())
    if not status_due.empty:
        for _, row in status_due.iterrows():
            lines.append(
                f"| {row['status']} | {row['rows']} | {row['covered_rows']} | "
                f"{pct_display(row['coverage'])} | {row['confidence']} |"
            )

    lines.extend(["", "## Field Coverage", ""])
    coverage = reports.get("table_coverage", pd.DataFrame())
    if not coverage.empty:
        for table_name in coverage["table"].drop_duplicates():
            part = coverage[coverage["table"] == table_name]
            lines.extend(
                [
                    f"### {table_name}",
                    "| Field | Rows | Coverage | Missing | Confidence | Note |",
                    "|---|---:|---:|---:|---|---|",
                ]
            )
            for _, row in part.iterrows():
                missing = "" if pd.isna(row["missing"]) else int(row["missing"])
                lines.append(
                    f"| {row['field']} | {row['rows']} | {pct_display(row['coverage'])} | "
                    f"{missing} | {row['confidence']} | {row['note']} |"
                )
            lines.append("")

    return "\n".join(lines)
