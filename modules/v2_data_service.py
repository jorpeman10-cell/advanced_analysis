"""Standard data builders for the three-speed v2 model."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Optional
from zoneinfo import ZoneInfo

import pandas as pd

OFFER_TO_ONBOARD_GRACE_DAYS = 90
PROJECT_TO_OFFER_GRACE_DAYS = 45


def _name_expr(alias: str = "u") -> str:
    return f"TRIM(CONCAT(IFNULL({alias}.englishName, ''), ' ', IFNULL({alias}.chineseName, '')))"


def _to_datetime(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce")


class V2DataService:
    """Loads raw Gllue data and returns normalized DataFrames for v2 analyzers."""

    def __init__(self, db_client):
        self.db_client = db_client

    @staticmethod
    def default_window(days: int = 365) -> Dict[str, str]:
        end = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        start = end - timedelta(days=days)
        return {"start_date": start.isoformat(), "end_date": end.isoformat()}

    def load_process_data(self, start_date: str, end_date: str) -> pd.DataFrame:
        """Build one process row per referred jobsubmission."""
        cvs = self.db_client.query(f"""
            SELECT cs.id AS cvsent_id, cs.jobsubmission_id, cs.user_id,
                   {_name_expr('u')} AS consultant,
                   cs.client_id, cs.joborder_id, cs.dateAdded AS resume_sent_date,
                   jo.jobTitle AS position_name, jo.jobStatus AS job_status,
                   jo.openDate AS job_open_date, jo.closeDate AS job_close_date,
                   jo.jobStatusUpdateDate AS job_status_update_date,
                   jo.close_reason, jo.close_note, jo.function_normal,
                   c.name AS client_name,
                   t.name AS team
            FROM cvsent cs
            LEFT JOIN user u ON cs.user_id = u.id
            LEFT JOIN team t ON u.team_id = t.id
            LEFT JOIN joborder jo ON cs.joborder_id = jo.id
            LEFT JOIN client c ON cs.client_id = c.id
            WHERE cs.dateAdded >= '{start_date}' AND cs.dateAdded <= '{end_date}'
              AND cs.active = 1
        """)
        if cvs.empty:
            return pd.DataFrame()

        interviews = self.db_client.query(f"""
            SELECT ci.jobsubmission_id, MIN(ci.date) AS first_interview_date
            FROM clientinterview ci
            WHERE ci.date >= '{start_date}' AND ci.date <= '{end_date}'
              AND ci.active = 1
            GROUP BY ci.jobsubmission_id
        """)
        offers = self.db_client.query(f"""
            SELECT os.jobsubmission_id, js.joborder_id,
                   MIN(os.signDate) AS offer_date,
                   MIN(COALESCE(os.onboardDate, js.estimate_onboardDate)) AS expected_onboard_date,
                   SUM(os.revenue) AS fee_amount
            FROM offersign os
            LEFT JOIN jobsubmission js ON os.jobsubmission_id = js.id
            WHERE os.signDate >= '{start_date}' AND os.signDate <= '{end_date}'
              AND os.active = 1
            GROUP BY os.jobsubmission_id, js.joborder_id
        """)
        onboards = self.db_client.query("""
            SELECT js.id AS jobsubmission_id, MIN(js.onboardDate) AS onboard_date
            FROM jobsubmission js
            WHERE js.onboardDate IS NOT NULL
              AND js.active = 1
            GROUP BY js.id
        """)
        invoices = self.db_client.query(f"""
            SELECT i.joborder_id,
                   SUM(COALESCE(i.paymentReceived, 0)) AS actual_payment,
                   MAX(i.paymentReceivedDate) AS actual_payment_date
            FROM invoice i
            WHERE i.joborder_id IS NOT NULL
              AND (i.dateAdded >= '{start_date}' OR i.paymentReceivedDate >= '{start_date}')
            GROUP BY i.joborder_id
        """)

        process = (
            cvs.sort_values("resume_sent_date")
            .drop_duplicates("jobsubmission_id", keep="first")
            .copy()
        )
        for col in ["resume_sent_date"]:
            process[col] = _to_datetime(process[col])

        if not interviews.empty:
            process = process.merge(interviews, on="jobsubmission_id", how="left")
        else:
            process["first_interview_date"] = pd.NaT
        if not offers.empty:
            process = process.merge(
                offers[["jobsubmission_id", "offer_date", "expected_onboard_date", "fee_amount"]],
                on="jobsubmission_id",
                how="left",
            )
        else:
            process["offer_date"] = pd.NaT
            process["expected_onboard_date"] = pd.NaT
            process["fee_amount"] = 0.0
        if not onboards.empty:
            process = process.merge(onboards, on="jobsubmission_id", how="left")
        else:
            process["onboard_date"] = pd.NaT
        if not invoices.empty:
            process = process.merge(invoices, on="joborder_id", how="left")
        else:
            process["actual_payment"] = 0.0
            process["actual_payment_date"] = pd.NaT

        for col in ["first_interview_date", "offer_date", "expected_onboard_date", "onboard_date", "actual_payment_date"]:
            process[col] = _to_datetime(process[col])
        process["fee_amount"] = pd.to_numeric(process.get("fee_amount"), errors="coerce").fillna(0)
        process["actual_payment"] = pd.to_numeric(process.get("actual_payment"), errors="coerce").fillna(0)

        analysis_date = pd.to_datetime(end_date).normalize()
        onboard_mature_cutoff = analysis_date - pd.Timedelta(days=OFFER_TO_ONBOARD_GRACE_DAYS)

        process["is_recommended"] = process["resume_sent_date"].notna()
        process["is_first_interview"] = process["first_interview_date"].notna()
        process["is_offer"] = process["offer_date"].notna()
        process["is_onboard"] = process["onboard_date"].notna() & (process["onboard_date"] <= analysis_date)
        process["is_onboard_pending"] = process["onboard_date"].notna() & (process["onboard_date"] > analysis_date)
        has_expected_onboard = process["expected_onboard_date"].notna()
        process["offer_onboard_matured"] = process["is_offer"] & (
            process["is_onboard"]
            | (has_expected_onboard & (process["expected_onboard_date"] <= analysis_date))
            | (~has_expected_onboard & process["onboard_date"].isna() & (process["offer_date"] <= onboard_mature_cutoff))
        )
        process["is_paid"] = (
            process["is_offer"]
            & process["is_onboard"]
            & process["actual_payment_date"].notna()
            & (process["actual_payment"] > 0)
        )
        process["stage_source"] = "jobsubmission_process"
        return process

    def load_forecast_data(self, start_date: str, days: int = 180) -> pd.DataFrame:
        end_date = (pd.to_datetime(start_date) + pd.Timedelta(days=days)).date().isoformat()
        df = self.db_client.query(f"""
            SELECT fa.id AS assignment_id, f.id AS forecast_id, f.job_order_id AS joborder_id,
                   jo.jobTitle AS position_name, c.name AS client_name,
                   fa.user_id, {_name_expr('u')} AS consultant,
                   f.forecast_fee, f.forecast_fee_after_tax,
                   fa.amount_after_tax AS assignment_amount,
                   fa.ratio AS assignment_ratio,
                   f.close_date AS expected_close_date,
                   f.last_stage AS current_stage,
                   jo.jobStatus AS job_status
            FROM forecastassignment fa
            JOIN forecast f ON fa.forecast_id = f.id
            LEFT JOIN joborder jo ON f.job_order_id = jo.id
            LEFT JOIN client c ON jo.client_id = c.id
            LEFT JOIN user u ON fa.user_id = u.id
            WHERE jo.jobStatus = 'Live'
              AND f.close_date IS NOT NULL
        """)
        if df.empty:
            return df
        df["expected_close_date"] = _to_datetime(df["expected_close_date"])
        df["forecast_fee"] = pd.to_numeric(df["forecast_fee"], errors="coerce").fillna(0)
        df["assignment_amount"] = pd.to_numeric(df["assignment_amount"], errors="coerce").fillna(0)
        df["success_rate"] = df["current_stage"].apply(stage_success_rate)
        df["stage_category"] = df["current_stage"].apply(stage_category)
        df["weighted_revenue"] = df["forecast_fee"] * df["success_rate"]
        df["assignment_weighted_revenue"] = df["assignment_amount"] * df["success_rate"]
        analysis_date = pd.to_datetime(start_date).normalize()
        df["raw_days_to_close"] = (df["expected_close_date"].dt.normalize() - analysis_date).dt.days
        df["is_forecast_overdue"] = df["raw_days_to_close"] < 0
        df["days_to_close"] = df["raw_days_to_close"].clip(lower=0)
        df["stage_source"] = df["current_stage"].apply(lambda x: "mapped" if stage_category(x) != "Other" else "unknown")
        return df

    def load_collection_data(self, start_date: str, end_date: str) -> pd.DataFrame:
        df = self.db_client.query(f"""
            SELECT ia.invoice_id, ia.user_id, {_name_expr('u')} AS consultant,
                   ia.revenue AS collection_amount,
                   i.paymentReceivedDate AS payment_received_date,
                   i.joborder_id, c.name AS client_name
            FROM invoiceassignment ia
            JOIN invoice i ON ia.invoice_id = i.id
            LEFT JOIN user u ON ia.user_id = u.id
            LEFT JOIN client c ON i.client_id = c.id
            WHERE i.status = 'Received'
              AND i.paymentReceivedDate >= '{start_date}'
              AND i.paymentReceivedDate <= '{end_date}'
        """)
        if df.empty:
            return df
        df["collection_amount"] = pd.to_numeric(df["collection_amount"], errors="coerce").fillna(0)
        df["payment_received_date"] = _to_datetime(df["payment_received_date"])
        return df

    def load_consultants(self) -> pd.DataFrame:
        df = self.db_client.query(f"""
            SELECT u.id AS consultant_id, {_name_expr('u')} AS consultant,
                   t.name AS team, u.status, u.joinInDate, u.leaveDate
            FROM user u
            LEFT JOIN team t ON u.team_id = t.id
        """)
        if df.empty:
            return df
        df["joinInDate"] = _to_datetime(df["joinInDate"])
        df["leaveDate"] = _to_datetime(df["leaveDate"])
        df["is_active"] = df["status"].eq("Active")
        return df

    def load_cashflow_invoices(self, start_date: str, end_date: str) -> pd.DataFrame:
        end_year = pd.to_datetime(end_date).year
        legacy_start = f"{end_year - 1}-01-01"
        df = self.db_client.query(f"""
            SELECT i.id AS invoice_id, i.joborder_id, i.client_id, c.name AS client_name,
                   i.invoiceAmount AS invoice_amount,
                   COALESCE(i.paymentReceived, 0) AS payment_received,
                   i.status, i.sentDate AS sent_date, i.dateAdded AS date_added,
                   i.estimatepaymentReceivedDate AS estimated_payment_date,
                   i.paymentReceivedDate AS payment_received_date,
                   i.payment_days
            FROM invoice i
            LEFT JOIN client c ON i.client_id = c.id
            WHERE i.dateAdded >= '{legacy_start}'
               OR i.paymentReceivedDate >= '{start_date}'
               OR (
                    (i.status IN ('Sent', 'Invoice Added')
                     OR COALESCE(i.invoiceAmount, 0) > COALESCE(i.paymentReceived, 0))
                    AND COALESCE(i.sentDate, i.dateAdded) >= '{legacy_start}'
               )
        """)
        if df.empty:
            return df
        for col in ["sent_date", "date_added", "estimated_payment_date", "payment_received_date"]:
            df[col] = _to_datetime(df[col])
        for col in ["invoice_amount", "payment_received", "payment_days"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        df["pending_amount"] = (df["invoice_amount"] - df["payment_received"]).clip(lower=0)
        df = self._add_due_date(df)
        return df

    def load_fiscal_ytd_metrics(self, start_date: str, end_date: str, forecast_days: int = 180) -> Dict[str, pd.DataFrame]:
        """Load YTD Offer, Invoice, Collection, and Forecast facts.

        Company facts use source document totals. Consultant facts use assignment
        amounts where the source system splits revenue across consultants.
        """
        forecast_end = (pd.to_datetime(end_date) + pd.Timedelta(days=forecast_days)).date().isoformat()

        company_offer = self.db_client.query(f"""
            SELECT 'Offer' AS metric, COUNT(os.id) AS count_value,
                   SUM(os.revenue) AS amount_value
            FROM offersign os
            WHERE os.signDate >= '{start_date}' AND os.signDate <= '{end_date}'
              AND os.active = 1
        """)
        company_invoice = self.db_client.query(f"""
            SELECT 'Invoice' AS metric, COUNT(i.id) AS count_value,
                   SUM(i.invoiceAmount) AS amount_value
            FROM invoice i
            WHERE i.sentDate >= '{start_date}' AND i.sentDate <= '{end_date}'
        """)
        company_collection = self.db_client.query(f"""
            SELECT 'Collection' AS metric, COUNT(i.id) AS count_value,
                   SUM(i.paymentReceived) AS amount_value
            FROM invoice i
            WHERE i.status = 'Received'
              AND i.paymentReceivedDate >= '{start_date}' AND i.paymentReceivedDate <= '{end_date}'
        """)
        company_forecast = self.db_client.query(f"""
            SELECT 'Forecast' AS metric, COUNT(f.id) AS count_value,
                   SUM(f.forecast_fee) AS amount_value
            FROM forecast f
            LEFT JOIN joborder jo ON f.job_order_id = jo.id
            WHERE jo.jobStatus = 'Live'
              AND f.close_date IS NOT NULL
              AND f.last_stage IS NOT NULL
              AND f.last_stage != ''
        """)
        company = pd.concat([company_offer, company_invoice, company_collection, company_forecast], ignore_index=True)
        company["level"] = "Company"
        company["name"] = "Company"
        company["team"] = "Company"

        consultant_offer = self.db_client.query(f"""
            SELECT 'Offer' AS metric, {_name_expr('u')} AS consultant, t.name AS team,
                   COUNT(os.id) AS count_value, SUM(os.revenue) AS amount_value
            FROM offersign os
            LEFT JOIN user u ON os.user_id = u.id
            LEFT JOIN team t ON u.team_id = t.id
            WHERE os.signDate >= '{start_date}' AND os.signDate <= '{end_date}'
              AND os.active = 1
            GROUP BY os.user_id, consultant, t.name
        """)
        offer_detail = self.db_client.query(f"""
            SELECT os.id AS offer_id, os.jobsubmission_id, js.joborder_id,
                   {_name_expr('u')} AS consultant, t.name AS team,
                   c.name AS client_name, jo.jobTitle AS position_name,
                   os.signDate AS sign_date, os.dateAdded AS date_added,
                   os.offerStatus AS offer_status,
                   os.revenue AS offer_amount,
                   os.hunterFee AS hunter_fee,
                   os.total_billable_compensation,
                   os.annualSalary AS annual_salary,
                   os.active
            FROM offersign os
            LEFT JOIN jobsubmission js ON os.jobsubmission_id = js.id
            LEFT JOIN joborder jo ON js.joborder_id = jo.id
            LEFT JOIN client c ON jo.client_id = c.id
            LEFT JOIN user u ON os.user_id = u.id
            LEFT JOIN team t ON u.team_id = t.id
            WHERE os.signDate >= '{start_date}' AND os.signDate <= '{end_date}'
              AND os.active = 1
            ORDER BY os.signDate, os.id
        """)
        consultant_invoice = self.db_client.query(f"""
            SELECT 'Invoice' AS metric, {_name_expr('u')} AS consultant, t.name AS team,
                   COUNT(DISTINCT ia.invoice_id) AS count_value,
                   SUM(ia.revenue) AS amount_value
            FROM invoiceassignment ia
            JOIN invoice i ON ia.invoice_id = i.id
            LEFT JOIN user u ON ia.user_id = u.id
            LEFT JOIN team t ON u.team_id = t.id
            WHERE i.sentDate >= '{start_date}' AND i.sentDate <= '{end_date}'
            GROUP BY ia.user_id, consultant, t.name
        """)
        consultant_collection = self.db_client.query(f"""
            SELECT 'Collection' AS metric, {_name_expr('u')} AS consultant, t.name AS team,
                   COUNT(DISTINCT ia.invoice_id) AS count_value,
                   SUM(ia.revenue) AS amount_value
            FROM invoiceassignment ia
            JOIN invoice i ON ia.invoice_id = i.id
            LEFT JOIN user u ON ia.user_id = u.id
            LEFT JOIN team t ON u.team_id = t.id
            WHERE i.status = 'Received'
              AND i.paymentReceivedDate >= '{start_date}' AND i.paymentReceivedDate <= '{end_date}'
            GROUP BY ia.user_id, consultant, t.name
        """)
        consultant_forecast = self.db_client.query(f"""
            SELECT 'Forecast' AS metric, {_name_expr('u')} AS consultant, t.name AS team,
                   COUNT(fa.id) AS count_value,
                   SUM(COALESCE(fa.amount_after_tax, fa.amount_before_tax, f.forecast_fee * COALESCE(fa.ratio, 100) / 100)) AS amount_value
            FROM forecastassignment fa
            JOIN forecast f ON fa.forecast_id = f.id
            LEFT JOIN joborder jo ON f.job_order_id = jo.id
            LEFT JOIN user u ON fa.user_id = u.id
            LEFT JOIN team t ON u.team_id = t.id
            WHERE jo.jobStatus = 'Live'
              AND f.close_date IS NOT NULL
              AND f.last_stage IS NOT NULL
              AND f.last_stage != ''
            GROUP BY fa.user_id, consultant, t.name
        """)

        consultant = pd.concat(
            [consultant_offer, consultant_invoice, consultant_collection, consultant_forecast],
            ignore_index=True,
        )
        if not consultant.empty:
            consultant["level"] = "Consultant"
            consultant["name"] = consultant["consultant"]
            consultant["team"] = consultant["team"].fillna("(No Team)")

        for df in [company, consultant]:
            if not df.empty:
                df["count_value"] = pd.to_numeric(df["count_value"], errors="coerce").fillna(0)
                df["amount_value"] = pd.to_numeric(df["amount_value"], errors="coerce").fillna(0)

        team = pd.DataFrame()
        if not consultant.empty:
            team = (
                consultant.groupby(["metric", "team"], dropna=False)
                .agg(count_value=("count_value", "sum"), amount_value=("amount_value", "sum"))
                .reset_index()
            )
            team["level"] = "Team"
            team["name"] = team["team"]

        audit = self._metric_reconciliation(company, consultant)

        if not offer_detail.empty:
            offer_detail["sign_date"] = _to_datetime(offer_detail["sign_date"])
            offer_detail["date_added"] = _to_datetime(offer_detail["date_added"])
            for col in ["offer_amount", "hunter_fee", "total_billable_compensation", "annual_salary"]:
                if col in offer_detail.columns:
                    offer_detail[col] = pd.to_numeric(offer_detail[col], errors="coerce").fillna(0)
            offer_detail["team"] = offer_detail["team"].fillna("(No Team)")
            offer_detail["consultant"] = offer_detail["consultant"].fillna("(No Consultant)")

        return {"company": company, "team": team, "consultant": consultant, "audit": audit, "offer_detail": offer_detail}

    @staticmethod
    def _metric_reconciliation(company: pd.DataFrame, consultant: pd.DataFrame) -> pd.DataFrame:
        metrics = ["Offer", "Invoice", "Collection", "Forecast"]
        rows = []
        for metric in metrics:
            company_row = company[company["metric"] == metric] if isinstance(company, pd.DataFrame) and not company.empty else pd.DataFrame()
            consultant_rows = consultant[consultant["metric"] == metric] if isinstance(consultant, pd.DataFrame) and not consultant.empty else pd.DataFrame()
            company_amount = float(company_row["amount_value"].sum()) if not company_row.empty else 0.0
            consultant_amount = float(consultant_rows["amount_value"].sum()) if not consultant_rows.empty else 0.0
            company_count = int(company_row["count_value"].sum()) if not company_row.empty else 0
            consultant_count = int(consultant_rows["count_value"].sum()) if not consultant_rows.empty else 0
            rows.append(
                {
                    "metric": metric,
                    "company_amount": company_amount,
                    "consultant_amount_sum": consultant_amount,
                    "amount_diff": company_amount - consultant_amount,
                    "company_count": company_count,
                    "consultant_count_sum": consultant_count,
                    "count_diff": company_count - consultant_count,
                    "status": "OK" if abs(company_amount - consultant_amount) < 1 and company_count == consultant_count else "Check",
                }
            )
        return pd.DataFrame(rows)

    def load_offer_outcome_metrics(self, start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
        """Track same-period offers through onboard and payment outcomes."""
        df = self.db_client.query(f"""
            SELECT os.id AS offer_id, os.jobsubmission_id, js.joborder_id,
                   {_name_expr('u')} AS consultant, t.name AS team,
                   os.signDate AS offer_date, os.revenue AS offer_amount,
                   COALESCE(os.onboardDate, js.estimate_onboardDate) AS expected_onboard_date,
                   js.onboardDate AS actual_onboard_date,
                   SUM(COALESCE(i.paymentReceived, 0)) AS paid_amount,
                   MAX(i.paymentReceivedDate) AS paid_date
            FROM offersign os
            LEFT JOIN jobsubmission js ON os.jobsubmission_id = js.id
            LEFT JOIN user u ON os.user_id = u.id
            LEFT JOIN team t ON u.team_id = t.id
            LEFT JOIN invoice i ON i.joborder_id = js.joborder_id
            WHERE os.signDate >= '{start_date}' AND os.signDate <= '{end_date}'
              AND os.active = 1
            GROUP BY os.id, os.jobsubmission_id, js.joborder_id, consultant, t.name,
                     os.signDate, os.revenue, COALESCE(os.onboardDate, js.estimate_onboardDate), js.onboardDate
        """)
        if df.empty:
            empty = pd.DataFrame()
            return {"company": empty, "team": empty, "consultant": empty, "detail": empty}

        df["offer_date"] = _to_datetime(df["offer_date"])
        df["expected_onboard_date"] = _to_datetime(df["expected_onboard_date"])
        df["actual_onboard_date"] = _to_datetime(df["actual_onboard_date"])
        df["paid_date"] = _to_datetime(df["paid_date"])
        df["offer_amount"] = pd.to_numeric(df["offer_amount"], errors="coerce").fillna(0)
        df["paid_amount"] = pd.to_numeric(df["paid_amount"], errors="coerce").fillna(0)
        analysis_date = pd.to_datetime(end_date).normalize()
        onboard_mature_cutoff = analysis_date - pd.Timedelta(days=OFFER_TO_ONBOARD_GRACE_DAYS)
        df["is_onboard"] = df["actual_onboard_date"].notna() & (df["actual_onboard_date"] <= analysis_date)
        df["is_onboard_pending"] = df["expected_onboard_date"].notna() & (df["expected_onboard_date"] > analysis_date)
        has_expected_onboard = df["expected_onboard_date"].notna()
        df["offer_onboard_matured"] = df["is_onboard"] | (
            has_expected_onboard & (df["expected_onboard_date"] <= analysis_date)
        ) | (
            ~has_expected_onboard & df["actual_onboard_date"].isna() & (df["offer_date"] <= onboard_mature_cutoff)
        )
        df["is_paid"] = df["paid_amount"] > 0
        df["team"] = df["team"].fillna("(No Team)")
        df["consultant"] = df["consultant"].fillna("(No Consultant)")

        company = self._offer_outcome_group(df, [])
        company["level"] = "Company"
        company["name"] = "Company"
        team = self._offer_outcome_group(df, ["team"])
        team["level"] = "Team"
        team["name"] = team["team"]
        consultant = self._offer_outcome_group(df, ["consultant"])
        consultant["level"] = "Consultant"
        consultant["name"] = consultant["consultant"]
        return {"company": company, "team": team, "consultant": consultant, "detail": df}

    @staticmethod
    def _offer_outcome_group(df: pd.DataFrame, keys: list) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame()
        if not keys:
            grouped = pd.DataFrame([{
                "offer_count": int(df["offer_id"].nunique()),
                "matured_offer_count": int(df["offer_onboard_matured"].sum()),
                "pending_onboard_count": int((~df["offer_onboard_matured"]).sum()),
                "offer_amount": float(df["offer_amount"].sum()),
                "onboard_count": int(df["is_onboard"].sum()),
                "paid_offer_count": int(df["is_paid"].sum()),
                "paid_amount": float(df["paid_amount"].sum()),
            }])
        else:
            grouped = (
                df.groupby(keys, dropna=False)
                .agg(
                    offer_count=("offer_id", "nunique"),
                    matured_offer_count=("offer_onboard_matured", "sum"),
                    pending_onboard_count=("offer_onboard_matured", lambda x: int((~x).sum())),
                    offer_amount=("offer_amount", "sum"),
                    onboard_count=("is_onboard", "sum"),
                    paid_offer_count=("is_paid", "sum"),
                    paid_amount=("paid_amount", "sum"),
                )
                .reset_index()
            )
        grouped["offer_to_onboard_rate"] = grouped["onboard_count"] / grouped["matured_offer_count"].replace(0, pd.NA)
        grouped["offer_to_paid_rate"] = grouped["paid_offer_count"] / grouped["offer_count"].replace(0, pd.NA)
        grouped["paid_amount_per_offer_amount"] = grouped["paid_amount"] / grouped["offer_amount"].replace(0, pd.NA)
        return grouped

    def load_project_additions(self, start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
        """Monthly monitoring of newly added projects by company/team/consultant."""
        df = self.db_client.query(f"""
            SELECT jo.id AS joborder_id, jo.dateAdded AS added_date, jo.jobStatus AS job_status,
                   jo.jobTitle AS position_name, c.name AS client_name,
                   {_name_expr('u')} AS consultant, t.name AS team,
                   COUNT(DISTINCT os.id) AS offer_count,
                   SUM(os.revenue) AS offer_amount
            FROM joborder jo
            LEFT JOIN user u ON jo.addedBy_id = u.id
            LEFT JOIN team t ON u.team_id = t.id
            LEFT JOIN client c ON jo.client_id = c.id
            LEFT JOIN jobsubmission js ON js.joborder_id = jo.id
            LEFT JOIN offersign os ON os.jobsubmission_id = js.id AND os.active = 1
            WHERE jo.dateAdded >= '{start_date}' AND jo.dateAdded <= '{end_date}'
              AND (jo.is_deleted = 0 OR jo.is_deleted IS NULL)
            GROUP BY jo.id, jo.dateAdded, jo.jobStatus, jo.jobTitle, c.name, consultant, t.name
        """)
        if df.empty:
            return {"monthly": pd.DataFrame(), "company": pd.DataFrame(), "team": pd.DataFrame(), "consultant": pd.DataFrame(), "detail": df}

        df["added_date"] = _to_datetime(df["added_date"])
        df["month"] = df["added_date"].dt.to_period("M").astype(str)
        df["offer_count"] = pd.to_numeric(df["offer_count"], errors="coerce").fillna(0)
        df["offer_amount"] = pd.to_numeric(df["offer_amount"], errors="coerce").fillna(0)
        df["has_offer"] = df["offer_count"] > 0
        analysis_date = pd.to_datetime(end_date).normalize()
        project_mature_cutoff = analysis_date - pd.Timedelta(days=PROJECT_TO_OFFER_GRACE_DAYS)
        df["project_offer_matured"] = df["has_offer"] | (df["added_date"] <= project_mature_cutoff)
        df["is_live"] = df["job_status"].eq("Live")
        df["team"] = df["team"].fillna("(No Team)")
        df["consultant"] = df["consultant"].fillna("(No Consultant)")

        monthly = self._project_addition_group(df, ["month"])
        company = self._project_addition_group(df, [])
        company["name"] = "Company"
        company["level"] = "Company"

        perf_df = df[~df["consultant"].apply(self._is_non_consultant_account)].copy()
        team = self._project_addition_group(perf_df, ["team"])
        team["name"] = team["team"]
        team["level"] = "Team"
        consultant = self._project_addition_group(perf_df, ["consultant", "team"])
        consultant["name"] = consultant["consultant"]
        consultant["level"] = "Consultant"

        return {"monthly": monthly, "company": company, "team": team, "consultant": consultant, "detail": df}

    @staticmethod
    def _is_non_consultant_account(name: object) -> bool:
        value = str(name or "").strip().lower()
        excluded = ["郭建飞", "黄铮", "李文婷", "李菁", "黄梓茜", "sys", "csm", "运营", "system"]
        return any(part.lower() in value for part in excluded)

    @staticmethod
    def _project_addition_group(df: pd.DataFrame, keys: list) -> pd.DataFrame:
        if df.empty:
            columns = list(keys) + [
                "new_projects",
                "matured_projects",
                "pending_project_count",
                "live_projects",
                "offer_projects",
                "offer_count",
                "offer_amount",
                "project_to_offer_rate",
            ]
            return pd.DataFrame(columns=columns)
        if not keys:
            total = pd.DataFrame(
                [
                    {
                        "new_projects": int(df["joborder_id"].nunique()),
                        "matured_projects": int(df.loc[df["project_offer_matured"], "joborder_id"].nunique()),
                        "pending_project_count": int(df.loc[~df["project_offer_matured"], "joborder_id"].nunique()),
                        "live_projects": int(df.loc[df["is_live"], "joborder_id"].nunique()),
                        "offer_projects": int(df.loc[df["has_offer"], "joborder_id"].nunique()),
                        "offer_count": int(df["offer_count"].sum()),
                        "offer_amount": float(df["offer_amount"].sum()),
                    }
                ]
            )
            total["project_to_offer_rate"] = total["offer_projects"] / total["matured_projects"].replace(0, pd.NA)
            return total
        grouped = (
            df.groupby(keys, dropna=False)
            .agg(
                new_projects=("joborder_id", "nunique"),
                matured_projects=("project_offer_matured", "sum"),
                pending_project_count=("project_offer_matured", lambda x: int((~x).sum())),
                live_projects=("is_live", "sum"),
                offer_projects=("has_offer", "sum"),
                offer_count=("offer_count", "sum"),
                offer_amount=("offer_amount", "sum"),
            )
            .reset_index()
        )
        grouped["project_to_offer_rate"] = grouped["offer_projects"] / grouped["matured_projects"].replace(0, pd.NA)
        return grouped

    def _add_due_date(self, invoices: pd.DataFrame) -> pd.DataFrame:
        contracts = self.db_client.query("""
            SELECT client_id, payment_terms
            FROM clientcontract
            WHERE (is_deleted = 0 OR is_deleted IS NULL)
              AND (invalid != 1 OR invalid IS NULL)
              AND payment_terms IS NOT NULL
        """)
        term_map = {}
        if not contracts.empty:
            for _, row in contracts.iterrows():
                parsed = parse_payment_terms(row.get("payment_terms"))
                if parsed:
                    term_map[str(row.get("client_id"))] = parsed

        due_dates = []
        sources = []
        for _, row in invoices.iterrows():
            if pd.notna(row.get("estimated_payment_date")):
                due_dates.append(row["estimated_payment_date"])
                sources.append("estimatepaymentReceivedDate")
                continue
            sent_date = row.get("sent_date")
            if pd.notna(sent_date) and row.get("payment_days", 0) > 0:
                due_dates.append(sent_date + pd.Timedelta(days=int(row["payment_days"])))
                sources.append("sentDate_plus_payment_days")
                continue
            client_term = term_map.get(str(row.get("client_id")))
            if pd.notna(sent_date) and client_term:
                due_dates.append(sent_date + pd.Timedelta(days=client_term))
                sources.append("sentDate_plus_clientcontract")
                continue
            if row.get("status") == "Invoice Added" and pd.notna(row.get("date_added")):
                due_dates.append(row["date_added"] + pd.Timedelta(days=35))
                sources.append("invoice_added_plus_35_days")
                continue
            due_dates.append(pd.NaT)
            sources.append("missing")

        result = invoices.copy()
        result["due_date"] = due_dates
        result["due_date_source"] = sources
        return result


def stage_category(stage: object) -> str:
    value = str(stage or "").lower()
    if any(key in value for key in ["shortlist", "longlist", "referral", "recommend", "简历"]):
        return "Resume Referral"
    if any(key in value for key in ["1st", "first", "1面", "一面"]):
        return "1st Round Interview"
    if "offer" in value:
        return "Offer"
    if any(key in value for key in ["onboard", "入职"]):
        return "Onboard"
    return "Other"


def stage_success_rate(stage: object) -> float:
    value = str(stage or "").lower()
    if any(key in value for key in ["shortlist", "longlist", "referral", "recommend", "简历"]):
        return 0.10
    if any(key in value for key in ["1st", "first", "1面", "一面"]):
        return 0.25
    if any(key in value for key in ["2nd", "2面", "二面"]):
        return 0.30
    if any(key in value for key in ["3rd", "3面", "三面"]):
        return 0.40
    if any(key in value for key in ["final", "终面"]):
        return 0.50
    if "offer" in value:
        return 0.80
    if any(key in value for key in ["onboard", "入职"]):
        return 1.00
    return 0.10


def parse_payment_terms(value: object) -> Optional[int]:
    if value is None or pd.isna(value):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        pass
    encrypted_map = {
        "FXWBwWyR7sRFX6tGCh": 120,
        "_fdjDbWRqUypygU6nR": 90,
    }
    return encrypted_map.get(str(value).strip())
