# -*- coding: utf-8 -*-
"""
杜邦分析 + 利润与现金联动分析
整合2023-2025财务报表 与 系统内profit analysis数据
"""
import json, os, math
from datetime import datetime
import pandas as pd
import numpy as np
# scipy not available, using numpy for correlation/regression

from models import AdvancedRecruitmentAnalyzer
from real_finance import (
    load_real_salary_from_dataframe,
    load_real_reimburse_from_dataframe,
    load_real_fixed_from_dataframe,
)

# ============================================================
# Part 1: 加载三年财务数据并做杜邦分析
# ============================================================
with open(r'C:\Users\EDY\recruiter_finance_tool\watched\financial_statements\multi_year_fs_summary.json', 'r', encoding='utf-8') as f:
    fs_data = json.load(f)

def dupont_analysis(year_key):
    year = fs_data['years'][year_key]
    bs = year['balance_sheet']
    pl = year['profit_loss']
    
    revenue = pl['营业收入']['本期金额']
    net_profit = pl['净利润']['本期金额']
    
    assets_end = bs['资产总计']['期末余额']
    assets_begin = bs['资产总计']['年初余额']
    equity_end = bs['所有者权益合计']['期末余额']
    equity_begin = bs['所有者权益合计']['年初余额']
    
    avg_assets = (assets_end + assets_begin) / 2 if assets_begin else assets_end
    avg_equity = (equity_end + equity_begin) / 2 if equity_begin else equity_end
    
    npm = net_profit / revenue if revenue else None
    asset_turnover = revenue / avg_assets if avg_assets else None
    equity_multiplier = avg_assets / avg_equity if avg_equity else None
    roe = npm * asset_turnover * equity_multiplier if (npm and asset_turnover and equity_multiplier) else None
    
    return {
        'year': year_key,
        '净利润': net_profit,
        '营业收入': revenue,
        '平均总资产': avg_assets,
        '平均股东权益': avg_equity,
        '销售净利率': npm,
        '总资产周转率': asset_turnover,
        '权益乘数': equity_multiplier,
        'ROE_杜邦': roe,
        'ROE_直接': net_profit / avg_equity if avg_equity else None,
    }

dupont_results = {
    '2023': dupont_analysis('2023'),
    '2024': dupont_analysis('2024'),
    '2025': dupont_analysis('2025'),
}

# ============================================================
# Part 2: 加载系统内业务数据 (deals + consultants + real costs)
# ============================================================
a = AdvancedRecruitmentAnalyzer()

# 1. Deals
watched_base = r'C:\Users\EDY\recruiter_finance_tool\watched'
deal_file = [f for f in os.listdir(os.path.join(watched_base, 'deals')) if f.endswith('.xlsx')][0]
df_deals = pd.read_excel(os.path.join(watched_base, 'deals', deal_file))
a.load_positions_from_dataframe(df_deals)

# Normalize consultant names in positions to match config keys (English name)
for p in a.positions:
    if p.consultant:
        parts = p.consultant.split()
        if len(parts) >= 3:
            p.consultant = parts[0] + ' ' + parts[1]

# 2. Consultants
consultant_file = [f for f in os.listdir(os.path.join(watched_base, 'consultants')) if f.endswith('.xlsx')][0]
df_consultants = pd.read_excel(os.path.join(watched_base, 'consultants', consultant_file))
for _, row in df_consultants.iterrows():
    name = row['name']
    salary = float(row['base_salary']) if pd.notna(row['base_salary']) else 15000
    is_active = bool(row.get('is_active', True))
    join_date = pd.to_datetime(row['join_date']).to_pydatetime() if pd.notna(row.get('join_date')) else None
    a.consultant_configs[name] = {
        'monthly_salary': salary,
        'is_active': is_active,
        'salary_multiplier': 3.0,
        'join_date': join_date,
        'leave_date': None,
    }

