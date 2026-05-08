"""MVP business analyst agent orchestration.

The agent routes natural-language questions to whitelisted deterministic tools.
It does not run free SQL and does not use external web search.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Dict, List

import pandas as pd

from modules.business_toolkit import BusinessAnalysisToolkit, format_tool_result


QUICK_QUESTIONS = [
    "未来哪个月可能回款爆发，哪个月可能低产或收支不平衡？",
    "未来180天现金余额最低点会出现在哪个月？",
    "确认应收和Forecast分别支撑哪些月份的现金流？",
    "哪些顾问表现最好，哪些需要管理关注？",
    "公司当前经营健康度如何？",
    "未来90天现金流安全吗？",
    "哪些顾问成本压力最大？",
    "2025遗留应收有哪些？",
    "Offer到回款转化表现如何？",
    "Pipeline里哪些预测收入最关键？",
    "新增项目多但Offer少的问题在哪？",
    "项目推进效率的主要短板是什么？",
]


def answer_business_question(question: str, context: Dict[str, object]) -> Dict[str, object]:
    toolkit = BusinessAnalysisToolkit(context)
    tools = _select_tools(question)
    tool_results = [_call_tool(toolkit, name) for name in tools]
    return {
        "question": question,
        "tools": tools,
        "answer": _compose_answer(question, tool_results),
        "evidence": tool_results,
    }


def run_business_agent(
    question: str,
    context: Dict[str, object],
    selected_tools: List[str] | None = None,
    llm_config: Dict[str, object] | None = None,
    chat_history: List[Dict[str, str]] | None = None,
) -> Dict[str, object]:
    """Run tools for evidence, then require an LLM to synthesize the answer."""
    toolkit = BusinessAnalysisToolkit(context)
    consultant_focus = _detect_consultant_focus(question, context)
    if consultant_focus:
        tools = [
            "consultant_detail",
            "consultant_performance",
            "consultant_cost",
            "pipeline_forecast",
            "offer_outcomes",
            "conversion_efficiency",
            "project_additions",
        ]
        if selected_tools:
            tools.extend(selected_tools)
    else:
        tools = ["company_snapshot", "cashflow_forecast", "business_outlook"] + (selected_tools or _select_tools(question))
    tools = _dedupe_tools(tools)[:8]
    tool_results = [_call_tool(toolkit, name, context=context, consultant_names=consultant_focus) for name in tools]
    if not llm_config or not llm_config.get("api_key"):
        raise ValueError("LLM is required for Business Agent. Please provide an API Key.")

    result = {
        "question": question,
        "tools": tools,
        "answer": _generate_required_llm_agent_answer(
            question=question,
            tool_results=tool_results,
            llm_config=llm_config,
            chat_history=chat_history or [],
            consultant_focus=consultant_focus,
        ),
        "evidence": tool_results,
        "mode": "agent",
    }
    return result


def _select_tools(question: str) -> List[str]:
    q = (question or "").lower()
    selected: List[str] = []

    if any(k in q for k in ["未来", "月份", "哪个月", "爆发", "低产", "收支", "不平衡", "趋势", "预测", "最低点", "cash low", "burst", "trend"]):
        selected.append("business_outlook")
    if any(k in q for k in ["顾问", "consultant", "画像", "综合表现", "余粮", "潜力", "产能", "能力", "态度"]):
        selected.append("consultant_performance")
    if any(k in q for k in ["现金", "跑道", "90", "180", "回款", "逾期", "遗留", "应收"]):
        selected.append("cashflow_forecast")
    if any(k in q for k in ["成本", "顾问", "薪资", "产能", "效率"]):
        selected.append("consultant_cost")
    if any(k in q for k in ["offer", "入职", "试用", "交易", "转化"]):
        selected.append("offer_outcomes")
    if any(k in q for k in ["forecast", "pipeline", "预测"]):
        selected.append("pipeline_forecast")
    if any(k in q for k in ["新增", "项目", "岗位", "bd"]):
        selected.append("project_additions")
    if any(k in q for k in ["推荐", "一面", "面试", "推进", "交付"]):
        selected.append("conversion_efficiency")
    if any(k in q for k in ["健康", "整体", "公司", "经营"]):
        selected.insert(0, "company_snapshot")

    if not selected:
        selected = ["company_snapshot", "business_outlook", "cashflow_forecast", "consultant_cost"]

    return _dedupe_tools(selected)[:5]


def _dedupe_tools(tools: List[str]) -> List[str]:
    deduped: List[str] = []
    for name in tools:
        if name not in deduped:
            deduped.append(name)
    return deduped


def _call_tool(
    toolkit: BusinessAnalysisToolkit,
    name: str,
    context: Dict[str, object] | None = None,
    consultant_names: List[str] | None = None,
) -> Dict[str, object]:
    if name == "consultant_detail":
        return _consultant_detail(context or {}, consultant_names or [])
    if name == "company_snapshot":
        return toolkit.company_snapshot()
    if name == "business_outlook":
        return toolkit.business_outlook()
    if name == "cashflow_forecast":
        return toolkit.cashflow_forecast()
    if name == "consultant_cost":
        return toolkit.consultant_cost()
    if name == "consultant_performance":
        return toolkit.consultant_performance()
    if name == "offer_outcomes":
        return toolkit.offer_outcomes()
    if name == "pipeline_forecast":
        return toolkit.pipeline_forecast()
    if name == "project_additions":
        return toolkit.project_additions()
    if name == "conversion_efficiency":
        return toolkit.conversion_efficiency()
    return {"tool": name, "definition": "Unknown tool"}


def _detect_consultant_focus(question: str, context: Dict[str, object]) -> List[str]:
    q_norm = _norm_text(question)
    if not q_norm:
        return []

    names = _all_consultant_names(context)
    matched: List[str] = []
    for name in names:
        name_norm = _norm_text(name)
        if not name_norm:
            continue
        parts = [part for part in str(name).replace("/", " ").split() if len(part) >= 3]
        part_hit = any(_norm_text(part) in q_norm for part in parts)
        if name_norm in q_norm or part_hit:
            matched.append(name)

    # Avoid treating broad consultant-category questions as a named-consultant ask.
    if not matched and any(word in q_norm for word in ["顾问", "consultant"]):
        return []
    return _dedupe_tools(matched)[:3]


def _all_consultant_names(context: Dict[str, object]) -> List[str]:
    frames: List[pd.DataFrame] = []
    performance = context.get("consultant_performance", {})
    if isinstance(performance, dict):
        frames.append(performance.get("scorecard", pd.DataFrame()))
    cost = context.get("cost", {})
    if isinstance(cost, dict):
        frames.append(cost.get("ranking", pd.DataFrame()))
    conversion = context.get("conversion", {})
    if isinstance(conversion, dict):
        frames.append(conversion.get("consultant_ranking", pd.DataFrame()))
    pipeline = context.get("pipeline", {})
    if isinstance(pipeline, dict):
        frames.append(pipeline.get("by_consultant", pd.DataFrame()))
    offer = context.get("offer_outcomes", {})
    if isinstance(offer, dict):
        frames.append(offer.get("consultant", pd.DataFrame()))
    additions = context.get("project_additions", {})
    if isinstance(additions, dict):
        frames.append(additions.get("consultant", pd.DataFrame()))

    names: List[str] = []
    for df in frames:
        if isinstance(df, pd.DataFrame) and not df.empty and "consultant" in df.columns:
            names.extend([str(x).strip() for x in df["consultant"].dropna().tolist() if str(x).strip()])
    return _dedupe_tools(names)


def _consultant_detail(context: Dict[str, object], consultant_names: List[str]) -> Dict[str, object]:
    return {
        "tool": "consultant_detail",
        "definition": "指定顾问经营画像。只返回用户问题中命中的顾问数据，用于避免把公司整体诊断误当成顾问诊断。",
        "consultants": consultant_names,
        "scorecard": _consultant_records(context.get("consultant_performance", {}).get("scorecard"), consultant_names),
        "cost": _consultant_records(context.get("cost", {}).get("ranking"), consultant_names),
        "conversion": _consultant_records(context.get("conversion", {}).get("consultant_ranking"), consultant_names),
        "pipeline": _consultant_records(context.get("pipeline", {}).get("by_consultant"), consultant_names),
        "offers": _consultant_records(context.get("offer_outcomes", {}).get("consultant"), consultant_names),
        "project_additions": _consultant_records(context.get("project_additions", {}).get("consultant"), consultant_names),
    }


def _consultant_records(df: object, consultant_names: List[str], limit: int = 20) -> List[Dict[str, object]]:
    if not isinstance(df, pd.DataFrame) or df.empty or "consultant" not in df.columns or not consultant_names:
        return []
    wanted = {_norm_text(name) for name in consultant_names}
    work = df[df["consultant"].map(lambda value: _norm_text(value) in wanted)].copy()
    if work.empty:
        return []
    return work.head(limit).where(pd.notna(work), None).to_dict(orient="records")


def _norm_text(value: object) -> str:
    return "".join(str(value or "").strip().lower().split())


def _build_agent_guardrails(tool_results: List[Dict[str, object]]) -> str:
    cash = next((item for item in tool_results if item.get("tool") == "cashflow_forecast"), {})
    cash_facts = cash.get("facts", {}) if isinstance(cash, dict) else {}
    balance_90 = cash_facts.get("balance_90d")
    balance_180 = cash_facts.get("balance_180d")
    runway = cash_facts.get("cash_runway_months")
    confirmed_90 = cash_facts.get("confirmed_inflow_90d")
    forecast_90 = cash_facts.get("forecast_inflow_90d")
    outflow_90 = cash_facts.get("outflow_90d")
    confirmed_180 = cash_facts.get("confirmed_inflow_180d")
    forecast_180 = cash_facts.get("forecast_inflow_180d")
    outflow_180 = cash_facts.get("outflow_180d")

    lines = [
        "现金流判断必须优先使用 90天预期现金余额(balance_90d) 和 180天预期现金余额(balance_180d)，",
        "不能只用节点现金跑道(cash_runway_months)下结论。现金跑道只是静态压力指标。",
        "如果 balance_90d 和 balance_180d 均为正，不得表述为现金流危机、资金将在3个月内枯竭、立即断裂。",
        "此时只能表述为：现金仍为正，但存在回款兑现、成本覆盖或安全边际收窄压力。",
        "不得引用未在工具结果中提供的行业基准或安全线，例如'猎头行业6个月安全警戒线'。",
        "不得把 Forecast 加权收入、Pipeline总额和实际回款混为一谈；必须区分确认应收、Forecast加权回款、Pipeline预测。",
    ]
    if balance_90 is not None or balance_180 is not None:
        lines.append(
            "当前现金事实："
            f"90天余额={balance_90}, 90天确认应收={confirmed_90}, 90天Forecast={forecast_90}, 90天成本={outflow_90}; "
            f"180天余额={balance_180}, 180天确认应收={confirmed_180}, 180天Forecast={forecast_180}, 180天成本={outflow_180}; "
            f"静态现金跑道={runway}个月。"
        )
    return "\n".join(f"- {line}" for line in lines)


def _build_intent_guardrails(question: str, consultant_focus: List[str]) -> str:
    if consultant_focus:
        names = ", ".join(consultant_focus)
        return "\n".join(
            [
                f"- 用户问题命中了具体顾问：{names}。",
                "- 必须以这些顾问为主体回答，直接说明该顾问本月/当前数据情况、风险和动作。",
                "- 不要把公司整体现金流、整体健康分、整体成本收入比作为主结论；只能作为背景补充。",
                "- 优先使用 consultant_detail 工具中的 scorecard、cost、conversion、pipeline、offers、project_additions。",
                "- 如果该顾问某项数据为空，明确说该维度暂无数据，不要用其他顾问或公司整体数据替代。",
            ]
        )
    return "\n".join(
        [
            "- 用户问题未命中具体顾问，可按公司、团队、客户或现金流维度综合回答。",
            "- 如果用户问题看起来像在问某个顾问但没有明确姓名，先说明需要指定顾问姓名，再给可选下钻方向。",
        ]
    )


def _generate_required_llm_agent_answer(
    question: str,
    tool_results: List[Dict[str, object]],
    llm_config: Dict[str, object],
    chat_history: List[Dict[str, str]],
    consultant_focus: List[str] | None = None,
) -> str:
    base_url = str(llm_config.get("base_url") or "").rstrip("/")
    model = str(llm_config.get("model") or "").strip()
    api_key = str(llm_config.get("api_key") or "").strip()
    if not base_url or not model or not api_key:
        raise ValueError("LLM config requires base_url, model and api_key")

    compact_history = [
        {"role": item.get("role", "user"), "content": str(item.get("content", ""))[:1600]}
        for item in chat_history[-6:]
        if item.get("content")
    ]
    guardrails = _build_agent_guardrails(tool_results)
    intent_guardrails = _build_intent_guardrails(question, consultant_focus or [])
    payload = {
        "model": model,
        "temperature": float(llm_config.get("temperature", 1.0)),
        "max_tokens": int(llm_config.get("max_tokens", 3200)),
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是猎头公司经营决策 Agent。系统工具结果是你的数据上下文和知识库，"
                    "但最终回答必须由你综合判断，不要原样罗列工具口径。"
                    "你只能基于工具返回的经营事实回答，不能编造数据，不能说自己直接查询了数据库。"
                    "必须正面回答用户问题，先给结论，再给证据、风险和下一步动作。"
                    "如果证据不足，要明确说明缺口，并给出下一步需要下钻的数据。"
                ),
            },
            *compact_history,
            {
                "role": "user",
                "content": (
                    f"用户问题：{question}\n\n"
                    "系统工具结果 JSON：\n"
                    f"{json.dumps(tool_results, ensure_ascii=False, default=str)}\n\n"
                    f"Intent guardrails:\n{intent_guardrails}\n\n"
                    f"Agent 判断约束：\n{guardrails}\n\n"
                    "请用中文回答，结构必须为：\n"
                    "1. 直接判断：用1-2句话正面回答用户问题\n"
                    "2. 为什么：列出最关键的3-5条证据，不要贴满工具结果\n"
                    "3. 管理动作：给出本周可执行动作\n"
                    "4. 建议追问：给出2-3个自然追问方向"
                ),
            },
        ],
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=int(llm_config.get("timeout", 90))) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"AI service returned HTTP {exc.code}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"AI service request failed: {exc.reason}") from exc

    choices = data.get("choices", [])
    if not choices:
        raise RuntimeError("AI service returned no choices")
    choice = choices[0]
    content = choice.get("message", {}).get("content", "").strip()
    if choice.get("finish_reason") == "length":
        content += "\n\n> 输出被模型长度上限截断。请把 Max tokens 调高后重试，或追问“继续”。"
    return content


def _generate_llm_agent_answer(
    question: str,
    tool_results: List[Dict[str, object]],
    llm_config: Dict[str, object],
    chat_history: List[Dict[str, str]],
) -> str:
    base_url = str(llm_config.get("base_url") or "").rstrip("/")
    model = str(llm_config.get("model") or "").strip()
    api_key = str(llm_config.get("api_key") or "").strip()
    if not base_url or not model or not api_key:
        raise ValueError("LLM config requires base_url, model and api_key")

    compact_history = [
        {"role": item.get("role", "user"), "content": str(item.get("content", ""))[:1600]}
        for item in chat_history[-6:]
        if item.get("content")
    ]
    payload = {
        "model": model,
        "temperature": float(llm_config.get("temperature", 1.0)),
        "max_tokens": int(llm_config.get("max_tokens", 3200)),
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是猎头公司经营决策 Agent。你只能基于系统工具返回的经营事实回答，"
                    "不能编造数据，不能说自己查询了数据库。"
                    "输出要有结论、证据、风险、下一步动作，并主动给出可追问方向。"
                    "如果证据不足，要明确说明缺口。"
                ),
            },
            *compact_history,
            {
                "role": "user",
                "content": (
                    f"用户问题：{question}\n\n"
                    "已调用的系统工具结果 JSON：\n"
                    f"{json.dumps(tool_results, ensure_ascii=False, default=str)}\n\n"
                    "请用中文回答，结构为：\n"
                    "1. 直接判断\n"
                    "2. 关键证据\n"
                    "3. 管理动作\n"
                    "4. 还需要追问/下钻的问题"
                ),
            },
        ],
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=int(llm_config.get("timeout", 90))) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"AI service returned HTTP {exc.code}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"AI service request failed: {exc.reason}") from exc

    choices = data.get("choices", [])
    if not choices:
        raise RuntimeError("AI service returned no choices")
    choice = choices[0]
    content = choice.get("message", {}).get("content", "").strip()
    if choice.get("finish_reason") == "length":
        content += "\n\n> 输出被模型长度上限截断。请把 Max tokens 调高后重试，或追问“继续”。"
    return content


def _compose_answer(question: str, results: List[Dict[str, object]]) -> str:
    lines = [
        "### Business Analyst 回答",
        "",
        f"问题：{question}",
        "",
        "我先调用系统内置分析工具取数，不直接查库、不使用外部搜索。",
        "",
    ]

    outlook = next((r for r in results if r.get("tool") == "business_outlook"), None)
    if outlook:
        lines.extend(_outlook_answer(outlook))
        lines.append("")

    lines.append("### 工具口径与关键数据")
    for result in results:
        lines.append(format_tool_result(result))
        lines.append("")

    lines.extend(
        [
            "### 初步判断",
            _judgement(results),
            "",
            "### 下一步",
            "可以继续追问某个月、某个顾问、团队、客户、发票或Forecast明细；我会继续沿用同一套工具口径下钻。",
        ]
    )
    return "\n".join(lines)


def _outlook_answer(outlook: Dict[str, object]) -> List[str]:
    lines = ["### 预测性趋势判断"]
    burst = outlook.get("likely_burst_months", [])
    weak = outlook.get("low_or_imbalanced_months", [])
    low = outlook.get("cash_low_point_months", [])
    if burst:
        lines.append("- 可能回款爆发月：" + "；".join(_month_brief(x) for x in burst))
    if weak:
        lines.append("- 低产或收支不平衡月：" + "；".join(_month_brief(x) for x in weak))
    if low:
        lines.append("- 现金余额低点：" + "；".join(_balance_brief(x) for x in low))
    lines.append("- 判断口径：确认应收按到期日计入；Forecast按加权金额并按预计成交后约60天计入现金流；成本按顾问月成本日均摊。")
    return lines


def _judgement(results: List[Dict[str, object]]) -> str:
    outlook = next((r for r in results if r.get("tool") == "business_outlook"), None)
    cash = next((r for r in results if r.get("tool") == "cashflow_forecast"), None)
    cost = next((r for r in results if r.get("tool") == "consultant_cost"), None)
    offer = next((r for r in results if r.get("tool") == "offer_outcomes"), None)

    points = []
    if outlook:
        facts = outlook.get("facts", {})
        if facts.get("negative_balance_months", 0):
            points.append("预测周期内出现现金余额为负的月份，需要把确认应收和Forecast兑现按月拆解盯办。")
        elif facts.get("negative_net_months", 0):
            points.append("预测周期内存在月度净现金流为负，但不等于立即断裂；关键看前期余额和后续回款峰值能否覆盖。")
        else:
            points.append("预测周期内未出现月末现金余额为负，重点从回款峰值、低产月份和Forecast兑现节奏管理波动。")
    if cash:
        facts = cash.get("facts", {})
        runway = facts.get("cash_runway_months")
        balance_90 = facts.get("balance_90d")
        if runway is not None and runway < 3:
            points.append("现金跑道低于3个月，需要优先看确认应收回款和成本控制。")
        if balance_90 is not None and balance_90 < 0:
            points.append("90天预期现金余额为负，短期现金风险较高。")
        elif balance_90 is not None:
            points.append("90天预期现金余额为正，但仍需关注Forecast兑现和2025遗留应收。")
    if cost:
        summary = cost.get("summary", {})
        ratio = summary.get("cost_revenue_ratio")
        if ratio is not None and ratio > 0.8:
            points.append("YTD成本收入比偏高，顾问直接成本对利润率形成压力。")
    if offer:
        company = offer.get("company", [])
        if company:
            rate = company[0].get("offer_to_paid_rate")
            if rate is not None and rate < 0.3:
                points.append("Offer到回款转化偏低，需要区分未入职、试用失败、未开票和客户未回款。")
    if not points:
        points.append("当前没有单一工具显示严重异常，建议继续下钻到团队和顾问层面。")
    return "\n".join(f"- {p}" for p in points)


def _month_brief(row: Dict[str, object]) -> str:
    month = row.get("month", "-")
    inflow = row.get("total_inflow", 0) or 0
    net = row.get("net_cash", 0) or 0
    signal = row.get("signal", "")
    return f"{month} 流入{_fmt_money(inflow)}，净现金{_fmt_money(net)}，{signal}"


def _balance_brief(row: Dict[str, object]) -> str:
    month = row.get("month", "-")
    balance = row.get("ending_balance", 0) or 0
    risk = row.get("risk_level", "")
    return f"{month} 期末余额{_fmt_money(balance)}，风险{risk}"


def _fmt_money(value: object) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"RMB {amount / 10000:,.1f}万"
