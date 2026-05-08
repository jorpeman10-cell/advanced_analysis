"""Insert database direct connect section into app.py"""

with open(r"C:\Users\EDY\recruiter_finance_tool\advanced_analysis\app.py", "r", encoding="utf-8") as f:
    content = f.read()

# Find the insertion point: before "基础配置"
insert_marker = '    st.sidebar.markdown("---")\n    st.sidebar.markdown("### ⚙️ 基础配置")'

new_section = '''    # 数据库直连配置
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🗄️ 数据库直连（推荐）")
    
    with st.sidebar.expander("配置 Gllue 数据库", expanded=False):
        st.info("直接连接 Gllue MySQL 数据库，绕过 API 限制获取完整业绩数据。")
        
        use_ssh = st.checkbox(
            "通过 SSH 隧道连接",
            value=st.session_state.get('db_use_ssh', False),
            help="如果数据库在内网，需要通过 SSH 跳转"
        )
        
        if use_ssh:
            ssh_host = st.text_input(
                "SSH 服务器地址",
                value=st.session_state.get('db_ssh_host', '118.190.96.172'),
                help="ECS 公网 IP"
            )
            ssh_port = st.number_input(
                "SSH 端口",
                value=st.session_state.get('db_ssh_port', 9998),
                min_value=1, max_value=65535
            )
            ssh_user = st.text_input(
                "SSH 用户名",
                value=st.session_state.get('db_ssh_user', 'root')
            )
            ssh_pass = st.text_input(
                "SSH 密码",
                value=st.session_state.get('db_ssh_pass', ''),
                type="password"
            )
        
        db_host = st.text_input(
            "数据库 Host",
            value=st.session_state.get('db_host', '127.0.0.1'),
            help="通常是 127.0.0.1（如果通过 SSH 隧道）"
        )
        db_port = st.number_input(
            "数据库端口",
            value=st.session_state.get('db_port', 3306),
            min_value=1, max_value=65535
        )
        db_name = st.text_input(
            "数据库名",
            value=st.session_state.get('db_name', 'gllue')
        )
        db_user = st.text_input(
            "数据库用户名",
            value=st.session_state.get('db_user', 'debian-sys-maint')
        )
        db_pass = st.text_input(
            "数据库密码",
            value=st.session_state.get('db_pass', ''),
            type="password"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("💾 保存配置", key="db_save"):
                st.session_state.db_use_ssh = use_ssh
                if use_ssh:
                    st.session_state.db_ssh_host = ssh_host
                    st.session_state.db_ssh_port = ssh_port
                    st.session_state.db_ssh_user = ssh_user
                    st.session_state.db_ssh_pass = ssh_pass
                st.session_state.db_host = db_host
                st.session_state.db_port = db_port
                st.session_state.db_name = db_name
                st.session_state.db_user = db_user
                st.session_state.db_pass = db_pass
                st.success("已保存")
        
        with col2:
            if st.button("🔌 测试连接", key="db_test"):
                if not all([db_host, db_name, db_user, db_pass]):
                    st.error("请填写完整的数据库连接信息")
                else:
                    with st.spinner("连接中..."):
                        try:
                            from gllue_db_client import GllueDBConfig, GllueDBClient
                            kwargs = dict(
                                db_type="mysql",
                                host=db_host,
                                port=int(db_port),
                                database=db_name,
                                username=db_user,
                                password=db_pass
                            )
                            if use_ssh:
                                kwargs.update(
                                    use_ssh=True,
                                    ssh_host=st.session_state.get('db_ssh_host', ''),
                                    ssh_port=int(st.session_state.get('db_ssh_port', 22)),
                                    ssh_user=st.session_state.get('db_ssh_user', 'root'),
                                    ssh_password=st.session_state.get('db_ssh_pass', '')
                                )
                            db_config = GllueDBConfig(**kwargs)
                            db_client = GllueDBClient(db_config)
                            tables = db_client.query("SHOW TABLES LIMIT 5")
                            st.success(f"连接成功！发现 {len(tables)} 张表")
                        except Exception as e:
                            st.error(f"连接失败: {str(e)[:200]}")
        
        if st.button("🚀 从数据库同步", type="primary", key="db_sync"):
            if not all([db_host, db_name, db_user, db_pass]):
                st.error("请填写完整的数据库连接信息")
            else:
                with st.spinner("正在从数据库同步..."):
                    try:
                        from gllue_db_client import GllueDBConfig, GllueDBClient
                        kwargs = dict(
                            db_type="mysql",
                            host=db_host,
                            port=int(db_port),
                            database=db_name,
                            username=db_user,
                            password=db_pass
                        )
                        if use_ssh:
                            kwargs.update(
                                use_ssh=True,
                                ssh_host=st.session_state.get('db_ssh_host', ''),
                                ssh_port=int(st.session_state.get('db_ssh_port', 22)),
                                ssh_user=st.session_state.get('db_ssh_user', 'root'),
                                ssh_password=st.session_state.get('db_ssh_pass', '')
                            )
                        db_config = GllueDBConfig(**kwargs)
                        db_client = GllueDBClient(db_config)
                        stats = db_client.sync_to_finance_analyzer(
                            analyzer,
                            start_date=sync_start_date.strftime('%Y-%m-%d'),
                            end_date=sync_end_date.strftime('%Y-%m-%d')
                        )
                        st.success(f"同步完成！Offer: {stats['offers_fetched']}, Invoice: {stats['invoices_fetched']}, Onboard: {stats['onboards_fetched']}, Forecast: {stats['forecasts_fetched']}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"同步失败: {str(e)[:200]}")
    
'''

if insert_marker in content:
    content = content.replace(insert_marker, new_section + insert_marker)
    print("Database section inserted successfully")
else:
    print("WARNING: Could not find insertion marker")
    # Try alternative marker
    alt_marker = 'st.sidebar.markdown("---")\n    st.sidebar.markdown("### ⚙️ 基础配置")'
    if alt_marker in content:
        content = content.replace(alt_marker, new_section + alt_marker)
        print("Database section inserted with alternative marker")
    else:
        print("ERROR: Could not find any marker")

with open(r"C:\Users\EDY\recruiter_finance_tool\advanced_analysis\app.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Done!")
