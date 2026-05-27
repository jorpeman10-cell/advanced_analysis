"""Read-only MCP server for Recruiter Finance Tool v2.

This server exposes the same normalized data services used by the Streamlit
dashboard. It is intentionally read-only: an agent can retrieve evidence and
review management metrics, but cannot write tasks or mutate Gllue records.
"""

from __future__ import annotations

import hmac
import os
import copy
import atexit
import threading
import time
from contextlib import contextmanager
from datetime import date
from typing import Any, Iterator

import pandas as pd
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from pydantic import AnyHttpUrl

import db_config_manager
from gllue_db_client import GllueDBClient
from modules.cashflow_analyzer import CashFlowAnalyzer
from modules.cost_analyzer import CostEfficiencyAnalyzer
from modules.execution_followup import METRIC_DEFINITIONS, check_task, evidence_for_task
from modules.pipeline_analyzer import PipelineAnalyzer
from modules.salary_store import load_salary_df
from modules.v2_data_service import V2DataService


MCP_HOST = os.getenv("RECRUITER_FINANCE_MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("RECRUITER_FINANCE_MCP_PORT", "8765"))
MCP_PUBLIC_BASE_URL = os.getenv("RECRUITER_FINANCE_MCP_PUBLIC_URL", f"http://localhost:{MCP_PORT}")
READ_SCOPE = "finance:read"
CACHE_TTL_SECONDS = int(os.getenv("RECRUITER_FINANCE_MCP_CACHE_TTL", "600"))
DEFAULT_EVIDENCE_LIMIT = 10
MAX_EVIDENCE_LIMIT = 30
_DATA_CACHE: dict[tuple[str, ...], tuple[float, Any]] = {}
_DATA_CACHE_LOCK = threading.RLock()
_SHARED_DB_CLIENT: GllueDBClient | None = None
_SHARED_DATA_SERVICE: V2DataService | None = None


class StaticBearerVerifier(TokenVerifier):
    """Validate the private token configured for this MCP endpoint."""

    async def verify_token(self, token: str) -> AccessToken | None:
        expected = os.getenv("RECRUITER_FINANCE_MCP_TOKEN", "")
        if expected and hmac.compare_digest(token, expected):
            return AccessToken(token=token, client_id="lobe", scopes=[READ_SCOPE])
        return None


mcp = FastMCP(
    "Recruiter Finance Analysis",
    instructions=(
        "Read-only operational data tools for the Recruiter Finance Tool. "
        "Use evidence returned by these tools before concluding about cashflow, "
        "consultant performance, forecast or OKR completion. Minimize tool calls: "
        "start with the tool most specific to the user's question, never call "
        "get_consultant_review for all consultants, and request detail evidence "
        "only when the user needs record-level verification."
    ),
    host=MCP_HOST,
    port=MCP_PORT,
    stateless_http=True,
    json_response=True,
    token_verifier=StaticBearerVerifier(),
    auth=AuthSettings(
        issuer_url=AnyHttpUrl(MCP_PUBLIC_BASE_URL),
        resource_server_url=AnyHttpUrl(MCP_PUBLIC_BASE_URL),
        required_scopes=[READ_SCOPE],
    ),
)


@contextmanager
def _data_service() -> Iterator[V2DataService]:
    global _SHARED_DB_CLIENT, _SHARED_DATA_SERVICE
    if not db_config_manager.has_config():
        raise RuntimeError("Gllue database configuration is missing for the MCP server.")
    if _SHARED_DATA_SERVICE is None:
        _SHARED_DB_CLIENT = GllueDBClient(db_config_manager.get_gllue_db_config())
        _SHARED_DATA_SERVICE = V2DataService(_SHARED_DB_CLIENT)
    yield _SHARED_DATA_SERVICE


def _close_shared_data_service() -> None:
    global _SHARED_DB_CLIENT, _SHARED_DATA_SERVICE
    if _SHARED_DB_CLIENT is not None:
        _SHARED_DB_CLIENT.close()
    _SHARED_DB_CLIENT = None
    _SHARED_DATA_SERVICE = None


atexit.register(_close_shared_data_service)


def _load_datasets(*requests: tuple[str, tuple[object, ...]]) -> list[Any]:
    """Load cached datasets and prepare uncached ones in one DB/SSH session."""
    now = time.monotonic()
    with _DATA_CACHE_LOCK:
        keys = [(method, *(str(arg) for arg in args)) for method, args in requests]
        missing: list[tuple[tuple[str, ...], str, tuple[object, ...]]] = []
        missing_keys: set[tuple[str, ...]] = set()
        for key, (method, args) in zip(keys, requests):
            if key in missing_keys:
                continue
            if key not in _DATA_CACHE or _DATA_CACHE[key][0] <= now:
                missing.append((key, method, args))
                missing_keys.add(key)
        if missing:
            with _data_service() as service:
                for key, method, args in missing:
                    _DATA_CACHE[key] = (
                        time.monotonic() + CACHE_TTL_SECONDS,
                        getattr(service, method)(*args),
                    )
        return [copy.deepcopy(_DATA_CACHE[key][1]) for key in keys]


def _load_dataset(method: str, *args: object) -> Any:
    """Load one normalized dataset through the short-lived conversation cache."""
    return _load_datasets((method, args))[0]


def _today() -> str:
    return date.today().isoformat()


def _date_or_default(value: str | None, default: str) -> str:
    parsed = pd.to_datetime(value, errors="coerce") if value else pd.NaT
    return parsed.date().isoformat() if pd.notna(parsed) else default


def _fiscal_start(end_date: str) -> str:
    return f"{pd.to_datetime(end_date).year}-01-01"


def _name_match(series: pd.Series, name: str) -> pd.Series:
    key = " ".join(str(name or "").strip().lower().split())
    values = series.fillna("").astype(str).str.lower().str.replace(r"\s+", " ", regex=True)
    return values.str.contains(key, regex=False) if key else pd.Series(False, index=series.index)


def _frame(df: pd.DataFrame | None, limit: int = 50) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    data = df.head(limit).copy()
    for column in data.columns:
        if pd.api.types.is_datetime64_any_dtype(data[column]):
            data[column] = data[column].dt.strftime("%Y-%m-%d")
    data = data.astype(object).where(pd.notna(data), None)
    return data.to_dict(orient="records")


def _clean(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return _frame(value)
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, dict):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _filter_consultant(df: pd.DataFrame, consultant: str) -> pd.DataFrame:
    if df is None or df.empty or "consultant" not in df.columns:
        return pd.DataFrame()
    return df[_name_match(df["consultant"], consultant)].copy()


def _evidence_limit(value: int) -> int:
    return max(1, min(int(value or DEFAULT_EVIDENCE_LIMIT), MAX_EVIDENCE_LIMIT))


@mcp.tool()
def get_metric_definitions() -> dict[str, Any]:
    """List supported execution-review metrics and their target units."""
    definitions = {
        key: {
            "label": value["label"],
            "unit": value["unit"],
            "target_value_interpretation": (
                "decimal ratio, for example 0.5 means 50%"
                if value["unit"] == "percent"
                else "currency amount in CNY"
                if value["unit"] == "money"
                else "count"
            ),
            "default_operator": value["default_operator"],
        }
        for key, value in METRIC_DEFINITIONS.items()
    }
    return {"definitions": definitions, "read_only": True}


@mcp.tool()
def get_company_stage_metrics(end_date: str | None = None, forecast_days: int = 180) -> dict[str, Any]:
    """Return fiscal-year Offer, Invoice, Collection and Forecast summaries."""
    end = _date_or_default(end_date, _today())
    start = _fiscal_start(end)
    result = _load_dataset("load_fiscal_ytd_metrics", start, end, int(forecast_days), True)
    return {
        "period": {"start_date": start, "end_date": end, "forecast_days": int(forecast_days)},
        "accounting_note": (
            "Company totals use source-document totals; consultant totals use assignment amounts "
            "to preserve collaboration splits. Prior-year outstanding stages are included when "
            "they enter the fiscal-year performance chain."
        ),
        "data": _clean(result),
    }


@mcp.tool()
def get_consultant_review(
    consultant: str,
    start_date: str | None = None,
    end_date: str | None = None,
    forecast_days: int = 180,
    include_evidence: bool = False,
    evidence_limit: int = DEFAULT_EVIDENCE_LIMIT,
) -> dict[str, Any]:
    """Return one consultant's process, performance reserve, collection, forecast and cost evidence."""
    consultant_key = " ".join(str(consultant or "").strip().lower().split())
    if consultant_key in {"", "all", "company", "全部", "所有", "全体"}:
        return {
            "status": "consultant_required",
            "message": (
                "This tool reviews one named consultant only. Use get_company_stage_metrics "
                "for company totals, or call this tool once for the consultant requested by the user."
            ),
        }
    end = _date_or_default(end_date, _today())
    start = _date_or_default(start_date, _fiscal_start(end))
    consultants = _load_dataset("load_consultants")
    consultant_rows = _filter_consultant(consultants, consultant)
    if consultant_rows.empty or "consultant_id" not in consultant_rows.columns:
        return {"status": "not_found", "consultant": consultant, "message": "No matching consultant was found."}
    consultant_row = consultant_rows.iloc[[0]].copy()
    user_id = int(consultant_row.iloc[0]["consultant_id"])
    (
        process,
        collection,
        forecast,
        outcome_detail,
        fiscal_collection,
    ) = _load_datasets(
        ("load_consultant_process_data", (user_id, start, end)),
        ("load_consultant_collection_data", (user_id, start, end)),
        ("load_consultant_forecast_data", (user_id, end, int(forecast_days))),
        ("load_consultant_offer_outcome_detail", (user_id, start, end)),
        ("load_consultant_collection_data", (user_id, _fiscal_start(end), end)),
    )

    pipeline = PipelineAnalyzer().analyze(forecast, days=int(forecast_days), analysis_date=end)
    salary_df = load_salary_df()
    cost_row: list[dict[str, Any]] = []
    if salary_df is not None and not salary_df.empty:
        cost = CostEfficiencyAnalyzer().analyze(consultant_row, fiscal_collection, salary_df)
        ranking = cost.get("ranking", pd.DataFrame())
        cost_row = _frame(ranking, limit=1)

    referral_count = int(process["jobsubmission_id"].nunique()) if "jobsubmission_id" in process else 0
    interview_count = int(process["first_interview_date"].notna().sum()) if "first_interview_date" in process else 0
    offer_count = int(process["offer_date"].notna().sum()) if "offer_date" in process else 0
    result = {
        "status": "ok",
        "consultant": consultant,
        "period": {"start_date": start, "end_date": end, "forecast_days": int(forecast_days)},
        "summary": {
            "referrals": referral_count,
            "interviews": interview_count,
            "offers_from_process": offer_count,
            "referral_to_interview_rate": interview_count / referral_count if referral_count else 0,
            "collection_amount": float(collection.get("collection_amount", pd.Series(dtype=float)).sum()),
            "offer_unpaid_amount": float(outcome_detail.get("offer_amount", pd.Series(dtype=float)).sum()),
            "weighted_forecast": float(
                pipeline.get("by_consultant", pd.DataFrame()).get("weighted_revenue", pd.Series(dtype=float)).sum()
            ),
        },
        "cost_scorecard": cost_row,
        "evidence_available": {
            "process_rows": len(process),
            "offer_collection_rows": len(outcome_detail),
            "forecast_rows": len(forecast),
        },
    }
    if include_evidence:
        limit = _evidence_limit(evidence_limit)
        result.update(
            {
                "process_evidence": _frame(process, limit=limit),
                "offer_collection_evidence": _frame(outcome_detail, limit=limit),
                "forecast_evidence": _frame(forecast, limit=limit),
            }
        )
    return result


@mcp.tool()
def get_forecast_pipeline(
    analysis_date: str | None = None,
    forecast_days: int = 180,
    consultant: str | None = None,
    include_evidence: bool = False,
    evidence_limit: int = DEFAULT_EVIDENCE_LIMIT,
) -> dict[str, Any]:
    """Return live forecast including overdue pipeline instead of restricting to current-year creation."""
    end = _date_or_default(analysis_date, _today())
    forecast = _load_dataset("load_forecast_data", end, int(forecast_days))
    if consultant:
        forecast = _filter_consultant(forecast, consultant)
    result = PipelineAnalyzer().analyze(forecast, days=int(forecast_days), analysis_date=end)
    response = {
        "analysis_date": end,
        "forecast_days": int(forecast_days),
        "consultant": consultant or "Company",
        "rule": "Live forecast is evaluated by current stage; overdue active forecast remains included.",
        "summary": _clean(result.get("summary", {})),
        "by_stage": _frame(result.get("by_stage", pd.DataFrame())),
        "by_consultant": _frame(result.get("by_consultant", pd.DataFrame()), limit=20),
        "evidence_available": {"forecast_rows": len(forecast)},
    }
    if include_evidence:
        response["evidence"] = _frame(forecast, limit=_evidence_limit(evidence_limit))
    return response


@mcp.tool()
def get_receivables_cashflow(
    start_date: str | None = None,
    end_date: str | None = None,
    initial_cash: float = 0,
    monthly_cost: float = 0,
    forecast_days: int = 180,
    client_name: str | None = None,
    include_evidence: bool = False,
    evidence_limit: int = DEFAULT_EVIDENCE_LIMIT,
) -> dict[str, Any]:
    """Return open receivables, overdue evidence, contractual terms and projected cash nodes."""
    end = _date_or_default(end_date, _today())
    start = _date_or_default(start_date, _fiscal_start(end))
    invoices, forecast = _load_datasets(
        ("load_cashflow_invoices", (start, end)),
        ("load_forecast_data", (end, int(forecast_days))),
    )
    if client_name and not invoices.empty and "client_name" in invoices.columns:
        invoices = invoices[_name_match(invoices["client_name"], client_name)].copy()
    result = CashFlowAnalyzer().analyze(
        invoices,
        initial_cash=float(initial_cash),
        monthly_cost=float(monthly_cost),
        forecast_df=forecast,
        analysis_date=end,
        days=int(forecast_days),
    )
    response = {
        "period": {"start_date": start, "end_date": end, "forecast_days": int(forecast_days)},
        "client_name": client_name or "All Clients",
        "summary": _clean(result.get("summary", {})),
        "evidence_available": {
            "overdue_rows": len(result.get("overdue_orders", pd.DataFrame())),
            "client_payment_terms_rows": len(result.get("client_payment_terms", pd.DataFrame())),
        },
    }
    if include_evidence:
        limit = _evidence_limit(evidence_limit)
        response["overdue_orders"] = _frame(result.get("overdue_orders", pd.DataFrame()), limit=limit)
        response["client_payment_terms"] = _frame(
            result.get("client_payment_terms", pd.DataFrame()), limit=limit
        )
    return response


@mcp.tool()
def review_execution_metric(
    owner_name: str,
    metric_key: str,
    target_value: float,
    period_start: str,
    period_end: str,
    operator: str = ">=",
) -> dict[str, Any]:
    """Check one consultant KPI against source data and return evidence without saving a task."""
    if metric_key not in METRIC_DEFINITIONS:
        raise ValueError(f"Unsupported metric_key: {metric_key}")
    process, collection, forecast, outcomes, additions = _load_datasets(
        ("load_process_data", (period_start, period_end)),
        ("load_collection_data", (period_start, period_end)),
        ("load_forecast_data", (period_end, 180)),
        ("load_offer_outcome_metrics", (period_start, period_end)),
        ("load_project_additions", (period_start, period_end)),
    )
    context = {
        "active_process_df": process,
        "collection_df": collection,
        "pipeline": PipelineAnalyzer().analyze(forecast, days=180, analysis_date=period_end),
        "offer_outcomes": outcomes,
        "project_additions": additions,
    }
    task = {
        "owner_type": "consultant",
        "owner_name": owner_name,
        "metric_key": metric_key,
        "operator": operator,
        "target_value": float(target_value),
        "period_start": period_start,
        "period_end": period_end,
    }
    result = check_task(task, context)
    evidence = evidence_for_task(task, context)
    return {
        "task": task,
        "result": _clean(result),
        "evidence": _frame(evidence, limit=DEFAULT_EVIDENCE_LIMIT),
        "rule": "Read-only validation; this call does not create or modify an execution-followup task.",
    }


def main() -> None:
    if not os.getenv("RECRUITER_FINANCE_MCP_TOKEN", ""):
        raise RuntimeError(
            "Set RECRUITER_FINANCE_MCP_TOKEN before starting the server; unauthenticated mode is disabled."
        )
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
