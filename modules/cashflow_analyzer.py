"""Cash flow pressure analysis."""

from __future__ import annotations

from datetime import datetime
from typing import Dict

import pandas as pd


class CashFlowAnalyzer:
    def analyze(
        self,
        invoices_df: pd.DataFrame,
        initial_cash: float,
        monthly_cost: float,
        ytd_collection: float = 0.0,
        forecast_df: pd.DataFrame = None,
        analysis_date: object = None,
        days: int = 180,
    ) -> Dict[str, object]:
        if invoices_df is None or invoices_df.empty:
            return {"summary": {}, "calendar": pd.DataFrame(), "overdue_orders": pd.DataFrame(), "data_confidence": "Low"}

        df = invoices_df.copy()
        today = pd.Timestamp(analysis_date).normalize() if analysis_date is not None else pd.Timestamp(datetime.now().date())
        collectible = df[df["status"].isin(["Sent", "Invoice Added"]) | ((df["status"] == "Received") & (df["pending_amount"] > 0))].copy()
        collectible["is_overdue"] = collectible["due_date"].notna() & (collectible["due_date"] < today)
        collectible["overdue_days"] = (today - collectible["due_date"]).dt.days.clip(lower=0)
        fiscal_start = pd.Timestamp(year=today.year, month=1, day=1)
        legacy_start = pd.Timestamp(year=today.year - 1, month=1, day=1)
        collectible["source_date"] = collectible[["sent_date", "date_added"]].min(axis=1)
        collectible["is_legacy"] = (
            collectible["source_date"].notna()
            & (collectible["source_date"] >= legacy_start)
            & (collectible["source_date"] < fiscal_start)
        )

        overdue = collectible[collectible["is_overdue"]]
        legacy = collectible[collectible["is_legacy"]]
        severe_legacy = legacy[legacy["is_overdue"] & (legacy["overdue_days"] >= 60)]
        next_30 = collectible[
            collectible["due_date"].notna()
            & (collectible["due_date"] >= today)
            & (collectible["due_date"] <= today + pd.Timedelta(days=30))
        ]
        monthly_burn = float(monthly_cost)
        start_of_year = pd.Timestamp(year=today.year, month=1, day=1)
        cost_months_elapsed = _cost_months_elapsed(start_of_year, today, payroll_day=5)
        ytd_cost = monthly_burn * cost_months_elapsed
        node_balance = float(initial_cash) + float(ytd_collection) - ytd_cost
        runway = node_balance / monthly_burn if monthly_burn else None
        summary = {
            "initial_cash": float(initial_cash),
            "ytd_collection": float(ytd_collection),
            "ytd_cost": ytd_cost,
            "node_cash_balance": node_balance,
            "months_elapsed": cost_months_elapsed,
            "payroll_day": 5,
            "collectible_count": int(len(collectible)),
            "overdue_rate": len(overdue) / len(collectible) if len(collectible) else 0.0,
            "avg_overdue_days": float(overdue["overdue_days"].mean()) if len(overdue) else 0.0,
            "overdue_amount": float(overdue["pending_amount"].sum()),
            "legacy_pending_amount": float(legacy["pending_amount"].sum()),
            "legacy_overdue_amount": float(legacy.loc[legacy["is_overdue"], "pending_amount"].sum()),
            "severe_legacy_overdue_amount": float(severe_legacy["pending_amount"].sum()),
            "severe_legacy_overdue_count": int(len(severe_legacy)),
            "next_30d_pressure": float(next_30["pending_amount"].sum()),
            "cash_runway_months": runway,
            "cash_runway_cost_base": monthly_burn,
            "risk_level": self._risk_level(len(overdue) / len(collectible) if len(collectible) else 0.0, runway),
        }
        due_source_coverage = float((collectible["due_date_source"] != "missing").sum()) / len(collectible) if len(collectible) else 0.0
        confidence = "High" if due_source_coverage >= 0.90 else "Medium" if due_source_coverage >= 0.60 else "Low"
        forecast_inflow = self._forecast_inflow(forecast_df, today)
        calendar = self._calendar(collectible, forecast_inflow, node_balance, monthly_cost, today, days)
        summary.update(self._forecast_nodes(calendar, [90, 180]))

        return {
            "summary": summary,
            "calendar": calendar,
            "overdue_orders": overdue.sort_values("overdue_days", ascending=False),
            "legacy_orders": legacy.sort_values(["is_overdue", "overdue_days", "pending_amount"], ascending=[False, False, False]),
            "next_30_orders": next_30.sort_values("due_date"),
            "forecast_inflow_orders": forecast_inflow.sort_values("due_date") if not forecast_inflow.empty else forecast_inflow,
            "client_risk": self._client_risk(collectible),
            "client_payment_terms": self._client_payment_terms(df, collectible, today),
            "data_confidence": confidence,
        }

    @staticmethod
    def _calendar(df: pd.DataFrame, forecast_df: pd.DataFrame, node_balance: float, monthly_cost: float, start_date: pd.Timestamp, days: int) -> pd.DataFrame:
        start = pd.Timestamp(start_date).normalize()
        dates = pd.date_range(start, periods=days + 1, freq="D")
        cal = pd.DataFrame({"date": dates})
        daily_outflow = float(monthly_cost) / 30.0 if monthly_cost else 0.0
        confirmed = df[df["due_date"].notna()].copy()
        confirmed["due_date"] = pd.to_datetime(confirmed["due_date"]).dt.normalize()
        confirmed_inflow = confirmed.groupby("due_date")["pending_amount"].sum()
        if forecast_df is not None and not forecast_df.empty:
            forecast = forecast_df.copy()
            forecast["due_date"] = pd.to_datetime(forecast["due_date"]).dt.normalize()
            forecast_inflow = forecast.groupby("due_date")["forecast_cash_inflow"].sum()
        else:
            forecast_inflow = pd.Series(dtype=float)
        cal["confirmed_inflow"] = cal["date"].map(confirmed_inflow).fillna(0.0)
        cal["forecast_inflow"] = cal["date"].map(forecast_inflow).fillna(0.0)
        cal["total_inflow"] = cal["confirmed_inflow"] + cal["forecast_inflow"]
        cal["outflow"] = daily_outflow
        cal["net"] = cal["total_inflow"] - cal["outflow"]
        cal["balance"] = node_balance + cal["net"].cumsum()
        cal["is_gap"] = cal["balance"] < 0
        return cal

    @staticmethod
    def _forecast_inflow(forecast_df: pd.DataFrame, analysis_date: pd.Timestamp = None) -> pd.DataFrame:
        if forecast_df is None or forecast_df.empty:
            return pd.DataFrame(columns=["forecast_id", "due_date", "forecast_cash_inflow"])
        df = forecast_df.copy()
        if "forecast_id" in df.columns:
            df = df.drop_duplicates("forecast_id", keep="first")
        if "expected_close_date" not in df.columns:
            return pd.DataFrame(columns=["forecast_id", "due_date", "forecast_cash_inflow"])
        amount_col = "weighted_revenue" if "weighted_revenue" in df.columns else "forecast_fee"
        result = pd.DataFrame()
        result["forecast_id"] = df.get("forecast_id")
        # A forecast normally needs offer, onboard, invoice and client payment time.
        # Use expected close date + 60 days as the cash timing assumption.
        analysis_day = pd.Timestamp(analysis_date).normalize() if analysis_date is not None else pd.Timestamp(datetime.now().date())
        result["original_due_date"] = pd.to_datetime(df["expected_close_date"], errors="coerce") + pd.Timedelta(days=60)
        result["is_forecast_timing_overdue"] = result["original_due_date"].notna() & (result["original_due_date"] < analysis_day)
        result["due_date"] = result["original_due_date"].where(~result["is_forecast_timing_overdue"], analysis_day)
        result["forecast_cash_inflow"] = pd.to_numeric(df[amount_col], errors="coerce").fillna(0)
        result = result[result["due_date"].notna() & (result["forecast_cash_inflow"] > 0)]
        return result

    @staticmethod
    def _client_risk(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame()
        work = df.copy()
        grouped = (
            work.groupby("client_name", dropna=False)
            .agg(
                invoice_count=("invoice_id", "count"),
                pending_amount=("pending_amount", "sum"),
                overdue_count=("is_overdue", "sum"),
                max_overdue_days=("overdue_days", "max"),
            )
            .reset_index()
        )
        grouped["overdue_rate"] = grouped["overdue_count"] / grouped["invoice_count"]
        grouped["risk_level"] = grouped.apply(
            lambda r: "Very High" if r["overdue_rate"] >= 0.60 or r["max_overdue_days"] > 30 else "High" if r["overdue_rate"] >= 0.30 else "Low",
            axis=1,
        )
        return grouped.sort_values(["risk_level", "pending_amount"], ascending=[False, False])

    @staticmethod
    def _client_payment_terms(all_invoices: pd.DataFrame, collectible: pd.DataFrame, today: pd.Timestamp) -> pd.DataFrame:
        if all_invoices is None or all_invoices.empty:
            return pd.DataFrame()

        work = all_invoices.copy()
        work["invoice_base_date"] = work["sent_date"].where(work["sent_date"].notna(), work["date_added"])
        work["contract_payment_days"] = pd.to_numeric(work.get("payment_days"), errors="coerce")
        work["actual_payment_days"] = (
            pd.to_datetime(work.get("payment_received_date"), errors="coerce") - pd.to_datetime(work["invoice_base_date"], errors="coerce")
        ).dt.days
        work["actual_payment_days"] = work["actual_payment_days"].where(work["actual_payment_days"] >= 0)
        work["is_received_full_or_partial"] = (
            work.get("payment_received_date").notna()
            & (pd.to_numeric(work.get("payment_received"), errors="coerce").fillna(0) > 0)
        )

        paid = work[work["is_received_full_or_partial"] & work["actual_payment_days"].notna()].copy()
        contract = work[work["contract_payment_days"].notna() & (work["contract_payment_days"] >= 0)].copy()

        frames = []
        if not contract.empty:
            contract_grouped = (
                contract.groupby("client_name", dropna=False)
                .agg(
                    invoice_count=("invoice_id", "count"),
                    contract_avg_days=("contract_payment_days", "mean"),
                    contract_median_days=("contract_payment_days", "median"),
                    contract_min_days=("contract_payment_days", "min"),
                    contract_max_days=("contract_payment_days", "max"),
                )
                .reset_index()
            )
            frames.append(contract_grouped)
        if not paid.empty:
            paid_grouped = (
                paid.groupby("client_name", dropna=False)
                .agg(
                    paid_invoice_count=("invoice_id", "count"),
                    actual_avg_days=("actual_payment_days", "mean"),
                    actual_median_days=("actual_payment_days", "median"),
                    actual_min_days=("actual_payment_days", "min"),
                    actual_max_days=("actual_payment_days", "max"),
                )
                .reset_index()
            )
            frames.append(paid_grouped)

        if not frames:
            result = pd.DataFrame({"client_name": sorted(work["client_name"].dropna().astype(str).unique().tolist())})
        else:
            result = frames[0]
            for frame in frames[1:]:
                result = result.merge(frame, on="client_name", how="outer")

        if collectible is not None and not collectible.empty:
            open_grouped = (
                collectible.groupby("client_name", dropna=False)
                .agg(
                    open_invoice_count=("invoice_id", "count"),
                    pending_amount=("pending_amount", "sum"),
                    overdue_count=("is_overdue", "sum"),
                    max_overdue_days=("overdue_days", "max"),
                )
                .reset_index()
            )
            result = result.merge(open_grouped, on="client_name", how="outer")

        for col in ["actual_avg_days", "contract_avg_days"]:
            if col not in result.columns:
                result[col] = pd.NA
        result["terms_gap_days"] = result.get("actual_avg_days") - result.get("contract_avg_days")
        result["payment_behavior"] = result["terms_gap_days"].apply(
            lambda x: "慢于合同" if pd.notna(x) and x > 7 else "快于合同" if pd.notna(x) and x < -7 else "接近合同" if pd.notna(x) else "缺少实收样本"
        )
        numeric_cols = [
            "invoice_count",
            "contract_avg_days",
            "contract_median_days",
            "contract_min_days",
            "contract_max_days",
            "paid_invoice_count",
            "actual_avg_days",
            "actual_median_days",
            "actual_min_days",
            "actual_max_days",
            "terms_gap_days",
            "open_invoice_count",
            "pending_amount",
            "overdue_count",
            "max_overdue_days",
        ]
        for col in numeric_cols:
            if col in result.columns:
                result[col] = pd.to_numeric(result[col], errors="coerce")
        sort_cols = [col for col in ["terms_gap_days", "pending_amount"] if col in result.columns]
        if sort_cols:
            result = result.sort_values(sort_cols, ascending=[False] * len(sort_cols))
        return result.reset_index(drop=True)

    @staticmethod
    def _risk_level(overdue_rate: float, runway: object) -> str:
        if runway is not None and runway < 1:
            return "High"
        if overdue_rate >= 0.30:
            return "High"
        if overdue_rate >= 0.20 or (runway is not None and runway < 3):
            return "Medium"
        return "Low"

    @staticmethod
    def _forecast_nodes(calendar: pd.DataFrame, horizons: list[int]) -> Dict[str, float]:
        result: Dict[str, float] = {}
        if calendar is None or calendar.empty:
            for horizon in horizons:
                result[f"balance_{horizon}d"] = 0.0
                result[f"inflow_{horizon}d"] = 0.0
                result[f"outflow_{horizon}d"] = 0.0
            return result
        for horizon in horizons:
            horizon_df = calendar.head(horizon + 1)
            result[f"balance_{horizon}d"] = float(horizon_df["balance"].iloc[-1]) if not horizon_df.empty else 0.0
            result[f"inflow_{horizon}d"] = float(horizon_df["total_inflow"].sum()) if not horizon_df.empty else 0.0
            result[f"confirmed_inflow_{horizon}d"] = float(horizon_df["confirmed_inflow"].sum()) if not horizon_df.empty else 0.0
            result[f"forecast_inflow_{horizon}d"] = float(horizon_df["forecast_inflow"].sum()) if not horizon_df.empty else 0.0
            result[f"outflow_{horizon}d"] = float(horizon_df["outflow"].sum()) if not horizon_df.empty else 0.0
        return result


def _months_elapsed(start: pd.Timestamp, end: pd.Timestamp) -> int:
    return max((end.year - start.year) * 12 + end.month - start.month + 1, 1)


def _cost_months_elapsed(start: pd.Timestamp, end: pd.Timestamp, payroll_day: int = 5) -> float:
    """Accrue cost by natural month, with current month prorated before payroll day."""
    start = pd.Timestamp(start).normalize()
    end = pd.Timestamp(end).normalize()
    if end < start:
        return 0.0

    completed_months = max((end.year - start.year) * 12 + end.month - start.month, 0)
    month_start = pd.Timestamp(year=end.year, month=end.month, day=1)
    month_end = month_start + pd.offsets.MonthEnd(0)
    days_in_month = month_end.day

    if end.day >= payroll_day:
        current_month_fraction = min(end.day / days_in_month, 1.0)
    else:
        current_month_fraction = max((end.day - 1) / days_in_month, 0.0)
    return completed_months + current_month_fraction
