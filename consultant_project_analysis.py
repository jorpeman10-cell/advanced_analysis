"""
顾问项目新增分析模块
从Joborder数据深入分析顾问项目新增情况、客户维护和工作饱和度
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict


class ConsultantProjectAnalyzer:
    """顾问项目新增分析器"""
    
    def __init__(self, db_client=None):
        self.db_client = db_client
        self._joborders = None
        self._users = None
        self._teams = None
        self._offersign_revenue = None
        self._forecast_pipeline = None
    
    def load_from_db(self, start_date: str = None, end_date: str = None):
        """从数据库加载所有必要数据"""
        if self.db_client is None:
            return
        
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
        
        # 1. 项目数据（Joborder）
        self._joborders = self.db_client.query(f"""
            SELECT 
                j.id as joborder_id,
                j.client_id,
                j.addedBy_id,
                CONCAT(IFNULL(u.englishName, ''), ' ', IFNULL(u.chineseName, '')) as consultant,
                u.team_id,
                j.jobTitle as position_name,
                j.jobStatus,
                j.dateAdded as date_added,
                j.openDate,
                j.closeDate,
                j.totalCount as headcount,
                j.revenue as fee_amount,
                c.name as client_name
            FROM joborder j
            LEFT JOIN user u ON j.addedBy_id = u.id
            LEFT JOIN client c ON j.client_id = c.id
            WHERE j.dateAdded >= '{start_date}'
              AND j.dateAdded <= '{end_date}'
              AND j.is_deleted = 0
              AND u.status = 'Active'
        """)
        
        # 2. 用户数据（仅在职）
        self._users = self.db_client.query("""
            SELECT 
                id as user_id,
                CONCAT(IFNULL(englishName, ''), ' ', IFNULL(chineseName, '')) as consultant,
                team_id,
                status
            FROM user
            WHERE status = 'Active'
        """)
        
        # 3. 团队数据
        self._teams = self.db_client.query("""
            SELECT id as team_id, name as team_name, parent_id
            FROM team
        """)
        
        # 4. 历史Offer金额（用于对比）
        self._offersign_revenue = self.db_client.query("""
            SELECT 
                os.user_id,
                CONCAT(IFNULL(u.englishName, ''), ' ', IFNULL(u.chineseName, '')) as consultant,
                COUNT(*) as offer_count,
                SUM(os.revenue) as total_revenue,
                AVG(os.revenue) as avg_revenue
            FROM offersign os
            LEFT JOIN user u ON os.user_id = u.id
            WHERE os.signDate >= DATE_SUB(NOW(), INTERVAL 365 DAY)
              AND os.active = 1
              AND u.status = 'Active'
            GROUP BY os.user_id
        """)
        
        # 5. 当前Forecast Pipeline金额
        self._forecast_pipeline = self.db_client.query("""
            SELECT 
                fa.user_id,
                CONCAT(IFNULL(u.englishName, ''), ' ', IFNULL(u.chineseName, '')) as consultant,
                COUNT(*) as forecast_count,
                SUM(f.forecast_fee) as total_forecast_fee,
                SUM(fa.amount_after_tax) as total_assignment_amount
            FROM forecastassignment fa
            JOIN forecast f ON fa.forecast_id = f.id
            LEFT JOIN user u ON fa.user_id = u.id
            LEFT JOIN joborder jo ON f.job_order_id = jo.id
            WHERE jo.jobStatus = 'Live'
              AND f.last_stage IS NOT NULL
              AND f.last_stage != ''
              AND u.status = 'Active'
            GROUP BY fa.user_id
        """)
    
    def _get_team_name(self, team_id):
        """获取团队名称"""
        if self._teams is None or team_id is None:
            return '未分配'
        team_row = self._teams[self._teams['team_id'] == team_id]
        if not team_row.empty:
            return str(team_row.iloc[0]['team_name'])
        return f'团队{team_id}'
    
    def _calc_saturation_score(self, monthly_avg: float, live_rate: float, 
                                client_count: int, monthly_revenue: float) -> Dict:
        """
        计算工作饱和度评分及分项明细
        维度：月均项目数(25) + 活跃率(20) + 客户覆盖(20) + 项目金额(25) + 额外工作负荷(10)
        """
        # 1. 月均项目数得分 (25分)
        if monthly_avg >= 8:      job_score = 25
        elif monthly_avg >= 5:    job_score = 20
        elif monthly_avg >= 3:    job_score = 15
        elif monthly_avg >= 1:    job_score = 10
        else:                     job_score = max(0, int(monthly_avg * 5))
        
        # 2. 活跃项目占比得分 (20分)
        if live_rate >= 70:       active_score = 20
        elif live_rate >= 50:     active_score = 15
        elif live_rate >= 30:     active_score = 10
        else:                     active_score = max(0, int(live_rate * 0.25))
        
        # 3. 客户覆盖度得分 (20分)
        if client_count >= 12:    client_score = 20
        elif client_count >= 8:   client_score = 16
        elif client_count >= 5:   client_score = 12
        elif client_count >= 2:   client_score = 6
        else:                     client_score = client_count * 2
        
        # 4. 项目金额得分 (25分) — 月均历史Offer金额
        if monthly_revenue >= 150000:    revenue_score = 25
        elif monthly_revenue >= 80000:   revenue_score = 20
        elif monthly_revenue >= 40000:   revenue_score = 15
        elif monthly_revenue >= 20000:   revenue_score = 10
        elif monthly_revenue > 0:        revenue_score = max(2, int(monthly_revenue / 2000))
        else:                            revenue_score = 0
        
        # 5. 额外工作负荷 (10分) — 基于HC数
        # HC数反映项目复杂度，但不直接参与饱和度核心评分
        
        total = min(100, job_score + active_score + client_score + revenue_score)
        
        return {
            '总分': total,
            '项目数得分': job_score,
            '活跃率得分': active_score,
            '客户覆盖得分': client_score,
            '项目金额得分': revenue_score,
        }
    
    def _calc_maintenance_score(self, repeat_rate: float, new_clients: int) -> Dict:
        """
        计算客户维护度评分及分项明细
        维度：客户复购率(50) + 新客户开发(50)
        """
        # 1. 客户复购率得分 (50分)
        if repeat_rate >= 50:      repeat_score = 50
        elif repeat_rate >= 30:    repeat_score = 40
        elif repeat_rate >= 15:    repeat_score = 30
        elif repeat_rate >= 5:     repeat_score = 15
        elif repeat_rate > 0:      repeat_score = max(3, int(repeat_rate * 2))
        else:                      repeat_score = 0
        
        # 2. 新客户开发得分 (50分)
        if new_clients >= 8:       new_score = 50
        elif new_clients >= 5:     new_score = 40
        elif new_clients >= 3:     new_score = 30
        elif new_clients >= 1:     new_score = new_clients * 8
        else:                      new_score = 0
        
        total = min(100, repeat_score + new_score)
        
        return {
            '总分': total,
            '复购率得分': repeat_score,
            '新客户得分': new_score,
        }
    
    def get_consultant_project_stats(self, period_days: int = 180, active_only: bool = True) -> pd.DataFrame:
        """
        顾问项目新增统计（按顾问维度）
        判断客户维护情况和工作饱和度
        """
        if self._joborders is None or self._joborders.empty:
            return pd.DataFrame()
        
        df = self._joborders.copy()
        
        # 过滤已离职人员
        if active_only and self._users is not None and not self._users.empty:
            active_names = set(self._users['consultant'].dropna().unique())
            df = df[df['consultant'].isin(active_names)].copy()
        
        cutoff_date = datetime.now() - timedelta(days=period_days)
        period_df = df[pd.to_datetime(df['date_added']) >= cutoff_date].copy()
        
        if period_df.empty:
            return pd.DataFrame()
        
        # 获取历史数据（用于判断新老客户）
        history_cutoff = datetime.now() - timedelta(days=period_days)
        history_df = df[pd.to_datetime(df['date_added']) < history_cutoff].copy()
        historical_clients = set(history_df['client_id'].dropna().unique()) if not history_df.empty else set()
        
        # 构建收入对照字典
        revenue_map = {}
        avg_revenue_map = {}
        if self._offersign_revenue is not None and not self._offersign_revenue.empty:
            for _, row in self._offersign_revenue.iterrows():
                revenue_map[row['consultant']] = row['total_revenue'] or 0
                avg_revenue_map[row['consultant']] = row['avg_revenue'] or 0
        
        forecast_map = {}
        forecast_count_map = {}
        if self._forecast_pipeline is not None and not self._forecast_pipeline.empty:
            for _, row in self._forecast_pipeline.iterrows():
                forecast_map[row['consultant']] = row['total_forecast_fee'] or 0
                forecast_count_map[row['consultant']] = row['forecast_count'] or 0
        
        results = []
        for consultant in period_df['consultant'].dropna().unique():
            c_df = period_df[period_df['consultant'] == consultant].copy()
            if len(c_df) == 0:
                continue
            
            total_jobs = len(c_df)
            live_jobs = len(c_df[c_df['jobStatus'] == 'Live'])
            closed_jobs = total_jobs - live_jobs
            
            # 客户统计
            clients = set(c_df['client_id'].dropna().unique())
            client_count = len(clients)
            
            # 新老客户判断（基于历史数据）
            new_clients = clients - historical_clients
            repeat_clients = clients & historical_clients
            new_client_count = len(new_clients)
            repeat_client_count = len(repeat_clients)
            
            # 客户复购率 = 有2个及以上项目的客户占比
            client_job_counts = c_df.groupby('client_id').size()
            repeat_clients_in_period = len(client_job_counts[client_job_counts >= 2])
            client_repeat_rate = (repeat_clients_in_period / client_count * 100) if client_count > 0 else 0
            
            # 项目活跃率
            live_rate = (live_jobs / total_jobs * 100) if total_jobs > 0 else 0
            
            # 月均新增
            months = period_days / 30.0
            monthly_avg = total_jobs / months if months > 0 else 0
            
            # 总HC数
            total_hc = c_df['headcount'].fillna(1).sum()
            
            # 团队信息
            team_id = c_df['team_id'].iloc[0] if 'team_id' in c_df.columns else None
            team_name = self._get_team_name(team_id)
            
            # 历史收入数据
            hist_revenue = revenue_map.get(consultant, 0)
            avg_offer_revenue = avg_revenue_map.get(consultant, 0)
            monthly_revenue = hist_revenue / 12.0  # 年化转月均
            
            # Pipeline数据
            forecast_revenue = forecast_map.get(consultant, 0)
            forecast_count = forecast_count_map.get(consultant, 0)
            pipeline_ratio = (forecast_revenue / hist_revenue) if hist_revenue > 0 else (999 if forecast_revenue > 0 else 0)
            
            # 工作饱和度评分（含明细）
            sat_detail = self._calc_saturation_score(monthly_avg, live_rate, client_count, monthly_revenue)
            saturation_score = sat_detail['总分']
            
            # 客户维护评分（含明细）
            maint_detail = self._calc_maintenance_score(client_repeat_rate, new_client_count)
            maintenance_score = maint_detail['总分']
            
            results.append({
                '顾问': consultant,
                '团队': team_name,
                '新增项目数': total_jobs,
                '活跃项目数': live_jobs,
                '已关闭项目数': closed_jobs,
                '项目活跃率': round(live_rate, 1),
                '客户数': client_count,
                '新客户数': new_client_count,
                '老客户数': repeat_client_count,
                '客户复购率': round(client_repeat_rate, 1),
                '总HC数': int(total_hc),
                '月均新增': round(monthly_avg, 1),
                # 收入相关
                '历史Offer金额': round(hist_revenue, 0),
                '月均Offer金额': round(monthly_revenue, 0),
                '平均项目金额': round(avg_offer_revenue, 0),
                'Forecast金额': round(forecast_revenue, 0),
                'Forecast项目数': int(forecast_count),
                'Pipeline/历史比': round(pipeline_ratio, 2) if pipeline_ratio < 999 else 10.0,
                # 评分
                '工作饱和度': saturation_score,
                '客户维护度': maintenance_score,
                # 评分明细（用于展示计算过程）
                '_sat_detail': sat_detail,
                '_maint_detail': maint_detail,
            })
        
        result_df = pd.DataFrame(results)
        if result_df.empty:
            return result_df
        
        # 排序：饱和度降序
        return result_df.sort_values('工作饱和度', ascending=False)
    
    def get_team_project_stats(self, period_days: int = 180, active_only: bool = True) -> pd.DataFrame:
        """
        团队项目新增统计（按团队维度）
        """
        if self._joborders is None or self._joborders.empty:
            return pd.DataFrame()
        
        df = self._joborders.copy()
        
        # 过滤已离职人员
        if active_only and self._users is not None and not self._users.empty:
            active_names = set(self._users['consultant'].dropna().unique())
            df = df[df['consultant'].isin(active_names)].copy()
        
        cutoff_date = datetime.now() - timedelta(days=period_days)
        period_df = df[pd.to_datetime(df['date_added']) >= cutoff_date].copy()
        
        if period_df.empty:
            return pd.DataFrame()
        
        # 补充团队名称
        period_df['team_name'] = period_df['team_id'].apply(self._get_team_name)
        
        # 按团队分组统计
        results = []
        for team_name in period_df['team_name'].unique():
            if pd.isna(team_name):
                continue
            t_df = period_df[period_df['team_name'] == team_name]
            
            total_jobs = len(t_df)
            live_jobs = len(t_df[t_df['jobStatus'] == 'Live'])
            client_count = t_df['client_id'].nunique()
            consultant_count = t_df['consultant'].nunique()
            total_hc = t_df['headcount'].fillna(1).sum()
            
            live_rate = (live_jobs / total_jobs * 100) if total_jobs > 0 else 0
            avg_per_consultant = total_jobs / consultant_count if consultant_count > 0 else 0
            months = period_days / 30.0
            monthly_avg = total_jobs / months if months > 0 else 0
            
            results.append({
                '团队': team_name,
                '新增项目数': total_jobs,
                '活跃项目数': live_jobs,
                '项目活跃率': round(live_rate, 1),
                '客户数': client_count,
                '顾问数': consultant_count,
                '人均项目数': round(avg_per_consultant, 1),
                '总HC数': int(total_hc),
                '月均新增': round(monthly_avg, 1),
            })
        
        result_df = pd.DataFrame(results)
        if result_df.empty:
            return result_df
        
        return result_df.sort_values('新增项目数', ascending=False)
    
    def get_monthly_trend(self, months: int = 12, active_only: bool = True) -> pd.DataFrame:
        """
        月度项目新增趋势（按团队）
        """
        if self._joborders is None or self._joborders.empty:
            return pd.DataFrame()
        
        df = self._joborders.copy()
        
        # 过滤已离职人员
        if active_only and self._users is not None and not self._users.empty:
            active_names = set(self._users['consultant'].dropna().unique())
            df = df[df['consultant'].isin(active_names)].copy()
        
        df['month'] = pd.to_datetime(df['date_added']).dt.to_period('M').astype(str)
        df['team_name'] = df['team_id'].apply(self._get_team_name)
        
        # 取最近N个月
        recent_months = sorted(df['month'].unique())[-months:]
        df = df[df['month'].isin(recent_months)]
        
        # 按月和团队分组
        trend = df.groupby(['month', 'team_name']).size().reset_index(name='项目数')
        pivot = trend.pivot(index='month', columns='team_name', values='项目数').fillna(0)
        
        # 添加合计列
        pivot['合计'] = pivot.sum(axis=1)
        
        return pivot.reset_index()
    
    def get_consultant_monthly_trend(self, top_n: int = 10, months: int = 6) -> pd.DataFrame:
        """
        顾问月度项目新增趋势（Top N顾问）
        """
        if self._joborders is None or self._joborders.empty:
            return pd.DataFrame()
        
        df = self._joborders.copy()
        df['month'] = pd.to_datetime(df['date_added']).dt.to_period('M').astype(str)
        
        # 取最近N个月
        recent_months = sorted(df['month'].unique())[-months:]
        df = df[df['month'].isin(recent_months)]
        
        # 取Top N顾问（按项目总数）
        top_consultants = df['consultant'].value_counts().head(top_n).index.tolist()
        df = df[df['consultant'].isin(top_consultants)]
        
        trend = df.groupby(['month', 'consultant']).size().reset_index(name='项目数')
        pivot = trend.pivot(index='month', columns='consultant', values='项目数').fillna(0)
        
        return pivot.reset_index()
    
    def get_client_analysis(self, period_days: int = 180) -> pd.DataFrame:
        """
        客户维度分析：哪些客户被哪些顾问维护，复购情况
        """
        if self._joborders is None or self._joborders.empty:
            return pd.DataFrame()
        
        df = self._joborders.copy()
        cutoff_date = datetime.now() - timedelta(days=period_days)
        period_df = df[pd.to_datetime(df['date_added']) >= cutoff_date].copy()
        
        if period_df.empty:
            return pd.DataFrame()
        
        # 按客户统计
        client_stats = period_df.groupby('client_id').agg({
            'joborder_id': 'count',
            'consultant': lambda x: ', '.join(x.unique()),
            'client_name': 'first',
            'headcount': 'sum',
        }).reset_index()
        client_stats.columns = ['client_id', '项目数', '维护顾问', '客户名称', '总HC数']
        
        # 计算活跃项目数
        live_counts = period_df[period_df['jobStatus'] == 'Live'].groupby('client_id').size()
        client_stats['活跃项目数'] = client_stats['client_id'].map(live_counts).fillna(0).astype(int)
        
        return client_stats.sort_values('项目数', ascending=False)
