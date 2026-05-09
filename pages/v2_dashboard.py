"""Streamlit pages for the three-speed v2 dashboard."""

from __future__ import annotations

import os
from typing import Dict

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from modules.ai_expert import (
    DEFAULT_BASE_URL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT,
    build_business_context,
    generate_expert_analysis,
)


AI_PROVIDER_PRESETS = {
    "Kimi / Moonshot CN": {
        "base_url": "https://api.moonshot.cn/v1",
        "models": ["kimi-k2.5", "kimi-k2-turbo-preview", "kimi-k2-thinking", "kimi-k2-thinking-turbo"],
        "temperature": 1.0,
    },
    "Kimi / Moonshot Global": {
        "base_url": "https://api.moonshot.ai/v1",
        "models": ["kimi-k2.5", "kimi-k2-turbo-preview", "kimi-k2-thinking", "kimi-k2-thinking-turbo"],
        "temperature": 1.0,
    },
    "OpenAI": {
        "base_url": DEFAULT_BASE_URL,
        "models": [DEFAULT_MODEL, "gpt-4o", "gpt-4.1-mini", "gpt-4.1"],
        "temperature": 1.0,
    },
    "自定义 OpenAI-compatible": {
        "base_url": "",
        "models": ["自定义"],
        "temperature": 1.0,
    },
}


def _secret_lookup(secret_values, names: list[str]) -> tuple[str, str]:
    wanted = {name.strip().lower(): name for name in names}

    def walk(node, path: str = "secrets") -> tuple[str, str]:
        try:
            items = list(node.items())
        except Exception:
            return "", ""
        for key, value in items:
            key_text = str(key).strip()
            next_path = f"{path}.{key_text}"
            if key_text.lower() in wanted and value:
                return str(value).strip(), next_path
            if hasattr(value, "items") or isinstance(value, dict):
                found, source = walk(value, next_path)
                if found:
                    return found, source
        return "", ""

    return walk(secret_values)


def _get_ai_api_key(provider: str, typed_key: str) -> tuple[str, str]:
    typed_key = (typed_key or "").strip()
    if typed_key:
        return typed_key, "page input"

    env_names = ["OPENAI_API_KEY"]
    if provider.startswith("Kimi / Moonshot"):
        env_names = ["MOONSHOT_API_KEY", "KIMI_API_KEY"]

    try:
        secret_values = st.secrets
    except Exception:
        secret_values = {}

    for name in env_names:
        value = os.getenv(name, "")
        if value:
            return value.strip(), f"env:{name}"

    value, source = _secret_lookup(secret_values, env_names)
    if value:
        return value, source

    return "", ""


def _masked_key(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return "-"
    if len(value) <= 10:
        return f"{value[:3]}..."
    return f"{value[:6]}...{value[-4:]}"


def money(value) -> str:
    if value is None or pd.isna(value):
        return "-"
    value = float(value)
    if abs(value) >= 10000:
        return f"¥{value / 10000:,.1f}万"
    return f"¥{value:,.0f}"


def pct(value) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value) * 100:.1f}%"


def safe_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()
    result = df.copy()
    result = result.loc[:, ~result.columns.duplicated()].copy()
    result.columns = [str(col) for col in result.columns]
    return result


LEVEL_COLORS = {
    "强": "#dcfce7",
    "稳": "#e0f2fe",
    "观察": "#fef9c3",
    "待兑现": "#ffedd5",
    "预警": "#fee2e2",
}


def styled_consultant_df(df: pd.DataFrame):
    work = safe_df(df)
    if work.empty:
        return work

    def row_style(row):
        color = LEVEL_COLORS.get(row.get("efficiency_level"), "#ffffff")
        return [f"background-color: {color}" for _ in row]

    money_cols = [
        "monthly_cost",
        "total_collection",
        "period_cost",
        "collection_profit",
        "offer_unpaid_amount",
        "weighted_forecast",
    ]
    month_cols = ["offer_reserve_months", "forecast_cover_months"]
    pct_cols = ["collection_profit_margin", "offer_to_paid_rate", "forecast_cost_cover", "referral_to_interview", "interview_to_offer"]
    fmt = {col: "¥{:,.0f}" for col in money_cols if col in work.columns}
    fmt.update({col: "{:.1f}月" for col in month_cols if col in work.columns})
    fmt.update({col: "{:.1%}" for col in pct_cols if col in work.columns})
    return work.style.apply(row_style, axis=1).format(fmt, na_rep="-")


