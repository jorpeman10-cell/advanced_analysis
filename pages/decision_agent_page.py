"""Unified decision Agent page for the v2 dashboard."""

from __future__ import annotations

from typing import Dict, List

import pandas as pd
import streamlit as st

from modules.business_agent import QUICK_QUESTIONS, run_business_agent
from modules.business_toolkit import BusinessAnalysisToolkit
from pages.v2_dashboard import (
    AI_PROVIDER_PRESETS,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TIMEOUT,
    _diagnose_issues,
    _get_ai_api_key,
    _management_actions,
    _masked_key,
    _ninety_day_plan,
    _strategic_summary,
    safe_df,
)


TOOL_OPTIONS = {
    "公司快照": "company_snapshot",
    "未来经营趋势": "business_outlook",
    "现金流预测": "cashflow_forecast",
    "顾问成本": "consultant_cost",
    "顾问经营画像": "consultant_performance",
    "Offer 结果": "offer_outcomes",
    "Pipeline 预测": "pipeline_forecast",
    "新增项目": "project_additions",
    "转化效率": "conversion_efficiency",
}


AGENT_PROMPTS = [
    "未来90天公司最大的经营风险是什么？先给结论，再列证据和动作。",
    "哪些顾问需要重点管理？请区分成本压力、Offer余粮和Forecast覆盖。",
    "接下来哪几个月可能回款爆发，哪几个月需要提前控成本？",
    "新增项目不少但Offer少的问题主要在哪些团队或顾问？",
    "如果我要保证现金流安全，下周应该盯哪几个客户、发票或顾问？",
    "请把当前经营问题整理成管理层周会的3个议题。",
]


DEFAULT_AGENT_PROVIDER = "Kimi / Moonshot CN"
DEFAULT_AGENT_MODEL = "kimi-k2.5"
DEFAULT_AGENT_BASE_URL = "https://api.moonshot.cn/v1"
DEFAULT_AGENT_TEMPERATURE = 1.0
DEFAULT_AGENT_MAX_TOKENS = 3200
DEFAULT_AGENT_TIMEOUT = 90
AGENT_CONFIG_VERSION = "agent-config-2026-05-08-v2"


def _init_agent_config_defaults() -> None:
    st.session_state.setdefault("decision_agent_provider", DEFAULT_AGENT_PROVIDER)
    st.session_state.setdefault("decision_agent_model", DEFAULT_AGENT_MODEL)
    st.session_state.setdefault("decision_agent_base_url", DEFAULT_AGENT_BASE_URL)
    st.session_state.setdefault("decision_agent_temperature", DEFAULT_AGENT_TEMPERATURE)
    st.session_state.setdefault("decision_agent_max_tokens", DEFAULT_AGENT_MAX_TOKENS)
    st.session_state.setdefault("decision_agent_timeout", DEFAULT_AGENT_TIMEOUT)


def _option_index(options: List[str], value: str, default: int = 0) -> int:
    return options.index(value) if value in options else default


def render_decision_agent(context: Dict[str, object]) -> None:
    st.markdown("### 经营决策 Agent")
    st.caption(
        "把原来的决策建议和经营分析助手合并为一个可追问的经营 Agent。"
        "Agent 先调用当前页面已经计算好的三速模型、现金流、成本、Pipeline、Offer 和项目数据，再决定是否交给模型做综合判断。"
    )

    conversion = context["conversion"]
    cost = context["cost"]
    cashflow = context["cashflow"]
    project_additions = context.get("project_additions", {})
    issues = _diagnose_issues(conversion, cost, cashflow, project_additions)

    _render_agent_brief(context, issues)
    _render_action_queue(conversion, cost, cashflow)
    _render_agent_console(context, issues)


def _render_agent_brief(context: Dict[str, object], issues: List[Dict[str, object]]) -> None:
    toolkit = BusinessAnalysisToolkit(context)
    outlook = toolkit.business_outlook()
    facts = outlook.get("facts", {})
    health = context.get("health", {})
    cash_summary = context.get("cashflow", {}).get("summary", {})

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("综合健康分", f"{float(health.get('overall_score') or 0):.1f}", health.get("overall_status", "-"))
    c2.metric("问题队列", f"{len(issues)} 个", "High 优先" if any(i.get("优先级") == "High" for i in issues) else "可控")
    c3.metric("90天现金余额", _money(cash_summary.get("balance_90d")))
    c4.metric("负净现金月份", f"{int(facts.get('negative_net_months', 0))} 个")

    st.markdown("#### Agent 已读取的经营事实")
    left, right = st.columns([1, 1])
    with left:
        for item in _strategic_summary(
            context["conversion"],
            context["cost"],
            context["cashflow"],
            context.get("project_additions", {}),
        ):
            level = item.get("level")
            if level == "High":
                st.error(item.get("message"))
            elif level == "Medium":
                st.warning(item.get("message"))
            else:
                st.info(item.get("message"))
    with right:
        issue_df = pd.DataFrame(issues)
        if issue_df.empty:
            st.success("当前没有进入高优先级的问题源。")
        else:
            st.dataframe(safe_df(issue_df.head(8)), use_container_width=True, hide_index=True)


