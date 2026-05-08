"""Project referral efficiency analysis."""

from __future__ import annotations

from typing import Dict, List

import pandas as pd

OFFER_TO_ONBOARD_GRACE_DAYS = 90


STAGES = [
    ("Resume Referral", "is_recommended", "resume_sent_date"),
    ("1st Round Interview", "is_first_interview", "first_interview_date"),
    ("Offer", "is_offer", "offer_date"),
    ("Onboard", "is_onboard", "onboard_date"),
    ("Paid", "is_paid", "actual_payment_date"),
]


def _safe_rate(numerator: float, denominator: float) -> float:
    if denominator in (0, None) or pd.isna(denominator):
        return 0.0
    return round(float(numerator) / float(denominator), 4)


class ConversionAnalyzer:
    """Calculates the five-stage process funnel."""

    def analyze(self, process_df: pd.DataFrame, analysis_date: object = None, onboard_grace_days: int = OFFER_TO_ONBOARD_GRACE_DAYS) -> Dict[str, object]:
        if process_df is None or process_df.empty:
            return self._empty()

        funnel = []
        counts = {}
        for stage, flag, date_col in STAGES:
            mask = process_df[flag].fillna(False) if flag in process_df.columns else pd.Series(False, index=process_df.index)
            count = int(mask.sum())
            amount = self._stage_amount(process_df, stage, mask)
            counts[flag] = count
            funnel.append({"stage": stage, "count": count, "amount": amount})

        first_count = funnel[0]["count"] or 1
        for item in funnel:
            item["rate_from_start"] = _safe_rate(item["count"], first_count)

        matured_offer_mask = self._matured_offer_mask(process_df, analysis_date, onboard_grace_days)
        matured_offers = int(matured_offer_mask.sum())
        matured_onboards = int(process_df.loc[matured_offer_mask, "is_onboard"].fillna(False).sum()) if "is_onboard" in process_df.columns else 0
        pending_onboard_offers = int(counts["is_offer"] - matured_offers)

        stage_rates = {
            "referral_to_interview": _safe_rate(counts["is_first_interview"], counts["is_recommended"]),
            "interview_to_offer": _safe_rate(counts["is_offer"], counts["is_first_interview"]),
            "referral_to_offer": _safe_rate(counts["is_offer"], counts["is_recommended"]),
            "offer_to_onboard": _safe_rate(matured_onboards, matured_offers),
            "onboard_to_paid": _safe_rate(counts["is_paid"], counts["is_onboard"]),
            "overall": _safe_rate(counts["is_paid"], counts["is_recommended"]),
            "matured_offer_count": matured_offers,
            "matured_onboard_count": matured_onboards,
            "pending_onboard_offer_count": pending_onboard_offers,
        }

        return {
            "funnel": pd.DataFrame(funnel),
            "stage_rates": stage_rates,
            "consultant_ranking": self.consultant_ranking(process_df, analysis_date, onboard_grace_days),
            "health": self.health(stage_rates),
        }

    def consultant_ranking(self, process_df: pd.DataFrame, analysis_date: object = None, onboard_grace_days: int = OFFER_TO_ONBOARD_GRACE_DAYS) -> pd.DataFrame:
        if "consultant" not in process_df.columns or process_df.empty:
            return pd.DataFrame()
        rows: List[Dict[str, object]] = []
        for consultant, part in process_df.groupby("consultant", dropna=False):
            recommended = int(part["is_recommended"].fillna(False).sum())
            interviews = int(part["is_first_interview"].fillna(False).sum())
            offers = int(part["is_offer"].fillna(False).sum())
            onboards = int(part["is_onboard"].fillna(False).sum())
            paid = int(part["is_paid"].fillna(False).sum())
            matured_offer_mask = self._matured_offer_mask(part, analysis_date, onboard_grace_days)
            matured_offers = int(matured_offer_mask.sum())
            matured_onboards = int(part.loc[matured_offer_mask, "is_onboard"].fillna(False).sum()) if "is_onboard" in part.columns else 0
            rows.append(
                {
                    "consultant": consultant,
                    "referrals": recommended,
                    "first_interviews": interviews,
                    "offers": offers,
                    "matured_offers": matured_offers,
                    "pending_onboard_offers": offers - matured_offers,
                    "onboards": onboards,
                    "paid": paid,
                    "referral_to_interview": _safe_rate(interviews, recommended),
                    "interview_to_offer": _safe_rate(offers, interviews),
                    "referral_to_offer": _safe_rate(offers, recommended),
                    "offer_to_onboard": _safe_rate(matured_onboards, matured_offers),
                    "onboard_to_paid": _safe_rate(paid, onboards),
                    "overall": _safe_rate(paid, recommended),
                }
            )
        return pd.DataFrame(rows).sort_values(["overall", "paid"], ascending=[False, False])

    def health(self, rates: Dict[str, float]) -> Dict[str, object]:
        thresholds = {
            "referral_to_interview": 0.40,
            "interview_to_offer": 0.50,
            "offer_to_onboard": 0.90,
            "onboard_to_paid": 0.90,
            "referral_to_offer": 0.08,
        }
        weak = []
        for key, threshold in thresholds.items():
            if rates.get(key, 0) < threshold:
                weak.append({"metric": key, "actual": rates.get(key, 0), "threshold": threshold})
        status = "healthy" if not weak else "warning"
        return {
            "status": status,
            "bottlenecks": weak,
            "primary_bottleneck": weak[0]["metric"] if weak else None,
        }

    @staticmethod
    def _stage_amount(process_df: pd.DataFrame, stage: str, mask: pd.Series) -> float:
        if stage == "Paid":
            col = "actual_payment"
        else:
            col = "fee_amount"
        if col not in process_df.columns:
            return 0.0
        return float(pd.to_numeric(process_df.loc[mask, col], errors="coerce").fillna(0).sum())

    @staticmethod
    def _matured_offer_mask(process_df: pd.DataFrame, analysis_date: object = None, onboard_grace_days: int = OFFER_TO_ONBOARD_GRACE_DAYS) -> pd.Series:
        if process_df.empty:
            return pd.Series(False, index=process_df.index)
        if "offer_onboard_matured" in process_df.columns:
            return process_df["offer_onboard_matured"].fillna(False).astype(bool)
        is_offer = process_df["is_offer"].fillna(False) if "is_offer" in process_df.columns else pd.Series(False, index=process_df.index)
        offer_date = pd.to_datetime(process_df.get("offer_date"), errors="coerce")
        onboard_date = pd.to_datetime(process_df.get("onboard_date"), errors="coerce")
        expected_onboard_date = pd.to_datetime(process_df.get("expected_onboard_date"), errors="coerce")
        if analysis_date is None:
            analysis = pd.Timestamp.today().normalize()
        else:
            analysis = pd.to_datetime(analysis_date).normalize()
        cutoff = analysis - pd.Timedelta(days=onboard_grace_days)
        is_onboard_done = onboard_date.notna() & (onboard_date <= analysis)
        expected_due = expected_onboard_date.notna() & (expected_onboard_date <= analysis)
        no_expected_overdue = expected_onboard_date.isna() & onboard_date.isna() & (offer_date <= cutoff)
        return is_offer & (is_onboard_done | expected_due | no_expected_overdue)

    @staticmethod
    def _empty() -> Dict[str, object]:
        return {
            "funnel": pd.DataFrame(columns=["stage", "count", "amount", "rate_from_start"]),
            "stage_rates": {},
            "consultant_ranking": pd.DataFrame(),
            "health": {"status": "no_data", "bottlenecks": [], "primary_bottleneck": None},
        }