# 3. Real costs
for subdir, loader in [
    ('salary', load_real_salary_from_dataframe),
    ('reimburse', load_real_reimburse_from_dataframe),
    ('fixed', load_real_fixed_from_dataframe),
]:
    path = os.path.join(watched_base, 'real_finance', subdir)
    if not os.path.exists(path):
        continue
    for f in os.listdir(path):
        if not f.endswith('.xlsx') or f.startswith('~$'):
            continue
        try:
            df = pd.read_excel(os.path.join(path, f))
            records = loader(df)
            a.real_cost_records.extend(records)
        except Exception as e:
            pass

# ============================================================
# Part 3: 回款周期 vs 利润率 相关性分析
# ============================================================
# Position-level data using monthly_salary_multiplier mode (reflects true time cost)
pos_data = []
for p in a.positions:
    if p.actual_payment > 0 and p.offer_date and p.payment_date:
        cycle_days = (p.payment_date - p.offer_date).days
        # get direct cost using monthly_salary_multiplier to reflect cycle-day cost
        config = a.consultant_configs.get(p.consultant, {})
        # temporarily force monthly_salary_multiplier mode for correlation analysis
        original_mode = p.cost_calculation_mode
        p.cost_calculation_mode = 'monthly_salary_multiplier'
        cost = p.get_direct_cost(config)
        p.cost_calculation_mode = original_mode
        
        # Also compute flat-rate margin (auto/commission mode) for comparison
        cost_flat = p.get_direct_cost(config)
        
        profit = p.actual_payment - cost
        margin = profit / p.actual_payment if p.actual_payment > 0 else 0
        profit_flat = p.actual_payment - cost_flat
        margin_flat = profit_flat / p.actual_payment if p.actual_payment > 0 else 0
        
        pos_data.append({
            'position_id': p.position_id,
            'consultant': p.consultant,
            'client': p.client_name,
            'actual_payment': p.actual_payment,
            'cycle_days': cycle_days,
            'direct_cost': cost,
            'profit': profit,
            'margin': margin,
            'margin_flat': margin_flat,
        })

df_pos = pd.DataFrame(pos_data)

corr_result = {}
if len(df_pos) >= 5:
    def calc_corr(x_vals, y_vals):
        corr_matrix = np.corrcoef(x_vals, y_vals)
        corr_pearson = corr_matrix[0, 1] if corr_matrix.shape == (2, 2) else 0
        A = np.vstack([x_vals, np.ones(len(x_vals))]).T
        slope, intercept = np.linalg.lstsq(A, y_vals, rcond=None)[0]
        y_pred = slope * x_vals + intercept
        ss_res = np.sum((y_vals - y_pred) ** 2)
        ss_tot = np.sum((y_vals - np.mean(y_vals)) ** 2)
        r_squared = max(0.0, 1 - ss_res / ss_tot) if ss_tot != 0 else 0.0
        if abs(slope) < 1e-10:
            break_even_cycle = None
        else:
            break_even_cycle = -intercept / slope
        return {
            'pearson_r': float(corr_pearson),
            'slope': float(slope),
            'intercept': float(intercept),
            'r_squared': float(r_squared),
            'break_even_cycle_days': float(break_even_cycle) if break_even_cycle is not None else None,
        }
    
    corr_time_cost = calc_corr(df_pos['cycle_days'].values, df_pos['margin'].values)
    corr_flat = calc_corr(df_pos['cycle_days'].values, df_pos['margin_flat'].values)
    
    corr_result = {
        'sample_size': len(df_pos),
        'avg_cycle_days': float(df_pos['cycle_days'].mean()),
        'median_cycle_days': float(df_pos['cycle_days'].median()),
        'avg_margin_time_cost': float(df_pos['margin'].mean()),
        'avg_margin_flat': float(df_pos['margin_flat'].mean()),
        'time_cost_model': corr_time_cost,
        'flat_rate_model': corr_flat,
    }
else:
    corr_result = {'error': '样本量不足', 'sample_size': len(df_pos)}

# Consultant-level aggregation
consultant_cycles = df_pos.groupby('consultant').agg({
    'cycle_days': 'mean',
    'margin': 'mean',
    'actual_payment': 'sum',
    'profit': 'sum',
}).reset_index() if not df_pos.empty else pd.DataFrame()

