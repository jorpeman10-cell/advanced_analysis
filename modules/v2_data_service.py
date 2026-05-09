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

        fiscal_year = pd.to_datetime(start_date).year
        legacy_start = f"{fiscal_year - 1}-01-01"

        company_offer = self.db_client.query(f"""
            SELECT 'Offer' AS metric,
                   SUM(count_value) AS count_value,
                   SUM(amount_value) AS amount_value
            FROM (
                SELECT COUNT(DISTINCT i.id) AS count_value, SUM(i.invoiceAmount) AS amount_value
                FROM invoice i
                WHERE i.status = 'Invoice Added'
                  AND COALESCE(i.sentDate, i.dateAdded) >= '{start_date}'
                  AND COALESCE(i.sentDate, i.dateAdded) <= '{end_date}'
                UNION ALL
                SELECT COUNT(DISTINCT os.id) AS count_value, SUM(os.revenue) AS amount_value
                FROM offersign os
                JOIN jobsubmission js ON os.jobsubmission_id = js.id
                WHERE os.active = 1
                  AND os.signDate = '{end_date}'
                  AND EXISTS (
                    SELECT 1 FROM invoice i
                    WHERE i.joborder_id = js.joborder_id
                      AND i.status = 'Invoice Added'
                      AND DATE(COALESCE(i.sentDate, i.dateAdded)) = '{end_date}'
                  )
            ) x
        """)
        company_invoice = self.db_client.query(f"""
            SELECT 'Invoice' AS metric,
                   SUM(count_value) AS count_value,
                   SUM(amount_value) AS amount_value
            FROM (
                SELECT COUNT(DISTINCT i.id) AS count_value, SUM(i.invoiceAmount) AS amount_value
                FROM invoice i
                WHERE i.status = 'Sent'
                  AND i.sentDate >= '{start_date}' AND i.sentDate <= '{end_date}'
                  AND i.joborder_id IN (
                    SELECT DISTINCT js.joborder_id
                    FROM offersign os
                    JOIN jobsubmission js ON os.jobsubmission_id = js.id
                    WHERE os.active = 1
                      AND os.signDate >= '{start_date}'
                      AND os.signDate <= '{end_date}'
                  )
                UNION ALL
                SELECT COUNT(DISTINCT i.id) AS count_value, SUM(i.invoiceAmount) AS amount_value
                FROM invoice i
                WHERE i.status = 'Sent'
                  AND i.sentDate >= '{start_date}' AND i.sentDate <= '{end_date}'
                  AND NOT EXISTS (
                    SELECT 1 FROM offersign os
                    JOIN jobsubmission js ON os.jobsubmission_id = js.id
                    WHERE js.joborder_id = i.joborder_id
                      AND os.active = 1
                      AND os.signDate >= '{start_date}'
                      AND os.signDate <= '{end_date}'
                  )
                  AND EXISTS (
                    SELECT 1 FROM offersign os
                    JOIN jobsubmission js ON os.jobsubmission_id = js.id
                    WHERE js.joborder_id = i.joborder_id
                      AND os.active = 1
                      AND os.signDate >= '{legacy_start}'
                      AND os.signDate < '{start_date}'
                  )
                UNION ALL
                SELECT COUNT(DISTINCT i.id) AS count_value, SUM(i.invoiceAmount) AS amount_value
                FROM invoice i
                WHERE i.status = 'Sent'
                  AND COALESCE(i.sentDate, i.dateAdded) >= '{legacy_start}'
                  AND COALESCE(i.sentDate, i.dateAdded) < '{start_date}'
            ) x
        """)
        company_collection = self.db_client.query(f"""
            SELECT 'Collection' AS metric, COUNT(DISTINCT i.id) AS count_value,
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
            SELECT 'Offer' AS metric, consultant, team,
                   SUM(count_value) AS count_value, SUM(amount_value) AS amount_value
            FROM (
                SELECT {_name_expr('u')} AS consultant, t.name AS team,
                       COUNT(DISTINCT ia.invoice_id) AS count_value,
                       SUM(ia.revenue) AS amount_value
                FROM invoiceassignment ia
                JOIN invoice i ON ia.invoice_id = i.id
                LEFT JOIN user u ON ia.user_id = u.id
                LEFT JOIN team t ON u.team_id = t.id
                WHERE i.status = 'Invoice Added'
                  AND COALESCE(i.sentDate, i.dateAdded) >= '{start_date}'
                  AND COALESCE(i.sentDate, i.dateAdded) <= '{end_date}'
                GROUP BY ia.user_id, consultant, t.name
                UNION ALL
                SELECT {_name_expr('u')} AS consultant, t.name AS team,
                       COUNT(DISTINCT os.id) AS count_value,
                       SUM(os.revenue) AS amount_value
                FROM offersign os
                JOIN jobsubmission js ON os.jobsubmission_id = js.id
                LEFT JOIN user u ON os.user_id = u.id
                LEFT JOIN team t ON u.team_id = t.id
                WHERE os.active = 1
                  AND os.signDate = '{end_date}'
                  AND EXISTS (
                    SELECT 1 FROM invoice i
                    WHERE i.joborder_id = js.joborder_id
                      AND i.status = 'Invoice Added'
                      AND DATE(COALESCE(i.sentDate, i.dateAdded)) = '{end_date}'
                  )
                GROUP BY os.user_id, consultant, t.name
            ) x
            GROUP BY consultant, team
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
            SELECT 'Invoice' AS metric, consultant, team,
                   SUM(count_value) AS count_value, SUM(amount_value) AS amount_value
            FROM (
                SELECT {_name_expr('u')} AS consultant, t.name AS team,
                       COUNT(DISTINCT ia.invoice_id) AS count_value,
                       SUM(ia.revenue) AS amount_value
                FROM invoiceassignment ia
                JOIN invoice i ON ia.invoice_id = i.id
                LEFT JOIN user u ON ia.user_id = u.id
                LEFT JOIN team t ON u.team_id = t.id
                WHERE i.status = 'Sent'
                  AND i.sentDate >= '{start_date}' AND i.sentDate <= '{end_date}'
                  AND i.joborder_id IN (
                    SELECT DISTINCT js.joborder_id
                    FROM offersign os
                    JOIN jobsubmission js ON os.jobsubmission_id = js.id
                    WHERE os.active = 1
                      AND os.signDate >= '{start_date}'
                      AND os.signDate <= '{end_date}'
                  )
                GROUP BY ia.user_id, consultant, t.name
                UNION ALL
                SELECT {_name_expr('u')} AS consultant, t.name AS team,
                       COUNT(DISTINCT ia.invoice_id) AS count_value,
                       SUM(ia.revenue) AS amount_value
                FROM invoiceassignment ia
                JOIN invoice i ON ia.invoice_id = i.id
                LEFT JOIN user u ON ia.user_id = u.id
                LEFT JOIN team t ON u.team_id = t.id
                WHERE i.status = 'Sent'
                  AND i.sentDate >= '{start_date}' AND i.sentDate <= '{end_date}'
                  AND NOT EXISTS (
                    SELECT 1 FROM offersign os
                    JOIN jobsubmission js ON os.jobsubmission_id = js.id
                    WHERE js.joborder_id = i.joborder_id
                      AND os.active = 1
                      AND os.signDate >= '{start_date}'
                      AND os.signDate <= '{end_date}'
                  )
                  AND EXISTS (
                    SELECT 1 FROM offersign os
                    JOIN jobsubmission js ON os.jobsubmission_id = js.id
                    WHERE js.joborder_id = i.joborder_id
                      AND os.active = 1
                      AND os.signDate >= '{legacy_start}'
                      AND os.signDate < '{start_date}'
                  )
                GROUP BY ia.user_id, consultant, t.name
                UNION ALL
                SELECT {_name_expr('u')} AS consultant, t.name AS team,
                       COUNT(DISTINCT ia.invoice_id) AS count_value,
                       SUM(ia.revenue) AS amount_value
                FROM invoiceassignment ia
                JOIN invoice i ON ia.invoice_id = i.id
                LEFT JOIN user u ON ia.user_id = u.id
                LEFT JOIN team t ON u.team_id = t.id
                WHERE i.status = 'Sent'
                  AND COALESCE(i.sentDate, i.dateAdded) >= '{legacy_start}'
                  AND COALESCE(i.sentDate, i.dateAdded) < '{start_date}'
                GROUP BY ia.user_id, consultant, t.name
            ) x
            GROUP BY consultant, team
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
        stage_audit = self._load_stage_balance_audit(start_date, end_date)

        if not offer_detail.empty:
            offer_detail["sign_date"] = _to_datetime(offer_detail["sign_date"])
            offer_detail["date_added"] = _to_datetime(offer_detail["date_added"])
            for col in ["offer_amount", "hunter_fee", "total_billable_compensation", "annual_salary"]:
                if col in offer_detail.columns:
                    offer_detail[col] = pd.to_numeric(offer_detail[col], errors="coerce").fillna(0)
            offer_detail["team"] = offer_detail["team"].fillna("(No Team)")
            offer_detail["consultant"] = offer_detail["consultant"].fillna("(No Consultant)")

        return {
            "company": company,
            "team": team,
            "consultant": consultant,
            "audit": audit,
            "stage_audit": stage_audit.get("stage_audit", pd.DataFrame()),
            "legacy_audit": stage_audit.get("legacy_audit", pd.DataFrame()),
            "business_stage_audit": stage_audit.get("business_stage_audit", pd.DataFrame()),
            "joborder_stage_detail": stage_audit.get("joborder_stage_detail", pd.DataFrame()),
            "offer_detail": offer_detail,
        }

    def _load_stage_balance_audit(self, start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
        fiscal_start = pd.to_datetime(start_date).date().isoformat()
        fiscal_year = pd.to_datetime(start_date).year
        legacy_start = f"{fiscal_year - 1}-01-01"
        offers = self.db_client.query(f"""
            SELECT os.id AS offer_id, js.joborder_id, os.signDate AS sign_date,
                   os.revenue AS offer_amount, {_name_expr('u')} AS consultant,
                   t.name AS team, c.name AS client_name, jo.jobTitle AS position_name
            FROM offersign os
            LEFT JOIN jobsubmission js ON os.jobsubmission_id = js.id
            LEFT JOIN joborder jo ON js.joborder_id = jo.id
            LEFT JOIN client c ON jo.client_id = c.id
            LEFT JOIN user u ON os.user_id = u.id
            LEFT JOIN team t ON u.team_id = t.id
            WHERE os.signDate >= '{legacy_start}' AND os.signDate <= '{end_date}'
              AND os.active = 1
        """)
        invoices = self.db_client.query(f"""
            SELECT i.id AS invoice_id, i.joborder_id, i.client_id, c.name AS client_name,
                   i.invoiceAmount AS invoice_amount,
                   COALESCE(i.paymentReceived, 0) AS payment_received,
                   i.status, i.sentDate AS sent_date, i.dateAdded AS date_added,
                   i.paymentReceivedDate AS payment_received_date
            FROM invoice i
            LEFT JOIN client c ON i.client_id = c.id
            WHERE (
                    COALESCE(i.sentDate, i.dateAdded) >= '{legacy_start}'
                    OR i.paymentReceivedDate >= '{fiscal_start}'
                  )
              AND COALESCE(i.sentDate, i.dateAdded) <= '{end_date}'
        """)

        if offers.empty and invoices.empty:
            return {"stage_audit": pd.DataFrame(), "legacy_audit": pd.DataFrame(), "joborder_stage_detail": pd.DataFrame()}

        if not offers.empty:
            offers["sign_date"] = _to_datetime(offers["sign_date"])
            offers["offer_amount"] = pd.to_numeric(offers["offer_amount"], errors="coerce").fillna(0)
        else:
            offers = pd.DataFrame(columns=["offer_id", "joborder_id", "offer_amount", "sign_date", "client_name", "position_name", "consultant", "team"])

        if not invoices.empty:
            for col in ["sent_date", "date_added", "payment_received_date"]:
                invoices[col] = _to_datetime(invoices[col])
            invoices["invoice_date"] = invoices["sent_date"].where(invoices["sent_date"].notna(), invoices["date_added"])
            invoices["invoice_amount"] = pd.to_numeric(invoices["invoice_amount"], errors="coerce").fillna(0)
            invoices["payment_received"] = pd.to_numeric(invoices["payment_received"], errors="coerce").fillna(0)
        else:
            invoices = pd.DataFrame(columns=["invoice_id", "joborder_id", "invoice_amount", "payment_received", "invoice_date", "payment_received_date"])

        start_ts = pd.to_datetime(start_date)
        end_ts = pd.to_datetime(end_date)
        offer_group = (
            offers.groupby("joborder_id", dropna=False)
            .agg(
                offer_count=("offer_id", "nunique"),
                offer_amount=("offer_amount", "sum"),
                first_offer_date=("sign_date", "min"),
                latest_offer_date=("sign_date", "max"),
                consultant=("consultant", lambda s: " / ".join(sorted(set(s.dropna().astype(str))))),
                team=("team", lambda s: " / ".join(sorted(set(s.dropna().astype(str))))),
                client_name=("client_name", "first"),
                position_name=("position_name", "first"),
            )
            .reset_index()
        )
        invoice_group = (
            invoices.groupby("joborder_id", dropna=False)
            .agg(
                invoice_count=("invoice_id", "nunique"),
                invoice_amount=("invoice_amount", "sum"),
                payment_received=("payment_received", "sum"),
                first_invoice_date=("invoice_date", "min"),
                latest_payment_date=("payment_received_date", "max"),
            )
            .reset_index()
        )
        detail = offer_group.merge(invoice_group, on="joborder_id", how="outer")
        for col in ["offer_count", "offer_amount", "invoice_count", "invoice_amount", "payment_received"]:
            if col in detail.columns:
                detail[col] = pd.to_numeric(detail[col], errors="coerce").fillna(0)

        detail["uninvoiced_offer_amount"] = (detail["offer_amount"] - detail["invoice_amount"]).clip(lower=0)
        detail["unpaid_invoice_amount"] = (detail["invoice_amount"] - detail["payment_received"]).clip(lower=0)
        detail["over_invoiced_amount"] = (detail["invoice_amount"] - detail["offer_amount"]).clip(lower=0)
        detail["over_collected_amount"] = (detail["payment_received"] - detail["invoice_amount"]).clip(lower=0)
        detail["stage_status"] = detail.apply(self._stage_status, axis=1)

        current_offers = offers[(offers["sign_date"] >= start_ts) & (offers["sign_date"] <= end_ts)]
        current_invoices = invoices[(invoices["invoice_date"] >= start_ts) & (invoices["invoice_date"] <= end_ts)]
        current_payments = invoices[(invoices["payment_received_date"] >= start_ts) & (invoices["payment_received_date"] <= end_ts)]
        legacy_invoices = invoices[invoices["invoice_date"] < start_ts].copy()
        legacy_offers = detail[pd.to_datetime(detail["first_offer_date"], errors="coerce") < start_ts].copy()

        stage_audit = pd.DataFrame(
            [
                {"stage": "本期新增 Offer", "amount": float(current_offers["offer_amount"].sum()), "count": int(current_offers["offer_id"].nunique()), "meaning": "本期签约的 Offer 总额"},
                {"stage": "本期新增 Invoice", "amount": float(current_invoices["invoice_amount"].sum()), "count": int(current_invoices["invoice_id"].nunique()), "meaning": "本期开票/发送的发票总额"},
                {"stage": "本期 Collection", "amount": float(current_payments["payment_received"].sum()), "count": int(current_payments["invoice_id"].nunique()), "meaning": "本期实际收到的回款；可能来自本期或历史 Invoice"},
                {"stage": "期末未开票 Offer 库存", "amount": float(detail["uninvoiced_offer_amount"].sum()), "count": int((detail["uninvoiced_offer_amount"] > 0).sum()), "meaning": "Offer 金额尚未进入 Invoice 的余额"},
                {"stage": "期末未回款 Invoice 库存", "amount": float(detail["unpaid_invoice_amount"].sum()), "count": int((detail["unpaid_invoice_amount"] > 0).sum()), "meaning": "Invoice 金额尚未进入 Collection 的余额"},
                {"stage": "金额差异/超额开票", "amount": float(detail["over_invoiced_amount"].sum()), "count": int((detail["over_invoiced_amount"] > 0).sum()), "meaning": "Invoice 金额超过 Offer 金额，需检查税费、拆单或无 Offer 发票"},
                {"stage": "金额差异/超额回款", "amount": float(detail["over_collected_amount"].sum()), "count": int((detail["over_collected_amount"] > 0).sum()), "meaning": "Collection 超过 Invoice，需检查跨单据回款或历史数据"},
            ]
        )

        legacy_audit = pd.DataFrame(
            [
                {"legacy_item": "25年遗留 Invoice 本期回款", "amount": float(legacy_invoices.loc[legacy_invoices["payment_received_date"] >= start_ts, "payment_received"].sum()), "count": int(legacy_invoices.loc[legacy_invoices["payment_received_date"] >= start_ts, "invoice_id"].nunique()), "meaning": "本期 Collection 中来自 25 年或更早开票的金额"},
                {"legacy_item": "25年遗留未回 Invoice", "amount": float((legacy_invoices["invoice_amount"] - legacy_invoices["payment_received"]).clip(lower=0).sum()), "count": int(((legacy_invoices["invoice_amount"] - legacy_invoices["payment_received"]).clip(lower=0) > 0).sum()), "meaning": "期末仍未回款的历史发票余额"},
                {"legacy_item": "25年遗留未开票 Offer", "amount": float(legacy_offers["uninvoiced_offer_amount"].sum()), "count": int((legacy_offers["uninvoiced_offer_amount"] > 0).sum()), "meaning": "历史 Offer 尚未开票的余额"},
            ]
        )

        sort_cols = [col for col in ["unpaid_invoice_amount", "uninvoiced_offer_amount"] if col in detail.columns]
        if sort_cols:
            detail = detail.sort_values(sort_cols, ascending=[False] * len(sort_cols))
        return {
            "stage_audit": stage_audit,
            "legacy_audit": legacy_audit,
            "business_stage_audit": self._business_stage_audit(fiscal_start, end_date),
            "joborder_stage_detail": detail.reset_index(drop=True),
        }

    def _business_stage_audit(self, start_date: str, end_date: str) -> pd.DataFrame:
        def scalar(query: str) -> tuple[float, int]:
            data = self.db_client.query(query)
            if data.empty:
                return 0.0, 0
            amount = pd.to_numeric(data.iloc[0].get("amount"), errors="coerce")
            count = pd.to_numeric(data.iloc[0].get("count_value"), errors="coerce")
            return float(amount) if pd.notna(amount) else 0.0, int(count) if pd.notna(count) else 0

        legacy_offer, legacy_offer_count = scalar(f"""
            SELECT SUM(i.invoiceAmount) AS amount, COUNT(DISTINCT i.id) AS count_value
            FROM invoice i
            WHERE i.status = 'Invoice Added'
              AND COALESCE(i.sentDate, i.dateAdded) >= '{start_date}'
              AND COALESCE(i.sentDate, i.dateAdded) <= '{end_date}'
              AND NOT EXISTS (
                SELECT 1 FROM offersign os
                JOIN jobsubmission js ON os.jobsubmission_id = js.id
                WHERE js.joborder_id = i.joborder_id
                  AND os.active = 1
                  AND os.signDate >= '{start_date}'
                  AND os.signDate <= '{end_date}'
              )
        """)
        current_offer_added, current_offer_added_count = scalar(f"""
            SELECT SUM(i.invoiceAmount) AS amount, COUNT(DISTINCT i.id) AS count_value
            FROM invoice i
            WHERE i.status = 'Invoice Added'
              AND COALESCE(i.sentDate, i.dateAdded) >= '{start_date}'
              AND COALESCE(i.sentDate, i.dateAdded) <= '{end_date}'
              AND i.joborder_id IN (
                SELECT DISTINCT js.joborder_id
                FROM offersign os
                JOIN jobsubmission js ON os.jobsubmission_id = js.id
                WHERE os.active = 1
                  AND os.signDate >= '{start_date}'
                  AND os.signDate <= '{end_date}'
              )
        """)
        current_sent, current_sent_count = scalar(f"""
            SELECT SUM(i.invoiceAmount) AS amount, COUNT(DISTINCT i.id) AS count_value
            FROM invoice i
            WHERE i.status = 'Sent'
              AND i.sentDate >= '{start_date}'
              AND i.sentDate <= '{end_date}'
              AND i.joborder_id IN (
                SELECT DISTINCT js.joborder_id
                FROM offersign os
                JOIN jobsubmission js ON os.jobsubmission_id = js.id
                WHERE os.active = 1
                  AND os.signDate >= '{start_date}'
                  AND os.signDate <= '{end_date}'
              )
        """)
        current_collection, current_collection_count = scalar(f"""
            SELECT SUM(i.paymentReceived) AS amount, COUNT(DISTINCT i.id) AS count_value
            FROM invoice i
            WHERE i.status = 'Received'
              AND i.paymentReceivedDate >= '{start_date}'
              AND i.paymentReceivedDate <= '{end_date}'
              AND i.joborder_id IN (
                SELECT DISTINCT js.joborder_id
                FROM offersign os
                JOIN jobsubmission js ON os.jobsubmission_id = js.id
                WHERE os.active = 1
                  AND os.signDate >= '{start_date}'
                  AND os.signDate <= '{end_date}'
              )
        """)
        all_collection, all_collection_count = scalar(f"""
            SELECT SUM(i.paymentReceived) AS amount, COUNT(DISTINCT i.id) AS count_value
            FROM invoice i
            WHERE i.status = 'Received'
              AND i.paymentReceivedDate >= '{start_date}'
              AND i.paymentReceivedDate <= '{end_date}'
        """)
        legacy_collection, legacy_collection_count = scalar(f"""
            SELECT SUM(i.paymentReceived) AS amount, COUNT(DISTINCT i.id) AS count_value
            FROM invoice i
            WHERE i.status = 'Received'
              AND i.paymentReceivedDate >= '{start_date}'
              AND i.paymentReceivedDate <= '{end_date}'
              AND COALESCE(i.sentDate, i.dateAdded) < '{start_date}'
        """)
        same_day_offer, same_day_offer_count = scalar(f"""
            SELECT SUM(os.revenue) AS amount, COUNT(DISTINCT os.id) AS count_value
            FROM offersign os
            JOIN jobsubmission js ON os.jobsubmission_id = js.id
            WHERE os.active = 1
              AND os.signDate = '{end_date}'
              AND EXISTS (
                SELECT 1 FROM invoice i
                WHERE i.joborder_id = js.joborder_id
                  AND i.status = 'Invoice Added'
                  AND DATE(COALESCE(i.sentDate, i.dateAdded)) = '{end_date}'
              )
        """)
        rows = [
            {"stage": "25年遗留 Offer", "amount": legacy_offer, "count": legacy_offer_count, "formula": "本期 Invoice Added，但 joborder 没有本期 Offer"},
            {"stage": "26年新增 Offer-已生成 Invoice Added", "amount": current_offer_added, "count": current_offer_added_count, "formula": "Invoice Added 且 joborder 有本期 Offer"},
            {"stage": "同日 Offer/Invoice Added 待确认", "amount": same_day_offer, "count": same_day_offer_count, "formula": "分析结束日同日生成 Offer 与 Invoice Added，需确认是否重复阶段归属"},
            {"stage": "26年新增 Invoice", "amount": current_sent, "count": current_sent_count, "formula": "Sent 发票且 joborder 有本期 Offer"},
            {"stage": "26年新增 Collection", "amount": current_collection, "count": current_collection_count, "formula": "Received 回款且 joborder 有本期 Offer"},
            {"stage": "25年遗留 Collection", "amount": legacy_collection, "count": legacy_collection_count, "formula": "本期收到的历史发票回款"},
            {"stage": "26年综合 Collection", "amount": all_collection, "count": all_collection_count, "formula": "本期收到的全部有效回款，用于现金和顾问表现分析"},
            {"stage": "26年三项汇总-不含待确认", "amount": current_offer_added + current_sent + current_collection, "count": current_offer_added_count + current_sent_count + current_collection_count, "formula": "Offer-已生成 Invoice Added + Invoice + Collection"},
            {"stage": "26年三项汇总-含待确认", "amount": current_offer_added + same_day_offer + current_sent + current_collection, "count": current_offer_added_count + same_day_offer_count + current_sent_count + current_collection_count, "formula": "用于对齐系统截图；若同日项重复，应回退到不含待确认"},
            {"stage": "26年综合三项汇总", "amount": current_offer_added + same_day_offer + current_sent + all_collection, "count": current_offer_added_count + same_day_offer_count + current_sent_count + all_collection_count, "formula": "Offer阶段 + Invoice阶段 + 全部本期回款；用于经营现金和顾问表现"},
        ]
        return pd.DataFrame(rows)

    @staticmethod
    def _stage_status(row: pd.Series) -> str:
        if row.get("unpaid_invoice_amount", 0) > 0:
            return "Invoice未回款"
        if row.get("uninvoiced_offer_amount", 0) > 0:
            return "Offer未开票"
        if row.get("payment_received", 0) > 0:
            return "已回款"
        if row.get("invoice_amount", 0) > 0:
            return "已开票"
        return "仅Offer"

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
        """Track current offer reserve with consultant revenue assignments.

        Offer reserve is the business-stage amount still sitting in
        ``invoice.status = 'Invoice Added'``. Consultant-level amounts must use
        ``invoiceassignment.revenue`` so collaboration splits are respected.
        Rejected/voided invoices are excluded by status and never enter unpaid
        reserve.
        """
        df = self.db_client.query(f"""
            SELECT i.id AS offer_id, i.jobsubmission_id, i.joborder_id,
                   {_name_expr('u')} AS consultant, t.name AS team,
                   COALESCE(i.sentDate, i.dateAdded) AS offer_date,
                   ia.revenue AS offer_amount,
                   0 AS paid_amount,
                   js.estimate_onboardDate AS expected_onboard_date,
                   js.onboardDate AS actual_onboard_date,
                   NULL AS paid_date,
                   i.status AS invoice_status
            FROM invoiceassignment ia
            JOIN invoice i ON ia.invoice_id = i.id
            LEFT JOIN jobsubmission js ON i.jobsubmission_id = js.id
            LEFT JOIN user u ON ia.user_id = u.id
            LEFT JOIN team t ON u.team_id = t.id
            WHERE i.status = 'Invoice Added'
              AND COALESCE(i.active, 1) = 1
              AND COALESCE(i.sentDate, i.dateAdded) >= '{start_date}'
              AND COALESCE(i.sentDate, i.dateAdded) <= '{end_date}'
            UNION ALL
            SELECT i.id AS offer_id, i.jobsubmission_id, i.joborder_id,
                   {_name_expr('u')} AS consultant, t.name AS team,
                   i.paymentReceivedDate AS offer_date,
                   0 AS offer_amount,
                   ia.revenue AS paid_amount,
                   js.estimate_onboardDate AS expected_onboard_date,
                   js.onboardDate AS actual_onboard_date,
                   i.paymentReceivedDate AS paid_date,
                   i.status AS invoice_status
            FROM invoiceassignment ia
            JOIN invoice i ON ia.invoice_id = i.id
            LEFT JOIN jobsubmission js ON i.jobsubmission_id = js.id
            LEFT JOIN user u ON ia.user_id = u.id
            LEFT JOIN team t ON u.team_id = t.id
            WHERE i.status = 'Received'
              AND COALESCE(i.active, 1) = 1
              AND i.paymentReceivedDate >= '{start_date}'
              AND i.paymentReceivedDate <= '{end_date}'
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
        df["is_offer_reserve"] = df["invoice_status"].eq("Invoice Added")
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
        reserve = df[df["is_offer_reserve"]].copy()
        paid = df[df["is_paid"]].copy()
        if not keys:
            grouped = pd.DataFrame([{
                "offer_count": int(reserve["offer_id"].nunique()),
                "matured_offer_count": int(reserve["offer_onboard_matured"].sum()),
                "pending_onboard_count": int((~reserve["offer_onboard_matured"]).sum()) if not reserve.empty else 0,
                "offer_amount": float(reserve["offer_amount"].sum()),
                "offer_unpaid_amount": float(reserve["offer_amount"].sum()),
                "onboard_count": int(reserve["is_onboard"].sum()),
                "paid_offer_count": int(paid["offer_id"].nunique()),
                "paid_amount": float(paid["paid_amount"].sum()),
            }])
        else:
            reserve_grouped = (
                reserve.groupby(keys, dropna=False)
                .agg(
                    offer_count=("offer_id", "nunique"),
                    matured_offer_count=("offer_onboard_matured", "sum"),
                    pending_onboard_count=("offer_onboard_matured", lambda x: int((~x).sum())),
                    offer_amount=("offer_amount", "sum"),
                    offer_unpaid_amount=("offer_amount", "sum"),
                    onboard_count=("is_onboard", "sum"),
                )
                .reset_index()
                if not reserve.empty
                else pd.DataFrame(columns=keys)
            )
            paid_grouped = (
                paid.groupby(keys, dropna=False)
                .agg(
                    paid_offer_count=("offer_id", "nunique"),
                    paid_amount=("paid_amount", "sum"),
                )
                .reset_index()
                if not paid.empty
                else pd.DataFrame(columns=keys)
            )
            grouped = reserve_grouped.merge(paid_grouped, on=keys, how="outer") if not reserve_grouped.empty else paid_grouped
            for col in [
                "offer_count",
                "matured_offer_count",
                "pending_onboard_count",
                "offer_amount",
                "offer_unpaid_amount",
                "onboard_count",
                "paid_offer_count",
                "paid_amount",
            ]:
                if col not in grouped.columns:
                    grouped[col] = 0
                grouped[col] = pd.to_numeric(grouped[col], errors="coerce").fillna(0)
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
