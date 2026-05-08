"""Project-level progress and conversion analysis."""

from __future__ import annotations

from typing import Dict

import pandas as pd


def _safe_rate(numerator: float, denominator: float) -> float:
    if denominator in (0, None) or pd.isna(denominator):
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def _safe_date(series: pd.Series):
    return pd.to_datetime(series, errors="coerce")


def classify_function(title: object) -> str:
    value = str(title or "").lower()
    buckets = [
        ("临床医学/医学事务", ["medical", "physician", "msl", "医学", "医学事务", "临床医学"]),
        ("临床运营/项目管理", ["clinical", "crm", "crp", "cra", "ppm", "project", "临床", "项目"]),
        ("注册/法规", [" ra ", "regulatory", "registration", "注册", "法规"]),
        ("质量/QA/QC/PV", ["qa", "qc", "quality", "pv", "质量", "药物警戒"]),
        ("市场/商业/准入", ["marketing", "commercial", "market", "access", "bd", "sales", "市场", "商业", "准入"]),
        ("研发/技术/CMC", ["rd", "r&d", "cmc", "scientist", "研发", "工艺", "技术"]),
        ("供应链/生产", ["supply", "distribution", "manufacturing", "生产", "供应链", "渠道"]),
        ("职能管理", ["hr", "finance", "legal", "training", "人力", "财务", "法务", "培训"]),
    ]
    padded = f" {value} "
    for name, keys in buckets:
        if any(key in padded for key in keys):
            return name
    return "其他/待分类"


def _is_other_function(value: object) -> bool:
    text = str(value or "")
    return any(key in text for key in ["其他", "待分类", "鍏朵粬", "寰呭垎"])


def classify_function_by_team(team: object) -> str:
    value = str(team or "").strip()
    low = value.lower()
    if not value:
        return "其他/待分类"
    if any(key in low for key in ["临床", "clinical"]):
        return "临床团队覆盖岗位"
    if any(key in low for key in ["ga", "access", "准入"]):
        return "市场准入团队覆盖岗位"
    if any(key in low for key in ["ma", "m&a", "medical", "医学"]):
        return "MA医学团队覆盖岗位"
    if any(key in low for key in ["销售", "sales"]):
        return "销售团队覆盖岗位"
    if any(key in low for key in ["commercial", "商业"]):
        return "Commercial团队覆盖岗位"
    if any(key in low for key in ["cmc", "注册", "ra", "质量", "qa", "qc"]):
        return "CMC/注册/质量团队覆盖岗位"
    return f"{value}团队覆盖岗位"