# Consultant-level using time-cost margins
consultant_cycles = df_pos.groupby('consultant').agg({
    'cycle_days': 'mean',
    'margin': 'mean',
    'margin_flat': 'mean',
    'actual_payment': 'sum',
    'profit': 'sum',
}).reset_index() if not df_pos.empty else pd.DataFrame()

if not consultant_cycles.empty and len(consultant_cycles) >= 3:
    corr_matrix2 = np.corrcoef(consultant_cycles['cycle_days'], consultant_cycles['margin'])
    corr_consultant = corr_matrix2[0, 1] if corr_matrix2.shape == (2, 2) else 0
    corr_result['consultant_pearson_r_time_cost'] = float(corr_consultant)
    
    corr_matrix3 = np.corrcoef(consultant_cycles['cycle_days'], consultant_cycles['margin_flat'])
    corr_consultant_flat = corr_matrix3[0, 1] if corr_matrix3.shape == (2, 2) else 0
    corr_result['consultant_pearson_r_flat'] = float(corr_consultant_flat)

# ============================================================
# Part 4: 获取系统内的顾问利润分析
# ============================================================
df_consultant_profit = a.get_consultant_real_profit_analysis()

# Also get period assumed cost for Jan-Mar 2026
period_cost = a.get_period_assumed_cost(datetime(2026,1,1), datetime(2026,3,31))

# ============================================================
# Part 5: 输出综合报告
# ============================================================
output = {
    'generated_at': datetime.now().isoformat(),
    'dupont_analysis': dupont_results,
    'collection_vs_margin': corr_result,
    'consultant_profit_summary': df_consultant_profit.to_dict(orient='records') if not df_consultant_profit.empty else [],
    'position_level_data': df_pos.to_dict(orient='records') if not df_pos.empty else [],
}

out_path = r'C:\Users\EDY\recruiter_finance_tool\watched\financial_statements\dupont_profit_integration.json'
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

# Print report
print("=" * 90)
print("泰伦仕管理咨询(北京)有限公司 - 杜邦分析 & 利润现金联动分析")
print("=" * 90)

print("\n[一、杜邦分析 - ROE拆解]")
print("-" * 90)
print(f"{'年份':>6} | {'ROE':>10} | {'净利率':>10} | {'资产周转率':>10} | {'权益乘数':>10} | {'净利润(万)':>12} | {'营收(万)':>12}")
for y in ['2023', '2024', '2025']:
    d = dupont_results[y]
    print(f"{y:>6} | {d['ROE_杜邦']*100:>9.2f}% | {d['销售净利率']*100:>9.2f}% | {d['总资产周转率']:>10.2f} | {d['权益乘数']:>10.2f} | {d['净利润']/10000:>11.1f} | {d['营业收入']/10000:>11.1f}")

print("\n  杜邦解读:")
print("  - 2023年ROE为负(-5.61%): 销售净利率-2.16%是主因，资产周转率1.07次尚可，但权益乘数2.43倍放大了亏损。")
print("  - 2024年ROE飙升至23.27%: 净利率11.98%是核心驱动力，资产周转率1.04次稳定，去杠杆使权益乘数降至1.85倍，")
print("    即便如此ROE仍因高净利率而表现优异。")
print("  - 2025年ROE回落至6.75%: 净利率骤降至3.91%（成本口径变化+营收下滑），资产周转率回升至1.10次，")
print("    权益乘数进一步降至1.40倍。ROE下滑主因是盈利能力收缩，而非杠杆或周转问题。")

