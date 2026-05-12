"""Streamlit page for monthly execution follow-up."""

from __future__ import annotations

import json
from datetime import date
from typing import Callable, Dict

import pandas as pd
import streamlit as st

from modules.execution_followup import (
    METRIC_DEFINITIONS,
    OPERATORS,
    OWNER_TYPES,
    add_task,
    delete_tasks,
    evidence_for_task,
    load_tasks,
    parse_management_tasks,
    review_tasks,
    save_tasks,
)


def render_execution_followup(context: Dict[str, object], config: Dict[str, object], review_context_loader: Callable[[], Dict[str, object]] | None = None) -> None:
    st.markdown("### 执行跟进")
    st.caption("把月会行动项拆成可核查指标，并直接从系统数据追踪完成情况。")

    tasks_df = load_tasks()
    consultants = _consultant_options(context)
    teams = _team_options(context)

    mode = st.radio("执行跟进模式", ["任务解析", "完成核对", "任务库"], horizontal=True, label_visibility="collapsed")
    if mode == "任务解析":
        _render_parser(config, consultants)
    elif mode == "完成核对":
        if review_context_loader is not None:
            with st.spinner("加载核对数据..."):
                review_context = review_context_loader()
        else:
            review_context = context
        _render_review(tasks_df, review_context)
    else:
        _render_task_library(tasks_df)


def _render_parser(config: Dict[str, object], consultants: list[str]) -> None:
    st.markdown("#### 管理任务解析")
    st.caption("示例中的 Consultant 可替换为任意顾问姓名。")
    sample_text = "Consultant 下个月改善：BD 2家客户，新增面试5个，推面比50%，新增Offer 1个"
    if st.button("填入示例", use_container_width=True):
        st.session_state["execution_parse_text"] = sample_text
    text = st.text_area(
        "输入月会行动项",
        placeholder=f"例如：{sample_text}",
        height=110,
        key="execution_parse_text",
    )
    parsed = []
    if st.button("解析任务", use_container_width=True):
        if not str(text or "").strip():
            parsed = []
            st.session_state["parsed_execution_tasks"] = []
            st.warning("请先输入任务内容。灰色示例只是提示文案，不会自动作为输入。")
        else:
            parsed = parse_management_tasks(text, consultants, config)
            st.session_state["parsed_execution_tasks"] = parsed
            if not parsed:
                st.warning("没有识别到可核查指标。请包含目标数字，例如：新增面试5个、推面比50%、新增Offer 1个。")

    parsed = st.session_state.get("parsed_execution_tasks", parsed)
    if not parsed:
        st.info("输入自然语言任务后点击解析。解析结果需要确认后才会保存。")
        return

    st.markdown("##### 解析结果")
    preview = pd.DataFrame(parsed)
    edited = st.data_editor(
        _display_tasks(preview),
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        key="parsed_execution_editor",
    )
    if st.button("确认保存解析任务", type="primary", use_container_width=True):
        for idx, task in enumerate(parsed):
            if idx < len(edited):
                for col in ["meeting_month", "owner_type", "owner_name", "theme", "task", "operator", "target_value", "period_start", "period_end", "priority", "status", "notes"]:
                    if col in edited.columns:
                        task[col] = edited.iloc[idx].get(col)
                if "metric" in edited.columns:
                    metric_label = str(edited.iloc[idx].get("metric") or "")
                    metric_key = _metric_key_from_label(metric_label) or task.get("metric_key")
                    task["metric_key"] = metric_key
            add_task(task)
        st.session_state["parsed_execution_tasks"] = []
        st.success(f"已保存 {len(parsed)} 条任务")
        st.rerun()


