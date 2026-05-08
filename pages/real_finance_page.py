#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
财务状况分析页面 - 基于2023-2025三年财报深度分析
"""

import json
import math
import os
import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from real_finance import (
    load_real_salary_from_dataframe,
    load_real_reimburse_from_dataframe,
    load_real_fixed_from_dataframe,
)
from auth_guard import require_real_finance_auth, logout_real_finance, is_real_finance_protected
from auto_import import (
    _parse_financial_statement,
    _update_financial_statements_summary,
    _parse_year_from_filename,
)


def format_currency(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "¥0"
    if abs(value) >= 10000:
        return f"¥{value/10000:.1f}万"
    return f"¥{value:,.0f}"


def format_percent(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "-"
    return f"{value:.2f}%"


def load_financial_data():
    """加载三年财务数据"""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    fs_path = os.path.join(project_root, 'watched', 'financial_statements', 'multi_year_fs_summary.json')
    
    if not os.path.exists(fs_path):
        return None
    
    with open(fs_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def calculate_dupont_analysis(fs_data, years):
    """计算杜邦分析数据"""
    dupont_data = []
    
    for year in years:
        year_data = fs_data['years'][year]
        pl = year_data['profit_loss']
        bs = year_data['balance_sheet']
        
        # 净利润
        net_profit = pl.get('净利润', {}).get('本期金额', 0) or 0
        
        # 营业收入
        revenue = pl.get('营业收入', {}).get('本期金额', 0) or 0
        
        # 平均总资产
        assets_end = bs.get('资产总计', {}).get('期末余额', 0) or 0
        assets_begin = bs.get('资产总计', {}).get('年初余额', 0) or 0
        avg_assets = (assets_end + assets_begin) / 2 if assets_begin else assets_end
        
        # 平均净资产
        equity_end = bs.get('所有者权益合计', {}).get('期末余额', 0) or 0
        equity_begin = bs.get('所有者权益合计', {}).get('年初余额', 0) or 0
        avg_equity = (equity_end + equity_begin) / 2 if equity_begin else equity_end
        
        # 杜邦分析三因子
        npm = (net_profit / revenue * 100) if revenue else 0  # 销售净利率
        asset_turnover = (revenue / avg_assets) if avg_assets else 0  # 总资产周转率
        equity_multiplier = (avg_assets / avg_equity) if avg_equity else 0  # 权益乘数
        roe = npm * asset_turnover * equity_multiplier if avg_equity else 0  # ROE
        
        dupont_data.append({
            '年份': year,
            '净利润': net_profit,
            '营业收入': revenue,
            '平均总资产': avg_assets,
            '平均净资产': avg_equity,
            '销售净利率': npm,
            '总资产周转率': asset_turnover,
            '权益乘数': equity_multiplier,
            'ROE': roe,
        })
    
    return pd.DataFrame(dupont_data)


def _get_available_years(fs_data):
    """获取所有可用的财报年份并按顺序排列"""
    return sorted([y for y in fs_data.get('years', {}).keys() if fs_data['years'][y].get('balance_sheet') or fs_data['years'][y].get('profit_loss')], key=lambda x: int(x))


def _render_three_year_overview(fs_data):
    """渲染财务概览"""
    years = _get_available_years(fs_data)
    if not years:
        return
    
    year_range = f"({years[0]}-{years[-1]})" if len(years) > 1 else f"({years[0]})"
    st.markdown(f"### 📊 财务概览 {year_range}")
    
    first_year = years[0]
    last_year = years[-1]
    
    # 提取关键数据
    overview_data = []
    for year in years:
        year_data = fs_data['years'][year]
        pl = year_data['profit_loss']
        bs = year_data['balance_sheet']
        metrics = year_data['metrics']
        
        overview_data.append({
            '年份': year,
            '营业收入': pl.get('营业收入', {}).get('本期金额', 0) or 0,
            '净利润': pl.get('净利润', {}).get('本期金额', 0) or 0,
            '总资产': bs.get('资产总计', {}).get('期末余额', 0) or 0,
            '净资产': bs.get('所有者权益合计', {}).get('期末余额', 0) or 0,
            '货币资金': bs.get('货币资金', {}).get('期末余额', 0) or 0,
            '毛利率': metrics.get('毛利率', 0) or 0,
            '销售净利率': metrics.get('销售净利率', 0) or 0,
            '资产负债率': metrics.get('资产负债率', 0) or 0,
        })
    
    df_overview = pd.DataFrame(overview_data)
    
    # 显示关键指标卡片
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("**营业收入趋势**")
        revenue_first = df_overview[df_overview['年份']==first_year]['营业收入'].values[0]
        revenue_last = df_overview[df_overview['年份']==last_year]['营业收入'].values[0]
        revenue_change = ((revenue_last - revenue_first) / revenue_first * 100) if revenue_first else 0
        
        colors = ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6']
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=years,
            y=df_overview['营业收入'],
            marker_color=[colors[i % len(colors)] for i in range(len(years))],
            text=[format_currency(v) for v in df_overview['营业收入']],
            textposition='outside'
        ))
        fig.update_layout(height=250, showlegend=False, margin=dict(t=30, b=30))
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"{first_year}-{last_year}变化: {revenue_change:+.1f}%")
    
    with col2:
        st.markdown("**净利润趋势**")
        profit_first = df_overview[df_overview['年份']==first_year]['净利润'].values[0]
        profit_last = df_overview[df_overview['年份']==last_year]['净利润'].values[0]
        profit_change = ((profit_last - profit_first) / abs(profit_first) * 100) if profit_first else 0
        
        fig = go.Figure()
        colors = ['#EF4444' if v < 0 else '#10B981' for v in df_overview['净利润']]
        fig.add_trace(go.Bar(
            x=years,
            y=df_overview['净利润'],
            marker_color=colors,
            text=[format_currency(v) for v in df_overview['净利润']],
            textposition='outside'
        ))
        fig.update_layout(height=250, showlegend=False, margin=dict(t=30, b=30))
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"{first_year}-{last_year}变化: {profit_change:+.1f}%")
    
    with col3:
        st.markdown("**现金储备趋势**")
        cash_first = df_overview[df_overview['年份']==first_year]['货币资金'].values[0]
        cash_last = df_overview[df_overview['年份']==last_year]['货币资金'].values[0]
        cash_change = ((cash_last - cash_first) / cash_first * 100) if cash_first else 0
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=years,
            y=df_overview['货币资金'],
            mode='lines+markers+text',
            line=dict(color='#8B5CF6', width=3),
            marker=dict(size=12),
            text=[format_currency(v) for v in df_overview['货币资金']],
            textposition='top center'
        ))
        fig.update_layout(height=250, showlegend=False, margin=dict(t=30, b=30))
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"{first_year}-{last_year}变化: {cash_change:+.1f}%")
    
    # 详细数据表格
    with st.expander("查看详细财务数据"):
        display_df = df_overview.copy()
        for col in ['营业收入', '净利润', '总资产', '净资产', '货币资金']:
            display_df[col] = display_df[col].apply(format_currency)
        for col in ['毛利率', '销售净利率', '资产负债率']:
            display_df[col] = display_df[col].apply(format_percent)
        st.dataframe(display_df, use_container_width=True, hide_index=True)


def _render_dupont_analysis(fs_data):
    """渲染杜邦分析"""
    years = _get_available_years(fs_data)
    if len(years) < 2:
        return
    
    st.markdown("---")
    st.markdown("### 🔍 杜邦分析 (ROE拆解)")
    
    dupont_df = calculate_dupont_analysis(fs_data, years)
    
    col1, col2 = st.columns([2, 3])
    
    with col1:
        st.markdown("**ROE三因子分解**")
        display_df = dupont_df.copy()
        display_df['ROE'] = display_df['ROE'].apply(lambda x: f"{x:.2f}%")
        display_df['销售净利率'] = display_df['销售净利率'].apply(lambda x: f"{x:.2f}%")
        display_df['总资产周转率'] = display_df['总资产周转率'].apply(lambda x: f"{x:.2f}")
        display_df['权益乘数'] = display_df['权益乘数'].apply(lambda x: f"{x:.2f}")
        
        for col in ['净利润', '营业收入', '平均总资产', '平均净资产']:
            display_df[col] = display_df[col].apply(format_currency)
        
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        
        # ROE变化解读（最早 vs 最近）
        first_year = dupont_df['年份'].iloc[0]
        last_year = dupont_df['年份'].iloc[-1]
        roe_first = dupont_df.iloc[0]['ROE']
        roe_last = dupont_df.iloc[-1]['ROE']
        
        st.markdown("**ROE变化解读**")
        if roe_last < roe_first:
            st.warning(f"⚠️ ROE从{first_year}年的{roe_first:.2f}%下降至{last_year}年的{roe_last:.2f}%，盈利能力有所减弱")
        else:
            st.success(f"✅ ROE从{first_year}年的{roe_first:.2f}%上升至{last_year}年的{roe_last:.2f}%，盈利能力增强")
    
    with col2:
        st.markdown("**ROE三因子趋势对比**")
        
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=('ROE (净资产收益率)', '销售净利率', '总资产周转率', '权益乘数'),
            vertical_spacing=0.15,
            horizontal_spacing=0.1
        )
        
        years = dupont_df['年份'].tolist()
        
        # ROE
        fig.add_trace(go.Scatter(
            x=years, y=dupont_df['ROE'],
            mode='lines+markers',
            line=dict(color='#EF4444', width=3),
            marker=dict(size=10),
            name='ROE'
        ), row=1, col=1)
        
        # 销售净利率
        fig.add_trace(go.Scatter(
            x=years, y=dupont_df['销售净利率'],
            mode='lines+markers',
            line=dict(color='#10B981', width=3),
            marker=dict(size=10),
            name='销售净利率'
        ), row=1, col=2)
        
        # 总资产周转率
        fig.add_trace(go.Scatter(
            x=years, y=dupont_df['总资产周转率'],
            mode='lines+markers',
            line=dict(color='#3B82F6', width=3),
            marker=dict(size=10),
            name='总资产周转率'
        ), row=2, col=1)
        
        # 权益乘数
        fig.add_trace(go.Scatter(
            x=years, y=dupont_df['权益乘数'],
            mode='lines+markers',
            line=dict(color='#F59E0B', width=3),
            marker=dict(size=10),
            name='权益乘数'
        ), row=2, col=2)
        
        fig.update_layout(height=500, showlegend=False, template='plotly_white')
        st.plotly_chart(fig, use_container_width=True)


def _render_profitability_analysis(fs_data):
    """渲染盈利能力分析"""
    years = _get_available_years(fs_data)
    if not years:
        return
    
    st.markdown("---")
    st.markdown("### 💰 盈利能力深度分析")
    
    # 提取利润表详细数据
    profit_data = []
    for year in years:
        pl = fs_data['years'][year]['profit_loss']
        revenue = pl.get('营业收入', {}).get('本期金额', 0) or 0
        
        profit_data.append({
            '年份': year,
            '营业收入': revenue,
            '营业成本': pl.get('营业成本', {}).get('本期金额', 0) or 0,
            '税金及附加': pl.get('税金及附加', {}).get('本期金额', 0) or 0,
            '销售费用': pl.get('销售费用', {}).get('本期金额', 0) or 0,
            '管理费用': pl.get('管理费用', {}).get('本期金额', 0) or 0,
            '财务费用': pl.get('财务费用', {}).get('本期金额', 0) or 0,
            '营业利润': pl.get('营业利润', {}).get('本期金额', 0) or 0,
            '净利润': pl.get('净利润', {}).get('本期金额', 0) or 0,
        })
    
    df_profit = pd.DataFrame(profit_data)
    
    # 计算费用率
    for col in ['营业成本', '税金及附加', '销售费用', '管理费用', '财务费用']:
        df_profit[f'{col}率'] = (df_profit[col] / df_profit['营业收入'] * 100).round(2)
    
    col1, col2 = st.columns(2)
    latest_year = years[-1]
    
    with col1:
        st.markdown(f"**利润结构瀑布图 ({latest_year}年)**")
        
        y_latest = df_profit[df_profit['年份']==latest_year].iloc[0]
        
        fig = go.Figure(go.Waterfall(
            name="利润结构",
            orientation="v",
            measure=["relative", "relative", "relative", "relative", "relative", "relative", "relative", "total"],
            x=["营业收入", "营业成本", "税金", "销售费用", "管理费用", "财务费用", "其他", "净利润"],
            y=[
                y_latest['营业收入'],
                -y_latest['营业成本'],
                -y_latest['税金及附加'],
                -y_latest['销售费用'],
                -y_latest['管理费用'],
                -y_latest['财务费用'],
                y_latest['营业利润'] - y_latest['营业收入'] + y_latest['营业成本'] + y_latest['税金及附加'] + y_latest['销售费用'] + y_latest['管理费用'] + y_latest['财务费用'],
                y_latest['净利润']
            ],
            text=[format_currency(abs(v)) for v in [
                y_latest['营业收入'],
                y_latest['营业成本'],
                y_latest['税金及附加'],
                y_latest['销售费用'],
                y_latest['管理费用'],
                y_latest['财务费用'],
                y_latest['营业利润'] - y_latest['营业收入'] + y_latest['营业成本'] + y_latest['税金及附加'] + y_latest['销售费用'] + y_latest['管理费用'] + y_latest['财务费用'],
                y_latest['净利润']
            ]],
            textposition="outside",
            connector={"line": {"color": "rgb(63, 63, 63)"}},
            decreasing={"marker": {"color": "#EF4444"}},
            increasing={"marker": {"color": "#10B981"}},
            totals={"marker": {"color": "#3B82F6"}}
        ))
        fig.update_layout(height=400, template='plotly_white', showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.markdown("**费用率趋势对比**")
        
        fig = go.Figure()
        expense_items = ['营业成本率', '销售费用率', '管理费用率', '财务费用率']
        colors = ['#EF4444', '#F59E0B', '#8B5CF6', '#6B7280']
        
        for item, color in zip(expense_items, colors):
            fig.add_trace(go.Scatter(
                x=years,
                y=df_profit[item],
                mode='lines+markers',
                name=item.replace('率', ''),
                line=dict(width=3, color=color),
                marker=dict(size=10)
            ))
        
        fig.update_layout(
            height=400,
            template='plotly_white',
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            yaxis_title='费用率 (%)'
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # 盈利能力诊断
    st.markdown("**盈利能力诊断**")
    
    if len(years) >= 2:
        y_latest_data = df_profit[df_profit['年份']==latest_year].iloc[0]
        y_prev_year = years[-2]
        y_prev_data = df_profit[df_profit['年份']==y_prev_year].iloc[0]
        
        diagnoses = []
        
        gm_latest = y_latest_data['营业成本率']
        gm_prev = y_prev_data['营业成本率']
        if gm_latest > gm_prev + 10:
            diagnoses.append(f"⚠️ {latest_year}年营业成本率({gm_latest:.1f}%)较{y_prev_year}年({gm_prev:.1f}%)大幅上升，可能因收入结构变化或销售费用重分类至成本")
        
        se_latest = y_latest_data['销售费用率']
        se_prev = y_prev_data['销售费用率']
        if se_latest < se_prev - 20:
            diagnoses.append(f"ℹ️ {latest_year}年销售费用率({se_latest:.1f}%)较{y_prev_year}年({se_prev:.1f}%)大幅下降，可能与成本重分类有关")
        
        me_latest = y_latest_data['管理费用率']
        me_prev = y_prev_data['管理费用率']
        if me_latest < me_prev:
            diagnoses.append(f"✅ {latest_year}年管理费用率({me_latest:.1f}%)较{y_prev_year}年({me_prev:.1f}%)有所改善")
        
        npm_latest = (y_latest_data['净利润'] / y_latest_data['营业收入'] * 100)
        npm_prev = (y_prev_data['净利润'] / y_prev_data['营业收入'] * 100)
        if npm_latest < npm_prev - 5:
            diagnoses.append(f"🔴 {latest_year}年净利率({npm_latest:.1f}%)较{y_prev_year}年({npm_prev:.1f}%)明显下滑，需关注盈利质量")
        
        for d in diagnoses:
            st.markdown(f"- {d}")
    else:
        st.info("ℹ️ 需要至少两年的利润表数据才能进行盈利能力趋势诊断")


def _render_solvency_analysis(fs_data):
    """渲染偿债能力分析"""
    years = _get_available_years(fs_data)
    if not years:
        return
    
    st.markdown("---")
    st.markdown("### 🛡️ 偿债能力与流动性分析")
    
    # 提取资产负债数据
    solvency_data = []
    for year in years:
        bs = fs_data['years'][year]['balance_sheet']
        metrics = fs_data['years'][year]['metrics']
        
        solvency_data.append({
            '年份': year,
            '总资产': bs.get('资产总计', {}).get('期末余额', 0) or 0,
            '总负债': bs.get('负债合计', {}).get('期末余额', 0) or 0,
            '净资产': bs.get('所有者权益合计', {}).get('期末余额', 0) or 0,
            '货币资金': bs.get('货币资金', {}).get('期末余额', 0) or 0,
            '应收账款': bs.get('应收账款', {}).get('期末余额', 0) or 0,
            '流动资产': bs.get('流动资产合计', {}).get('期末余额', 0) or 0,
            '流动负债': bs.get('流动负债合计', {}).get('期末余额', 0) or 0,
            '短期借款': bs.get('短期借款', {}).get('期末余额', 0) or 0,
            '资产负债率': metrics.get('资产负债率', 0) or 0,
            '流动比率': metrics.get('流动比率', 0) or 0,
        })
    
    df_sol = pd.DataFrame(solvency_data)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**资产负债结构变化**")
        
        fig = go.Figure()
        fig.add_trace(go.Bar(
            name='净资产', x=years, y=df_sol['净资产'],
            marker_color='#10B981'
        ))
        fig.add_trace(go.Bar(
            name='总负债', x=years, y=df_sol['总负债'],
            marker_color='#EF4444'
        ))
        fig.update_layout(
            barmode='stack',
            height=350,
            template='plotly_white',
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.markdown("**流动性指标趋势**")
        
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        
        fig.add_trace(go.Scatter(
            x=years, y=df_sol['资产负债率'],
            mode='lines+markers',
            name='资产负债率 (%)',
            line=dict(color='#EF4444', width=3),
            marker=dict(size=10)
        ), secondary_y=False)
        
        fig.add_trace(go.Scatter(
            x=years, y=df_sol['流动比率'],
            mode='lines+markers',
            name='流动比率',
            line=dict(color='#3B82F6', width=3),
            marker=dict(size=10)
        ), secondary_y=True)
        
        fig.update_yaxes(title_text="资产负债率 (%)", secondary_y=False)
        fig.update_yaxes(title_text="流动比率", secondary_y=True)
        fig.update_layout(height=350, template='plotly_white')
        st.plotly_chart(fig, use_container_width=True)
    
    # 偿债能力评估
    st.markdown("**偿债能力评估**")
    
    latest_year = years[-1]
    latest = df_sol[df_sol['年份']==latest_year].iloc[0]
    
    assessments = []
    
    if latest['资产负债率'] < 30:
        assessments.append(f"✅ 资产负债率 {latest['资产负债率']:.1f}% (优秀)，长期偿债风险极低")
    elif latest['资产负债率'] < 50:
        assessments.append(f"✅ 资产负债率 {latest['资产负债率']:.1f}% (良好)，长期偿债风险可控")
    else:
        assessments.append(f"⚠️ 资产负债率 {latest['资产负债率']:.1f}% (偏高)，需关注债务风险")
    
    if latest['流动比率'] > 2:
        assessments.append(f"✅ 流动比率 {latest['流动比率']:.2f} (优秀)，短期偿债能力非常充裕")
    elif latest['流动比率'] > 1.5:
        assessments.append(f"✅ 流动比率 {latest['流动比率']:.2f} (良好)，短期偿债能力充足")
    elif latest['流动比率'] > 1:
        assessments.append(f"⚠️ 流动比率 {latest['流动比率']:.2f} (一般)，短期偿债能力尚可")
    else:
        assessments.append(f"🔴 流动比率 {latest['流动比率']:.2f} (危险)，短期偿债压力大")
    
    # 现金覆盖率
    if latest['流动负债'] > 0:
        cash_coverage = latest['货币资金'] / latest['流动负债'] * 100
        if cash_coverage > 50:
            assessments.append(f"✅ 现金覆盖率达 {cash_coverage:.1f}%，流动性充裕")
        else:
            assessments.append(f"⚠️ 现金覆盖率仅 {cash_coverage:.1f}%，需关注流动性")
    
    for a in assessments:
        st.markdown(f"- {a}")


def _render_fs_analysis():
    """渲染财务报表分析总入口"""
    
    # ===== 手动上传财务报表 =====
    st.markdown("### 📤 上传财务报表")
    st.caption("支持手动上传资产负债表和利润表，数据将自动解析并汇总到历史财务分析中。")
    
    col_upload1, col_upload2 = st.columns(2)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    base_path = os.path.join(project_root, 'watched')
    
    with col_upload1:
        bs_file = st.file_uploader("上传资产负债表", type=['xlsx', 'xls'], key='manual_bs_upload')
        if bs_file is not None:
            try:
                df_bs = pd.read_excel(bs_file)
                parsed = _parse_financial_statement(df_bs, 'balance_sheet')
                year = _parse_year_from_filename(bs_file.name) or '2025'
                _update_financial_statements_summary(base_path, year, 'balance_sheet', parsed)
                st.success(f"✓ 已导入 {year} 年资产负债表，共 {len(parsed)} 个科目")
            except Exception as e:
                st.error(f"× 导入失败: {e}")
    
    with col_upload2:
        pl_file = st.file_uploader("上传利润表", type=['xlsx', 'xls'], key='manual_pl_upload')
        if pl_file is not None:
            try:
                df_pl = pd.read_excel(pl_file)
                parsed = _parse_financial_statement(df_pl, 'profit_loss')
                year = _parse_year_from_filename(pl_file.name) or '2025'
                _update_financial_statements_summary(base_path, year, 'profit_loss', parsed)
                st.success(f"✓ 已导入 {year} 年利润表，共 {len(parsed)} 个科目")
            except Exception as e:
                st.error(f"× 导入失败: {e}")
    
    st.markdown("---")
    
    fs_data = load_financial_data()
    
    if not fs_data:
        st.info("💡 提示：请将财报数据文件放置于 `watched/financial_statements/` 目录下，或通过上方上传框手动导入。")
        return
    
    # 主要分析板块
    _render_three_year_overview(fs_data)
    _render_dupont_analysis(fs_data)
    _render_profitability_analysis(fs_data)
    _render_solvency_analysis(fs_data)
    
    # 财务健康度总结（基于最新数据动态生成）
    st.markdown("---")
    st.markdown("### 🏥 财务健康度总结")
    
    years = _get_available_years(fs_data)
    latest_year = years[-1] if years else None
    
    strengths = []
    risks = []
    suggestions = []
    
    if latest_year and latest_year in fs_data.get('years', {}):
        bs = fs_data['years'][latest_year]['balance_sheet']
        pl = fs_data['years'][latest_year]['profit_loss']
        metrics = fs_data['years'][latest_year]['metrics']
        
        debt_ratio = metrics.get('资产负债率', 0) or 0
        current_ratio = metrics.get('流动比率', 0) or 0
        cash = bs.get('货币资金', {}).get('期末余额', 0) or 0
        revenue = pl.get('营业收入', {}).get('本期金额', 0) or 0
        net_profit = pl.get('净利润', {}).get('本期金额', 0) or 0
        npm = (net_profit / revenue * 100) if revenue else 0
        receivable = bs.get('应收账款', {}).get('期末余额', 0) or 0
        current_assets = bs.get('流动资产合计', {}).get('期末余额', 0) or 0
        
        if debt_ratio < 40:
            strengths.append(f"✅ {latest_year}年资产负债率{debt_ratio:.1f}%，长期偿债风险较低")
        if current_ratio > 2:
            strengths.append(f"✅ {latest_year}年流动比率{current_ratio:.2f}，流动性充裕")
        if cash >= 5000000:
            strengths.append(f"✅ 现金储备{cash/10000:.0f}万，资金较为充裕")
        
        if debt_ratio >= 50:
            risks.append(f"⚠️ 资产负债率{debt_ratio:.1f}%偏高，需关注债务风险")
        if current_ratio <= 1.5:
            risks.append(f"⚠️ 流动比率{current_ratio:.2f}一般，短期偿债能力需关注")
        if npm < 10:
            risks.append(f"⚠️ {latest_year}年净利率{npm:.1f}%，盈利能力有待提升")
        if current_assets and receivable / current_assets > 0.3:
            risks.append(f"⚠️ 应收账款占流动资产{(receivable/current_assets*100):.1f}%，需关注回款")
        
        if npm < 10:
            suggestions.append("💡 优化成本结构，提升净利率")
        if current_assets and receivable / current_assets > 0.3:
            suggestions.append("💡 加强应收账款管理，改善现金流")
        if debt_ratio >= 50:
            suggestions.append("💡 控制负债规模，降低财务风险")
    
    if not strengths:
        strengths = ["✅ 财务数据已导入，可继续补充历史数据以完善分析"]
    if not risks:
        risks = ["ℹ️ 暂无显著风险指标"]
    if not suggestions:
        suggestions = ["💡 持续跟踪季度财务数据变化"]
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("**优势**")
        for s in strengths[:3]:
            st.markdown(f"- {s}")
    
    with col2:
        st.markdown("**风险**")
        for r in risks[:3]:
            st.markdown(f"- {r}")
    
    with col3:
        st.markdown("**建议**")
        for s in suggestions[:3]:
            st.markdown(f"- {s}")


def render_real_finance_page(analyzer):
    # 访问控制
    if not require_real_finance_auth():
        return
    
    col_title, col_logout = st.columns([6, 1])
    with col_title:
        st.markdown('<div class="main-header">📒 财务状况分析</div>', unsafe_allow_html=True)
        st.markdown('<div class="sub-header">基于2023-2025三年财报的深度财务分析</div>', unsafe_allow_html=True)
    with col_logout:
        if is_real_finance_protected():
            st.write("")
            st.write("")
            if st.button("🔓 退出登录", type="secondary", use_container_width=True, key="real_finance_logout_btn"):
                logout_real_finance()
                st.success("已退出")
                st.rerun()
    
    # 三年财报分析（优先显示）
    _render_fs_analysis()
    
    # 2026年实时财务数据（原功能保留）
    st.markdown("---")
    st.markdown("### 📅 2026年实时财务追踪")
    st.caption("基于上传的工资支出和费用支出数据进行实时分析")
    
    # 数据上传区
    st.markdown("#### 📁 上传2026年财务数据")
    
    col1, col2 = st.columns(2)
    
    with col1:
        salary_file = st.file_uploader("工资", type=['xlsx', 'xls', 'csv'], key='real_salary_file')
        if salary_file:
            try:
                if salary_file.name.lower().endswith('.csv'):
                    df_sal = pd.read_csv(salary_file)
                else:
                    df_sal = pd.read_excel(salary_file)
                records = load_real_salary_from_dataframe(df_sal)
                # 覆盖模式：先清除已有的 salary 记录，再导入新记录
                analyzer.real_cost_records = [r for r in analyzer.real_cost_records if r.category != 'salary']
                analyzer.real_cost_records.extend(records)
                st.success(f"✓ 导入工资记录 {len(records)} 条")
            except Exception as e:
                st.error(f"× 导入失败: {e}")
    
    with col2:
        expense_file = st.file_uploader("综合费用", type=['xlsx', 'xls', 'csv'], key='real_expense_file')
        if expense_file:
            try:
                if expense_file.name.lower().endswith('.csv'):
                    df_exp = pd.read_csv(expense_file)
                else:
                    df_exp = pd.read_excel(expense_file)
                records = load_real_salary_from_dataframe(df_exp)
                # 覆盖模式：先清除已有的 reimburse + fixed 记录，再导入新记录
                analyzer.real_cost_records = [r for r in analyzer.real_cost_records if r.category not in ('reimburse', 'fixed')]
                analyzer.real_cost_records.extend(records)
                st.success(f"✓ 导入费用记录 {len(records)} 条")
            except Exception as e:
                st.error(f"× 导入失败: {e}")
    
    # 清空按钮
    if st.button("🗑️ 清空已导入的财务数据", type="secondary"):
        analyzer.real_cost_records = []
        import auto_import, os
        watched_base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'watched')
        watched_base = os.path.abspath(watched_base)
        auto_import.clear_import_log(watched_base)
        st.success("已清空财务数据及导入记录")
        st.rerun()
    
    # 实时财务分析
    summary = analyzer.get_real_cost_summary()
    
    if summary['has_data']:
        st.markdown("---")
        st.markdown("#### 💰 2026年实时财务状况")
        
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        total_revenue = sum(p.actual_payment for p in analyzer.positions)
        operating_total = summary['operating_total']
        annual_bonus = summary.get('annual_bonus_2025', 0)
        operating_profit = total_revenue - operating_total
        operating_margin = (operating_profit / total_revenue * 100) if total_revenue > 0 else 0
        
        with c1:
            st.metric("累计回款", format_currency(total_revenue))
        with c2:
            st.metric("真实工资", format_currency(summary['salary']))
        with c3:
            st.metric("真实报销", format_currency(summary['reimburse']))
        with c4:
            st.metric("真实固定", format_currency(summary['fixed']))
        with c5:
            st.metric("经营总成本", format_currency(operating_total))
        with c6:
            st.metric("经营利润(不含奖金)", format_currency(operating_profit))
        
        # 下方注释：淡化奖金影响，强调不含奖金口径
        st.markdown(
            f"**经营利润(不含奖金):** {format_currency(operating_profit)} | "
            f"**经营利润率:** {operating_margin:.1f}%"
        )
        if annual_bonus > 0:
            st.caption(f"*注：本年度已发生年度递延奖金 {format_currency(annual_bonus)}（属上年度遗留），未计入上述经营利润*")
        
        # ===== 真实成本 vs 三倍成本预估对比 =====
        st.markdown("---")
        st.markdown("#### 📊 真实成本 vs 三倍成本预估对比")
        
        # 计算三倍成本预估（基于在职顾问月薪×3）
        assumed_monthly_cost = sum(
            cfg.get('monthly_salary', 15000) * 3.0
            for cfg in analyzer.consultant_configs.values()
            if cfg.get('is_active', True)
        )
        
        # 计算有效月份数：直接从 real_cost_records 中统计，不受positions回款月份干扰
        salary_months = set()
        expense_months = set()
        for r in analyzer.real_cost_records:
            ym = f"{r.date.year}-{r.date.month:02d}"
            if r.category == 'salary':
                salary_months.add(ym)
            elif r.category in ('reimburse', 'fixed'):
                expense_months.add(ym)
        
        salary_month_count = max(1, len(salary_months))
        expense_month_count = max(1, len(expense_months))
        month_count = max(salary_month_count, expense_month_count)
        
        avg_monthly_salary = summary['salary'] / salary_month_count
        avg_monthly_expense = (summary['reimburse'] + summary['fixed']) / expense_month_count
        avg_monthly_total = avg_monthly_salary + avg_monthly_expense
        
        diff = assumed_monthly_cost - avg_monthly_total
        coverage_ratio = (avg_monthly_total / assumed_monthly_cost * 100) if assumed_monthly_cost > 0 else 0
        
        col_a1, col_a2, col_a3, col_a4 = st.columns(4)
        with col_a1:
            st.metric("三倍成本预估/月", format_currency(assumed_monthly_cost))
        with col_a2:
            st.metric("月均实际工资", format_currency(avg_monthly_salary))
        with col_a3:
            st.metric("月均综合费用", format_currency(avg_monthly_expense))
        with col_a4:
            st.metric("月均实际总支出", format_currency(avg_monthly_total), 
                     delta=f"{coverage_ratio:.0f}%" if assumed_monthly_cost > 0 else None)
        
        st.caption(f"*工资基于 {salary_month_count} 个月、费用基于 {expense_month_count} 个月的有效出纳数据计算*")
        
        # 解读
        if coverage_ratio < 220:
            st.info(f"ℹ️ 月均实际总支出为三倍成本预估的 **{coverage_ratio:.0f}%**。实际支出约为 **{avg_monthly_total/assumed_monthly_cost*3:.1f}倍工资**，主要覆盖了工资和固定摊销/社保税务等成本，奖金部分预留空间较大（差异约 {format_currency(diff)}）")
        elif coverage_ratio <= 280:
            st.info(f"ℹ️ 月均实际总支出为三倍成本预估的 **{coverage_ratio:.0f}%**。实际支出约为 **{avg_monthly_total/assumed_monthly_cost*3:.1f}倍工资**，成本结构与预估基本匹配（差异约 {format_currency(diff)}）")
        else:
            st.warning(f"⚠️ 月均实际总支出为三倍成本预估的 **{coverage_ratio:.0f}%**。实际支出约为 **{avg_monthly_total/assumed_monthly_cost*3:.1f}倍工资**，已接近或超过三倍成本预估，需关注费用控制（差异约 {format_currency(diff)}）")
        
        # 月度盈亏表（不含奖金口径）
        st.markdown("#### 📅 月度真实盈亏")
        monthly_df = analyzer.get_monthly_real_summary_df()
        if not monthly_df.empty:
            # 默认只显示不含奖金口径
            display_cols = ['年月', '回款', '真实工资', '真实报销', '真实固定', '经营总成本(不含奖金)', '经营利润(不含奖金)']
            st.dataframe(monthly_df[display_cols], use_container_width=True, hide_index=True)
            
            # 含奖金的完整数据作为参考
            if (monthly_df['年度奖金'] > 0).any():
                with st.expander("查看含奖金的完整数据"):
                    bonus_cols = ['年月', '回款', '年度奖金', '真实总成本', '真实利润']
                    st.dataframe(monthly_df[bonus_cols], use_container_width=True, hide_index=True)
        
        # 顾问真实盈亏
        st.markdown("#### 👤 顾问真实盈亏")
        consultant_df = analyzer.get_consultant_real_profit_analysis()
        if not consultant_df.empty:
            st.dataframe(consultant_df, use_container_width=True, hide_index=True)
        
        # 职位真实边际贡献
        st.markdown("#### 📋 职位真实边际贡献")
        if analyzer.positions:
            pos_real_df = analyzer.get_position_real_mc_analysis()
            if not pos_real_df.empty:
                st.dataframe(pos_real_df, use_container_width=True, hide_index=True)
    else:
        st.info("📊 请上传2026年财务数据（工资表、综合费用表）以查看实时分析")
