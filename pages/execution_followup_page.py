"""Streamlit page for monthly execution follow-up."""

from __future__ import annotations

import json
from typing import Callable, Dict

import pandas as pd
import streamlit as st

from modules.execution_followup import (
    METRIC_DEFINITIONS,
    add_task,
    delete_tasks,
    evidence_for_task,
    load_tasks,
    review_tasks,
    run_task_definition_agent,
    save_tasks,
)
from pages.v2_dashboard import AI_PROVIDER_PRESETS, _get_ai_api_key, _masked_key


DEFAULT_AGENT_PROVIDER = "Kimi / Moonshot CN"
DEFAULT_AGENT_MODEL = "kimi-k2.5"
DEFAULT_AGENT_MAX_TOKENS = 1800
DEFAULT_AGENT_TIMEOUT = 90


def render_execution_followup(
    context: Dict[str, object],
    config: Dict[str, object],
    review_context_loader: Callable[[], Dict[str, object]] | None = None,
) -> None:
    st.markdown("### 执行跟进")
    st.caption("把月会行动项拆成可核查指标，并在复盘时直接从系统数据追踪完成情况。")

    tasks_df = load_tasks()
    consultants = _consultant_options(context)

    mode = st.radio(
        "执行跟进模式",
        ["指标录入", "完成核对", "任务库"],
        horizontal=True,
        label_visibility="collapsed",
    )
    if mode == "指标录入":
        _render_task_definition(config, consultants)
    elif mode == "完成核对":
        _render_review(tasks_df, context, config, review_context_loader)
    else:
        _render_task_library(tasks_df)


def _render_task_definition(config: Dict[str, object], consultants: list[str]) -> None:
    st.markdown("#### 管理任务指标录入")
    st.caption("优先用指标下拉框定义任务，避免模型误解业务表达。Agent 只作为辅助整理，不影响你手动选择指标口径。")

    _render_manual_task_builder(config, consultants)

    with st.expander("任务 Agent 辅助整理", expanded=False):
        _render_task_agent(config, consultants)


def _render_manual_task_builder(config: Dict[str, object], consultants: list[str]) -> None:
    _render_metric_reference()
    st.markdown("##### 新增任务指标")
    metric_labels = _metric_label_options()
    owner_type = st.selectbox("对象类型", ["consultant", "team", "company"], key="manual_task_owner_type")
    owner_name = ""
    if owner_type == "consultant":
        owner_name = st.selectbox("Consultant", consultants or [""], key="manual_task_owner_name")
    elif owner_type == "team":
        owner_name = st.text_input("团队", key="manual_task_owner_team", placeholder="例如：临床 / 销售 / MA&GA")
    else:
        owner_name = "Company"

    c1, c2, c3 = st.columns([1.3, 0.8, 0.9])
    with c1:
        metric_label = st.selectbox("指标", metric_labels, key="manual_task_metric")
    metric_key = _metric_key_from_label(metric_label)
    definition = METRIC_DEFINITIONS.get(metric_key, {})
    with c2:
        operator = st.selectbox("判断", [">=", "<=", "="], index=0, key="manual_task_operator")
    with c3:
        target_value = st.number_input("目标值", value=1.0, step=1.0, key="manual_task_target")

    c4, c5, c6 = st.columns([1, 1, 1])
    default_start, default_end = _default_assessment_period(config)
    with c4:
        period_start = st.date_input("核查开始日期", value=default_start, key="manual_task_period_start")
    with c5:
        period_end = st.date_input("核查结束日期", value=default_end, key="manual_task_period_end")
    with c6:
        priority = st.selectbox("优先级", ["High", "Medium", "Low"], index=1, key="manual_task_priority")

    task_text = st.text_input(
        "任务说明",
        value=f"{metric_label} {operator} {_format_target_for_task(target_value, definition.get('unit', 'count'))}",
        key="manual_task_text",
    )
    if st.button("保存任务指标", type="primary", use_container_width=True):
        if not owner_name:
            st.error("请先选择或输入任务对象。")
            return
        add_task(
            {
                "meeting_month": str(config.get("end_date") or "")[:7],
                "owner_type": owner_type,
                "owner_name": owner_name,
                "theme": _theme_for_metric(metric_key),
                "task": task_text,
                "metric_key": metric_key,
                "operator": operator,
                "target_value": float(target_value or 0),
                "period_start": pd.to_datetime(period_start).date().isoformat(),
                "period_end": pd.to_datetime(period_end).date().isoformat(),
                "priority": priority,
                "status": "active",
                "notes": "手动指标选项录入",
                "source_text": task_text,
            }
        )
        st.success("已保存任务指标")
        st.rerun()