class ProjectProgressAnalyzer:
    """Build project-level conversion, stagnation, and timeline facts."""

    def analyze(self, process_df: pd.DataFrame, stale_days: int = 30) -> Dict[str, pd.DataFrame]:
        if process_df is None or process_df.empty or "joborder_id" not in process_df.columns:
            empty = pd.DataFrame()
            return self._empty(empty)

        df = process_df.copy()
        for col in ["resume_sent_date", "first_interview_date", "offer_date", "onboard_date", "actual_payment_date", "job_open_date", "job_close_date", "job_status_update_date"]:
            if col in df.columns:
                df[col] = _safe_date(df[col])
        today = pd.Timestamp.today().normalize()

        rows = []
        for joborder_id, part in df.groupby("joborder_id", dropna=False):
            recommended = int(part["is_recommended"].fillna(False).sum())
            interviews = int(part["is_first_interview"].fillna(False).sum())
            offers = int(part["is_offer"].fillna(False).sum())
            onboards = int(part["is_onboard"].fillna(False).sum())
            paid = int(part["is_paid"].fillna(False).sum())
            first_referral = part["resume_sent_date"].min()
            first_interview = part["first_interview_date"].min()
            first_offer = part["offer_date"].min()
            first_onboard = part["onboard_date"].min()
            last_paid = part["actual_payment_date"].max()
            dated = [x for x in [first_referral, first_interview, first_offer, first_onboard, last_paid] if pd.notna(x)]
            last_activity = max(dated) if dated else pd.NaT
            current_stage = self._current_stage(recommended, interviews, offers, onboards, paid)
            days_since_last = int((today - last_activity.normalize()).days) if pd.notna(last_activity) else None
            is_stalled = bool(days_since_last is not None and days_since_last > stale_days and current_stage not in ["Paid"])
            position = part["position_name"].dropna().iloc[0] if "position_name" in part and part["position_name"].notna().any() else ""
            client = part["client_name"].dropna().iloc[0] if "client_name" in part and part["client_name"].notna().any() else ""
            if "team" in part and part["team"].notna().any():
                team = part["team"].dropna().astype(str).value_counts().idxmax()
            else:
                team = ""
            job_status = part["job_status"].dropna().iloc[0] if "job_status" in part and part["job_status"].notna().any() else ""
            close_reason = part["close_reason"].dropna().iloc[0] if "close_reason" in part and part["close_reason"].notna().any() else ""
            close_note = part["close_note"].dropna().iloc[0] if "close_note" in part and part["close_note"].notna().any() else ""
            function_normal = part["function_normal"].dropna().iloc[0] if "function_normal" in part and part["function_normal"].notna().any() else ""
            job_close_date = part["job_close_date"].dropna().max() if "job_close_date" in part else pd.NaT
            status_update_date = part["job_status_update_date"].dropna().max() if "job_status_update_date" in part else pd.NaT
            outcome_candidates = [x for x in [job_close_date, status_update_date, last_activity] if pd.notna(x)]
            outcome_date = max(outcome_candidates) if outcome_candidates else pd.NaT
            cycle_days = max(0, int((outcome_date.normalize() - first_referral.normalize()).days)) if pd.notna(outcome_date) and pd.notna(first_referral) else None
            is_live = str(job_status).lower() == "live"
            consultants = "、".join(sorted(part["consultant"].dropna().astype(str).unique().tolist())) if "consultant" in part else ""
            function = str(function_normal).strip() if str(function_normal).strip() else classify_function(position)
            if _is_other_function(function):
                function = classify_function_by_team(team)
            category = self._case_category(job_status, current_stage, is_stalled and is_live, cycle_days)
            outcome_category = self._outcome_category(job_status, current_stage)
            diagnosis = self._diagnosis(category, recommended, interviews, offers, onboards, paid, close_reason, days_since_last)
            rows.append(
                {
                    "joborder_id": joborder_id,
                    "client_name": client,
                    "position_name": position,
                    "job_status": job_status,
                    "function": function,
                    "team": team,
                    "consultants": consultants,
                    "job_close_date": job_close_date,
                    "job_status_update_date": status_update_date,
                    "project_cycle_days": cycle_days,
                    "close_reason": close_reason,
                    "close_note": close_note,
                    "referrals": recommended,
                    "first_interviews": interviews,
                    "offers": offers,
                    "onboards": onboards,
                    "paid": paid,
                    "referral_to_interview": _safe_rate(interviews, recommended),
                    "interview_to_offer": _safe_rate(offers, interviews),
                    "offer_to_onboard": _safe_rate(onboards, offers),
                    "onboard_to_paid": _safe_rate(paid, onboards),
                    "first_referral_date": first_referral,
                    "first_interview_date": first_interview,
                    "first_offer_date": first_offer,
                    "first_onboard_date": first_onboard,
                    "last_paid_date": last_paid,
                    "last_activity_date": last_activity,
                    "days_since_last_activity": days_since_last,
                    "current_stage": current_stage,
                    "is_stalled": is_stalled and is_live,
                    "stale_reason": self._stale_reason(current_stage, days_since_last, stale_days) if is_live else "",
                    "case_category": category,
                    "outcome_category": outcome_category,
                    "diagnosis": diagnosis,
                }
            )

        projects = pd.DataFrame(rows)
        if projects.empty:
            empty = pd.DataFrame()
            return self._empty(empty)

        return {
            "projects": projects.sort_values(["is_stalled", "days_since_last_activity"], ascending=[False, False]),
            "by_client": self._group(projects, "client_name"),
            "by_function": self._group(projects, "function"),
            "by_position": self._group(projects, "position_name"),
            "by_case_function": self._case_group(projects, "function"),
            "by_case_client": self._case_group(projects, "client_name"),
            "by_case_consultant": self._consultant_case_group(projects),
            "by_outcome_function": self._outcome_group(projects, "function"),
            "by_outcome_client": self._outcome_group(projects, "client_name"),
            "by_outcome_consultant": self._consultant_outcome_group(projects),
            "gantt": pd.DataFrame(),
            "stalled": projects[projects["is_stalled"]].sort_values("days_since_last_activity", ascending=False),
            "fast_closed_failed": projects[projects["case_category"].eq("快速关闭/失败")].sort_values("project_cycle_days", ascending=True),
            "fast_success": projects[projects["case_category"].eq("快速成功")].sort_values("project_cycle_days", ascending=True),
            "successful_projects": projects[projects["outcome_category"].eq("成功")].sort_values("project_cycle_days", ascending=True),
            "failed_projects": projects[projects["outcome_category"].eq("失败")].sort_values("project_cycle_days", ascending=True),
        }

    @staticmethod
    def _empty(empty: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        return {
            "projects": empty,
            "by_client": empty,
            "by_function": empty,
            "by_position": empty,
            "by_case_function": empty,
            "by_case_client": empty,
            "by_case_consultant": empty,
            "by_outcome_function": empty,
            "by_outcome_client": empty,
            "by_outcome_consultant": empty,
            "gantt": empty,
            "stalled": empty,
            "fast_closed_failed": empty,
            "fast_success": empty,
            "successful_projects": empty,
            "failed_projects": empty,
        }

    @staticmethod
    def _case_category(job_status: str, current_stage: str, is_stalled: bool, cycle_days: int | None) -> str:
        status = str(job_status or "").lower()
        fast = cycle_days is not None and cycle_days <= 90
        if is_stalled:
            return "停滞项目"
        if status in ("failed", "canceled") and fast:
            return "快速关闭/失败"
        if (status == "successful" or current_stage in ("Paid", "Onboard")) and fast:
            return "快速成功"
        if status in ("failed", "canceled"):
            return "慢速关闭/失败"
        if status == "successful" or current_stage in ("Paid", "Onboard"):
            return "成功/已兑现"
        return "正常推进/观察"

    @staticmethod
    def _outcome_category(job_status: str, current_stage: str) -> str:
        status = str(job_status or "").lower()
        if status == "successful" or current_stage in ("Paid", "Onboard"):
            return "成功"
        if status in ("failed", "canceled"):
            return "失败"
        if status == "live":
            return "Live推进"
        return "其他/观察"

    @staticmethod
    def _diagnosis(category: str, referrals: int, interviews: int, offers: int, onboards: int, paid: int, close_reason: str, days_since_last: int | None) -> str:
        if category == "快速成功":
            return "客户反馈、岗位画像和交付节奏较顺，建议复盘客户关系、岗位类型和顾问动作并复制经验。"
        if category == "快速关闭/失败":
            if referrals < 3:
                return f"快速关闭且推荐不足；可能是客户需求变化、岗位吸引力弱或启动后投入不足。关闭原因：{close_reason or '-'}"
            if interviews == 0:
                return f"有推荐但未转面；需复盘简历质量、岗位匹配和客户筛选口径。关闭原因：{close_reason or '-'}"
            if offers == 0:
                return f"进面后未出Offer；需复盘客户反馈、候选人竞争力、薪酬匹配和岗位真实吸引力。关闭原因：{close_reason or '-'}"
            return f"已到Offer/入职前后仍关闭；需复盘turn down、客户预算或组织变化。关闭原因：{close_reason or '-'}"
        if category == "停滞项目":
            if referrals < 3:
                return f"停滞且推荐不足，可能推荐不出人或岗位画像过窄；已{days_since_last or 0}天未推进。"
            if interviews == 0:
                return f"推荐未转面，可能客户反馈慢、简历质量弱或岗位匹配偏差；已{days_since_last or 0}天未推进。"
            if offers == 0:
                return f"面试后无Offer，可能陷入客户反馈/候选人意愿/薪酬匹配僵局；已{days_since_last or 0}天未推进。"
            if offers > 0 and onboards == 0:
                return f"Offer后未入职，需排查turn down、反Offer、背调或入职时间风险；已{days_since_last or 0}天未推进。"
            return f"项目仍Live但长期无新动作，需明确客户反馈、下一步动作和是否继续投入；已{days_since_last or 0}天未推进。"
        return ""

    @staticmethod
    def _current_stage(recommended: int, interviews: int, offers: int, onboards: int, paid: int) -> str:
        if paid > 0:
            return "Paid"
        if onboards > 0:
            return "Onboard"
        if offers > 0:
            return "Offer"
        if interviews > 0:
            return "Interview"
        if recommended > 0:
            return "Referral"
        return "No Activity"

    @staticmethod
    def _stale_reason(stage: str, days_since_last: int | None, stale_days: int) -> str:
        if days_since_last is None or days_since_last <= stale_days or stage == "Paid":
            return ""
        return f"停留在{stage}阶段 {days_since_last} 天未推进"

    @staticmethod
    def _group(projects: pd.DataFrame, key: str) -> pd.DataFrame:
        if key not in projects.columns or projects.empty:
            return pd.DataFrame()
        grouped = (
            projects.groupby(key, dropna=False)
            .agg(
                project_count=("joborder_id", "nunique"),
                stalled_projects=("is_stalled", "sum"),
                live_projects=("job_status", lambda s: int((s.astype(str).str.lower() == "live").sum())),
                referrals=("referrals", "sum"),
                first_interviews=("first_interviews", "sum"),
                offers=("offers", "sum"),
                onboards=("onboards", "sum"),
                paid=("paid", "sum"),
            )
            .reset_index()
        )
        grouped["referral_to_interview"] = grouped["first_interviews"] / grouped["referrals"].replace(0, pd.NA)
        grouped["interview_to_offer"] = grouped["offers"] / grouped["first_interviews"].replace(0, pd.NA)
        grouped["project_to_offer_rate"] = grouped["offers"] / grouped["project_count"].replace(0, pd.NA)
        return grouped.sort_values(["stalled_projects", "referrals"], ascending=[False, False])

    @staticmethod
    def _case_group(projects: pd.DataFrame, key: str) -> pd.DataFrame:
        if key not in projects.columns or projects.empty:
            return pd.DataFrame()
        grouped = (
            projects.groupby([key, "case_category"], dropna=False)
            .agg(
                project_count=("joborder_id", "nunique"),
                avg_cycle_days=("project_cycle_days", "mean"),
                referrals=("referrals", "sum"),
                first_interviews=("first_interviews", "sum"),
                offers=("offers", "sum"),
            )
            .reset_index()
        )
        grouped["referral_to_interview"] = grouped["first_interviews"] / grouped["referrals"].replace(0, pd.NA)
        grouped["interview_to_offer"] = grouped["offers"] / grouped["first_interviews"].replace(0, pd.NA)
        return grouped.sort_values(["case_category", "project_count"], ascending=[True, False])

    @staticmethod
    def _consultant_case_group(projects: pd.DataFrame) -> pd.DataFrame:
        if projects.empty or "consultants" not in projects.columns:
            return pd.DataFrame()
        work = projects.copy()
        work["consultant"] = work["consultants"].fillna("").astype(str).str.split("、")
        work = work.explode("consultant")
        work["consultant"] = work["consultant"].astype(str).str.strip()
        work = work[work["consultant"] != ""]
        if work.empty:
            return pd.DataFrame()
        return ProjectProgressAnalyzer._case_group(work, "consultant")

    @staticmethod
    def _outcome_group(projects: pd.DataFrame, key: str) -> pd.DataFrame:
        if key not in projects.columns or projects.empty:
            return pd.DataFrame()
        grouped = (
            projects.groupby([key, "outcome_category"], dropna=False)
            .agg(
                project_count=("joborder_id", "nunique"),
                avg_cycle_days=("project_cycle_days", "mean"),
                referrals=("referrals", "sum"),
                first_interviews=("first_interviews", "sum"),
                offers=("offers", "sum"),
                onboards=("onboards", "sum"),
                paid=("paid", "sum"),
            )
            .reset_index()
        )
        totals = grouped.groupby(key)["project_count"].sum().rename("total_projects").reset_index()
        success = grouped[grouped["outcome_category"].eq("成功")].groupby(key)["project_count"].sum().rename("successful_projects").reset_index()
        failed = grouped[grouped["outcome_category"].eq("失败")].groupby(key)["project_count"].sum().rename("failed_projects").reset_index()
        grouped = grouped.merge(totals, on=key, how="left").merge(success, on=key, how="left").merge(failed, on=key, how="left")
        grouped["successful_projects"] = grouped["successful_projects"].fillna(0)
        grouped["failed_projects"] = grouped["failed_projects"].fillna(0)
        closed = grouped["successful_projects"] + grouped["failed_projects"]
        grouped["success_rate_closed"] = grouped["successful_projects"] / closed.replace(0, pd.NA)
        grouped["failure_rate_closed"] = grouped["failed_projects"] / closed.replace(0, pd.NA)
        return grouped.sort_values(["total_projects", "project_count"], ascending=[False, False])

    @staticmethod
    def _consultant_outcome_group(projects: pd.DataFrame) -> pd.DataFrame:
        if projects.empty or "consultants" not in projects.columns:
            return pd.DataFrame()
        work = projects.copy()
        work["consultant"] = work["consultants"].fillna("").astype(str).str.split("、")
        work = work.explode("consultant")
        work["consultant"] = work["consultant"].astype(str).str.strip()
        work = work[work["consultant"] != ""]
        if work.empty:
            return pd.DataFrame()
        return ProjectProgressAnalyzer._outcome_group(work, "consultant")

    @staticmethod
    def _gantt(projects: pd.DataFrame) -> pd.DataFrame:
        rows = []
        stage_pairs = [
            ("推荐", "first_referral_date", "first_interview_date"),
            ("一面", "first_interview_date", "first_offer_date"),
            ("Offer", "first_offer_date", "first_onboard_date"),
            ("入职", "first_onboard_date", "last_paid_date"),
        ]
        today = pd.Timestamp.today().normalize()
        for _, row in projects.iterrows():
            label = f"{row.get('client_name', '')} | {row.get('position_name', '')}"
            for stage, start_col, end_col in stage_pairs:
                start = row.get(start_col)
                if pd.isna(start):
                    continue
                end = row.get(end_col)
                if pd.isna(end):
                    end = today
                rows.append(
                    {
                        "project": label[:80],
                        "stage": stage,
                        "start": start,
                        "end": end,
                        "current_stage": row.get("current_stage"),
                        "is_stalled": row.get("is_stalled"),
                        "days_since_last_activity": row.get("days_since_last_activity"),
                    }
                )
        return pd.DataFrame(rows)
