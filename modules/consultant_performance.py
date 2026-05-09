"""Consultant 360 performance model.

The model combines past cash results, near-term offer reserve, weighted
forecast potential, and process conversion behavior. It is intentionally
deterministic so dashboard and agent answers share the same facts.
"""

from __future__ import annotations

from typing import Dict

import pandas as pd


def _norm_name(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return " ".join(str(value).strip().lower().split())


def _safe_num(value: object) -> float:
    if value is None or pd.isna(value):
        return 0.0
    return float(value)


def _score_ratio(actual: float, target: float) -> float:
    if target <= 0:
        return 0.0
    return round(max(0.0, min(actual / target, 1.0)) * 100, 1)


def _match_merge(left: pd.DataFrame, right: pd.DataFrame, value_cols: list[str]) -> pd.DataFrame:
    if right is None or right.empty or "name_key" not in right.columns:
        for col in value_cols:
            if col not in left.columns:
                left[col] = 0.0
        return left
    existing = ["name_key"] + [col for col in value_cols if col in right.columns]
    return left.merge(right[existing], on="name_key", how="left")


class ConsultantPerformanceAnalyzer:
    """Build a management-facing consultant scorecard."""

    WEIGHTS = {
        "past_score": 0.25,
        "offer_reserve_score": 0.35,
        "future_score": 0.20,
        "process_score": 0.20,
    }

    PROCESS_THRESHOLDS = {
        "referral_to_interview": 0.40,
        "interview_to_offer": 0.50,
        "offer_to_onboard": 0.90,
        "onboard_to_paid": 0.90,
        "overall": 0.05,
    }

    def analyze(
        self,
        cost: Dict[str, object],
        offer_outcomes: Dict[str, pd.DataFrame],
        pipeline: Dict[str, object],
        conversion: Dict[str, object],
        forecast_days: int = 180,
    ) -> Dict[str, object]:
        base = cost.get("ranking", pd.DataFrame()) if isinstance(cost, dict) else pd.DataFrame()
        if base is None or base.empty:
            return {"scorecard": pd.DataFrame(), "definition": self.definition(), "weights": self.WEIGHTS}

        scorecard = base.copy()
        scorecard["name_key"] = scorecard["consultant"].map(_norm_name)
        scorecard = scorecard[scorecard["name_key"] != ""].copy()

        offers = self._prepare_offers(offer_outcomes.get("consultant", pd.DataFrame()) if isinstance(offer_outcomes, dict) else pd.DataFrame())
        forecast = self._prepare_forecast(pipeline.get("by_consultant", pd.DataFrame()) if isinstance(pipeline, dict) else pd.DataFrame())
        process = self._prepare_process(conversion.get("consultant_ranking", pd.DataFrame()) if isinstance(conversion, dict) else pd.DataFrame())

        scorecard = _match_merge(
            scorecard,
            offers,
            ["offer_count", "offer_amount", "paid_amount", "offer_unpaid_amount", "offer_to_onboard_rate", "offer_to_paid_rate"],
        )
        scorecard = _match_merge(
            scorecard,
            forecast,
            ["forecast_deal_count", "forecast_amount", "weighted_forecast"],
        )
        scorecard = _match_merge(
            scorecard,
            process,
            [
                "referrals",
                "first_interviews",
                "offers",
                "onboards",
                "paid",
                "referral_to_interview",
                "interview_to_offer",
                "offer_to_onboard",
                "onboard_to_paid",
                "overall",
            ],
        )

        numeric_cols = [
            "offer_count",
            "offer_amount",
            "paid_amount",
            "offer_unpaid_amount",
            "offer_to_onboard_rate",
            "offer_to_paid_rate",
            "forecast_deal_count",
            "forecast_amount",
            "weighted_forecast",
            "referrals",
            "first_interviews",
            "offers",
            "onboards",
            "paid",
            "referral_to_interview",
            "interview_to_offer",
            "offer_to_onboard",
            "onboard_to_paid",
            "overall",
        ]
        for col in numeric_cols:
            if col in scorecard.columns:
                scorecard[col] = pd.to_numeric(scorecard[col], errors="coerce").fillna(0.0)

        forecast_months = max(float(forecast_days) / 30.0, 1.0)
        scorecard["past_cost_cover"] = scorecard.apply(
            lambda r: _safe_num(r.get("total_collection")) / max(_safe_num(r.get("period_cost")), 1.0),
            axis=1,
        )
        scorecard["offer_reserve_months"] = scorecard.apply(
            lambda r: _safe_num(r.get("offer_unpaid_amount")) / max(_safe_num(r.get("monthly_cost")), 1.0),
            axis=1,
        )
        scorecard["forecast_cost_cover"] = scorecard.apply(
            lambda r: _safe_num(r.get("weighted_forecast")) / max(_safe_num(r.get("monthly_cost")) * forecast_months, 1.0),
            axis=1,
        )
        scorecard["collection_profit"] = scorecard["total_collection"] - scorecard["period_cost"]
        scorecard["collection_profit_margin"] = scorecard.apply(
            lambda r: _safe_num(r.get("collection_profit")) / _safe_num(r.get("total_collection"))
            if _safe_num(r.get("total_collection")) > 0
            else None,
            axis=1,
        )
        scorecard["forecast_cover_months"] = scorecard.apply(
            lambda r: _safe_num(r.get("weighted_forecast")) / max(_safe_num(r.get("monthly_cost")), 1.0),
            axis=1,
        )
        scorecard["sustainability_profile"] = scorecard.apply(self._sustainability_profile, axis=1)
        scorecard["efficiency_level"] = scorecard.apply(self._efficiency_level, axis=1)

        scorecard["past_score"] = scorecard["past_cost_cover"].apply(lambda x: _score_ratio(x, 1.0))
        scorecard["offer_reserve_score"] = scorecard.apply(self._offer_reserve_score, axis=1)
        scorecard["future_score"] = scorecard["forecast_cost_cover"].apply(lambda x: _score_ratio(x, 1.0))
        scorecard["process_score"] = scorecard.apply(self._process_score, axis=1)
        scorecard["consultant_score"] = scorecard.apply(self._overall_score, axis=1)
        scorecard["consultant_status"] = scorecard.apply(self._status, axis=1)
        scorecard["risk_flags"] = scorecard.apply(self._risk_flags, axis=1)
        scorecard["management_signal"] = scorecard.apply(self._signal, axis=1)

        scorecard = scorecard.sort_values(
            ["collection_profit", "offer_reserve_months", "forecast_cover_months"],
            ascending=[False, False, False],
        )
        return {
            "scorecard": scorecard,
            "definition": self.definition(),
            "weights": self.WEIGHTS,
            "forecast_months": forecast_months,
        }

    @staticmethod
    def definition() -> str:
        return (
            "顾问360评价 = 本财年已回款(过去成绩)25% + 当前Offer未回款(余粮)35% "
            "+ Pipeline加权预测业绩(未来产能)20% + 推荐/面试/Offer/入职/回款转化(能力与态度)20%。"
        )

    @staticmethod
    def _prepare_offers(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty or "consultant" not in df.columns:
            return pd.DataFrame()
        work = df.copy()
        work["name_key"] = work["consultant"].map(_norm_name)
        for col in [
            "offer_count",
            "offer_amount",
            "paid_amount",
            "offer_unpaid_amount",
            "offer_to_onboard_rate",
            "offer_to_paid_rate",
        ]:
            if col not in work.columns:
                work[col] = 0.0
            work[col] = pd.to_numeric(work[col], errors="coerce").fillna(0.0)
        if "offer_unpaid_amount" not in df.columns:
            work["offer_unpaid_amount"] = (work["offer_amount"] - work["paid_amount"]).clip(lower=0.0)
        return work

    @staticmethod
    def _prepare_forecast(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty or "consultant" not in df.columns:
            return pd.DataFrame()
        work = df.copy()
        work["name_key"] = work["consultant"].map(_norm_name)
        rename = {
            "deal_count": "forecast_deal_count",
            "forecast_fee": "forecast_amount",
            "weighted_revenue": "weighted_forecast",
        }
        work = work.rename(columns=rename)
        for col in ["forecast_deal_count", "forecast_amount", "weighted_forecast"]:
            if col not in work.columns:
                work[col] = 0.0
            work[col] = pd.to_numeric(work[col], errors="coerce").fillna(0.0)
        return work

    @staticmethod
    def _prepare_process(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty or "consultant" not in df.columns:
            return pd.DataFrame()
        work = df.copy()
        work["name_key"] = work["consultant"].map(_norm_name)
        return work

    def _process_score(self, row: pd.Series) -> float:
        lead_scores = [
            _score_ratio(_safe_num(row.get("referral_to_interview")), self.PROCESS_THRESHOLDS["referral_to_interview"]) * 0.25,
            _score_ratio(_safe_num(row.get("interview_to_offer")), self.PROCESS_THRESHOLDS["interview_to_offer"]) * 0.35,
            _score_ratio(_safe_num(row.get("overall")), self.PROCESS_THRESHOLDS["overall"]) * 0.20,
        ]
        activity_score = _score_ratio(_safe_num(row.get("referrals")), 30.0)
        return round(sum(lead_scores) + activity_score * 0.20, 1)

    def _offer_reserve_score(self, row: pd.Series) -> float:
        reserve_months_score = _score_ratio(_safe_num(row.get("offer_reserve_months")), 2.0)
        offer_amount_score = _score_ratio(_safe_num(row.get("offer_unpaid_amount")), 300000.0)
        paid_rate_score = _score_ratio(_safe_num(row.get("offer_to_paid_rate")), 0.70)
        offer_count_score = _score_ratio(_safe_num(row.get("offer_count")), 3.0)
        return round(
            reserve_months_score * 0.35
            + offer_amount_score * 0.35
            + paid_rate_score * 0.15
            + offer_count_score * 0.15,
            1,
        )

    def _overall_score(self, row: pd.Series) -> float:
        return round(
            _safe_num(row.get("past_score")) * self.WEIGHTS["past_score"]
            + _safe_num(row.get("offer_reserve_score")) * self.WEIGHTS["offer_reserve_score"]
            + _safe_num(row.get("future_score")) * self.WEIGHTS["future_score"]
            + _safe_num(row.get("process_score")) * self.WEIGHTS["process_score"],
            1,
        )

    @staticmethod
    def _status(row: pd.Series) -> str:
        score = _safe_num(row.get("consultant_score"))
        offer_amount = _safe_num(row.get("offer_unpaid_amount"))
        offer_count = _safe_num(row.get("offer_count"))
        weighted_forecast = _safe_num(row.get("weighted_forecast"))
        interview_to_offer = _safe_num(row.get("interview_to_offer"))
        total_collection = _safe_num(row.get("total_collection"))

        if total_collection >= 300000 and offer_amount >= 300000:
            return "Growth / Near Target"
        if score >= 65 and (offer_amount < 100000 or offer_count <= 1) and interview_to_offer < 0.12:
            return "Score Inflated / PIP Review"
        if weighted_forecast < 50000 and interview_to_offer < 0.15:
            return "Performance Watch"
        if score >= 75:
            return "High Potential"
        if score >= 60:
            return "Stable"
        if score >= 45:
            return "Watch"
        return "Restructure"

    @staticmethod
    def _risk_flags(row: pd.Series) -> str:
        flags = []
        if _safe_num(row.get("offer_count")) <= 1 or _safe_num(row.get("offer_unpaid_amount")) < 100000:
            flags.append("Offer储备不足")
        if _safe_num(row.get("interview_to_offer")) < 0.15 and _safe_num(row.get("first_interviews")) >= 10:
            flags.append("面试到Offer转化弱")
        if _safe_num(row.get("weighted_forecast")) < 50000:
            flags.append("Pipeline潜力弱")
        if _safe_num(row.get("offer_to_paid_rate")) == 0 and _safe_num(row.get("offer_count")) > 0:
            flags.append("Offer尚未兑现回款")
        return "；".join(flags) if flags else "暂无明显结构性风险"

    @staticmethod
    def _sustainability_profile(row: pd.Series) -> str:
        profit = _safe_num(row.get("collection_profit"))
        offer_months = _safe_num(row.get("offer_reserve_months"))
        forecast_months = _safe_num(row.get("forecast_cover_months"))
        interview_to_offer = _safe_num(row.get("interview_to_offer"))
        if profit > 0 and offer_months >= 3:
            return "已盈利且Offer余粮充足"
        if profit > 0 and offer_months >= 1:
            return "已盈利但需盯Offer兑现"
        if profit <= 0 and (offer_months >= 2 or forecast_months >= 2):
            return "当前未覆盖成本，依赖Offer/Forecast兑现"
        if forecast_months < 1 and interview_to_offer < 0.15:
            return "未来覆盖弱且转化偏弱"
        return "需要结合过程和回款继续观察"

    @staticmethod
    def _efficiency_level(row: pd.Series) -> str:
        profit = _safe_num(row.get("collection_profit"))
        offer_months = _safe_num(row.get("offer_reserve_months"))
        forecast_months = _safe_num(row.get("forecast_cover_months"))
        interview_to_offer = _safe_num(row.get("interview_to_offer"))
        if profit > 0 and offer_months >= 3 and forecast_months >= 2:
            return "强"
        if profit > 0 and (offer_months >= 1 or forecast_months >= 1):
            return "稳"
        if profit > 0:
            return "观察"
        if offer_months >= 2 or forecast_months >= 2:
            return "待兑现"
        if interview_to_offer < 0.15:
            return "预警"
        return "观察"

    @staticmethod
    def _signal(row: pd.Series) -> str:
        status = str(row.get("consultant_status") or "")
        past = _safe_num(row.get("past_score"))
        reserve = _safe_num(row.get("offer_reserve_score"))
        future = _safe_num(row.get("future_score"))
        process = _safe_num(row.get("process_score"))
        if status == "Growth / Near Target":
            return "本年回款和当前Offer储备都较强，重点管理Offer兑现、入职和回款节奏。"
        if status == "Score Inflated / PIP Review":
            return "总分受成本覆盖或Forecast抬高，但Offer储备和面试到Offer转化不足，建议按PIP/产能改善口径管理。"
        if status == "Performance Watch":
            return "Pipeline潜力和转化都偏弱，建议进入业绩改善观察。"
        if past >= 75 and future < 45:
            return "过去业绩较好，但未来产能不足，需要补Pipeline。"
        if past < 45 and (reserve >= 60 or future >= 60):
            return "短期回款弱，但存在Offer/Forecast储备，应盯兑现。"
        if process < 45:
            return "过程动作或转化弱，优先复盘推荐质量、面试推进和岗位匹配。"
        if past < 45 and reserve < 45 and future < 45:
            return "业绩、余粮和未来产能都偏弱，建议进入产能改善或岗位调整观察。"
        return "表现相对均衡，继续跟踪回款兑现和新增Pipeline。"
