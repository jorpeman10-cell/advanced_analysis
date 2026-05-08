#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
import os
sys.path.insert(0, r'C:\Users\EDY\recruiter_finance_tool\advanced_analysis')

from auto_import import scan_financial_statements

# 清除旧数据
fs_dir = r'C:\Users\EDY\recruiter_finance_tool\watched\financial_statements'
for fname in ['import_log.json', 'multi_year_fs_summary.json']:
    fpath = os.path.join(fs_dir, fname)
    if os.path.exists(fpath):
        os.remove(fpath)

print('重新扫描财务报表...')
results = scan_financial_statements(r'C:\Users\EDY\recruiter_finance_tool\watched')

for r in results:
    print(f"{r['status']}: {r['file']} - {r['message']}")

# 检查结果
import json
with open(os.path.join(fs_dir, 'multi_year_fs_summary.json'), 'r', encoding='utf-8') as f:
    data = json.load(f)

print('\n三年利润表营业收入对比:')
for year in ['2023', '2024', '2025']:
    pl = data['years'][year]['profit_loss']
    revenue = pl.get('营业收入', {}).get('本期金额', 0)
    profit = pl.get('净利润', {}).get('本期金额', 0)
    print(f'  {year}年: 营业收入={revenue:,.0f}, 净利润={profit:,.0f}')
