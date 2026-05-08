"""
预警系统页面模块
"""

import math
import streamlit as st
from alert_config import get_alert_config, AlertSender


def format_currency(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "¥0"
    if abs(value) >= 10000:
        return f"¥{value/10000:.1f}万"
    return f"¥{value:,.0f}"


def render_alert_system(analyzer):
    """渲染智能预警系统"""
    st.markdown('<div class="main-header">🔔 智能预警系统</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">自动监控经营风险，及时推送预警通知</div>', unsafe_allow_html=True)
    
    if not analyzer.positions:
        st.info("📊 请上传成单数据以启用预警系统")
        return
    
    # 设置当前实际现金余额（从session_state获取首页设置的值）
    cash_reserve = analyzer.config.get('cash_reserve', 1800000)
    # 优先使用首页设置的值，否则使用默认值
    default_balance = st.session_state.get('home_current_balance', cash_reserve)
    current_balance = st.number_input(
        "当前现金余额 (元)",
        value=int(default_balance),
        step=100000,
        help="已回款可能已消耗，请填入当前实际现金余额（如180万）",
        key="alert_current_balance"
    )
    
    # 获取所有预警
    all_alerts = analyzer.get_all_alerts(current_balance=current_balance)
    summary = analyzer.get_alert_summary(current_balance=current_balance)
    
    # 统计卡片
    st.markdown("#### 📊 预警统计")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("🔴 紧急", summary['danger'])
    with col2:
        st.metric("🟡 警告", summary['warning'])
    with col3:
        st.metric("🔵 提示", summary['info'])
    with col4:
        st.metric("总计", summary['total'])
    
    st.markdown("---")
    
    # 预警详情
    tabs = st.tabs(["现金流预警", "回款催收", "顾问绩效", "邮件配置"])
    
    with tabs[0]:
        cashflow_alerts = all_alerts['cashflow']
        if cashflow_alerts:
            for alert in cashflow_alerts:
                color = "#ef4444" if alert['level'] == 'danger' else "#f59e0b"
                st.markdown(f"""
                <div style="background: white; border-left: 4px solid {color}; 
                            padding: 15px; margin: 10px 0; border-radius: 8px;">
                    <strong style="color: {color};">{alert['title']}</strong>
                    <p>{alert['message']}</p>
                    <p style="color: #6b7280; font-size: 0.9rem;">
                        💡 {alert['action']} | 👤 {alert['responsible']} | 📅 {alert['due_date']}
                    </p>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.success("✅ 现金流状况良好，暂无预警")
    
    with tabs[1]:
        # 优先使用真实 invoice 逾期数据（从analyzer或数据库获取）
        overdue_detail = None
        # 1. 先从 analyzer 获取（如果已同步）
        if hasattr(analyzer, 'overdue_invoices_detail') and analyzer.overdue_invoices_detail is not None:
            if not analyzer.overdue_invoices_detail.empty:
                overdue_detail = analyzer.overdue_invoices_detail.copy()
        
        # 2. 如果 analyzer 中没有，尝试从数据库获取
        if overdue_detail is None and st.session_state.get('db_host'):
            try:
                import sys
                sys.path.insert(0, r'C:\Users\EDY\recruiter_finance_tool\advanced_analysis')
                from gllue_db_client import GllueDBConfig, GllueDBClient
                kwargs = dict(
                    db_type="mysql",
                    host=st.session_state.get('db_host', '127.0.0.1'),
                    port=st.session_state.get('db_port', 3306),
                    database=st.session_state.get('db_name', 'gllue'),
                    username=st.session_state.get('db_user', ''),
                    password=st.session_state.get('db_pass', ''),
                )
                if st.session_state.get('db_use_ssh', False):
                    kwargs.update(
                        use_ssh=True,
                        ssh_host=st.session_state.get('db_ssh_host', ''),
                        ssh_port=st.session_state.get('db_ssh_port', 9998),
                        ssh_user=st.session_state.get('db_ssh_user', 'root'),
                        ssh_password=st.session_state.get('db_ssh_pass', ''),
                    )
                db_config = GllueDBConfig(**kwargs)
                db_client = GllueDBClient(db_config)
                from datetime import datetime
                overdue_detail = db_client.get_overdue_invoices_detail(cutoff_date=datetime.now())
            except Exception:
                overdue_detail = None
        
        if overdue_detail is not None and not overdue_detail.empty:
            # 使用真实 invoice 逾期数据
            total_overdue = overdue_detail['pending_amount'].sum()
            max_overdue_days = overdue_detail['overdue_days'].max()
            
            st.markdown(f"**🚨 已逾期回款 {len(overdue_detail)} 笔**")
            st.error(f"合计 {format_currency(total_overdue)}，最长逾期 {max_overdue_days} 天")
            st.write("**建议:** 立即电话催收，必要时发律师函")
            st.write("**负责人:** 对应顾问 + 财务")
            st.write("**涉及职位:**")
            
            for _, row in overdue_detail.iterrows():
                hist_info = ""
                if row['hist_avg_days'] != 'N/A' and row['hist_overdue_rate'] != 'N/A':
                    hist_info = f" | 历史平均账期:{row['hist_avg_days']}天 逾期率:{row['hist_overdue_rate']}%"
                
                contract_info = f"合同账期:{row['contract_terms']}天"
                if row['status'] == 'Invoice Added':
                    contract_info = "超35天未寄出"
                
                st.write(
                    f"- **{row['client_name']}** - {row['job_title']} | "
                    f"负责人:{row['consultants']} | "
                    f"{format_currency(row['pending_amount'])} | "
                    f"{contract_info} | "
                    f"逾期{row['overdue_days']}天"
                    f"{hist_info}"
                )
        else:
            # Fallback：使用 positions 推算数据
            collection_alerts = all_alerts['collection']
            if collection_alerts:
                for alert in collection_alerts:
                    with st.expander(f"{alert['level_text']} {alert['title']}"):
                        st.write(f"**详情:** {alert['message']}")
                        st.write(f"**建议:** {alert['action']}")
                        st.write(f"**负责人:** {alert['responsible']}")
                        
                        if 'items' in alert and alert['items']:
                            st.write("**涉及职位:**")
                            for item in alert['items']:
                                days_text = f"逾期{abs(item['days'])}天" if item['days'] < 0 else f"{item['days']}天后"
                                st.write(f"- {item['client']} - {item['consultant']}: "
                                       f"{format_currency(item['amount'])} ({days_text})")
            else:
                st.success("✅ 回款正常，暂无催收预警")
    
    with tabs[2]:
        consultant_alerts = all_alerts['consultant']
        if consultant_alerts:
            for alert in consultant_alerts:
                color = "#ef4444" if alert['level'] == 'danger' else "#f59e0b" if alert['level'] == 'warning' else "#3b82f6"
                st.markdown(f"""
                <div style="background: white; border-left: 4px solid {color}; 
                            padding: 15px; margin: 10px 0; border-radius: 8px;">
                    <strong style="color: {color};">{alert['title']}</strong>
                    <p>{alert['message']}</p>
                    <p style="color: #6b7280; font-size: 0.9rem;">
                        {alert['action']} | 负责人: {alert['responsible']}
                    </p>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.success("✅ 顾问绩效正常，暂无预警")
    
    with tabs[3]:
        alert_config = get_alert_config()
        render_notify_config(alert_config)


def render_notify_config(alert_config):
    st.markdown("#### 通知配置")
    
    # 主通知渠道
    channel_options = {
        'wechat': '企业微信 Webhook（推荐）',
        'email': '邮件 SMTP',
        'none': '不发送通知',
    }
    current_channel = alert_config.config.get('notify_channel', 'wechat')
    selected_channel = st.radio(
        "选择通知渠道",
        options=list(channel_options.keys()),
        format_func=lambda x: channel_options[x],
        index=list(channel_options.keys()).index(current_channel) if current_channel in channel_options else 0,
    )
    
    # Webhook 配置（企业微信）
    if selected_channel == 'wechat':
        st.info("💡 配置步骤：在企业微信群 → 群设置 → 添加群机器人 → 复制 Webhook 地址")
        webhook_url = st.text_input(
            "企业微信机器人 Webhook 地址",
            value=alert_config.config.get('webhook_url', ''),
            help="格式类似：https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxxx"
        )
    else:
        webhook_url = alert_config.config.get('webhook_url', '')
    
    if st.button("保存通知配置", type="primary"):
        update = {
            'notify_channel': selected_channel,
        }
        if selected_channel == 'wechat':
            update['webhook_url'] = webhook_url
        alert_config.update_config(update)
        st.success("通知配置已保存")
    
    if st.button("测试推送"):
        sender = AlertSender(alert_config)
        # 先保存当前选择再测试
        alert_config.update_config({
            'notify_channel': selected_channel,
            'webhook_url': webhook_url if selected_channel == 'wechat' else alert_config.config.get('webhook_url', '')
        })
        success, msg = sender.test_connection()
        st.success(msg) if success else st.error(msg)
    
    st.markdown("---")
    with st.expander("📧 邮件配置（作为备用渠道）"):
        email_enabled = st.checkbox("启用邮件 fallback", value=alert_config.config.get('email_enabled', False))
        server = st.text_input("SMTP服务器", alert_config.config.get('smtp_server', ''))
        port = st.number_input("端口", value=alert_config.config.get('smtp_port', 465))
        username = st.text_input("邮箱账号", alert_config.config.get('smtp_username', ''))
        password = st.text_input("密码", value=alert_config.config.get('smtp_password', ''), type="password")
        recipients = st.text_area(
            "收件人列表（每行一个邮箱）",
            value="\n".join(alert_config.config.get('recipients', []))
        )
        if st.button("保存邮件配置"):
            alert_config.update_config({
                'email_enabled': email_enabled,
                'smtp_server': server,
                'smtp_port': port,
                'smtp_username': username,
                'smtp_password': password,
                'recipients': [r.strip() for r in recipients.split('\n') if r.strip()],
            })
            st.success("邮件配置已保存")
