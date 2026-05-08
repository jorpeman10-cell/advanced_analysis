"""
权限管理模块
支持顾问（只看自己）和管理层（看全部）两级权限
"""

import streamlit as st
from enum import Enum
from typing import Optional


class UserRole(Enum):
    """用户角色"""
    ADMIN = "admin"        # 管理员/老板
    MANAGER = "manager"    # 团队负责人
    CONSULTANT = "consultant"  # 普通顾问


# 简化的用户数据库（实际项目中应连接真实用户系统）
# 格式: username -> {password, role, consultant_name, team}
USER_DB = {
    "admin": {"password": "admin123", "role": UserRole.ADMIN, "name": "管理员", "team": None},
    "manager1": {"password": "mgr123", "role": UserRole.MANAGER, "name": "运营负责人", "team": "运营"},
    "manager2": {"password": "mgr456", "role": UserRole.MANAGER, "name": "临床负责人", "team": "临床"},
}

# Force reload marker
_RELOAD_MARKER = 42


def init_auth():
    """初始化认证状态"""
    if 'auth_user' not in st.session_state:
        st.session_state.auth_user = None
    if 'auth_role' not in st.session_state:
        st.session_state.auth_role = None
    if 'auth_name' not in st.session_state:
        st.session_state.auth_name = None
    if 'auth_team' not in st.session_state:
        st.session_state.auth_team = None


def login(username: str, password: str) -> bool:
    """登录验证"""
    user = USER_DB.get(username)
    # Debug output
    if user is None:
        st.error(f"DEBUG: 用户 '{username}' 不存在")
        return False
    if user["password"] != password:
        st.error(f"DEBUG: 密码不匹配。输入='{password}', 期望='{user['password']}'")
        return False
    st.session_state.auth_user = username
    st.session_state.auth_role = user["role"]
    st.session_state.auth_name = user["name"]
    st.session_state.auth_team = user.get("team")
    return True


def logout():
    """登出"""
    st.session_state.auth_user = None
    st.session_state.auth_role = None
    st.session_state.auth_name = None
    st.session_state.auth_team = None


def is_logged_in() -> bool:
    """是否已登录"""
    return st.session_state.auth_user is not None


def get_current_role() -> Optional[UserRole]:
    """获取当前用户角色"""
    return st.session_state.auth_role


def get_current_user_name() -> str:
    """获取当前用户显示名"""
    return st.session_state.auth_name or "访客"


def get_current_team() -> Optional[str]:
    """获取当前用户所属团队"""
    return st.session_state.auth_team


def can_view_all() -> bool:
    """是否可以查看全部数据（管理员/经理）"""
    role = get_current_role()
    return role in [UserRole.ADMIN, UserRole.MANAGER]


def can_view_consultant(consultant_name: str) -> bool:
    """是否可以查看指定顾问的数据"""
    if can_view_all():
        return True
    # 顾问只能看自己
    return consultant_name == get_current_user_name()


def filter_by_permission(df, consultant_col: str = '顾问'):
    """根据权限过滤 DataFrame"""
    if can_view_all():
        return df
    
    # 顾问只能看自己的数据
    user_name = get_current_user_name()
    return df[df[consultant_col].str.contains(user_name, na=False)]


def render_login_page():
    """渲染登录页面"""
    st.markdown("""
    <style>
    .login-container {
        max-width: 400px;
        margin: 100px auto;
        padding: 40px;
        background: white;
        border-radius: 16px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.1);
    }
    .login-title {
        font-size: 1.8rem;
        font-weight: 700;
        color: #1a365d;
        text-align: center;
        margin-bottom: 8px;
    }
    .login-subtitle {
        font-size: 0.9rem;
        color: #718096;
        text-align: center;
        margin-bottom: 32px;
    }
    </style>
    """, unsafe_allow_html=True)
    
    st.markdown("""
    <div class="login-container">
        <div class="login-title">T-STAR 财务分析</div>
        <div class="login-subtitle">请先登录以查看数据</div>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        username = st.text_input("用户名", key="login_username")
        password = st.text_input("密码", type="password", key="login_password")
        
        if st.button("登录", type="primary"):
            if login(username, password):
                st.success("登录成功！")
                st.rerun()
            else:
                st.error("用户名或密码错误")
        
        st.markdown("""
        <div style="margin-top: 20px; padding: 12px; background: #f7fafc; border-radius: 8px; font-size: 0.8rem; color: #718096;">
        <b>测试账号：</b><br>
        管理员: admin / admin123<br>
        经理: manager1 / mgr123<br>
        经理: manager2 / mgr456
        </div>
        """, unsafe_allow_html=True)


def render_user_banner():
    """渲染用户状态横幅"""
    if is_logged_in():
        role_icon = "👑" if get_current_role() == UserRole.ADMIN else "👔" if get_current_role() == UserRole.MANAGER else "👤"
        team_info = f" | {get_current_team()}" if get_current_team() else ""
        
        st.markdown(f"""
        <div style="display: flex; justify-content: space-between; align-items: center; 
                    padding: 8px 16px; background: #f7fafc; border-radius: 8px; margin-bottom: 16px;">
            <span style="font-size: 0.9rem; color: #4a5568;">
                {role_icon} <b>{get_current_user_name()}</b>{team_info}
            </span>
            <span style="font-size: 0.8rem; color: #a0aec0;">
                权限: {'全部数据' if can_view_all() else '仅自己'}
            </span>
        </div>
        """, unsafe_allow_html=True)
