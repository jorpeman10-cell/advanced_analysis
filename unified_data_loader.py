"""
统一数据加载器
一次性加载所有需要的数据，减少重复查询
"""

import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Optional
from data_cache import get_cached_query


class UnifiedDataLoader:
    """统一数据加载器 - 一次加载，多处使用"""
    
    def __init__(self, db_client):
        self.db_client = db_client
        self._data = {}
        self._loaded = False
    
    def load_all(self, force_refresh: bool = False):
        """加载所有核心数据"""
        if self._loaded and not force_refresh:
            return
        
        print("[UnifiedLoader] Loading all data...")
        
        # 计算1年前的日期（多处复用）
        year_ago = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
        
        # 1. 顾问基础信息（只加载有业务数据的顾问：有回款、有推荐、有职位或在职的）
        self._data['users'] = get_cached_query(f"""
            SELECT DISTINCT u.id, u.englishName, u.chineseName, u.team_id, u.status,
                   u.joinInDate, u.leaveDate
            FROM user u
            WHERE u.status = 'Active'
               OR u.id IN (SELECT user_id FROM cvsent WHERE dateAdded >= '{year_ago}')
               OR u.id IN (SELECT addedBy_id FROM joborder WHERE dateAdded >= '{year_ago}')
               OR u.id IN (SELECT user_id FROM offersign WHERE signDate >= '{year_ago}')
               OR u.id IN (SELECT user_id FROM invoiceassignment WHERE dateAdded >= '{year_ago}')
               OR u.id IN (SELECT js.user_id FROM clientinterview ci 
                           JOIN jobsubmission js ON ci.jobsubmission_id = js.id 
                           WHERE ci.date >= '{year_ago}')
        """, self.db_client, force_refresh)
        
        # 2. 团队信息
        self._data['teams'] = get_cached_query("""
            SELECT id, name, parent_id FROM team
        """, self.db_client, force_refresh)
        
        # 3. 职位数据（近1年）
        self._data['joborders'] = get_cached_query(f"""
            SELECT j.id, j.client_id, j.addedBy_id, j.jobTitle, j.jobStatus,
                   j.dateAdded, j.totalCount, j.revenue,
                   CONCAT(IFNULL(u.englishName, ''), ' ', IFNULL(u.chineseName, '')) as consultant
            FROM joborder j
            LEFT JOIN user u ON j.addedBy_id = u.id
            WHERE j.dateAdded >= '{year_ago}' AND j.is_deleted = 0
        """, self.db_client, force_refresh)
        
        # 4. 简历推荐（cvsent）
        self._data['cvsents'] = get_cached_query(f"""
            SELECT cs.id, cs.user_id, cs.dateAdded, cs.status,
                   CONCAT(IFNULL(u.englishName, ''), ' ', IFNULL(u.chineseName, '')) as consultant
            FROM cvsent cs
            LEFT JOIN user u ON cs.user_id = u.id
            WHERE cs.dateAdded >= '{year_ago}' AND cs.active = 1
        """, self.db_client, force_refresh)
        
        # 5. 面试数据
        self._data['interviews'] = get_cached_query(f"""
            SELECT ci.id, ci.jobsubmission_id, ci.round, ci.status, ci.date,
                   js.user_id,
                   CONCAT(IFNULL(u.englishName, ''), ' ', IFNULL(u.chineseName, '')) as consultant
            FROM clientinterview ci
            JOIN jobsubmission js ON ci.jobsubmission_id = js.id
            LEFT JOIN user u ON js.user_id = u.id
            WHERE ci.date >= '{year_ago}' AND ci.active = 1
        """, self.db_client, force_refresh)
        
        # 6. Offer数据
        self._data['offers'] = get_cached_query(f"""
            SELECT os.id, os.user_id, os.signDate, os.revenue, os.jobsubmission_id,
                   CONCAT(IFNULL(u.englishName, ''), ' ', IFNULL(u.chineseName, '')) as consultant
            FROM offersign os
            LEFT JOIN user u ON os.user_id = u.id
            WHERE os.signDate >= '{year_ago}' AND os.active = 1
        """, self.db_client, force_refresh)
        
        # 7. 回款数据（invoiceassignment）
        # 注意：invoiceassignment 表没有 invoice_status 和 dateAdded 列
        # 通过 invoice_id 关联 invoice 表获取 paymentReceivedDate，限制为近1年
        # 统一口径：只统计近1年实际收到的回款（与过程数据时间周期一致）
        self._data['invoices'] = get_cached_query(f"""
            SELECT ia.id, ia.user_id, ia.revenue, i.paymentReceivedDate as dateAdded,
                   CONCAT(IFNULL(u.englishName, ''), ' ', IFNULL(u.chineseName, '')) as consultant
            FROM invoiceassignment ia
            JOIN invoice i ON ia.invoice_id = i.id
            LEFT JOIN user u ON ia.user_id = u.id
            WHERE ia.revenue > 0 AND i.paymentReceivedDate >= '{year_ago}' AND i.status = 'Received'
        """, self.db_client, force_refresh)
        
        # 8. Forecast数据
        self._data['forecasts'] = get_cached_query("""
            SELECT fa.user_id, f.forecast_fee, f.last_stage, f.close_date,
                   fa.amount_after_tax, fa.role,
                   CONCAT(IFNULL(u.englishName, ''), ' ', IFNULL(u.chineseName, '')) as consultant
            FROM forecastassignment fa
            JOIN forecast f ON fa.forecast_id = f.id
            LEFT JOIN user u ON fa.user_id = u.id
            LEFT JOIN joborder jo ON f.job_order_id = jo.id
            WHERE jo.jobStatus = 'Live' AND f.last_stage IS NOT NULL
        """, self.db_client, force_refresh)
        
        # 9. Mapping数据
        self._data['mappings'] = get_cached_query("""
            SELECT m.content, co.name as org_name, co.client_name, co.id as org_id,
                   CONCAT(IFNULL(u.englishName, ''), ' ', IFNULL(u.chineseName, '')) as creator
            FROM companyorganizationmapping m
            JOIN companyorganization co ON m.organization_id = co.id
            LEFT JOIN user u ON co.addedBy_id = u.id
            WHERE m.is_current = 1 AND m.is_deleted = 0 AND co.is_deleted = 0
        """, self.db_client, force_refresh)
        
        self._loaded = True
        print("[UnifiedLoader] All data loaded successfully")
    
    def get(self, key: str) -> pd.DataFrame:
        """获取指定数据"""
        if not self._loaded:
            self.load_all()
        return self._data.get(key, pd.DataFrame())
    
    def get_consultant_summary(self) -> pd.DataFrame:
        """获取顾问综合汇总（用于产能差距分析）"""
        if not self._loaded:
            self.load_all()
        
        users = self._data['users']
        cvsents = self._data['cvsents']
        interviews = self._data['interviews']
        offers = self._data['offers']
        invoices = self._data['invoices']
        forecasts = self._data['forecasts']
        joborders = self._data['joborders']
        
        # 排除的运营/非业务顾问名单
        EXCLUDED_CONSULTANTS = [
            '郭建飞', '黄铮', '李菁', '李文婷', 
            'Karmen Huang', 'CSM 支持', 'SYS 账号',
            'Kimbort Guo', 'Steven Huang', 'Lily Li', 
            'Carrie Li', 'Karmen Huang',
            'SYS', 'CSM', '系统账号', '客户支持'
        ]
        
        results = []
        for _, user in users.iterrows():
            consultant = f"{user['englishName'] or ''} {user['chineseName'] or ''}".strip()
            user_id = user['id']
            
            # 跳过已离职顾问
            if user.get('status') == 'Leave':
                continue
            
            # 跳过运营/非业务团队顾问
            if any(excluded in consultant for excluded in EXCLUDED_CONSULTANTS):
                continue
            
            # 行为指标
            cv_count = len(cvsents[cvsents['user_id'] == user_id])
            interview_count = len(interviews[interviews['user_id'] == user_id])
            offer_count = len(offers[offers['user_id'] == user_id])
            
            # 结果指标（统一口径：近1年）
            invoice_total = invoices[invoices['user_id'] == user_id]['revenue'].sum()
            forecast_total = forecasts[forecasts['user_id'] == user_id]['forecast_fee'].sum()
            
            # 项目指标
            job_count = len(joborders[joborders['addedBy_id'] == user_id])
            live_jobs = len(joborders[(joborders['addedBy_id'] == user_id) & (joborders['jobStatus'] == 'Live')])
            
            # 转化率
            cv_to_interview = (interview_count / cv_count * 100) if cv_count > 0 else 0
            interview_to_offer = (offer_count / interview_count * 100) if interview_count > 0 else 0
            offer_to_invoice = (invoice_total / offers[offers['user_id'] == user_id]['revenue'].sum() * 100) if offer_count > 0 else 0
            
            results.append({
                '顾问': consultant,
                'user_id': user_id,
                '推荐数': cv_count,
                '面试数': interview_count,
                'Offer数': offer_count,
                '已回款': invoice_total,
                'Forecast金额': forecast_total,
                '新增项目': job_count,
                '活跃项目': live_jobs,
                '推荐→面试率': round(cv_to_interview, 1),
                '面试→Offer率': round(interview_to_offer, 1),
                'Offer→回款率': round(offer_to_invoice, 1),
            })
        
        return pd.DataFrame(results)
