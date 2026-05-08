"""
数据库配置管理模块
用于安全存储和管理 Gllue 数据库连接配置
"""

import json
import base64
from pathlib import Path
from typing import Any


CONFIG_DIR = Path(__file__).parent / "config"
CONFIG_FILE = CONFIG_DIR / "db_config.json"
SECRET_SECTION = "gllue_db"


def _encode_password(password: str) -> str:
    """简单编码密码（混淆，非加密）"""
    if not password:
        return ""
    return base64.b64encode(password.encode()).decode()


def _decode_password(encoded: str) -> str:
    """解码密码"""
    if not encoded:
        return ""
    try:
        return base64.b64decode(encoded.encode()).decode()
    except Exception:
        return ""


def load_db_config() -> dict:
    """加载数据库配置，返回配置字典（密码已解码）"""
    secrets_config = _load_streamlit_secrets_config()
    if secrets_config:
        config = _default_config()
        config.update(secrets_config)
        return config

    if not CONFIG_FILE.exists():
        return _default_config()
    
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        # 解码密码
        if config.get('password'):
            config['password'] = _decode_password(config['password'])
        if config.get('ssh_password'):
            config['ssh_password'] = _decode_password(config['ssh_password'])
        return config
    except Exception:
        return _default_config()


def save_db_config(config: dict) -> bool:
    """保存数据库配置（密码编码存储）"""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        # 复制配置并编码密码
        save_config = config.copy()
        save_config = config.copy()
        if save_config.get('password'):
            save_config['password'] = _encode_password(save_config['password'])
        if save_config.get('ssh_password'):
            save_config['ssh_password'] = _encode_password(save_config['ssh_password'])
        
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(save_config, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"保存配置失败: {e}")
        return False


def _default_config() -> dict:
    """默认配置"""
    return {
        "host": "127.0.0.1",
        "port": 3306,
        "database": "gllue",
        "username": "",
        "password": "",
        "use_ssh": True,
        "ssh_host": "118.190.96.172",
        "ssh_port": 9998,
        "ssh_user": "root",
        "ssh_password": "",
    }


def _load_streamlit_secrets_config() -> dict:
    """Load deployment config from Streamlit secrets when available."""
    try:
        import streamlit as st

        secrets: Any = st.secrets
        if SECRET_SECTION in secrets:
            raw_config = dict(secrets[SECRET_SECTION])
        else:
            raw_config = {
                key: secrets[key]
                for key in [
                    "host",
                    "port",
                    "database",
                    "username",
                    "password",
                    "use_ssh",
                    "ssh_host",
                    "ssh_port",
                    "ssh_user",
                    "ssh_password",
                ]
                if key in secrets
            }
    except Exception:
        return {}

    config = {key: value for key, value in raw_config.items() if value not in (None, "")}
    for key in ["port", "ssh_port"]:
        if key in config:
            try:
                config[key] = int(config[key])
            except (TypeError, ValueError):
                config.pop(key, None)
    if "use_ssh" in config and isinstance(config["use_ssh"], str):
        config["use_ssh"] = config["use_ssh"].strip().lower() in {"1", "true", "yes", "y", "on"}
    return config


def has_config() -> bool:
    """检查是否已配置数据库连接"""
    config = load_db_config()
    return bool(config.get('username') and config.get('password'))


def config_diagnostics() -> dict:
    """Return non-sensitive deployment diagnostics for Streamlit Cloud."""
    secrets_config = _load_streamlit_secrets_config()
    config = load_db_config()
    return {
        "streamlit_secrets_loaded": bool(secrets_config),
        "streamlit_secret_keys": sorted(secrets_config.keys()),
        "local_config_file_exists": CONFIG_FILE.exists(),
        "has_username": bool(config.get("username")),
        "has_password": bool(config.get("password")),
        "has_ssh_password": bool(config.get("ssh_password")),
        "use_ssh": bool(config.get("use_ssh")),
        "host": config.get("host", ""),
        "database": config.get("database", ""),
        "ssh_host": config.get("ssh_host", ""),
    }


def get_gllue_db_config():
    """返回 GllueDBConfig 对象"""
    from gllue_db_client import GllueDBConfig
    cfg = load_db_config()
    return GllueDBConfig(
        host=cfg.get('host', '127.0.0.1'),
        port=cfg.get('port', 3306),
        database=cfg.get('database', 'gllue'),
        username=cfg.get('username', ''),
        password=cfg.get('password', ''),
        use_ssh=cfg.get('use_ssh', True),
        ssh_host=cfg.get('ssh_host', '118.190.96.172'),
        ssh_port=cfg.get('ssh_port', 9998),
        ssh_user=cfg.get('ssh_user', 'root'),
        ssh_password=cfg.get('ssh_password', ''),
    )
