#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'C:\Users\EDY\recruiter_finance_tool\advanced_analysis')

from auto_import import _normalize_account_name

# 从汇总文件中读取实际的科目名称
import json
with open(r'C:\Users\EDY\recruiter_finance_tool\watched\financial_statements\multi_year_fs_summary.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print('2023年利润表科目标准化:')
pl = data['years']['2023']['profit_loss']
for k in pl.keys():
    result = _normalize_account_name(k, 'profit_loss')
    if k != result:  # 只显示被标准化的
        print(f'  {k} -> {result}')
    elif '利润' in k or '亏损' in k or '收益' in k:
        print(f'  {k} -> {result} (未变化)')