def _render_task_agent(config: Dict[str, object], consultants: list[str]) -> None:
    st.markdown("##### Agent 对话")
    st.caption("用于把自然语言整理成草案；保存前仍需在下拉指标表格中确认口径。")

    llm_config = _execution_agent_llm_config()
    with st.expander("模型连接", expanded=False):
        if llm_config.get("api_key"):
            st.success(f"已读取模型 Key：{llm_config.get('key_source')} / {_masked_key(str(llm_config.get('api_key')))}")
        else:
            st.warning("未读取到模型 Key。请在 Streamlit Secrets 配置 MOONSHOT_API_KEY。")
        st.caption(
            f"provider={llm_config.get('provider')} | model={llm_config.get('model')} | "
            f"base_url={llm_config.get('base_url')}"
        )

    st.session_state.setdefault("execution_task_agent_messages", [])
    st.session_state.setdefault("execution_agent_draft_tasks", [])

    for message in st.session_state["execution_task_agent_messages"]:
        role = "user" if message.get("role") == "user" else "assistant"
        with st.chat_message(role):
            st.markdown(message.get("content", ""))

    sample_text = "Consultant 下个月改善：BD 2家客户，新增面试5个，推面比50%，新增Offer 1个"
    user_text = st.text_area(
        "和任务 Agent 说明本次月会行动项",
        placeholder=f"例如：{sample_text}",
        height=110,
        key="execution_agent_user_text",
    )
    col1, col2, col3 = st.columns([1.2, 1, 1])
    with col1:
        send_clicked = st.button("发送给任务 Agent", type="primary", use_container_width=True)
    with col2:
        if st.button("填入示例", use_container_width=True):
            st.session_state["execution_agent_user_text"] = sample_text
            st.rerun()
    with col3:
        if st.button("清空对话", use_container_width=True):
            st.session_state["execution_task_agent_messages"] = []
            st.session_state["execution_agent_draft_tasks"] = []
            st.rerun()

    if send_clicked:
        if not str(user_text or "").strip():
            st.error("请先输入你希望跟进的管理动作。灰色示例只是提示文案，不会自动作为输入。")
        elif not llm_config.get("api_key"):
            st.error("任务定义 Agent 需要模型 Key。当前没有读取到 MOONSHOT_API_KEY。")
        else:
            st.session_state["execution_task_agent_messages"].append({"role": "user", "content": user_text})
            try:
                with st.spinner("任务 Agent 正在澄清并生成指标草案..."):
                    result = run_task_definition_agent(
                        user_message=user_text,
                        chat_history=st.session_state["execution_task_agent_messages"],
                        consultants=consultants,
                        config=config,
                        llm_config=llm_config,
                    )
                assistant_message = result.get("assistant_message") or "我已经整理出任务草案，请在下方确认。"
                tasks = result.get("tasks") or []
                if tasks:
                    st.session_state["execution_agent_draft_tasks"] = tasks
                    assistant_message += f"\n\n已生成 {len(tasks)} 条可核查指标草案。"
                st.session_state["execution_task_agent_messages"].append(
                    {"role": "assistant", "content": assistant_message}
                )
                st.rerun()
            except Exception as exc:
                st.session_state["execution_task_agent_messages"].append(
                    {"role": "assistant", "content": f"任务 Agent 调用失败：{exc}"}
                )
                st.error(f"任务 Agent 调用失败：{exc}")

    draft_tasks = st.session_state.get("execution_agent_draft_tasks", [])
    if not draft_tasks:
        st.info("可以连续对话补充：对象、周期、指标口径、目标值。Agent 只在信息足够时生成待确认任务。")
        return

    _render_metric_reference()
    st.markdown("##### 待确认任务指标")
    edited = st.data_editor(
        _display_tasks(pd.DataFrame(draft_tasks)),
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        column_config=_task_editor_column_config(),
        key="execution_agent_draft_editor",
    )
    if st.button("确认保存任务指标", type="primary", use_container_width=True):
        for idx, task in enumerate(draft_tasks):
            if idx < len(edited):
                _apply_editor_row(task, edited.iloc[idx])
            add_task(task)
        st.session_state["execution_agent_draft_tasks"] = []
        st.success(f"已保存 {len(draft_tasks)} 条任务指标")
        st.rerun()


