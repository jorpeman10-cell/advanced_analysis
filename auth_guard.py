#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
简单访问控制模块
用于给财务状况分析页面等敏感功能添加密码保护
"""

import os
import json
import base64
import streamlit as st


AUTH_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'auth_config.json'
)


def _load_auth_config() -> dict:
    """加载认证配置"""
    if os.path.exists(AUTH_CONFIG_PATH):
        try:
            with open(AUTH_CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_auth_config(config: dict):
    """保存认证配置"""
    try:
        with open(AUTH_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存认证配置失败: {e}")


def _encode_password(pwd: str) -> str:
    """Base64 编码密码（简单混淆，非加密）"""
    return base64.b64encode(pwd.encode('utf-8')).decode('utf-8')


def _decode_password(encoded: str) -> str:
    """Base64 解码密码"""
    try:
        return base64.b64decode(encoded).decode('utf-8')
    except Exception:
        return ""


def set_real_finance_password(password: str):
    """设置财务状况分析页面访问密码（空字符串表示取消密码）"""
    config = _load_auth_config()
    if password:
        config['real_finance_password'] = _encode_password(password)
    else:
        config.pop('real_finance_password', None)
    _save_auth_config(config)


def get_real_finance_password() -> str:
    """获取已设置的财务状况分析页面密码（明文），未设置返回空字符串"""
    config = _load_auth_config()
    encoded = config.get('real_finance_password', '')
    if encoded:
        return _decode_password(encoded)
    return ""


def is_real_finance_protected() -> bool:
    """财务状况分析页面是否已设置密码保护"""
    return bool(get_real_finance_password())


def verify_real_finance_password(password: str) -> bool:
    """验证财务状况分析页面密码"""
    correct = get_real_finance_password()
    if not correct:
        return True
    return password == correct


def require_real_finance_auth() -> bool:
    """
    在财务状况分析页面顶部调用，处理登录态检查。
    返回 True 表示已通过验证，可以继续渲染页面内容。
    返回 False 表示未通过验证，页面应停止渲染。
    
    使用方式:
        if not require_real_finance_auth():
            return
    """
    if not is_real_finance_protected():
        return True
    
    session_key = 'real_finance_authenticated'
    if st.session_state.get(session_key, False):
        return True
    
    st.markdown('<div class="main-header">🔒 财务状况分析</div>', unsafe_allow_html=True)
    st.info("该页面已设置访问密码，请输入密码后查看")
    
    col1, col2 = st.columns([2, 1])
    with col1:
        pwd = st.text_input("访问密码", type="password", key="real_finance_pwd_input")
    with col2:
        st.write("")
        st.write("")
        if st.button("验证", use_container_width=True, key="real_finance_auth_btn"):
            if verify_real_finance_password(pwd):
                st.session_state[session_key] = True
                st.success("验证通过")
                st.rerun()
            else:
                st.error("密码错误")
    
    return False


def logout_real_finance():
    """退出财务状况分析页面登录状态"""
    st.session_state.pop('real_finance_authenticated', None)
