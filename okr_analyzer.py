"""
OKR 绩效工资自动计算模块

核心流程：
1. 从Excel模板提取每个顾问的OKR规则（指标、权重、计分规则）
2. 每月自动从系统获取实际业务数据
3. 根据规则自动打分并计算奖金
4. 支持人工校对和调整

Excel格式：
- 每个顾问占多行（1行主信息 + 多行子行）
- 子行共享主行的考核项目名称，但各自有独立的实际完成值和奖金
- 列8: 考核项目名称
- 列9: 考核指标（如"10分/周"）
- 列10: 权重
- 列11: 计分规则
- 列12: 实际完成值
- 列13: 实得奖金（Excel中已计算，用于对比验证）
- 列14: 3月奖金合计
- 列15: 2月待补发奖金
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path
import json
import re


@dataclass
class OKRRule:
    """OKR单项规则（一个考核项目）"""
    name: str  # 指标名称
    target_desc: str  # 目标描述（如"10分/周"）
    weight: float  # 权重
    period: str  # 周期: weekly/monthly/quarterly
    
    # 计分规则（用于周考核得分计算）
    score_rules: Dict[str, float] = field(default_factory=dict)
    
    # 阈值规则（用于判断是否发奖金）
    threshold_no_bonus: float = 0.0
    threshold_half_bonus: float = 0.0  
    threshold_full_bonus: float = 0.0
    
    # 阶梯奖金规则（直接定义各档奖金）
    tier_rules: List[Dict] = field(default_factory=list)
    # 例如: [{'min': 0, 'max': 6, 'bonus': 0}, {'min': 7, 'max': 9, 'bonus': 125}, {'min': 10, 'bonus': 250}]
    
    # 奖金基数（该指标对应的每周/每月奖金）
    base_amount: float = 0.0
    
    # 起算比例（如0.8表示80%起算）
    start_ratio: float = 0.0


@dataclass
class ConsultantOKR:
    """顾问OKR记录"""
    name: str  # 英文名
    chinese_name: str  # 中文名
    level: str  # 级别
    team: str  # 团队
    manager: str  # 汇报线
    base_bonus: float = 1000.0  # 月度奖金基数
    rules: List[OKRRule] = field(default_factory=list)
    
    def to_dict(self):
        return {
            'name': self.name,
            'chinese_name': self.chinese_name,
            'level': self.level,
            'team': self.team,
            'manager': self.manager,
            'base_bonus': self.base_bonus,
            'rules': [
                {
                    'name': r.name,
                    'target_desc': r.target_desc,
                    'weight': r.weight,
                    'period': r.period,
                    'score_rules': r.score_rules,
                    'threshold_no_bonus': r.threshold_no_bonus,
                    'threshold_half_bonus': r.threshold_half_bonus,
                    'threshold_full_bonus': r.threshold_full_bonus,
                    'tier_rules': r.tier_rules,
                    'base_amount': r.base_amount,
                }
                for r in self.rules
            ]
        }
    
    @classmethod
    def from_dict(cls, data):
        okr = cls(
            name=data.get('name', data.get('consultant_name', '')),
            chinese_name=data.get('chinese_name', ''),
            level=data.get('level', ''),
            team=data.get('team', ''),
            manager=data.get('manager', ''),
            base_bonus=data.get('base_bonus', 1000.0),
        )
        for r in data.get('rules', []):
            okr.rules.append(OKRRule(
                name=r['name'],
                target_desc=r['target_desc'],
                weight=r['weight'],
                period=r['period'],
                score_rules=r.get('score_rules', {}),
                threshold_no_bonus=r.get('threshold_no_bonus', 0),
                threshold_half_bonus=r.get('threshold_half_bonus', 0),
                threshold_full_bonus=r.get('threshold_full_bonus', 0),
                tier_rules=r.get('tier_rules', []),
                base_amount=r.get('base_amount', 0),
            ))
        return okr


class OKRParser:
    """OKR Excel解析器"""
    
    @staticmethod
    def parse_excel(file_path: str) -> List[ConsultantOKR]:
        """解析OKR Excel文件"""
        df = pd.read_excel(file_path, header=None)
        
        # 找出所有顾问行（有英文名字的行，列1）
        name_rows = []
        for i in range(len(df)):
            val = df.iloc[i, 1]
            if (pd.notna(val) and isinstance(val, str) and 
                val not in ['英文名字', 'NaN', 'nan'] and len(val) > 1):
                name_rows.append(i)
        
        consultants = []
        for i, start_row in enumerate(name_rows):
            end_row = name_rows[i+1] if i+1 < len(name_rows) else len(df)
            consultant = OKRParser._parse_consultant(df, start_row, end_row)
            if consultant:
                consultants.append(consultant)
        
        return consultants
    
    @staticmethod
    def _parse_consultant(df: pd.DataFrame, start: int, end: int) -> Optional[ConsultantOKR]:
        """解析单个顾问的所有行"""
        name = str(df.iloc[start, 1]).strip()
        if not name or name == '英文名字':
            return None
        
        consultant = ConsultantOKR(
            name=name,
            chinese_name=str(df.iloc[start, 2]).strip() if pd.notna(df.iloc[start, 2]) else '',
            level=str(df.iloc[start, 3]).strip() if pd.notna(df.iloc[start, 3]) else '',
            team=str(df.iloc[start, 4]).strip() if pd.notna(df.iloc[start, 4]) else '',
            manager=str(df.iloc[start, 5]).strip() if pd.notna(df.iloc[start, 5]) else '',
        )
        
        # 先收集主行的规则信息（用于子行继承）
        main_rule_text = str(df.iloc[start, 11]).strip() if pd.notna(df.iloc[start, 11]) else ''
        main_project = str(df.iloc[start, 8]).strip() if pd.notna(df.iloc[start, 8]) else ''
        main_target = str(df.iloc[start, 9]).strip() if pd.notna(df.iloc[start, 9]) else ''
        
        # 解析主行的规则（只解析一次）
        main_score_rules = OKRParser._parse_score_rules(main_rule_text)
        main_thresholds = OKRParser._parse_thresholds(main_rule_text)
        main_tier_rules = OKRParser._parse_tier_rules(main_rule_text, 0)
        
        # 跟踪最近的有规则的行
        last_rule_text = main_rule_text
        last_score_rules = main_score_rules
        last_thresholds = main_thresholds
        last_tier_rules = main_tier_rules
        last_project = main_project
        last_target = main_target
        
        # 第一遍：收集所有行的原始数据
        raw_rows = []
        for row in range(start, end):
            weight = OKRParser._to_float(df.iloc[row, 10])
            if weight <= 0:
                continue
            
            project = str(df.iloc[row, 8]).strip() if pd.notna(df.iloc[row, 8]) else ''
            target = str(df.iloc[row, 9]).strip() if pd.notna(df.iloc[row, 9]) else ''
            rule_text = str(df.iloc[row, 11]).strip() if pd.notna(df.iloc[row, 11]) else ''
            actual = OKRParser._to_float(df.iloc[row, 12])
            bonus = OKRParser._to_float(df.iloc[row, 13])
            
            # 如果子行没有项目名称，向上查找最近的有项目的行
            if not project and row > start:
                for prev in range(row-1, start-1, -1):
                    prev_project = str(df.iloc[prev, 8]).strip() if pd.notna(df.iloc[prev, 8]) else ''
                    if prev_project:
                        project = prev_project
                        break
                if not project:
                    project = main_project
            if not target and row > start:
                for prev in range(row-1, start-1, -1):
                    prev_target = str(df.iloc[prev, 9]).strip() if pd.notna(df.iloc[prev, 9]) else ''
                    if prev_target:
                        target = prev_target
                        break
                if not target:
                    target = main_target
            
            # 确定规则来源
            if row == start:
                score_rules = main_score_rules
                thresholds = main_thresholds
                tier_rules = main_tier_rules
            else:
                if rule_text:
                    last_rule_text = rule_text
                    last_score_rules = OKRParser._parse_score_rules(rule_text)
                    last_thresholds = OKRParser._parse_thresholds(rule_text)
                    last_tier_rules = OKRParser._parse_tier_rules(rule_text, bonus)
                    last_project = project
                    last_target = target
                score_rules = last_score_rules
                thresholds = last_thresholds
                tier_rules = last_tier_rules
            
            raw_rows.append({
                'row': row,
                'project': project,
                'target': target,
                'weight': weight,
                'rule_text': rule_text if row == start else last_rule_text,
                'actual': actual,
                'bonus': bonus,
                'score_rules': score_rules,
                'thresholds': thresholds,
                'tier_rules': tier_rules,
            })
        
        # 第二遍：按项目名称分组，推断每个项目的base_amount和tier_rules
        project_bonuses = {}
        for r in raw_rows:
            proj = r['project']
            if proj not in project_bonuses:
                project_bonuses[proj] = []
            if r['bonus'] > 0:
                project_bonuses[proj].append(r['bonus'])
        
        # 推断base_amount：取每个项目非零bonus的最大值（通常是全额奖金）
        project_base = {}
        project_unique_bonuses = {}
        for proj, bonuses in project_bonuses.items():
            if bonuses:
                project_base[proj] = max(bonuses)
                project_unique_bonuses[proj] = len(set(bonuses))
        
        # 第三遍：创建规则
        for r in raw_rows:
            proj = r['project']
            
            # 解析周期
            period = 'monthly'
            if '/周' in r['target'] or '/周' in proj or '周' in proj:
                period = 'weekly'
            elif ('季度' in r['target'] or '季度' in r['rule_text'] or 'quarter' in proj.lower() or
                  '年度' in proj or 'OKR' in proj or 'okr' in proj.lower() or
                  '新客户' in proj or 'BDcase' in proj or '边际贡献率' in proj or '新领域' in proj or
                  '职位成功率' in proj):
                period = 'quarterly'
            
            # 确定base_amount
            if proj in project_base:
                base_amount = project_base[proj]
            else:
                base_amount = OKRParser._infer_base_amount(r['rule_text'], r['bonus'], r['weight'], consultant.base_bonus)
            
            # 修正：对于有阈值规则的指标，base_amount不应低于base_bonus * weight
            if r['thresholds']['full_bonus'] > 0:
                expected_base = consultant.base_bonus * r['weight']
                if base_amount < expected_base:
                    base_amount = expected_base
            
            # 修正：对于阶梯规则，如果推断的base_amount过低，使用base_bonus * weight
            if r['tier_rules'] and base_amount < consultant.base_bonus * r['weight']:
                max_tier_bonus = max([t.get('bonus', 0) for t in r['tier_rules']], default=0)
                if max_tier_bonus > base_amount:
                    base_amount = max_tier_bonus
            
            # 修正：月度考核指标，base_amount不应低于base_bonus * weight
            if period == 'monthly' and base_amount < consultant.base_bonus * r['weight']:
                base_amount = consultant.base_bonus * r['weight']
            
            # 修正tier_rules：如果项目下所有非零bonus都相同，简化tier_rules
            tier_rules = r['tier_rules']
            if proj in project_unique_bonuses and project_unique_bonuses[proj] == 1 and tier_rules:
                # 所有非零bonus相同，找到最低门槛
                min_threshold = min([t.get('min', float('inf')) for t in tier_rules], default=0)
                if min_threshold > 0:
                    tier_rules = [{'min': min_threshold, 'bonus': base_amount}]
            
            # 修正：对于\"开始计算\"类型的规则，如果项目下非零bonus只有一种
            # 且tier_bonus低于base_amount，提升为base_amount
            if ('开始计算' in r['rule_text'] or '起算' in r['rule_text']) and proj in project_unique_bonuses and project_unique_bonuses[proj] == 1:
                for t in tier_rules:
                    if t.get('bonus', 0) < base_amount:
                        t['bonus'] = base_amount
            
            # 解析起算比例
            start_ratio = OKRParser._parse_start_ratio(r['rule_text'])
            
            rule = OKRRule(
                name=proj or r['target'] or f'指标{r["row"]-start+1}',
                target_desc=r['target'],
                weight=r['weight'],
                period=period,
                score_rules=r['score_rules'],
                threshold_no_bonus=r['thresholds']['no_bonus'],
                threshold_half_bonus=r['thresholds']['half_bonus'],
                threshold_full_bonus=r['thresholds']['full_bonus'],
                tier_rules=tier_rules,
                base_amount=base_amount,
                start_ratio=start_ratio,
            )
            consultant.rules.append(rule)
        
        return consultant
    
    @staticmethod
    def _parse_score_rules(text: str) -> Dict[str, float]:
        """解析计分规则，如'推荐报告1分，第一轮面试1分，offer 3分'"""
        rules = {}
        if not text:
            return rules
        
        # 匹配各种计分格式
        patterns = [
            (r'推荐报告?\s*(\d+(?:\.\d+)?)\s*分?', '推荐报告'),
            (r'第一轮?面试?\s*(\d+(?:\.\d+)?)\s*分?', '第一轮面试'),
            (r'offer\s*(\d+(?:\.\d+)?)\s*分?', 'offer'),
            (r'简历\s*(\d+(?:\.\d+)?)\s*分?', '简历'),
            (r'推荐\s*(\d+(?:\.\d+)?)\s*分?', '推荐'),
            (r'面试\s*(\d+(?:\.\d+)?)\s*分?', '面试'),
        ]
        
        for pattern, keyword in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                rules[keyword] = float(match.group(1))
        
        return rules
    
    @staticmethod
    def _parse_thresholds(text: str) -> Dict[str, float]:
        """解析奖金阈值"""
        result = {'no_bonus': 0, 'half_bonus': 0, 'full_bonus': 0}
        if not text:
            return result
        
        # 无奖金门槛: "0-6分无奖金"
        no_match = re.search(r'(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*分?\s*无', text)
        if no_match:
            result['no_bonus'] = float(no_match.group(2))
        
        # 半奖门槛: "7-9分一半"
        half_match = re.search(r'(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*分?\s*一半|半额', text)
        if half_match:
            result['half_bonus'] = float(half_match.group(1))
        
        # 全奖门槛: "10分及以上全额"
        full_match = re.search(r'(\d+(?:\.\d+)?)\s*分?\s*及?以?上?\s*全', text)
        if full_match:
            result['full_bonus'] = float(full_match.group(1))
        
        return result
    
    @staticmethod
    def _parse_tier_rules(text: str, sample_bonus: float) -> List[Dict]:
        """解析阶梯奖金规则"""
        tiers = []
        if not text:
            return tiers
        
        # 模式1: "电话量≥60→100元，50≤电话量<60→50元"
        tier_matches = re.findall(
            r'(\d+)\s*[≤<]\s*\w+\s*[<≤]\s*(\d+)\s*→\s*(\d+)\s*元?',
            text
        )
        for m in tier_matches:
            tiers.append({'min': float(m[0]), 'max': float(m[1]), 'bonus': float(m[2])})
        
        # 模式2: "2个25一周;3个50一周"
        tier_matches2 = re.findall(
            r'(\d+)\s*个\s*(\d+)\s*元?\s*一?周?',
            text
        )
        for m in tier_matches2:
            tiers.append({'min': float(m[0]), 'bonus': float(m[1])})
        
        # 模式3: "9-11个150元，12-14个200元，15个300元"
        tier_matches3 = re.findall(
            r'(\d+)\s*-\s*(\d+)\s*个\s*(\d+)\s*元',
            text
        )
        for m in tier_matches3:
            tiers.append({'min': float(m[0]), 'max': float(m[1]), 'bonus': float(m[2])})
        
        tier_matches4 = re.findall(
            r'(\d+)\s*个\s*(\d+)\s*元',
            text
        )
        for m in tier_matches4:
            # 避免重复添加
            found = False
            for t in tiers:
                if t.get('min') == float(m[0]) and t.get('bonus') == float(m[1]):
                    found = True
                    break
            if not found:
                tiers.append({'min': float(m[0]), 'bonus': float(m[1])})
        
        # 模式5: "大于或等于X个可以获得Y元" / "≥X个可以获得Y元"
        tier_matches5 = re.findall(
            r'大于或等于\s*(\d+)\s*个.*?\s*(\d+)\s*元',
            text
        )
        for m in tier_matches5:
            found = False
            for t in tiers:
                if t.get('min') == float(m[0]):
                    found = True
                    break
            if not found:
                tiers.append({'min': float(m[0]), 'bonus': float(m[1])})
        
        # 模式6: "完成X个开始算，X个Y元" / "完成X个开始算，X个获Y元"
        tier_matches6 = re.findall(
            r'完成\s*(\d+)\s*个开始算.*?等于\s*(\d+)\s*个.*?\s*(\d+)\s*元',
            text
        )
        for m in tier_matches6:
            tiers.append({'min': float(m[1]), 'bonus': float(m[2])})
        
        # 模式7: "X个以上...Y元" (如"20个以上BD call...100元")
        tier_matches7 = re.findall(
            r'(\d+)\s*个以?上.*?\s*(\d+)\s*元',
            text
        )
        for m in tier_matches7:
            found = False
            for t in tiers:
                if t.get('min') == float(m[0]):
                    found = True
                    break
            if not found:
                tiers.append({'min': float(m[0]), 'bonus': float(m[1])})
        
        # 模式8: "≥X→Y元" (大于等于X得Y元)
        tier_matches8 = re.findall(
            r'[≥≥]\s*(\d+)\s*→\s*(\d+)\s*元',
            text
        )
        for m in tier_matches8:
            found = False
            for t in tiers:
                if t.get('min') == float(m[0]):
                    found = True
                    break
            if not found:
                tiers.append({'min': float(m[0]), 'bonus': float(m[1])})
        
        # 模式9: "<X→Y元" (小于X得Y元，通常是0)
        tier_matches9 = re.findall(
            r'<\s*(\d+)\s*→\s*(\d+)\s*元',
            text
        )
        for m in tier_matches9:
            found = False
            for t in tiers:
                if t.get('max') == float(m[0]) and t.get('bonus') == float(m[1]):
                    found = True
                    break
            if not found:
                tiers.append({'max': float(m[0]), 'bonus': float(m[1])})
        
        return tiers
    
    @staticmethod
    def _infer_base_amount(rule_text: str, sample_bonus: float, weight: float, base_bonus: float) -> float:
        """从规则文本和样本奖金反推每周/每月基础奖金金额"""
        if sample_bonus > 0:
            # 从样本奖金反推
            if sample_bonus == 250:
                return 250  # 常见周奖金
            elif sample_bonus == 125:
                return 250  # 半奖对应的全额
            elif sample_bonus == 500:
                return 500
            elif sample_bonus == 100:
                return 100
            elif sample_bonus == 50:
                return 50
            elif sample_bonus == 200:
                return 200
            elif sample_bonus == 300:
                return 300
            elif sample_bonus == 900:
                return 900
            elif sample_bonus == 175:
                return 175
        
        # 从规则文本中提取金额
        amount_match = re.search(r'(\d+)\s*元', rule_text)
        if amount_match:
            return float(amount_match.group(1))
        
        # 默认按权重分配
        return base_bonus * weight
    
    @staticmethod
    def _to_float(val) -> float:
        if pd.isna(val):
            return 0.0
        try:
            return float(val)
        except:
            return 0.0
    
    @staticmethod
    def _parse_target_value(target_desc: str) -> float:
        """解析目标值，支持各种格式"""
        if not target_desc:
            return 0.0
        
        # 尝试直接解析数字
        try:
            return float(target_desc.strip())
        except:
            pass
        
        # 匹配 "X个/月", "X分/周", "X%" 等格式
        m = re.search(r'(\d+(?:\.\d+)?)\s*(?:个|分)', target_desc)
        if m:
            return float(m.group(1))
        
        # 匹配百分比
        m = re.search(r'(\d+(?:\.\d+)?)\s*%', target_desc)
        if m:
            return float(m.group(1)) / 100
        
        # 匹配 "≥X" 格式
        m = re.search(r'≥\s*(\d+(?:\.\d+)?)', target_desc)
        if m:
            return float(m.group(1))
        
        return 0.0
    
    @staticmethod
    def _parse_start_ratio(rule_text: str) -> float:
        """解析起算比例，如'80%起算'"""
        if not rule_text:
            return 0.0
        m = re.search(r'(\d+)%?\s*起算', rule_text)
        if m:
            ratio = float(m.group(1))
            if ratio > 1:
                ratio = ratio / 100
            return ratio
        return 0.0


class OKRDataStore:
    """OKR数据存储"""
    CONFIG_DIR = Path(__file__).parent / "okr_configs"
    
    def __init__(self):
        self.CONFIG_DIR.mkdir(exist_ok=True)
    
    def save(self, consultant: ConsultantOKR):
        """保存顾问OKR配置"""
        safe_name = re.sub(r'[^\w\-]', '_', consultant.name)
        path = self.CONFIG_DIR / f"{safe_name}.json"
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(consultant.to_dict(), f, ensure_ascii=False, indent=2)
    
    def load(self, name: str) -> Optional[ConsultantOKR]:
        """加载顾问OKR配置"""
        safe_name = re.sub(r'[^\w\-]', '_', name)
        path = self.CONFIG_DIR / f"{safe_name}.json"
        if not path.exists():
            return None
        with open(path, 'r', encoding='utf-8') as f:
            return ConsultantOKR.from_dict(json.load(f))
    
    def load_all(self) -> List[ConsultantOKR]:
        """加载所有顾问OKR配置"""
        consultants = []
        for path in self.CONFIG_DIR.glob("*.json"):
            with open(path, 'r', encoding='utf-8') as f:
                consultants.append(ConsultantOKR.from_dict(json.load(f)))
        return consultants
    
    def parse_and_save(self, file_path: str) -> List[ConsultantOKR]:
        """解析Excel并保存"""
        consultants = OKRParser.parse_excel(file_path)
        for c in consultants:
            self.save(c)
        return consultants


class OKRCalculator:
    """OKR奖金计算器"""
    
    def __init__(self, db_client=None):
        self.db_client = db_client
    
    def get_monthly_data(self, consultant_name: str, year: int, month: int) -> Dict:
        """从数据库获取月度业务数据"""
        if not self.db_client:
            return {}
        
        start = f"{year}-{month:02d}-01"
        end = f"{year}-{month+1:02d}-01" if month < 12 else f"{year+1}-01-01"
        
        # 获取user_id（支持英文名匹配）
        user_df = self.db_client.query(f"""
            SELECT id, englishName, chineseName FROM user 
            WHERE englishName LIKE '%{consultant_name}%' 
               OR chineseName LIKE '%{consultant_name}%'
            LIMIT 1
        """)
        if user_df.empty:
            return {}
        
        user_id = user_df.iloc[0]['id']
        
        stats = {}
        
        # 推荐数
        df = self.db_client.query(f"""
            SELECT COUNT(*) as cnt FROM cvsent 
            WHERE user_id = {user_id} AND dateAdded >= '{start}' AND dateAdded < '{end}' AND active = 1
        """)
        stats['cvsent'] = int(df.iloc[0]['cnt']) if not df.empty else 0
        
        # 面试数
        df = self.db_client.query(f"""
            SELECT COUNT(*) as cnt FROM clientinterview ci
            JOIN jobsubmission js ON ci.jobsubmission_id = js.id
            WHERE js.user_id = {user_id} AND ci.date >= '{start}' AND ci.date < '{end}' AND ci.active = 1
        """)
        stats['interview'] = int(df.iloc[0]['cnt']) if not df.empty else 0
        
        # Offer数
        df = self.db_client.query(f"""
            SELECT COUNT(*) as cnt FROM offersign 
            WHERE user_id = {user_id} AND signDate >= '{start}' AND signDate < '{end}' AND active = 1
        """)
        stats['offer'] = int(df.iloc[0]['cnt']) if not df.empty else 0
        
        # 新增职位
        df = self.db_client.query(f"""
            SELECT COUNT(*) as cnt FROM joborder
            WHERE addedBy_id = {user_id} AND dateAdded >= '{start}' AND dateAdded < '{end}' AND is_deleted = 0
        """)
        stats['new_job'] = int(df.iloc[0]['cnt']) if not df.empty else 0
        
        return stats
    
    def calculate_weekly_score(self, rule: OKRRule, weekly_data: Dict) -> float:
        """计算周考核得分（基于计分规则）"""
        if not rule.score_rules:
            return 0
        
        score = 0
        for key, points in rule.score_rules.items():
            if '推荐' in key or '简历' in key:
                score += weekly_data.get('cvsent', 0) * points
            elif '面试' in key:
                score += weekly_data.get('interview', 0) * points
            elif 'offer' in key.lower():
                score += weekly_data.get('offer', 0) * points
        
        return score
    
    def calculate_rule_bonus(self, rule: OKRRule, actual_value: float) -> Dict:
        """计算单项规则奖金（基于实际完成值）"""
        result = {
            'actual': actual_value,
            'bonus': 0.0,
            'detail': '',
        }
        
        # 优先使用阶梯规则
        if rule.tier_rules:
            bonus = 0
            detail_parts = []
            for tier in sorted(rule.tier_rules, key=lambda x: x.get('min', 0), reverse=True):
                min_val = tier.get('min', 0)
                max_val = tier.get('max', float('inf'))
                tier_bonus = tier.get('bonus', 0)
                if actual_value >= min_val and actual_value <= max_val:
                    bonus = tier_bonus
                    detail_parts.append(f'{actual_value}在{min_val}-{max_val}区间，奖金{tier_bonus}元')
                    break
                elif actual_value >= min_val and max_val == float('inf'):
                    bonus = tier_bonus
                    detail_parts.append(f'{actual_value}≥{min_val}，奖金{tier_bonus}元')
                    break
            
            if not detail_parts:
                detail_parts.append(f'{actual_value}未达任何阶梯，无奖金')
            
            result['bonus'] = bonus
            result['detail'] = '; '.join(detail_parts)
            return result
        
        # 使用阈值规则
        if rule.threshold_full_bonus > 0:
            if actual_value >= rule.threshold_full_bonus:
                result['bonus'] = rule.base_amount
                result['detail'] = f'得分{actual_value}，达到全额门槛{rule.threshold_full_bonus}，奖金{rule.base_amount}元'
            elif rule.threshold_half_bonus > 0 and actual_value >= rule.threshold_half_bonus:
                result['bonus'] = rule.base_amount * 0.5
                result['detail'] = f'得分{actual_value}，达到半奖门槛{rule.threshold_half_bonus}，奖金{result["bonus"]}元'
            else:
                result['detail'] = f'得分{actual_value}，未达到门槛{rule.threshold_no_bonus}，无奖金'
            return result
        
        # 检查起算比例
        if rule.start_ratio > 0:
            if actual_value >= rule.start_ratio:
                result['bonus'] = actual_value * rule.base_amount
                result['detail'] = f'完成度{actual_value*100:.0f}%，达到起算比例{rule.start_ratio*100:.0f}%，奖金{result["bonus"]}元'
            else:
                result['detail'] = f'完成度{actual_value*100:.0f}%，未达到起算比例{rule.start_ratio*100:.0f}%，无奖金'
            return result
        
        # 按比例计算
        target = OKRParser._parse_target_value(rule.target_desc)
        
        # 判断actual是否为完成度比例（非整数且period为quarterly）
        is_ratio = (rule.period == 'quarterly' and 
                    actual_value != int(actual_value) and 
                    rule.threshold_full_bonus == 0)
        
        if target > 0 and not is_ratio:
            ratio = actual_value / target
            if ratio >= 1.0:
                result['bonus'] = rule.base_amount
                result['detail'] = f'完成率{ratio*100:.0f}%，全额奖金{rule.base_amount}元'
            elif ratio >= 0.7:
                result['bonus'] = rule.base_amount * 0.5
                result['detail'] = f'完成率{ratio*100:.0f}%，半额奖金{result["bonus"]}元'
            else:
                result['detail'] = f'完成率{ratio*100:.0f}%，未达70%无奖金'
            return result
        
        # 目标无法解析为数字，或actual是完成度比例
        # 使用通用比例计算
        if rule.base_amount > 0:
            if actual_value >= 1.0:
                result['bonus'] = rule.base_amount
                result['detail'] = f'完成度{actual_value*100:.0f}%，全额奖金{rule.base_amount}元'
            else:
                result['bonus'] = actual_value * rule.base_amount
                result['detail'] = f'完成度{actual_value*100:.0f}%，奖金{result["bonus"]}元'
        else:
            result['detail'] = '目标值未设置'
        
        return result
    
    def calculate(self, consultant: ConsultantOKR, year: int, month: int, 
                  weekly_actuals: Optional[List[float]] = None) -> Dict:
        """
        计算顾问月度OKR奖金
        
        Args:
            consultant: 顾问OKR配置
            year, month: 年月
            weekly_actuals: 每周实际完成值列表（可选，用于周考核指标）
                              如果提供，直接使用；否则尝试从数据库获取
        """
        # 获取系统数据（月度汇总）
        monthly_data = self.get_monthly_data(consultant.name, year, month)
        
        results = []
        total_bonus = 0
        
        for i, rule in enumerate(consultant.rules):
            if rule.period == 'weekly':
                # 周考核指标
                if weekly_actuals and i < len(weekly_actuals):
                    actual = weekly_actuals[i]
                else:
                    # 从数据库数据计算周得分（简化：月度数据/4周）
                    weekly_data = {
                        'cvsent': monthly_data.get('cvsent', 0) / 4,
                        'interview': monthly_data.get('interview', 0) / 4,
                        'offer': monthly_data.get('offer', 0) / 4,
                    }
                    actual = self.calculate_weekly_score(rule, weekly_data)
            else:
                # 月度/季度指标
                actual = monthly_data.get('cvsent', 0)
            
            calc = self.calculate_rule_bonus(rule, actual)
            total_bonus += calc['bonus']
            
            results.append({
                'name': rule.name,
                'target': rule.target_desc,
                'weight': rule.weight,
                'period': rule.period,
                'actual': actual,
                'bonus': calc['bonus'],
                'detail': calc['detail'],
            })
        
        return {
            'consultant': consultant.name,
            'chinese_name': consultant.chinese_name,
            'year': year,
            'month': month,
            'total_bonus': total_bonus,
            'rules': results,
        }
    
    def calculate_with_excel_actuals(self, consultant: ConsultantOKR, 
                                     actual_values: List[float]) -> Dict:
        """
        使用Excel中的实际完成值计算奖金（用于验证）
        
        Args:
            consultant: 顾问OKR配置
            actual_values: 每个rule对应的实际完成值列表
        """
        results = []
        total_bonus = 0
        
        for i, rule in enumerate(consultant.rules):
            actual = actual_values[i] if i < len(actual_values) else 0
            calc = self.calculate_rule_bonus(rule, actual)
            total_bonus += calc['bonus']
            
            results.append({
                'name': rule.name,
                'target': rule.target_desc,
                'weight': rule.weight,
                'period': rule.period,
                'actual': actual,
                'bonus': calc['bonus'],
                'detail': calc['detail'],
            })
        
        return {
            'consultant': consultant.name,
            'chinese_name': consultant.chinese_name,
            'total_bonus': total_bonus,
            'rules': results,
        }


# 便捷函数
def parse_okr_excel(file_path: str) -> List[ConsultantOKR]:
    """解析OKR Excel"""
    return OKRParser.parse_excel(file_path)
