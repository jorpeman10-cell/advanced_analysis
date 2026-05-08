#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
财务状况数据模块
支持导入真实工资表、报销表、固定支出表、奖金递延表，并进行成本分摊
"""

import math
import uuid
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from collections import defaultdict


@dataclass
class RealCostRecord:
    """真实成本记录"""
    record_id: str
    date: datetime
    category: str          # salary | reimburse | fixed | sourcing | interview
    amount: float
    consultant: Optional[str] = None
    description: str = ""
    position_id: Optional[str] = None
    client_name: Optional[str] = None
    sub_category: Optional[str] = None   # 如：基本工资、社保、差旅费等


def _parse_date_val(val):
    """安全解析日期"""
    if pd.isna(val):
        return None
    try:
        return pd.to_datetime(val)
    except Exception:
        return None


def _find_column(row: pd.Series, candidates: List[str]) -> Optional[str]:
    """从候选列名中查找存在的列并返回值"""
    for col in candidates:
        if col in row and pd.notna(row[col]):
            return row[col]
    return None


def _to_float(val, default: float = 0.0) -> float:
    """安全转 float"""
    if val is None:
        return default
    try:
        v = float(val)
        if math.isnan(v):
            return default
        return v
    except Exception:
        return default


# ============================================================
# 1. DataFrame 加载函数
# ============================================================

# 费用类型自动分类关键词
SALARY_TYPE_KEYWORDS = {'工资', '社保', '公积金', '奖金', '提成', '补贴', '津贴', '薪酬', 'salary', 'social', 'housing', 'bonus'}
REIMBURSE_TYPE_KEYWORDS = {'差旅', '招待', '餐饮', '交通', '滴滴', '打车', '加油', '停车', '过路费', '渠道', '广告', '推广', 'reimburse', 'travel', 'entertainment', 'transport'}
FIXED_TYPE_KEYWORDS = {'租金', '物业', '房租', '行政', '办公', '软件', '系统', '订阅', '认证', '财务费', '年会', '体检', '招聘', '通讯', '电脑', '网络', 'fixed', 'rent', 'admin', 'software'}


def _classify_expense_type(type_str: str) -> str:
    """根据费用类型字符串自动分类为 salary / reimburse / fixed"""
    if not type_str:
        return 'unknown'
    ts = type_str.lower()
    for kw in SALARY_TYPE_KEYWORDS:
        if kw in ts:
            return 'salary'
    for kw in REIMBURSE_TYPE_KEYWORDS:
        if kw in ts:
            return 'reimburse'
    for kw in FIXED_TYPE_KEYWORDS:
        if kw in ts:
            return 'fixed'
    return 'unknown'


def _extract_expense_type(row: pd.Series) -> str:
    """从行中提取费用类型"""
    for col in ['费用类型', 'category', '类型', '费用类别', 'type', '类别', '项目']:
        if col in row and pd.notna(row[col]):
            return str(row[col]).strip()
    return ""


def load_real_salary_from_dataframe(df: pd.DataFrame) -> List[RealCostRecord]:
    """
    从工资表 DataFrame 加载真实成本记录
    支持的列名（中文/英文混排）:
      - 日期/年月/date/month/月份
      - 顾问姓名/姓名/顾问/name/consultant/用户/部门
      - 基本工资/底薪/base_salary/基本工资
      - 社保/社保公司部分/social_insurance
      - 公积金/公积金公司部分/housing_fund
      - 奖金/提成/bonus
      - 其他补贴/津贴/allowance
      - 合计/总额/total/amount/实发/成本
      
    如果表格中包含"费用类型"列，系统会根据费用类型自动分类（工资类→salary，
    差旅招待类→reimburse，房租行政类→fixed），避免混合表格重复计算。
    """
    records = []
    has_type_col = any(c in df.columns for c in ['费用类型', 'category', '类型', '费用类别', 'type', '类别', '项目'])
    
    for idx, row in df.iterrows():
        # 日期
        date_val = None
        for col in ['date', '日期', '年月', '月份', 'month', '时间']:
            if col in row and pd.notna(row[col]):
                date_val = _parse_date_val(row[col])
                if date_val:
                    break
        if not date_val:
            date_val = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # 顾问/部门/姓名
        consultant = None
        for col in ['consultant', '顾问', '顾问姓名', '姓名', 'name', '用户', '员工', '部门', '备注']:
            if col in row and pd.notna(row[col]):
                consultant = str(row[col]).strip()
                break
        
        # 费用类型（如果有的话）
        expense_type = _extract_expense_type(row)
        
        # 尝试读取金额列
        total_amount = 0.0
        for col in ['amount', '合计', '总额', 'total', '实发', '成本', '总金额', '金额']:
            if col in row and pd.notna(row[col]):
                total_amount = _to_float(row[col])
                break
        
        # 如果没有直接金额列，累加明细
        if total_amount == 0.0:
            components = [
                ('base_salary', '基本工资', '底薪'),
                ('social_insurance', '社保', '社保公司部分'),
                ('housing_fund', '公积金', '公积金公司部分'),
                ('bonus', '奖金', '提成'),
                ('allowance', '津贴', '补贴', '其他补贴'),
            ]
            for eng, *cns in components:
                cols = [eng] + list(cns)
                for col in cols:
                    if col in row and pd.notna(row[col]):
                        total_amount += _to_float(row[col])
                        break
        
        # 跳过汇总行（空费用类型且没有顾问/部门的金额大数）
        if not expense_type and not consultant and total_amount > 100000:
            continue
        if total_amount <= 0:
            continue
        
        # 自动分类
        if has_type_col and expense_type:
            classified = _classify_expense_type(expense_type)
            if classified == 'unknown':
                # 无法识别的类型，保守归入 fixed（避免误增工资）
                classified = 'fixed'
            category = classified
            description = expense_type
        else:
            category = 'salary'
            description = '真实工资成本'
        
        prefix = {'salary': 'SAL', 'reimburse': 'RMB', 'fixed': 'FXD'}.get(category, 'RCT')
        records.append(RealCostRecord(
            record_id=f"{prefix}-{uuid.uuid4().hex[:8]}",
            date=date_val,
            category=category,
            amount=total_amount,
            consultant=consultant,
            description=description
        ))
    return records


def load_real_reimburse_from_dataframe(df: pd.DataFrame) -> List[RealCostRecord]:
    """
    从报销/费用表 DataFrame 加载真实成本记录
    支持的列名:
      - 日期/date/时间
      - 顾问/姓名/name/consultant/用户/员工/部门
      - 费用类型/类型/category/type/费用类别
      - 金额/amount/费用/总价
      - 关联职位/职位/position/项目/project/客户/client
      - 说明/备注/description/note
      
    如果表格中包含"费用类型"列，会自动筛选出报销/差旅/招待相关记录，
    工资类记录会被忽略（避免与工资表重复）。
    """
    records = []
    has_type_col = any(c in df.columns for c in ['费用类型', 'category', '类型', '费用类别', 'type', '类别', '项目'])
    
    for idx, row in df.iterrows():
        date_val = None
        for col in ['date', '日期', '时间']:
            if col in row and pd.notna(row[col]):
                date_val = _parse_date_val(row[col])
                if date_val:
                    break
        if not date_val:
            date_val = datetime.now()
        
        consultant = None
        for col in ['consultant', '顾问姓名', '顾问', '姓名', 'name', '用户', '员工', '部门', '部门/顾问']:
            if col in row and pd.notna(row[col]):
                consultant = str(row[col]).strip()
                break
        
        sub_category = _extract_expense_type(row)
        
        # 如果有费用类型列，但类型是工资/社保/房租/固定类，则跳过（避免重复）
        if has_type_col and sub_category:
            classified = _classify_expense_type(sub_category)
            if classified in ('salary', 'fixed'):
                continue
        
        amount = 0.0
        for col in ['amount', '金额', '费用', '总价', 'total']:
            if col in row and pd.notna(row[col]):
                amount = _to_float(row[col])
                break
        
        # 跳过无明确类型的汇总行
        if not sub_category and not consultant and amount > 100000:
            continue
        if amount <= 0:
            continue
        
        position_id = None
        for col in ['position_id', '关联职位', '职位', 'position', '项目']:
            if col in row and pd.notna(row[col]):
                position_id = str(row[col]).strip()
                break
        
        client_name = None
        for col in ['client_name', '客户', 'client', '客户名称']:
            if col in row and pd.notna(row[col]):
                client_name = str(row[col]).strip()
                break
        
        description = ""
        for col in ['description', '说明', '备注', 'note', '摘要']:
            if col in row and pd.notna(row[col]):
                description = str(row[col]).strip()
                break
        
        records.append(RealCostRecord(
            record_id=f"RMB-{uuid.uuid4().hex[:8]}",
            date=date_val,
            category='reimburse',
            amount=amount,
            consultant=consultant,
            description=description or sub_category,
            position_id=position_id,
            client_name=client_name,
            sub_category=sub_category
        ))
    return records


def load_real_fixed_from_dataframe(df: pd.DataFrame) -> List[RealCostRecord]:
    """
    从固定支出表 DataFrame 加载真实成本记录
    支持的列名:
      - 日期/date/年月/月份
      - 费用类型/类型/category/type/费用类别
      - 金额/amount/费用/总价
      - 说明/备注/description/note
      
    如果表格中包含"费用类型"列，会自动筛选出固定支出相关记录，
    工资/差旅类记录会被忽略（避免与其他表格重复）。
    """
    records = []
    has_type_col = any(c in df.columns for c in ['费用类型', 'category', '类型', '费用类别', 'type', '类别', '项目'])
    
    for idx, row in df.iterrows():
        date_val = None
        for col in ['date', '日期', '年月', '月份', 'month']:
            if col in row and pd.notna(row[col]):
                date_val = _parse_date_val(row[col])
                if date_val:
                    break
        if not date_val:
            date_val = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        consultant = None
        for col in ['consultant', '顾问姓名', '顾问', '姓名', 'name', '用户', '员工', '部门', '部门/顾问']:
            if col in row and pd.notna(row[col]):
                consultant = str(row[col]).strip()
                break
        
        sub_category = _extract_expense_type(row)
        
        # 如果有费用类型列，跳过工资/差旅/招待类
        if has_type_col and sub_category:
            classified = _classify_expense_type(sub_category)
            if classified in ('salary', 'reimburse'):
                continue
        
        amount = 0.0
        for col in ['amount', '金额', '费用', '总价', 'total']:
            if col in row and pd.notna(row[col]):
                amount = _to_float(row[col])
                break
        
        # 跳过汇总行（空费用类型且没有顾问/部门的金额大数）
        if not sub_category and not consultant and amount > 100000:
            continue
        if amount <= 0:
            continue
        
        description = ""
        for col in ['description', '说明', '备注', 'note', '摘要']:
            if col in row and pd.notna(row[col]):
                description = str(row[col]).strip()
                break
        
        # 识别 2025 年度奖金递延
        sub_category_out = sub_category
        if not sub_category_out:
            if '2025年度奖金' in description or '奖金递延' in description:
                sub_category_out = 'annual_bonus_2025'
        
        records.append(RealCostRecord(
            record_id=f"FXD-{uuid.uuid4().hex[:8]}",
            date=date_val,
            category='fixed',
            amount=amount,
            consultant=consultant,
            description=description or sub_category_out,
            sub_category=sub_category_out
        ))
    return records


# ============================================================
# 2. 成本分摊引擎
# ============================================================

def _days_in_month(year: int, month: int) -> int:
    """获取某月的天数"""
    if month == 12:
        next_month = datetime(year + 1, 1, 1)
    else:
        next_month = datetime(year, month + 1, 1)
    return (next_month - datetime(year, month, 1)).days


def _month_range(start_date: datetime, end_date: datetime) -> List[Tuple[int, int]]:
    """生成从 start_date 到 end_date 之间的所有 (year, month)"""
    months = []
    current = datetime(start_date.year, start_date.month, 1)
    end = datetime(end_date.year, end_date.month, 1)
    while current <= end:
        months.append((current.year, current.month))
        if current.month == 12:
            current = datetime(current.year + 1, 1, 1)
        else:
            current = datetime(current.year, current.month + 1, 1)
    return months


def _overlap_days(range_start: datetime, range_end: datetime,
                  record_date: datetime) -> float:
    """
    计算一个月度记录与某日期区间的重叠天数比例（0~1）
    财务记录无论日期是当月几号，都视为该月整月的费用
    返回：重叠天数 / 当月总天数
    """
    month_start = datetime(record_date.year, record_date.month, 1)
    month_days = _days_in_month(record_date.year, record_date.month)
    
    # 财务记录视为当月整月费用
    record_day_start = month_start
    record_day_end = month_start + timedelta(days=month_days)
    
    overlap_start = max(range_start, record_day_start)
    overlap_end = min(range_end, record_day_end)
    if overlap_start >= overlap_end:
        return 0.0
    overlap = (overlap_end - overlap_start).days
    return max(0.0, overlap) / month_days


def calculate_position_real_costs(
    position_id: str,
    consultant_name: str,
    client_name: str,
    start_date: datetime,
    end_date: datetime,
    all_records: List[RealCostRecord],
    active_consultant_count: int = 1,
    consultant_aliases: List[str] = None
) -> Dict[str, float]:
    """
    计算单个职位的真实成本分摊
    
    分摊规则：
    1. 直接匹配：record.position_id == position_id 或 record.client_name == client_name
    2. 顾问相关（salary/reimburse）：按该职位周期与记录月份的重叠比例分摊
    3. 固定支出（fixed）：按所有在职顾问人数平均分摊
    
    Returns:
        {
            'salary': float,
            'reimburse': float,
            'fixed': float,
            'direct': float,   # 直接关联到该职位的成本
            'total': float,
        }
    """
    if not start_date:
        start_date = datetime.now()
    if not end_date:
        end_date = datetime.now()
    
    # 确保 end_date >= start_date
    if end_date < start_date:
        end_date = start_date
    
    salary_total = 0.0
    reimburse_total = 0.0
    fixed_total = 0.0
    direct_total = 0.0
    
    active_consultant_count = max(1, active_consultant_count)
    
    for r in all_records:
        # 直接匹配判断
        is_direct = False
        if r.position_id and r.position_id == position_id:
            is_direct = True
        if r.client_name and r.client_name == client_name:
            is_direct = True
        
        if is_direct:
            direct_total += r.amount
            if r.category == 'salary':
                salary_total += r.amount
            elif r.category == 'reimburse':
                reimburse_total += r.amount
            elif r.category == 'fixed':
                fixed_total += r.amount
            continue
        
        if r.category == 'salary':
            if r.consultant and (r.consultant == consultant_name or (consultant_aliases and r.consultant in consultant_aliases)):
                ratio = _overlap_days(start_date, end_date, r.date)
                salary_total += r.amount * ratio
        
        elif r.category == 'reimburse':
            if r.consultant and (r.consultant == consultant_name or (consultant_aliases and r.consultant in consultant_aliases)):
                ratio = _overlap_days(start_date, end_date, r.date)
                reimburse_total += r.amount * ratio
        
        elif r.category == 'fixed':
            # 固定成本：先按月份重叠比例算出该月应分摊的部分，再除以顾问数
            ratio = _overlap_days(start_date, end_date, r.date)
            fixed_total += (r.amount * ratio) / active_consultant_count
    
    return {
        'salary': salary_total,
        'reimburse': reimburse_total,
        'fixed': fixed_total,
        'direct': direct_total,
        'total': salary_total + reimburse_total + fixed_total + direct_total,
    }


def calculate_monthly_real_summary(
    year_month: Tuple[int, int],
    all_records: List[RealCostRecord],
    positions_revenue: Dict[str, float] = None
) -> Dict[str, float]:
    """
    计算某个月份的真实成本汇总（用于月度盈亏表）
    
    Args:
        year_month: (year, month)
        all_records: 所有真实成本记录
        positions_revenue: 可选，该月各职位的回款字典 {position_id: revenue}
    
    Returns:
        {
            'salary': x,
            'reimburse': y,
            'fixed': z,
            'total': t,
            'revenue': v,  # 如果传入
        }
    """
    y, m = year_month
    month_start = datetime(y, m, 1)
    month_end = datetime(y, m, _days_in_month(y, m))
    
    salary = 0.0
    reimburse = 0.0
    fixed = 0.0
    annual_bonus_2025 = 0.0
    
    for r in all_records:
        if r.category == 'salary':
            ratio = _overlap_days(month_start, month_end, r.date)
            salary += r.amount * ratio
        elif r.category == 'reimburse':
            ratio = _overlap_days(month_start, month_end, r.date)
            reimburse += r.amount * ratio
        elif r.category == 'fixed':
            ratio = _overlap_days(month_start, month_end, r.date)
            if r.sub_category == 'annual_bonus_2025':
                annual_bonus_2025 += r.amount * ratio
            else:
                fixed += r.amount * ratio
    
    result = {
        'salary': salary,
        'reimburse': reimburse,
        'fixed': fixed,
        'annual_bonus_2025': annual_bonus_2025,
        'total': salary + reimburse + fixed + annual_bonus_2025,
    }
    
    if positions_revenue:
        result['revenue'] = sum(positions_revenue.values())
    
    return result


def get_consultant_real_costs(
    consultant_name: str,
    all_records: List[RealCostRecord],
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    aliases: List[str] = None,
) -> Dict[str, float]:
    """
    计算某个顾问在指定区间内的真实成本汇总
    """
    if not start_date:
        start_date = datetime.min
    if not end_date:
        end_date = datetime.max
    
    salary = 0.0
    reimburse = 0.0
    
    names_to_match = {consultant_name}
    if aliases:
        names_to_match.update(aliases)
    
    for r in all_records:
        if r.consultant not in names_to_match:
            continue
        ratio = _overlap_days(start_date, end_date, r.date)
        if r.category == 'salary':
            salary += r.amount * ratio
        elif r.category == 'reimburse':
            reimburse += r.amount * ratio
    
    return {
        'salary': salary,
        'reimburse': reimburse,
        'total': salary + reimburse,
    }