def render_dashboard(context: Dict[str, object]) -> None:
    conversion = context["conversion"]
    pipeline = context["pipeline"]
    cost = context["cost"]
    cashflow = context["cashflow"]
    health = context["health"]

    st.markdown("### 全景仪表盘")
    st.caption("三大指标：项目推荐效率、顾问成本效率、现金流压力")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("综合健康分", f"{health['overall_score']:.1f}", health["overall_status"])
    c2.metric("项目推荐效率", f"{health['scores']['conversion']:.1f}", conversion["health"]["status"])
    c3.metric("顾问成本效率", f"{health['scores']['cost']:.1f}", cost["data_confidence"])
    c4.metric("现金流压力", f"{health['scores']['cashflow']:.1f}", cashflow["summary"].get("risk_level", "-"))

    render_score_explanation(context)

    left, right = st.columns([1.15, 1])
    with left:
        st.markdown("#### 过去一年转化漏斗")
        funnel = conversion["funnel"]
        if not funnel.empty:
            fig = go.Figure(
                go.Funnel(
                    y=funnel["stage"],
                    x=funnel["count"],
                    textinfo="value+percent initial",
                    marker={"color": ["#2563eb", "#0891b2", "#16a34a", "#f59e0b", "#dc2626"]},
                )
            )
            fig.update_layout(height=360, margin=dict(l=10, r=10, t=20, b=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("暂无过程数据")

    with right:
        st.markdown("#### Pipeline 预测")
        summary = pipeline["summary"]
        st.metric("未来 Pipeline 总额", money(summary.get("forecast_fee", 0)))
        st.metric("加权预测收入", money(summary.get("weighted_revenue", 0)))
        st.metric("平均成功率", pct(summary.get("avg_success_rate", 0)))
        st.caption(f"数据可信度：{pipeline['data_confidence']}")

    st.markdown("#### 关键动作")
    risks = health.get("top_risks", [])
    if not risks:
        st.success("当前未发现高优先级风险。")
    else:
        for risk in risks:
            st.warning(
                f"{risk.get('priority')} | {risk.get('area')}：{risk.get('problem')}\n\n"
                f"证据：{risk.get('evidence', '-')}\n\n"
                f"判断：{risk.get('meaning', '-')}\n\n"
                f"建议：{risk.get('suggestion', '-')}"
            )


def render_management_review(context: Dict[str, object]) -> None:
    st.markdown("### 管理层经营复盘")
    st.caption("按管理层读数习惯组织：整体进展节奏 -> 顾问交付和结果 -> 客户/项目推进流畅度 -> 调整思路。")

    conversion = context.get("conversion", {})
    cost = context.get("cost", {})
    cashflow = context.get("cashflow", {})
    project_progress = context.get("project_progress", {})
    consultant_performance = context.get("consultant_performance", {})
    project_additions = context.get("project_additions", {})

    st.markdown("#### 1. 整体进展节奏")
    rates = conversion.get("stage_rates", {})
    cost_summary = cost.get("summary", {})
    cash_summary = cashflow.get("summary", {})
    projects = project_progress.get("projects", pd.DataFrame()) if isinstance(project_progress, dict) else pd.DataFrame()
    outcome_counts = projects["outcome_category"].value_counts() if isinstance(projects, pd.DataFrame) and not projects.empty and "outcome_category" in projects else pd.Series(dtype=float)
    closed = int(outcome_counts.get("成功", 0) + outcome_counts.get("失败", 0))
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("推荐 -> Offer", pct(rates.get("referral_to_offer")))
    c2.metric("一面 -> Offer", pct(rates.get("interview_to_offer")))
    c3.metric("项目关闭成功率", pct(outcome_counts.get("成功", 0) / closed if closed else None))
    c4.metric("YTD成本收入比", pct(cost_summary.get("cost_revenue_ratio")))
    c5.metric("90天预期现金", money(cash_summary.get("balance_90d", 0)))

    rhythm_rows = [
        {"观察项": "过程节奏", "当前表现": f"推荐到Offer {pct(rates.get('referral_to_offer'))}；一面到Offer {pct(rates.get('interview_to_offer'))}", "管理含义": "业务过程重点看推荐质量、面试后推进和岗位真实吸引力。"},
        {"观察项": "项目结果", "当前表现": f"成功 {int(outcome_counts.get('成功', 0))}；失败 {int(outcome_counts.get('失败', 0))}；Live {int(outcome_counts.get('Live推进', 0))}", "管理含义": "成功/失败用于复盘客户、职能、岗位和顾问的结果质量。"},
        {"观察项": "成本覆盖", "当前表现": f"YTD成本 {money(cost_summary.get('period_cost', 0))}；YTD回款 {money(cost_summary.get('annual_collection', 0))}", "管理含义": "财务结果看累计成本是否被已回款覆盖。"},
        {"观察项": "现金承压", "当前表现": f"节点现金 {money(cash_summary.get('node_cash_balance', 0))}；跑道 {cash_summary.get('cash_runway_months', 0):.1f}月", "管理含义": "现金跑道是静态压力，还要结合确认应收和Forecast兑现节奏。"},
    ]
    st.dataframe(pd.DataFrame(rhythm_rows), use_container_width=True, hide_index=True)

    st.markdown("#### 2. 每个顾问的交付和结果")
    scorecard = consultant_performance.get("scorecard", pd.DataFrame()) if isinstance(consultant_performance, dict) else pd.DataFrame()
    if isinstance(scorecard, pd.DataFrame) and not scorecard.empty:
        cols = [
            "consultant",
            "team",
            "efficiency_level",
            "total_collection",
            "period_cost",
            "collection_profit",
            "offer_reserve_months",
            "forecast_cover_months",
            "referral_to_interview",
            "interview_to_offer",
            "sustainability_profile",
            "risk_flags",
            "management_signal",
        ]
        st.dataframe(styled_consultant_df(scorecard[[c for c in cols if c in scorecard.columns]]), use_container_width=True, hide_index=True)
    else:
        st.info("暂无顾问经营画像数据。")

    st.markdown("#### 3. 客户/项目推进流畅度")
    by_client = project_progress.get("by_outcome_client", pd.DataFrame()) if isinstance(project_progress, dict) else pd.DataFrame()
    by_process_client = project_progress.get("by_client", pd.DataFrame()) if isinstance(project_progress, dict) else pd.DataFrame()
    if isinstance(by_client, pd.DataFrame) and not by_client.empty:
        chart_df = by_client[by_client["outcome_category"].isin(["成功", "失败", "Live推进"])].copy()
        top_clients = chart_df.groupby("client_name")["project_count"].sum().sort_values(ascending=False).head(12).index.tolist()
        chart_df = chart_df[chart_df["client_name"].isin(top_clients)]
        if not chart_df.empty:
            fig = px.bar(
                chart_df,
                x="client_name",
                y="project_count",
                color="outcome_category",
                barmode="stack",
                text="project_count",
                color_discrete_map={"成功": "#16a34a", "失败": "#dc2626", "Live推进": "#2563eb"},
            )
            fig.update_layout(height=380, margin=dict(l=10, r=10, t=20, b=90), xaxis_tickangle=-35)
            st.plotly_chart(fig, use_container_width=True)
    if isinstance(by_process_client, pd.DataFrame) and not by_process_client.empty:
        cols = ["client_name", "project_count", "stalled_projects", "referrals", "first_interviews", "offers", "referral_to_interview", "interview_to_offer", "project_to_offer_rate"]
        st.dataframe(safe_df(by_process_client[[c for c in cols if c in by_process_client.columns]].head(30)), use_container_width=True, hide_index=True)

    st.markdown("#### 4. 下一步调整思路和决策建议")
    issues = pd.DataFrame(_diagnose_issues(conversion, cost, cashflow, project_additions))
    if not issues.empty:
        st.dataframe(safe_df(issues.head(10)), use_container_width=True, hide_index=True)
    actions = pd.DataFrame(_management_actions(conversion, cost, cashflow))
    st.dataframe(safe_df(actions), use_container_width=True, hide_index=True)


def render_score_explanation(context: Dict[str, object]) -> None:
    health = context["health"]
    conversion = context["conversion"]
    cost = context["cost"]
    cashflow = context["cashflow"]

    with st.expander("评分体系说明", expanded=False):
        st.markdown(
            """
            **综合健康分 = 项目推荐效率 35% + 顾问成本效率 30% + 现金流压力 35%**

            等级判断：
            - `80-100`：健康，当前经营状态整体可接受
            - `60-79`：预警，有明显短板，需要管理动作
            - `<60`：危险，建议优先处理关键风险

            具体算法：
            - 项目推荐效率：5 个转化率分别除以健康线，超过健康线按满分计，再取平均。
            - 顾问成本效率：按成本收入比分档，`<=40%` 得 100，`<=60%` 得 80，`<=100%` 得 55，超过 100% 得 30。
            - 现金流压力：从 100 分开始扣分；逾期率超过 20% 开始扣分，现金跑道低于 3 个月继续扣分。
            """
        )
        score_rows = [
            {"指标": "项目推荐效率", "权重": "35%", "当前得分": health["scores"].get("conversion"), "判断依据": _conversion_reason(conversion)},
            {"指标": "顾问成本效率", "权重": "30%", "当前得分": health["scores"].get("cost"), "判断依据": _cost_reason(cost)},
            {"指标": "现金流压力", "权重": "35%", "当前得分": health["scores"].get("cashflow"), "判断依据": _cashflow_reason(cashflow)},
        ]
        st.dataframe(safe_df(pd.DataFrame(score_rows)), use_container_width=True, hide_index=True)


def _conversion_reason(conversion: Dict[str, object]) -> str:
    rates = conversion.get("stage_rates", {})
    if not rates:
        return "暂无过程数据"
    parts = [
        f"推荐到一面 {pct(rates.get('referral_to_interview'))}",
        f"一面到 Offer {pct(rates.get('interview_to_offer'))}",
        f"Offer 到入职 {pct(rates.get('offer_to_onboard'))}",
        f"入职到回款 {pct(rates.get('onboard_to_paid'))}",
        f"整体 {pct(rates.get('overall'))}",
    ]
    bottleneck = conversion.get("health", {}).get("primary_bottleneck")
    if bottleneck:
        parts.append(f"主要短板：{bottleneck}")
    return "；".join(parts)


def _cost_reason(cost: Dict[str, object]) -> str:
    summary = cost.get("summary", {})
    return (
        f"成本收入比 {pct(summary.get('cost_revenue_ratio'))}；"
        f"工资覆盖率 {pct(summary.get('salary_coverage'))}；"
        f"缺薪资人数 {summary.get('missing_salary_count', 0)}"
    )


def _cashflow_reason(cashflow: Dict[str, object]) -> str:
    summary = cashflow.get("summary", {})
    return (
        f"逾期率 {pct(summary.get('overdue_rate'))}；"
        f"逾期金额 {money(summary.get('overdue_amount'))}；"
        f"未来30天到期应收 {money(summary.get('next_30d_pressure'))}；"
        f"节点现金余额 {money(summary.get('node_cash_balance', 0))}；"
        f"现金跑道 {summary.get('cash_runway_months', 0):.1f}月"
    )


def render_conversion(context: Dict[str, object]) -> None:
    st.markdown("### 项目推荐效率")
    st.caption("过程分析仅纳入当前在职顾问；已离职员工不进入转化排行、瓶颈诊断和决策建议。")
    conversion = context["conversion"]
    rates = conversion["stage_rates"]
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("推荐 -> 一面", pct(rates.get("referral_to_interview")))
    c2.metric("一面 -> Offer", pct(rates.get("interview_to_offer")))
    c3.metric(
        "Offer -> 入职(到期)",
        pct(rates.get("offer_to_onboard")),
        f"到期 {int(rates.get('matured_offer_count', 0))} / 待观察 {int(rates.get('pending_onboard_offer_count', 0))}",
        help="Offer入职率使用到期口径：已到预计入职日，或缺少预计入职日但Offer已超过90天的Offer才进入分母；未到预计入职日的Offer进入待观察，不作为失败。",
    )
    c4.metric("入职 -> 回款", pct(rates.get("onboard_to_paid")))
    c5.metric("推荐 -> Offer", pct(rates.get("referral_to_offer")))

    left, right = st.columns([1, 1])
    with left:
        funnel = conversion["funnel"]
        if not funnel.empty:
            st.dataframe(safe_df(funnel), use_container_width=True, hide_index=True)
    with right:
        ranking = conversion["consultant_ranking"]
        if not ranking.empty:
            top = ranking.head(15)
            y_col = "referral_to_offer" if "referral_to_offer" in top.columns else "overall"
            fig = go.Figure(go.Bar(x=top["consultant"], y=top[y_col], marker_color="#2563eb"))
            fig.update_layout(height=360, yaxis_tickformat=".0%", margin=dict(l=10, r=10, t=20, b=80))
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### 顾问转化明细")
    st.dataframe(safe_df(conversion["consultant_ranking"]), use_container_width=True, hide_index=True)
    render_project_progress(context)


def render_project_progress(context: Dict[str, object]) -> None:
    progress = context.get("project_progress", {})
    projects = progress.get("projects", pd.DataFrame()) if isinstance(progress, dict) else pd.DataFrame()
    stalled = progress.get("stalled", pd.DataFrame()) if isinstance(progress, dict) else pd.DataFrame()
    fast_closed = progress.get("fast_closed_failed", pd.DataFrame()) if isinstance(progress, dict) else pd.DataFrame()
    fast_success = progress.get("fast_success", pd.DataFrame()) if isinstance(progress, dict) else pd.DataFrame()
    if projects.empty:
        st.info("暂无项目级推进数据。")
        return

    st.markdown("### 项目推进看板")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("项目数", f"{projects['joborder_id'].nunique()}")
    c2.metric("快速成功", f"{len(fast_success)}")
    c3.metric("快速关闭/失败", f"{len(fast_closed)}")
    c4.metric("Live停滞", f"{len(stalled)}")

    case_tabs = st.tabs(["快速成功", "快速关闭/失败", "停滞项目"])
    case_cols = [
        "client_name",
        "position_name",
        "function",
        "consultants",
        "job_status",
        "project_cycle_days",
        "current_stage",
        "referrals",
        "first_interviews",
        "offers",
        "referral_to_interview",
        "interview_to_offer",
        "close_reason",
        "diagnosis",
    ]
    with case_tabs[0]:
        st.caption("快速成功：90天内进入Successful、Paid或Onboard的项目，用于复盘可复制的客户关系、岗位类型和交付动作。")
        if fast_success.empty:
            st.info("暂无快速成功项目。")
        else:
            st.dataframe(safe_df(fast_success[[c for c in case_cols if c in fast_success.columns]].head(50)), use_container_width=True, hide_index=True)
    with case_tabs[1]:
        st.caption("快速关闭/失败：90天内进入Failed/Canceled的项目，用于识别客户需求变化、岗位质量、推荐不足或面试后无Offer问题。")
        if fast_closed.empty:
            st.info("暂无快速关闭/失败项目。")
        else:
            st.dataframe(safe_df(fast_closed[[c for c in case_cols if c in fast_closed.columns]].head(50)), use_container_width=True, hide_index=True)
    with case_tabs[2]:
        st.caption("停滞项目：当前仍Live，且超过30天没有推荐、面试、Offer、入职或回款动作。")
        stalled_cols = [
            "client_name",
            "position_name",
            "job_status",
            "function",
            "consultants",
            "current_stage",
            "days_since_last_activity",
            "referrals",
            "first_interviews",
            "offers",
            "referral_to_interview",
            "interview_to_offer",
            "stale_reason",
            "diagnosis",
        ]
        if stalled.empty:
            st.success("当前没有超过30天未推进的Live项目。")
        else:
            st.dataframe(safe_df(stalled[[c for c in stalled_cols if c in stalled.columns]].head(50)), use_container_width=True, hide_index=True)

    render_project_outcomes(progress)

    st.markdown("#### 三类项目分布")
    dist_tabs = st.tabs(["按职能", "按客户", "按顾问"])
    dist_specs = [
        ("by_case_function", "function"),
        ("by_case_client", "client_name"),
        ("by_case_consultant", "consultant"),
    ]
    dist_cols = [
        "case_category",
        "project_count",
        "avg_cycle_days",
        "referrals",
        "first_interviews",
        "offers",
        "referral_to_interview",
        "interview_to_offer",
    ]
    for tab, (key, name_col) in zip(dist_tabs, dist_specs):
        with tab:
            df = progress.get(key, pd.DataFrame())
            if df is None or df.empty:
                st.info("暂无数据。")
                continue
            display_cols = [name_col] + [c for c in dist_cols if c in df.columns]
            chart_df = df[df["case_category"].isin(["快速成功", "快速关闭/失败", "停滞项目"])].copy()
            if not chart_df.empty:
                top_names = (
                    chart_df.groupby(name_col)["project_count"]
                    .sum()
                    .sort_values(ascending=False)
                    .head(15)
                    .index
                    .tolist()
                )
                chart_df = chart_df[chart_df[name_col].isin(top_names)]
                fig = px.bar(
                    chart_df,
                    x=name_col,
                    y="project_count",
                    color="case_category",
                    barmode="stack",
                    color_discrete_map={
                        "快速成功": "#16a34a",
                        "快速关闭/失败": "#f97316",
                        "停滞项目": "#dc2626",
                    },
                    hover_data=["avg_cycle_days", "referrals", "first_interviews", "offers", "referral_to_interview", "interview_to_offer"],
                )
                fig.update_layout(height=420, margin=dict(l=10, r=10, t=20, b=90), xaxis_tickangle=-35)
                st.plotly_chart(fig, use_container_width=True)
            st.dataframe(safe_df(df[display_cols].head(80)), use_container_width=True, hide_index=True)

    st.markdown("#### 项目推进转化结构")
    st.caption("该区继续保留所有项目的推荐到面试、面试到Offer、项目到Offer率，用于判断哪些职能/客户/岗位更值得投入。")
    tabs = st.tabs(["职能", "客户", "岗位"])
    group_specs = [
        ("by_function", "function"),
        ("by_client", "client_name"),
        ("by_position", "position_name"),
    ]
    cols = [
        "project_count",
        "live_projects",
        "stalled_projects",
        "referrals",
        "first_interviews",
        "offers",
        "referral_to_interview",
        "interview_to_offer",
        "project_to_offer_rate",
    ]
    for tab, (key, name_col) in zip(tabs, group_specs):
        with tab:
            df = progress.get(key, pd.DataFrame())
            if df is None or df.empty:
                st.info("暂无数据。")
                continue
            display_cols = [name_col] + [c for c in cols if c in df.columns]
            chart_df = df.sort_values("referrals", ascending=False).head(15).copy()
            if not chart_df.empty:
                fig = make_subplots(specs=[[{"secondary_y": True}]])
                fig.add_trace(
                    go.Bar(
                        x=chart_df[name_col],
                        y=chart_df["referrals"],
                        name="推荐",
                        marker_color="#2563eb",
                        text=chart_df["referrals"],
                        textposition="outside",
                    ),
                    secondary_y=False,
                )
                fig.add_trace(
                    go.Bar(
                        x=chart_df[name_col],
                        y=chart_df["first_interviews"],
                        name="一面",
                        marker_color="#0891b2",
                        text=chart_df["first_interviews"],
                        textposition="outside",
                    ),
                    secondary_y=False,
                )
                fig.add_trace(
                    go.Scatter(
                        x=chart_df[name_col],
                        y=chart_df["offers"],
                        name="Offer",
                        mode="lines+markers+text",
                        line={"color": "#16a34a", "width": 3},
                        marker={"size": 9},
                        text=chart_df["offers"],
                        textposition="top center",
                    ),
                    secondary_y=True,
                )
                fig.update_layout(
                    barmode="group",
                    height=460,
                    margin=dict(l=10, r=10, t=20, b=110),
                    xaxis_tickangle=-35,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
                )
                fig.update_yaxes(title_text="推荐 / 一面", secondary_y=False)
                fig.update_yaxes(title_text="Offer", secondary_y=True, rangemode="tozero")
                st.plotly_chart(fig, use_container_width=True)

                heat_cols = ["referral_to_interview", "interview_to_offer", "project_to_offer_rate"]
                heat_existing = [c for c in heat_cols if c in chart_df.columns]
                if heat_existing:
                    heat = chart_df[[name_col] + heat_existing].copy()
                    heat = heat.set_index(name_col)
                    heat = heat.rename(
                        columns={
                            "referral_to_interview": "推荐→一面",
                            "interview_to_offer": "一面→Offer",
                            "project_to_offer_rate": "项目→Offer",
                        }
                    )
                    heat_fig = px.imshow(
                        heat.T,
                        text_auto=".0%",
                        aspect="auto",
                        color_continuous_scale=["#fee2e2", "#fef9c3", "#dcfce7"],
                        zmin=0,
                        zmax=1,
                    )
                    heat_fig.update_layout(height=260, margin=dict(l=10, r=10, t=20, b=90), xaxis_tickangle=-35)
                    st.plotly_chart(heat_fig, use_container_width=True)
            st.dataframe(safe_df(df[display_cols].head(50)), use_container_width=True, hide_index=True)


def render_project_outcomes(progress: Dict[str, object]) -> None:
    projects = progress.get("projects", pd.DataFrame()) if isinstance(progress, dict) else pd.DataFrame()
    if projects.empty or "outcome_category" not in projects.columns:
        return

    st.markdown("#### 项目成功/失败分析")
    st.caption("最终结果维度用于复盘哪些职能、客户、顾问更容易形成成功项目，哪些更容易关闭失败；Live项目单独展示，不混入关闭成功率分母。")
    outcome_counts = projects["outcome_category"].value_counts()
    success_count = int(outcome_counts.get("成功", 0))
    failed_count = int(outcome_counts.get("失败", 0))
    live_count = int(outcome_counts.get("Live推进", 0))
    closed = success_count + failed_count
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("成功项目", f"{success_count}")
    c2.metric("失败项目", f"{failed_count}")
    c3.metric("Live推进", f"{live_count}")
    c4.metric("关闭成功率", pct(success_count / closed if closed else None))

    outcome_tabs = st.tabs(["按职能", "按客户", "按顾问", "成功明细", "失败明细"])
    specs = [
        ("by_outcome_function", "function"),
        ("by_outcome_client", "client_name"),
        ("by_outcome_consultant", "consultant"),
    ]
    for tab, (key, name_col) in zip(outcome_tabs[:3], specs):
        with tab:
            df = progress.get(key, pd.DataFrame())
            if df is None or df.empty:
                st.info("暂无数据。")
                continue
            chart_df = df[df["outcome_category"].isin(["成功", "失败", "Live推进"])].copy()
            if not chart_df.empty:
                top_names = (
                    chart_df.groupby(name_col)["project_count"]
                    .sum()
                    .sort_values(ascending=False)
                    .head(15)
                    .index
                    .tolist()
                )
                chart_df = chart_df[chart_df[name_col].isin(top_names)]
                fig = px.bar(
                    chart_df,
                    x=name_col,
                    y="project_count",
                    color="outcome_category",
                    barmode="stack",
                    text="project_count",
                    color_discrete_map={"成功": "#16a34a", "失败": "#dc2626", "Live推进": "#2563eb"},
                    hover_data=["avg_cycle_days", "referrals", "first_interviews", "offers", "success_rate_closed"],
                )
                fig.update_layout(height=420, margin=dict(l=10, r=10, t=20, b=90), xaxis_tickangle=-35)
                st.plotly_chart(fig, use_container_width=True)
            display_cols = [
                name_col,
                "outcome_category",
                "project_count",
                "total_projects",
                "successful_projects",
                "failed_projects",
                "success_rate_closed",
                "avg_cycle_days",
                "referrals",
                "first_interviews",
                "offers",
            ]
            st.dataframe(safe_df(df[[c for c in display_cols if c in df.columns]].head(100)), use_container_width=True, hide_index=True)

    detail_cols = [
        "client_name",
        "position_name",
        "function",
        "consultants",
        "job_status",
        "project_cycle_days",
        "referrals",
        "first_interviews",
        "offers",
        "onboards",
        "paid",
        "close_reason",
        "diagnosis",
    ]
    with outcome_tabs[3]:
        successful = progress.get("successful_projects", pd.DataFrame())
        if successful is None or successful.empty:
            st.info("暂无成功项目。")
        else:
            st.dataframe(safe_df(successful[[c for c in detail_cols if c in successful.columns]].head(80)), use_container_width=True, hide_index=True)
    with outcome_tabs[4]:
        failed = progress.get("failed_projects", pd.DataFrame())
        if failed is None or failed.empty:
            st.info("暂无失败项目。")
        else:
            st.dataframe(safe_df(failed[[c for c in detail_cols if c in failed.columns]].head(80)), use_container_width=True, hide_index=True)


def render_fiscal_ytd(context: Dict[str, object]) -> None:
    st.markdown("### 本财年业务数据")
    st.caption("截至当前分析结束日：Offer、开票、回款、Forecast。公司层使用单据总额，团队/顾问层使用顾问分摊额。")

    ytd = context.get("ytd", {})
    offer_outcomes = context.get("offer_outcomes", {})
    company = ytd.get("company", pd.DataFrame())
    team = ytd.get("team", pd.DataFrame())
    consultant = ytd.get("consultant", pd.DataFrame())
    outcome_company = offer_outcomes.get("company", pd.DataFrame())
    outcome_team = offer_outcomes.get("team", pd.DataFrame())
    outcome_consultant = offer_outcomes.get("consultant", pd.DataFrame())

    if company.empty:
        st.info("暂无本财年业务数据。")
        return

    metrics = ["Offer", "Invoice", "Collection", "Forecast"]
    cols = st.columns(4)
    for idx, metric in enumerate(metrics):
        row = company[company["metric"] == metric]
        amount = float(row["amount_value"].sum()) if not row.empty else 0.0
        count = int(row["count_value"].sum()) if not row.empty else 0
        cols[idx].metric(metric, money(amount), f"{count} 条")

    st.markdown("#### 公司整体")
    st.dataframe(safe_df(_pivot_metric(company, index_col="name", outcome_df=outcome_company)), use_container_width=True)

    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown("#### By 团队")
        team_pivot = _pivot_metric(team, index_col="team", outcome_df=outcome_team)
        st.dataframe(safe_df(team_pivot), use_container_width=True)
    with c2:
        if not team.empty:
            st.plotly_chart(_metric_bar(team, "team"), use_container_width=True)

    st.markdown("#### By 顾问")
    consultant_pivot = _pivot_metric(consultant, index_col="consultant", outcome_df=outcome_consultant)
    st.dataframe(safe_df(consultant_pivot), use_container_width=True)

    audit = ytd.get("audit", pd.DataFrame())
    stage_audit = ytd.get("stage_audit", pd.DataFrame())
    legacy_audit = ytd.get("legacy_audit", pd.DataFrame())
    joborder_stage_detail = ytd.get("joborder_stage_detail", pd.DataFrame())
    offer_detail = ytd.get("offer_detail", pd.DataFrame())
    with st.expander("数据口径校验、阶段流转与 Offer 原始明细", expanded=False):
        st.caption(
            "Offer / Invoice / Collection 是阶段流转关系：Offer 进入 Invoice 后会从未开票 Offer 库存减少；"
            "Invoice 进入 Collection 后会从未回款 Invoice 库存减少。这里同时展示本期流量、期末库存和历史遗留影响。"
        )
        if isinstance(stage_audit, pd.DataFrame) and not stage_audit.empty:
            st.markdown("##### 阶段流转校验")
            st.dataframe(safe_df(stage_audit), use_container_width=True, hide_index=True)
        if isinstance(legacy_audit, pd.DataFrame) and not legacy_audit.empty:
            st.markdown("##### 25年遗留影响")
            st.dataframe(safe_df(legacy_audit), use_container_width=True, hide_index=True)

        st.markdown("##### Company vs 顾问层分摊校验")
        st.caption("amount_diff 不为 0 时，通常代表未分摊、重复分摊、跨期、税前/税后或 Forecast 分摊口径差异。")
        if isinstance(audit, pd.DataFrame) and not audit.empty:
            st.dataframe(safe_df(audit), use_container_width=True, hide_index=True)
        else:
            st.info("暂无校验数据。")

        if isinstance(joborder_stage_detail, pd.DataFrame) and not joborder_stage_detail.empty:
            detail_cols = [
                "joborder_id",
                "client_name",
                "position_name",
                "consultant",
                "team",
                "stage_status",
                "offer_amount",
                "invoice_amount",
                "payment_received",
                "uninvoiced_offer_amount",
                "unpaid_invoice_amount",
                "over_invoiced_amount",
                "over_collected_amount",
                "first_offer_date",
                "first_invoice_date",
                "latest_payment_date",
            ]
            existing = [col for col in detail_cols if col in joborder_stage_detail.columns]
            st.markdown("##### Job Order 阶段余额明细")
            st.dataframe(safe_df(joborder_stage_detail[existing]), use_container_width=True, hide_index=True)

        if isinstance(offer_detail, pd.DataFrame) and not offer_detail.empty:
            detail_cols = [
                "offer_id",
                "sign_date",
                "consultant",
                "team",
                "client_name",
                "position_name",
                "offer_amount",
                "offer_status",
                "jobsubmission_id",
                "joborder_id",
                "date_added",
            ]
            existing = [col for col in detail_cols if col in offer_detail.columns]
            st.markdown("##### Offer 原始明细")
            st.dataframe(safe_df(offer_detail[existing]), use_container_width=True, hide_index=True)
        else:
            st.info("暂无 Offer 原始明细。")


def _pivot_metric(df: pd.DataFrame, index_col: str, outcome_df: pd.DataFrame = None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    pivot_amount = df.pivot_table(index=index_col, columns="metric", values="amount_value", aggfunc="sum", fill_value=0)
    pivot_count = df.pivot_table(index=index_col, columns="metric", values="count_value", aggfunc="sum", fill_value=0)
    result = pd.DataFrame(index=pivot_amount.index)
    for metric in ["Offer", "Invoice", "Collection", "Forecast"]:
        result[f"{metric}金额"] = pivot_amount[metric] if metric in pivot_amount.columns else 0
        result[f"{metric}数量"] = (pivot_count[metric] if metric in pivot_count.columns else 0).astype(int) if metric in pivot_count.columns else 0
    result = result.reset_index()
    if outcome_df is not None and isinstance(outcome_df, pd.DataFrame) and not outcome_df.empty:
        outcome_cols = [
            index_col,
            "matured_offer_count",
            "pending_onboard_count",
            "offer_to_onboard_rate",
            "offer_to_paid_rate",
            "paid_offer_count",
            "paid_amount",
        ]
        existing = [c for c in outcome_cols if c in outcome_df.columns]
        if index_col in existing:
            result = result.merge(outcome_df[existing], on=index_col, how="left")
    rename_map = {
        "matured_offer_count": "已到入职观察期Offer数",
        "pending_onboard_count": "待入职观察Offer数",
        "offer_to_onboard_rate": "Offer入职率",
        "offer_to_paid_rate": "Offer回款转化率",
        "paid_offer_count": "已回款Offer数",
        "paid_amount": "Offer后回款金额",
    }
    result = result.rename(columns=rename_map)
    return result.sort_values("Collection金额", ascending=False)


def _metric_bar(df: pd.DataFrame, group_col: str):
    plot_df = df[df["metric"].isin(["Offer", "Invoice", "Collection", "Forecast"])].copy()
    fig = go.Figure()
    for metric, color in [("Offer", "#2563eb"), ("Invoice", "#0891b2"), ("Collection", "#16a34a"), ("Forecast", "#f59e0b")]:
        part = plot_df[plot_df["metric"] == metric]
        fig.add_trace(go.Bar(x=part[group_col], y=part["amount_value"], name=metric, marker_color=color))
    fig.update_layout(barmode="group", height=420, margin=dict(l=10, r=10, t=20, b=80))
    return fig


def render_cost_efficiency(context: Dict[str, object]) -> None:
    st.markdown("### 顾问成本效率")
    cost = context["cost"]
    summary = cost["summary"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("在职顾问", f"{summary.get('active_consultants', 0)}")
    c2.metric("月成本", money(summary.get("monthly_cost", 0)))
    c3.metric("公司本年回款(YTD)", money(summary.get("annual_collection", 0)))
    c4.metric("YTD成本收入比", pct(summary.get("cost_revenue_ratio")))
    st.caption(
        f"成本数据可信度：{cost['data_confidence']} | YTD成本：{money(summary.get('period_cost', 0))} "
        f"({summary.get('months_elapsed', 0)}个月；在职{money(summary.get('active_period_cost', 0))}"
        f" + 离职{money(summary.get('departed_period_cost', 0))}/2倍) | 工资覆盖率：{pct(summary.get('salary_coverage', 0))} "
        f"| 缺薪资人数：{summary.get('missing_salary_count', 0)} "
        f"| 离职/未匹配回款：{money(summary.get('departed_or_unmatched_collection', 0))} "
        f"| 离职成本计入人数：{summary.get('departed_costed_count', 0)} "
        f"| 离职缺薪资：{summary.get('departed_missing_salary_count', 0)}"
    )

    ranking = cost["ranking"]
    if ranking.empty:
        st.info("暂无顾问成本数据。请上传工资表或检查顾问数据。")
        render_project_additions(context)
        return

    render_consultant_performance(context)

    display_cols = [
        "consultant",
        "team",
        "base_salary",
        "monthly_cost",
        "total_collection",
        "monthly_collection",
        "cost_revenue_ratio",
        "efficiency_rating",
        "cost_source",
    ]
    existing = [c for c in display_cols if c in ranking.columns]
    st.info("运营团队、Sys、CSM 等账号已从顾问分析中排除；离职员工不进入顾问排名，其回款只计入公司本年回款。")
    st.dataframe(safe_df(ranking[existing]), use_container_width=True, hide_index=True)
    render_project_additions(context)


def render_consultant_performance(context: Dict[str, object]) -> None:
    st.markdown("### 顾问经营画像")
    performance = context.get("consultant_performance", {})
    scorecard = performance.get("scorecard", pd.DataFrame()) if isinstance(performance, dict) else pd.DataFrame()
    if scorecard is None or scorecard.empty:
        st.info("暂无顾问经营画像数据。")
        return

    st.caption(performance.get("definition", ""))
    with st.expander("状态判定说明", expanded=False):
        st.markdown(
            """
            - `Growth / Near Target`：本财年已回款 >= 30万，且当前Offer未回款 >= 30万。代表业绩兑现和短期余粮都较强，重点跟进入职、开票和回款。
            - `Score Inflated / PIP Review`：综合分 >= 65，但当前Offer未回款 < 10万或Offer数量 <= 1，同时一面到Offer转化 < 12%。代表分数可能被低成本、历史回款或Forecast抬高，实际产能和交付质量需要复核。
            - `Performance Watch`：加权Pipeline < 5万，且一面到Offer转化 < 15%。代表未来产能和面试后转化都偏弱，建议进入业绩观察。
            - `High Potential`：综合分 >= 75，且没有触发上述风险规则。
            - `Stable`：综合分 60-74，且没有触发上述风险规则。
            - `Watch`：综合分 45-59。
            - `Restructure`：综合分 < 45。
            """
        )
    top = scorecard.sort_values("consultant_score", ascending=False).head(5)
    watch = scorecard.sort_values("consultant_score", ascending=True).head(5)

    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown("#### 综合得分 Top 5")
        st.dataframe(
            safe_df(
                top[
                    [
                        "consultant",
                        "team",
                        "consultant_score",
                        "consultant_status",
                        "total_collection",
                        "offer_unpaid_amount",
                        "weighted_forecast",
                        "process_score",
                    ]
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
    with c2:
        st.markdown("#### 需要管理关注")
        st.dataframe(
            safe_df(
                watch[
                    [
                        "consultant",
                        "team",
                        "consultant_score",
                        "consultant_status",
                        "past_score",
                        "offer_reserve_score",
                        "future_score",
                        "process_score",
                        "risk_flags",
                        "management_signal",
                    ]
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )

    display_cols = [
        "consultant",
        "team",
        "consultant_score",
        "consultant_status",
        "total_collection",
        "past_cost_cover",
        "offer_unpaid_amount",
        "offer_to_paid_rate",
        "weighted_forecast",
        "forecast_cost_cover",
        "referrals",
        "referral_to_interview",
        "interview_to_offer",
        "process_score",
        "risk_flags",
        "management_signal",
    ]
    existing = [c for c in display_cols if c in scorecard.columns]
    st.markdown("#### 顾问360明细")
    st.dataframe(safe_df(scorecard[existing]), use_container_width=True, hide_index=True)


def render_consultant_performance(context: Dict[str, object]) -> None:
    st.markdown("### 顾问经营画像")
    performance = context.get("consultant_performance", {})
    scorecard = performance.get("scorecard", pd.DataFrame()) if isinstance(performance, dict) else pd.DataFrame()
    if scorecard is None or scorecard.empty:
        st.info("暂无顾问经营画像数据。")
        return

    st.caption("不做单一综合打分；用经营事实判断顾问业绩可持续性：已回款利润、Offer余粮月份、Forecast覆盖月份和过程转化。")
    with st.expander("指标口径说明", expanded=False):
        st.markdown(
            """
            - 已回款利润 = 本财年已回款 - 截至当前实际月份累计月成本。
            - 已回款利润率 = 已回款利润 / 本财年已回款。
            - Offer余粮月份 = 当前Offer未回款金额 / 顾问月成本。
            - Forecast覆盖月份 = Forecast加权预测金额 / 顾问月成本。
            - Forecast覆盖率 = Forecast加权预测金额 / 预测窗口内累计月成本。
            - 过程转化只作为风险提示，不再折算为综合分。
            """
        )

    level_counts = scorecard.get("efficiency_level", pd.Series(dtype=object)).value_counts().to_dict()
    cols = st.columns(5)
    for idx, level in enumerate(["强", "稳", "观察", "待兑现", "预警"]):
        cols[idx].metric(level, int(level_counts.get(level, 0)))

    profit_leaders = scorecard.sort_values("collection_profit", ascending=False).head(5)
    weak_sustainability = scorecard.sort_values(["offer_reserve_months", "forecast_cover_months"], ascending=[True, True]).head(5)

    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown("#### 已回款利润 Top 5")
        cols = [
            "consultant",
            "team",
            "efficiency_level",
            "total_collection",
            "period_cost",
            "collection_profit",
            "collection_profit_margin",
            "offer_reserve_months",
            "forecast_cover_months",
        ]
        st.dataframe(styled_consultant_df(profit_leaders[[c for c in cols if c in profit_leaders.columns]]), use_container_width=True, hide_index=True)
    with c2:
        st.markdown("#### 可持续性风险")
        cols = [
            "consultant",
            "team",
            "efficiency_level",
            "sustainability_profile",
            "offer_unpaid_amount",
            "offer_reserve_months",
            "weighted_forecast",
            "forecast_cover_months",
            "risk_flags",
            "management_signal",
        ]
        st.dataframe(styled_consultant_df(weak_sustainability[[c for c in cols if c in weak_sustainability.columns]]), use_container_width=True, hide_index=True)

    display_cols = [
        "consultant",
        "team",
        "efficiency_level",
        "monthly_cost",
        "total_collection",
        "period_cost",
        "collection_profit",
        "collection_profit_margin",
        "offer_count",
        "offer_unpaid_amount",
        "offer_reserve_months",
        "offer_to_paid_rate",
        "weighted_forecast",
        "forecast_cover_months",
        "forecast_cost_cover",
        "referrals",
        "referral_to_interview",
        "interview_to_offer",
        "sustainability_profile",
        "risk_flags",
        "management_signal",
    ]
    existing = [c for c in display_cols if c in scorecard.columns]
    st.markdown("#### 顾问经营明细")
    st.dataframe(styled_consultant_df(scorecard[existing]), use_container_width=True, hide_index=True)


def render_project_additions(context: Dict[str, object]) -> None:
    st.markdown("### 项目新增月度监测")
    st.caption("该板块先作为过程观察指标，不计入当前综合评分；团队和顾问维度已排除运营、Sys、CSM 等非顾问账号。")

    project_additions = context.get("project_additions", {})
    company = project_additions.get("company", pd.DataFrame())
    monthly = project_additions.get("monthly", pd.DataFrame())
    team = project_additions.get("team", pd.DataFrame())
    consultant = project_additions.get("consultant", pd.DataFrame())

    if not isinstance(company, pd.DataFrame) or company.empty:
        st.info("暂无本财年新增项目数据。")
        return

    row = company.iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("本财年新增项目", f"{int(row.get('new_projects', 0))}")
    c2.metric("当前 Live 项目", f"{int(row.get('live_projects', 0))}")
    c3.metric("已产生 Offer 项目", f"{int(row.get('offer_projects', 0))}")
    c4.metric("项目到 Offer", pct(row.get("project_to_offer_rate")))

    if isinstance(monthly, pd.DataFrame) and not monthly.empty:
        st.markdown("#### 月度趋势")
        monthly_plot = monthly.sort_values("month")
        fig = go.Figure()
        fig.add_trace(go.Bar(x=monthly_plot["month"], y=monthly_plot["new_projects"], name="新增项目", marker_color="#2563eb"))
        fig.add_trace(go.Scatter(x=monthly_plot["month"], y=monthly_plot["offer_projects"], name="产生 Offer 项目", mode="lines+markers", line={"color": "#16a34a"}))
        fig.update_layout(height=360, margin=dict(l=10, r=10, t=20, b=50))
        st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown("#### By 团队")
        st.dataframe(safe_df(_project_addition_display(team, "team")), use_container_width=True, hide_index=True)
    with c2:
        if isinstance(team, pd.DataFrame) and not team.empty:
            top_team = team.sort_values("new_projects", ascending=False).head(12)
            fig = go.Figure(go.Bar(x=top_team["team"], y=top_team["new_projects"], marker_color="#0891b2"))
            fig.update_layout(height=360, margin=dict(l=10, r=10, t=20, b=80))
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### By 顾问")
    st.dataframe(safe_df(_project_addition_display(consultant, "consultant")), use_container_width=True, hide_index=True)


def _project_addition_display(df: pd.DataFrame, name_col: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    display_cols = [name_col, "team", "new_projects", "matured_projects", "pending_project_count", "live_projects", "offer_projects", "offer_count", "offer_amount", "project_to_offer_rate"]
    existing = []
    for col in display_cols:
        if col in df.columns and col not in existing:
            existing.append(col)
    result = safe_df(df[existing].copy())
    if "project_to_offer_rate" in result.columns:
        result["project_to_offer_rate"] = result["project_to_offer_rate"].apply(pct)
    return result.sort_values("new_projects", ascending=False) if "new_projects" in result.columns else result


def render_cashflow(context: Dict[str, object]) -> None:
    st.markdown("### 现金流压力")
    cashflow = context["cashflow"]
    summary = cashflow["summary"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("节点现金余额", money(summary.get("node_cash_balance", 0)))
    c2.metric("现金跑道", f"{summary.get('cash_runway_months', 0):.1f}月")
    c3.metric("逾期金额", money(summary.get("overdue_amount", 0)))
    c4.metric("未来30天到期应收", money(summary.get("next_30d_pressure", 0)))
    st.caption(
        f"现金流数据可信度：{cashflow['data_confidence']} | "
        f"节点现金余额 = 年初现金余额({money(summary.get('initial_cash', 0))}) "
        f"+ 本年已回款({money(summary.get('ytd_collection', 0))}) "
        f"- 本年累计月成本({money(summary.get('ytd_cost', 0))}，{summary.get('months_elapsed', 0):.2f}个月，次月{summary.get('payroll_day', 5)}日发薪口径)；"
        f"跑道 = 节点现金余额 / 顾问月成本({money(summary.get('cash_runway_cost_base', 0))})"
    )
    st.caption(
        f"2025遗留应收：{money(summary.get('legacy_pending_amount', 0))}；"
        f"2025遗留逾期：{money(summary.get('legacy_overdue_amount', 0))}；"
        f"2025严重遗留逾期(>=60天)：{summary.get('severe_legacy_overdue_count', 0)}笔 / {money(summary.get('severe_legacy_overdue_amount', 0))}"
    )

    st.markdown("#### 预测现金余额")
    p1, p2 = st.columns(2)
    p1.metric(
        "90天预期现金余额",
        money(summary.get("balance_90d", 0)),
        f"流入 {money(summary.get('inflow_90d', 0))} / 成本 {money(summary.get('outflow_90d', 0))}",
    )
    p2.metric(
        "180天预期现金余额",
        money(summary.get("balance_180d", 0)),
        f"流入 {money(summary.get('inflow_180d', 0))} / 成本 {money(summary.get('outflow_180d', 0))}",
    )
    st.caption(
        "预测公式：预期现金余额 = 节点现金余额 + 已开票/到期应收 + Forecast加权预测回款 - 截至预测日期产生的顾问成本。"
        f"90天流入拆分：确认应收 {money(summary.get('confirmed_inflow_90d', 0))}，Forecast {money(summary.get('forecast_inflow_90d', 0))}；"
        f"180天流入拆分：确认应收 {money(summary.get('confirmed_inflow_180d', 0))}，Forecast {money(summary.get('forecast_inflow_180d', 0))}。"
    )

    cal = cashflow["calendar"]
    if not cal.empty:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=cal["date"], y=cal["balance"], mode="lines", name="预期现金余额"))
        fig.add_trace(go.Bar(x=cal["date"], y=cal["confirmed_inflow"], name="确认应收流入", marker_color="#16a34a"))
        fig.add_trace(go.Bar(x=cal["date"], y=cal["forecast_inflow"], name="Forecast预测流入", marker_color="#f59e0b"))
        fig.update_layout(height=380, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### 逾期订单")
    overdue = cashflow["overdue_orders"]
    if overdue.empty:
        st.success("暂无逾期订单。")
    else:
        st.dataframe(safe_df(overdue), use_container_width=True, hide_index=True)

    st.markdown("#### 2025遗留应收")
    legacy = cashflow.get("legacy_orders", pd.DataFrame())
    if legacy.empty:
        st.success("暂无2025遗留应收。")
    else:
        cols = [
            "invoice_id",
            "client_name",
            "status",
            "pending_amount",
            "source_date",
            "due_date",
            "due_date_source",
            "is_overdue",
            "overdue_days",
            "invoice_amount",
            "payment_received",
        ]
        existing = [c for c in cols if c in legacy.columns]
        st.caption("遗留应收口径：发票发送日/录入日在2025年，且当前仍有未回款余额或处于已发送/已录入状态；2017-2024历史问题不纳入当前经营判断。")
        st.dataframe(safe_df(legacy[existing]), use_container_width=True, hide_index=True)

    st.markdown("#### 未来30天到期应收")
    next_30 = cashflow.get("next_30_orders", pd.DataFrame())
    if next_30.empty:
        st.success("未来30天暂无到期应收。")
    else:
        cols = [
            "invoice_id",
            "client_name",
            "status",
            "pending_amount",
            "due_date",
            "due_date_source",
            "invoice_amount",
            "payment_received",
        ]
        existing = [c for c in cols if c in next_30.columns]
        st.caption("说明：该金额是未来30天到期但尚未回款的应收款，不是未来30天现金支出；若 due_date_source 为 invoice_added_plus_35_days，表示因缺少明确预计付款日而按录入日+35天估算。")
        st.dataframe(safe_df(next_30[existing]), use_container_width=True, hide_index=True)

    st.markdown("#### 客户回款风险画像")
    st.dataframe(safe_df(cashflow["client_risk"]), use_container_width=True, hide_index=True)

    st.markdown("#### 客户合同账期 vs 真实平均账期")
    terms = cashflow.get("client_payment_terms", pd.DataFrame())
    if terms.empty:
        st.info("暂无可计算账期的数据。需要发票日期、合同账期和实际回款日期。")
    else:
        display_cols = [
            "client_name",
            "invoice_count",
            "contract_payment_days",
            "contract_day_values",
            "paid_invoice_count",
            "actual_avg_days",
            "actual_median_days",
            "terms_gap_days",
            "payment_behavior",
            "open_invoice_count",
            "pending_amount",
            "overdue_count",
            "max_overdue_days",
        ]
        existing = [col for col in display_cols if col in terms.columns]
        st.caption("合同账期取客户合同/发票中的 payment_days 有效值，不做平均；真实账期 = 实际回款日期 - 发票发送日；账期差 = 真实平均账期 - 合同账期。")
        st.dataframe(safe_df(terms[existing]), use_container_width=True, hide_index=True)


def render_recommendations(context: Dict[str, object]) -> None:
    st.markdown("### 经营诊断与决策建议")
    conversion = context["conversion"]
    cost = context["cost"]
    cashflow = context["cashflow"]
    project_additions = context.get("project_additions", {})

    st.caption(
        "诊断逻辑：用项目推进效率判断增长质量，用顾问成本判断产能杠杆，用现金流判断风险承受能力；"
        "再结合医药行业岗位减少、交付难度上升、费率收缩和 AI 降本趋势，给出经营动作。"
    )

    st.markdown("#### 当前经营结论")
    for item in _strategic_summary(conversion, cost, cashflow, project_additions):
        if item["level"] == "High":
            st.error(item["message"])
        elif item["level"] == "Medium":
            st.warning(item["message"])
        else:
            st.info(item["message"])

    st.markdown("#### 关键问题源")
    issue_df = pd.DataFrame(_diagnose_issues(conversion, cost, cashflow, project_additions))
    if issue_df.empty:
        st.success("当前三速模型没有发现需要立即处理的关键问题源。")
    else:
        st.dataframe(safe_df(issue_df), use_container_width=True, hide_index=True)

    st.markdown("#### 管理动作建议")
    st.dataframe(safe_df(pd.DataFrame(_management_actions(conversion, cost, cashflow))), use_container_width=True, hide_index=True)

    st.markdown("#### 90 天经营重点")
    st.dataframe(safe_df(pd.DataFrame(_ninety_day_plan())), use_container_width=True, hide_index=True)

    _render_ai_expert(context, issue_df.to_dict(orient="records") if not issue_df.empty else [])

    with st.expander("行业背景与管理假设", expanded=False):
        st.markdown(
            """
            - 外部市场假设：医药与生物技术招聘从 2023-2025 的扩张后回撤进入更谨慎周期，2026 有企稳迹象，但客户更关注确定性岗位、关键岗位和现金效率。
            - 对猎头公司的含义：不能再用“广撒项目 + 高人力投入”覆盖低转化，必须用客户分层、岗位分层、顾问产能分层来保护利润率。
            - 对 15 年医药行业积累的使用方式：把存量客户和候选人知识库产品化，优先沉淀到 AI 寻访、岗位画像、候选人匹配、客户风险识别。
            - 当前转型原则：低产出职能收缩，利润板块聚焦，现金回款优先，AI 先服务于重复寻访、名单生成、岗位理解和顾问训练，而不是替代高价值顾问判断。
            """
        )


def _render_ai_expert(context: Dict[str, object], issues: list) -> None:
    st.markdown("#### AI 经营专家")
    st.caption("模型只分析本页已结构化的经营事实，不直接查询数据库，也不改变三速评分。")
    with st.expander("模型配置", expanded=False):
        provider_names = list(AI_PROVIDER_PRESETS.keys())
        provider = st.selectbox(
            "服务商",
            provider_names,
            index=provider_names.index(st.session_state.get("ai_expert_provider", "Kimi / Moonshot CN"))
            if st.session_state.get("ai_expert_provider", "Kimi / Moonshot CN") in provider_names
            else 0,
        )
        preset = AI_PROVIDER_PRESETS[provider]
        model_options = preset["models"] + (["自定义"] if "自定义" not in preset["models"] else [])
        saved_model = st.session_state.get("ai_expert_model", preset["models"][0])
        model_index = model_options.index(saved_model) if saved_model in model_options else 0

        col1, col2 = st.columns([1, 1])
        with col1:
            base_default = preset["base_url"] or st.session_state.get("ai_expert_base_url", os.getenv("OPENAI_BASE_URL", DEFAULT_BASE_URL))
            base_url = st.text_input("Base URL", value=base_default)
        with col2:
            selected_model = st.selectbox("Model", model_options, index=model_index)
            if selected_model == "自定义":
                model = st.text_input("自定义 Model", value=st.session_state.get("ai_expert_custom_model", ""))
            else:
                model = selected_model
        temperature = st.number_input(
            "Temperature",
            min_value=0.0,
            max_value=2.0,
            value=float(st.session_state.get("ai_expert_temperature", preset["temperature"])),
            step=0.1,
            help="Kimi 部分模型只允许 1.0；如报 temperature 错误，请保持 1.0。",
        )
        analysis_mode = st.selectbox(
            "分析模式",
            ["快速", "深度"],
            index=0,
            help="快速模式只传核心指标和少量问题源，更适合 Kimi 防超时；深度模式会传更多明细。",
        )
        max_tokens = st.number_input(
            "Max tokens",
            min_value=800,
            max_value=8000,
            value=int(DEFAULT_MAX_TOKENS),
            step=200,
            help="输出越长越容易超时。Kimi 建议先用 1200-1800。",
        )
        timeout = st.number_input(
            "Timeout seconds",
            min_value=30,
            max_value=600,
            value=int(DEFAULT_TIMEOUT),
            step=30,
            help="Kimi 分析长上下文时可能较慢，建议 180-300 秒。",
        )
        api_key = st.text_input("API Key", value="", type="password", help="也可以设置环境变量 OPENAI_API_KEY。页面不会保存该密钥。")

    st.session_state["ai_expert_provider"] = provider
    st.session_state["ai_expert_base_url"] = base_url
    st.session_state["ai_expert_model"] = model
    if selected_model == "自定义":
        st.session_state["ai_expert_custom_model"] = model
    st.session_state["ai_expert_temperature"] = temperature
    st.session_state["ai_expert_analysis_mode"] = analysis_mode
    st.session_state["ai_expert_max_tokens"] = max_tokens
    st.session_state["ai_expert_timeout"] = timeout
    generate = st.button("生成专家分析", use_container_width=False)
    if generate:
        key, key_source = _get_ai_api_key(provider, api_key)
        st.caption(
            f"AI request: provider={provider} | base_url={base_url} | model={model} "
            f"| key_source={key_source or '-'} | key={_masked_key(key)}"
        )
        if not key:
            st.warning("请填写 API Key，或先设置 OPENAI_API_KEY 环境变量。")
            return
        try:
            business_context = build_business_context(context, issues, mode="fast" if analysis_mode == "快速" else "deep")
            with st.spinner("AI 经营专家正在分析三速模型和问题源..."):
                st.session_state["ai_expert_result"] = generate_expert_analysis(
                    business_context,
                    api_key=key,
                    model=model,
                    base_url=base_url,
                    temperature=temperature,
                    max_tokens=int(max_tokens),
                    timeout=int(timeout),
                )
        except Exception as exc:
            st.error(f"AI 专家分析生成失败：{exc}")
            return

    result = st.session_state.get("ai_expert_result")
    if result:
        st.markdown(result)
    else:
        st.info("填写模型配置后点击“生成专家分析”，这里会输出面向管理层的经营诊断报告。")


def _strategic_summary(conversion, cost, cashflow, project_additions) -> list:
    rates = conversion.get("stage_rates", {})
    cost_summary = cost.get("summary", {})
    cash_summary = cashflow.get("summary", {})
    company_projects = project_additions.get("company", pd.DataFrame()) if isinstance(project_additions, dict) else pd.DataFrame()
    project_rate = None
    new_projects = 0
    if isinstance(company_projects, pd.DataFrame) and not company_projects.empty:
        row = company_projects.iloc[0]
        project_rate = row.get("project_to_offer_rate")
        new_projects = int(row.get("new_projects", 0))

    result = []
    cost_ratio = cost_summary.get("cost_revenue_ratio")
    overdue_rate = cash_summary.get("overdue_rate", 0)
    overall = rates.get("referral_to_offer", 0)
    interview_to_offer = rates.get("interview_to_offer", 0)

    if cost_ratio and cost_ratio > 0.60 and overall < 0.08:
        result.append({"level": "High", "message": f"经营主矛盾是业务交付转化不足但人力成本偏重：整体推荐到 Offer {pct(overall)}，成本收入比 {pct(cost_ratio)}。业务侧优先提升推荐质量和面试后推进，财务侧单独盯回款兑现。"})
    if False and cost_ratio and cost_ratio > 0.60 and overall < 0.08:
        result.append({"level": "High", "message": f"经营主矛盾是交付转化不足但人力成本偏重：整体推荐到回款 {pct(overall)}，成本收入比 {pct(cost_ratio)}。应优先收缩低转化项目和低产出顾问投入。"})
    if overdue_rate >= 0.20:
        level = "High" if overdue_rate >= 0.30 else "Medium"
        result.append({"level": level, "message": f"现金流压力来自回款质量：逾期率 {pct(overdue_rate)}，逾期金额 {money(cash_summary.get('overdue_amount', 0))}。短期经营动作应优先围绕应收回款。"})
    if project_rate is not None and project_rate < 0.10 and new_projects >= 20:
        result.append({"level": "Medium", "message": f"新增项目数量不低，但项目到 Offer 只有 {pct(project_rate)}。需要复盘新增项目质量、岗位选择或推进速度。"})
    if interview_to_offer < 0.50:
        result.append({"level": "Medium", "message": f"面试到 Offer 转化 {pct(interview_to_offer)} 低于健康线，问题可能在候选人匹配质量、客户决策速度或顾问推进能力。"})
    if not result:
        result.append({"level": "Low", "message": "当前没有单一指标失控，建议继续按客户质量、岗位利润和顾问产能做结构优化。"})
    return result


def _diagnose_issues(conversion, cost, cashflow, project_additions) -> list:
    issues = []
    issues.extend(_conversion_issues(conversion))
    issues.extend(_cost_issues(cost))
    issues.extend(_cashflow_issues(cashflow))
    issues.extend(_project_addition_issues(project_additions))
    priority_order = {"High": 0, "Medium": 1, "Low": 2}
    return sorted(_dedupe_issues(issues), key=lambda x: priority_order.get(x.get("优先级"), 9))


def _dedupe_issues(issues: list) -> list:
    priority_order = {"High": 0, "Medium": 1, "Low": 2}
    merged = {}
    for issue in issues:
        key = (issue.get("维度"), issue.get("问题源"))
        if key not in merged:
            merged[key] = issue
            continue
        current = merged[key]
        if priority_order.get(issue.get("优先级"), 9) < priority_order.get(current.get("优先级"), 9):
            current["优先级"] = issue.get("优先级")
        current["证据"] = "；".join([x for x in [current.get("证据"), issue.get("证据")] if x])
        current["判断"] = "；".join(dict.fromkeys([x for x in [current.get("判断"), issue.get("判断")] if x]))
        current["建议"] = "；".join(dict.fromkeys([x for x in [current.get("建议"), issue.get("建议")] if x]))
    return list(merged.values())


def _conversion_issues(conversion) -> list:
    ranking = conversion.get("consultant_ranking", pd.DataFrame())
    issues = []
    if ranking is None or ranking.empty:
        return issues
    work = ranking.copy()
    work["referrals"] = pd.to_numeric(work.get("referrals"), errors="coerce").fillna(0)
    if "paid" in work.columns:
        work["paid"] = pd.to_numeric(work.get("paid"), errors="coerce").fillna(0)
    high_result_names = set(work[work.get("paid", 0) >= 3]["consultant"].dropna().astype(str).tolist()) if "paid" in work.columns else set()
    active = work[work["referrals"] >= 10].copy()
    if active.empty:
        return issues

    for _, row in active.sort_values("referrals", ascending=True).head(3).iterrows():
        if row["referrals"] < 20:
            issues.append({"优先级": "Medium", "维度": "项目推进效率", "问题源": row.get("consultant"), "证据": f"推荐量 {int(row.get('referrals', 0))}，整体转化 {pct(row.get('overall'))}", "判断": "顾问活跃项目推进或候选人触达不足，可能拖慢职位响应速度。", "建议": "检查其负责项目数量、每日触达量、候选人名单质量；用 AI 先生成长名单和候选人相似画像。"})

    for _, row in active[active["referral_to_interview"] < 0.30].sort_values("referral_to_interview").head(3).iterrows():
        priority = "Medium" if str(row.get("consultant")) in high_result_names else "High"
        judgement = "高业绩顾问存在单项过程改善点，不等同于经营风险。" if priority == "Medium" else "简历质量或岗位匹配弱，客户没有把推荐转成面试。"
        issues.append({"优先级": priority, "维度": "项目推进效率", "问题源": row.get("consultant"), "证据": f"推荐到一面 {pct(row.get('referral_to_interview'))}，推荐量 {int(row.get('referrals', 0))}", "判断": judgement, "建议": "复盘最近 10 份未进面候选人，校准岗位画像、必备条件和客户偏好。"})

    low_offer = active[(active["first_interviews"] >= 3) & (active["interview_to_offer"] < 0.30)].sort_values("interview_to_offer").head(3)
    for _, row in low_offer.iterrows():
        priority = "Medium" if str(row.get("consultant")) in high_result_names else "High"
        judgement = "高业绩顾问的面试后转化偏低，应作为提效机会而非风险名单。" if priority == "Medium" else "面试后推进、候选人意愿管理或客户岗位真实吸引力不足。"
        issues.append({"优先级": priority, "维度": "项目推进效率", "问题源": row.get("consultant"), "证据": f"一面到 Offer {pct(row.get('interview_to_offer'))}，一面 {int(row.get('first_interviews', 0))}", "判断": judgement, "建议": "建立面试后 24 小时复盘机制，区分能力不匹配、薪酬不匹配、客户决策慢三类原因。"})
    return issues


def _cost_issues(cost) -> list:
    ranking = cost.get("ranking", pd.DataFrame())
    issues = []
    if ranking is None or ranking.empty:
        return issues
    work = ranking.copy()
    no_revenue = work[work.get("efficiency_rating").eq("No Revenue")].copy()
    if "monthly_cost" in no_revenue.columns:
        no_revenue = no_revenue.sort_values("monthly_cost", ascending=False)
    for _, row in no_revenue.head(5).iterrows():
        issues.append({"优先级": "High", "维度": "顾问成本", "问题源": row.get("consultant"), "证据": f"月成本 {money(row.get('monthly_cost', 0))}，本年回款 {money(row.get('total_collection', 0))}", "判断": "当前薪资成本没有形成回款贡献，若同时项目推进弱，应进入产能改善或岗位调整名单。", "建议": "给出 30 天产能目标：有效推荐、面试、Offer Pipeline；低于目标则减少低利润项目占用。"})
    needs = work[work.get("efficiency_rating").eq("Needs Improvement")].copy()
    if "cost_revenue_ratio" in needs.columns:
        needs["cost_revenue_ratio"] = pd.to_numeric(needs["cost_revenue_ratio"], errors="coerce")
        needs = needs[needs["cost_revenue_ratio"] >= 1.5].sort_values("cost_revenue_ratio", ascending=False)
    for _, row in needs.head(5).iterrows():
        issues.append({"优先级": "Medium", "维度": "顾问成本", "问题源": row.get("consultant"), "证据": f"成本收入比 {pct(row.get('cost_revenue_ratio'))}，本年回款 {money(row.get('total_collection', 0))}", "判断": "成本覆盖不足，需要提升高质量职位承接或减少无效交付时间。", "建议": "优先分配现金好、费率稳、岗位确定性高的项目；重复寻访工作交给 AI 工具和助理流程。"})
    return issues


def _cashflow_issues(cashflow) -> list:
    issues = []
    client_risk = cashflow.get("client_risk", pd.DataFrame())
    overdue_orders = cashflow.get("overdue_orders", pd.DataFrame())
    if isinstance(client_risk, pd.DataFrame) and not client_risk.empty:
        high_clients = client_risk[client_risk["risk_level"].isin(["Very High", "High"])].head(5)
        for _, row in high_clients.iterrows():
            level = "High" if row.get("risk_level") == "Very High" else "Medium"
            issues.append({"优先级": level, "维度": "公司现金流", "问题源": row.get("client_name"), "证据": f"待回款 {money(row.get('pending_amount', 0))}，逾期率 {pct(row.get('overdue_rate'))}，最长逾期 {row.get('max_overdue_days', 0):.0f} 天", "判断": "客户回款质量影响利润兑现，应纳入客户分层和项目准入。", "建议": "新职位承接前检查历史回款；高逾期客户要求预付款、缩短账期或暂停低确定性岗位。"})
    if isinstance(overdue_orders, pd.DataFrame) and not overdue_orders.empty:
        top = overdue_orders.sort_values("pending_amount", ascending=False).head(1).iloc[0]
        issues.append({"优先级": "High", "维度": "公司现金流", "问题源": top.get("client_name"), "证据": f"单笔逾期待回款 {money(top.get('pending_amount', 0))}，逾期 {top.get('overdue_days', 0):.0f} 天", "判断": "大额单笔逾期会放大短期现金压力。", "建议": "设为本周回款战役，明确负责人、客户联系人、承诺付款日和升级路径。"})
    return issues


def _project_addition_issues(project_additions) -> list:
    issues = []
    if not isinstance(project_additions, dict):
        return issues
    consultant = project_additions.get("consultant", pd.DataFrame())
    team = project_additions.get("team", pd.DataFrame())
    if isinstance(team, pd.DataFrame) and not team.empty:
        weak_team = team[(team["new_projects"] >= 10) & (team["project_to_offer_rate"] < 0.05)].sort_values("new_projects", ascending=False).head(3)
        for _, row in weak_team.iterrows():
            issues.append({"优先级": "Medium", "维度": "项目新增质量", "问题源": row.get("team"), "证据": f"新增项目 {int(row.get('new_projects', 0))}，项目到 Offer {pct(row.get('project_to_offer_rate'))}", "判断": "新增项目没有有效转化为结果，可能存在岗位质量、客户预算或推进优先级问题。", "建议": "按客户付费能力、岗位紧急度、费率和历史回款重排项目优先级，低质量岗位减少投入。"})
    if isinstance(consultant, pd.DataFrame) and not consultant.empty:
        heavy_no_offer = consultant[(consultant["new_projects"] >= 8) & (consultant["offer_projects"] == 0)].sort_values("new_projects", ascending=False).head(5)
        for _, row in heavy_no_offer.iterrows():
            issues.append({"优先级": "Medium", "维度": "项目新增质量", "问题源": row.get("consultant"), "证据": f"新增项目 {int(row.get('new_projects', 0))}，产生 Offer 项目 0", "判断": "承接或新增项目多，但结果产出不足，需要判断是 BD 质量还是交付能力问题。", "建议": "抽样复盘项目来源、客户真实需求、候选人供给难度；必要时减少长尾岗位。"})
    return issues


def _management_actions(conversion, cost, cashflow) -> list:
    rates = conversion.get("stage_rates", {})
    cost_ratio = cost.get("summary", {}).get("cost_revenue_ratio")
    overdue_rate = cashflow.get("summary", {}).get("overdue_rate", 0)
    return [
        {"方向": "利润板块聚焦", "触发依据": f"成本收入比 {pct(cost_ratio)}，整体转化 {pct(rates.get('overall'))}", "动作": "把项目分为 A/B/C 三层：A 类高费率高回款优先投入；B 类限时验证；C 类停止深度交付。", "负责人视角": "管理层 + Team Lead"},
        {"方向": "交付效率提升", "触发依据": f"推荐到一面 {pct(rates.get('referral_to_interview'))}，一面到 Offer {pct(rates.get('interview_to_offer'))}", "动作": "建立岗位 48 小时校准机制：职位画像、目标公司、薪资带、候选人拒绝原因必须结构化沉淀。", "负责人视角": "交付负责人"},
        {"方向": "现金优先", "触发依据": f"逾期率 {pct(overdue_rate)}，逾期金额 {money(cashflow.get('summary', {}).get('overdue_amount', 0))}", "动作": "将客户分层加入回款维度，高逾期客户不再默认获得同等交付资源。", "负责人视角": "财务 + 客户负责人"},
        {"方向": "AI 降本", "触发依据": "医药岗位减少、候选人供给复杂、顾问重复寻访成本高", "动作": "优先把 AI 用于岗位解析、候选人长名单、相似候选人推荐、面试反馈归因和顾问训练，不先做大而全系统。", "负责人视角": "产品 + 业务专家"},
    ]


def _ninety_day_plan() -> list:
    return [
        {"阶段": "0-30 天", "重点": "止血", "动作": "锁定高逾期客户、No Revenue 顾问、低转化项目；建立每周现金回款战役。", "结果指标": "逾期金额下降，低效项目清单明确"},
        {"阶段": "31-60 天", "重点": "提效", "动作": "按岗位利润和交付难度重排项目；上线 AI 长名单和岗位画像辅助流程。", "结果指标": "推荐到一面、一面到 Offer 改善"},
        {"阶段": "61-90 天", "重点": "收敛", "动作": "保留利润板块和高质量客户；对低产出职能和低质量岗位形成退出机制。", "结果指标": "成本收入比下降，现金回款稳定"},
    ]