def _render_review(
    tasks_df: pd.DataFrame,
    base_context: Dict[str, object],
    config: Dict[str, object],
    review_context_loader: Callable[[], Dict[str, object]] | None = None,
) -> None:
    st.markdown("#### 完成情况复盘")
    if tasks_df.empty:
        st.info("还没有执行任务。")
        return

    default_start, default_end = _default_assessment_period(config)
    c1, c2, c3 = st.columns([1, 1, 1.2])
    with c1:
        review_start = st.date_input("考核开始日期", value=default_start, key="execution_review_start")
    with c2:
        review_end = st.date_input("考核结束日期", value=default_end, key="execution_review_end")
    with c3:
        override_period = st.checkbox("用筛选周期核查", value=True, help="开启后，完成核对按上方日期重新计算，不受任务保存时的周期影响。")

    active = tasks_df[tasks_df["status"].astype(str).isin(["active", "跟进中", "计划中", ""])]
    active = _filter_tasks_by_review_period(active, review_start, review_end)
    if override_period and not active.empty:
        active = active.copy()
        active["period_start"] = pd.to_datetime(review_start).date().isoformat()
        active["period_end"] = pd.to_datetime(review_end).date().isoformat()
    if active.empty:
        st.info("当前考核周期内没有可复盘任务。")
        return

    if review_context_loader is not None:
        with st.spinner("加载核对数据..."):
            context = review_context_loader()
    else:
        context = base_context
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
    st.download_button(
        "导出任务 JSON",
        data=current_json,
        file_name="execution_followups.json",
        mime="application/json",
        use_container_width=True,
    )
    uploaded = st.file_uploader("导入任务 JSON", type=["json"])
    if uploaded is not None and st.button("确认导入并覆盖", use_container_width=True):
        data = json.loads(uploaded.read().decode("utf-8"))
        imported = pd.DataFrame(data.get("tasks", []))
        count = save_tasks(imported)
        st.success(f"已导入 {count} 条任务")
        st.rerun()


def _execution_agent_llm_config() -> Dict[str, object]:
    provider = st.session_state.get("decision_agent_provider", DEFAULT_AGENT_PROVIDER)
    if provider not in AI_PROVIDER_PRESETS:
        provider = DEFAULT_AGENT_PROVIDER if DEFAULT_AGENT_PROVIDER in AI_PROVIDER_PRESETS else list(AI_PROVIDER_PRESETS)[0]
    preset = AI_PROVIDER_PRESETS[provider]
    model = st.session_state.get("decision_agent_model", DEFAULT_AGENT_MODEL)
    if not model:
        model = preset["models"][0]
    base_url = st.session_state.get("decision_agent_base_url", preset["base_url"])
    api_key, key_source = _get_ai_api_key(provider, "")
    return {
        "provider": provider,
        "model": model,
        "base_url": base_url,
        "api_key": api_key,
        "key_source": key_source,
        "temperature": 1.0,
        "max_tokens": DEFAULT_AGENT_MAX_TOKENS,
        "timeout": DEFAULT_AGENT_TIMEOUT,
    }


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


def _task_editor_column_config() -> Dict[str, object]:
    return {
        "metric": st.column_config.SelectboxColumn(
            "指标",
            options=_metric_label_options(),
            required=True,
            help="选择系统可核查的指标口径，避免 Agent 误解业务表达。",
        ),
        "operator": st.column_config.SelectboxColumn("判断", options=[">=", "<=", "="], required=True),
        "owner_type": st.column_config.SelectboxColumn("对象类型", options=["consultant", "team", "company"], required=True),
        "target_value": st.column_config.NumberColumn("目标值", step=1.0),
    }


