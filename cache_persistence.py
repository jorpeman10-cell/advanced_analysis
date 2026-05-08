"""
缓存持久化模块 - SQLite 存储
解决内存缓存重启丢失问题
"""

import sqlite3
import pickle
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import hashlib
import json

CACHE_DB = Path(__file__).parent / "cache" / "data_cache.db"
CACHE_DB.parent.mkdir(exist_ok=True)
CACHE_TTL_MINUTES = 30


def _init_db():
    """初始化 SQLite 缓存表"""
    conn = sqlite3.connect(CACHE_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS query_cache (
            cache_key TEXT PRIMARY KEY,
            sql_hash TEXT,
            data BLOB,
            created_at TIMESTAMP,
            expires_at TIMESTAMP,
            row_count INTEGER
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_expires ON query_cache(expires_at)
    """)
    conn.commit()
    conn.close()


def get_persistent_cache(sql: str, db_client=None, force_refresh: bool = False) -> pd.DataFrame:
    """
    获取持久化缓存的查询结果
    
    Args:
        sql: SQL查询语句
        db_client: 数据库客户端
        force_refresh: 强制刷新
    
    Returns:
        DataFrame
    """
    _init_db()
    
    sql_hash = hashlib.md5(sql.encode()).hexdigest()
    cache_key = f"query_{sql_hash}"
    
    conn = sqlite3.connect(CACHE_DB)
    
    try:
        # 检查缓存是否有效
        if not force_refresh:
            cursor = conn.execute(
                "SELECT data, expires_at FROM query_cache WHERE cache_key = ?",
                (cache_key,)
            )
            row = cursor.fetchone()
            
            if row:
                data_blob, expires_at = row
                expires = datetime.fromisoformat(expires_at)
                
                if datetime.now() < expires:
                    # 缓存有效
                    df = pickle.loads(data_blob)
                    conn.close()
                    return df
        
        # 缓存无效或不存在，重新查询
        if db_client is None:
            raise ValueError("缓存不存在且未提供db_client")
        
        df = db_client.query(sql)
        
        # 保存到 SQLite
        data_blob = pickle.dumps(df)
        expires_at = datetime.now() + timedelta(minutes=CACHE_TTL_MINUTES)
        
        conn.execute(
            """INSERT OR REPLACE INTO query_cache 
               (cache_key, sql_hash, data, created_at, expires_at, row_count)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (cache_key, sql_hash, data_blob, datetime.now().isoformat(), 
             expires_at.isoformat(), len(df))
        )
        conn.commit()
        
        return df
        
    finally:
        conn.close()


def clear_expired_cache():
    """清除过期缓存"""
    _init_db()
    conn = sqlite3.connect(CACHE_DB)
    conn.execute("DELETE FROM query_cache WHERE expires_at < ?", (datetime.now().isoformat(),))
    conn.commit()
    deleted = conn.total_changes
    conn.close()
    return deleted


def clear_all_cache():
    """清除所有缓存"""
    _init_db()
    conn = sqlite3.connect(CACHE_DB)
    conn.execute("DELETE FROM query_cache")
    conn.commit()
    conn.close()


def get_cache_stats() -> dict:
    """获取缓存统计"""
    _init_db()
    conn = sqlite3.connect(CACHE_DB)
    
    total = conn.execute("SELECT COUNT(*) FROM query_cache").fetchone()[0]
    total_size = conn.execute("SELECT SUM(LENGTH(data)) FROM query_cache").fetchone()[0] or 0
    expired = conn.execute(
        "SELECT COUNT(*) FROM query_cache WHERE expires_at < ?",
        (datetime.now().isoformat(),)
    ).fetchone()[0]
    
    conn.close()
    
    return {
        'total_entries': total,
        'expired_entries': expired,
        'total_size_mb': round(total_size / 1024 / 1024, 2),
        'ttl_minutes': CACHE_TTL_MINUTES,
    }