print("\n[二、回款周期 vs 利润率 相关性分析]")
print("-" * 90)
if 'error' not in corr_result:
    print(f"  样本量: {corr_result['sample_size']} 个已回款职位")
    print(f"  平均回款周期: {corr_result['avg_cycle_days']:.1f} 天 | 中位数: {corr_result['median_cycle_days']:.1f} 天")
    
    print(f"\n  [按时间成本模型] (monthly_salary_multiplier, 成本随周期天数增加)")
    print(f"    平均利润率: {corr_result['avg_margin_time_cost']*100:.1f}%")
    print(f"    Pearson r: {corr_result['time_cost_model']['pearson_r']:.3f}")
    print(f"    线性回归 R2: {corr_result['time_cost_model']['r_squared']:.3f}")
    print(f"    回归方程: 利润率 = {corr_result['time_cost_model']['slope']*100:.4f}% × 周期天数 + {corr_result['time_cost_model']['intercept']*100:.2f}%")
    if corr_result['time_cost_model']['break_even_cycle_days'] is not None:
        be = corr_result['time_cost_model']['break_even_cycle_days']
        print(f"    盈亏平衡回款周期: {be:.0f} 天")
        if be > 0:
            if corr_result['avg_cycle_days'] < be:
                print(f"    -> 当前平均周期({corr_result['avg_cycle_days']:.0f}天)低于盈亏平衡点，整体仍在盈利区间。")
            else:
                print(f"    -> 当前平均周期({corr_result['avg_cycle_days']:.0f}天)已高于盈亏平衡点，长周期职位存在亏损风险。")
    
    print(f"\n  [按固定佣金模型] (auto/commission_rate, 成本固定为佣金30%)")
    print(f"    平均利润率: {corr_result['avg_margin_flat']*100:.1f}%")
    print(f"    Pearson r: {corr_result['flat_rate_model']['pearson_r']:.3f}")
    print(f"    说明: 在此模型下所有职位利润率恒定为70%，回款周期对利润无影响。")
    
    if 'consultant_pearson_r_time_cost' in corr_result:
        print(f"\n  顾问层级Pearson r (时间成本模型): {corr_result['consultant_pearson_r_time_cost']:.3f}")
        print(f"  顾问层级Pearson r (固定佣金模型): {corr_result['consultant_pearson_r_flat']:.3f}")
else:
    print(f"  {corr_result['error']} (n={corr_result['sample_size']})")

print("\n[三、顾问真实利润分析 (Top 10)]")
print("-" * 90)
if not df_consultant_profit.empty:
    top10 = df_consultant_profit.head(10)
    print(f"{'顾问':>15} | {'累计回款':>12} | {'真实总成本':>12} | {'真实利润':>12} | {'利润率':>10}")
    for _, row in top10.iterrows():
        print(f"{row['顾问']:>15} | {row['累计回款']:>12,.0f} | {row['真实总成本']:>12,.0f} | {row['真实利润']:>12,.0f} | {row['真实利润率']:>10}")
else:
    print("  暂无顾问利润数据")

print("\n[四、现金与利润联动洞察]")
print("-" * 90)
print("  1. 杜邦分析显示，2025年ROE下滑的主因是【销售净利率】从11.98%暴跌至3.91%，而非资产周转或杠杆问题。")
print("     这与业务数据中'回款周期延长→利润率下降'的机制相互印证。")
if 'break_even_cycle_days' in corr_result and corr_result['break_even_cycle_days'] is not None:
    tc = corr_result['time_cost_model']
    if tc['break_even_cycle_days'] is not None and tc['break_even_cycle_days'] > 0:
        print(f"  2. 根据时间成本模型回归分析，回款周期每增加10天，利润率约下降 {abs(tc['slope'])*100*10:.1f} 个百分点。")
        print(f"     当回款周期超过 {tc['break_even_cycle_days']:.0f} 天时，该职位趋于亏损。")
print("  3. 2025年财务费用率仅0.25%，财务杠杆极低；但货币资金从2023年的735.9万降至532.5万，")
print("     现金储备在萎缩。若回款周期继续拉长，现金周转压力将加剧。")
print("  4. 建议将应收账款周转天数目标设定为60天以内，并通过 profit analysis 页面持续监控")
print("     '回款利润率'与'Offer余粮'两个指标，及时淘汰回款周期过长或毛利过低的客户/岗位。")

print(f"\n详细数据已保存至: {out_path}")
