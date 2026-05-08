"""
顾问产能差距分析模块
精准发现顾问行为与结果的差距，提供可执行的改进建议
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple


class ConsultantGapAnalyzer:
    """顾问产能差距分析器"""
    
    def __init__(self, unified_loader):
        self.loader = unified_loader
        self._summary = None
    
    def analyze(self) -> pd.DataFrame:
        """执行全面差距分析"""
        df = self.loader.get_consultant_summary()
        if df.empty:
            return df
        
        # 计算团队均值（作为基准）
        avg_cv = df['推荐数'].mean()
        avg_interview = df['面试数'].mean()
        avg_offer = df['Offer数'].mean()
        avg_invoice = df['已回款'].mean()
        avg_cv_to_int = df['推荐→面试率'].mean()
        avg_int_to_offer = df['面试→Offer率'].mean()
        
        # 差距分析
        results = []
        for _, row in df.iterrows():
            gaps = []
            actions = []
            
            # === 行为差距分析 ===
            
            # 1. 推荐量差距
            if row['推荐数'] < avg_cv * 0.5:
                gaps.append("推荐量严重不足")
                actions.append("每日至少新增2个推荐，扩大候选人搜寻范围")
            elif row['推荐数'] < avg_cv * 0.8:
                gaps.append("推荐量偏低")
                actions.append("增加简历筛选时间，提高推荐频率")
            
            # 2. 面试转化率差距
            if row['推荐→面试率'] < avg_cv_to_int * 0.6:
                gaps.append("推荐→面试转化率低")
                actions.append("提升简历质量：加强候选人沟通，确保匹配度后再推荐")
            
            # 3. 面试→Offer转化率差距
            if row['面试数'] > 0 and row['面试→Offer率'] < avg_int_to_offer * 0.5:
                gaps.append("面试→Offer转化率极低")
                actions.append("加强面试辅导：帮助候选人准备客户面试，提升通过率")
            
            # === 结果差距分析 ===
            
            # 4. Offer量差距
            if row['Offer数'] < avg_offer * 0.5 and row['面试数'] > avg_interview:
                gaps.append("高面试低Offer（转化问题）")
                actions.append("复盘面试失败原因，调整候选人筛选标准")
            elif row['Offer数'] < avg_offer * 0.5:
                gaps.append("Offer量不足")
                actions.append("增加Pipeline深度，同时推进多个职位")
            
            # 5. 回款差距
            if row['已回款'] < avg_invoice * 0.3 and row['Offer数'] > 0:
                gaps.append("有Offer但回款差")
                actions.append("跟进候选人入职流程，确保Offer顺利落地")
            
            # 6. Pipeline差距
            if row['Forecast金额'] < row['已回款'] * 0.5:
                gaps.append("Pipeline不足（后续乏力）")
                actions.append("紧急开发新客户/职位，补充Pipeline")
            
            # === 综合评级 ===
            if len(gaps) >= 3:
                level = "🔴 需重点关注"
                priority = 1
            elif len(gaps) >= 1:
                level = "🟡 有改进空间"
                priority = 2
            else:
                level = "🟢 表现优秀"
                priority = 3
            
            # 确定主攻方向（最重要的1个差距）
            main_focus = gaps[0] if gaps else "保持当前状态"
            main_action = actions[0] if actions else "继续保持"
            
            results.append({
                '顾问': row['顾问'],
                'user_id': row['user_id'],
                '综合评级': level,
                '优先级': priority,
                '推荐数': row['推荐数'],
                '面试数': row['面试数'],
                'Offer数': row['Offer数'],
                '已回款': row['已回款'],
                'Forecast金额': row['Forecast金额'],
                '推荐→面试率': row['推荐→面试率'],
                '面试→Offer率': row['面试→Offer率'],
                '差距数量': len(gaps),
                '差距详情': '；'.join(gaps) if gaps else '无',
                '主攻方向': main_focus,
                '改进建议': main_action,
                '全部建议': '\n'.join([f"{i+1}. {a}" for i, a in enumerate(actions)]) if actions else '继续保持',
            })
        
        result_df = pd.DataFrame(results)
        return result_df.sort_values('优先级')
    
    def get_team_benchmark(self) -> Dict:
        """获取团队基准值"""
        df = self.loader.get_consultant_summary()
        if df.empty:
            return {}
        
        return {
            'avg_cv': df['推荐数'].mean(),
            'avg_interview': df['面试数'].mean(),
            'avg_offer': df['Offer数'].mean(),
            'avg_invoice': df['已回款'].mean(),
            'avg_cv_to_int': df['推荐→面试率'].mean(),
            'avg_int_to_offer': df['面试→Offer率'].mean(),
            'top_performer': df.nlargest(1, '已回款')['顾问'].iloc[0] if len(df) > 0 else '',
        }
