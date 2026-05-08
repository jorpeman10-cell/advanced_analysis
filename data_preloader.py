"""
数据预加载模块
在应用启动时后台加载所有需要的数据，减少用户等待时间

设计原则：
1. 懒加载：只在需要时启动预加载
2. 后台线程：不阻塞UI渲染
3. 缓存复用：使用现有的 data_cache 机制
4. 状态跟踪：通过 session_state 共享预加载状态
"""

import threading
import time
from typing import Optional, Dict, Any
from datetime import datetime
import pandas as pd
import streamlit as st


class DataPreloader:
    """
    数据预加载器
    
    使用单例模式管理预加载状态，确保多个组件共享同一份数据
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._data = {}
        self._loading = False
        self._loaded = False
        self._error = None
        self._load_time = None
        self._thread = None
    
    @property
    def is_loading(self) -> bool:
        return self._loading
    
    @property
    def is_loaded(self) -> bool:
        return self._loaded
    
    @property
    def error(self) -> Optional[str]:
        return self._error
    
    @property
    def load_time(self) -> Optional[float]:
        return self._load_time
    
    def get_data(self, key: str) -> Optional[pd.DataFrame]:
        """获取预加载的数据"""
        return self._data.get(key)
    
    def get_all_data(self) -> Dict[str, pd.DataFrame]:
        """获取所有预加载的数据"""
        return self._data.copy()
    
    def start_loading(self, db_client):
        """启动后台数据加载线程"""
        if self._loading or self._loaded:
            return
        
        self._loading = True
        self._error = None
        self._thread = threading.Thread(
            target=self._load_data_thread,
            args=(db_client,),
            daemon=True
        )
        self._thread.start()
    
    def _load_data_thread(self, db_client):
        """后台线程：加载所有数据"""
        start_time = time.time()
        
        try:
            from unified_data_loader import UnifiedDataLoader
            from data_cache import get_cached_query
            
            # 使用 UnifiedDataLoader 加载所有核心数据
            loader = UnifiedDataLoader(db_client)
            loader.load_all(force_refresh=False)
            
            # 提取所有数据到预加载器
            self._data = {
                'users': loader.get('users'),
                'teams': loader.get('teams'),
                'joborders': loader.get('joborders'),
                'cvsents': loader.get('cvsents'),
                'interviews': loader.get('interviews'),
                'offers': loader.get('offers'),
                'invoices': loader.get('invoices'),
                'forecasts': loader.get('forecasts'),
                'mappings': loader.get('mappings'),
            }
            
            # 额外加载预警系统需要的数据
            try:
                # 加载 invoice 逾期明细（用于回款预警）
                overdue_detail = get_cached_query("""
                    SELECT i.id, i.invoice_number, i.invoice_status, i.amount,
                           i.dateAdded as invoice_date, i.expected_payment_date,
                           DATEDIFF(CURDATE(), i.expected_payment_date) as overdue_days,
                           c.name as client_name,
                           jo.jobTitle as position_name
                    FROM invoice i
                    LEFT JOIN joborder jo ON i.job_order_id = jo.id
                    LEFT JOIN client c ON jo.client_id = c.id
                    WHERE i.invoice_status IN ('Sent', 'Issued', '部分回款')
                      AND i.expected_payment_date < CURDATE()
                      AND i.amount > 0
                    ORDER BY i.expected_payment_date ASC
                """, db_client, force_refresh=False)
                self._data['overdue_invoices'] = overdue_detail
            except Exception as e:
                # 逾期数据加载失败不影响整体
                self._data['overdue_invoices'] = pd.DataFrame()
            
            self._loaded = True
            self._load_time = time.time() - start_time
            print(f"[DataPreloader] 数据预加载完成，耗时 {self._load_time:.1f} 秒")
            
        except Exception as e:
            self._error = str(e)
            print(f"[DataPreloader] 数据预加载失败: {e}")
        finally:
            self._loading = False
    
    def wait_for_completion(self, timeout: float = 30.0) -> bool:
        """等待加载完成（阻塞调用）"""
        if self._loaded:
            return True
        if not self._loading:
            return False
        
        start = time.time()
        while self._loading and (time.time() - start) < timeout:
            time.sleep(0.1)
        
        return self._loaded
    
    def reset(self):
        """重置预加载状态（用于强制重新加载）"""
        self._data = {}
        self._loading = False
        self._loaded = False
        self._error = None
        self._load_time = None
        self._thread = None


def init_preloader_in_session(db_client=None) -> DataPreloader:
    """
    在 Streamlit session_state 中初始化预加载器
    
    Args:
        db_client: 数据库客户端实例，如果提供则自动启动预加载
    
    Returns:
        DataPreloader 实例
    """
    # 使用 session_state 存储预加载器状态，确保跨rerun保持
    if 'data_preloader' not in st.session_state:
        st.session_state.data_preloader = DataPreloader()
    
    preloader = st.session_state.data_preloader
    
    # 如果提供了db_client且未加载，启动后台加载
    if db_client and not preloader.is_loaded and not preloader.is_loading:
        preloader.start_loading(db_client)
    
    return preloader


def get_preloaded_data(key: str) -> Optional[pd.DataFrame]:
    """
    获取预加载的数据（便捷函数）
    
    Args:
        key: 数据键名，如 'users', 'offers', 'invoices' 等
    
    Returns:
        DataFrame 或 None（如果未预加载）
    """
    if 'data_preloader' not in st.session_state:
        return None
    return st.session_state.data_preloader.get_data(key)


def is_data_ready() -> bool:
    """检查数据是否已预加载完成"""
    if 'data_preloader' not in st.session_state:
        return False
    return st.session_state.data_preloader.is_loaded


def render_preload_status():
    """渲染预加载状态指示器（在侧边栏或页面顶部使用）"""
    if 'data_preloader' not in st.session_state:
        return
    
    preloader = st.session_state.data_preloader
    
    if preloader.is_loading:
        st.info("⏳ 正在后台加载数据...")
    elif preloader.is_loaded:
        load_time = preloader.load_time
        if load_time:
            st.success(f"✅ 数据已预加载 ({load_time:.1f}s)")
    elif preloader.error:
        st.error(f"❌ 数据加载失败: {preloader.error[:50]}")


def preload_all_data_sync(db_client) -> Dict[str, pd.DataFrame]:
    """
    同步预加载所有数据（阻塞调用，用于需要立即使用数据的场景）
    
    Args:
        db_client: 数据库客户端实例
    
    Returns:
        包含所有预加载数据的字典
    """
    preloader = init_preloader_in_session()
    
    if not preloader.is_loaded:
        # 直接在当前线程加载
        preloader._load_data_thread(db_client)
    
    return preloader.get_all_data()
