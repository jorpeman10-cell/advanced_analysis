"""AI expert layer for management-level business analysis.

This module only sends structured, already-computed facts to an
OpenAI-compatible chat endpoint. It does not query the database or change any
deterministic scores.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, Iterable

import pandas as pd


DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TIMEOUT = 60
DEFAULT_MAX_TOKENS = 900


def build_business_context(context: Dict[str, object], issues: Iterable[Dict[str, object]], mode: str = "fast") -> Dict[str, object]:
    conversion = context.get("conversion", {})
    cost = context.get("cost", {})
    cashflow = context.get("cashflow", {})
    ytd = context.get("ytd", {})
    project_additions = context.get("project_additions", {})
    consultant_performance = context.get("consultant_performance", {})
    fast = mode == "fast"

    return {
        "_mode": mode,
        "company_profile": {
            "industry": "医药行业猎头",
            "history_years": 15,
            "strategic_context": [
                "医药行业整体走低，客户招聘需求减少，岗位交付难度增加",
                "行业竞争加剧，费率有收缩压力",
                "公司正在探索 AI 工具和行业专属 AI 招聘专家，以降低顾问成本并提升效率",
                "经营策略倾向于放弃低产出职能和岗位，聚焦利润板块，收拢投资，确保利润率",
            ],
        },
        "three_speed_metrics": {
            "conversion_rates": _clean_mapping(conversion.get("stage_rates", {})),
            "conversion_health": _clean_mapping(conversion.get("health", {})),
            "cost_summary": _clean_mapping(cost.get("summary", {})),
            "cashflow_summary": _clean_mapping(cashflow.get("summary", {})),
            "cost_confidence": cost.get("data_confidence"),
            "cashflow_confidence": cashflow.get("data_confidence"),
        },
        "ytd": {
            "company": _records(ytd.get("company"), limit=8 if fast else 12),
            "team": _records(ytd.get("team"), limit=3 if fast else 12),
            "consultant": _records(ytd.get("consultant"), limit=3 if fast else 15),
        },
        "project_additions": {
            "company": _records(project_additions.get("company"), limit=3),
            "monthly": _records(project_additions.get("monthly"), limit=4 if fast else 12),
            "team": _records(project_additions.get("team"), limit=3 if fast else 12),
            "consultant": _records(project_additions.get("consultant"), limit=3 if fast else 15),
        },
        "rankings_and_risks": {
            "consultant_conversion": _records(conversion.get("consultant_ranking"), limit=3 if fast else 15),
            "consultant_cost": _records(cost.get("ranking"), limit=3 if fast else 15),
            "consultant_360": _records(consultant_performance.get("scorecard"), limit=3 if fast else 15)
            if isinstance(consultant_performance, dict)
            else [],
            "client_cashflow_risk": _records(cashflow.get("client_risk"), limit=3 if fast else 12),
            "overdue_orders": _records(cashflow.get("overdue_orders"), limit=3 if fast else 12),
            "rule_based_issues": list(issues)[:5 if fast else 20],
        },
    }


def generate_expert_analysis(
    business_context: Dict[str, object],
    api_key: str,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE_URL,
    temperature: float = 1.0,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    api_key = (api_key or "").strip()
    if not api_key:
        raise ValueError("API Key is required")
    base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
    model = (model or DEFAULT_MODEL).strip()

    payload = {
        "model": model,
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是一名医药行业猎头公司经营管理专家，也理解 AI 招聘产品转型。"
                    "你必须基于用户提供的结构化经营数据分析，不得编造不存在的数据。"
                    "输出要像给老板看的经营诊断，清楚指出主矛盾、问题源、证据和管理动作。"
                ),
            },
            {
                "role": "user",
                "content": _prompt(business_context),
            },
        ],
    }

    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"AI service returned HTTP {exc.code}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"AI service request failed: {exc.reason}") from exc

    choices = data.get("choices", [])
    if not choices:
        raise RuntimeError("AI service returned no choices")
    return choices[0].get("message", {}).get("content", "").strip()


def _prompt(business_context: Dict[str, object]) -> str:
    if business_context.get("_mode") == "fast":
        return (
            "请基于以下结构化经营数据，输出中文快速经营诊断。要求不超过800字，禁止编造数据。\n"
            "固定格式：\n"
            "1. 一句话判断\n"
            "2. 最关键的3个证据\n"
            "3. 业务过程问题：只看推荐到Offer、面试到Offer等过程指标，不把推荐到回款作为顾问过程评价\n"
            "4. 财务/现金问题：只看回款、逾期、现金余额和成本覆盖\n"
            "5. 下周3个动作\n\n"
            "约束：语气克制；不得使用灾难化表达；现金跑道只是静态压力指标；未到预计入职日的Offer不作为入职失败。\n\n"
            f"经营数据 JSON:\n{json.dumps(business_context, ensure_ascii=False, default=str)}"
        )
    return (
        "请基于以下结构化经营数据，输出中文经营专家分析。格式固定为：\n"
        "1. 一句话经营判断\n"
        "2. 当前主矛盾\n"
        "3. 三速匹配分析：项目推进效率、顾问成本、现金流之间的关系\n"
        "4. 关键问题源：按顾问、团队、客户或业务环节列出，必须引用数据证据\n"
        "5. 管理动作：短期止血、中期提效、长期转型\n"
        "6. AI 招聘专家产品化建议：优先落地的 3 个场景\n"
        "7. 下周优先级清单\n\n"
        "重要约束：\n"
        "- 语气必须克制、客观、管理咨询风格，不要使用“死亡交叉”“现金流断裂”“崩坏”等灾难化措辞。\n"
        "- 现金跑道 = 节点现金余额 / 月成本，只是静态压力指标；必须同时参考确认应收、已Offer未回款、Forecast加权流入、90天/180天预期现金余额和后续成本。\n"
        "- 不得把未来30天到期应收解释为付款支出；它是尚未回款的应收压力。\n"
        "- 只有当90天或180天预期现金余额为负，才可以判断为现金流缺口；否则只能表述为安全边际、回款兑现和成本覆盖压力。\n"
        "- 不要声称行业基准，除非输入数据中明确提供；如需使用20%、80%等阈值，必须说明这是当前模型健康线或管理假设。\n"
        "- 顾问评价以客观经营指标为主：已回款利润、Offer余粮月份、Forecast覆盖月份、过程转化风险；不要用单一分数判断好坏。\n"
        "- 不要泛泛而谈；不要改写指标定义；如果数据不足，要明确指出缺口。\n\n"
        f"经营数据 JSON：\n{json.dumps(business_context, ensure_ascii=False, default=str)}"
    )


def _records(value: Any, limit: int = 20) -> list:
    if not isinstance(value, pd.DataFrame) or value.empty:
        return []
    clean = value.head(limit).copy()
    for col in clean.columns:
        if pd.api.types.is_datetime64_any_dtype(clean[col]):
            clean[col] = clean[col].dt.strftime("%Y-%m-%d")
    return json.loads(clean.where(pd.notna(clean), None).to_json(orient="records", force_ascii=False))


def _clean_mapping(value: Any) -> Dict[str, object]:
    if not isinstance(value, dict):
        return {}
    result = {}
    for key, item in value.items():
        if isinstance(item, (int, float, str, bool)) or item is None:
            result[key] = item
        elif not isinstance(item, (dict, list, tuple, set)) and pd.isna(item):
            result[key] = None
        else:
            result[key] = str(item)
    return result
