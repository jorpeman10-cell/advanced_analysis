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

    _render_management_goal_builder(config, consultants)
    st.divider()
    _render_manual_task_builder(config, consultants)

    with st.expander("任务 Agent 辅助整理", expanded=False):
        _render_task_agent(config, consultants)


def _render_management_goal_builder(config: Dict[str, object], consultants: list[str]) -> None:
    st.markdown("##### 管理目标")
    st.caption("记录方向型目标，例如客户结构调整、目标客户/岗位/领域突破；下面再添加可量化行为指标。")
    with st.expander("新增管理目标", expanded=True):
        owner_type = st.selectbox("目标对象类型", ["consultant", "team", "company"], key="goal_owner_type")
        if owner_type == "consultant":
            owner_name = st.selectbox("Consultant", consultants or [""], key="goal_owner_name")
        elif owner_type == "team":
            owner_name = st.text_input("团队", key="goal_owner_team", placeholder="例如：CMC / 临床 / 销售")
        else:
            owner_name = "Company"

        c1, c2 = st.columns([1, 1])
        with c1:
            goal_type = st.selectbox(
                "目标类型",
                ["客户结构调整", "目标客户突破", "岗位领域调整", "BD方向调整", "交付质量改善", "其他"],
                key="goal_type",
            )
        with c2:
            priority = st.selectbox("目标优先级", ["High", "Medium", "Low"], index=1, key="goal_priority")

        c3, c4, c5 = st.columns([1, 1, 1])
        with c3:
            target_customer = st.text_input("目标客户", key="goal_target_customer", placeholder="例如：亚虹医药 / 内资创新药")
        with c4:
            target_domain = st.text_input("目标领域", key="goal_target_domain", placeholder="例如：CMC / 临床 / 商业化")
        with c5:
            target_position = st.text_input("目标岗位", key="goal_target_position", placeholder="例如：生产负责人 / 注册 / BD")

        goal_direction = st.text_area(
            "方向说明",
            key="goal_direction",
            height=80,
            placeholder="例如：下月重点从外资客户转向内资创新药客户，优先BD CMC生产/质量岗位。",
        )

        default_start, default_end = _default_assessment_period(config)
        c6, c7, c8 = st.columns([1, 1, 1])
        with c6:
            period_start = st.date_input("目标开始日期", value=default_start, key="goal_period_start")
        with c7:
            period_end = st.date_input("目标结束日期", value=default_end, key="goal_period_end")
        with c8:
            weekly_check_day = st.selectbox("每周提醒", ["周一", "周二", "周三", "周四", "周五"], index=0, key="goal_weekly_day")

        if st.button("保存管理目标", use_container_width=True):
            if not owner_name:
                st.error("请先选择或输入目标对象。")
                return
            if not any([target_customer, target_domain, target_position, goal_direction]):
                st.error("请至少填写目标客户、领域、岗位或方向说明。")
                return
            task_text = _build_goal_task_text(goal_type, target_customer, target_domain, target_position, goal_direction)
            payload = {
                "meeting_month": str(config.get("end_date") or "")[:7],
                "owner_type": owner_type,
                "owner_name": owner_name,
                "theme": "管理目标",
                "task": task_text,
                "metric_key": "management_goal",
                "operator": "=",
                "target_value": 0,
                "period_start": pd.to_datetime(period_start).date().isoformat(),
                "period_end": pd.to_datetime(period_end).date().isoformat(),
                "priority": priority,
                "status": "active",
                "notes": "管理方向目标，需结合下方量化行为指标跟进",
                "source_text": goal_direction,
                "goal_type": goal_type,
                "target_customer": target_customer,
                "target_domain": target_domain,
                "target_position": target_position,
                "goal_direction": goal_direction,
                "weekly_check_day": weekly_check_day,
                "next_check_date": _next_weekly_check_date(weekly_check_day),
                "progress_note": "",
            }
            if _is_duplicate_task(load_tasks(), payload):
                st.warning("该管理目标已存在，未重复保存。")
                return
            with st.spinner("正在保存管理目标..."):
                add_task(payload)
            st.success("已保存管理目标。请继续在下方添加对应的行为/结果指标。")
            st.rerun()


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

    entry_mode = st.radio("录入方式", ["单个指标", "多个指标"], horizontal=True, key="manual_task_entry_mode")
    metric_entries = []
    if entry_mode == "单个指标":
        c1, c2, c3 = st.columns([1.3, 0.8, 0.9])
        with c1:
            metric_label = st.selectbox("指标", metric_labels, key="manual_task_metric")
        metric_key = _metric_key_from_label(metric_label)
        definition = METRIC_DEFINITIONS.get(metric_key, {})
        with c2:
            operator = st.selectbox("判断", [">=", "<=", "="], index=0, key="manual_task_operator")
        with c3:
            target_value = st.number_input("目标值", value=1.0, step=1.0, key="manual_task_target")
        metric_entries.append(
            {
                "metric_label": metric_label,
                "metric_key": metric_key,
                "definition": definition,
                "operator": operator,
                "target_value": float(target_value or 0),
            }
        )
    else:
        selected_metric_labels = st.multiselect(
            "选择多个指标",
            metric_labels,
            default=metric_labels[:2] if len(metric_labels) >= 2 else metric_labels,
            key="manual_task_metrics_multi",
        )
        for metric_label in selected_metric_labels:
            metric_key = _metric_key_from_label(metric_label)
            definition = METRIC_DEFINITIONS.get(metric_key, {})
            c1, c2, c3 = st.columns([1.3, 0.8, 0.9])
            with c1:
                st.text_input("指标", value=metric_label, disabled=True, key=f"manual_task_metric_name_{metric_key}")
            with c2:
                default_operator = str(definition.get("default_operator") or ">=")
                operator_options = [">=", "<=", "="]
                default_index = operator_options.index(default_operator) if default_operator in operator_options else 0
                operator = st.selectbox("判断", operator_options, index=default_index, key=f"manual_task_operator_{metric_key}")
            with c3:
                target_value = st.number_input("目标值", value=1.0, step=1.0, key=f"manual_task_target_{metric_key}")
            metric_entries.append(
                {
                    "metric_label": metric_label,
                    "metric_key": metric_key,
                    "definition": definition,
                    "operator": operator,
                    "target_value": float(target_value or 0),
                }
            )

    c4, c5, c6 = st.columns([1, 1, 1])
    default_start, default_end = _default_assessment_period(config)
    with c4:
        period_start = st.date_input("核查开始日期", value=default_start, key="manual_task_period_start")
    with c5:
        period_end = st.date_input("核查结束日期", value=default_end, key="manual_task_period_end")
    with c6:
        priority = st.selectbox("优先级", ["High", "Medium", "Low"], index=1, key="manual_task_priority")

    task_note = st.text_input(
        "任务说明前缀",
        value="",
        placeholder="可选，例如：5月月会行动项 / 下月改善计划",
        key="manual_task_note",
    )
    save_clicked = st.button("保存任务指标", type="primary", use_container_width=True)
    if save_clicked:
        if not owner_name:
            st.error("请先选择或输入任务对象。")
            return
        if not metric_entries:
            st.error("请先选择至少一个指标。")
            return
        with st.spinner("正在保存任务指标..."):
            existing = load_tasks()
            saved_count = 0
            skipped_count = 0
            for entry in metric_entries:
                metric_key = entry["metric_key"]
                definition = entry["definition"]
                operator = entry["operator"]
                target_value = entry["target_value"]
                metric_label = entry["metric_label"]
                task_text = f"{metric_label} {operator} {_format_target_for_task(target_value, definition.get('unit', 'count'))}"
                if task_note:
                    task_text = f"{task_note}：{task_text}"
                payload = {
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
                if _is_duplicate_task(existing, payload):
                    skipped_count += 1
                    continue
                add_task(payload)
                existing = pd.concat([existing, pd.DataFrame([payload])], ignore_index=True)
                saved_count += 1
        if saved_count:
            st.success(f"已保存 {saved_count} 条任务指标" + (f"，跳过 {skipped_count} 条重复任务" if skipped_count else ""))
        else:
            st.warning(f"没有新增任务，已跳过 {skipped_count} 条重复任务。")
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
        metric_mask = ~active["metric_key"].astype(str).eq("management_goal")
        active.loc[metric_mask, "period_start"] = pd.to_datetime(review_start).date().isoformat()
        active.loc[metric_mask, "period_end"] = pd.to_datetime(review_end).date().isoformat()
    if active.empty:
        st.info("当前考核周期内没有可复盘任务。")
        return

    goals = active[active["metric_key"].astype(str).eq("management_goal")].copy()
    _render_goal_followup(goals)

    if review_context_loader is not None:
        with st.spinner("加载核对数据..."):
            context = review_context_loader()
    else:
        context = base_context
    metric_tasks = active[~active["metric_key"].astype(str).eq("management_goal")].copy()
    reviewed = review_tasks(metric_tasks, context)
    if reviewed.empty:
        st.info("暂无可量化复盘任务。")
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
        filtered = _task_library_filters(tasks_df)
        if filtered.empty:
            st.info("当前筛选条件下没有任务。")
        else:
            _render_grouped_task_list(filtered)

        with st.expander("原始明细", expanded=False):
            st.dataframe(_display_tasks(filtered), use_container_width=True, hide_index=True)

        ids = filtered["id"].astype(str).tolist()
        selected = st.multiselect("选择要删除的任务", ids, format_func=lambda x: _task_label(filtered, x))
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


def _render_goal_followup(goals_df: pd.DataFrame) -> None:
    st.markdown("#### 管理目标周跟进")
    if goals_df is None or goals_df.empty:
        st.info("当前周期内没有管理目标。")
        return
    display = goals_df.copy()
    today = pd.Timestamp.today().normalize()
    next_dates = pd.to_datetime(display.get("next_check_date"), errors="coerce").dt.normalize()
    display["提醒状态"] = ["本周/已到期" if pd.notna(d) and d <= today else "未到提醒" for d in next_dates]
    display["目标状态"] = display["status"].fillna("").replace("", "active")
    cols = [
        "owner_name",
        "goal_type",
        "target_customer",
        "target_domain",
        "target_position",
        "goal_direction",
        "weekly_check_day",
        "next_check_date",
        "提醒状态",
        "目标状态",
        "progress_note",
    ]
    st.dataframe(display[[c for c in cols if c in display.columns]], use_container_width=True, hide_index=True)
    due_count = int((next_dates <= today).fillna(False).sum())
    c1, c2, c3 = st.columns(3)
    c1.metric("管理目标数", len(display))
    c2.metric("本周需跟进", due_count)
    c3.metric("高优先级", int(display["priority"].astype(str).eq("High").sum()) if "priority" in display.columns else 0)


def _task_library_filters(tasks_df: pd.DataFrame) -> pd.DataFrame:
    work = tasks_df.copy()
    work["task_kind"] = work["metric_key"].astype(str).apply(lambda x: "管理目标" if x == "management_goal" else "量化指标")
    c1, c2, c3, c4 = st.columns([1, 1, 1.2, 1])
    with c1:
        months = ["全部"] + sorted([str(x) for x in work["meeting_month"].dropna().unique() if str(x)])
        month = st.selectbox("月份", months, key="task_library_month")
    with c2:
        kinds = ["全部", "管理目标", "量化指标"]
        kind = st.selectbox("类型", kinds, key="task_library_kind")
    with c3:
        owners = ["全部"] + sorted([str(x) for x in work["owner_name"].dropna().unique() if str(x)])
        owner = st.selectbox("对象", owners, key="task_library_owner")
    with c4:
        statuses = ["全部"] + sorted([str(x) for x in work["status"].fillna("").unique() if str(x)])
        status = st.selectbox("状态", statuses, key="task_library_status")

    if month != "全部":
        work = work[work["meeting_month"].astype(str).eq(month)]
    if kind != "全部":
        work = work[work["task_kind"].eq(kind)]
    if owner != "全部":
        work = work[work["owner_name"].astype(str).eq(owner)]
    if status != "全部":
        work = work[work["status"].astype(str).eq(status)]
    return work.copy()


def _render_grouped_task_list(tasks_df: pd.DataFrame) -> None:
    summary = (
        tasks_df.assign(
            is_goal=tasks_df["metric_key"].astype(str).eq("management_goal"),
            is_metric=~tasks_df["metric_key"].astype(str).eq("management_goal"),
        )
        .groupby(["owner_type", "owner_name"], dropna=False)
        .agg(
            task_count=("id", "count"),
            goal_count=("is_goal", "sum"),
            metric_count=("is_metric", "sum"),
            high_count=("priority", lambda s: int(s.astype(str).eq("High").sum())),
        )
        .reset_index()
        .sort_values(["owner_type", "owner_name"])
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("对象数", len(summary))
    c2.metric("管理目标", int(summary["goal_count"].sum()))
    c3.metric("量化指标", int(summary["metric_count"].sum()))

    for _, row in summary.iterrows():
        owner_type = str(row.get("owner_type") or "")
        owner_name = str(row.get("owner_name") or "")
        owner_tasks = tasks_df[
            tasks_df["owner_type"].astype(str).eq(owner_type)
            & tasks_df["owner_name"].astype(str).eq(owner_name)
        ].copy()
        title = (
            f"{owner_name or '(未指定对象)'} | {owner_type} | "
            f"{int(row['goal_count'])} 个管理目标 / {int(row['metric_count'])} 个量化指标"
        )
        with st.expander(title, expanded=False):
            goals = owner_tasks[owner_tasks["metric_key"].astype(str).eq("management_goal")].copy()
            metrics = owner_tasks[~owner_tasks["metric_key"].astype(str).eq("management_goal")].copy()
            if not goals.empty:
                st.markdown("**管理目标**")
                goal_cols = [
                    "meeting_month",
                    "goal_type",
                    "target_customer",
                    "target_domain",
                    "target_position",
                    "goal_direction",
                    "weekly_check_day",
                    "next_check_date",
                    "priority",
                    "status",
                ]
                st.dataframe(goals[[c for c in goal_cols if c in goals.columns]], use_container_width=True, hide_index=True)
            if not metrics.empty:
                st.markdown("**量化指标**")
                metric_display = _display_tasks(metrics)
                metric_cols = [
                    "meeting_month",
                    "theme",
                    "task",
                    "metric",
                    "operator",
                    "target_value",
                    "period_start",
                    "period_end",
                    "priority",
                    "status",
                ]
                st.dataframe(metric_display[[c for c in metric_cols if c in metric_display.columns]], use_container_width=True, hide_index=True)


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
        "goal_type",
        "target_customer",
        "target_domain",
        "target_position",
        "weekly_check_day",
        "next_check_date",
        "progress_note",
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


def _is_duplicate_task(existing: pd.DataFrame, payload: Dict[str, object]) -> bool:
    if existing is None or existing.empty:
        return False
    work = existing.copy()
    checks = {
        "meeting_month": str(payload.get("meeting_month") or ""),
        "owner_type": str(payload.get("owner_type") or ""),
        "owner_name": str(payload.get("owner_name") or ""),
        "metric_key": str(payload.get("metric_key") or ""),
        "operator": str(payload.get("operator") or ""),
        "period_start": str(payload.get("period_start") or ""),
        "period_end": str(payload.get("period_end") or ""),
        "status": str(payload.get("status") or "active"),
    }
    mask = pd.Series(True, index=work.index)
    for col, value in checks.items():
        if col not in work.columns:
            return False
        mask &= work[col].fillna("").astype(str).eq(value)
    if str(payload.get("metric_key") or "") == "management_goal" and "task" in work.columns:
        mask &= work["task"].fillna("").astype(str).eq(str(payload.get("task") or ""))
    target = pd.to_numeric(work.get("target_value"), errors="coerce").fillna(0)
    mask &= (target - float(payload.get("target_value") or 0)).abs() < 0.000001
    return bool(mask.any())


def _build_goal_task_text(goal_type: str, customer: str, domain: str, position: str, direction: str) -> str:
    parts = [str(goal_type or "").strip()]
    if customer:
        parts.append(f"客户：{customer}")
    if domain:
        parts.append(f"领域：{domain}")
    if position:
        parts.append(f"岗位：{position}")
    if direction:
        parts.append(f"方向：{direction}")
    return " | ".join([part for part in parts if part])


def _next_weekly_check_date(day_label: str) -> str:
    weekday_map = {"周一": 0, "周二": 1, "周三": 2, "周四": 3, "周五": 4}
    target = weekday_map.get(str(day_label), 0)
    today = pd.Timestamp.today().normalize()
    delta = (target - today.weekday()) % 7
    if delta == 0:
        delta = 7
    return (today + pd.Timedelta(days=delta)).date().isoformat()


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
