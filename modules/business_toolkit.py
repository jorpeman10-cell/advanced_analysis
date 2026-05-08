"""Deterministic business analysis toolkit for the agent page.

The agent layer should call these tools instead of querying the database or
inventing metrics. Each tool returns facts plus metric definitions.
"""

from __future__ import annotations

from typing import Dict, List

import pandas as pd


def _money(value) -> str:
    if value is None or pd.isna(value):
        return "-"
    value = float(value)
    if abs(value) >= 10000:
        return f"¥{value / 10000:,.1f}万"
    return f"¥{value:,.0f}"


def _pct(value) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value) * 100:.1f}%"


def _top_records(df: pd.DataFrame, columns: List[str], sort_by: str = "", limit: int = 8) -> List[Dict[str, object]]:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return []
    existing = [c for c in columns if c in df.columns]
    work = df[existing].copy()
    if sort_by and sort_by in work.columns:
        work = work.sort_values(sort_by, ascending=False)
    return work.head(limit).where(pd.notna(work), None).to_dict(orient="records")


def _records(df: pd.DataFrame, limit: int = 12) -> List[Dict[str, object]]:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return []
    return df.head(limit).where(pd.notna(df), None).to_dict(orient="records")


class BusinessAnalysisToolkit:
    """Read-only, context-backed business tools."""

    def __init__(self, context: Dict[str, object]):
        self.context = context

    def company_snapshot(self) -> Dict[str, object]:
        health = self.context.get("health", {})
        cost = self.context.get("cost", {})
        cashflow = self.context.get("cashflow", {})
        pipeline = self.context.get("pipeline", {})
        ytd = self.context.get("ytd", {})
        company_ytd = ytd.get("company", pd.DataFrame()) if isinstance(ytd, dict) else pd.DataFrame()
        return {
            "tool": "company_snapshot",
            "definition": "公司经营快照，来自三速模型、YTD业务数据、成本模型、现金流模型和Pipeline模型。",
            "facts": {
                "overall_score": health.get("overall_score"),
                "overall_status": health.get("overall_status"),
                "cost_revenue_ratio": cost.get("summary", {}).get("cost_revenue_ratio"),
                "monthly_cost": cost.get("summary", {}).get("monthly_cost"),
                "node_cash_balance": cashflow.get("summary", {}).get("node_cash_balance"),
                "cash_runway_months": cashflow.get("summary", {}).get("cash_runway_months"),
                "pipeline_forecast_fee": pipeline.get("summary", {}).get("forecast_fee"),
                "pipeline_weighted_revenue": pipeline.get("summary", {}).get("weighted_revenue"),
            },
            "ytd_company": _top_records(company_ytd, ["metric", "count_value", "amount_value"], limit=12),
        }

    def cashflow_forecast(self) -> Dict[str, object]:
        cashflow = self.context.get("cashflow", {})
        summary = cashflow.get("summary", {})
        return {
            "tool": "cashflow_forecast",
            "definition": "节点现金余额 = 年初现金余额 + 本年已回款 - 本年累计月成本；预期现金余额 = 节点现金余额 + 确认应收 + Forecast加权预测回款 - 周期内顾问成本。",
            "facts": {
                "initial_cash": summary.get("initial_cash"),
                "ytd_collection": summary.get("ytd_collection"),
                "ytd_cost": summary.get("ytd_cost"),
                "node_cash_balance": summary.get("node_cash_balance"),
                "cash_runway_months": summary.get("cash_runway_months"),
                "balance_90d": summary.get("balance_90d"),
                "confirmed_inflow_90d": summary.get("confirmed_inflow_90d"),
                "forecast_inflow_90d": summary.get("forecast_inflow_90d"),
                "outflow_90d": summary.get("outflow_90d"),
                "balance_180d": summary.get("balance_180d"),
                "confirmed_inflow_180d": summary.get("confirmed_inflow_180d"),
                "forecast_inflow_180d": summary.get("forecast_inflow_180d"),
                "outflow_180d": summary.get("outflow_180d"),
                "legacy_pending_amount": summary.get("legacy_pending_amount"),
                "severe_legacy_overdue_amount": summary.get("severe_legacy_overdue_amount"),
            },
            "overdue_orders": _top_records(
                cashflow.get("overdue_orders"),
                ["invoice_id", "client_name", "status", "pending_amount", "due_date", "overdue_days"],
                "pending_amount",
                8,
            ),
            "legacy_orders": _top_records(
                cashflow.get("legacy_orders"),
                ["invoice_id", "client_name", "status", "pending_amount", "source_date", "due_date", "overdue_days"],
                "pending_amount",
                8,
            ),
        }

    def business_outlook(self) -> Dict[str, object]:
        """Forward-looking monthly operating outlook from existing model outputs."""
        cashflow = self.context.get("cashflow", {})
        cost = self.context.get("cost", {})
        pipeline = self.context.get("pipeline", {})
        additions = self.context.get("project_additions", {})
        monthly_cost = float(cost.get("summary", {}).get("monthly_cost") or cashflow.get("summary", {}).get("cash_runway_cost_base") or 0)

        cash_monthly = self._monthly_cash_calendar(cashflow.get("calendar"), monthly_cost)
        project_monthly = additions.get("monthly", pd.DataFrame()) if isinstance(additions, dict) else pd.DataFrame()
        pipeline_calendar = pipeline.get("calendar", pd.DataFrame()) if isinstance(pipeline, dict) else pd.DataFrame()

        best_inflow = cash_monthly[cash_monthly["total_inflow"] > 0].sort_values("total_inflow", ascending=False).head(3) if not cash_monthly.empty else pd.DataFrame()
        weakest_net = cash_monthly.sort_values("net_cash", ascending=True).head(3) if not cash_monthly.empty else pd.DataFrame()
        cash_low = cash_monthly.sort_values("ending_balance", ascending=True).head(3) if not cash_monthly.empty else pd.DataFrame()
        project_signal = self._monthly_project_signal(project_monthly)
        pipeline_signal = self._monthly_pipeline_signal(pipeline_calendar)

        return {
            "tool": "business_outlook",
            "definition": (
                "未来经营趋势工具：按月汇总确认应收、Forecast加权预计回款和顾问成本，"
                "识别回款爆发月、低产月、收支不平衡月和现金余额低点。"
            ),
            "facts": {
                "monthly_cost_base": monthly_cost,
                "months_covered": int(len(cash_monthly)) if not cash_monthly.empty else 0,
                "negative_net_months": int((cash_monthly["net_cash"] < 0).sum()) if not cash_monthly.empty else 0,
                "negative_balance_months": int((cash_monthly["ending_balance"] < 0).sum()) if not cash_monthly.empty else 0,
            },
            "monthly_cash": _records(cash_monthly, 12),
            "likely_burst_months": _records(best_inflow, 3),
            "low_or_imbalanced_months": _records(weakest_net, 3),
            "cash_low_point_months": _records(cash_low, 3),
            "project_monthly_signal": _records(project_signal, 12),
            "pipeline_monthly_signal": _records(pipeline_signal, 12),
        }

    def consultant_cost(self) -> Dict[str, object]:
        cost = self.context.get("cost", {})
        ranking = cost.get("ranking", pd.DataFrame())
        return {
            "tool": "consultant_cost",
            "definition": "顾问成本收入比 = 顾问月成本 × 实际财年月份 / 顾问YTD累计回款。",
            "summary": cost.get("summary", {}),
            "top_pressure": _top_records(
                ranking,
                ["consultant", "team", "base_salary", "monthly_cost", "total_collection", "monthly_collection", "period_cost", "cost_revenue_ratio", "efficiency_rating"],
                "cost_revenue_ratio",
                10,
            ),
        }

    def consultant_performance(self) -> Dict[str, object]:
        performance = self.context.get("consultant_performance", {})
        scorecard = performance.get("scorecard", pd.DataFrame()) if isinstance(performance, dict) else pd.DataFrame()
        return {
            "tool": "consultant_performance",
            "definition": performance.get("definition", "顾问360评价：过去成绩、Offer余粮、Forecast潜力、过程转化综合判断。")
            if isinstance(performance, dict)
            else "顾问360评价：过去成绩、Offer余粮、Forecast潜力、过程转化综合判断。",
            "summary": {
                "consultant_count": int(len(scorecard)) if isinstance(scorecard, pd.DataFrame) else 0,
                "avg_score": float(scorecard["consultant_score"].mean()) if isinstance(scorecard, pd.DataFrame) and not scorecard.empty and "consultant_score" in scorecard else 0.0,
                "watch_or_restructure_count": int(scorecard["consultant_status"].isin(["Watch", "Restructure"]).sum())
                if isinstance(scorecard, pd.DataFrame) and not scorecard.empty and "consultant_status" in scorecard
                else 0,
            },
            "weights": performance.get("weights", {}) if isinstance(performance, dict) else {},
            "top_consultants": _top_records(
                scorecard,
                ["consultant", "team", "efficiency_level", "total_collection", "period_cost", "collection_profit", "collection_profit_margin", "offer_reserve_months", "forecast_cover_months", "sustainability_profile"],
                "collection_profit",
                8,
            ),
            "watch_list": _top_records(
                scorecard.sort_values(["offer_reserve_months", "forecast_cover_months"], ascending=[True, True]) if isinstance(scorecard, pd.DataFrame) and not scorecard.empty else scorecard,
                ["consultant", "team", "efficiency_level", "sustainability_profile", "offer_unpaid_amount", "offer_reserve_months", "weighted_forecast", "forecast_cover_months", "risk_flags", "management_signal"],
                "",
                8,
            ),
        }

    def offer_outcomes(self) -> Dict[str, object]:
        outcomes = self.context.get("offer_outcomes", {})
        return {
            "tool": "offer_outcomes",
            "definition": "Offer入职率 = 已到预计入职观察期且实际入职的Offer数 / 已到预计入职观察期Offer数；未到预计入职日的Offer不进失败分母。Offer回款转化率 = 本财年Offer中已产生回款的Offer数量 / 本财年Offer数量。",
            "company": _top_records(outcomes.get("company"), ["offer_count", "matured_offer_count", "pending_onboard_count", "offer_amount", "onboard_count", "paid_offer_count", "paid_amount", "offer_to_onboard_rate", "offer_to_paid_rate"], limit=3),
            "team": _top_records(outcomes.get("team"), ["team", "offer_count", "matured_offer_count", "pending_onboard_count", "offer_amount", "onboard_count", "paid_offer_count", "offer_to_onboard_rate", "offer_to_paid_rate"], "offer_count", 10),
            "consultant": _top_records(outcomes.get("consultant"), ["consultant", "offer_count", "matured_offer_count", "pending_onboard_count", "offer_amount", "onboard_count", "paid_offer_count", "offer_to_onboard_rate", "offer_to_paid_rate"], "offer_count", 10),
        }

    def pipeline_forecast(self) -> Dict[str, object]:
        pipeline = self.context.get("pipeline", {})
        return {
            "tool": "pipeline_forecast",
            "definition": "Pipeline公司总额按forecast_id去重；现金预测采用weighted_revenue，并按expected_close_date + 60天作为预计到账时间。",
            "summary": pipeline.get("summary", {}),
            "by_stage": _top_records(pipeline.get("by_stage"), ["stage_category", "deal_count", "forecast_fee", "weighted_revenue", "avg_success_rate"], "weighted_revenue", 10),
            "by_consultant": _top_records(pipeline.get("by_consultant"), ["consultant", "deal_count", "forecast_fee", "weighted_revenue", "avg_success_rate"], "weighted_revenue", 10),
        }

    def project_additions(self) -> Dict[str, object]:
        additions = self.context.get("project_additions", {})
        return {
            "tool": "project_additions",
            "definition": "项目新增监测为过程观察指标，不纳入当前评分；顾问和团队维度排除运营/Sys/CSM账号。",
            "company": _top_records(additions.get("company"), ["new_projects", "live_projects", "offer_projects", "offer_count", "offer_amount", "project_to_offer_rate"], limit=3),
            "team": _top_records(additions.get("team"), ["team", "new_projects", "live_projects", "offer_projects", "offer_count", "project_to_offer_rate"], "new_projects", 10),
            "consultant": _top_records(additions.get("consultant"), ["consultant", "team", "new_projects", "live_projects", "offer_projects", "offer_count", "project_to_offer_rate"], "new_projects", 10),
        }

    @staticmethod
    def _monthly_cash_calendar(calendar: pd.DataFrame, monthly_cost: float) -> pd.DataFrame:
        if calendar is None or not isinstance(calendar, pd.DataFrame) or calendar.empty or "date" not in calendar.columns:
            return pd.DataFrame()
        df = calendar.copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df[df["date"].notna()].copy()
        if df.empty:
            return pd.DataFrame()
        for col in ["confirmed_inflow", "forecast_inflow", "total_inflow", "outflow", "net", "balance"]:
            if col not in df.columns:
                df[col] = 0.0
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
        df["month"] = df["date"].dt.to_period("M").astype(str)
        grouped = (
            df.groupby("month", dropna=False)
            .agg(
                confirmed_inflow=("confirmed_inflow", "sum"),
                forecast_inflow=("forecast_inflow", "sum"),
                total_inflow=("total_inflow", "sum"),
                outflow=("outflow", "sum"),
                net_cash=("net", "sum"),
                ending_balance=("balance", "last"),
                min_balance=("balance", "min"),
            )
            .reset_index()
        )
        grouped["cost_base"] = monthly_cost
        grouped["risk_level"] = grouped.apply(BusinessAnalysisToolkit._month_risk, axis=1)
        grouped["signal"] = grouped.apply(BusinessAnalysisToolkit._month_signal, axis=1)
        return grouped

    @staticmethod
    def _month_risk(row: pd.Series) -> str:
        if row.get("ending_balance", 0) < 0 or row.get("min_balance", 0) < 0:
            return "High"
        if row.get("net_cash", 0) < 0 and row.get("ending_balance", 0) < row.get("cost_base", 0):
            return "Medium"
        if row.get("net_cash", 0) < 0:
            return "Watch"
        return "Low"

    @staticmethod
    def _month_signal(row: pd.Series) -> str:
        total_inflow = float(row.get("total_inflow", 0) or 0)
        forecast = float(row.get("forecast_inflow", 0) or 0)
        confirmed = float(row.get("confirmed_inflow", 0) or 0)
        net = float(row.get("net_cash", 0) or 0)
        if net < 0 and total_inflow <= float(row.get("outflow", 0) or 0) * 0.5:
            return "低产且收支承压"
        if confirmed > 0 and forecast > 0:
            return "确认应收+Forecast共同支撑"
        if confirmed > 0:
            return "主要依赖确认应收"
        if forecast > 0:
            return "主要依赖Forecast兑现"
        return "无明显回款流入"

    @staticmethod
    def _monthly_project_signal(monthly: pd.DataFrame) -> pd.DataFrame:
        if monthly is None or not isinstance(monthly, pd.DataFrame) or monthly.empty:
            return pd.DataFrame()
        df = monthly.copy()
        keep = [c for c in ["month", "new_projects", "matured_projects", "pending_project_count", "offer_projects", "offer_count", "project_to_offer_rate"] if c in df.columns]
        if not keep:
            return pd.DataFrame()
        df = df[keep].copy()
        if "project_to_offer_rate" in df.columns:
            df = df.sort_values("month")
        return df

    @staticmethod
    def _monthly_pipeline_signal(calendar: pd.DataFrame) -> pd.DataFrame:
        if calendar is None or not isinstance(calendar, pd.DataFrame) or calendar.empty:
            return pd.DataFrame()
        df = calendar.copy()
        if "expected_close_date" not in df.columns:
            return pd.DataFrame()
        df["month"] = pd.to_datetime(df["expected_close_date"], errors="coerce").dt.to_period("M").astype(str)
        for col in ["forecast_fee", "weighted_revenue"]:
            if col not in df.columns:
                df[col] = 0.0
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
        return (
            df.groupby("month", dropna=False)
            .agg(forecast_fee=("forecast_fee", "sum"), weighted_revenue=("weighted_revenue", "sum"))
            .reset_index()
            .sort_values("month")
        )

    def conversion_efficiency(self) -> Dict[str, object]:
        conversion = self.context.get("conversion", {})
        return {
            "tool": "conversion_efficiency",
            "definition": "项目推进效率来自推荐、一面、Offer、入职、回款五段漏斗。",
            "stage_rates": conversion.get("stage_rates", {}),
            "health": conversion.get("health", {}),
            "consultant_ranking": _top_records(
                conversion.get("consultant_ranking"),
                ["consultant", "referrals", "first_interviews", "offers", "onboards", "paid", "referral_to_interview", "interview_to_offer", "referral_to_offer", "offer_to_onboard", "onboard_to_paid", "overall"],
                "referrals",
                12,
            ),
        }


def format_tool_result(result: Dict[str, object]) -> str:
    """Compact deterministic answer text for early MVP."""
    tool = result.get("tool", "unknown")
    facts = result.get("facts") or result.get("summary") or {}
    lines = [f"工具：{tool}", f"口径：{result.get('definition', '-')}"]
    if isinstance(facts, dict) and facts:
        lines.append("关键数据：")
        for key, value in facts.items():
            if isinstance(value, float):
                if "ratio" in key or "rate" in key:
                    shown = _pct(value)
                elif "months" in key:
                    shown = f"{value:.1f}月"
                else:
                    shown = _money(value)
            else:
                shown = value
            lines.append(f"- {key}: {shown}")
    return "\n".join(lines)
