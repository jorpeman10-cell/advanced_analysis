"""Execution follow-up tasks and metric checkers for monthly management reviews."""

from __future__ import annotations

import json
import re
import uuid
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pandas as pd


CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "execution_followups.json"


METRIC_DEFINITIONS = {
    "new_bd_clients": {"label": "BD新增客户数", "unit": "count", "default_operator": ">="},
    "new_case_bd": {"label": "新增Case BD数", "unit": "count", "default_operator": ">="},
    "new_projects": {"label": "新增岗位/项目数", "unit": "count", "default_operator": ">="},
    "new_referrals": {"label": "新增推荐数", "unit": "count", "default_operator": ">="},
    "avg_referrals_per_project": {"label": "平均推荐量", "unit": "count", "default_operator": ">="},
    "new_interviews": {"label": "新增面试数", "unit": "count", "default_operator": ">="},
    "referral_to_interview_rate": {"label": "推面比", "unit": "percent", "default_operator": ">="},
    "interview_to_offer_rate": {"label": "一面到Offer", "unit": "percent", "default_operator": ">="},
    "new_offers": {"label": "新增Offer数", "unit": "count", "default_operator": ">="},
    "offer_unpaid_amount": {"label": "总未回款储备", "unit": "money", "default_operator": "<="},
    "collection_amount": {"label": "回款金额", "unit": "money", "default_operator": ">="},
    "weighted_forecast": {"label": "Forecast加权金额", "unit": "money", "default_operator": ">="},
}

OWNER_TYPES = {
    "consultant": "顾问",
    "team": "团队",
    "company": "公司",
}

OPERATORS = [">=", "<=", "="]


def _empty_store() -> Dict[str, list]:
    return {"tasks": []}


def load_tasks() -> pd.DataFrame:
    if not CONFIG_PATH.exists():
        return pd.DataFrame(columns=_task_columns())
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return pd.DataFrame(columns=_task_columns())
    tasks = data.get("tasks", [])
    df = pd.DataFrame(tasks)
    for col in _task_columns():
        if col not in df.columns:
            df[col] = None
    return df[_task_columns()]