def _render_metric_reference() -> None:
    with st.expander("可核查指标口径", expanded=False):
        rows = [
            {"指标": "新增Case BD数", "系统口径": "joborder 新增数，按 addedBy 归属顾问；用于跟进新开 Case/岗位 BD。"},
            {"指标": "新增岗位/项目数", "系统口径": "有推荐动作的去重 joborder 数；用于跟进开始推进的项目。"},
            {"指标": "新增推荐数", "系统口径": "本周期新增推荐记录数。"},
            {"指标": "平均推荐量", "系统口径": "新增推荐数 / 有推荐动作的去重岗位数。"},
            {"指标": "新增面试数", "系统口径": "本周期新增一面记录数。"},
            {"指标": "推面比", "系统口径": "新增面试数 / 新增推荐数。"},
            {"指标": "新增Offer数", "系统口径": "本周期新增 Offer 数。"},
            {"指标": "总未回款储备", "系统口径": "Invoice Added + Sent 未回款业绩，按顾问业绩分配拆分。"},
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _metric_label_options() -> list[str]:
    return [str(item.get("label")) for item in METRIC_DEFINITIONS.values()]


def _default_assessment_period(config: Dict[str, object]) -> tuple[object, object]:
    end = pd.to_datetime(config.get("end_date"), errors="coerce")
    if pd.isna(end):
        end = pd.Timestamp.today().normalize()
    start = end.replace(day=1)
    return start.date(), end.date()


def _filter_tasks_by_review_period(tasks_df: pd.DataFrame, review_start: object, review_end: object) -> pd.DataFrame:
    if tasks_df is None or tasks_df.empty:
        return pd.DataFrame()
    start = pd.to_datetime(review_start, errors="coerce")
    end = pd.to_datetime(review_end, errors="coerce")
    if pd.isna(start) or pd.isna(end):
        return tasks_df.copy()
    work = tasks_df.copy()
    task_start = pd.to_datetime(work.get("period_start"), errors="coerce")
    task_end = pd.to_datetime(work.get("period_end"), errors="coerce")
    missing = task_start.isna() | task_end.isna()
    overlaps = missing | ((task_start.dt.normalize() <= end.normalize()) & (task_end.dt.normalize() >= start.normalize()))
    return work[overlaps].copy()


def _apply_editor_row(task: Dict[str, object], row: pd.Series) -> None:
    for col in [
        "meeting_month",
        "owner_type",
        "owner_name",
        "theme",
        "task",
        "operator",
        "target_value",
        "period_start",
        "period_end",
        "priority",
        "status",
        "notes",
    ]:
        if col in row.index:
            task[col] = row.get(col)
    if "metric" in row.index:
        metric_label = str(row.get("metric") or "")
        metric_key = _metric_key_from_label(metric_label) or task.get("metric_key")
        task["metric_key"] = metric_key
        if metric_key in METRIC_DEFINITIONS:
            definition = METRIC_DEFINITIONS[metric_key]
            task["operator"] = task.get("operator") or definition.get("default_operator")
            task["theme"] = task.get("theme") or _theme_for_metric(metric_key)


def _consultant_options(context: Dict[str, object]) -> list[str]:
    df = context.get("consultants_df", pd.DataFrame())
    if df is None or df.empty or "consultant" not in df.columns:
        return []
    if "is_active" in df.columns:
        df = df[df["is_active"].fillna(False)]
    return sorted([str(x) for x in df["consultant"].dropna().unique() if str(x).strip()])


def _task_label(df: pd.DataFrame, task_id: str) -> str:
    row = df[df["id"].astype(str).eq(str(task_id))]
    if row.empty:
        return task_id
    item = row.iloc[0]
    return f"{item.get('owner_name')} | {item.get('task')}"


def _metric_key_from_label(label: str) -> str:
    for key, definition in METRIC_DEFINITIONS.items():
        if str(definition.get("label")) == str(label):
            return key
    return ""


def _format_target_for_task(value: float, unit: str) -> str:
    if unit == "percent":
        return f"{float(value):.0%}" if float(value) <= 1 else f"{float(value):.0f}%"
    if unit == "money":
        return f"¥{float(value):,.0f}"
    return f"{float(value):g}"


def _theme_for_metric(metric_key: str) -> str:
    if metric_key in {
        "new_bd_clients",
        "new_case_bd",
        "new_projects",
        "new_referrals",
        "avg_referrals_per_project",
        "new_interviews",
        "referral_to_interview_rate",
        "interview_to_offer_rate",
        "new_offers",
    }:
        return "顾问产能"
    if metric_key in {"collection_amount", "offer_unpaid_amount"}:
        return "现金回款"
    if metric_key == "weighted_forecast":
        return "Pipeline"
    return "经营跟进"
