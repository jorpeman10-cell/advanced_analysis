#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
猎头公司财务分析工具 - 完整版
版本: v1.11
发布日期: 2026-04-07
新增: 数据预加载机制，减少标签页切换等待时间
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from models import AdvancedRecruitmentAnalyzer, PositionLifecycle, CashFlowEvent
from alert_page import render_alert_system
from pages.real_finance_page import render_real_finance_page
import auto_import
import auth_guard

st.set_page_config(
    page_title="T-STAR 猎头财务分析 v1.11",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
/* ===== 全局风格：咨询级灰白蓝 ===== */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

.main-header {
    font-size: 2rem;
    font-weight: 700;
    color: #1a365d;
    margin-bottom: 0.3rem;
    font-family: 'Inter', sans-serif;
    letter-spacing: -0.02em;
}
.sub-header {
    font-size: 0.95rem;
    color: #718096;
    margin-bottom: 1.5rem;
    font-family: 'Inter', sans-serif;
}

/* KPI 卡片 */
.kpi-card {
    background: linear-gradient(135deg, #ffffff 0%, #f7fafc 100%);
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 20px 16px;
    text-align: center;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    transition: all 0.2s ease;
}
.kpi-card:hover {
    box-shadow: 0 4px 12px rgba(26,54,93,0.1);
    transform: translateY(-1px);
}
.kpi-value {
    font-size: 2.4rem;
    font-weight: 700;
    color: #1a365d;
    line-height: 1.2;
    margin: 8px 0;
    font-family: 'Inter', sans-serif;
}
.kpi-value.positive { color: #059669; }
.kpi-value.warning { color: #d97706; }
.kpi-value.danger { color: #dc2626; }
.kpi-label {
    font-size: 0.8rem;
    color: #718096;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    font-weight: 500;
    font-family: 'Inter', sans-serif;
}
.kpi-delta {
    font-size: 0.8rem;
    font-weight: 600;
    margin-top: 4px;
    font-family: 'Inter', sans-serif;
}

/* 章节标题 */
.section-title {
    font-size: 1.1rem;
    font-weight: 600;
    color: #2d3748;
    margin: 24px 0 12px 0;
    padding-bottom: 8px;
    border-bottom: 2px solid #e2e8f0;
    font-family: 'Inter', sans-serif;
}
.section-title .icon {
    margin-right: 6px;
}

/* 数据表格美化 */
.data-table th {
    background-color: #f7fafc !important;
    color: #2d3748 !important;
    font-weight: 600 !important;
    font-size: 0.85rem !important;
    border-bottom: 2px solid #e2e8f0 !important;
}
.data-table td {
    font-size: 0.85rem !important;
    color: #4a5568 !important;
    border-bottom: 1px solid #edf2f7 !important;
}
.data-table tr:hover td {
    background-color: #f7fafc !important;
}

/* 状态标签 */
.status-tag {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 600;
    font-family: 'Inter', sans-serif;
}
.status-good { background: #d1fae5; color: #065f46; }
.status-warning { background: #fef3c7; color: #92400e; }
.status-danger { background: #fee2e2; color: #991b1b; }
.status-info { background: #dbeafe; color: #1e40af; }

/* 侧边栏优化 */
[data-testid="stSidebar"] {
    background-color: #f8fafc !important;
}
[data-testid="stSidebar"] .stMarkdown h3 {
    color: #2d3748 !important;
    font-size: 0.9rem !important;
    font-weight: 600 !important;
}
[data-testid="stSidebar"] .stButton>button {
    border-radius: 8px !important;
    font-weight: 500 !important;
}
[data-testid="stSidebar"] .stButton>button[kind="primary"] {
    background-color: #1a365d !important;
    border-color: #1a365d !important;
}
[data-testid="stSidebar"] .stButton>button[kind="primary"]:hover {
    background-color: #2c5282 !important;
    border-color: #2c5282 !important;
}

/* Tab 美化 */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    border-bottom: 2px solid #e2e8f0;
}
.stTabs [data-baseweb="tab"] {
    padding: 10px 20px !important;
    font-weight: 500 !important;
    color: #718096 !important;
    border-radius: 8px 8px 0 0 !important;
}
.stTabs [data-baseweb="tab"][aria-selected="true"] {
    color: #1a365d !important;
    border-bottom: 2px solid #1a365d !important;
    background: #f7fafc !important;
}

/* 预警卡片 */
.alert-card {
    border-radius: 10px;
    padding: 16px;
    margin: 8px 0;
    border-left: 4px solid;
}
.alert-card.success { background: #f0fdf4; border-left-color: #059669; }
.alert-card.warning { background: #fffbeb; border-left-color: #d97706; }
.alert-card.danger { background: #fef2f2; border-left-color: #dc2626; }
.alert-card.info { background: #eff6ff; border-left-color: #2563eb; }

/* 分页按钮 */
.stButton>button {
    border-radius: 8px !important;
}
.stButton>button[kind="primary"] {
    background-color: #1a365d !important;
    border-color: #1a365d !important;
}
.stButton>button[kind="primary"]:hover {
    background-color: #2c5282 !important;
}

/* 分割线 */
hr {
    border: none;
    height: 1px;
    background: linear-gradient(90deg, transparent, #e2e8f0, transparent);
    margin: 20px 0;
}

/* 小字注释 */
.caption-muted {
    color: #a0aec0;
    font-size: 0.8rem;
    font-style: italic;
}

/* ===== 移动端适配 ===== */
@media screen and (max-width: 768px) {
    .main-header {
        font-size: 1.4rem !important;
    }
    .sub-header {
        font-size: 0.85rem !important;
    }
    .kpi-value {
        font-size: 1.6rem !important;
    }
    .kpi-card {
        padding: 12px 8px !important;
    }
    .section-title {
        font-size: 1rem !important;
        margin: 16px 0 8px 0 !important;
    }
    .stDataFrame {
        overflow-x: auto !important;
    }
    [data-testid="stHorizontalBlock"] {
        gap: 0.5rem !important;
    }
}

@media (pointer: coarse) {
    .kpi-card {
        min-height: 80px;
    }
    .stButton>button {
        min-height: 44px;
        font-size: 1rem;
    }
}
</style>
""", unsafe_allow_html=True)

def format_currency(value):
    """格式化货币显示"""
    if pd.isna(value) or value is None:
        return "¥0"
    if abs(value) >= 10000:
        return f"¥{value/10000:.1f}万"
    return f"¥{value:,.0f}"

def format_percent(value):
    """格式化百分比显示"""
    if pd.isna(value) or value is None:
        return "0.0%"
    return f"{value*100:.1f}%"


def render_sidebar():
    """渲染侧边栏"""
    st.sidebar.markdown("<div style='font-size: 1.5rem; font-weight: bold; color: #1E3A8A;'>📊 数据配置</div>", unsafe_allow_html=True)
    st.sidebar.markdown("<div style='font-size: 0.75rem; color: #718096;'>v1.11</div>", unsafe_allow_html=True)
    
    analyzer = st.session_state.analyzer
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📁 数据上传")
    
    # 成单数据上传
    deal_file = st.sidebar.file_uploader("成单数据 (Excel)", type=['xlsx', 'xls'], key='deal_file')
    if deal_file:
        try:
            df_deals = pd.read_excel(deal_file)
            analyzer.load_positions_from_dataframe(df_deals)
            st.sidebar.success(f"✓ 成单数据: {len(df_deals)}条")
        except Exception as e:
            st.sidebar.error(f"× 加载失败: {e}")
    
    # 顾问数据上传
    consultant_file = st.sidebar.file_uploader("顾问数据 (Excel)", type=['xlsx', 'xls'], key='consultant_file')
    if consultant_file:
        try:
            df_consultants = pd.read_excel(consultant_file)
            # 清空现有顾问配置，防止重复叠加
            analyzer.consultant_configs = {}
            # 加载顾问配置
            for idx, row in df_consultants.iterrows():
                name = row.get('name')
                if pd.notna(name):
                    salary = float(row['base_salary']) if pd.notna(row.get('base_salary')) else 20000
                    is_active = bool(row.get('is_active', True))
                    analyzer.consultant_configs[name] = {
                        'monthly_salary': salary,
                        'is_active': is_active,
                        'salary_multiplier': 3.0
                    }
            st.sidebar.success(f"✓ 顾问数据: {len(df_consultants)}人")
        except Exception as e:
            st.sidebar.error(f"× 加载失败: {e}")
    
    # Forecast数据上传
    forecast_file = st.sidebar.file_uploader("Forecast数据 (Excel)", type=['xlsx'], key='forecast_file')
    if forecast_file:
        try:
            df_forecast = pd.read_excel(forecast_file)
            analyzer.load_forecast_from_dataframe(df_forecast)
            st.sidebar.success(f"✓ Forecast: {len(df_forecast)}条")
        except Exception as e:
            st.sidebar.error(f"× 加载失败: {e}")
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🔄 Gllue API 同步")
    
    with st.sidebar.expander("配置谷露 API", expanded=False):
        # API 配置
        gllue_base_url = st.text_input(
            "Gllue 域名",
            value=st.session_state.get('gllue_base_url', ''),
            placeholder="如: yourcompany.gllue.com",
            help="你的谷露系统域名，不需要 https:// 前缀"
        )
        gllue_api_key = st.text_input(
            "API 密钥",
            value=st.session_state.get('gllue_api_key', ''),
            type="password",
            placeholder="从谷露系统获取的 API Key"
        )
        
        # 同步日期范围
        sync_start_date = st.date_input(
            "开始日期",
            value=datetime.now() - timedelta(days=365),
            help="同步此日期之后的 Offer/入职数据"
        )
        sync_end_date = st.date_input(
            "结束日期",
            value=datetime.now(),
            help="同步此日期之前的 Offer/入职数据"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("💾 保存", width='stretch'):
                st.session_state.gllue_base_url = gllue_base_url
                st.session_state.gllue_api_key = gllue_api_key
                st.success("已保存")
        
        with col2:
            if st.button("🔌 测试", width='stretch'):
                if not gllue_base_url or not gllue_api_key:
                    st.error("请填写域名和密钥")
                else:
                    with st.spinner("测试中..."):
                        try:
                            import sys
                            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                            from gllue_client import GllueConfig, GllueAPIClient
                            
                            config = GllueConfig(
                                base_url=gllue_base_url,
                                api_key=gllue_api_key
                            )
                            client = GllueAPIClient(config)
                            test_data = client.get_users()
                            st.success(f"连接成功！{len(test_data)} 个用户")
                        except Exception as e:
                            st.error(f"连接失败: {str(e)[:50]}")
        
        if st.button("🚀 同步数据", type="primary", width='stretch'):
            if not gllue_base_url or not gllue_api_key:
                st.error("请填写域名和密钥")
            else:
                with st.spinner("正在同步..."):
                    try:
                        import sys
                        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                        from gllue_client import GllueConfig, GllueAPIClient
                        
                        config = GllueConfig(
                            base_url=gllue_base_url,
                            api_key=gllue_api_key
                        )
                        client = GllueAPIClient(config)
                        
                        stats = client.sync_to_finance_analyzer(
                            analyzer,
                            start_date=sync_start_date.strftime('%Y-%m-%d'),
                            end_date=sync_end_date.strftime('%Y-%m-%d')
                        )
                        
                        st.success(f"同步完成！Offer: {stats['offers_fetched']}, 入职: {stats['onboards_fetched']}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"同步失败: {str(e)[:100]}")
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🔄 自动同步")
    
    with st.sidebar.expander("📁 文件夹自动监控", expanded=False):
        watched_base = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'watched')
        watched_base = os.path.abspath(watched_base)
        auto_import.ensure_watched_dirs(watched_base)
        
        st.write(f"**监控目录:** `{watched_base}`")
        st.caption("📂 将Excel/CSV文件放入对应子目录，点击『立即扫描』自动导入")
        
        if st.button("🔄 立即扫描", width='stretch', key="auto_scan_btn"):
            with st.spinner("扫描中..."):
                results = auto_import.scan_and_import(analyzer, watched_base)
                if results:
                    for r in results:
                        if r['status'] == 'success':
                            st.success(f"✓ [{r['type']}] {r['file']}: {r['message']}")
                        elif r['status'] == 'failed':
                            st.error(f"× {r['file']}: {r['message']}")
                        else:
                            st.info(f"- {r['file']}: {r['message']}")
                else:
                    st.info("未发现新文件")
        
        history = auto_import.get_import_history(watched_base)
        if history:
            st.write("**最近导入记录:**")
            for h in history[:5]:
                st.caption(f"{h['imported_at'][:10]} | {h['type']} | {h['file']} ({h['rows']}行)")
        
        if st.button("🗑️ 清空导入记录", type="secondary", width='stretch', key="clear_import_log_btn"):
            auto_import.clear_import_log(watched_base)
            st.success("已清空，下次扫描将重新导入所有文件")
    
    # 数据库直连配置（新版：密码后台存储，界面不暴露）
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🗄️ 数据库连接")
    
    # 导入配置管理模块
    import db_config_manager
    
    # 检查是否已配置
    db_configured = db_config_manager.has_config()
    
    if not db_configured:
        st.sidebar.warning("⚠️ 未配置数据库连接")
        with st.sidebar.expander("首次配置数据库", expanded=True):
            st.info("请填写数据库连接信息，密码将安全保存在本地配置文件")
            cfg_use_ssh = st.checkbox("通过 SSH 隧道连接", value=True)
            if cfg_use_ssh:
                cfg_ssh_host = st.text_input("SSH 服务器", value="118.190.96.172")
                cfg_ssh_port = st.number_input("SSH 端口", value=9998, min_value=1, max_value=65535)
                cfg_ssh_user = st.text_input("SSH 用户名", value="root")
                cfg_ssh_pass = st.text_input("SSH 密码", type="password")
            cfg_db_host = st.text_input("数据库 Host", value="127.0.0.1")
            cfg_db_port = st.number_input("数据库端口", value=3306, min_value=1, max_value=65535)
            cfg_db_name = st.text_input("数据库名", value="gllue")
            cfg_db_user = st.text_input("数据库用户名", value="debian-sys-maint")
            cfg_db_pass = st.text_input("数据库密码", type="password")
            
            if st.button("💾 保存并连接", type="primary", key="first_save"):
                if not all([cfg_db_host, cfg_db_name, cfg_db_user, cfg_db_pass]):
                    st.error("请填写完整的数据库连接信息")
                else:
                    new_config = {
                        "host": cfg_db_host,
                        "port": int(cfg_db_port),
                        "database": cfg_db_name,
                        "username": cfg_db_user,
                        "password": cfg_db_pass,
                        "use_ssh": cfg_use_ssh,
                        "ssh_host": cfg_ssh_host if cfg_use_ssh else "",
                        "ssh_port": int(cfg_ssh_port) if cfg_use_ssh else 22,
                        "ssh_user": cfg_ssh_user if cfg_use_ssh else "",
                        "ssh_password": cfg_ssh_pass if cfg_use_ssh else "",
                    }
                    if db_config_manager.save_db_config(new_config):
                        st.success("✅ 配置已保存")
                        st.rerun()
                    else:
                        st.error("保存失败")
    else:
        # 已配置：显示连接状态和操作按钮
        db_cfg = db_config_manager.load_db_config()
        
        # 每次启动都尝试连接（不重试间隔限制）
        conn_status = st.session_state.get('db_connection_status', None)
        conn_error = st.session_state.get('db_connection_error', '')
        
        # 自动检测（仅在未连接时）
        if conn_status != 'connected':
            try:
                from gllue_db_client import GllueDBClient
                db_client = GllueDBClient(db_config_manager.get_gllue_db_config())
                ok, table_count = db_client.test_connection_and_tables()
                if ok:
                    st.session_state.db_connection_status = 'connected'
                    st.session_state.db_connection_error = ''
                    st.session_state.db_table_count = table_count
                    conn_status = 'connected'
            except Exception as e:
                st.session_state.db_connection_status = 'failed'
                err_msg = str(e)
                # 精简错误信息
                if 'Authentication' in err_msg:
                    err_msg = 'SSH/数据库密码错误'
                elif 'Connection refused' in err_msg or 'Unable to connect' in err_msg:
                    err_msg = '无法连接到服务器，请检查IP/端口'
                elif 'Network' in err_msg or 'timed out' in err_msg:
                    err_msg = '连接超时，请检查网络'
                st.session_state.db_connection_error = err_msg
                conn_status = 'failed'
        
        # 显示连接状态
        if conn_status == 'connected':
            st.sidebar.success("✅ 数据库已连接")
        elif conn_status == 'failed':
            st.sidebar.error(f"❌ {conn_error or '连接失败'}")
            st.sidebar.caption("💡 点击『设置』→『测试连接』检查配置")
        else:
            st.sidebar.info("⏳ 未连接数据库")
        
        # 同步数据按钮
        sync_col1, sync_col2 = st.sidebar.columns([3, 2])
        with sync_col1:
            if st.button("🚀 同步数据", type="primary", key="db_sync_btn"):
                with st.spinner("同步中..."):
                    try:
                        from gllue_db_client import GllueDBClient
                        db_client = GllueDBClient(db_config_manager.get_gllue_db_config())
                        stats = db_client.sync_to_finance_analyzer(
                            analyzer,
                            start_date=sync_start_date.strftime('%Y-%m-%d'),
                            end_date=sync_end_date.strftime('%Y-%m-%d')
                        )
                        st.session_state.db_connection_status = 'connected'
                        st.session_state.db_connection_error = ''
                        
                        # 同步完成后，刷新预加载数据
                        try:
                            from data_preloader import DataPreloader
                            preloader = DataPreloader()
                            preloader.reset()
                            preloader.start_loading(db_client)
                        except Exception:
                            pass
                        
                        st.sidebar.success(f"✅ 同步完成")
                        st.sidebar.caption(f"Offer:{stats['offers_fetched']} | Invoice:{stats['invoices_fetched']} | Forecast:{stats['forecasts_fetched']}")
                        st.rerun()
                    except Exception as e:
                        st.session_state.db_connection_status = 'failed'
                        err_msg = str(e)
                        if 'Authentication' in err_msg:
                            err_msg = '密码错误，请检查配置'
                        st.session_state.db_connection_error = err_msg
                        st.sidebar.error(f"同步失败: {err_msg[:80]}")
        
        with sync_col2:
            if st.button("⚙️ 设置", key="db_settings_btn"):
                st.session_state.show_db_settings = True
        
        # 设置面板（弹窗）
        if st.session_state.get('show_db_settings', False):
            with st.sidebar.expander("数据库设置", expanded=True):
                st.info("修改数据库连接配置")
                edit_use_ssh = st.checkbox("SSH 隧道", value=db_cfg.get('use_ssh', True))
                if edit_use_ssh:
                    edit_ssh_host = st.text_input("SSH 服务器", value=db_cfg.get('ssh_host', '118.190.96.172'))
                    edit_ssh_port = st.number_input("SSH 端口", value=db_cfg.get('ssh_port', 9998), min_value=1, max_value=65535)
                    edit_ssh_user = st.text_input("SSH 用户", value=db_cfg.get('ssh_user', 'root'))
                    edit_ssh_pass = st.text_input("SSH 密码", type="password", value=db_cfg.get('ssh_password', ''))
                edit_db_host = st.text_input("DB Host", value=db_cfg.get('host', '127.0.0.1'))
                edit_db_port = st.number_input("DB 端口", value=db_cfg.get('port', 3306), min_value=1, max_value=65535)
                edit_db_name = st.text_input("DB 名称", value=db_cfg.get('database', 'gllue'))
                edit_db_user = st.text_input("DB 用户", value=db_cfg.get('username', ''))
                edit_db_pass = st.text_input("DB 密码", type="password", value=db_cfg.get('password', ''))
                
                c1, c2, c3 = st.columns([2, 2, 2])
                with c1:
                    if st.button("💾 保存", key="save_settings"):
                        updated = {
                            "host": edit_db_host,
                            "port": int(edit_db_port),
                            "database": edit_db_name,
                            "username": edit_db_user,
                            "password": edit_db_pass,
                            "use_ssh": edit_use_ssh,
                            "ssh_host": edit_ssh_host if edit_use_ssh else "",
                            "ssh_port": int(edit_ssh_port) if edit_use_ssh else 22,
                            "ssh_user": edit_ssh_user if edit_use_ssh else "",
                            "ssh_password": edit_ssh_pass if edit_use_ssh else "",
                        }
                        if db_config_manager.save_db_config(updated):
                            st.success("已保存")
                            st.session_state.show_db_settings = False
                            # 重置连接状态，下次自动检测
                            st.session_state.db_connection_status = None
                            st.session_state.db_connection_error = ''
                            st.rerun()
                with c2:
                    if st.button("🔌 测试", key="test_settings"):
                        test_cfg = {
                            "host": edit_db_host,
                            "port": int(edit_db_port),
                            "database": edit_db_name,
                            "username": edit_db_user,
                            "password": edit_db_pass,
                            "use_ssh": edit_use_ssh,
                            "ssh_host": edit_ssh_host if edit_use_ssh else "",
                            "ssh_port": int(edit_ssh_port) if edit_use_ssh else 22,
                            "ssh_user": edit_ssh_user if edit_use_ssh else "",
                            "ssh_password": edit_ssh_pass if edit_use_ssh else "",
                        }
                        with st.spinner("测试中..."):
                            try:
                                from gllue_db_client import GllueDBConfig, GllueDBClient
                                tcfg = GllueDBConfig(
                                    host=test_cfg['host'],
                                    port=test_cfg['port'],
                                    database=test_cfg['database'],
                                    username=test_cfg['username'],
                                    password=test_cfg['password'],
                                    use_ssh=test_cfg['use_ssh'],
                                    ssh_host=test_cfg['ssh_host'],
                                    ssh_port=test_cfg['ssh_port'],
                                    ssh_user=test_cfg['ssh_user'],
                                    ssh_password=test_cfg['ssh_password'],
                                )
                                tclient = GllueDBClient(tcfg)
                                ok, tcount = tclient.test_connection_and_tables()
                                if ok:
                                    st.success(f"✅ 连接成功！{tcount} 张表")
                                else:
                                    st.error("连接成功但无法读取表")
                            except Exception as te:
                                terr = str(te)
                                if 'Authentication' in terr:
                                    st.error("❌ 认证失败：SSH或数据库密码错误")
                                elif 'Connection refused' in terr:
                                    st.error("❌ 连接被拒绝：请检查IP和端口")
                                else:
                                    st.error(f"❌ {terr[:100]}")
                with c3:
                    if st.button("❌ 取消", key="cancel_settings"):
                        st.session_state.show_db_settings = False
                        st.rerun()
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### ⚙️ 基础配置")
    
    # 核算模式切换
    if 'use_real_costs' not in analyzer.config:
        analyzer.config['use_real_costs'] = False
    mode_options = {False: "假设模式 (3倍工资估算)", True: "财务状况分析模式 (实际工资/报销/固定)"}
    current_mode = analyzer.config.get('use_real_costs', False)
    selected_mode = st.sidebar.radio(
        "核算模式",
        options=[False, True],
        format_func=lambda x: mode_options[x],
        index=0 if not current_mode else 1,
        key="cost_mode_radio"
    )
    if selected_mode != current_mode:
        analyzer.config['use_real_costs'] = selected_mode
        st.sidebar.success(f"已切换到: {mode_options[selected_mode]}")
        st.rerun()
    
    # 现金储备
    if 'cash_reserve' not in analyzer.config:
        analyzer.config['cash_reserve'] = 1800000
    analyzer.config['cash_reserve'] = st.sidebar.number_input(
        "现金储备 (元)",
        value=int(analyzer.config['cash_reserve']),
        step=100000
    )
    
    # 工资倍数
    if 'salary_multiplier' not in analyzer.config:
        analyzer.config['salary_multiplier'] = 3.0
    analyzer.config['salary_multiplier'] = st.sidebar.slider(
        "成本倍数 (工资×N)",
        min_value=2.0, max_value=5.0, value=3.0, step=0.5,
        help="包含社保、办公费用等的综合倍数"
    )
    
    st.sidebar.markdown("---")
    
    # 数据摘要
    if analyzer.positions or analyzer.forecast_positions or analyzer.real_cost_records:
        st.sidebar.markdown("### 📈 数据摘要")
        if analyzer.positions:
            st.sidebar.write(f"- 成单数据: {len(analyzer.positions)}条")
        if analyzer.consultant_configs:
            active_count = sum(1 for c in analyzer.consultant_configs.values() if c.get('is_active', True))
            st.sidebar.write(f"- 在职顾问: {active_count}人")
        if analyzer.forecast_positions:
            st.sidebar.write(f"- Forecast: {len(analyzer.forecast_positions)}条")
        if analyzer.real_cost_records:
            real_summary = analyzer.get_real_cost_summary()
            st.sidebar.write(f"- 财务状况: {real_summary['record_count']}条")
    else:
        st.sidebar.info("👆 请先上传数据文件")
    
    st.sidebar.markdown("---")
    # 数据预加载状态
    try:
        from data_preloader import render_preload_status
        st.sidebar.markdown("---")
        st.sidebar.markdown("### ⚡ 数据状态")
        render_preload_status()
    except Exception:
        pass
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 👤 用户")
    from auth_manager import logout, get_current_user_name, get_current_role, UserRole, can_view_all
    st.sidebar.write(f"当前用户: **{get_current_user_name()}**")
    st.sidebar.write(f"权限: **{'全部数据' if can_view_all() else '仅自己'}**")
    if st.sidebar.button("🚪 退出登录"):
        logout()
        st.rerun()
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🔐 访问控制")
    with st.sidebar.expander("财务状况密码", expanded=False):
        current_pwd_set = auth_guard.is_real_finance_protected()
        if current_pwd_set:
            st.caption("当前已设置访问密码")
        else:
            st.caption("当前未设置访问密码（任何人可查看）")
        
        new_pwd = st.text_input("新密码", type="password", key="set_real_pwd")
        confirm_pwd = st.text_input("确认密码", type="password", key="confirm_real_pwd")
        
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("保存", width='stretch', key="save_real_pwd_btn"):
                if new_pwd != confirm_pwd:
                    st.error("两次输入不一致")
                else:
                    auth_guard.set_real_finance_password(new_pwd)
                    if new_pwd:
                        st.success("财务状况分析密码已设置")
                    else:
                        st.success("密码已清除")
        with col_b:
            if st.button("清除密码", type="secondary", width='stretch', key="clear_real_pwd_btn"):
                auth_guard.set_real_finance_password("")
                auth_guard.logout_real_finance()
                st.success("密码已清除")
    
    # PDF 报告导出
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📄 报告导出")
    
    if analyzer.positions or analyzer.forecast_positions or analyzer.real_cost_records:
        if st.sidebar.button("📄 生成股东报告 PDF", type="secondary", use_container_width=True, key="export_pdf_btn"):
            with st.spinner("正在生成 PDF 报告..."):
                try:
                    from pdf_report import generate_shareholder_report
                    output_path = generate_shareholder_report(analyzer)
                    with open(output_path, "rb") as f:
                        pdf_bytes = f.read()
                    st.sidebar.success(f"✅ 报告已生成")
                    st.sidebar.download_button(
                        label="⬇️ 下载 PDF",
                        data=pdf_bytes,
                        file_name=os.path.basename(output_path),
                        mime="application/pdf",
                        use_container_width=True,
                        key="download_pdf_btn"
                    )
                except Exception as e:
                    st.sidebar.error(f"生成失败: {str(e)[:80]}")
    else:
        st.sidebar.caption("上传数据后可生成 PDF 报告")


def render_dashboard():
    """渲染现金流安全分析页面"""
    st.markdown('<div class="main-header">💰 现金流安全分析</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">90天/180天现金流预测与风险预警</div>', unsafe_allow_html=True)
    
    analyzer = st.session_state.analyzer
    
    if not analyzer.positions:
        st.info("📊 请先在侧边栏上传成单数据")
        return
    
    # 设置当前实际现金余额（已回款可能已消耗，请根据实际余额调整）
    cash_reserve = analyzer.config.get('cash_reserve', 1800000)
    current_balance = st.sidebar.number_input(
        "当前现金余额 (元)",
        value=int(cash_reserve),
        step=100000,
        help="已回款可能已消耗，请填入当前实际现金余额（如180万）",
        key="home_current_balance"
    )
    
    # 获取分析结果
    safety = analyzer.get_cash_safety_analysis(current_balance=current_balance)
    
    # 顶部指标
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("当前现金余额", format_currency(safety['current_balance']))
    with col2:
        st.metric("已回款(本年)", format_currency(safety['collected_revenue']))
    with col3:
        st.metric("月度成本", format_currency(safety['monthly_cost']))
    with col4:
        st.metric("90天预测余额", format_currency(safety['balance_90d']))
    with col5:
        st.metric("90天回款", format_currency(safety['future_90d_collected']))
    
    st.markdown("---")
    
    # 90天/180天余额卡片
    col1, col2 = st.columns(2)
    
    with col1:
        color_90d = safety['color_90d']
        # 财务恒等式展示
        formula_90d = f"""
        <div style="background: #f8f9fa; border-radius: 12px; padding: 15px; margin-top: 15px; font-size: 0.85rem; color: #666;">
            <div style="font-weight: bold; margin-bottom: 8px;">💰 财务恒等式（90天）</div>
            <div>期初余额: {format_currency(safety['current_balance'])}</div>
            <div style="color: #10B981;">+ 90天回款: {format_currency(safety['future_90d_collected'])}</div>
            <div style="color: #10B981;">+ Forecast: {format_currency(safety['forecast_90d'])}</div>
            <div style="color: #EF4444;">- 3个月成本: {format_currency(safety['monthly_cost'] * 3)}</div>
            <div style="border-top: 1px solid #ddd; margin-top: 8px; padding-top: 8px; font-weight: bold; color: #333;">
                = 期末余额: {format_currency(safety['balance_90d'])}
            </div>
        </div>
        """
        st.markdown(f"""
        <div style="background: {color_90d}; border-radius: 16px; padding: 30px; color: white; text-align: center;">
            <div style="font-size: 3rem; font-weight: bold;">{format_currency(safety['balance_90d'])}</div>
            <div style="font-size: 1.2rem; margin-top: 10px;">90天预测余额 ({safety['status_90d']})</div>
        </div>
        {formula_90d}
        """, unsafe_allow_html=True)
    
    with col2:
        color_180d = safety['color_180d']
        # 财务恒等式展示
        formula_180d = f"""
        <div style="background: #f8f9fa; border-radius: 12px; padding: 15px; margin-top: 15px; font-size: 0.85rem; color: #666;">
            <div style="font-weight: bold; margin-bottom: 8px;">💰 财务恒等式（180天）</div>
            <div>期初余额: {format_currency(safety['current_balance'])}</div>
            <div style="color: #10B981;">+ 180天回款: {format_currency(safety['future_180d_collected'])}</div>
            <div style="color: #10B981;">+ Forecast: {format_currency(safety['forecast_180d'])}</div>
            <div style="color: #F59E0B;">+ 已逾期: {format_currency(safety.get('overdue_collected', 0))}</div>
            <div style="color: #EF4444;">- 6个月成本: {format_currency(safety['monthly_cost'] * 6)}</div>
            <div style="border-top: 1px solid #ddd; margin-top: 8px; padding-top: 8px; font-weight: bold; color: #333;">
                = 期末余额: {format_currency(safety['balance_180d'])}
            </div>
        </div>
        """
        st.markdown(f"""
        <div style="background: {color_180d}; border-radius: 16px; padding: 30px; color: white; text-align: center;">
            <div style="font-size: 3rem; font-weight: bold;">{format_currency(safety['balance_180d'])}</div>
            <div style="font-size: 1.2rem; margin-top: 10px;">180天预测余额 ({safety['status_180d']})</div>
        </div>
        {formula_180d}
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # 结论
    runway = safety['runway_months']
    st.markdown("### 📋 分析结论")
    
    # 红线 = 5个月储备金
    if runway >= 5:
        st.success(f"**现金储备可覆盖约 {runway:.1f} 个月成本。** 高于5个月红线，现金流状况良好。")
    elif runway >= 3:
        st.warning(f"**现金储备可覆盖约 {runway:.1f} 个月成本。** 低于5个月红线，建议关注回款进度。")
    else:
        st.error(f"**现金储备仅能覆盖约 {runway:.1f} 个月成本。** 远低于5个月红线，建议立即催收并控制支出。")


def format_consultant_details(details: dict):
    """渲染顾问核算明细（拆分：实际回款 | Offer待回 | Forecast）"""
    st.markdown(f"**📅 核算周期：** {details['period']}")
    
    # 成本明细
    cost = details['cost_details']
    st.markdown("##### 💰 成本计算")
    col1, col2, col3 = st.columns(3)
    col1.metric("月薪", f"{cost['monthly_salary']:,.0f}")
    col2.metric("成本倍数", f"×{cost['salary_multiplier']}")
    col3.metric("Q1累计成本", f"{cost['period_cost']:,.0f}")
    st.caption(f"计算公式：{cost['calculation']}")
    
    # 核心指标卡片
    st.markdown("##### 📊 核心指标")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("回款利润", f"{details['actual_profit']:,.0f}", f"利润率 {details['actual_margin']}")
    with c2:
        st.metric("Offer业绩余粮", f"{details['offer_reserve_months']:.1f}个月")
    with c3:
        coverage = details['forecast_coverage'] * 100
        st.metric("Forecast覆盖", f"{coverage:.0f}%", help="(累计Offer未回款+未来3个月Forecast) / 6个月成本")
    
    # ========== 实际回款明细 ==========
    st.markdown(f"##### ✅ 实际已回款明细 ({details['actual_collection_count']}笔)")
    if details['actual_collection_details']:
        df_actual = pd.DataFrame(details['actual_collection_details'])
        df_actual.columns = ['职位ID', '客户', '职位名称', '回款金额', '回款日期', '剩余天数', '状态']
        df_actual['回款金额'] = df_actual['回款金额'].apply(lambda x: f"{x:,.0f}")
        st.dataframe(df_actual, width='stretch', hide_index=True)
        st.success(f"**累计实际回款：{details['actual_collection']:,.0f}元，利润：{details['actual_profit']:,.0f}元，利润率：{details['actual_margin']}**")
    else:
        st.warning("暂无实际回款记录")
    
    # ========== Offer待回明细 ==========
    st.markdown(f"##### 📝 Offer未回款明细 ({details['offer_pending_count']}笔)")
    if details['offer_pending_details']:
        df_offer = pd.DataFrame(details['offer_pending_details'])
        df_offer.columns = ['职位ID', '客户', '职位名称', '预期金额', '预计回款日', '剩余天数', '状态']
        df_offer['预期金额'] = df_offer['预期金额'].apply(lambda x: f"{x:,.0f}")
        st.dataframe(df_offer, width='stretch', hide_index=True)
        st.info(f"**累计Offer未回款：{details['offer_pending']:,.0f}元，相当于 {details['offer_reserve_months']:.1f} 个月业绩余粮**")
    else:
        st.info("暂无Offer待回款记录")
    
    # ========== Forecast明细 ==========
    st.markdown(f"##### 📋 90天Forecast明细 ({details['forecast_count']}笔)")
    if details['forecast_details']:
        df_fore = pd.DataFrame(details['forecast_details'])
        df_fore.columns = ['Forecast ID', '客户', '职位', '预估费用', '成功率', '加权收入', '预期回款日', '剩余天数', '阶段']
        df_fore['预估费用'] = df_fore['预估费用'].apply(lambda x: f"{x:,.0f}")
        df_fore['加权收入'] = df_fore['加权收入'].apply(lambda x: f"{x:,.0f}")
        df_fore['成功率'] = df_fore['成功率'].apply(lambda x: f"{x*100:.0f}%")
        st.dataframe(df_fore, width='stretch', hide_index=True)
        st.info(f"**未来3个月Forecast：{details['total_forecast']:,.0f}元，(Offer未回款+Forecast)覆盖未来6个月成本（{details['future_6m_cost']:,.0f}元）的 {details['forecast_coverage']*100:.0f}%**")
    else:
        st.info("暂无未来3个月内Forecast回款")
    
    # ========== 汇总对比 ==========
    st.markdown("---")
    st.markdown("##### 📊 盈亏汇总对比")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("实际回款利润", f"{details['actual_profit']:,.0f}", 
                 f"利润率 {details['actual_margin']}")
    with col2:
        st.metric("Offer业绩余粮", f"{details['offer_reserve_months']:.1f}个月",
                 help="累计Offer未回款 / 月成本，反映中期业绩缓冲")
    with col3:
        coverage = details['forecast_coverage'] * 100
        st.metric("Forecast覆盖", f"{coverage:.0f}%",
                 help=f"(累计Offer未回款+未来3个月Forecast) / 6个月成本 = {details['future_6m_cost']:,.0f}元")
    
    # 计算过程
    st.markdown("##### 🧮 详细计算过程")
    for line in details['calculation_process']:
        st.markdown(f"- {line}")


def render_consultant_profit():
    """渲染顾问盈亏分析页面"""
    st.markdown('<div class="main-header">📊 顾问盈亏分析</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">顾问实时盈亏分析（成本基数：年初至今实际在岗月数×月薪×3）</div>', unsafe_allow_html=True)
    
    analyzer = st.session_state.analyzer
    
    if not analyzer.positions and not analyzer.forecast_positions:
        st.info("📊 请上传成单数据或Forecast数据")
        return
    
    forecast_df = analyzer.get_consultant_profit_forecast(forecast_days=90)
    
    if forecast_df.empty:
        st.warning("暂无足够数据生成分析")
        return
    
    # ========== 汇总指标（KPI 卡片样式）==========
    st.markdown('<div class="section-title"><span class="icon">💰</span>核心指标汇总</div>', unsafe_allow_html=True)
    
    actual_90d = forecast_df['已回款'].sum()
    total_profit = forecast_df['回款利润'].sum()
    # 平均Offer余粮只计算在职人员，避免已离职/未配置人员的0值拉低平均值
    active_df = forecast_df[forecast_df['状态码'] == 2]
    avg_reserve = active_df['Offer余粮(月)'].mean() if len(active_df) > 0 else 0
    # Pipeline不足人数只统计在职顾问
    low_coverage = (active_df['Forecast覆盖数值'] < 0.5).sum() if len(active_df) > 0 else 0
    
    profit_color = 'positive' if total_profit > 0 else 'danger'
    reserve_color = 'positive' if avg_reserve >= 6 else ('warning' if avg_reserve >= 3 else 'danger')
    
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f'''
        <div class="kpi-card">
            <div class="kpi-label">已回款</div>
            <div class="kpi-value">{format_currency(actual_90d)}</div>
            <div class="kpi-delta" style="color:#059669;">✓ 实际到账</div>
        </div>
        ''', unsafe_allow_html=True)
    with c2:
        st.markdown(f'''
        <div class="kpi-card">
            <div class="kpi-label">回款总利润</div>
            <div class="kpi-value {profit_color}">{format_currency(total_profit)}</div>
            <div class="kpi-delta" style="color:{'#059669' if total_profit>0 else '#dc2626'};">
                {'▲ 盈利' if total_profit>0 else '▼ 亏损'}
            </div>
        </div>
        ''', unsafe_allow_html=True)
    with c3:
        st.markdown(f'''
        <div class="kpi-card">
            <div class="kpi-label">平均Offer余粮</div>
            <div class="kpi-value {reserve_color}">{avg_reserve:.1f}<span style="font-size:1rem">个月</span></div>
            <div class="kpi-delta" style="color:{'#059669' if avg_reserve>=6 else ('#d97706' if avg_reserve>=3 else '#dc2626')};">
                {'✓ 充足' if avg_reserve>=6 else ('⚠ 警戒' if avg_reserve>=3 else '❌ 危险')}
            </div>
        </div>
        ''', unsafe_allow_html=True)
    with c4:
        st.markdown(f'''
        <div class="kpi-card">
            <div class="kpi-label">Pipeline不足人数</div>
            <div class="kpi-value {'warning' if low_coverage>0 else 'positive'}">{low_coverage}<span style="font-size:1rem">人</span></div>
            <div class="kpi-delta" style="color:{'#d97706' if low_coverage>0 else '#059669'};">
                {'需关注' if low_coverage>0 else '全部健康'}
            </div>
        </div>
        ''', unsafe_allow_html=True)
    
    st.markdown('<div class="section-title"><span class="icon">📊</span>累计资源储备</div>', unsafe_allow_html=True)
    
    actual_total = forecast_df['累计实际回款'].sum()
    offer_total = forecast_df['累计Offer待回'].sum()
    forecast_total = forecast_df['累计Forecast'].sum()
    total_pipeline = actual_total + offer_total + forecast_total
    
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f'''
        <div class="kpi-card">
            <div class="kpi-label">累计实际回款</div>
            <div class="kpi-value positive">{format_currency(actual_total)}</div>
        </div>
        ''', unsafe_allow_html=True)
    with c2:
        st.markdown(f'''
        <div class="kpi-card">
            <div class="kpi-label">累计Offer待回</div>
            <div class="kpi-value">{format_currency(offer_total)}</div>
        </div>
        ''', unsafe_allow_html=True)
    with c3:
        st.markdown(f'''
        <div class="kpi-card">
            <div class="kpi-label">累计Forecast</div>
            <div class="kpi-value info" style="color:#2563eb;">{format_currency(forecast_total)}</div>
        </div>
        ''', unsafe_allow_html=True)
    with c4:
        st.markdown(f'''
        <div class="kpi-card" style="background: linear-gradient(135deg, #1a365d 0%, #2c5282 100%);">
            <div class="kpi-label" style="color:#a0aec0;">Pipeline 总计</div>
            <div class="kpi-value" style="color:#ffffff;">{format_currency(total_pipeline)}</div>
            <div class="kpi-delta" style="color:#90cdf4;">全部可预期收入</div>
        </div>
        ''', unsafe_allow_html=True)
    
    st.markdown("---")
    
    # ========== 顾问明细表格 ==========
    st.markdown("#### 📋 顾问明细")
    
    # 创建简化版展示表格
    # 状态列已经在 models.py 中生成：在职 / 已离职 / 未配置
    # 已离职/未配置人员的风险评级已设为空
    
    display_cols = [
        '顾问', '状态',
        '已回款', '累计成本', '回款利润', '回款利润率',
        '90天Offer待回', 'Offer余粮(月)',
        '未来6个月成本', 'Forecast覆盖率',
        '风险评级'
    ]
    
    # 确保只包含存在的列
    display_cols = [c for c in display_cols if c in forecast_df.columns]
    display_df = forecast_df[display_cols].copy()
    
    # 格式化金额列
    currency_cols = ['已回款', '累计成本', '回款利润', '90天Offer待回', '未来6个月成本']
    for col in currency_cols:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(format_currency)
    
    st.dataframe(
        display_df,
        width='stretch',
        hide_index=True,
        use_container_width=True
    )
    
    # ========== 可视化对比 ==========
    st.markdown("---")
    st.markdown("#### 📈 顾问收入构成对比")
    
    # 选择要对比的顾问
    selected_consultants = st.multiselect(
        "选择顾问进行对比（最多选择5人）",
        options=forecast_df['顾问'].tolist(),
        default=forecast_df.head(3)['顾问'].tolist(),
        max_selections=5,
        key="consultant_compare_select"
    )
    
    if selected_consultants:
        compare_df = forecast_df[forecast_df['顾问'].isin(selected_consultants)]
        
        # 堆叠柱状图：实际回款 vs Offer待回 vs Forecast
        fig = go.Figure()
        
        fig.add_trace(go.Bar(
            name='实际回款',
            x=compare_df['顾问'],
            y=compare_df['已回款'],
            marker_color='#10B981'
        ))
        fig.add_trace(go.Bar(
            name='Offer待回',
            x=compare_df['顾问'],
            y=compare_df['90天Offer待回'],
            marker_color='#3B82F6'
        ))
        fig.add_trace(go.Bar(
            name='Forecast',
            x=compare_df['顾问'],
            y=compare_df['90天Forecast'],
            marker_color='#F59E0B'
        ))
        
        fig.update_layout(
            title='顾问收入构成对比（实际回款 | Offer待回 | Forecast）',
            barmode='stack',
            xaxis_title='顾问',
            yaxis_title='金额（元）',
            template='plotly_white',
            height=400,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        st.plotly_chart(fig, width='stretch')
        
        # 利润能力 vs 业绩余粮 vs Pipeline覆盖（拆分为三个独立小图，更清晰）
        def parse_margin(margin_str):
            if margin_str == '-' or pd.isna(margin_str):
                return None
            try:
                return float(margin_str.replace('%', ''))
            except:
                return None
        
        compare_df_plot = compare_df.copy()
        compare_df_plot['回款利润率数值'] = compare_df_plot['回款利润率'].apply(parse_margin)
        
        st.markdown("##### 📊 顾问盈利能力与资源储备分析")
        c1, c2, c3 = st.columns(3)
        
        # 小图1：回款利润率
        with c1:
            fig_margin = go.Figure()
            fig_margin.add_trace(go.Bar(
                x=compare_df_plot['顾问'],
                y=compare_df_plot['回款利润率数值'],
                marker_color='#10B981',
                text=compare_df_plot['回款利润率数值'].apply(lambda x: f"{x:.0f}%" if pd.notna(x) else '-'),
                textposition='outside'
            ))
            fig_margin.add_hline(y=20, line_dash="dash", line_color="red",
                                annotation_text="目标20%", annotation_position="right")
            fig_margin.update_layout(
                title=dict(text='回款利润率', font=dict(size=14)),
                xaxis_title='',
                yaxis_title='利润率(%)',
                template='plotly_white',
                height=320,
                margin=dict(t=40, b=40),
                showlegend=False
            )
            st.plotly_chart(fig_margin, width='stretch', key=f"margin_{selected_consultants}")
        
        # 小图2：Offer余粮
        with c2:
            fig_reserve = go.Figure()
            fig_reserve.add_trace(go.Bar(
                x=compare_df_plot['顾问'],
                y=compare_df_plot['Offer余粮(月)'],
                marker_color='#3B82F6',
                text=compare_df_plot['Offer余粮(月)'].apply(lambda x: f"{x:.1f}月"),
                textposition='outside'
            ))
            fig_reserve.add_hline(y=3, line_dash="dash", line_color="red",
                                 annotation_text="安全线3月", annotation_position="right")
            fig_reserve.update_layout(
                title=dict(text='Offer业绩余粮', font=dict(size=14)),
                xaxis_title='',
                yaxis_title='余粮月数',
                template='plotly_white',
                height=320,
                margin=dict(t=40, b=40),
                showlegend=False
            )
            st.plotly_chart(fig_reserve, width='stretch', key=f"reserve_{selected_consultants}")
        
        # 小图3：Forecast覆盖率
        with c3:
            fig_cover = go.Figure()
            cover_vals = compare_df_plot['Forecast覆盖数值'] * 100
            fig_cover.add_trace(go.Bar(
                x=compare_df_plot['顾问'],
                y=cover_vals,
                marker_color='#F59E0B',
                text=cover_vals.apply(lambda x: f"{x:.0f}%"),
                textposition='outside'
            ))
            fig_cover.add_hline(y=50, line_dash="dash", line_color="red",
                               annotation_text="目标50%", annotation_position="right")
            fig_cover.update_layout(
                title=dict(text='Forecast覆盖未来6个月成本', font=dict(size=14)),
                xaxis_title='',
                yaxis_title='覆盖率(%)',
                template='plotly_white',
                height=320,
                margin=dict(t=40, b=40),
                showlegend=False
            )
            st.plotly_chart(fig_cover, width='stretch', key=f"cover_{selected_consultants}")
    
    # 核算明细展开
    st.markdown("---")
    st.markdown("#### 🔍 顾问核算明细（点击展开查看详细核算过程）")
    
    consultants = forecast_df['顾问'].tolist()
    if consultants:
        selected_consultant = st.selectbox(
            "选择顾问查看核算明细",
            options=consultants,
            key="consultant_detail_select"
        )
        
        if selected_consultant:
            with st.expander(f"📊 {selected_consultant} 的Q1盈亏与资源储备明细", expanded=True):
                details = analyzer.get_consultant_profit_details(selected_consultant, forecast_days=90)
                format_consultant_details(details)
    
    # 风险分布
    st.markdown("---")
    st.markdown("#### 📊 风险评级分布")
    
    risk_counts = forecast_df['风险评级'].value_counts()
    
    col1, col2, col3 = st.columns(3)
    with col1:
        healthy = sum(1 for r in risk_counts.index if '🟢' in str(r))
        st.metric("健康", healthy)
    with col2:
        warning = sum(1 for r in risk_counts.index if '🟡' in str(r))
        st.metric("低利润", warning)
    with col3:
        danger = sum(1 for r in risk_counts.index if '🔴' in str(r))
        st.metric("亏损风险", danger)


def render_consultant_performance():
    """渲染顾问绩效-行为关联分析页面"""
    st.markdown('<div class="main-header">🎯 顾问绩效行为分析</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">基于Pipeline数据深入分析顾问行为与业绩的关系</div>', unsafe_allow_html=True)
    
    analyzer = st.session_state.analyzer
    
    # 尝试从数据库加载行为数据
    perf_df = None
    funnel_df = None
    pipeline_df = None
    
    try:
        from gllue_db_client import GllueDBClient
        import db_config_manager
        if db_config_manager.has_config():
            db_client = GllueDBClient(db_config_manager.get_gllue_db_config())
            from consultant_performance import ConsultantPerformanceAnalyzer
            perf_analyzer = ConsultantPerformanceAnalyzer(db_client)
            perf_analyzer.load_from_db('2026-01-01')
            funnel_df = perf_analyzer.get_funnel_analysis()
            pipeline_df = perf_analyzer.get_pipeline_health()
    except Exception as e:
        st.error(f"加载Pipeline数据失败: {str(e)[:100]}")
    
    if funnel_df is None or funnel_df.empty:
        st.info("📊 请确保已连接数据库并同步数据")
        return
    
    # ========== 核心指标 ==========
    st.markdown('<div class="section-title"><span class="icon">📊</span>核心行为指标</div>', unsafe_allow_html=True)
    
    total_subs = funnel_df['推荐数'].sum()
    total_ints = funnel_df['面试数'].sum()
    total_offers = funnel_df['Offer数'].sum()
    total_onboards = funnel_df['入职数'].sum()
    
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f'''
        <div class="kpi-card">
            <div class="kpi-label">总推荐数</div>
            <div class="kpi-value">{total_subs:,}</div>
            <div class="kpi-delta" style="color:#2563eb;">本年度累计</div>
        </div>
        ''', unsafe_allow_html=True)
    with c2:
        st.markdown(f'''
        <div class="kpi-card">
            <div class="kpi-label">总面试数</div>
            <div class="kpi-value">{total_ints:,}</div>
            <div class="kpi-delta" style="color:#2563eb;">转化率 {total_ints/total_subs*100:.1f}%</div>
        </div>
        ''', unsafe_allow_html=True)
    with c3:
        st.markdown(f'''
        <div class="kpi-card">
            <div class="kpi-label">总Offer数</div>
            <div class="kpi-value">{total_offers}</div>
            <div class="kpi-delta" style="color:#2563eb;">转化率 {total_offers/total_subs*100:.1f}%</div>
        </div>
        ''', unsafe_allow_html=True)
    with c4:
        st.markdown(f'''
        <div class="kpi-card">
            <div class="kpi-label">总入职数</div>
            <div class="kpi-value">{total_onboards}</div>
            <div class="kpi-delta" style="color:#2563eb;">转化率 {total_onboards/total_subs*100:.1f}%</div>
        </div>
        ''', unsafe_allow_html=True)
    
    # ========== 漏斗转化分析 ==========
    st.markdown('<div class="section-title"><span class="icon">🔽</span>顾问漏斗转化率</div>', unsafe_allow_html=True)
    
    # 筛选
    min_subs = st.slider("最少推荐数", min_value=5, max_value=100, value=10, key="perf_min_subs")
    filtered = funnel_df[funnel_df['推荐数'] >= min_subs].copy()
    
    if not filtered.empty:
        # 展示表格
        display_cols = ['顾问', '推荐数', '面试数', '有面试推荐', 'Offer数', '入职数',
                       '推荐到面试率', '面试到Offer率', '推荐到Offer率']
        st.dataframe(filtered[display_cols], width='stretch', hide_index=True, use_container_width=True)
        
        # 可视化：推荐量 vs 转化率
        st.markdown('<div class="section-title"><span class="icon">📈</span>推荐量与转化率散点图</div>', unsafe_allow_html=True)
        
        import plotly.express as px
        fig = px.scatter(
            filtered,
            x='推荐数',
            y='推荐到Offer率',
            size='Offer数',
            color='面试到Offer率',
            hover_name='顾问',
            color_continuous_scale='RdYlGn',
            title='顾问推荐量 vs 成单转化率（气泡大小=Offer数，颜色=面试到Offer率）',
            labels={'推荐数': '推荐数', '推荐到Offer率': '推荐到Offer率(%)', '面试到Offer率': '面试到Offer率(%)'}
        )
        fig.update_layout(template='plotly_white', height=450)
        st.plotly_chart(fig, use_container_width=True)
    
    # ========== Pipeline健康度 ==========
    if pipeline_df is not None and not pipeline_df.empty:
        st.markdown('<div class="section-title"><span class="icon">🌿</span>Pipeline健康度</span></div>', unsafe_allow_html=True)
        
        # 按加权收入排序
        pipeline_sorted = pipeline_df.sort_values('加权Pipeline收入', ascending=False)
        
        c1, c2 = st.columns(2)
        with c1:
            st.dataframe(pipeline_sorted[['顾问', 'Pipeline总数', '阶段6-Offer', '阶段7-入职', '加权Pipeline收入', '平均成功率']], 
                        width='stretch', hide_index=True, use_container_width=True)
        
        with c2:
            # Pipeline阶段分布堆叠柱状图
            stage_cols = ['阶段1-简历', '阶段2-1面', '阶段3-2面', '阶段4-3面', '阶段5-终面', '阶段6-Offer', '阶段7-入职']
            available_stages = [c for c in stage_cols if c in pipeline_sorted.columns]
            
            if available_stages:
                fig = go.Figure()
                colors = ['#E2E8F0', '#CBD5E1', '#94A3B8', '#64748B', '#475569', '#2563EB', '#059669']
                for i, col in enumerate(available_stages):
                    fig.add_trace(go.Bar(
                        name=col.replace('阶段', ''),
                        x=pipeline_sorted['顾问'].head(15),
                        y=pipeline_sorted[col].head(15),
                        marker_color=colors[i % len(colors)]
                    ))
                fig.update_layout(
                    title='顾问Pipeline阶段分布（Top 15）',
                    barmode='stack',
                    xaxis_title='',
                    yaxis_title='数量',
                    template='plotly_white',
                    height=400,
                    legend=dict(orientation='h', yanchor='bottom', y=1.02)
                )
                st.plotly_chart(fig, use_container_width=True)
    
    # ========== 行为画像 ==========
    st.markdown('<div class="section-title"><span class="icon">👤</span>顾问行为画像</div>', unsafe_allow_html=True)
    
    try:
        from consultant_performance import ConsultantPerformanceAnalyzer
        if db_config_manager.has_config():
            db_client = GllueDBClient(db_config_manager.get_gllue_db_config())
            perf_analyzer = ConsultantPerformanceAnalyzer(db_client)
            perf_analyzer.load_from_db('2026-01-01')
            profile_df = perf_analyzer.get_behavior_profile(min_submissions=min_subs)
            
            if not profile_df.empty:
                for profile_type in profile_df['行为画像'].unique():
                    with st.expander(f"{profile_type} ({len(profile_df[profile_df['行为画像']==profile_type])}人)"):
                        st.dataframe(profile_df[profile_df['行为画像']==profile_type].drop('行为画像', axis=1), 
                                    width='stretch', hide_index=True, use_container_width=True)
    except Exception:
        pass


def render_consultant_project_analysis():
    """渲染顾问项目新增分析页面"""
    st.markdown('<div class="main-header">📋 项目新增分析</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">从项目新增情况判断客户维护情况和顾问工作饱和度</div>', unsafe_allow_html=True)
    
    # 时间范围选择
    col1, col2 = st.columns([1, 3])
    with col1:
        period_options = {'90天': 90, '180天': 180, '365天': 365}
        period_label = st.selectbox('统计周期', list(period_options.keys()), index=1)
        period_days = period_options[period_label]
    
    # 加载数据
    try:
        from gllue_db_client import GllueDBClient
        import db_config_manager
        from consultant_project_analysis import ConsultantProjectAnalyzer
        
        if db_config_manager.has_config():
            db_client = GllueDBClient(db_config_manager.get_gllue_db_config())
            proj_analyzer = ConsultantProjectAnalyzer(db_client)
            proj_analyzer.load_from_db()
            
            consultant_df = proj_analyzer.get_consultant_project_stats(period_days=period_days)
            team_df = proj_analyzer.get_team_project_stats(period_days=period_days)
            monthly_trend = proj_analyzer.get_monthly_trend(months=12)
        else:
            st.warning("请先配置数据库连接")
            return
    except Exception as e:
        st.error(f"加载项目数据失败: {str(e)[:100]}")
        return
    
    if consultant_df.empty:
        st.info("暂无项目数据")
        return
    
    # ========== KPI 卡片 ==========
    total_jobs = consultant_df['新增项目数'].sum()
    live_jobs = consultant_df['活跃项目数'].sum()
    total_clients = consultant_df['客户数'].sum()
    avg_monthly = consultant_df['月均新增'].mean()
    avg_saturation = consultant_df['工作饱和度'].mean()
    total_hist_revenue = consultant_df['历史Offer金额'].sum()
    total_forecast = consultant_df['Forecast金额'].sum()
    
    st.markdown('<div class="section-title"><span class="icon">📊</span>核心指标汇总</div>', unsafe_allow_html=True)
    
    c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
    with c1:
        st.metric("新增项目总数", f"{total_jobs}个")
    with c2:
        st.metric("活跃项目数", f"{live_jobs}个")
    with c3:
        st.metric("覆盖客户数", f"{total_clients}家")
    with c4:
        st.metric("人均月新增", f"{avg_monthly:.1f}个")
    with c5:
        st.metric("历史Offer金额", f"¥{total_hist_revenue/10000:.0f}万")
    with c6:
        st.metric("Forecast金额", f"¥{total_forecast/10000:.0f}万")
    with c7:
        ratio = (total_forecast / total_hist_revenue * 100) if total_hist_revenue > 0 else 0
        st.metric("Pipeline/历史比", f"{ratio:.0f}%")
    
    st.markdown("---")
    
    # ========== 评分计算说明 ==========
    with st.expander("📖 饱和度与维护度评分计算说明", expanded=False):
        st.markdown("""
        **工作饱和度（0-100分）= 项目数(25) + 活跃率(20) + 客户覆盖(20) + 项目金额(25) + 额外(10)**
        
        | 维度 | 权重 | 评分标准 |
        |------|------|---------|
        | 月均项目数 | 25分 | ≥8个→25; ≥5→20; ≥3→15; ≥1→10; <1→月数×5 |
        | 活跃项目占比 | 20分 | ≥70%→20; ≥50%→15; ≥30%→10; <30%→比例×0.25 |
        | 客户覆盖度 | 20分 | ≥12家→20; ≥8→16; ≥5→12; ≥2→6; <2→家数×2 |
        | 月均Offer金额 | 25分 | ≥15万→25; ≥8万→20; ≥4万→15; ≥2万→10; <2万→金额÷2000 |
        
        **客户维护度（0-100分）= 复购率(50) + 新客户(50)**
        
        | 维度 | 权重 | 评分标准 |
        |------|------|---------|
        | 客户复购率 | 50分 | ≥50%→50; ≥30%→40; ≥15%→30; ≥5%→15; <5%→比例×2 |
        | 新客户开发 | 50分 | ≥8家→50; ≥5→40; ≥3→30; ≥1→家数×8 |
        
        **Pipeline/历史比**：当前Forecast金额 ÷ 近1年历史Offer金额，>100%说明Pipeline比历史产出更充裕
        """)
    
    st.markdown("---")
    
    # ========== 视图切换 ==========
    view_tab1, view_tab2, view_tab3, view_tab4 = st.tabs(["👤 按顾问查看", "💰 历史vsPipeline", "🏢 按团队查看", "📈 月度趋势"])
    
    # ---------- 按顾问 ----------
    with view_tab1:
        st.markdown('<div class="section-title"><span class="icon">👤</span>顾问项目新增明细</div>', unsafe_allow_html=True)
        
        # 饱和度分布
        sat_col1, sat_col2, sat_col3 = st.columns(3)
        with sat_col1:
            high_sat = len(consultant_df[consultant_df['工作饱和度'] >= 70])
            st.metric("高饱和顾问", f"{high_sat}人", help="饱和度≥70")
        with sat_col2:
            mid_sat = len(consultant_df[(consultant_df['工作饱和度'] >= 40) & (consultant_df['工作饱和度'] < 70)])
            st.metric("中等饱和", f"{mid_sat}人", help="饱和度40-70")
        with sat_col3:
            low_sat = len(consultant_df[consultant_df['工作饱和度'] < 40])
            st.metric("低饱和顾问", f"{low_sat}人", help="饱和度<40")
        
        st.markdown("---")
        
        # 详细表格（含原始数据）
        display_cols = ['顾问', '团队', '新增项目数', '活跃项目数', '已关闭项目数', 
                        '项目活跃率', '客户数', '新客户数', '客户复购率',
                        '月均新增', '历史Offer金额', '月均Offer金额', 'Forecast金额',
                        'Pipeline/历史比', '工作饱和度', '客户维护度']
        
        # 添加饱和度颜色标记
        def color_saturation(val):
            if val >= 70:
                return 'background-color: #d1fae5; color: #065f46'
            elif val >= 40:
                return 'background-color: #fef3c7; color: #92400e'
            else:
                return 'background-color: #fee2e2; color: #991b1b'
        
        styled_df = consultant_df[display_cols].style.map(
            color_saturation, subset=['工作饱和度']
        ).map(
            lambda x: 'background-color: #dbeafe; color: #1e40af' if x >= 50 else '',
            subset=['客户维护度']
        ).map(
            lambda x: 'color: #dc2626; font-weight: bold' if isinstance(x, (int, float)) and x < 0.5 else ('color: #059669; font-weight: bold' if isinstance(x, (int, float)) and x >= 1.0 else ''),
            subset=['Pipeline/历史比']
        )
        
        st.dataframe(styled_df, width='stretch', hide_index=True, use_container_width=True)
        
        # 评分明细展开
        st.markdown("#### 📋 评分明细（点击顾问查看计算过程）")
        for _, row in consultant_df.iterrows():
            sat_d = row['_sat_detail']
            maint_d = row['_maint_detail']
            with st.expander(f"{row['顾问'].split(' ')[0]} — 饱和度{row['工作饱和度']}分 / 维护度{row['客户维护度']}分"):
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown(f"**工作饱和度 breakdown：**")
                    st.markdown(f"- 项目数得分：{sat_d['项目数得分']}/25（月均{row['月均新增']}个）")
                    st.markdown(f"- 活跃率得分：{sat_d['活跃率得分']}/20（活跃率{row['项目活跃率']}%）")
                    st.markdown(f"- 客户覆盖得分：{sat_d['客户覆盖得分']}/20（{row['客户数']}家客户）")
                    st.markdown(f"- 项目金额得分：{sat_d['项目金额得分']}/25（月均¥{row['月均Offer金额']:,.0f}）")
                with c2:
                    st.markdown(f"**客户维护度 breakdown：**")
                    st.markdown(f"- 复购率得分：{maint_d['复购率得分']}/50（复购率{row['客户复购率']}%）")
                    st.markdown(f"- 新客户得分：{maint_d['新客户得分']}/50（新客户{row['新客户数']}家）")
        
        # 工作饱和度 vs 客户维护度 散点图
        try:
            fig = go.Figure()
            
            for _, row in consultant_df.iterrows():
                color = '#10b981' if row['工作饱和度'] >= 70 else ('#f59e0b' if row['工作饱和度'] >= 40 else '#ef4444')
                fig.add_trace(go.Scatter(
                    x=[row['工作饱和度']],
                    y=[row['客户维护度']],
                    mode='markers+text',
                    text=[row['顾问'].split(' ')[0]],
                    textposition='top center',
                    marker=dict(size=15 + row['新增项目数'] * 0.3, color=color, opacity=0.7),
                    name=row['顾问'],
                    showlegend=False
                ))
            
            fig.add_hline(y=50, line_dash="dash", line_color="#9ca3af", annotation_text="维护度基准")
            fig.add_vline(x=70, line_dash="dash", line_color="#9ca3af", annotation_text="饱和度基准")
            
            fig.update_layout(
                title="顾问工作饱和度 vs 客户维护度（气泡大小=项目数）",
                xaxis_title="工作饱和度",
                yaxis_title="客户维护度",
                height=500,
                plot_bgcolor='rgba(0,0,0,0)',
            )
            st.plotly_chart(fig, use_container_width=True)
        except Exception:
            pass
    
    # ---------- 历史 vs Pipeline ----------
    with view_tab2:
        st.markdown('<div class="section-title"><span class="icon">💰</span>历史产出 vs 当前Pipeline</div>', unsafe_allow_html=True)
        
        try:
            # 数据准备
            compare_df = consultant_df[['顾问', '历史Offer金额', 'Forecast金额', 'Pipeline/历史比']].copy()
            compare_df = compare_df.sort_values('历史Offer金额', ascending=True)
            
            fig = go.Figure()
            
            # 历史金额柱状图
            fig.add_trace(go.Bar(
                y=[c.split(' ')[0] for c in compare_df['顾问']],
                x=compare_df['历史Offer金额'] / 10000,
                name='历史Offer金额（近1年）',
                orientation='h',
                marker_color='#3b82f6',
                text=[f"¥{v/10000:.0f}万" for v in compare_df['历史Offer金额']],
                textposition='inside'
            ))
            
            # Forecast金额柱状图
            fig.add_trace(go.Bar(
                y=[c.split(' ')[0] for c in compare_df['顾问']],
                x=compare_df['Forecast金额'] / 10000,
                name='当前Forecast金额',
                orientation='h',
                marker_color='#10b981',
                text=[f"¥{v/10000:.0f}万" for v in compare_df['Forecast金额']],
                textposition='inside'
            ))
            
            fig.update_layout(
                title="顾问历史产出 vs 当前Pipeline对比（万元）",
                barmode='group',
                height=500,
                plot_bgcolor='rgba(0,0,0,0)',
                xaxis_title="金额（万元）",
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Pipeline/历史比 表格
            st.markdown("#### 📊 Pipeline充盈度排名")
            ratio_df = consultant_df[['顾问', '历史Offer金额', 'Forecast金额', 'Pipeline/历史比', '工作饱和度']].copy()
            ratio_df = ratio_df.sort_values('Pipeline/历史比', ascending=False)
            
            def color_ratio(val):
                if isinstance(val, str):
                    return ''
                if val >= 1.0:
                    return 'background-color: #d1fae5; color: #065f46'
                elif val >= 0.5:
                    return 'background-color: #fef3c7; color: #92400e'
                else:
                    return 'background-color: #fee2e2; color: #991b1b'
            
            styled_ratio = ratio_df.style.map(color_ratio, subset=['Pipeline/历史比'])
            st.dataframe(styled_ratio, width='stretch', hide_index=True, use_container_width=True)
            
            st.info("""
            **解读：** Pipeline/历史比 > 100% 表示当前在途项目预期金额超过近1年历史产出，
            顾问处于"升温"状态；< 50% 表示Pipeline不足，顾问工作状态可能趋于"降温"。
            """)
            
        except Exception as e:
            st.error(f"生成对比图失败: {e}")
    
    # ---------- 按团队 ----------
    with view_tab3:
        st.markdown('<div class="section-title"><span class="icon">🏢</span>团队项目新增统计</div>', unsafe_allow_html=True)
        
        if not team_df.empty:
            st.dataframe(team_df, width='stretch', hide_index=True, use_container_width=True)
            
            # 团队对比柱状图
            try:
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=team_df['团队'],
                    y=team_df['新增项目数'],
                    name='新增项目数',
                    marker_color='#3b82f6'
                ))
                fig.add_trace(go.Bar(
                    x=team_df['团队'],
                    y=team_df['活跃项目数'],
                    name='活跃项目数',
                    marker_color='#10b981'
                ))
                fig.update_layout(
                    title="团队项目新增对比",
                    barmode='group',
                    height=400,
                    plot_bgcolor='rgba(0,0,0,0)',
                )
                st.plotly_chart(fig, use_container_width=True)
            except Exception:
                pass
        else:
            st.info("暂无团队数据")
    
    # ---------- 月度趋势 ----------
    with view_tab4:
        st.markdown('<div class="section-title"><span class="icon">📈</span>月度项目新增趋势</div>', unsafe_allow_html=True)
        
        if not monthly_trend.empty:
            st.dataframe(monthly_trend, width='stretch', hide_index=True, use_container_width=True)
            
            try:
                # 排除合计列绘制趋势图
                chart_cols = [c for c in monthly_trend.columns if c != 'month' and c != '合计']
                fig = go.Figure()
                for col in chart_cols:
                    fig.add_trace(go.Scatter(
                        x=monthly_trend['month'],
                        y=monthly_trend[col],
                        mode='lines+markers',
                        name=col,
                        line=dict(width=2)
                    ))
                fig.update_layout(
                    title="各团队月度项目新增趋势",
                    xaxis_title="月份",
                    yaxis_title="项目数",
                    height=450,
                    plot_bgcolor='rgba(0,0,0,0)',
                    legend=dict(orientation="h", yanchor="bottom", y=1.02)
                )
                st.plotly_chart(fig, use_container_width=True)
            except Exception:
                pass
        else:
            st.info("暂无趋势数据")


def render_forecast_analysis():
    """渲染Forecast预测分析页面"""
    st.markdown('<div class="main-header">📈 Forecast预测分析</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">在途单的加权预期价值与回款预测</div>', unsafe_allow_html=True)
    
    analyzer = st.session_state.analyzer
    
    if not analyzer.forecast_positions:
        st.info("📊 请上传Forecast预测数据")
        return
    
    summary = analyzer.get_forecast_summary()
    
    # 汇总指标
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("在途单数", summary['total_forecasts'])
    with col2:
        st.metric("预计佣金总额", format_currency(summary['total_estimated_fee']))
    with col3:
        st.metric("加权预测收入", format_currency(summary['weighted_revenue']))
    with col4:
        st.metric("平均成功率", f"{summary['avg_success_rate']:.1f}%")
    
    st.markdown("---")
    
    # 回款日期推算说明
    avg_cycle = analyzer.get_historical_payment_cycle()
    offer_to_payment = analyzer.AVG_OFFER_TO_ONBOARD_DAYS + avg_cycle
    
    st.info(f"""
    **Forecast回款日期推算：** Offer时间 + {analyzer.AVG_OFFER_TO_ONBOARD_DAYS}天(入职) + {avg_cycle}天(账期) = {offer_to_payment}天
    """)
    
    # 明细表
    st.markdown("#### 📋 Forecast明细")
    
    forecast_df = analyzer.get_forecast_analysis()
    
    # 筛选
    col1, col2 = st.columns(2)
    with col1:
        consultants = forecast_df['顾问'].unique().tolist()
        filter_consultant = st.multiselect("筛选顾问", options=consultants)
    with col2:
        stages = forecast_df['阶段'].unique().tolist()
        filter_stage = st.multiselect("筛选阶段", options=stages)
    
    filtered_df = forecast_df.copy()
    if filter_consultant:
        filtered_df = filtered_df[filtered_df['顾问'].isin(filter_consultant)]
    if filter_stage:
        filtered_df = filtered_df[filtered_df['阶段'].isin(filter_stage)]
    
    st.dataframe(filtered_df, width='stretch', hide_index=True)


def render_cashflow_calendar():
    """渲染现金流日历页面"""
    st.markdown('<div class="main-header">📅 现金流日历</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">半月现金流预测与关键节点</div>', unsafe_allow_html=True)
    
    analyzer = st.session_state.analyzer
    
    if not analyzer.positions:
        st.info("📊 请上传成单数据")
        return
    
    # 计算参考数据
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    cash_reserve = analyzer.config.get('cash_reserve', 1800000)
    collected_revenue = sum(
        p.actual_payment for p in analyzer.positions
        if p.payment_date and p.payment_date.year == today.year and p.payment_date <= today
    )
    # 注：已回款可能已消耗，默认只使用现金储备作为初始余额
    default_balance = cash_reserve
    
    # 设置
    col1, col2 = st.columns(2)
    with col1:
        days = st.slider("预测天数", min_value=30, max_value=180, value=90)
    with col2:
        initial_balance = st.number_input(
            "初始现金余额", 
            value=int(default_balance),
            step=10000,
            help=f"现金储备: {cash_reserve:,.0f}元 | 本年已回款: {collected_revenue:,.0f}元（可能已消耗，请根据实际余额调整）"
        )
    
    # KPI 概览卡片
    st.markdown('<div class="section-title"><span class="icon">📊</span>现金流概览</div>', unsafe_allow_html=True)
    
    # 计算未来流入/流出
    biweekly_preview = analyzer.generate_biweekly_cashflow_calendar(periods=3, cash_reserve=initial_balance)
    total_inflow = biweekly_preview['确认流入'].sum() + biweekly_preview['预期流入'].sum() if '确认流入' in biweekly_preview.columns else 0
    total_outflow = biweekly_preview['确认流出'].sum() + biweekly_preview['预期流出'].sum() if '确认流出' in biweekly_preview.columns else 0
    ending_balance = biweekly_preview['累计余额'].iloc[-1] if '累计余额' in biweekly_preview.columns and len(biweekly_preview) > 0 else initial_balance
    
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f'''
        <div class="kpi-card">
            <div class="kpi-label">初始现金余额</div>
            <div class="kpi-value">{format_currency(initial_balance)}</div>
        </div>
        ''', unsafe_allow_html=True)
    with c2:
        st.markdown(f'''
        <div class="kpi-card">
            <div class="kpi-label">{days}天预计流入</div>
            <div class="kpi-value positive">{format_currency(total_inflow)}</div>
        </div>
        ''', unsafe_allow_html=True)
    with c3:
        st.markdown(f'''
        <div class="kpi-card">
            <div class="kpi-label">{days}天预计流出</div>
            <div class="kpi-value danger">{format_currency(total_outflow)}</div>
        </div>
        ''', unsafe_allow_html=True)
    with c4:
        balance_color = 'positive' if ending_balance > initial_balance * 0.5 else ('warning' if ending_balance > 0 else 'danger')
        st.markdown(f'''
        <div class="kpi-card" style="background: linear-gradient(135deg, #1a365d 0%, #2c5282 100%);">
            <div class="kpi-label" style="color:#a0aec0;">{days}天后预计余额</div>
            <div class="kpi-value" style="color:#ffffff;">{format_currency(ending_balance)}</div>
            <div class="kpi-delta" style="color:{'#6ee7b7' if ending_balance>initial_balance*0.5 else ('#fcd34d' if ending_balance>0 else '#fca5a5')};">
                {'✓ 安全' if ending_balance>initial_balance*0.5 else ('⚠ 关注' if ending_balance>0 else '❌ 缺口')}
            </div>
        </div>
        ''', unsafe_allow_html=True)
    
    st.markdown("---")
    
    # 说明逻辑
    st.info(f"💡 **现金流计算逻辑**：从初始余额 **{format_currency(initial_balance)}** 开始，未来回款按预计日期流入，成本按日流出")
    
    # 半月汇总表格
    periods = 6 if days <= 90 else 12
    st.markdown(f'<div class="section-title"><span class="icon">📅</span>未来{days}天现金流明细（按半月汇总）</div>', unsafe_allow_html=True)
    
    biweekly = analyzer.generate_biweekly_cashflow_calendar(periods=periods, cash_reserve=initial_balance)
    
    # 格式化显示
    for col in ['确认流入', '预期流入', '确认流出', '预期流出', 
                '净现金流(确认)', '净现金流(预期)', '累计余额']:
        if col in biweekly.columns:
            biweekly[col] = biweekly[col].apply(format_currency)
    
    st.dataframe(biweekly, width='stretch', hide_index=True)
    
    st.markdown("---")
    
    # 关键节点
    st.markdown("#### 📍 关键现金流节点")
    
    # 催收预警
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # 优先使用真实 invoice 数据（从analyzer或数据库获取）
    overdue_detail = None
    # 1. 先从 analyzer 获取（如果已同步）
    if hasattr(analyzer, 'overdue_invoices_detail') and analyzer.overdue_invoices_detail is not None:
        if not analyzer.overdue_invoices_detail.empty:
            overdue_detail = analyzer.overdue_invoices_detail.copy()
    
    # 2. 如果 analyzer 中没有，尝试从数据库获取（使用安全配置）
    if overdue_detail is None:
        import db_config_manager
        if db_config_manager.has_config():
            try:
                from gllue_db_client import GllueDBClient
                db_client = GllueDBClient(db_config_manager.get_gllue_db_config())
                overdue_detail = db_client.get_overdue_invoices_detail(cutoff_date=today)
            except Exception:
                overdue_detail = None
    
    if overdue_detail is not None and not overdue_detail.empty:
        # 使用真实 invoice 逾期数据
        total_overdue = overdue_detail['pending_amount'].sum()
        
        st.markdown(f'''
        <div class="alert-card danger">
            <div style="font-weight:600; font-size:1rem; margin-bottom:6px;">🚨 已逾期回款（基于真实发票数据）</div>
            <div style="font-size:1.4rem; font-weight:700; color:#dc2626;">
                {format_currency(total_overdue)}
                <span style="font-size:0.9rem; color:#7f1d1d; font-weight:500;">共 {len(overdue_detail)} 笔</span>
            </div>
        </div>
        ''', unsafe_allow_html=True)
        
        # 按客户分组展示（表格化）
        alert_df = overdue_detail[['client_name', 'job_title', 'consultants', 'pending_amount', 'contract_terms', 'status', 'overdue_days', 'hist_avg_days', 'hist_overdue_rate']].copy()
        alert_df['pending_amount_fmt'] = alert_df['pending_amount'].apply(format_currency)
        alert_df['contract_info'] = alert_df.apply(
            lambda r: '超35天未寄出' if r['status'] == 'Invoice Added' else f"合同账期:{r['contract_terms']}天", axis=1
        )
        alert_df['逾期'] = alert_df['overdue_days'].astype(str) + '天'
        alert_df['历史参考'] = alert_df.apply(
            lambda r: f"平均{r['hist_avg_days']}天 / 逾期率{r['hist_overdue_rate']}%" 
            if r['hist_avg_days'] != 'N/A' and r['hist_overdue_rate'] != 'N/A' else '无历史数据', axis=1
        )
        
        display_alert = alert_df[['client_name', 'job_title', 'consultants', 'pending_amount_fmt', 'contract_info', '逾期', '历史参考']].copy()
        display_alert.columns = ['客户', '项目', '负责人', '金额', '账期状态', '逾期', '历史参考']
        
        st.markdown('<div class="data-table">', unsafe_allow_html=True)
        st.dataframe(display_alert, width='stretch', hide_index=True, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        # Fallback：使用 positions 推算数据
        overdue = []
        due_7d = []
        
        for p in analyzer.positions:
            if not p.is_successful:
                continue
            if p.payment_status in ['已回款', '部分回款', '回款完成']:
                continue
            if not p.offer_date:
                continue
            
            expected_amount = p.actual_payment if p.actual_payment > 0 else p.fee_amount
            if expected_amount <= 0:
                continue
            
            payment_cycle = analyzer.get_position_payment_cycle(p)
            offer_to_payment_days = analyzer.AVG_OFFER_TO_ONBOARD_DAYS + payment_cycle
            est_date = p.offer_date + timedelta(days=offer_to_payment_days)
            days_until = (est_date - today).days
            
            item = {
                'client': p.client_name,
                'position': p.position_name,
                'consultant': p.consultant,
                'amount': expected_amount,
                'days': days_until
            }
            
            if days_until < 0:
                overdue.append(item)
            elif days_until <= 7:
                due_7d.append(item)
        
        if overdue:
            total_overdue = sum(i['amount'] for i in overdue)
            st.markdown(f'''
            <div class="alert-card danger">
                <div style="font-weight:600; font-size:1rem; margin-bottom:6px;">🚨 已逾期回款（基于Offer日期推算）</div>
                <div style="font-size:1.4rem; font-weight:700; color:#dc2626;">
                    {format_currency(total_overdue)}
                    <span style="font-size:0.9rem; color:#7f1d1d; font-weight:500;">共 {len(overdue)} 笔</span>
                </div>
            </div>
            ''', unsafe_allow_html=True)
            for item in overdue:
                st.write(f"- {item['client']} - {item['consultant']}: {format_currency(item['amount'])} (逾期{abs(item['days'])}天)")
        
        if due_7d:
            total_7d = sum(i['amount'] for i in due_7d)
            st.markdown(f'''
            <div class="alert-card warning">
                <div style="font-weight:600; font-size:1rem; margin-bottom:6px;">⚠️ 7天内到期</div>
                <div style="font-size:1.2rem; font-weight:700; color:#d97706;">
                    {format_currency(total_7d)}
                    <span style="font-size:0.9rem; color:#92400e; font-weight:500;">共 {len(due_7d)} 笔</span>
                </div>
            </div>
            ''', unsafe_allow_html=True)
        
        if not overdue and not due_7d:
            st.markdown('''
            <div class="alert-card success">
                <div style="font-weight:600; font-size:1rem;">✅ 暂无紧急催款事项</div>
                <div style="font-size:0.85rem; color:#059669; margin-top:4px;">所有回款均在正常账期内</div>
            </div>
            ''', unsafe_allow_html=True)


def render_whatif_simulator():
    """渲染情景模拟器 (What-if Analysis)"""
    st.markdown('<div class="main-header">🔮 情景模拟器</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">模拟经营决策对现金流的影响</div>', unsafe_allow_html=True)
    
    analyzer = st.session_state.analyzer
    
    if not analyzer.positions:
        st.info("📊 请上传成单数据以使用情景模拟功能")
        return
    
    # 获取基础数据
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    cash_reserve = analyzer.config.get('cash_reserve', 1800000)
    collected_revenue = sum(
        p.actual_payment for p in analyzer.positions
        if p.payment_date and p.payment_date.year == today.year and p.payment_date <= today
    )
    current_balance = cash_reserve
    
    # 显示当前基准
    st.markdown("#### 📊 当前基准")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("现金储备", format_currency(cash_reserve))
    with col2:
        st.metric("已回款(本年)", format_currency(collected_revenue))
    with col3:
        st.metric("当前现金余额", format_currency(current_balance))
    
    st.markdown("---")
    
    # 模拟1：人员变动
    st.markdown("#### 👥 模拟1：人员变动影响")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        headcount_change = st.number_input(
            "调整人数", min_value=-5, max_value=5, value=0,
            help="正数=招聘，负数=裁员"
        )
    with col2:
        headcount_salary = st.number_input(
            "人均月薪", min_value=5000, max_value=100000, value=20000, step=1000
        )
    with col3:
        headcount_effective = st.number_input(
            "生效天数", min_value=0, max_value=90, value=0,
            help="0=立即生效"
        )
    
    if headcount_change != 0:
        result = analyzer.simulate_headcount_change(
            headcount_change, headcount_salary, headcount_effective, forecast_days=180
        )
        
        impact_color = "#10B981" if result['adjusted_balance'] > result['base_balance'] else "#EF4444"
        
        st.markdown(f"""
        <div style="background: white; padding: 15px; border-radius: 8px; border-left: 4px solid {impact_color};">
            <strong>模拟结果：</strong>{'新增' if headcount_change > 0 else '减少'} {abs(headcount_change)} 人<br>
            月度成本变化: <strong>{format_currency(result['monthly_cost_change'])}/月</strong><br>
            180天总影响: <strong>{format_currency(result['total_cost_impact'])}</strong><br>
            调整后180天余额: <strong style="color: {impact_color};">{format_currency(result['adjusted_balance'])}</strong> 
            (原 {format_currency(result['base_balance'])})<br>
            建议: <strong>{result['recommendation']}</strong>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # 模拟2：账期调整
    st.markdown("#### ⏱️ 模拟2：客户账期调整")
    
    col1, col2 = st.columns(2)
    with col1:
        clients = list(set(p.client_name for p in analyzer.positions if p.client_name))
        selected_client = st.selectbox("选择客户", clients[:10] if clients else ["无数据"])
    with col2:
        new_cycle = st.slider("新账期天数", min_value=30, max_value=180, value=90)
    
    if selected_client != "无数据":
        result = analyzer.simulate_payment_cycle_change(selected_client, new_cycle)
        
        st.markdown(f"""
        <div style="background: white; padding: 15px; border-radius: 8px; border-left: 4px solid #3B82F6;">
            <strong>客户:</strong> {result['client_keyword']}<br>
            <strong>影响单数:</strong> {result['affected_count']} 笔<br>
            <strong>涉及金额:</strong> {format_currency(result['affected_amount'])}<br>
            <strong>账期调整:</strong> {result['old_cycle_days']}天 → {result['new_cycle_days']}天<br>
            <strong>影响:</strong> {result['impact_description']}<br>
            <strong>建议:</strong> {result['recommendation']}
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # 模拟3：回款加速
    st.markdown("#### 🚀 模拟3：催收加速效果")
    
    col1, col2 = st.columns(2)
    with col1:
        accel_rate = st.slider(
            "加速回款比例 (%)", min_value=0, max_value=100, value=30
        ) / 100
    with col2:
        days_ahead = st.slider("提前天数", min_value=15, max_value=90, value=30)
    
    result = analyzer.simulate_collection_acceleration(accel_rate, days_ahead)
    
    if result['overdue_count'] > 0:
        impact_color = "#10B981"
        st.markdown(f"""
        <div style="background: white; padding: 15px; border-radius: 8px; border-left: 4px solid {impact_color};">
            <strong>逾期款项:</strong> {result['overdue_count']} 笔，合计 {format_currency(result['overdue_total'])}<br>
            <strong>加速回收:</strong> {accel_rate*100:.0f}% = <strong>{format_currency(result['improved_amount'])}</strong><br>
            <strong>180天余额改善:</strong> {format_currency(result['base_balance'])} → <strong>{format_currency(result['new_balance'])}</strong><br>
            <strong>可覆盖成本:</strong> {result['monthly_cost_cover']:.1f} 个月<br>
            <strong>建议:</strong> {result['recommendation']}
        </div>
        """, unsafe_allow_html=True)
    else:
        st.success("✅ 暂无逾期款项，无需催收加速")


def load_default_data(analyzer):
    """自动加载默认数据文件（用于部署后无需上传即可查看）"""
    import os
    
    # 数据文件路径（相对于app.py）
    base_path = os.path.join(os.path.dirname(__file__), '..', 'data_templates', 'analysis_db')
    # 兼容旧的中文路径
    legacy_path = os.path.join(os.path.dirname(__file__), '..', 'data_templates', '分析数据库')
    if not os.path.exists(base_path) and os.path.exists(legacy_path):
        base_path = legacy_path
    
    deal_file = os.path.join(base_path, '成单数据模板03.xlsx')
    consultant_file = os.path.join(base_path, '顾问数据模板03.xlsx')
    forecast_file = os.path.join(base_path, 'forecastassignment_202604020626.xlsx')
    
    # 加载成单数据
    if os.path.exists(deal_file) and not analyzer.positions:
        try:
            df_deals = pd.read_excel(deal_file)
            analyzer.load_positions_from_dataframe(df_deals)
        except Exception as e:
            st.error(f"加载成单数据失败: {e}")
    
    # 加载顾问数据
    if os.path.exists(consultant_file) and not analyzer.consultant_configs:
        try:
            df_consultants = pd.read_excel(consultant_file)
            analyzer.consultant_configs = {}
            for idx, row in df_consultants.iterrows():
                name = row.get('name')
                if pd.notna(name):
                    analyzer.consultant_configs[name] = {
                        'monthly_salary': float(row['base_salary']) if pd.notna(row.get('base_salary')) else 20000,
                        'is_active': bool(row.get('is_active', True)),
                        'salary_multiplier': 3.0
                    }
        except Exception as e:
            st.error(f"加载顾问数据失败: {e}")
    
    # 加载Forecast数据
    if os.path.exists(forecast_file) and not analyzer.forecast_positions:
        try:
            df_forecast = pd.read_excel(forecast_file)
            analyzer.load_forecast_from_dataframe(df_forecast)
        except Exception as e:
            st.error(f"加载Forecast数据失败: {e}")

def main():
    """主函数"""
    # 初始化认证
    from auth_manager import init_auth, is_logged_in, render_login_page, render_user_banner, can_view_all
    init_auth()
    
    # 未登录时显示登录页
    if not is_logged_in():
        render_login_page()
        return
    
    # 初始化 analyzer
    if 'analyzer' not in st.session_state:
        st.session_state.analyzer = AdvancedRecruitmentAnalyzer()
        load_default_data(st.session_state.analyzer)
    
    # ========== 数据预加载（后台线程）==========
    # 如果数据库已配置，启动后台预加载，减少后续标签页切换等待时间
    try:
        import db_config_manager
        from data_preloader import init_preloader_in_session
        
        if db_config_manager.has_config():
            # 只在首次初始化时创建预加载器
            if 'data_preloader' not in st.session_state:
                from gllue_db_client import GllueDBClient
                db_cfg = db_config_manager.get_gllue_db_config()
                db_client = GllueDBClient(db_cfg)
                init_preloader_in_session(db_client)
    except Exception as e:
        # 预加载失败不影响主流程
        pass
    
    # 渲染用户横幅
    render_user_banner()
    
    # 渲染侧边栏
    render_sidebar()
    
    # 主内容区标签页（合并为7大板块）
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "💰 现金流与预警",
        "👤 顾问全景分析",
        "📈 Pipeline与预测",
        "🗺️ Mapping质量",
        "📋 财务深度分析",
        "🎯 OKR与绩效",
        "🔮 情景模拟",
    ])
    
    with tab1:
        render_dashboard()
        st.markdown("---")
        render_alert_system(st.session_state.analyzer)
    
    with tab2:
        render_consultant_full_analysis()
    
    with tab3:
        render_forecast_analysis()
        st.markdown("---")
        render_cashflow_calendar()
    
    with tab4:
        render_mapping_analysis()
    
    with tab5:
        render_real_finance_page(st.session_state.analyzer)
    
    with tab6:
        from pages.okr_page import render_okr_page
        render_okr_page()
    
    with tab7:
        render_whatif_simulator()


def render_mapping_analysis():
    """渲染 Mapping 组织架构图分析页面"""
    st.markdown('<div class="main-header">🗺️ Mapping 组织架构分析</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">组织架构图数据质量分析与整改建议</div>', unsafe_allow_html=True)
    
    try:
        from gllue_db_client import GllueDBClient
        import db_config_manager
        from mapping_analyzer import MappingAnalyzer
        from data_preloader import get_preloaded_data, is_data_ready
        
        if db_config_manager.has_config():
            db_client = GllueDBClient(db_config_manager.get_gllue_db_config())
            analyzer = MappingAnalyzer(db_client)
            
            # 优先使用预加载的 Mapping 数据
            if is_data_ready():
                preloaded_mappings = get_preloaded_data('mappings')
                if preloaded_mappings is not None and not preloaded_mappings.empty:
                    # 预加载的 mappings 数据需要解析 content 字段
                    # 直接调用 load_from_db() 会重新查询，这里我们需要复用预加载的原始数据
                    # 但 mapping_analyzer 需要解析 JSON content，所以还是需要执行 load_from_db
                    # 不过预加载的数据已经缓存了，实际查询会走缓存，不会重复SSH
                    pass
            analyzer.load_from_db()
        else:
            st.warning("请先配置数据库连接")
            return
    except Exception as e:
        st.error(f"加载 Mapping 数据失败: {str(e)[:100]}")
        return
    
    summary = analyzer.get_summary()
    if not summary:
        st.info("暂无 Mapping 数据")
        return
    
    # ========== KPI 卡片 ==========
    st.markdown('<div class="section-title"><span class="icon">📊</span>核心指标</div>', unsafe_allow_html=True)
    
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Mapping总数", f"{summary['total_orgs']}张")
    with c2:
        st.metric("总节点数", f"{summary['total_nodes']}个")
    with c3:
        st.metric("人名节点占比", f"{summary['person_ratio']}%")
    with c4:
        st.metric("平均质量分", f"{summary['avg_quality_score']}")
    with c5:
        st.metric("需整改", f"{summary['need_fix']}张", delta_color="inverse")
    
    st.markdown("---")
    
    # ========== 视图切换 ==========
    m_tab1, m_tab2, m_tab3, m_tab4 = st.tabs(["📋 Mapping清单", "👤 录入人排名", "📊 节点分布", "⚠️ 待整改"])
    
    # ---------- Mapping 清单 ----------
    with m_tab1:
        st.markdown('<div class="section-title"><span class="icon">📋</span>Mapping 质量清单</div>', unsafe_allow_html=True)
        
        org_df = analyzer.get_org_stats()
        if not org_df.empty:
            display_cols = ['org_name', 'client_name', 'creator', 'total_nodes', 'person_nodes',
                           'low_quality_nodes', 'desc_nodes', 'quality_score', 'recommendation']
            
            def color_quality(val):
                if val >= 80:
                    return 'background-color: #d1fae5; color: #065f46'
                elif val >= 60:
                    return 'background-color: #fef3c7; color: #92400e'
                else:
                    return 'background-color: #fee2e2; color: #991b1b'
            
            styled = org_df[display_cols].style.map(color_quality, subset=['quality_score'])
            st.dataframe(styled, width='stretch', hide_index=True, use_container_width=True)
        else:
            st.info("暂无数据")
    
    # ---------- 录入人排名 ----------
    with m_tab2:
        st.markdown('<div class="section-title"><span class="icon">👤</span>录入人质量排名</div>', unsafe_allow_html=True)
        
        creator_df = analyzer.get_creator_ranking()
        if not creator_df.empty:
            st.dataframe(creator_df, width='stretch', hide_index=True, use_container_width=True)
            
            # 柱状图：录入人 Mapping 数量 vs 平均分
            try:
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=creator_df['录入人'].apply(lambda x: x.split(' ')[0] if ' ' in str(x) else str(x)),
                    y=creator_df['Mapping数量'],
                    name='Mapping数量',
                    marker_color='#3b82f6'
                ))
                fig.add_trace(go.Scatter(
                    x=creator_df['录入人'].apply(lambda x: x.split(' ')[0] if ' ' in str(x) else str(x)),
                    y=creator_df['平均质量分'],
                    name='平均质量分',
                    mode='lines+markers',
                    marker=dict(size=10, color='#ef4444'),
                    yaxis='y2'
                ))
                fig.update_layout(
                    title="录入人 Mapping 数量 vs 平均质量分",
                    yaxis=dict(title="Mapping数量"),
                    yaxis2=dict(title="质量分", overlaying='y', side='right'),
                    height=450,
                    plot_bgcolor='rgba(0,0,0,0)',
                )
                st.plotly_chart(fig, use_container_width=True)
            except Exception:
                pass
        else:
            st.info("暂无数据")
    
    # ---------- 节点分布 ----------
    with m_tab3:
        st.markdown('<div class="section-title"><span class="icon">📊</span>节点类型分布</div>', unsafe_allow_html=True)
        
        cat_df = analyzer.get_category_distribution()
        if not cat_df.empty:
            c1, c2 = st.columns([1, 2])
            with c1:
                st.dataframe(cat_df, width='stretch', hide_index=True, use_container_width=True)
            with c2:
                try:
                    colors = ['#10b981' if '人名' in str(c) else '#f59e0b' if '低质' not in str(c) else '#ef4444' for c in cat_df['节点类型']]
                    fig = go.Figure(data=[go.Pie(
                        labels=cat_df['节点类型'],
                        values=cat_df['数量'],
                        hole=0.4,
                        marker_colors=colors
                    )])
                    fig.update_layout(title="节点类型占比", height=450)
                    st.plotly_chart(fig, use_container_width=True)
                except Exception:
                    pass
        else:
            st.info("暂无数据")
    
    # ---------- 待整改 ----------
    with m_tab4:
        st.markdown('<div class="section-title"><span class="icon">⚠️</span>待整改 Mapping 清单</div>', unsafe_allow_html=True)
        
        lowq_df = analyzer.get_low_quality_list()
        if not lowq_df.empty:
            st.markdown(f"共 **{len(lowq_df)}** 张 Mapping 质量分低于 60，需要整改：")
            
            for _, row in lowq_df.iterrows():
                with st.expander(f"{row['org_name']} ({row['client_name']}) — 质量分 {row['quality_score']} | 录入人: {row['creator']}"):
                    st.markdown(f"**总节点**: {row['total_nodes']} | **人名节点**: {row['person_nodes']} | **低质节点**: {row['low_quality_nodes']} | **描述节点**: {row['desc_nodes']}")
                    st.markdown(f"**整改建议**: {row['recommendation']}")
                    
                    # 显示该 Mapping 的节点明细
                    nodes_detail = analyzer.get_nodes_by_org(row['org_id'])
                    if not nodes_detail.empty:
                        problem_nodes = nodes_detail[nodes_detail['category'].str.startswith('低质数据') | (nodes_detail['category'] == '描述性文字')]
                        if not problem_nodes.empty:
                            st.markdown("**问题节点:**")
                            st.dataframe(problem_nodes[['text', 'note', 'category', 'reason']], width='stretch', hide_index=True)
        else:
            st.success("✅ 所有 Mapping 数据质量良好，暂无待整改项！")


def render_consultant_full_analysis():
    """顾问全景分析 - 合并盈亏、绩效、项目、产能差距"""
    st.markdown('<div class="main-header">👤 顾问全景分析</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">盈亏、产能、行为与改进建议一站式查看</div>', unsafe_allow_html=True)
    
    # 优先使用预加载的数据
    try:
        from data_preloader import get_preloaded_data, is_data_ready
        from unified_data_loader import UnifiedDataLoader
        from consultant_gap_analyzer import ConsultantGapAnalyzer
        from gllue_db_client import GllueDBClient
        import db_config_manager
        
        if db_config_manager.has_config():
            # 检查是否有预加载的数据
            if is_data_ready():
                # 使用预加载的数据，避免重复查询
                users_df = get_preloaded_data('users')
                if users_df is None:
                    users_df = pd.DataFrame()
                # 创建 loader 但不执行 load_all()，直接注入预加载的数据
                db_client = GllueDBClient(db_config_manager.get_gllue_db_config())
                loader = UnifiedDataLoader(db_client)
                # 手动注入预加载的数据到 loader
                for key in ['users', 'teams', 'joborders', 'cvsents', 'interviews', 
                           'offers', 'invoices', 'forecasts', 'mappings']:
                    data = get_preloaded_data(key)
                    if data is not None:
                        loader._data[key] = data
                loader._loaded = True
            else:
                # 回退：直接加载
                db_client = GllueDBClient(db_config_manager.get_gllue_db_config())
                loader = UnifiedDataLoader(db_client)
                loader.load_all()
                users_df = loader.get('users')
            
            # 加载顾问数据库信息（用于准确的状态和成本计算）
            if not loader.get('users').empty:
                st.session_state.analyzer.load_consultant_db_info(loader.get('users'))
            
            # 产能差距分析
            gap_analyzer = ConsultantGapAnalyzer(loader)
            gap_df = gap_analyzer.analyze()
            benchmark = gap_analyzer.get_team_benchmark()
        else:
            gap_df = pd.DataFrame()
            benchmark = {}
    except Exception as e:
        import traceback
        st.error(f"数据加载失败: {e}")
        with st.expander("查看详细错误"):
            st.code(traceback.format_exc())
        gap_df = pd.DataFrame()
        benchmark = {}
    
    # ========== 团队基准 ==========
    if benchmark:
        st.markdown('<div class="section-title"><span class="icon">📊</span>团队基准（人均）</div>', unsafe_allow_html=True)
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        with c1:
            st.metric("推荐数", f"{benchmark.get('avg_cv', 0):.0f}")
        with c2:
            st.metric("面试数", f"{benchmark.get('avg_interview', 0):.0f}")
        with c3:
            st.metric("Offer数", f"{benchmark.get('avg_offer', 0):.1f}")
        with c4:
            st.metric("已回款", f"¥{benchmark.get('avg_invoice', 0)/10000:.1f}万")
        with c5:
            st.metric("推荐→面试", f"{benchmark.get('avg_cv_to_int', 0):.1f}%")
        with c6:
            st.metric("面试→Offer", f"{benchmark.get('avg_int_to_offer', 0):.1f}%")
        
        st.markdown("---")
    
    # ========== 顾问产能差距排名 ==========
    if not gap_df.empty:
        st.markdown('<div class="section-title"><span class="icon">🔍</span>顾问产能差距分析</div>', unsafe_allow_html=True)
        
        # 筛选
        filter_col1, filter_col2 = st.columns(2)
        with filter_col1:
            show_only_issues = st.checkbox("只显示有差距的顾问", value=False)
        with filter_col2:
            sort_by = st.selectbox("排序", ["优先级", "已回款", "推荐数", "面试→Offer率"])
        
        display_df = gap_df.copy()
        if show_only_issues:
            display_df = display_df[display_df['优先级'] < 3]
        
        if sort_by == "优先级":
            display_df = display_df.sort_values('优先级')
        elif sort_by == "已回款":
            display_df = display_df.sort_values('已回款', ascending=False)
        elif sort_by == "推荐数":
            display_df = display_df.sort_values('推荐数', ascending=False)
        elif sort_by == "面试→Offer率":
            display_df = display_df.sort_values('面试→Offer率', ascending=False)
        
        # 颜色标记
        def color_rating(val):
            if '🔴' in str(val):
                return 'background-color: #fee2e2; color: #991b1b; font-weight: bold'
            elif '🟡' in str(val):
                return 'background-color: #fef3c7; color: #92400e'
            else:
                return 'background-color: #d1fae5; color: #065f46'
        
        styled = display_df[['顾问', '综合评级', '推荐数', '面试数', 'Offer数', '已回款', 
                              '推荐→面试率', '面试→Offer率', '差距数量', '主攻方向', '改进建议']].style.map(
            color_rating, subset=['综合评级']
        )
        
        st.dataframe(styled, width='stretch', hide_index=True, use_container_width=True)
        
        # 详细改进建议展开
        st.markdown("#### 📋 详细改进建议")
        st.caption("💡 数据口径：推荐/面试/Offer/已回款均为近1年数据 | 增减基准=团队均值")
        for _, row in display_df.iterrows():
            if row['差距数量'] > 0:
                with st.expander(f"{row['顾问']} — {row['综合评级']} | 主攻: {row['主攻方向']}"):
                    st.markdown(f"**全部建议：**")
                    st.markdown(row['全部建议'])
                    
                    # 与团队均值对比
                    st.markdown("**与团队均值对比：**")
                    st.caption(f"团队均值: 推荐={benchmark.get('avg_cv', 0):.0f} | 面试={benchmark.get('avg_interview', 0):.0f} | Offer={benchmark.get('avg_offer', 0):.1f} | 已回款=¥{benchmark.get('avg_invoice', 0)/10000:.1f}万")
                    c1, c2, c3, c4 = st.columns(4)
                    with c1:
                        diff_cv = row['推荐数'] - benchmark.get('avg_cv', 0)
                        st.metric("推荐数", f"{row['推荐数']}", f"{diff_cv:+.0f}")
                    with c2:
                        diff_int = row['面试数'] - benchmark.get('avg_interview', 0)
                        st.metric("面试数", f"{row['面试数']}", f"{diff_int:+.0f}")
                    with c3:
                        diff_offer = row['Offer数'] - benchmark.get('avg_offer', 0)
                        st.metric("Offer数", f"{row['Offer数']}", f"{diff_offer:+.1f}")
                    with c4:
                        diff_inv = (row['已回款'] - benchmark.get('avg_invoice', 0)) / 10000
                        st.metric("已回款", f"¥{row['已回款']/10000:.1f}万", f"{diff_inv:+.1f}万")
    
    st.markdown("---")
    
    # ========== 原有的盈亏分析 ==========
    st.markdown('<div class="section-title"><span class="icon">💰</span>顾问盈亏明细</div>', unsafe_allow_html=True)
    render_consultant_profit()
    
    st.markdown("---")
    
    # ========== 原有的绩效行为 ==========
    st.markdown('<div class="section-title"><span class="icon">🎯</span>顾问绩效漏斗</div>', unsafe_allow_html=True)
    render_consultant_performance()
    
    st.markdown("---")
    
    # ========== 原有的项目新增 ==========
    st.markdown('<div class="section-title"><span class="icon">📋</span>项目新增与饱和度</div>', unsafe_allow_html=True)
    render_consultant_project_analysis()


if __name__ == "__main__":
    main()
