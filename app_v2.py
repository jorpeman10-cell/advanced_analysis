#!/usr/bin/env python
"""Three-Speed Model v2 Streamlit app."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import db_config_manager
from gllue_db_client import GllueDBClient
from modules.cashflow_analyzer import CashFlowAnalyzer
from modules.consultant_performance import ConsultantPerformanceAnalyzer
from modules.conversion_analyzer import ConversionAnalyzer
from modules.cost_analyzer import CostEfficiencyAnalyzer
from modules.health_scorer import HealthScorer
from modules.pipeline_analyzer import PipelineAnalyzer
from modules.project_progress_analyzer import ProjectProgressAnalyzer
from modules.salary_store import load_salary_df, save_salary_df
from modules.v2_data_service import V2DataService
from pages.decision_agent_page import render_decision_agent
from pages.v2_dashboard import (
    render_cashflow,
    render_conversion,
    render_cost_efficiency,
    render_dashboard,
    render_fiscal_ytd,
    render_management_review,
)


st.set_page_config(
    page_title="Three-Speed Model v2",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data(ttl=900, show_spinner=False)
def load_v2_data(start_date: str, end_date: str, forecast_days: int):
    db = GllueDBClient(db_config_manager.get_gllue_db_config())
    service = V2DataService(db)
    fiscal_start = f"{pd.to_datetime(end_date).year}-01-01"
    process_df = service.load_process_data(start_date, end_date)
    forecast_df = service.load_forecast_data(end_date, forecast_days)
    collection_df = service.load_collection_data(start_date, end_date)
    fiscal_collection_df = service.load_collection_data(fiscal_start, end_date)
    consultants_df = service.load_consultants()
    cashflow_invoices_df = service.load_cashflow_invoices(start_date, end_date)
    ytd = service.load_fiscal_ytd_metrics(fiscal_start, end_date, forecast_days)
    offer_outcomes = service.load_offer_outcome_metrics(fiscal_start, end_date)
    project_additions = service.load_project_additions(fiscal_start, end_date)
    db.close()
    return process_df, forecast_df, collection_df, fiscal_collection_df, consultants_df, cashflow_invoices_df, ytd, offer_outcomes, project_additions


def read_salary_file(uploaded_file) -> pd.DataFrame:
    if uploaded_file is None:
        return pd.DataFrame()
    if uploaded_file.name.lower().endswith(".csv"):
        return pd.read_csv(uploaded_file)
    return pd.read_excel(uploaded_file)


PROCESS_DEPARTED_EXCLUDES = (
    "潘亚兰",
    "bunny pan",
    "吴双",
    "sunday wu",
    "刘科利",
    "kerry liu",
)


def _norm_name(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return " ".join(str(value).strip().lower().split())


def _is_departed_process_account(value: object) -> bool:
    name = _norm_name(value)
    return bool(name) and any(excluded in name for excluded in PROCESS_DEPARTED_EXCLUDES)


def filter_active_process_rows(process_df: pd.DataFrame, consultants_df: pd.DataFrame) -> pd.DataFrame:
    """Keep process diagnosis focused on current consultants only."""
    if process_df is None or process_df.empty or "consultant" not in process_df.columns:
        return process_df.copy() if isinstance(process_df, pd.DataFrame) else pd.DataFrame()

    if consultants_df is None or consultants_df.empty or "consultant" not in consultants_df.columns:
        return process_df.iloc[0:0].copy()

    if "is_active" in consultants_df.columns:
        consultants_df = consultants_df[consultants_df["is_active"].fillna(False)].copy()

    active_keys = [
        key
        for key in consultants_df["consultant"].map(_norm_name).dropna().unique().tolist()
        if key
    ]

    def is_active(value: object) -> bool:
        name = _norm_name(value)
        if not name or _is_departed_process_account(name):
            return False
        return any(active_key in name or name in active_key for active_key in active_keys)

    return process_df[process_df["consultant"].apply(is_active)].copy()


def build_context(config: dict, salary_df: pd.DataFrame) -> dict:
    process_df, forecast_df, collection_df, fiscal_collection_df, consultants_df, cashflow_invoices_df, ytd, offer_outcomes, project_additions = load_v2_data(
        config["start_date"],
        config["end_date"],
        config["forecast_days"],
    )

    active_process_df = filter_active_process_rows(process_df, consultants_df)
    conversion = ConversionAnalyzer().analyze(active_process_df, analysis_date=config["end_date"])
    project_progress = ProjectProgressAnalyzer().analyze(active_process_df)
    pipeline = PipelineAnalyzer().analyze(forecast_df, days=config["forecast_days"], analysis_date=config["end_date"])
    cost = CostEfficiencyAnalyzer(
        salary_multiplier=config["salary_multiplier"],
    ).analyze(consultants_df, fiscal_collection_df, salary_df)
    cashflow = CashFlowAnalyzer().analyze(
        cashflow_invoices_df,
        initial_cash=config["initial_cash"],
        monthly_cost=cost.get("summary", {}).get("monthly_cost", 0),
        ytd_collection=cost.get("summary", {}).get("annual_collection", 0),
        forecast_df=forecast_df,
        analysis_date=config["end_date"],
        days=180,
    )
    consultant_performance = ConsultantPerformanceAnalyzer().analyze(
        cost,
        offer_outcomes,
        pipeline,
        conversion,
        forecast_days=config["forecast_days"],
    )
    health = HealthScorer().score(conversion, cost, cashflow)

    return {
        "process_df": process_df,
        "active_process_df": active_process_df,
        "forecast_df": forecast_df,
        "collection_df": collection_df,
        "fiscal_collection_df": fiscal_collection_df,
        "consultants_df": consultants_df,
        "cashflow_invoices_df": cashflow_invoices_df,
        "ytd": ytd,
        "offer_outcomes": offer_outcomes,
        "project_additions": project_additions,
        "conversion": conversion,
        "project_progress": project_progress,
        "pipeline": pipeline,
        "cost": cost,
        "consultant_performance": consultant_performance,
        "cashflow": cashflow,
        "health": health,
    }


def render_sidebar() -> tuple[dict, pd.DataFrame]:
    st.sidebar.title("Three-Speed v2")
    st.sidebar.caption("数据口径：过程转化 + 顾问成本 + 现金流压力")

    window = V2DataService.default_window()
    start_date = st.sidebar.date_input("分析开始日期", value=pd.to_datetime(window["start_date"]))
    end_date = st.sidebar.date_input("分析结束日期", value=pd.to_datetime(window["end_date"]))
    forecast_days = st.sidebar.radio("Pipeline 预测窗口", [90, 180], index=1, horizontal=True)

    st.sidebar.markdown("---")
    initial_cash = st.sidebar.number_input("年初现金余额", min_value=0, value=1800000, step=100000)
    salary_multiplier = st.sidebar.number_input("工资成本倍数", min_value=1.0, max_value=6.0, value=3.0, step=0.5)

    st.sidebar.markdown("---")
    st.sidebar.caption("顾问成本必须上传工资表；不再使用默认薪资。运营/系统账号会自动排除出顾问分析。")
    salary_file = st.sidebar.file_uploader("顾问薪资表", type=["xlsx", "xls", "csv"])
    if salary_file is not None:
        uploaded_salary_df = read_salary_file(salary_file)
        saved_count = save_salary_df(uploaded_salary_df)
        salary_df = load_salary_df()
        st.session_state["current_salary_df"] = salary_df
        st.sidebar.success(f"薪资表已更新并记忆：{saved_count} 行")
    elif "current_salary_df" in st.session_state and not st.session_state["current_salary_df"].empty:
        salary_df = st.session_state["current_salary_df"]
        st.sidebar.success(f"已沿用当前薪资数据：{len(salary_df)} 行")
    else:
        salary_df = load_salary_df()
        if not salary_df.empty:
            st.session_state["current_salary_df"] = salary_df
            st.sidebar.success(f"已读取记忆薪资数据：{len(salary_df)} 行")
        else:
            st.sidebar.warning("未找到薪资配置。顾问成本只展示收入，成本可信度为 Low。")

    if st.sidebar.button("刷新数据", use_container_width=True):
        load_v2_data.clear()
        st.rerun()

    config = {
        "start_date": pd.to_datetime(start_date).date().isoformat(),
        "end_date": pd.to_datetime(end_date).date().isoformat(),
        "forecast_days": int(forecast_days),
        "initial_cash": float(initial_cash),
        "salary_multiplier": float(salary_multiplier),
    }
    return config, salary_df


def main() -> None:
    st.title("猎头三速差模型 v2")
    if not db_config_manager.has_config():
        st.info(
            "Streamlit Cloud 不会读取本地 config/db_config.json。请在 App Settings -> Secrets 中配置 [gllue_db]，保存后 Reboot app。"
        )
        with st.expander("配置读取诊断（不显示密码）", expanded=True):
            st.json(db_config_manager.config_diagnostics())
        st.error("数据库连接尚未配置。请先在原高级分析工具中完成数据库配置。")
        return

    config, salary_df = render_sidebar()
    with st.spinner("加载并计算 v2 指标..."):
        context = build_context(config, salary_df)

    tabs = st.tabs(["全景仪表盘", "管理层复盘", "本财年数据", "项目推荐效率", "顾问成本效率", "现金流压力", "经营决策Agent"])
    with tabs[0]:
        render_dashboard(context)
    with tabs[1]:
        render_management_review(context)
    with tabs[2]:
        render_fiscal_ytd(context)
    with tabs[3]:
        render_conversion(context)
    with tabs[4]:
        render_cost_efficiency(context)
    with tabs[5]:
        render_cashflow(context)
    with tabs[6]:
        render_decision_agent(context)


if __name__ == "__main__":
    main()