def _render_review(tasks_df: pd.DataFrame, context: Dict[str, object]) -> None:
    st.markdown("#### 完成情况复盘")
    if tasks_df.empty:
        st.info("还没有执行任务。")
        return

    active = tasks_df[tasks_df["status"].astype(str).isin(["active", "跟进中", "计划中", ""])]
    reviewed = review_tasks(active, context)
    if reviewed.empty:
        st.info("暂无可复盘任务。")
        return

    summary_cols = [
        "meeting_month",
        "owner_name",
        "theme",
        "task",
        "metric_label",
        "target_display",
        "actual_display",
        "completion_rate",
        "review_status",
        "gap_display",
        "evidence_count",
        "data_source",
    ]
    display = reviewed[[c for c in summary_cols if c in reviewed.columns]].copy()
    if "completion_rate" in display.columns:
        display["completion_rate"] = display["completion_rate"].apply(lambda x: f"{float(x):.0%}")
    st.dataframe(display, use_container_width=True, hide_index=True)

    completed = int(reviewed["is_completed"].fillna(False).sum())
    total = len(reviewed)
    c1, c2, c3 = st.columns(3)
    c1.metric("任务数", total)
    c2.metric("完成数", completed)
    c3.metric("完成率", f"{completed / total:.0%}" if total else "-")

    st.markdown("#### 证据明细")
    task_options = reviewed["id"].astype(str).tolist()
    labels = {
        str(row["id"]): f"{row.get('owner_name')} | {row.get('metric_label')} | {row.get('review_status')}"
        for _, row in reviewed.iterrows()
    }
    selected = st.selectbox("选择任务查看系统证据", task_options, format_func=lambda x: labels.get(x, x))
    row = reviewed[reviewed["id"].astype(str).eq(str(selected))].iloc[0].to_dict()
    evidence = evidence_for_task(row, context)
    if evidence.empty:
        st.warning("该任务没有可展示的证据明细。")
    else:
        st.dataframe(evidence, use_container_width=True, hide_index=True)


def _render_task_library(tasks_df: pd.DataFrame) -> None:
    st.markdown("#### 任务库")
    if tasks_df.empty:
        st.info("任务库为空。")
    else:
        st.dataframe(_display_tasks(tasks_df), use_container_width=True, hide_index=True)
        ids = tasks_df["id"].astype(str).tolist()
        selected = st.multiselect("选择要删除的任务", ids, format_func=lambda x: _task_label(tasks_df, x))
        if st.button("删除所选任务", disabled=not selected, use_container_width=True):
            deleted = delete_tasks(selected)
            st.success(f"已删除 {deleted} 条任务")
            st.rerun()

    st.markdown("#### 导入 / 导出")
    current_json = json.dumps({"tasks": tasks_df.fillna("").to_dict(orient="records")}, ensure_ascii=False, indent=2)
    st.download_button("导出任务 JSON", data=current_json, file_name="execution_followups.json", mime="application/json", use_container_width=True)
    uploaded = st.file_uploader("导入任务 JSON", type=["json"])
    if uploaded is not None and st.button("确认导入并覆盖", use_container_width=True):
        data = json.loads(uploaded.read().decode("utf-8"))
        imported = pd.DataFrame(data.get("tasks", []))
        count = save_tasks(imported)
        st.success(f"已导入 {count} 条任务")
        st.rerun()


def _display_tasks(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    work = df.copy()
    if "metric_key" in work.columns:
        work["metric"] = work["metric_key"].map(lambda x: METRIC_DEFINITIONS.get(str(x), {}).get("label", x))
    cols = [
        "meeting_month",
        "owner_type",
        "owner_name",
        "theme",
        "task",
        "metric",
        "operator",
        "target_value",
        "period_start",
        "period_end",
        "priority",
        "status",
        "notes",
    ]
    return work[[c for c in cols if c in work.columns]]


def _consultant_options(context: Dict[str, object]) -> list[str]:
    df = context.get("consultants_df", pd.DataFrame())
    if df is None or df.empty or "consultant" not in df.columns:
        return []
    if "is_active" in df.columns:
        df = df[df["is_active"].fillna(False)]
    return sorted([str(x) for x in df["consultant"].dropna().unique() if str(x).strip()])


def _team_options(context: Dict[str, object]) -> list[str]:
    df = context.get("consultants_df", pd.DataFrame())
    if df is None or df.empty or "team" not in df.columns:
        return []
    return sorted([str(x) for x in df["team"].dropna().unique() if str(x).strip()])


def _task_label(df: pd.DataFrame, task_id: str) -> str:
    row = df[df["id"].astype(str).eq(str(task_id))]
    if row.empty:
        return task_id
    item = row.iloc[0]
    return f"{item.get('owner_name')} | {item.get('task')}"


def _default_theme(metric_key: str) -> str:
    if metric_key in {"collection_amount", "offer_unpaid_amount"}:
        return "现金回款"
    if metric_key == "weighted_forecast":
        return "Pipeline"
    return "顾问产能"


def _metric_key_from_label(label: str) -> str:
    for key, definition in METRIC_DEFINITIONS.items():
        if str(definition.get("label")) == str(label):
            return key
    return ""
