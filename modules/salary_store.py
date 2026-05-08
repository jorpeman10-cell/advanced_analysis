"""Local consultant salary configuration.

Salary changes are low-frequency, so v2 keeps a local JSON copy and only
updates it when the user uploads a new salary sheet.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import pandas as pd


CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "consultant_salaries.json"


def load_salary_df() -> pd.DataFrame:
    if not CONFIG_PATH.exists():
        return pd.DataFrame(columns=["consultant", "base_salary"])
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return pd.DataFrame(columns=["consultant", "base_salary"])
    rows = data.get("salaries", [])
    return pd.DataFrame(rows, columns=["consultant", "base_salary"])


def save_salary_df(df: pd.DataFrame) -> int:
    normalized = normalize_salary_df(df)
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "salaries": normalized.to_dict(orient="records"),
        "note": "Local salary config for Three-Speed v2. Do not commit.",
    }
    CONFIG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(normalized)


def normalize_salary_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["consultant", "base_salary"])
    name_col = _find_column(df, ["consultant", "name", "顾问", "姓名", "员工", "员工姓名", "顾问姓名"])
    salary_col = _find_column(df, ["base_salary", "salary", "monthly_salary", "底薪", "基本工资", "月薪", "工资", "顾问底薪"])
    if not name_col or not salary_col:
        return pd.DataFrame(columns=["consultant", "base_salary"])
    result = df[[name_col, salary_col]].copy()
    result.columns = ["consultant", "base_salary"]
    result["consultant"] = result["consultant"].astype(str).str.strip()
    result["base_salary"] = pd.to_numeric(result["base_salary"], errors="coerce")
    result = result[(result["consultant"] != "") & result["base_salary"].notna()]
    result = result.drop_duplicates("consultant", keep="last")
    return result.reset_index(drop=True)


def _find_column(df: pd.DataFrame, candidates: Iterable[str]) -> str:
    normalized = {str(col).strip().lower(): col for col in df.columns}
    for candidate in candidates:
        key = candidate.strip().lower()
        if key in normalized:
            return normalized[key]
    return ""

