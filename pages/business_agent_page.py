"""Business Analyst agent page."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from modules.business_agent import QUICK_QUESTIONS, answer_business_question
from modules.business_toolkit import BusinessAnalysisToolkit


def render_business_agent(context: dict) -> None:
    st.markdown("### 经营分析助手")
    st.caption(
        "Agent MVP：只调用当前系统已验证的经营分析工具，不联网搜索，不自由写SQL。"
        "回答中的数字来自三速模型、现金流模型、顾问成本、Offer结果、Pipeline和应收数据。"
    )

    _render_proactive_outlook(context)

    st.markdown("#### 向 Business Analyst 提问")
    question = st.text_area(
        "问题",
        value=st.session_state.get("business_agent_question", "未来哪个月可能回款爆发，哪个月可能低产或收支不平衡？"),
        height=96,
        placeholder="例如：未来哪个月现金压力最大？Lucy 和 Amber 的产能差异在哪里？哪些客户回款风险最高？",
    )

    cols = st.columns(4)
    for idx, question_text in enumerate(QUICK_QUESTIONS):
        if cols[idx % 4].button(question_text, use_container_width=True):
            st.session_state["business_agent_question"] = question_text
            question = question_text

    if st.button("分析", type="primary"):
        st.session_state["business_agent_question"] = question
        with st.spinner("Business Analyst 正在调用分析工具..."):
            st.session_state["business_agent_result"] = answer_business_question(question, context)

    result = st.session_state.get("business_agent_result")
    if not result:
        st.info("可以直接输入自由问题，或点击上方常用问题。系统会自动选择工具、输出判断和证据。")
        return

    st.markdown(result["answer"])

    with st.expander("工具调用与证据", expanded=False):
        st.write("调用工具：", ", ".join(result.get("tools", [])))
        for item in result.get("evidence", []):
            st.markdown(f"#### {item.get('tool')}")
            st.caption(item.get("definition", ""))
            for key, value in item.items():
                if key in ("tool", "definition"):
                    continue
                if isinstance(value, list):
                    if value:
                        st.dataframe(pd.DataFrame(value), use_container_width=True, hide_index=True)
                    else:
                        st.write(f"{key}: 无数据")
                elif isinstance(value, dict):
                    st.json(value)
                else:
                    st.write(f"{key}: {value}")


def _render_proactive_outlook(context: dict) -> None:
    toolkit = BusinessAnalysisToolkit(context)
    outlook = toolkit.business_outlook()
    facts = outlook.get("facts", {})
    st.markdown("#### 主动经营洞察")
    c1, c2, c3 = st.columns(3)
    c1.metric("预测覆盖月份", f"{int(facts.get('months_covered', 0))}")
    c2.metric("月净现金为负", f"{int(facts.get('negative_net_months', 0))} 月")
    c3.metric("月末余额为负", f"{int(facts.get('negative_balance_months', 0))} 月")

    burst = pd.DataFrame(outlook.get("likely_burst_months", []))
    weak = pd.DataFrame(outlook.get("low_or_imbalanced_months", []))
    left, right = st.columns(2)
    with left:
        st.markdown("##### 可能回款爆发月")
        _show_month_table(burst)
    with right:
        st.markdown("##### 低产/收支承压月")
        _show_month_table(weak)


def _show_month_table(df: pd.DataFrame) -> None:
    if df is None or df.empty:
        st.write("暂无数据")
        return
    cols = [c for c in ["month", "confirmed_inflow", "forecast_inflow", "total_inflow", "outflow", "net_cash", "ending_balance", "risk_level", "signal"] if c in df.columns]
    st.dataframe(df[cols], use_container_width=True, hide_index=True)
