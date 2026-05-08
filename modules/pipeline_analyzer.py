"""Pipeline health analysis."""

from __future__ import annotations

from typing import Dict

import pandas as pd


class PipelineAnalyzer:
    def analyze(self, forecast_df: pd.DataFrame, days: int = 180, analysis_date: object = None) -> Dict[str, object]:
        if forecast_df is None or forecast_df.empty:
            return {
                "summary": {"deal_count": 0, "forecast_fee": 0.0, "weighted_revenue": 0.0, "avg_success_rate": 0.0},
                "by_stage": pd.DataFrame(),
                "by_consultant": pd.DataFrame(),
                "calendar": pd.DataFrame(),
                "data_confidence": "Low",
            }

        df = forecast_df.copy()
        analysis_day = pd.Timestamp(analysis_date).normalize() if analysis_date is not None else pd.Timestamp.today().normalize()
        if "raw_days_to_close" in df.columns:
            df["is_within_forecast_window"] = df["raw_days_to_close"].fillna(days + 1) <= days
        elif "expected_close_date" in df.columns:
            raw_days = (pd.to_datetime(df["expected_close_date"], errors="coerce").dt.normalize() - analysis_day).dt.days
            df["is_within_forecast_window"] = raw_days.fillna(days + 1) <= days
        else:
            df["is_within_forecast_window"] = True

        company_df = df.drop_duplicates("forecast_id", keep="first").copy()
        in_window = company_df[company_df["is_within_forecast_window"].fillna(False)].copy()
        summary = {
            "deal_count": int(company_df["forecast_id"].nunique()),
            "forecast_fee": float(company_df["forecast_fee"].sum()),
            "weighted_revenue": float(company_df["weighted_revenue"].sum()),
            "avg_success_rate": float(company_df["success_rate"].mean()) if len(company_df) else 0.0,
            "in_window_deal_count": int(in_window["forecast_id"].nunique()) if not in_window.empty else 0,
            "in_window_forecast_fee": float(in_window["forecast_fee"].sum()) if not in_window.empty else 0.0,
            "in_window_weighted_revenue": float(in_window["weighted_revenue"].sum()) if not in_window.empty else 0.0,
            "overdue_deal_count": int(company_df["is_forecast_overdue"].fillna(False).sum()) if "is_forecast_overdue" in company_df.columns else 0,
            "overdue_forecast_fee": float(company_df.loc[company_df["is_forecast_overdue"].fillna(False), "forecast_fee"].sum()) if "is_forecast_overdue" in company_df.columns else 0.0,
            "overdue_weighted_revenue": float(company_df.loc[company_df["is_forecast_overdue"].fillna(False), "weighted_revenue"].sum()) if "is_forecast_overdue" in company_df.columns else 0.0,
        }
        by_stage = self._company_group(company_df, "stage_category")
        by_consultant = self._assignment_group(df, "consultant")
        calendar = pd.DataFrame()
        if "expected_close_date" in df.columns:
            company_df["forecast_timing_date"] = pd.to_datetime(company_df["expected_close_date"], errors="coerce")
            overdue_mask = company_df.get("is_forecast_overdue", False)
            company_df.loc[overdue_mask.fillna(False), "forecast_timing_date"] = analysis_day
            calendar = (
                company_df.groupby(pd.Grouper(key="forecast_timing_date", freq="W"))[["forecast_fee", "weighted_revenue"]]
                .sum()
                .reset_index()
            )
            calendar = calendar.rename(columns={"forecast_timing_date": "expected_close_date"})

        known_stage_rate = 0.0
        if "stage_source" in df.columns and len(df):
            known_stage_rate = float((df["stage_source"] == "mapped").sum()) / len(df)
        confidence = "High" if known_stage_rate >= 0.90 else "Medium" if known_stage_rate >= 0.60 else "Low"

        return {
            "summary": summary,
            "by_stage": by_stage,
            "by_consultant": by_consultant,
            "calendar": calendar,
            "data_confidence": confidence,
        }

    @staticmethod
    def _company_group(df: pd.DataFrame, column: str) -> pd.DataFrame:
        if column not in df.columns or df.empty:
            return pd.DataFrame()
        return (
            df.groupby(column, dropna=False)
            .agg(
                deal_count=("forecast_id", "count"),
                forecast_fee=("forecast_fee", "sum"),
                weighted_revenue=("weighted_revenue", "sum"),
                avg_success_rate=("success_rate", "mean"),
            )
            .reset_index()
            .sort_values("weighted_revenue", ascending=False)
        )

    @staticmethod
    def _assignment_group(df: pd.DataFrame, column: str) -> pd.DataFrame:
        if column not in df.columns or df.empty:
            return pd.DataFrame()
        amount_col = "assignment_amount" if "assignment_amount" in df.columns else "forecast_fee"
        weighted_col = "assignment_weighted_revenue" if "assignment_weighted_revenue" in df.columns else "weighted_revenue"
        return (
            df.groupby(column, dropna=False)
            .agg(
                deal_count=("forecast_id", "nunique"),
                forecast_fee=(amount_col, "sum"),
                weighted_revenue=(weighted_col, "sum"),
                avg_success_rate=("success_rate", "mean"),
            )
            .reset_index()
            .sort_values("weighted_revenue", ascending=False)
        )
