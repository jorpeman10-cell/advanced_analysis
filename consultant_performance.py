"""
顾问绩效-行为关联分析模块
从Pipeline数据深入分析顾问行为与业绩的关系
数据口径：
  - 简历推荐 = cvsent (简历发送给客户)
  - 客户面试 = clientinterview 
  - Offer = offersign
  - 入职 = jobsubmission.onboardDate
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict


class ConsultantPerformanceAnalyzer:
    """顾问绩效行为分析器"""
    
    def __init__(self, db_client=None):
        self.db_client = db_client
        self._cvsents = None
        self._interviews = None
        self._forecasts = None
        self._offers = None
        self._onboards = None
    
    def load_from_db(self, start_date: str = "2026-01-01", end_date: str = None):
        """从数据库加载所有必要数据"""
        if self.db_client is None:
            return
        
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')
        
        # 1. 简历推荐数据 (cvsent)
        self._cvsents = self.db_client.query(f"""
            SELECT 
                cs.id as cvsent_id,
                cs.jobsubmission_id,
                cs.user_id,
                CONCAT(IFNULL(u.englishName, ''), ' ', IFNULL(u.chineseName, '')) as consultant,
                cs.dateAdded as date_added,
                cs.date as sent_date,
                cs.status,
                cs.client_id,
                cs.joborder_id,
                jo.jobTitle as position_name,
                c.name as client_name
            FROM cvsent cs
            LEFT JOIN user u ON cs.user_id = u.id
            LEFT JOIN joborder jo ON cs.joborder_id = jo.id
            LEFT JOIN client c ON cs.client_id = c.id
            WHERE cs.dateAdded >= '{start_date}'
              AND cs.dateAdded <= '{end_date}'
              AND cs.active = 1
        """)
        
        # 2. 面试数据
        self._interviews = self.db_client.query(f"""
            SELECT 
                ci.id as interview_id,
                ci.jobsubmission_id,
                ci.round,
                ci.status as interview_status,
                ci.date as interview_date,
                js.user_id,
                CONCAT(IFNULL(u.englishName, ''), ' ', IFNULL(u.chineseName, '')) as consultant
            FROM clientinterview ci
            JOIN jobsubmission js ON ci.jobsubmission_id = js.id
            LEFT JOIN user u ON js.user_id = u.id
            WHERE ci.date >= '{start_date}'
              AND ci.date <= '{end_date}'
              AND ci.active = 1
        """)
        
        # 3. Pipeline/Forecast数据
        self._forecasts = self.db_client.query(f"""
            SELECT 
                fa.id as assignment_id,
                f.id as forecast_id,
                f.job_order_id as joborder_id,
                jo.jobTitle as position_name,
                c.name as client_name,
                f.forecast_fee,
                f.last_stage as stage,
                f.close_date,
                fa.user_id,
                CONCAT(IFNULL(u.englishName, ''), ' ', IFNULL(u.chineseName, '')) as consultant,
                fa.amount_after_tax as assignment_amount,
                fa.role as assignment_role
            FROM forecastassignment fa
            JOIN forecast f ON fa.forecast_id = f.id
            LEFT JOIN joborder jo ON f.job_order_id = jo.id
            LEFT JOIN client c ON jo.client_id = c.id
            LEFT JOIN user u ON fa.user_id = u.id
            WHERE f.close_date >= '{start_date}'
              AND f.close_date <= '{end_date}'
              AND jo.jobStatus = 'Live'
              AND f.last_stage IS NOT NULL
              AND f.last_stage != ''
        """)
        
        # 4. Offer数据
        self._offers = self.db_client.query(f"""
            SELECT 
                os.id as offer_id,
                os.jobsubmission_id,
                os.user_id,
                CONCAT(IFNULL(u.englishName, ''), ' ', IFNULL(u.chineseName, '')) as consultant,
                os.signDate as sign_date,
                os.revenue as fee_amount,
                os.annualSalary,
                jo.jobTitle as position_name,
                c.name as client_name
            FROM offersign os
            LEFT JOIN user u ON os.user_id = u.id
            LEFT JOIN jobsubmission js ON os.jobsubmission_id = js.id
            LEFT JOIN joborder jo ON js.joborder_id = jo.id
            LEFT JOIN client c ON jo.client_id = c.id
            WHERE os.signDate >= '{start_date}'
              AND os.signDate <= '{end_date}'
              AND os.active = 1
        """)
        
        # 5. 入职数据 (从jobsubmission中提取)
        self._onboards = self.db_client.query(f"""
            SELECT 
                js.id as jobsubmission_id,
                js.user_id,
                CONCAT(IFNULL(u.englishName, ''), ' ', IFNULL(u.chineseName, '')) as consultant,
                js.onboardDate as onboard_date,
                jo.jobTitle as position_name,
                c.name as client_name
            FROM jobsubmission js
            LEFT JOIN user u ON js.user_id = u.id
            LEFT JOIN joborder jo ON js.joborder_id = jo.id
            LEFT JOIN client c ON jo.client_id = c.id
            WHERE js.onboardDate >= '{start_date}'
              AND js.onboardDate <= '{end_date}'
              AND js.active = 1
        """)
    
    def get_funnel_analysis(self) -> pd.DataFrame:
        """顾问漏斗转化率分析：推荐 → 面试 → Offer → 入职"""
        if self._cvsents is None or self._cvsents.empty:
            return pd.DataFrame()
        
        cvs = self._cvsents.copy()
        ints = self._interviews.copy() if self._interviews is not None else pd.DataFrame()
        offs = self._offers.copy() if self._offers is not None else pd.DataFrame()
        onbs = self._onboards.copy() if self._onboards is not None else pd.DataFrame()
        
        results = []
        for consultant in cvs['consultant'].dropna().unique():
            c_cv = cvs[cvs['consultant'] == consultant]
            total_cvsents = len(c_cv)
            
            # 面试数
            total_interviews = 0
            interviewed_js_ids = set()
            if not ints.empty:
                c_ints = ints[ints['consultant'] == consultant]
                total_interviews = len(c_ints)
                interviewed_js_ids = set(c_ints['jobsubmission_id'].dropna().unique())
            
            # 有面试的推荐（基于jobsubmission_id关联）
            cv_js_ids = set(c_cv['jobsubmission_id'].dropna().unique())
            cvsents_with_interview = len(cv_js_ids & interviewed_js_ids)
            
            # Offer数
            total_offers = 0
            offer_js_ids = set()
            if not offs.empty:
                c_offs = offs[offs['consultant'] == consultant]
                total_offers = len(c_offs)
                offer_js_ids = set(c_offs['jobsubmission_id'].dropna().unique())
            
            # 入职数
            total_onboards = 0
            if not onbs.empty:
                c_onbs = onbs[onbs['consultant'] == consultant]
                total_onboards = len(c_onbs)
            
            # 转化率
            interview_rate = (cvsents_with_interview / total_cvsents * 100) if total_cvsents > 0 else 0
            offer_from_interview = (total_offers / cvsents_with_interview * 100) if cvsents_with_interview > 0 else 0
            offer_rate = (total_offers / total_cvsents * 100) if total_cvsents > 0 else 0
            onboard_rate = (total_onboards / total_cvsents * 100) if total_cvsents > 0 else 0
            avg_round = c_ints['round'].mean() if not ints.empty and 'c_ints' in dir() and len(c_ints) > 0 else 0
            
            results.append({
                '顾问': consultant,
                '推荐数': total_cvsents,
                '面试数': total_interviews,
                '有面试推荐': cvsents_with_interview,
                'Offer数': total_offers,
                '入职数': total_onboards,
                '推荐到面试率': round(interview_rate, 1),
                '面试到Offer率': round(offer_from_interview, 1),
                '推荐到Offer率': round(offer_rate, 1),
                '推荐到入职率': round(onboard_rate, 1),
                '平均面试轮次': round(avg_round, 1),
            })
        
        return pd.DataFrame(results).sort_values('推荐数', ascending=False)
    
    def get_pipeline_health(self) -> pd.DataFrame:
        """Pipeline健康度分析：各阶段分布、加权收入"""
        if self._forecasts is None or self._forecasts.empty:
            return pd.DataFrame()
        
        fc = self._forecasts.copy()
        
        # 阶段成功率映射
        def get_success_rate(stage):
            if not stage:
                return 0.05
            stage_str = str(stage).lower()
            if 'shortlist' in stage_str or '简历' in stage_str or 'longlist' in stage_str:
                return 0.10
            elif '1st' in stage_str or '客户1面' in stage_str:
                return 0.25
            elif '2nd' in stage_str or '客户2面' in stage_str:
                return 0.30
            elif '3rd' in stage_str or '客户3面' in stage_str:
                return 0.40
            elif 'final' in stage_str or '终面' in stage_str:
                return 0.50
            elif 'offer' in stage_str and '签署' not in stage_str:
                return 0.80
            elif 'onboard' in stage_str or '入职' in stage_str:
                return 1.00
            elif 'new' in stage_str or '加入' in stage_str:
                return 0.05
            return 0.10
        
        fc['success_rate'] = fc['stage'].apply(get_success_rate)
        fc['weighted_revenue'] = fc['forecast_fee'] * fc['success_rate']
        
        results = []
        for consultant in fc['consultant'].dropna().unique():
            c_fc = fc[fc['consultant'] == consultant]
            
            stage_counts = {}
            for stage in ['Shortlist', '1st', '2nd', '3rd', 'Final', 'Offer', 'Onboard']:
                stage_counts[f'stage_{stage.lower()}'] = len(c_fc[c_fc['stage'].str.contains(stage, na=False)])
            
            results.append({
                '顾问': consultant,
                'Pipeline总数': len(c_fc),
                '阶段1-简历': stage_counts.get('stage_shortlist', 0),
                '阶段2-1面': stage_counts.get('stage_1st', 0),
                '阶段3-2面': stage_counts.get('stage_2nd', 0),
                '阶段4-3面': stage_counts.get('stage_3rd', 0),
                '阶段5-终面': stage_counts.get('stage_final', 0),
                '阶段6-Offer': stage_counts.get('stage_offer', 0),
                '阶段7-入职': stage_counts.get('stage_onboard', 0),
                '加权Pipeline收入': round(c_fc['weighted_revenue'].sum(), 0),
                '平均成功率': round(c_fc['success_rate'].mean() * 100, 1),
            })
        
        return pd.DataFrame(results).sort_values('加权Pipeline收入', ascending=False)
    
    def get_behavior_profile(self, min_submissions: int = 10) -> pd.DataFrame:
        """
        顾问行为画像分析
        将顾问分类为：高产型、精准型、全能型、低效型
        """
        funnel = self.get_funnel_analysis()
        if funnel.empty:
            return pd.DataFrame()
        
        # 过滤数据量不足的顾问
        funnel = funnel[funnel['推荐数'] >= min_submissions].copy()
        
        if len(funnel) == 0:
            return pd.DataFrame()
        
        # 计算分位数
        sub_median = funnel['推荐数'].median()
        offer_rate_median = funnel['推荐到Offer率'].median()
        interview_rate_median = funnel['推荐到面试率'].median()
        
        def classify(row):
            high_volume = row['推荐数'] >= sub_median
            high_conversion = row['推荐到Offer率'] >= offer_rate_median
            high_interview = row['推荐到面试率'] >= interview_rate_median
            
            if high_volume and high_conversion:
                return '⭐ 高产高转（全能型）'
            elif high_volume and not high_conversion:
                return '📊 高产低转（量大型）'
            elif not high_volume and high_conversion:
                return '🎯 低产高转（精准型）'
            else:
                return '⚠️ 低产低转（需关注）'
        
        funnel['行为画像'] = funnel.apply(classify, axis=1)
        
        # 添加效率指标
        funnel['人均职位数'] = funnel['推荐数'] / funnel['推荐数']  # 需要job_count
        
        return funnel[['顾问', '行为画像', '推荐数', '面试数', 'Offer数', '入职数',
                       '推荐到面试率', '面试到Offer率', '推荐到Offer率']]
    
    def get_consultant_full_report(self) -> pd.DataFrame:
        """顾问综合绩效报告（行为+财务）"""
        funnel = self.get_funnel_analysis()
        pipeline = self.get_pipeline_health()
        
        if funnel.empty:
            return pd.DataFrame()
        
        # 合并数据
        report = funnel.copy()
        if not pipeline.empty:
            report = report.merge(pipeline, on='顾问', how='left')
        
        return report
