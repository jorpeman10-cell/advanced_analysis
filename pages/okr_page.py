"""
OKR分析和绩效工资计算页面
支持自动从固定路径读取OKR Excel，自动计算奖金
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import sys
import os
import tempfile
import glob

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from okr_analyzer import OKRDataStore, OKRCalculator, OKRParser


# 固定路径配置
OKR_WATCH_PATHS = [
    "D:/win设备桌面/2025年业绩核算/OKR 记录",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "watched", "okr"),
]


def format_currency(value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "¥0"
    if abs(value) >= 10000:
        return f"¥{value/10000:.1f}万"
    return f"¥{value:,.0f}"


def find_okr_excel(year: int, month: int) -> str:
    """查找固定路径下的OKR Excel文件"""
    # 尝试多种命名格式
    patterns = [
        f"OKR-{year}.{month}.xlsx",
        f"OKR-{year}{month:02d}.xlsx",
        f"OKR-{year}-{month}.xlsx",
        f"OKR_{year}_{month}.xlsx",
        f"OKR-{year}.{month}*.xlsx",
        f"OKR*.xlsx",
    ]
    
    for path in OKR_WATCH_PATHS:
        if not os.path.exists(path):
            continue
        for pattern in patterns:
            full_pattern = os.path.join(path, pattern)
            files = glob.glob(full_pattern)
            if files:
                # 返回最新修改的文件
                return max(files, key=os.path.getmtime)
    return ""


def auto_load_okr_configs(store: OKRDataStore, year: int, month: int) -> bool:
    """自动加载OKR配置：优先从已有配置，其次从Excel文件"""
    # 1. 检查是否已有配置
    configs = store.load_all()
    if configs:
        return True
    
    # 2. 尝试从固定路径读取Excel
    excel_path = find_okr_excel(year, month)
    if excel_path and os.path.exists(excel_path):
        try:
            store.parse_and_save(excel_path)
            return True
        except Exception as e:
            print(f"[OKR] 自动解析Excel失败: {e}")
            return False
    
    return False


def auto_calculate_okr(store: OKRDataStore, year: int, month: int) -> list:
    """自动计算所有顾问的OKR奖金"""
    configs = store.load_all()
    if not configs:
        return []
    
    # 检查数据库连接
    try:
        import db_config_manager
        from gllue_db_client import GllueDBClient
        if not db_config_manager.has_config():
            return []
        
        db_client = GllueDBClient(db_config_manager.get_gllue_db_config())
        calc = OKRCalculator(db_client)
        
        all_results = []
        for c in configs:
            result = calc.calculate(c, year, month)
            all_results.append(result)
        
        return all_results
    except Exception as e:
        print(f"[OKR] 自动计算失败: {e}")
        return []


def render_okr_page():
    """渲染OKR分析页面"""
    st.markdown('<div class="main-header">🎯 OKR分析与绩效工资</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">自动从系统获取数据计算奖金</div>', unsafe_allow_html=True)
    
    # 初始化
    store = OKRDataStore()
    
    # 月份选择（移到主内容区顶部，避免sidebar冲突）
    col1, col2, col3 = st.columns([2, 2, 6])
    with col1:
        year = st.selectbox("年份", [2025, 2026], index=1, key="okr_year")
    with col2:
        month = st.selectbox("月份", list(range(1, 13)), index=2, key="okr_month")
    with col3:
        # 自动加载状态
        has_configs = auto_load_okr_configs(store, year, month)
        if has_configs:
            configs = store.load_all()
            st.success(f"✅ 已加载 {len(configs)} 位顾问的OKR配置")
        else:
            st.info("💡 未找到OKR配置，请手动上传Excel文件")
    
    # 自动计算（页面加载时自动执行）
    if has_configs:
        cache_key = f"okr_results_{year}_{month}"
        if cache_key not in st.session_state:
            with st.spinner("正在自动计算奖金..."):
                results = auto_calculate_okr(store, year, month)
                if results:
                    st.session_state[cache_key] = results
                    st.session_state.okr_results = results
                    st.success(f"✅ 自动计算完成！{len(results)}位顾问")
    
    # 标签页
    tab1, tab2 = st.tabs(["📋 规则配置与计算", "📊 计算结果"])
    
    with tab1:
        render_config_and_calc(store, year, month)
    
    with tab2:
        render_results(store, year, month)


def render_config_and_calc(store: OKRDataStore, year: int, month: int):
    """规则配置和计算"""
    
    # 上传Excel（作为fallback）
    with st.expander("📤 手动上传OKR模板（可选）"):
        uploaded = st.file_uploader("选择OKR Excel文件", type=['xlsx', 'xls'], key='okr_upload')
        
        if uploaded:
            if st.button("🔄 解析规则", type="primary"):
                with st.spinner("解析中..."):
                    try:
                        # 保存临时文件
                        temp = os.path.join(tempfile.gettempdir(), f"okr_{datetime.now().strftime('%Y%m%d%H%M%S')}.xlsx")
                        with open(temp, "wb") as f:
                            f.write(uploaded.getvalue())
                        
                        # 解析并保存
                        consultants = store.parse_and_save(temp)
                        st.success(f"✅ 已解析并保存 {len(consultants)} 位顾问的OKR规则")
                        
                        # 自动重新计算
                        cache_key = f"okr_results_{year}_{month}"
                        if cache_key in st.session_state:
                            del st.session_state[cache_key]
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"解析失败: {e}")
                        import traceback
                        st.code(traceback.format_exc())
    
    # 显示已配置规则
    st.markdown("---")
    st.markdown("### 📋 已配置的规则")
    
    configs = store.load_all()
    if not configs:
        st.info("暂无配置，系统会自动检测以下路径的OKR Excel文件：")
        for p in OKR_WATCH_PATHS:
            st.caption(f"- `{p}`")
        return
    
    st.write(f"共 **{len(configs)}** 位顾问已配置")
    
    # 选择顾问查看
    names = [c.name for c in configs]
    selected = st.selectbox("查看顾问规则", names)
    
    if selected:
        c = store.load(selected)
        if c:
            st.write(f"**级别**: {c.level} | **团队**: {c.team} | **汇报线**: {c.manager}")
            st.write(f"**奖金基数**: {c.base_bonus}元")
            
            rules_data = []
            for r in c.rules:
                rules_data.append({
                    '指标': r.name,
                    '目标': r.target_desc,
                    '权重': r.weight,
                    '周期': r.period,
                    '奖金基数': r.base_amount,
                    '计分规则': str(r.score_rules) if r.score_rules else '按比例',
                })
            st.dataframe(pd.DataFrame(rules_data), hide_index=True, use_container_width=True)
    
    # 手动计算按钮（如果自动计算失败）
    st.markdown("---")
    st.markdown("### 🚀 手动计算")
    
    # 检查数据库连接
    db_ok = False
    try:
        import db_config_manager
        from gllue_db_client import GllueDBClient
        db_ok = db_config_manager.has_config()
    except:
        pass
    
    if not db_ok:
        st.warning("⚠️ 未配置数据库连接，无法自动获取系统数据")
        return
    
    if st.button("🚀 重新计算", type="primary"):
        with st.spinner("计算中..."):
            try:
                cache_key = f"okr_results_{year}_{month}"
                results = auto_calculate_okr(store, year, month)
                if results:
                    st.session_state[cache_key] = results
                    st.session_state.okr_results = results
                    st.success(f"✅ 计算完成！{len(results)}位顾问")
                else:
                    st.warning("计算结果为空，请检查配置")
            except Exception as e:
                st.error(f"计算失败: {e}")
                import traceback
                st.code(traceback.format_exc())


def render_results(store: OKRDataStore, year: int, month: int):
    """显示计算结果"""
    
    cache_key = f"okr_results_{year}_{month}"
    
    if cache_key not in st.session_state and 'okr_results' not in st.session_state:
        st.info("暂无计算结果，请在『规则配置与计算』标签页等待自动计算完成")
        return
    
    results = st.session_state.get(cache_key) or st.session_state.get('okr_results', [])
    
    if not results:
        st.info("计算结果为空")
        return
    
    # 汇总
    st.markdown("### 📊 汇总")
    total = sum(r['total_bonus'] for r in results)
    
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("顾问人数", len(results))
    with c2:
        st.metric("总奖金", format_currency(total))
    with c3:
        avg = total / len(results) if results else 0
        st.metric("人均奖金", format_currency(avg))
    
    # 结果表格
    st.markdown("### 📋 明细")
    
    data = []
    for r in results:
        data.append({
            '顾问': r['consultant'],
            '中文名': r['chinese_name'],
            '总奖金': r['total_bonus'],
        })
    
    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    # 详细展开
    st.markdown("### 🔍 详细计算过程")
    for r in results:
        with st.expander(f"{r['consultant']} ({r['chinese_name']}) - {format_currency(r['total_bonus'])}"):
            for rule in r['rules']:
                col1, col2, col3 = st.columns([3, 2, 3])
                with col1:
                    st.write(f"**{rule['name']}**")
                    st.caption(f"目标: {rule['target']} | 权重: {rule['weight']}")
                with col2:
                    st.write(f"实际: {rule['actual']}")
                    st.write(f"奖金: {format_currency(rule['bonus'])}")
                with col3:
                    st.caption(rule['detail'])
