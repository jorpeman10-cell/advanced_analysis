"""
数据缓存模块
统一缓存数据库查询结果，减少SSH连接压力
"""

import json
import hashlib
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import pickle

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)
CACHE_TTL_MINUTES = 30


def _get_cache_key(sql: str) -> str:
    """生成SQL查询的缓存key"""
    return hashlib.md5(sql.encode()).hexdigest()


def _get_cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.pkl"


def _get_meta_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.json"


def get_cached_query(sql: str, db_client=None, force_refresh: bool = False) -> pd.DataFrame:
    """
    获取缓存的查询结果，如果缓存过期或不存在则重新查询
    
    Args:
        sql: SQL查询语句
        db_client: 数据库客户端实例（用于重新查询）
        force_refresh: 强制刷新缓存
    
    Returns:
        DataFrame
    """
    key = _get_cache_key(sql)
    cache_path = _get_cache_path(key)
    meta_path = _get_meta_path(key)
    
    # 检查缓存是否有效
    if not force_refresh and cache_path.exists() and meta_path.exists():
        try:
            with open(meta_path, 'r') as f:
                meta = json.load(f)
            
            cached_time = datetime.fromisoformat(meta['timestamp'])
            if datetime.now() - cached_time < timedelta(minutes=CACHE_TTL_MINUTES):
                # 缓存有效，直接读取
                with open(cache_path, 'rb') as f:
                    return pickle.load(f)
        except Exception:
            pass  # 缓存读取失败，重新查询
    
    # 缓存无效或不存在，执行查询
    if db_client is None:
        raise ValueError("缓存不存在且未提供db_client")
    
    df = db_client.query(sql)
    
    # 保存缓存
    try:
        with open(cache_path, 'wb') as f:
            pickle.dump(df, f)
        with open(meta_path, 'w') as f:
            json.dump({'timestamp': datetime.now().isoformat(), 'sql': sql[:200]}, f)
    except Exception as e:
        print(f"缓存保存失败: {e}")
    
    return df


def clear_cache():
    """清除所有缓存"""
    for f in CACHE_DIR.glob("*.pkl"):
        f.unlink()
    for f in CACHE_DIR.glob("*.json"):
        f.unlink()
    print("[Cache] All cache cleared")


def get_cache_status() -> dict:
    """获取缓存状态"""
    cache_files = list(CACHE_DIR.glob("*.pkl"))
    total_size = sum(f.stat().st_size for f in cache_files)
    
    return {
        'cache_count': len(cache_files),
        'total_size_mb': round(total_size / 1024 / 1024, 2),
        'ttl_minutes': CACHE_TTL_MINUTES,
    }