def save_tasks(df: pd.DataFrame) -> int:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if df is None or df.empty:
        CONFIG_PATH.write_text(json.dumps(_empty_store(), ensure_ascii=False, indent=2), encoding="utf-8")
        return 0
    work = df.copy()
    for col in _task_columns():
        if col not in work.columns:
            work[col] = None
    records = work[_task_columns()].fillna("").to_dict(orient="records")
    CONFIG_PATH.write_text(json.dumps({"tasks": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(records)


def add_task(payload: Dict[str, object]) -> Dict[str, object]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    task = {
        "id": payload.get("id") or str(uuid.uuid4()),
        "meeting_month": str(payload.get("meeting_month") or ""),
        "owner_type": str(payload.get("owner_type") or "consultant"),
        "owner_name": str(payload.get("owner_name") or ""),
        "theme": str(payload.get("theme") or ""),
        "task": str(payload.get("task") or ""),
        "metric_key": str(payload.get("metric_key") or ""),
        "operator": str(payload.get("operator") or ">="),
        "target_value": float(payload.get("target_value") or 0),
        "period_start": str(payload.get("period_start") or ""),
        "period_end": str(payload.get("period_end") or ""),
        "priority": str(payload.get("priority") or "Medium"),
        "status": str(payload.get("status") or "active"),
        "notes": str(payload.get("notes") or ""),
        "source_text": str(payload.get("source_text") or ""),
        "goal_type": str(payload.get("goal_type") or ""),
        "target_customer": str(payload.get("target_customer") or ""),
        "target_domain": str(payload.get("target_domain") or ""),
        "target_position": str(payload.get("target_position") or ""),
        "goal_direction": str(payload.get("goal_direction") or ""),
        "weekly_check_day": str(payload.get("weekly_check_day") or ""),
        "next_check_date": str(payload.get("next_check_date") or ""),
        "progress_note": str(payload.get("progress_note") or ""),
        "created_at": str(payload.get("created_at") or now),
        "updated_at": now,
    }
    df = load_tasks()
    df = pd.concat([df, pd.DataFrame([task])], ignore_index=True)
    save_tasks(df)
    return task


def delete_tasks(task_ids: Iterable[str]) -> int:
    ids = {str(x) for x in task_ids if str(x)}
    df = load_tasks()
    if df.empty or not ids:
        return 0
    before = len(df)
    df = df[~df["id"].astype(str).isin(ids)].copy()
    save_tasks(df)
    return before - len(df)


def parse_management_tasks(text: str, consultants: Iterable[str], config: Dict[str, object]) -> List[Dict[str, object]]:
    """Rule-first parser for common management tasks.

    The parser intentionally maps text only to supported metric keys. It does
    not invent new metrics; ambiguous items should be edited in the UI before
    saving.
    """
    text = str(text or "").strip()
    if not text:
        return []

    owner_name, confidence = _match_owner(text, consultants)
    period_start, period_end = _infer_period(text, config)
    meeting_month = str(config.get("end_date") or "")[:7]
    candidates = [
        ("new_case_bd", [r"Case\s*BD\s*(\d+)", r"新增\s*Case\s*BD\s*(\d+)", r"新增.*?BD.*?Case\s*(\d+)"]),
        ("new_bd_clients", [r"BD\s*(\d+)\s*家客户", r"BD\s*客户\s*(\d+)", r"客户\s*(\d+)\s*家"]),
        ("new_projects", [r"新增.*?岗位\s*(\d+)", r"新增.*?项目\s*(\d+)", r"岗位\s*(\d+)\s*个"]),
        ("new_referrals", [r"推荐\s*(\d+)", r"简历\s*(\d+)"]),
        ("avg_referrals_per_project", [r"平均.*?岗位.*?推荐.*?(\d+)", r"平均推荐量\s*(\d+)", r"每.*?岗位.*?推荐.*?(\d+)", r"岗位推荐.*?(\d+)"]),
        ("new_interviews", [r"面试\s*(\d+)", r"一面\s*(\d+)"]),
        ("referral_to_interview_rate", [r"推面比.*?(\d+(?:\.\d+)?)\s*%", r"推荐到面试.*?(\d+(?:\.\d+)?)\s*%"]),
        ("interview_to_offer_rate", [r"一面到\s*Offer.*?(\d+(?:\.\d+)?)\s*%", r"面试到\s*Offer.*?(\d+(?:\.\d+)?)\s*%"]),
        ("new_offers", [r"Offer\s*(?:新增)?\s*(\d+)", r"新增\s*Offer\s*(\d+)"]),
        ("collection_amount", [r"回款\s*(\d+(?:\.\d+)?)\s*(万)?"]),
        ("weighted_forecast", [r"Forecast\s*(\d+(?:\.\d+)?)\s*(万)?"]),
    ]

    tasks: List[Dict[str, object]] = []
    for metric_key, patterns in candidates:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            value = float(match.group(1))
            unit = METRIC_DEFINITIONS[metric_key]["unit"]
            if unit == "percent":
                value = value / 100.0
            elif len(match.groups()) >= 2 and match.group(2) == "万":
                value = value * 10000.0
            tasks.append(
                {
                    "meeting_month": meeting_month,
                    "owner_type": "consultant" if owner_name else "company",
                    "owner_name": owner_name,
                    "theme": _infer_theme(metric_key),
                    "task": f"{METRIC_DEFINITIONS[metric_key]['label']} {METRIC_DEFINITIONS[metric_key]['default_operator']} {_format_value(value, unit)}",
                    "metric_key": metric_key,
                    "operator": METRIC_DEFINITIONS[metric_key]["default_operator"],
                    "target_value": value,
                    "period_start": period_start,
                    "period_end": period_end,
                    "priority": "Medium",
                    "status": "active",
                    "notes": f"解析置信度: {confidence}",
                    "source_text": text,
                }
            )
            break
    return tasks


def run_task_definition_agent(
    user_message: str,
    chat_history: List[Dict[str, str]],
    consultants: Iterable[str],
    config: Dict[str, object],
    llm_config: Dict[str, object],
) -> Dict[str, object]:
    """Use an LLM to turn management intent into confirmable OKR metric tasks.

    This is intentionally an OKR-definition assistant only. It should clarify
    Objectives and Key Results, but it must not review completion or claim that
    it has checked system results.
    """
    base_url = str(llm_config.get("base_url") or "").rstrip("/")
    model = str(llm_config.get("model") or "").strip()
    api_key = str(llm_config.get("api_key") or "").strip()
    if not base_url or not model or not api_key:
        raise ValueError("OKR task assistant requires base_url, model and api_key")

    metric_specs = [
        {
            "metric_key": key,
            "label": value.get("label"),
            "unit": value.get("unit"),
            "default_operator": value.get("default_operator"),
        }
        for key, value in METRIC_DEFINITIONS.items()
    ]
    consultant_list = [str(x) for x in consultants if str(x).strip()]
    period_start, period_end = _infer_period(user_message, config)
    meeting_month = str(config.get("end_date") or "")[:7]
    compact_history = [
        {"role": item.get("role", "user"), "content": str(item.get("content", ""))[:1200]}
        for item in (chat_history or [])[-8:]
        if item.get("content")
    ]
    okr_skill_prompt = (
        "OKR Coach 方法论：Objective 是方向性目标，必须定性、清晰、有周期边界、团队可影响，"
        "不要把数字写进 Objective；Key Result 是衡量目标是否达成的关键结果，必须 SMART：具体、可衡量、"
        "有目标值或里程碑、有挑战但可达成、与 Objective 直接相关、有时限。"
        "每个 Objective 建议对应2-5个 KR；KR 优先使用指标型，其次里程碑型，尽量避免纯二元任务。"
        "检查 KR 是否只是任务动作：如果只是'拜访客户/整理名单'，应转成可核查的行为数量或结果数量。"
        "信息不足时最多问3个澄清问题，优先补齐对象、周期、指标口径、基线/目标值。"
    )
    system_prompt = (
        "你是猎头公司月会执行跟进的 OKR 任务拆解助手。你的目标不是简单抽取字段，"
        "而是通过对话帮助管理者把月会行动要求澄清成 Objective + 可追踪、可核查的 Key Results。\n"
        f"{okr_skill_prompt}\n"
        "你只能做任务定义，不要核查完成情况，不要声称读取了系统结果。\n"
        "如果信息不足，先提出1-3个具体澄清问题；如果信息足够，输出任务草案。\n"
        "任务草案必须使用给定 metric_key，不要自造指标。对象可以是 consultant/team/company。"
        "JSON里的theme字段写Objective方向，例如'客户结构改善'；task字段写KR或行动指标，例如'BD新增客户数 >= 2'。"
        "金额单位用人民币元，百分比用0-1小数，例如50%写0.5。\n"
        "你必须只返回JSON，不要Markdown。JSON格式："
        "{\"status\":\"clarify|draft\",\"assistant_message\":\"...\","
        "\"tasks\":[{\"owner_type\":\"consultant\",\"owner_name\":\"...\",\"theme\":\"...\","
        "\"task\":\"...\",\"metric_key\":\"new_interviews\",\"operator\":\">=\","
        "\"target_value\":5,\"period_start\":\"YYYY-MM-DD\",\"period_end\":\"YYYY-MM-DD\","
        "\"priority\":\"Medium\",\"notes\":\"...\"}]}"
    )
    payload = {
        "model": model,
        "temperature": float(llm_config.get("temperature", 1.0)),
        "max_tokens": int(llm_config.get("max_tokens", 1800)),
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "meeting_month": meeting_month,
                        "default_period_start": period_start,
                        "default_period_end": period_end,
                        "supported_metrics": metric_specs,
                        "known_consultants": consultant_list[:120],
                        "conversation": compact_history,
                        "latest_user_message": user_message,
                    },
                    ensure_ascii=False,
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

    content = str(data["choices"][0]["message"]["content"]).strip()
    try:
        result = _loads_agent_json(content)
    except Exception:
        fallback_tasks = parse_management_tasks(f"{user_message}\n{content}", consultants, config)
        return {
            "status": "draft" if fallback_tasks else "clarify",
            "assistant_message": (
                "模型返回的结构化 JSON 不完整，我已保留这轮回复。"
                "请继续补充或重试；如果下方出现草案，是系统根据文本做的兜底解析。\n\n"
                f"{content[:1200]}"
            ),
            "tasks": fallback_tasks,
            "model": model,
            "raw_content": content,
        }
    tasks = []
    for item in result.get("tasks", []) if isinstance(result.get("tasks"), list) else []:
        task = _normalize_agent_task(item, user_message, meeting_month, period_start, period_end)
        if task:
            tasks.append(task)
    return {
        "status": result.get("status") or ("draft" if tasks else "clarify"),
        "assistant_message": str(result.get("assistant_message") or ""),
        "tasks": tasks,
        "model": model,
    }


def _loads_agent_json(content: str) -> Dict[str, object]:
    text = str(content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()
    text = _strip_invalid_json_controls(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _strip_invalid_json_controls(text: str) -> str:
    return "".join(ch for ch in text if ch in "\t\n\r" or ord(ch) >= 32)


def _normalize_agent_task(
    item: Dict[str, object],
    source_text: str,
    meeting_month: str,
    default_start: str,
    default_end: str,
) -> Dict[str, object] | None:
    if not isinstance(item, dict):
        return None
    metric_key = str(item.get("metric_key") or "").strip()
    if metric_key not in METRIC_DEFINITIONS:
        return None
    definition = METRIC_DEFINITIONS[metric_key]
    operator = str(item.get("operator") or definition.get("default_operator") or ">=").strip()
    if operator not in OPERATORS:
        operator = str(definition.get("default_operator") or ">=")
    try:
        target_value = float(item.get("target_value") or 0)
    except (TypeError, ValueError):
        target_value = 0.0
    owner_type = str(item.get("owner_type") or "consultant").strip()
    if owner_type not in OWNER_TYPES:
        owner_type = "consultant"
    task_text = str(item.get("task") or "").strip()
    if not task_text:
        task_text = f"{definition.get('label', metric_key)} {operator} {_format_value(target_value, definition.get('unit', 'count'))}"
    return {
        "meeting_month": str(item.get("meeting_month") or meeting_month),
        "owner_type": owner_type,
        "owner_name": str(item.get("owner_name") or "").strip(),
        "theme": str(item.get("theme") or _infer_theme(metric_key)),
        "task": task_text,
        "metric_key": metric_key,
        "operator": operator,
        "target_value": target_value,
        "period_start": str(item.get("period_start") or default_start),
        "period_end": str(item.get("period_end") or default_end),
        "priority": str(item.get("priority") or "Medium"),
        "status": "active",
        "notes": str(item.get("notes") or "OKR任务拆解助手生成，需人工确认"),
        "source_text": source_text,
    }


def review_tasks(tasks_df: pd.DataFrame, context: Dict[str, object]) -> pd.DataFrame:
    if tasks_df is None or tasks_df.empty:
        return pd.DataFrame()
    rows = []
    for _, task in tasks_df.iterrows():
        result = check_task(task.to_dict(), context)
        rows.append({**task.to_dict(), **result})
    return pd.DataFrame(rows)


def check_task(task: Dict[str, object], context: Dict[str, object]) -> Dict[str, object]:
    metric_key = str(task.get("metric_key") or "")
    target = _num(task.get("target_value"))
    actual, evidence, source = _actual_value(metric_key, task, context)
    operator = str(task.get("operator") or ">=")
    completed = _compare(actual, target, operator)
    completion_rate = _completion_rate(actual, target, operator)
    gap = _gap(actual, target, operator)
    return {
        "metric_label": METRIC_DEFINITIONS.get(metric_key, {}).get("label", metric_key),
        "actual_value": actual,
        "target_display": _format_value(target, METRIC_DEFINITIONS.get(metric_key, {}).get("unit", "count")),
        "actual_display": _format_value(actual, METRIC_DEFINITIONS.get(metric_key, {}).get("unit", "count")),
        "completion_rate": completion_rate,
        "is_completed": completed,
        "gap": gap,
        "gap_display": _format_value(abs(gap), METRIC_DEFINITIONS.get(metric_key, {}).get("unit", "count")),
        "review_status": "完成" if completed else "未完成",
        "evidence_count": len(evidence),
        "evidence_preview": _evidence_preview(evidence),
        "data_source": source,
    }


def evidence_for_task(task: Dict[str, object], context: Dict[str, object]) -> pd.DataFrame:
    _, evidence, _ = _actual_value(str(task.get("metric_key") or ""), task, context)
    return pd.DataFrame(evidence)


def _actual_value(metric_key: str, task: Dict[str, object], context: Dict[str, object]) -> Tuple[float, List[dict], str]:
    if metric_key in {"new_case_bd", "new_projects", "new_referrals", "new_interviews", "avg_referrals_per_project", "referral_to_interview_rate", "interview_to_offer_rate"}:
        return _process_metric(metric_key, task, context)
    if metric_key in {"new_offers", "offer_unpaid_amount"}:
        return _offer_metric(metric_key, task, context)
    if metric_key == "collection_amount":
        return _collection_metric(task, context)
    if metric_key == "weighted_forecast":
        return _forecast_metric(task, context)
    if metric_key == "new_bd_clients":
        return 0.0, [], "pending_schema:new_bd_clients"
    return 0.0, [], "unsupported_metric"


def _process_metric(metric_key: str, task: Dict[str, object], context: Dict[str, object]) -> Tuple[float, List[dict], str]:
    if metric_key == "new_case_bd":
        return _case_bd_metric(task, context)
    df = context.get("active_process_df", pd.DataFrame())
    if df is None or df.empty:
        return 0.0, [], "active_process_df"
    work = _filter_owner(df.copy(), task)
    start, end = _period(task)
    referrals = _filter_date(work, "resume_sent_date", start, end)
    interviews = _filter_date(work, "first_interview_date", start, end)
    offers = _filter_date(work, "offer_date", start, end)
    if metric_key == "new_projects":
        if "joborder_id" not in referrals.columns:
            return 0.0, [], "active_process_df.joborder_id"
        project_rows = referrals.drop_duplicates("joborder_id", keep="first").copy()
        evidence = _process_evidence(project_rows)
        return float(project_rows["joborder_id"].nunique()), evidence, "active_process_df distinct joborder_id with referrals"
    if metric_key == "new_referrals":
        evidence = _process_evidence(referrals)
        return float(len(evidence)), evidence, "active_process_df.resume_sent_date"
    if metric_key == "avg_referrals_per_project":
        project_count = referrals["joborder_id"].nunique() if "joborder_id" in referrals.columns else 0
        return _safe_rate(len(referrals), project_count), _process_evidence(referrals), "active_process_df referrals / distinct joborder_id"
    if metric_key == "new_interviews":
        evidence = _process_evidence(interviews)
        return float(len(evidence)), evidence, "active_process_df.first_interview_date"
    if metric_key == "referral_to_interview_rate":
        return _safe_rate(len(interviews), len(referrals)), _process_evidence(interviews), "active_process_df referral/interview"
    if metric_key == "interview_to_offer_rate":
        return _safe_rate(len(offers), len(interviews)), _process_evidence(offers), "active_process_df interview/offer"
    return 0.0, [], "active_process_df"


def _case_bd_metric(task: Dict[str, object], context: Dict[str, object]) -> Tuple[float, List[dict], str]:
    project_additions = context.get("project_additions", {})
    detail = project_additions.get("detail", pd.DataFrame()) if isinstance(project_additions, dict) else pd.DataFrame()
    if detail is None or detail.empty:
        return 0.0, [], "project_additions.detail"
    work = _filter_owner(detail.copy(), task)
    start, end = _period(task)
    work = _filter_date(work, "added_date", start, end)
    if "joborder_id" not in work.columns:
        return 0.0, [], "project_additions.detail.joborder_id"
    rows = work.drop_duplicates("joborder_id", keep="first").copy()
    evidence = []
    for _, row in rows.iterrows():
        evidence.append(
            {
                "joborder_id": row.get("joborder_id"),
                "client_name": row.get("client_name"),
                "position_name": row.get("position_name"),
                "consultant": row.get("consultant"),
                "team": row.get("team"),
                "added_date": row.get("added_date"),
                "job_status": row.get("job_status"),
                "offer_count": row.get("offer_count"),
            }
        )
    return float(rows["joborder_id"].nunique()), evidence, "project_additions.detail.added_date"


def _offer_metric(metric_key: str, task: Dict[str, object], context: Dict[str, object]) -> Tuple[float, List[dict], str]:
    offer_outcomes = context.get("offer_outcomes", {})
    detail = offer_outcomes.get("detail", pd.DataFrame()) if isinstance(offer_outcomes, dict) else pd.DataFrame()
    if detail is None or detail.empty:
        return 0.0, [], "offer_outcomes.detail"
    work = _filter_owner(detail.copy(), task)
    start, end = _period(task)
    work = _filter_date(work, "offer_date", start, end)
    reserve = work[work.get("invoice_status").isin(["Invoice Added", "Sent"])].copy()
    if metric_key == "new_offers":
        offer_only = reserve[reserve.get("invoice_status").eq("Invoice Added")]
        evidence = _offer_evidence(offer_only)
        return float(offer_only["offer_id"].nunique()) if "offer_id" in offer_only.columns else 0.0, evidence, "offer_outcomes.detail Invoice Added"
    evidence = _offer_evidence(reserve)
    return float(pd.to_numeric(reserve.get("offer_amount"), errors="coerce").fillna(0).sum()), evidence, "offer_outcomes.detail Invoice Added + Sent"


def _collection_metric(task: Dict[str, object], context: Dict[str, object]) -> Tuple[float, List[dict], str]:
    df = context.get("collection_df", pd.DataFrame())
    if df is None or df.empty:
        return 0.0, [], "collection_df"
    work = _filter_owner(df.copy(), task)
    start, end = _period(task)
    work = _filter_date(work, "payment_received_date", start, end)
    evidence = _collection_evidence(work)
    return float(pd.to_numeric(work.get("collection_amount"), errors="coerce").fillna(0).sum()), evidence, "collection_df.payment_received_date"


def _forecast_metric(task: Dict[str, object], context: Dict[str, object]) -> Tuple[float, List[dict], str]:
    pipeline = context.get("pipeline", {})
    df = pipeline.get("by_consultant", pd.DataFrame()) if isinstance(pipeline, dict) else pd.DataFrame()
    if df is None or df.empty:
        return 0.0, [], "pipeline.by_consultant"
    work = _filter_owner(df.copy(), task)
    amount_col = "weighted_revenue" if "weighted_revenue" in work.columns else "weighted_forecast"
    value = float(pd.to_numeric(work.get(amount_col), errors="coerce").fillna(0).sum())
    evidence = work.head(20).to_dict(orient="records")
    return value, evidence, "pipeline.by_consultant"


def _filter_owner(df: pd.DataFrame, task: Dict[str, object]) -> pd.DataFrame:
    owner_type = str(task.get("owner_type") or "consultant")
    owner_name = _norm(task.get("owner_name"))
    if not owner_name or owner_type == "company":
        return df
    col = "team" if owner_type == "team" else "consultant"
    if col not in df.columns:
        return df.iloc[0:0].copy()
    keys = df[col].map(_norm)
    return df[keys.apply(lambda x: owner_name in x or x in owner_name)].copy()


def _filter_date(df: pd.DataFrame, col: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    if col not in df.columns or df.empty:
        return df.iloc[0:0].copy()
    dates = pd.to_datetime(df[col], errors="coerce").dt.normalize()
    return df[(dates >= start) & (dates <= end)].copy()


def _period(task: Dict[str, object]) -> Tuple[pd.Timestamp, pd.Timestamp]:
    start = pd.to_datetime(task.get("period_start"), errors="coerce")
    end = pd.to_datetime(task.get("period_end"), errors="coerce")
    if pd.isna(start):
        start = pd.Timestamp.today().replace(day=1).normalize()
    if pd.isna(end):
        end = pd.Timestamp.today().normalize()
    return start.normalize(), end.normalize()


def _process_evidence(df: pd.DataFrame) -> List[dict]:
    cols = ["consultant", "team", "client_name", "position_name", "jobsubmission_id", "resume_sent_date", "first_interview_date", "offer_date"]
    return df[[c for c in cols if c in df.columns]].head(50).to_dict(orient="records")


def _offer_evidence(df: pd.DataFrame) -> List[dict]:
    cols = ["consultant", "team", "offer_id", "joborder_id", "invoice_status", "offer_date", "offer_amount"]
    return df[[c for c in cols if c in df.columns]].head(50).to_dict(orient="records")


def _collection_evidence(df: pd.DataFrame) -> List[dict]:
    cols = ["consultant", "client_name", "invoice_id", "payment_received_date", "collection_amount"]
    return df[[c for c in cols if c in df.columns]].head(50).to_dict(orient="records")


def _match_owner(text: str, consultants: Iterable[str]) -> Tuple[str, str]:
    text_key = _norm(text)
    best = ""
    for name in consultants:
        name = str(name or "").strip()
        if not name:
            continue
        parts = [_norm(name), _norm(str(name).split()[0])]
        if any(part and part in text_key for part in parts):
            best = name
            break
    return best, "High" if best else "Low"


def _infer_period(text: str, config: Dict[str, object]) -> Tuple[str, str]:
    base = pd.to_datetime(config.get("end_date"), errors="coerce")
    if pd.isna(base):
        base = pd.Timestamp.today()
    base = base.normalize()
    if "下月" in text or "下个月" in text:
        start = (base + pd.offsets.MonthBegin(1)).normalize()
        end = (start + pd.offsets.MonthEnd(0)).normalize()
    elif "本月" in text or "这个月" in text:
        start = base.replace(day=1)
        end = (start + pd.offsets.MonthEnd(0)).normalize()
    else:
        start = pd.to_datetime(config.get("start_date"), errors="coerce")
        end = pd.to_datetime(config.get("end_date"), errors="coerce")
    return start.date().isoformat(), end.date().isoformat()


def _infer_theme(metric_key: str) -> str:
    if metric_key in {"new_bd_clients", "new_case_bd", "new_projects", "new_referrals", "new_interviews", "avg_referrals_per_project", "referral_to_interview_rate", "interview_to_offer_rate", "new_offers"}:
        return "顾问产能"
    if metric_key in {"collection_amount", "offer_unpaid_amount"}:
        return "现金回款"
    if metric_key == "weighted_forecast":
        return "Pipeline"
    return "经营跟进"


def _compare(actual: float, target: float, operator: str) -> bool:
    if operator == "<=":
        return actual <= target
    if operator == "=":
        return abs(actual - target) < 1e-9
    return actual >= target


def _completion_rate(actual: float, target: float, operator: str) -> float:
    if target <= 0:
        return 1.0 if _compare(actual, target, operator) else 0.0
    if operator == "<=":
        if actual <= target:
            return 1.0
        return max(0.0, min(target / actual, 1.0)) if actual else 1.0
    return max(0.0, min(actual / target, 1.0))


def _gap(actual: float, target: float, operator: str) -> float:
    if operator == "<=":
        return max(actual - target, 0.0)
    return max(target - actual, 0.0)


def _safe_rate(numerator: float, denominator: float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def _format_value(value: float, unit: str) -> str:
    value = _num(value)
    if unit == "percent":
        return f"{value:.1%}"
    if unit == "money":
        return f"¥{value:,.0f}"
    return f"{value:g}"


def _evidence_preview(evidence: List[dict]) -> str:
    if not evidence:
        return ""
    first = evidence[0]
    bits = [str(first.get(k) or "") for k in ["client_name", "position_name", "offer_id", "invoice_id"]]
    return " / ".join([bit for bit in bits if bit])[:120]


def _num(value: object) -> float:
    try:
        if value is None or pd.isna(value):
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def _norm(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return " ".join(str(value).strip().lower().split())


def _task_columns() -> List[str]:
    return [
        "id",
        "meeting_month",
        "owner_type",
        "owner_name",
        "theme",
        "task",
        "metric_key",
        "operator",
        "target_value",
        "period_start",
        "period_end",
        "priority",
        "status",
        "notes",
        "source_text",
        "goal_type",
        "target_customer",
        "target_domain",
        "target_position",
        "goal_direction",
        "weekly_check_day",
        "next_check_date",
        "progress_note",
        "created_at",
        "updated_at",
    ]