def _render_action_queue(conversion, cost, cashflow) -> None:
    with st.expander("行动队列与90天计划", expanded=True):
        left, right = st.columns([1.1, 1])
        with left:
            st.markdown("##### 管理动作")
            st.dataframe(safe_df(pd.DataFrame(_management_actions(conversion, cost, cashflow))), use_container_width=True, hide_index=True)
        with right:
            st.markdown("##### 90天重点")
            st.dataframe(safe_df(pd.DataFrame(_ninety_day_plan())), use_container_width=True, hide_index=True)


def _render_agent_console(context: Dict[str, object], issues: List[Dict[str, object]]) -> None:
    st.markdown("#### 对话式经营分析")
    _init_agent_config_defaults()
    st.caption(f"Agent config version: {AGENT_CONFIG_VERSION} | 默认自动读取 MOONSHOT_API_KEY，页面 Key 仅作临时覆盖")

    provider_names = list(AI_PROVIDER_PRESETS.keys())
    saved_provider = st.session_state.get("decision_agent_provider", DEFAULT_AGENT_PROVIDER)
    if saved_provider not in provider_names:
        saved_provider = DEFAULT_AGENT_PROVIDER if DEFAULT_AGENT_PROVIDER in provider_names else provider_names[0]

    with st.expander("模型与工具配置", expanded=False):
        provider = st.selectbox(
            "服务商",
            provider_names,
            index=_option_index(provider_names, saved_provider),
            key="decision_agent_provider_select",
        )
        preset = AI_PROVIDER_PRESETS[provider]
        model_options = preset["models"] + (["自定义"] if "自定义" not in preset["models"] else [])
        saved_model = st.session_state.get("decision_agent_model", DEFAULT_AGENT_MODEL)
        selected_model = st.selectbox(
            "Model",
            model_options,
            index=_option_index(model_options, saved_model),
            key="decision_agent_model_select",
        )
        model = (
            st.text_input("自定义 Model", value=st.session_state.get("decision_agent_custom_model", ""))
            if selected_model == "自定义"
            else selected_model
        )
        base_url = st.text_input(
            "Base URL",
            value=st.session_state.get("decision_agent_base_url", preset["base_url"]),
            key="decision_agent_base_url_input",
        )
        use_llm = True
        stored_key, stored_source = _get_ai_api_key(provider, "")
        if stored_key:
            st.success(f"已自动读取模型 Key：{stored_source} / {_masked_key(stored_key)}")
        else:
            st.warning("未读取到默认 API Key。请在 Streamlit Secrets 配置 MOONSHOT_API_KEY，或临时填写下方覆盖 Key。")
        st.info("经营 Agent 已设为强模型模式：工具只负责取数和证据，最终回答必须由 LLM 生成。")
        api_key = st.text_input(
            "API Key 覆盖（可选）",
            value="",
            type="password",
            help="通常不用填写；默认读取 Streamlit Secrets / 环境变量中的 MOONSHOT_API_KEY。页面输入只作为临时覆盖，不写入文件。",
        )
        col1, col2, col3 = st.columns(3)
        with col1:
            temperature = st.number_input(
                "Temperature",
                min_value=0.0,
                max_value=2.0,
                value=float(st.session_state.get("decision_agent_temperature", DEFAULT_AGENT_TEMPERATURE)),
                step=0.1,
            )
        with col2:
            max_tokens = st.number_input(
                "Max tokens",
                min_value=800,
                max_value=16000,
                value=int(st.session_state.get("decision_agent_max_tokens", max(3200, int(DEFAULT_MAX_TOKENS)))),
                step=400,
            )
        with col3:
            timeout = st.number_input(
                "Timeout seconds",
                min_value=30,
                max_value=600,
                value=int(st.session_state.get("decision_agent_timeout", max(90, int(DEFAULT_TIMEOUT)))),
                step=30,
            )

        auto_tools = st.toggle("Agent 自动选择工具", value=True)
        chosen_labels = st.multiselect(
            "手动指定工具",
            list(TOOL_OPTIONS.keys()),
            default=list(TOOL_OPTIONS.keys())[:4],
            disabled=auto_tools,
        )

    st.session_state["decision_agent_provider"] = provider
    st.session_state["decision_agent_model"] = model
    st.session_state["decision_agent_custom_model"] = model if selected_model == "自定义" else st.session_state.get("decision_agent_custom_model", "")
    st.session_state["decision_agent_base_url"] = base_url
    st.session_state["decision_agent_temperature"] = float(temperature)
    st.session_state["decision_agent_max_tokens"] = int(max_tokens)
    st.session_state["decision_agent_timeout"] = int(timeout)

    if "decision_agent_messages" not in st.session_state:
        st.session_state["decision_agent_messages"] = []

    prompt_cols = st.columns(3)
    for idx, prompt in enumerate(AGENT_PROMPTS):
        if prompt_cols[idx % 3].button(prompt, use_container_width=True, key=f"agent_prompt_{idx}"):
            _run_agent_turn(
                prompt,
                context,
                provider,
                base_url,
                model,
                api_key,
                use_llm,
                temperature,
                max_tokens,
                timeout,
                None if auto_tools else [TOOL_OPTIONS[label] for label in chosen_labels],
            )

    for message in st.session_state["decision_agent_messages"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("evidence"):
                with st.expander("工具调用与证据", expanded=False):
                    st.write("调用工具：", ", ".join(message.get("tools", [])))
                    for item in message["evidence"]:
                        st.markdown(f"##### {item.get('tool')}")
                        st.caption(item.get("definition", ""))
                        _render_evidence_item(item)

    question = st.chat_input("问经营问题，例如：下周管理层应该先处理哪三个风险？")
    if question:
        _run_agent_turn(
            question,
            context,
            provider,
            base_url,
            model,
            api_key,
            use_llm,
            temperature,
            max_tokens,
            timeout,
            None if auto_tools else [TOOL_OPTIONS[label] for label in chosen_labels],
        )
        st.rerun()


def _run_agent_turn(
    question: str,
    context: Dict[str, object],
    provider: str,
    base_url: str,
    model: str,
    api_key: str,
    use_llm: bool,
    temperature: float,
    max_tokens: int,
    timeout: int,
    selected_tools: List[str] | None,
) -> None:
    st.session_state["decision_agent_messages"].append({"role": "user", "content": question})
    key, key_source = _get_ai_api_key(provider, api_key)
    if not key:
        default_provider = st.session_state.get("decision_agent_provider", DEFAULT_AGENT_PROVIDER)
        key, key_source = _get_ai_api_key(default_provider, "")
    if not key:
        st.session_state["decision_agent_messages"].append(
            {
                "role": "assistant",
                "content": (
                    f"**未调用 LLM：没有读取到 API Key。当前默认模型：{model}**\n\n"
                    "经营 Agent 是强模型模式，不会退回到简单工具调用。请在 Streamlit Secrets 配置 "
                    "`MOONSHOT_API_KEY`，或在模型配置中临时填写覆盖 Key。"
                ),
            }
        )
        return

    llm_config = {
        "api_key": key,
        "base_url": base_url,
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "timeout": timeout,
    }

    try:
        with st.spinner("Agent 正在选择工具、读取证据并调用模型生成判断..."):
            result = run_business_agent(
                question,
                context,
                selected_tools=selected_tools,
                llm_config=llm_config,
                chat_history=st.session_state["decision_agent_messages"],
            )
        source_text = f"\n\n`LLM called: provider={provider} | base_url={base_url} | model={model} | key_source={key_source or '-'} | key={_masked_key(key)}`"
        answer_text = f"**本次调用的 LLM 模型：{model}**\n\n{result['answer']}"
        st.session_state["decision_agent_messages"].append(
            {
                "role": "assistant",
                "content": answer_text + source_text,
                "tools": result.get("tools", []),
                "evidence": result.get("evidence", []),
            }
        )
    except Exception as exc:
        st.session_state["decision_agent_messages"].append(
            {
                "role": "assistant",
                "content": f"Agent 生成失败：{exc}\n\n问题已保留。请检查模型 Key、Base URL、模型名或 token 限制后重试。",
            }
        )


def _render_evidence_item(item: Dict[str, object]) -> None:
    for key, value in item.items():
        if key in ("tool", "definition"):
            continue
        if isinstance(value, list):
            if value:
                st.dataframe(pd.DataFrame(value), use_container_width=True, hide_index=True)
            else:
                st.caption(f"{key}: 无数据")
        elif isinstance(value, dict):
            st.json(value)
        else:
            st.write(f"{key}: {value}")


def _money(value) -> str:
    if value is None or pd.isna(value):
        return "-"
    amount = float(value)
    if abs(amount) >= 10000:
        return f"¥{amount / 10000:,.1f}万"
    return f"¥{amount:,.0f}"
