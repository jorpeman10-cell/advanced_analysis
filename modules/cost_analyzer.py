"""Consultant cost efficiency analysis."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable, Optional

import pandas as pd


def _norm_name(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _months_between(start: pd.Timestamp, end: pd.Timestamp) -> float:
    if pd.isna(start) or pd.isna(end) or end < start:
        return 0.0
    month_start = pd.Timestamp(year=start.year, month=start.month, day=1)
    month_end = pd.Timestamp(year=end.year, month=end.month, day=1)
    whole_months = (month_end.year - month_start.year) * 12 + month_end.month - month_start.month
    days_in_end_month = (month_end + pd.offsets.MonthEnd(0)).day
    end_fraction = min(end.day / days_in_end_month, 1.0)
    start_fraction = 1.0
    if start.day > 1:
        days_in_start_month = (month_start + pd.offsets.MonthEnd(0)).day
        start_fraction = max((days_in_start_month - start.day + 1) / days_in_start_month, 0.0)
    if whole_months == 0:
        days_in_month = (month_start + pd.offsets.MonthEnd(0)).day
        return max((end.day - start.day + 1) / days_in_month, 0.0)
    return max(start_fraction + max(whole_months - 1, 0) + end_fraction, 0.0)


class CostEfficiencyAnalyzer:
    DEFAULT_EXCLUDED_ACCOUNTS = {
        "郭建飞",
        "黄铮",
        "李文婷",
        "李菁",
        "黄梓茜",
        "sys",
        "csm",
        "运营",
        "system",
    }
    DEFAULT_SALARY_OVERRIDES = {
        "carrie li": 16000.0,
        "李彩霞": 16000.0,
    }

    def __init__(
        self,
        salary_multiplier: float = 3.0,
        departed_salary_multiplier: float = 2.0,
        excluded_accounts: Optional[Iterable[str]] = None,
        salary_overrides: Optional[Dict[str, float]] = None,
    ):
        self.salary_multiplier = salary_multiplier
        self.departed_salary_multiplier = departed_salary_multiplier
        base = set(self.DEFAULT_EXCLUDED_ACCOUNTS)
        if excluded_accounts:
            base.update(str(x) for x in excluded_accounts)
        self.excluded_accounts = {_norm_name(x) for x in base}
        overrides = dict(self.DEFAULT_SALARY_OVERRIDES)
        if salary_overrides:
            overrides.update(salary_overrides)
        self.salary_overrides = {_norm_name(k): float(v) for k, v in overrides.items()}

    def analyze(
        self,
        consultants_df: pd.DataFrame,
        collections_df: pd.DataFrame,
        salary_df: Optional[pd.DataFrame] = None,
        active_positions_df: Optional[pd.DataFrame] = None,
    ) -> Dict[str, object]:
        consultants = consultants_df.copy() if consultants_df is not None else pd.DataFrame()
        if consultants.empty:
            return {"summary": {}, "ranking": pd.DataFrame(), "data_confidence": "Low"}

        consultants["name_key"] = consultants["consultant"].apply(_norm_name)
        consultants = consultants[~consultants["name_key"].apply(self._is_excluded)].copy()
        if consultants.empty:
            return {"summary": {}, "ranking": pd.DataFrame(), "data_confidence": "Low"}

        salaries = self._salary_map(salary_df)
        all_consultants = consultants.copy()
        if "is_active" in all_consultants.columns:
            consultants = all_consultants[all_consultants["is_active"].fillna(False)].copy()
        else:
            consultants = all_consultants.copy()
        if consultants.empty:
            return {"summary": {}, "ranking": pd.DataFrame(), "data_confidence": "Low"}

        consultants["base_salary"] = consultants["name_key"].apply(lambda key: self._match_salary(key, salaries))
        consultants["cost_source"] = consultants.apply(
            lambda r: "provided_salary"
            if pd.notna(r["base_salary"])
            else "manual_override"
            if self._match_salary(r["name_key"], self.salary_overrides) is not None
            else "missing_salary",
            axis=1,
        )
        consultants["base_salary"] = consultants.apply(
            lambda r: r["base_salary"]
            if pd.notna(r["base_salary"])
            else self._match_salary(r["name_key"], self.salary_overrides),
            axis=1,
        )
        consultants["monthly_cost"] = consultants["base_salary"] * self.salary_multiplier
        today = pd.Timestamp(datetime.now().date())
        months_elapsed = max(datetime.now().month - 1, 0) + min(datetime.now().day / pd.Timestamp(datetime.now().date()).days_in_month, 1.0)
        months_elapsed = max(months_elapsed, 1.0)
        if "joinInDate" in consultants.columns:
            consultants["tenure_months"] = consultants["joinInDate"].apply(
                lambda value: _months_between(pd.to_datetime(value, errors="coerce"), today)
                if pd.notna(pd.to_datetime(value, errors="coerce"))
                else None
            )
        else:
            consultants["tenure_months"] = None
        consultants["maturity_stage"] = consultants["tenure_months"].apply(
            lambda value: "Ramp-up (<6m)" if pd.notna(value) and float(value) < 6 else "Mature"
        )

        company_total_collection = 0.0
        departed_period_cost = 0.0
        departed_cost_meta = {"departed_costed_count": 0, "departed_missing_salary_count": 0, "departed_missing_leave_date_count": 0}
        if collections_df is not None and not collections_df.empty:
            work = collections_df.copy()
            work["name_key"] = work["consultant"].apply(_norm_name)
            company_total_collection = float(pd.to_numeric(work["collection_amount"], errors="coerce").fillna(0).sum())
            work = work[~work["name_key"].apply(self._is_excluded)].copy()
            active_keys = set(consultants["name_key"].dropna().tolist())
            departed_work = work[~work["name_key"].isin(active_keys)].copy()
            collection_by_consultant = (
                work[work["name_key"].isin(active_keys)]
                .groupby("name_key")["collection_amount"]
                .sum()
                .reset_index()
                .rename(columns={"collection_amount": "total_collection"})
            )
            consultants = consultants.merge(collection_by_consultant, on="name_key", how="left")
            departed_period_cost, departed_cost_meta = self._departed_period_cost(all_consultants, departed_work, salaries, months_elapsed)
        else:
            consultants["total_collection"] = 0.0
        consultants["total_collection"] = consultants["total_collection"].fillna(0.0)
        consultants["monthly_collection"] = consultants["total_collection"] / months_elapsed
        consultants["period_cost"] = consultants["monthly_cost"] * months_elapsed
        consultants["cost_revenue_ratio"] = consultants.apply(
            lambda r: r["period_cost"] / r["total_collection"] if r["total_collection"] > 0 else None,
            axis=1,
        )
        consultants["efficiency_rating"] = consultants["cost_revenue_ratio"].apply(self._rating)

        active_count = int(consultants["is_active"].fillna(True).sum()) if "is_active" in consultants else len(consultants)
        total_monthly_cost = float(consultants["monthly_cost"].sum())
        active_consultant_collection = float(consultants["total_collection"].sum())
        total_collection = company_total_collection if company_total_collection else active_consultant_collection
        active_period_cost = total_monthly_cost * months_elapsed
        period_cost = active_period_cost + departed_period_cost
        salary_coverage = float((consultants["cost_source"].isin(["provided_salary", "manual_override"])).sum()) / len(consultants)
        confidence = "High" if salary_coverage >= 0.90 else "Medium" if salary_coverage >= 0.60 else "Low"
        summary = {
            "active_consultants": active_count,
            "monthly_cost": total_monthly_cost,
            "period_cost": period_cost,
            "active_period_cost": active_period_cost,
            "departed_period_cost": departed_period_cost,
            "departed_salary_multiplier": self.departed_salary_multiplier,
            **departed_cost_meta,
            "months_elapsed": months_elapsed,
            "annual_collection": total_collection,
            "active_consultant_collection": active_consultant_collection,
            "departed_or_unmatched_collection": max(total_collection - active_consultant_collection, 0.0),
            "per_capita_monthly_collection": (total_collection / months_elapsed / active_count) if active_count else 0.0,
            "cost_revenue_ratio": (period_cost / total_collection) if total_collection else None,
            "salary_coverage": salary_coverage,
            "missing_salary_count": int((consultants["cost_source"] == "missing_salary").sum()),
        }
        return {
            "summary": summary,
            "ranking": consultants.sort_values(["efficiency_rating", "total_collection"], ascending=[True, False]),
            "data_confidence": confidence,
        }

    def _departed_period_cost(self, all_consultants: pd.DataFrame, departed_work: pd.DataFrame, salaries: Dict[str, float], months_elapsed: float):
        if departed_work is None or departed_work.empty or all_consultants is None or all_consultants.empty:
            return 0.0, {"departed_costed_count": 0, "departed_missing_salary_count": 0, "departed_missing_leave_date_count": 0}
        today = pd.Timestamp(datetime.now().date())
        fiscal_start = pd.Timestamp(year=today.year, month=1, day=1)
        names = departed_work["name_key"].dropna().unique().tolist()
        departed = all_consultants[all_consultants["name_key"].isin(names)].copy()
        if departed.empty:
            return 0.0
        total = 0.0
        costed = 0
        missing_salary = 0
        missing_leave = 0
        for _, row in departed.drop_duplicates("name_key").iterrows():
            salary = self._match_salary(row.get("name_key"), salaries)
            if salary is None:
                salary = self._match_salary(row.get("name_key"), self.salary_overrides)
            if salary is None or pd.isna(salary):
                missing_salary += 1
                continue
            join_date = pd.to_datetime(row.get("joinInDate"), errors="coerce")
            leave_date = pd.to_datetime(row.get("leaveDate"), errors="coerce")
            start = max(fiscal_start, join_date.normalize()) if pd.notna(join_date) else fiscal_start
            if pd.notna(leave_date) and leave_date.normalize() >= fiscal_start:
                end = min(today, leave_date.normalize())
                months = _months_between(start, end)
            else:
                missing_leave += 1
                continue
            total += float(salary) * self.departed_salary_multiplier * months
            costed += 1
        return total, {
            "departed_costed_count": costed,
            "departed_missing_salary_count": missing_salary,
            "departed_missing_leave_date_count": missing_leave,
        }

    def _salary_map(self, salary_df: Optional[pd.DataFrame]) -> Dict[str, float]:
        if salary_df is None or salary_df.empty:
            return {}
        df = salary_df.copy()
        name_col = self._find_column(df, ["consultant", "name", "顾问", "姓名", "员工", "员工姓名", "顾问姓名"])
        salary_col = self._find_column(df, ["base_salary", "salary", "monthly_salary", "底薪", "基本工资", "月薪", "工资", "顾问底薪"])
        if name_col not in df.columns or salary_col not in df.columns:
            return {}
        df["name_key"] = df[name_col].apply(_norm_name)
        df[salary_col] = pd.to_numeric(df[salary_col], errors="coerce")
        return df.dropna(subset=[salary_col]).set_index("name_key")[salary_col].to_dict()

    @staticmethod
    def _match_salary(consultant_key: str, salaries: Dict[str, float]):
        if consultant_key in salaries:
            return salaries[consultant_key]
        for salary_key in sorted(salaries.keys(), key=len, reverse=True):
            if not salary_key:
                continue
            if salary_key in consultant_key or consultant_key in salary_key:
                return salaries[salary_key]
        return None

    def _is_excluded(self, consultant_key: str) -> bool:
        if not consultant_key:
            return True
        return any(excluded and excluded in consultant_key for excluded in self.excluded_accounts)

    @staticmethod
    def _find_column(df: pd.DataFrame, candidates: Iterable[str]) -> str:
        normalized = {str(col).strip().lower(): col for col in df.columns}
        for candidate in candidates:
            key = candidate.strip().lower()
            if key in normalized:
                return normalized[key]
        return ""

    @staticmethod
    def _rating(value: object) -> str:
        if value is None or pd.isna(value):
            return "No Revenue"
        if value < 0.40:
            return "Excellent"
        if value < 0.60:
            return "Good"
        return "Needs Improvement"
