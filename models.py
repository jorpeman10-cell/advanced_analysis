"""
猎头公司进阶财务分析工具 - 核心数据模型
聚焦：职位流速度 × 顾问产能 × 现金周转 = 三速差分析
"""

import pandas as pd


# ============ 团队分类映射 ============
# Commercial 团队：市场、销售、准入（market access）
# R&D 团队：CMC 和 CO（CO 包括 RA、PV、医学 和 CO）
TEAM_CATEGORY_MAP = {
    # Commercial
    'commercial': 'Commercial',
    '市场': 'Commercial',
    'marketing': 'Commercial',
    '销售': 'Commercial',
    'sales': 'Commercial',
    '准入': 'Commercial',
    'market access': 'Commercial',
    'ma': 'Commercial',
    'ma&ga': 'Commercial',
    'ga': 'Commercial',
    'mkt': 'Commercial',
    # R&D (包括 CO、CMC、RA、PV、医学、临床等)
    'cmc': 'R&D',
    'co': 'R&D',
    'ra': 'R&D',
    'pv': 'R&D',
    '医学': 'R&D',
    'medical': 'R&D',
    '临床': 'R&D',
}


def classify_team_category(team_name: str) -> str:
    """
    根据团队名称分类为大类
    
    Returns:
        'Commercial', 'R&D', 或 'Other'
    """
    if not team_name:
        return 'Other'
    
    team_lower = team_name.lower().strip()
    
    # 直接匹配
    if team_lower in TEAM_CATEGORY_MAP:
        return TEAM_CATEGORY_MAP[team_lower]
    
    # 关键词匹配
    for keyword, category in TEAM_CATEGORY_MAP.items():
        if keyword in team_lower:
            return category
    
    return 'Other'
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
from real_finance import (
    RealCostRecord,
    calculate_position_real_costs,
    get_consultant_real_costs,
    calculate_monthly_real_summary,
)


@dataclass
class PositionLifecycle:
    """职位全生命周期跟踪 - 速度差分析的核心"""
    position_id: str
    client_name: str
    position_name: str
    consultant: str
    team: str = ""
    
    # 关键时间节点（用于计算速度）
    created_date: datetime = None  # 职位发布日期
    signed_date: Optional[datetime] = None  # 签约日期
    first_candidate_date: Optional[datetime] = None  # 首次推荐日期
    first_interview_date: Optional[datetime] = None  # 首次面试日期
    offer_date: Optional[datetime] = None  # Offer日期
    onboard_date: Optional[datetime] = None  # 入职日期
    payment_date: Optional[datetime] = None  # 回款日期
    closed_date: Optional[datetime] = None  # 结案日期
    
    # 财务数据
    annual_salary: float = 0  # 年薪
    fee_rate: float = 20  # 费率%
    fee_amount: float = 0  # 佣金总额
    actual_payment: float = 0  # 实际回款
    
    # 成本数据（单职位成本核算）- 不再依赖工时
    sourcing_cost: float = 0  # sourcing成本（广告、渠道等）
    interview_cost: float = 0  # 面试成本（差旅、会议室等）
    other_direct_cost: float = 0  # 其他直接成本
    
    # 成本计算方式（可选）
    cost_calculation_mode: str = "auto"  # auto/period/commission_rate/manual
    
    # 状态
    status: str = "进行中"  # 进行中/已关闭/已暂停
    is_successful: bool = False  # 是否成功成单
    payment_status: str = ""  # 回款状态：已回款/未回款/已开票等
    
    # 客户账期（天数）- 用于计算预期回款日期
    client_payment_cycle: Optional[int] = None  # 如果为空，使用系统默认值
    
    @property
    def cycle_days(self) -> int:
        """职位生命周期总天数"""
        if self.closed_date and self.created_date:
            return (self.closed_date - self.created_date).days
        elif self.created_date:
            return (datetime.now() - self.created_date).days
        return 0
    
    @property
    def to_offer_days(self) -> Optional[int]:
        """从发布到offer的天数（转化速度）"""
        if self.offer_date and self.created_date:
            return (self.offer_date - self.created_date).days
        return None
    
    @property
    def to_payment_days(self) -> Optional[int]:
        """从入职到回款的天数（现金回收速度）"""
        if self.payment_date and self.onboard_date:
            return (self.payment_date - self.onboard_date).days
        return None
    
    @property
    def gross_revenue(self) -> float:
        """毛收入 = 实际回款"""
        return self.actual_payment
    
    def get_direct_cost(self, config: Dict = None, consultant_configs: Dict = None) -> float:
        """
        计算直接成本 - 支持多种计算方式（不依赖工时）
        
        方式1: monthly_salary_multiplier - 月工资×倍数法（推荐，符合内部核算）
        方式2: period - 基于周期天数 × 日均顾问成本
        方式3: commission_rate - 基于佣金比例
        方式4: manual - 仅使用录入的成本数据
        方式5: auto - 智能组合
        
        如果提供了 consultant_configs，会根据顾问姓名自动获取其工资配置
        """
        if config is None:
            config = {}
        
        # 基础成本（可明确统计的：广告、面试等）
        base_cost = self.sourcing_cost + self.interview_cost + self.other_direct_cost
        
        mode = self.cost_calculation_mode or config.get('cost_calculation_mode', 'monthly_salary_multiplier')
        
        # 获取顾问专属配置（如果提供了 consultant_configs）
        consultant_config = None
        if consultant_configs and self.consultant in consultant_configs:
            consultant_config = consultant_configs[self.consultant]
        
        if mode == 'manual':
            # 仅使用录入的数据
            return base_cost
        
        elif mode == 'monthly_salary_multiplier':
            # 月工资×倍数法（符合内部核算：工资×3 = 工资+社保+固定/运营均摊+奖金）
            
            # 优先使用顾问专属配置
            if consultant_config:
                monthly_salary = consultant_config.get('monthly_salary', 15000)
                avg_positions = consultant_config.get('avg_positions', 6)
            else:
                monthly_salary = config.get('consultant_monthly_salary', 15000)
                avg_positions = config.get('avg_positions_per_consultant', 6)
            
            multiplier = config.get('salary_multiplier', 3.0)
            
            # 计算该职位占用的时间比例（按周期天数）
            days = self.cycle_days if self.cycle_days > 0 else 30  # 默认30天
            
            # 该职位的成本 = 月成本 × 倍数 × 占用月数 / 同时在操作职位数
            monthly_total_cost = monthly_salary * multiplier
            position_cost = monthly_total_cost * (days / 30) / avg_positions
            
            return position_cost + base_cost
        
        elif mode == 'commission_rate':
            # 基于佣金比例
            rate = config.get('commission_cost_rate', 0.30)
            return self.fee_amount * rate + base_cost
        
        elif mode == 'period':
            # 基于周期天数 × 日均成本
            daily_cost = config.get('daily_consultant_cost', 500)
            period_cost = self.cycle_days * daily_cost
            return period_cost + base_cost
        
        else:  # auto - 智能组合
            # 如果有回款，使用佣金比例法；否则使用月工资倍数法
            if self.actual_payment > 0:
                rate = config.get('commission_cost_rate', 0.30)
                consultant_cost = self.fee_amount * rate
            else:
                # 未回款职位，使用月工资倍数法
                if consultant_config:
                    monthly_salary = consultant_config.get('monthly_salary', 15000)
                    avg_positions = consultant_config.get('avg_positions', 6)
                else:
                    monthly_salary = config.get('consultant_monthly_salary', 15000)
                    avg_positions = config.get('avg_positions_per_consultant', 6)
                
                multiplier = config.get('salary_multiplier', 3.0)
                days = self.cycle_days if self.cycle_days > 0 else 30
                monthly_total_cost = monthly_salary * multiplier
                consultant_cost = monthly_total_cost * (days / 30) / avg_positions
            
            return consultant_cost + base_cost
    
    @property
    def direct_cost(self) -> float:
        """直接成本（使用默认配置）"""
        return self.get_direct_cost()
    
    @property
    def marginal_contribution(self) -> float:
        """边际贡献 = 毛收入 - 直接成本"""
        return self.gross_revenue - self.direct_cost
    
    @property
    def mc_per_day(self) -> float:
        """日均边际贡献 = 边际贡献 / 周期天数"""
        days = self.cycle_days
        if days > 0:
            return self.marginal_contribution / days
        return 0
    
    @property
    def current_stage(self) -> str:
        """当前阶段"""
        if self.payment_date:
            return "已回款"
        elif self.onboard_date:
            return "已入职待回款"
        elif self.offer_date:
            return "已发offer"
        elif self.first_interview_date:
            return "面试中"
        elif self.first_candidate_date:
            return "推荐中"
        elif self.signed_date:
            return "已签约"
        return "新建"


# Forecast阶段成功率映射（来自ForecastAssignment）
FORECAST_STAGE_SUCCESS_RATE = {
    '简历推荐': 10,
    '推荐简历': 10,
    '客户一面': 25,
    '客户1面': 25,
    '客户二面': 35,
    '客户2面': 35,
    '客户三面': 40,
    '客户3面': 40,
    '终面': 50,
    '客户终面': 50,
    'offer谈判': 80,
    'offer': 80,
    '待发offer': 85,
    '已发offer': 90,
    '入职': 100,
    '已入职': 100,
}


@dataclass
class ForecastPosition:
    """预测/在途单 - 用于未来收入预测和投入决策"""
    forecast_id: str
    client_name: str
    position_name: str
    consultant: str
    team: str = ""
    
    # 预计财务数据
    estimated_salary: float = 0  # 预计年薪
    fee_rate: float = 20  # 费率%
    estimated_fee: float = 0  # 预计佣金
    
    # 阶段与成功率
    stage: str = ""  # 当前阶段
    success_rate: float = 0  # 成功率（%）
    
    # 时间
    start_date: datetime = None  # 开始日期
    expected_close_date: datetime = None  # 预计成交日期
    expected_payment_date: Optional[datetime] = None  # 预计回款日期（基于历史回款周期推算）
    
    # 已投入成本（实际发生）
    sourcing_cost: float = 0  # 已投入sourcing成本
    interview_cost: float = 0  # 已投入面试成本
    
    # 成本计算配置
    consultant_monthly_salary: float = 15000  # 顾问月基本工资
    salary_multiplier: float = 3.0  # 成本倍数（工资×3）
    avg_positions_per_consultant: int = 6  # 同时在操作职位数
    
    note: str = ""  # 备注
    
    @property
    def weighted_revenue(self) -> float:
        """加权预测收入 = 预计佣金 × 成功率"""
        return self.estimated_fee * (self.success_rate / 100)
    
    @property
    def cycle_days(self) -> int:
        """已进行天数"""
        if self.start_date:
            return (datetime.now() - self.start_date).days
        return 0
    
    @property
    def accumulated_cost(self) -> float:
        """已累计投入成本 = 实际投入 + 顾问时间成本"""
        # 基础成本
        base_cost = self.sourcing_cost + self.interview_cost
        
        # 顾问时间成本（按月工资倍数法）
        if self.start_date:
            monthly_total_cost = self.consultant_monthly_salary * self.salary_multiplier
            days = self.cycle_days
            position_cost = monthly_total_cost * (days / 30) / self.avg_positions_per_consultant
            return base_cost + position_cost
        
        return base_cost
    
    @property
    def expected_marginal_contribution(self) -> float:
        """预期边际贡献 = 加权预测收入 - 已累计成本"""
        return self.weighted_revenue - self.accumulated_cost
    
    @property
    def roi_ratio(self) -> float:
        """投资回报率 = 预期MC / 已投入成本"""
        if self.accumulated_cost > 0:
            return self.expected_marginal_contribution / self.accumulated_cost
        return 0
    
    @property
    def is_viable(self) -> bool:
        """是否值得继续投入（预期MC为正）"""
        return self.expected_marginal_contribution > 0
    
    @classmethod
    def get_stage_success_rate(cls, stage: str) -> float:
        """根据阶段名称获取默认成功率"""
        if not stage:
            return 10  # 默认10%
        
        # 精确匹配
        if stage in FORECAST_STAGE_SUCCESS_RATE:
            return FORECAST_STAGE_SUCCESS_RATE[stage]
        
        # 模糊匹配
        for key, rate in FORECAST_STAGE_SUCCESS_RATE.items():
            if key in stage or stage in key:
                return rate
        
        return 10  # 默认10%


@dataclass
class CashFlowEvent:
    """现金流事件 - 用于现金流日历"""
    event_id: str
    event_date: datetime
    event_type: str  # 流入/流出
    category: str  # 回款/工资/租金/营销/其他
    amount: float
    related_position_id: Optional[str] = None
    related_consultant: Optional[str] = None
    description: str = ""
    probability: float = 100  # 概率（用于预测）
    
    @property
    def expected_amount(self) -> float:
        """预期金额 = 金额 × 概率"""
        return self.amount * (self.probability / 100)


@dataclass
class ConsultantVelocity:
    """顾问产能速度指标"""
    consultant_name: str
    team: str = ""
    team_category: str = ""  # 团队大类：Commercial / R&D / Other
    
    # 职位处理能力
    active_positions: int = 0  # 在操作职位数
    max_capacity: int = 8  # 最大容量（可配置）
    
    # 转化速度
    avg_offer_cycle: float = 0  # 平均成单周期（天）
    avg_payment_cycle: float = 0  # 平均回款周期（天）
    
    # 产出效率
    positions_per_month: float = 0  # 月均操作职位数
    offers_per_month: float = 0  # 月均offer数
    deals_per_month: float = 0  # 月均成单数
    
    # 财务效率
    revenue_per_month: float = 0  # 月均产出
    mc_per_month: float = 0  # 月均边际贡献
    
    @property
    def capacity_utilization(self) -> float:
        """产能利用率"""
        if self.max_capacity > 0:
            return (self.active_positions / self.max_capacity) * 100
        return 0
    
    @property
    def velocity_score(self) -> float:
        """速度综合评分（0-100）"""
        # 基于周期、产出、利用率的综合评分
        cycle_score = max(0, 100 - self.avg_offer_cycle) if self.avg_offer_cycle else 50
        output_score = min(100, self.deals_per_month * 20)  # 每月5单=100分
        util_score = min(100, self.capacity_utilization * 1.25)  # 80%利用率=100分
        return (cycle_score * 0.4 + output_score * 0.4 + util_score * 0.2)


class AdvancedRecruitmentAnalyzer:
    """进阶财务分析器 - 三速差分析"""
    
    def __init__(self):
        self.positions: List[PositionLifecycle] = []  # 实际职位（已成单/已关闭）
        self.forecast_positions: List[ForecastPosition] = []  # 预测职位（在途单）
        self.cashflow_events: List[CashFlowEvent] = []
        self.consultant_configs: Dict[str, dict] = {}  # 顾问配置（从Excel加载）
        self.consultant_db_info: Dict[str, dict] = {}  # 顾问数据库信息（从user表加载，含入职/离职日期）
        self.real_cost_records: List[RealCostRecord] = []  # 财务状况成本记录
        self.overdue_from_invoices: float = 0  # 基于invoice表的逾期未回款金额
        
        # 配置参数
        self.config = {
            # 成本计算配置（支持多种方式）
            'cost_calculation_mode': 'monthly_salary_multiplier',  # monthly_salary_multiplier/period/commission_rate/manual
            
            # 方式1: 月工资倍数法（推荐，符合内部核算）
            'consultant_monthly_salary': 15000,  # 顾问月基本工资
            'salary_multiplier': 3.0,  # 倍数（工资×3 = 工资+社保+固定成本+运营+奖金）
            
            # 方式2: 周期天数法
            'daily_consultant_cost': 500,  # 日均顾问成本（元/天）
            
            # 方式3: 佣金比例法
            'commission_cost_rate': 0.30,  # 佣金成本比例
            
            # 固定费用配置
            'fixed_monthly_expense': 50000,  # 月度固定费用
            
            # 预警配置
            'cash_warning_months': 5,  # 现金流预警月数（红线 = 5个月储备金）
            'mc_warning_threshold': 0,  # 边际贡献预警阈值
            
            # 财务状况分析模式开关
            'use_real_costs': False,  # False=假设模式(3倍工资), True=财务状况分析模式
        }
    
    def add_position(self, position: PositionLifecycle):
        """添加职位记录"""
        self.positions.append(position)
    
    def add_cashflow_event(self, event: CashFlowEvent):
        """添加现金流事件"""
        self.cashflow_events.append(event)
    
    def load_consultant_db_info(self, users_df: pd.DataFrame):
        """
        从数据库user表加载顾问信息
        
        Args:
            users_df: 包含id, englishName, chineseName, status, joinInDate, leaveDate的DataFrame
        """
        self.consultant_db_info = {}
        for _, row in users_df.iterrows():
            name = f"{row.get('englishName', '') or ''} {row.get('chineseName', '') or ''}".strip()
            if not name:
                continue
            
            # 解析日期
            join_date = None
            leave_date = None
            try:
                if pd.notna(row.get('joinInDate')):
                    join_date = pd.to_datetime(row['joinInDate'])
                if pd.notna(row.get('leaveDate')):
                    leave_date = pd.to_datetime(row['leaveDate'])
            except:
                pass
            
            self.consultant_db_info[name] = {
                'id': row.get('id'),
                'status': row.get('status', ''),
                'join_date': join_date,
                'leave_date': leave_date,
                'english_name': row.get('englishName', ''),
                'chinese_name': row.get('chineseName', ''),
            }
    
    def _get_db_status(self, consultant_name: str) -> tuple:
        """
        从数据库获取顾问状态
        
        Returns:
            (status_code, status_label, join_date, leave_date)
            status_code: 2=在职, 1=已离职, 0=未配置
        """
        if not self.consultant_db_info:
            return None, None, None, None
        
        # 精确匹配
        if consultant_name in self.consultant_db_info:
            info = self.consultant_db_info[consultant_name]
            status = info.get('status', '')
            if status == 'Active':
                return 2, '在职', info.get('join_date'), info.get('leave_date')
            elif status == 'Leave':
                return 1, '已离职', info.get('join_date'), info.get('leave_date')
            else:
                return 1, '已离职', info.get('join_date'), info.get('leave_date')
        
        # 模糊匹配：支持中英文部分匹配（处理名字差异，如"芃"vs"梵"）
        for db_name, info in self.consultant_db_info.items():
            if (db_name == consultant_name or 
                db_name in consultant_name or 
                consultant_name in db_name):
                status = info.get('status', '')
                if status == 'Active':
                    return 2, '在职', info.get('join_date'), info.get('leave_date')
                elif status == 'Leave':
                    return 1, '已离职', info.get('join_date'), info.get('leave_date')
                else:
                    return 1, '已离职', info.get('join_date'), info.get('leave_date')
        
        # 英文名匹配：如果配置表名字和数据库名字的英文部分相同（处理中文名差异）
        # 提取 consultant_name 中的英文单词
        import re
        consultant_en_words = set(re.findall(r'[A-Za-z]+', consultant_name.lower()))
        if consultant_en_words:
            for db_name, info in self.consultant_db_info.items():
                db_en_words = set(re.findall(r'[A-Za-z]+', db_name.lower()))
                # 如果英文单词完全匹配（如 Leslie + Yang），认为是同一个人
                if consultant_en_words == db_en_words and len(consultant_en_words) >= 2:
                    status = info.get('status', '')
                    if status == 'Active':
                        return 2, '在职', info.get('join_date'), info.get('leave_date')
                    elif status == 'Leave':
                        return 1, '已离职', info.get('join_date'), info.get('leave_date')
                    else:
                        return 1, '已离职', info.get('join_date'), info.get('leave_date')
        
        return None, None, None, None
    
    def load_positions_from_dataframe(self, df: pd.DataFrame, clear_existing: bool = True):
        """
        从DataFrame加载职位数据
        支持两种格式：
        1. 完整生命周期数据（有created_date, offer_date等）
        2. 简化成单数据（基础版格式，有deal_date, fee_amount等）
        
        Args:
            df: 职位数据DataFrame
            clear_existing: 是否清空现有数据（默认True，防止重复叠加）
        """
        # 清空现有数据，防止重复叠加
        if clear_existing:
            self.positions = []
        
        for idx, row in df.iterrows():
            try:
                # 职位ID - 支持多种列名
                position_id = f'P{idx+1:04d}'
                for col in ['position_id', '职位ID', '职位编号', 'deal_id', '成单编号', '编号', 'id']:
                    if col in row and pd.notna(row[col]):
                        position_id = str(row[col]).strip()
                        break
                
                # 客户名称
                client_name = ''
                for col in ['client_name', '客户', '客户名称']:
                    if col in row and pd.notna(row[col]):
                        client_name = str(row[col]).strip()
                        break
                
                # 职位名称 - 支持candidate_name作为备选
                position_name = ''
                for col in ['position_name', '职位', '职位名称', '岗位', 'position']:
                    if col in row and pd.notna(row[col]):
                        position_name = str(row[col]).strip()
                        break
                # 如果没有职位名称，尝试用候选人名称
                if not position_name:
                    for col in ['candidate_name', '候选人', '姓名']:
                        if col in row and pd.notna(row[col]):
                            position_name = str(row[col]).strip()
                            break
                
                # 顾问
                consultant = ''
                for col in ['consultant', '顾问', '负责顾问', '用户']:
                    if col in row and pd.notna(row[col]):
                        consultant = str(row[col]).strip()
                        break
                
                # 团队
                team = ''
                for col in ['team', '团队', '部门']:
                    if col in row and pd.notna(row[col]):
                        team = str(row[col]).strip()
                        break
                
                # 日期解析函数
                def parse_date(row, cols):
                    for col in cols:
                        if col in row and pd.notna(row[col]):
                            try:
                                val = pd.to_datetime(row[col])
                                if pd.notna(val):
                                    return val
                            except:
                                continue
                    return None
                
                # 优先使用created_date，如果没有则用deal_date
                created_date = parse_date(row, ['created_date', '发布日期', '开始日期', '添加日期', 'deal_date', '成单日期', '日期'])
                
                # 成单数据通常只有这些日期
                deal_date = parse_date(row, ['deal_date', 'Deal_date', '成单日期', '日期'])
                payment_date = parse_date(row, ['payment_date', '回款日期', '实际回款日期'])
                
                # 详细生命周期日期（可选）
                signed_date = parse_date(row, ['signed_date', '签约日期'])
                first_candidate_date = parse_date(row, ['first_candidate_date', '首次推荐日期'])
                first_interview_date = parse_date(row, ['first_interview_date', '首次面试日期'])
                offer_date = parse_date(row, ['offer_date', 'offer日期', 'Offer日期'])
                onboard_date = parse_date(row, ['onboard_date', '入职日期'])
                closed_date = parse_date(row, ['closed_date', '结案日期'])
                
                # 如果没有created_date但有deal_date，用deal_date作为created_date
                if not created_date and deal_date:
                    created_date = deal_date
                
                # 如果 deal_date 存在但没有 offer_date，将 deal_date 作为 offer_date
                # （因为用户说 Deal_date 就是 Offer 日期）
                if deal_date and not offer_date:
                    offer_date = deal_date
                
                # 财务数据 - 支持基础版成单数据格式
                # 年薪
                annual_salary = 0.0
                for col in ['annual_salary', '年薪', '收费基数']:
                    if col in row and pd.notna(row[col]):
                        val = pd.to_numeric(row[col], errors='coerce')
                        if pd.notna(val):
                            annual_salary = float(val)
                            break
                
                # 费率
                fee_rate = 20.0
                for col in ['fee_rate', '费率']:
                    if col in row and pd.notna(row[col]):
                        val = pd.to_numeric(row[col], errors='coerce')
                        if pd.notna(val):
                            fee_rate = float(val)
                            if fee_rate < 1:  # 小数转百分比
                                fee_rate = fee_rate * 100
                            break
                
                # 佣金金额 - 基础版是fee_amount/佣金/佣金金额
                fee_amount = 0.0
                for col in ['fee_amount', '佣金', '佣金金额', 'fee']:
                    if col in row and pd.notna(row[col]):
                        val = pd.to_numeric(row[col], errors='coerce')
                        if pd.notna(val):
                            fee_amount = float(val)
                            break
                
                # 如果没有佣金但有年薪和费率，计算佣金
                if fee_amount == 0 and annual_salary > 0 and fee_rate > 0:
                    fee_amount = annual_salary * fee_rate / 100
                
                # 实际回款 - 基础版是actual_payment/实际回款/回款
                actual_payment = 0.0
                for col in ['actual_payment', '实际回款', '回款', 'collected']:
                    if col in row and pd.notna(row[col]):
                        val = pd.to_numeric(row[col], errors='coerce')
                        if pd.notna(val):
                            actual_payment = float(val)
                            break
                
                # 回款状态字段 - 用于判断是否已回款
                payment_status = ""
                for col in ['payment_status', '回款状态', '回款情况']:
                    if col in row and pd.notna(row[col]):
                        payment_status = str(row[col]).strip()
                        break
                
                # 状态判断：
                # 1. 如果有payment_status字段，以它为准（已回款=成功，未回款/已开票=已成单但未回款）
                # 2. 如果没有，按fallback：actual_payment>0或fee_amount>0视为成功
                if payment_status:
                    is_successful = fee_amount > 0  # 只要有佣金金额就视为成单
                    is_paid = payment_status in ['已回款', '回款完成', 'paid']
                else:
                    is_successful = actual_payment > 0 or fee_amount > 0
                    is_paid = actual_payment > 0
                
                status = "已关闭" if is_successful else "进行中"
                # 成本数据（可选，简化版成单数据可能没有）
                sourcing_cost = 0.0
                for col in ['sourcing_cost', 'sourcing成本', '渠道成本', '广告成本']:
                    if col in row and pd.notna(row[col]):
                        val = pd.to_numeric(row[col], errors='coerce')
                        if pd.notna(val):
                            sourcing_cost = float(val)
                            break
                
                interview_cost = 0.0
                for col in ['interview_cost', '面试成本', '差旅成本']:
                    if col in row and pd.notna(row[col]):
                        val = pd.to_numeric(row[col], errors='coerce')
                        if pd.notna(val):
                            interview_cost = float(val)
                            break
                
                other_direct_cost = 0.0
                for col in ['other_direct_cost', '其他直接成本', '直接成本']:
                    if col in row and pd.notna(row[col]):
                        val = pd.to_numeric(row[col], errors='coerce')
                        if pd.notna(val):
                            other_direct_cost = float(val)
                            break
                
                # 成本计算方式（可选）
                cost_mode = 'auto'
                for col in ['cost_calculation_mode', '成本计算方式']:
                    if col in row and pd.notna(row[col]):
                        val = str(row[col]).strip().lower()
                        if val in ['auto', 'period', 'commission_rate', 'manual', 'monthly_salary_multiplier']:
                            cost_mode = val
                            break
                
                # 客户账期（可选，用于单独设置该客户的回款周期）
                client_payment_cycle = None
                for col in ['client_payment_cycle', '客户账期', '账期天数']:
                    if col in row and pd.notna(row[col]):
                        val = pd.to_numeric(row[col], errors='coerce')
                        if pd.notna(val):
                            client_payment_cycle = int(val)
                            break
                
                position = PositionLifecycle(
                    position_id=position_id,
                    client_name=client_name,
                    position_name=position_name,
                    consultant=consultant,
                    team=team,
                    created_date=created_date or datetime.now(),
                    signed_date=signed_date,
                    first_candidate_date=first_candidate_date,
                    first_interview_date=first_interview_date,
                    offer_date=offer_date,
                    onboard_date=onboard_date,
                    payment_date=payment_date,
                    closed_date=closed_date,
                    annual_salary=annual_salary,
                    fee_rate=fee_rate,
                    fee_amount=fee_amount,
                    actual_payment=actual_payment,
                    sourcing_cost=sourcing_cost,
                    interview_cost=interview_cost,
                    other_direct_cost=other_direct_cost,
                    cost_calculation_mode=cost_mode,
                    status=status,
                    is_successful=is_successful,
                    payment_status=payment_status if payment_status else ('已回款' if is_paid else ''),
                    client_payment_cycle=client_payment_cycle
                )
                self.add_position(position)
            except Exception as e:
                print(f"处理职位第 {idx} 行时出错: {e}")
                continue
    
    def add_forecast(self, forecast: ForecastPosition):
        """添加预测职位记录"""
        self.forecast_positions.append(forecast)
    
    # 行业经验值：从 Offer 到入职的平均周期
    AVG_OFFER_TO_ONBOARD_DAYS = 30
    
    def get_historical_payment_cycle(self) -> int:
        """
        基于历史成单数据计算平均账期（从入职到回款的天数）
        这是纯粹的账期，不包含Offer到入职的时间
        """
        cycles = []
        for p in self.positions:
            if pd.notna(p.payment_date) and pd.notna(p.onboard_date):
                # 只计算入职到回款的周期（账期）
                cycles.append((p.payment_date - p.onboard_date).days)
        if cycles:
            mean_cycle = np.mean(cycles)
            if not np.isnan(mean_cycle):
                return int(mean_cycle)
        return 60  # 默认60天账期
    
    def get_historical_offer_to_payment_cycle(self) -> int:
        """
        获取从 Offer 到回款的完整周期
        = 30天(入职周期) + 平均账期
        """
        return self.AVG_OFFER_TO_ONBOARD_DAYS + self.get_historical_payment_cycle()
    
    def get_position_payment_cycle(self, position: PositionLifecycle) -> int:
        """
        获取单个职位的账期天数
        优先使用职位设置的客户账期，否则使用系统默认账期
        """
        if position.client_payment_cycle is not None:
            return position.client_payment_cycle
        return self.get_historical_payment_cycle()
    
    def estimate_monthly_cost(self) -> float:
        """估算公司月度总成本（基于顾问3倍工资法 或 财务数据）- 只计算在职顾问"""
        # 如果启用了财务状况分析模式且有成本记录，使用真实数据估算月均成本
        if self.config.get('use_real_costs', False) and self.real_cost_records:
            today = datetime.now()
            # 取最近3个月的真实成本平均值作为月度估算
            months_back = 3
            start_month = datetime(today.year, today.month, 1)
            for _ in range(months_back):
                if start_month.month == 1:
                    start_month = datetime(start_month.year - 1, 12, 1)
                else:
                    start_month = datetime(start_month.year, start_month.month - 1, 1)
            
            total_real = 0.0
            count = 0
            current = start_month
            while current <= datetime(today.year, today.month, 1):
                summary = calculate_monthly_real_summary((current.year, current.month), self.real_cost_records)
                total_real += summary['total']
                count += 1
                if current.month == 12:
                    current = datetime(current.year + 1, 1, 1)
                else:
                    current = datetime(current.year, current.month + 1, 1)
            
            avg_monthly = total_real / count if count > 0 else 0
            return avg_monthly if avg_monthly > 0 else 1
        
        # 原有假设模式逻辑 - 优先使用数据库状态判断在职
        if self.consultant_configs:
            total = 0
            for name, config in self.consultant_configs.items():
                # 优先从数据库获取状态（更准确）
                db_status = self._get_db_status(name)
                if db_status and db_status[0] is not None:
                    # db_status = (status_code, status_label, join_date, leave_date)
                    status_code = db_status[0]
                    # 只计算在职顾问（状态码=2）
                    if status_code == 2:
                        total += config.get('monthly_salary', 15000) * config.get('salary_multiplier', 3.0)
                else:
                    # 回退到Excel配置
                    if config.get('is_active', True):
                        total += config.get('monthly_salary', 15000) * config.get('salary_multiplier', 3.0)
            return total if total > 0 else 1  # 避免返回0
        
        # 如果没有顾问配置，从职位数据中推断顾问人数
        consultants = set(p.consultant for p in self.positions if p.consultant)
        consultant_count = len(consultants) if consultants else 1
        monthly_salary = self.config.get('consultant_monthly_salary', 15000)
        multiplier = self.config.get('salary_multiplier', 3.0)
        return consultant_count * monthly_salary * multiplier
    
    @staticmethod
    def _calc_consultant_active_months(join_date: Optional[datetime], leave_date: Optional[datetime],
                                       period_start: datetime, period_end: datetime) -> float:
        """
        计算顾问在指定周期内的在岗月数
        规则：每个自然月内，实际在岗天数 >15 天按1个月，<=15 天按0.5个月
        """
        if not join_date:
            join_date = period_start
        if not leave_date:
            leave_date = period_end
        
        actual_start = max(join_date, period_start)
        actual_end = min(leave_date, period_end)
        if actual_start > actual_end:
            return 0.0
        
        months = 0.0
        current = datetime(actual_start.year, actual_start.month, 1)
        end = datetime(actual_end.year, actual_end.month, 1)
        
        while current <= end:
            year, month = current.year, current.month
            month_start = datetime(year, month, 1)
            if month == 12:
                month_end = datetime(year + 1, 1, 1) - timedelta(days=1)
            else:
                month_end = datetime(year, month + 1, 1) - timedelta(days=1)
            
            overlap_start = max(actual_start, month_start)
            overlap_end = min(actual_end, month_end)
            days = (overlap_end - overlap_start).days + 1
            
            if days > 15:
                months += 1.0
            else:
                months += 0.5
            
            if month == 12:
                current = datetime(year + 1, 1, 1)
            else:
                current = datetime(year, month + 1, 1)
        
        return months
    
    def _build_consultant_name_map(self) -> Dict[str, str]:
        """从 positions 的 consultant 字段提取英文名<->中文名映射"""
        name_map = {}
        for p in self.positions:
            if not p.consultant:
                continue
            parts = p.consultant.split()
            if len(parts) >= 3:
                english_name = parts[0] + ' ' + parts[1]
                chinese_name = ' '.join(parts[2:])
                name_map[english_name] = chinese_name
                name_map[chinese_name] = english_name
        return name_map
    
    def get_period_assumed_cost(self, period_start: datetime, period_end: datetime) -> Dict:
        """
        计算指定周期内的假设人力成本（基于顾问3倍工资法）
        根据 join_date / leave_date 精确计算在岗月数：
          - 超过15天按1个月
          - 15天及以下按0.5个月
        对于缺少精确日期的顾问，优先用真实工资记录反推在岗月份（有工资记录的月份视为在岗1个月）。
        """
        total = 0.0
        details = []
        name_map = self._build_consultant_name_map()
        
        # 用于去重：只处理原始英文名 key（避免中文别名重复计算）
        processed_names = set()
        
        for name, config in list(self.consultant_configs.items()):
            # 跳过中文别名 key（通过映射找到原始英文名）
            if name in processed_names:
                continue
            original_name = name_map.get(name, name)
            if original_name in processed_names:
                continue
            processed_names.add(original_name)
            
            # 获取原始配置
            cfg = self.consultant_configs.get(original_name, config)
            
            # 优先从数据库获取入职/离职日期（更准确）
            db_status = self._get_db_status(original_name)
            if db_status and db_status[0] is not None:
                join_date = db_status[2]  # db_join_date
                leave_date = db_status[3]  # db_leave_date
            else:
                join_date = cfg.get('join_date')
                leave_date = cfg.get('leave_date')
            
            # 查找该顾问在周期内的真实工资记录（匹配英文名或中文名）
            chinese_name = name_map.get(original_name)
            salary_records = [
                r for r in self.real_cost_records
                if r.category == 'salary' and r.consultant
                and (r.consultant == original_name or r.consultant == chinese_name)
                and period_start <= r.date <= period_end
            ]
            
            months = 0.0
            if join_date or leave_date:
                # 有精确日期，按日期规则计算
                months = self._calc_consultant_active_months(join_date, leave_date, period_start, period_end)
            elif salary_records:
                # 没有日期，但有工资记录：按有工资的月份数估算
                months_set = set((r.date.year, r.date.month) for r in salary_records)
                months = float(len(months_set))
            else:
                # 既无日期也无工资记录：按 is_active 判断
                if cfg.get('is_active', True):
                    months = self._calc_consultant_active_months(None, None, period_start, period_end)
            
            # 如果没有 leave_date，优先用 salary 记录修正（防止离职但无日期时高估）
            if not leave_date:
                if salary_records:
                    months_from_salary = float(len(set((r.date.year, r.date.month) for r in salary_records)))
                    months = min(months, months_from_salary)
                elif not cfg.get('is_active', True):
                    # inactive 且既无 leave_date 也无 salary 记录 = 视为已不在岗
                    months = 0.0
            
            if months > 0:
                monthly_salary = cfg.get('monthly_salary', 15000)
                multiplier = cfg.get('salary_multiplier', 3.0)
                cost = monthly_salary * multiplier * months
                total += cost
                details.append({
                    '顾问': original_name,
                    '月薪': monthly_salary,
                    '倍数': multiplier,
                    '在岗月数': months,
                    '假设成本': cost,
                })
        
        return {
            'total': total,
            'details': details,
        }
    
    def get_cash_safety_analysis(self, current_balance: float = 0) -> Dict:
        """
        现金流安全分析 - 核心简化指标
        
        Args:
            current_balance: 当前实际现金余额（如180万，已扣除已消耗的已回款）
        """
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        current_year = today.year
        
        # 1. 月度总成本
        monthly_cost = self.estimate_monthly_cost()
        
        # 2. 已回款总额（本年度已实际到账，用于利润核算）
        collected_revenue = sum(
            p.actual_payment for p in self.positions
            if p.payment_date and p.payment_date.year == current_year and p.payment_date <= today
        )
        # Fallback：使用 consultant_collections（从 invoiceassignment 获取的顾问回款总和）
        if hasattr(self, 'consultant_collections') and self.consultant_collections:
            cc_total = sum(d.get('total_received', 0) for d in self.consultant_collections.values())
            if cc_total > collected_revenue:
                collected_revenue = cc_total
        
        # 3. 未来90天/180天即将到账的已确认回款
        # 包括：已填写payment_date的回款 + 已成单但未填写payment_date的（根据offer推算）
        avg_payment_cycle = self.get_historical_payment_cycle()
        offer_to_payment_days = self.AVG_OFFER_TO_ONBOARD_DAYS + avg_payment_cycle
        
        future_90d_collected = 0
        future_91_180d_collected = 0
        overdue_collected = 0  # 已逾期的回款
        
        for p in self.positions:
            # 确定预期回款金额：已回款的用actual_payment，未回款的用fee_amount
            if p.payment_date and p.payment_date >= today:
                # 已填写未来回款日期的，用actual_payment
                expected_amount = p.actual_payment
            elif not p.payment_date and p.fee_amount > 0:
                # 未填写回款日期的，用fee_amount作为预期
                expected_amount = p.fee_amount
            else:
                continue  # 没有可预测的回款金额
            
            if p.payment_date and p.payment_date >= today:
                # 已填写回款日期的
                if today <= p.payment_date <= today + timedelta(days=90):
                    future_90d_collected += expected_amount
                elif today + timedelta(days=90) < p.payment_date <= today + timedelta(days=180):
                    future_91_180d_collected += expected_amount
            elif not p.payment_date and p.offer_date:
                # 未填写回款日期，但有offer_date的，推算回款日期
                # 使用职位级别的账期（如果有设置）
                payment_cycle = self.get_position_payment_cycle(p)
                offer_to_payment_days = self.AVG_OFFER_TO_ONBOARD_DAYS + payment_cycle
                estimated_payment_date = p.offer_date + timedelta(days=offer_to_payment_days)
                days_until = (estimated_payment_date - today).days
                
                if days_until < 0:
                    # 已逾期 —— 如果已从invoice表获取真实逾期金额，这里不再重复累加
                    # 否则使用推算值作为fallback
                    pass  # 见下方：优先使用invoice真实数据
                elif days_until <= 90:
                    future_90d_collected += expected_amount
                elif days_until <= 180:
                    future_91_180d_collected += expected_amount
        
        # 优先使用基于invoice表的真实逾期金额（数据库同步时获取）
        # 这比基于Offer日期的推算更准确
        if hasattr(self, 'overdue_from_invoices') and self.overdue_from_invoices > 0:
            overdue_collected = self.overdue_from_invoices
        else:
            # Fallback：没有invoice数据时，使用offer日期推算（但会高估逾期金额）
            for p in self.positions:
                if p.payment_date or not p.offer_date or p.fee_amount <= 0:
                    continue
                payment_cycle = self.get_position_payment_cycle(p)
                offer_to_payment_days = self.AVG_OFFER_TO_ONBOARD_DAYS + payment_cycle
                estimated_payment_date = p.offer_date + timedelta(days=offer_to_payment_days)
                days_until = (estimated_payment_date - today).days
                if days_until < 0:
                    overdue_collected += p.fee_amount
        
        # 180天回款 = 90天内回款 + 91-180天回款（财务恒等式一致性）
        future_180d_collected = future_90d_collected + future_91_180d_collected
        
        # 4. Forecast 预期回款（基于预计回款日期和成功率加权）
        # 先确保 forecast 都有 expected_payment_date
        avg_cycle = self.get_historical_payment_cycle()
        for f in self.forecast_positions:
            if f.expected_payment_date is None and f.expected_close_date:
                f.expected_payment_date = f.expected_close_date + timedelta(days=avg_cycle)
        
        forecast_90d = sum(
            f.weighted_revenue for f in self.forecast_positions
            if f.expected_payment_date and today <= f.expected_payment_date <= today + timedelta(days=90)
        )
        forecast_180d = sum(
            f.weighted_revenue for f in self.forecast_positions
            if f.expected_payment_date and today <= f.expected_payment_date <= today + timedelta(days=180)
        )
        
        # 5. 计算90天/180天预测余额
        cost_90d = monthly_cost * 3  # 90天 = 3个月成本
        cost_180d = monthly_cost * 6  # 180天 = 6个月成本
        
        # 注：current_balance 是直接传入的当前实际余额（如180万），不再自动加已回款
        
        balance_90d = current_balance + future_90d_collected + forecast_90d - cost_90d
        # 180天余额包含未来180天回款 + 已逾期待回款
        balance_180d = current_balance + future_180d_collected + forecast_180d + overdue_collected - cost_180d
        
        def _status(balance, monthly):
            red_line = 5 * monthly  # 5个月储备金红线
            if balance >= red_line:
                return '安全', '#10B981'
            elif balance >= 0:
                return '低于安全线', '#F59E0B'
            else:
                return '危险', '#EF4444'
        
        status_90d, color_90d = _status(balance_90d, monthly_cost)
        status_180d, color_180d = _status(balance_180d, monthly_cost)
        
        return {
            'current_balance': current_balance,  # 当前实际现金余额（如180万）
            'collected_revenue': collected_revenue,  # 本年已回款（用于利润核算）
            'monthly_cost': monthly_cost,
            'future_90d_collected': future_90d_collected,
            'future_180d_collected': future_180d_collected,
            'overdue_collected': overdue_collected,  # 已逾期待回款
            'forecast_90d': forecast_90d,
            'forecast_180d': forecast_180d,
            'balance_90d': balance_90d,
            'balance_180d': balance_180d,
            'status_90d': status_90d,
            'status_180d': status_180d,
            'color_90d': color_90d,
            'color_180d': color_180d,
            'runway_months': current_balance / monthly_cost if monthly_cost > 0 else 999,
            'avg_payment_cycle_days': avg_cycle,
        }
    
    def load_forecast_from_dataframe(self, df: pd.DataFrame, clear_existing: bool = True):
        """
        从DataFrame加载Forecast预测数据（支持ForecastAssignment格式）
        
        Args:
            df: Forecast数据DataFrame
            clear_existing: 是否清空现有数据（默认True，防止重复叠加）
        """
        # 清空现有数据，防止重复叠加
        if clear_existing:
            self.forecast_positions = []
        
        # 计算历史平均回款周期，用于推算 forecast 的回款日期
        avg_payment_cycle = self.get_historical_payment_cycle()
        
        for idx, row in df.iterrows():
            try:
                # 预测ID
                forecast_id = f'F{idx+1:04d}'
                for col in ['forecast_id', '预测编号', '编号', 'id']:
                    if col in row and pd.notna(row[col]):
                        forecast_id = str(row[col]).strip()
                        break
                
                # 客户名称
                client_name = ''
                for col in ['client_name', '客户', '客户名称']:
                    if col in row and pd.notna(row[col]):
                        client_name = str(row[col]).strip()
                        break
                
                # 职位名称
                position_name = ''
                for col in ['position_name', 'position', '职位', '岗位', '项目']:
                    if col in row and pd.notna(row[col]):
                        position_name = str(row[col]).strip()
                        break
                
                # 顾问（ForecastAssignment中的'用户'）
                consultant = ''
                for col in ['consultant', '顾问', '负责顾问', '用户']:
                    if col in row and pd.notna(row[col]):
                        consultant = str(row[col]).strip()
                        break
                
                # 团队
                team = ''
                for col in ['team', '团队', '部门']:
                    if col in row and pd.notna(row[col]):
                        team = str(row[col]).strip()
                        break
                
                # 预计年薪（ForecastAssignment中的'收费基数'）
                estimated_salary = 0.0
                for col in ['estimated_salary', 'charge_package', '预计年薪', '年薪', '收费基数']:
                    if col in row and pd.notna(row[col]):
                        val = pd.to_numeric(row[col], errors='coerce')
                        if pd.notna(val):
                            estimated_salary = float(val)
                            break
                
                # 费率（ForecastAssignment中的'费率'，小数格式如0.21）
                fee_rate = 20.0
                for col in ['fee_rate', '费率']:
                    if col in row and pd.notna(row[col]):
                        val = pd.to_numeric(row[col], errors='coerce')
                        if pd.notna(val):
                            fee_rate = float(val)
                            if fee_rate < 1:  # 小数转百分比
                                fee_rate = fee_rate * 100
                            break
                
                # 预计佣金（ForecastAssignment中的'Forecast * 成功率'或'Forecast分配'）
                estimated_fee = 0.0
                for col in ['estimated_fee', 'forecast_fee', '预计佣金', '佣金', 'Forecast * 成功率', 'Forecast分配']:
                    if col in row and pd.notna(row[col]):
                        val = pd.to_numeric(row[col], errors='coerce')
                        if pd.notna(val):
                            estimated_fee = float(val)
                            break
                
                # 如果没有直接提供预计佣金，计算：年薪 × 费率
                if estimated_fee == 0 and estimated_salary > 0:
                    estimated_fee = estimated_salary * fee_rate / 100
                
                # 阶段（ForecastAssignment中的'最新进展'）
                stage = ''
                for col in ['stage', '阶段', '状态', '最新进展']:
                    if col in row and pd.notna(row[col]):
                        stage = str(row[col]).strip()
                        break
                
                # 成功率（ForecastAssignment中的'比例'，或根据阶段自动映射）
                success_rate = 0.0
                for col in ['success_rate', '成功率', '成功概率', '比例']:
                    if col in row and pd.notna(row[col]):
                        val = pd.to_numeric(row[col], errors='coerce')
                        if pd.notna(val):
                            success_rate = float(val)
                            # ForecastAssignment中的比例已经是百分比（如10表示10%）
                            # 如果小于1，可能是小数格式，需要转换
                            if success_rate < 1 and success_rate > 0:
                                success_rate = success_rate * 100
                            break
                
                # 如果没有提供成功率，根据阶段自动映射
                if success_rate == 0:
                    success_rate = ForecastPosition.get_stage_success_rate(stage)
                
                # 日期处理
                start_date = None
                for col in ['start_date', 'job_open_date', 'openDate', '开始日期', 'created_date', '发布日期']:
                    if col in row and pd.notna(row[col]):
                        try:
                            val = pd.to_datetime(row[col])
                            if pd.notna(val):
                                start_date = val
                                break
                        except:
                            continue
                
                expected_close_date = None
                for col in ['expected_close_date', 'close_date', '预计成交日期', '预计成功时间']:
                    if col in row and pd.notna(row[col]):
                        try:
                            val = pd.to_datetime(row[col])
                            if pd.notna(val):
                                expected_close_date = val
                                break
                        except:
                            continue
                
                # 备注
                note = ''
                for col in ['note', '备注', '说明', 'Forecast备注']:
                    if col in row and pd.notna(row[col]):
                        note = str(row[col]).strip()
                        break
                
                # 已投入成本（可选）
                sourcing_cost = 0.0
                for col in ['sourcing_cost', 'sourcing成本']:
                    if col in row and pd.notna(row[col]):
                        val = pd.to_numeric(row[col], errors='coerce')
                        if pd.notna(val):
                            sourcing_cost = float(val)
                            break
                
                interview_cost = 0.0
                for col in ['interview_cost', '面试成本']:
                    if col in row and pd.notna(row[col]):
                        val = pd.to_numeric(row[col], errors='coerce')
                        if pd.notna(val):
                            interview_cost = float(val)
                            break
                
                # 如果 consultant_configs 中有该顾问的配置，使用其工资数据
                consultant_config = self.consultant_configs.get(consultant, {})
                
                # 推算预计回款日期
                # 预计成功时间(Offer) + 30天(入职周期) + 平均账期
                expected_payment_date = None
                if expected_close_date:
                    offer_to_payment_days = self.AVG_OFFER_TO_ONBOARD_DAYS + avg_payment_cycle
                    expected_payment_date = expected_close_date + timedelta(days=offer_to_payment_days)
                
                forecast = ForecastPosition(
                    forecast_id=forecast_id,
                    client_name=client_name,
                    position_name=position_name,
                    consultant=consultant,
                    team=team,
                    estimated_salary=estimated_salary,
                    fee_rate=fee_rate,
                    estimated_fee=estimated_fee,
                    stage=stage,
                    success_rate=success_rate,
                    start_date=start_date or datetime.now(),
                    expected_close_date=expected_close_date,
                    expected_payment_date=expected_payment_date,
                    sourcing_cost=sourcing_cost,
                    interview_cost=interview_cost,
                    consultant_monthly_salary=consultant_config.get('monthly_salary', 
                                                                     self.config.get('consultant_monthly_salary', 15000)),
                    salary_multiplier=self.config.get('salary_multiplier', 3.0),
                    avg_positions_per_consultant=consultant_config.get('avg_positions',
                                                                        self.config.get('avg_positions_per_consultant', 6)),
                    note=note
                )
                self.add_forecast(forecast)
            except Exception as e:
                print(f"处理预测第 {idx} 行时出错: {e}")
                continue
    
    def get_forecast_analysis(self) -> pd.DataFrame:
        """预测职位分析表"""
        if not self.forecast_positions:
            return pd.DataFrame(columns=[
                '预测ID', '客户', '职位', '顾问', '阶段', '成功率',
                '预计佣金', '加权收入', '预计回款日期', '已投入成本', '预期MC', 'ROI', '建议'
            ])
        
        data = []
        for f in self.forecast_positions:
            data.append({
                '预测ID': f.forecast_id,
                '客户': f.client_name,
                '职位': f.position_name,
                '顾问': f.consultant,
                '阶段': f.stage,
                '成功率': f'{f.success_rate:.0f}%',
                '预计佣金': f.estimated_fee,
                '加权收入': f.weighted_revenue,
                '预计回款日期': f.expected_payment_date.strftime('%Y-%m-%d') if f.expected_payment_date else '-',
                '已投入成本': f.accumulated_cost,
                '预期MC': f.expected_marginal_contribution,
                'ROI': f'{f.roi_ratio:.1%}' if f.roi_ratio != 0 else '-',
                '建议': '✓ 继续投入' if f.is_viable else '✗ 考虑止损',
            })
        
        return pd.DataFrame(data)
    
    def get_forecast_summary(self) -> Dict:
        """预测数据汇总"""
        if not self.forecast_positions:
            return {
                'total_forecasts': 0,
                'total_estimated_fee': 0,
                'weighted_revenue': 0,
                'total_accumulated_cost': 0,
                'total_expected_mc': 0,
                'viable_count': 0,
                'stop_loss_count': 0,
            }
        
        viable = [f for f in self.forecast_positions if f.is_viable]
        
        return {
            'total_forecasts': len(self.forecast_positions),
            'total_estimated_fee': sum(f.estimated_fee for f in self.forecast_positions),
            'weighted_revenue': sum(f.weighted_revenue for f in self.forecast_positions),
            'total_accumulated_cost': sum(f.accumulated_cost for f in self.forecast_positions),
            'total_expected_mc': sum(f.expected_marginal_contribution for f in self.forecast_positions),
            'viable_count': len(viable),
            'stop_loss_count': len(self.forecast_positions) - len(viable),
            'avg_success_rate': np.mean([f.success_rate for f in self.forecast_positions]),
        }
    
    # ============ 单职位边际贡献分析 ============
    
    def get_position_mc_analysis(self) -> pd.DataFrame:
        """单职位边际贡献分析表"""
        if not self.positions:
            return pd.DataFrame(columns=[
                '职位ID', '客户', '职位', '顾问', '团队', '状态',
                '佣金', '回款', '直接成本', '边际贡献', '日均MC', '周期天数'
            ])
        
        data = []
        for p in self.positions:
            # 使用配置计算成本（传入 consultant_configs 以支持顾问专属工资）
            direct_cost = p.get_direct_cost(self.config, self.consultant_configs)
            marginal_contribution = p.actual_payment - direct_cost
            mc_per_day = marginal_contribution / p.cycle_days if p.cycle_days > 0 else 0
            
            data.append({
                '职位ID': p.position_id,
                '客户': p.client_name,
                '职位': p.position_name,
                '顾问': p.consultant,
                '团队': p.team,
                '当前阶段': p.current_stage,
                '状态': p.status,
                '佣金': p.fee_amount,
                '回款': p.actual_payment,
                '直接成本': direct_cost,
                '边际贡献': marginal_contribution,
                '日均MC': mc_per_day,
                '周期天数': p.cycle_days,
                '发布日期': p.created_date.strftime('%Y-%m-%d') if p.created_date else '-',
                '回款日期': p.payment_date.strftime('%Y-%m-%d') if p.payment_date else '-',
            })
        
        return pd.DataFrame(data)
    
    def get_mc_summary(self) -> Dict:
        """边际贡献汇总分析"""
        if not self.positions:
            return {
                'total_positions': 0,
                'successful_positions': 0,
                'total_revenue': 0,
                'total_direct_cost': 0,
                'total_mc': 0,
                'avg_mc_per_position': 0,
                'avg_mc_per_day': 0,
                'mc_positive_rate': 0,
            }
        
        successful = [p for p in self.positions if p.is_successful]
        
        # 使用配置计算成本（传入 consultant_configs 以支持顾问专属工资）
        total_revenue = sum(p.actual_payment for p in self.positions)
        total_cost = sum(p.get_direct_cost(self.config, self.consultant_configs) for p in self.positions)
        total_mc = total_revenue - total_cost
        
        # 计算各职位的MC
        mc_values = []
        for p in self.positions:
            cost = p.get_direct_cost(self.config, self.consultant_configs)
            mc = p.actual_payment - cost
            mc_values.append(mc)
        
        positive_mc = [mc for mc in mc_values if mc > 0]
        
        # 计算日均MC
        avg_mc_per_day = 0
        valid_positions = [p for p in self.positions if p.cycle_days > 0]
        if valid_positions:
            total_mc_days = sum((p.actual_payment - p.get_direct_cost(self.config, self.consultant_configs)) / p.cycle_days 
                               for p in valid_positions)
            avg_mc_per_day = total_mc_days / len(valid_positions)
        
        return {
            'total_positions': len(self.positions),
            'successful_positions': len(successful),
            'success_rate': len(successful) / len(self.positions) * 100 if self.positions else 0,
            'total_revenue': total_revenue,
            'total_direct_cost': total_cost,
            'total_mc': total_mc,
            'avg_mc_per_position': total_mc / len(self.positions),
            'avg_mc_per_day': avg_mc_per_day,
            'mc_positive_rate': len(positive_mc) / len(self.positions) * 100 if self.positions else 0,
            'profitable_positions': len(positive_mc),
            'loss_positions': len(self.positions) - len(positive_mc),
        }
    
    def get_mc_by_consultant(self) -> pd.DataFrame:
        """顾问边际贡献排名"""
        if not self.positions:
            return pd.DataFrame()
        
        consultant_data = defaultdict(lambda: {
            '职位数': 0, '成单数': 0, '总收入': 0, 
            '总成本': 0, '总MC': 0, '总天数': 0
        })
        
        for p in self.positions:
            d = consultant_data[p.consultant]
            d['职位数'] += 1
            if p.is_successful:
                d['成单数'] += 1
            d['总收入'] += p.actual_payment
            # 使用配置计算成本（传入 consultant_configs 以支持顾问专属工资）
            cost = p.get_direct_cost(self.config, self.consultant_configs)
            d['总成本'] += cost
            d['总MC'] += (p.actual_payment - cost)
            d['总天数'] += p.cycle_days
        
        result = []
        for consultant, data in consultant_data.items():
            result.append({
                '顾问': consultant,
                '职位数': data['职位数'],
                '成单数': data['成单数'],
                '转化率': data['成单数'] / data['职位数'] * 100 if data['职位数'] > 0 else 0,
                '总收入': data['总收入'],
                '总成本': data['总成本'],
                '总边际贡献': data['总MC'],
                '单职位平均MC': data['总MC'] / data['职位数'] if data['职位数'] > 0 else 0,
                '日均MC': data['总MC'] / data['总天数'] if data['总天数'] > 0 else 0,
            })
        
        return pd.DataFrame(result).sort_values('总边际贡献', ascending=False)
    
    def get_mc_by_stage(self) -> pd.DataFrame:
        """各阶段边际贡献分析"""
        stage_data = defaultdict(lambda: {'职位数': 0, '收入': 0, '成本': 0, 'MC': 0})
        
        for p in self.positions:
            stage = p.current_stage
            cost = p.get_direct_cost(self.config, self.consultant_configs)
            mc = p.actual_payment - cost
            stage_data[stage]['职位数'] += 1
            stage_data[stage]['收入'] += p.actual_payment
            stage_data[stage]['成本'] += cost
            stage_data[stage]['MC'] += mc
        
        result = []
        for stage, data in stage_data.items():
            result.append({
                '阶段': stage,
                '职位数': data['职位数'],
                '收入': data['收入'],
                '成本': data['成本'],
                '边际贡献': data['MC'],
                '平均MC': data['MC'] / data['职位数'] if data['职位数'] > 0 else 0,
            })
        
        return pd.DataFrame(result).sort_values('边际贡献', ascending=False)
    
    def _get_consultant_period_cost(self, consultant_name: str, period_start: datetime, period_end: datetime) -> float:
        """从 get_period_assumed_cost 结果中匹配单个顾问的周期成本"""
        result = self.get_period_assumed_cost(period_start, period_end)
        for d in result['details']:
            stored = d['顾问']
            if stored == consultant_name or consultant_name in stored or stored in consultant_name:
                return d['假设成本']
        return 0.0
    
    def get_consultant_profit_forecast(self, forecast_days: int = 90) -> pd.DataFrame:
        """
        顾问盈亏分析（2026年Q1）- 用于管理决策（优化/PIP）
        
        计算逻辑（拆分实际贡献和预期贡献）：
        - 实际已回款：已填写payment_date且到账的回款（累计贡献）
        - Offer未回款：已成单（有offer_date）但尚未回款的（预期贡献）
        - Forecast预期：在途单的加权预期（纯预期）
        - 成本基数：2026年1-3月实际在岗月数 × 月薪 × 3倍
        
        注：主要计算在职顾问（consultant_configs中is_active=True），
            但1-3月有工资记录或回款记录的离职顾问也会被纳入。
        """
        if not self.positions and not self.forecast_positions:
            return pd.DataFrame()
        
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        forecast_end = today + timedelta(days=forecast_days)
        
        # 构建顾问列表：在职顾问 + 有实际回款/发票的顾问（含已离职）
        active_consultants = set()
        
        def _names_match(name1, name2):
            """检查两个顾问名字是否指向同一个人"""
            if not name1 or not name2:
                return False
            if name1 == name2:
                return True
            if name1.startswith(name2) or name2.startswith(name1):
                return True
            if name1 in name2 or name2 in name1:
                return True
            return False
        
        # 排除的运营/非业务顾问名单
        EXCLUDED_CONSULTANTS = [
            '郭建飞', '黄铮', '李菁', '李文婷', 
            'Karmen Huang', 'CSM 支持', 'SYS 账号',
            'Kimbort Guo', 'Steven Huang', 'Lily Li', 
            'Carrie Li', 'Karmen Huang',
            'SYS', 'CSM', '系统账号', '客户支持'
        ]
        
        def _is_excluded(name):
            """检查是否是需要排除的运营/非业务顾问"""
            if not name:
                return True
            return any(excluded in name for excluded in EXCLUDED_CONSULTANTS)
        
        # 1. 先加入在职顾问（排除运营团队）
        for name, config in self.consultant_configs.items():
            if config.get('is_active', True) and not _is_excluded(name):
                active_consultants.add(name)
        
        # 2. 补充有实际回款的顾问（排除运营团队）
        if hasattr(self, 'consultant_collections') and self.consultant_collections:
            for coll_name in self.consultant_collections.keys():
                if _is_excluded(coll_name):
                    continue
                already_covered = any(_names_match(coll_name, existing) for existing in active_consultants)
                if not already_covered:
                    active_consultants.add(coll_name)
        
        # 3. 补充有未回款发票的顾问（排除运营团队）
        if hasattr(self, 'consultant_invoice_assignments') and self.consultant_invoice_assignments:
            for ia_name in self.consultant_invoice_assignments.keys():
                if _is_excluded(ia_name):
                    continue
                already_covered = any(_names_match(ia_name, existing) for existing in active_consultants)
                if not already_covered:
                    active_consultants.add(ia_name)
        
        # 4. 如果仍为空，从 forecast/positions 推断（排除运营团队）
        if not active_consultants:
            for f in self.forecast_positions:
                if f.consultant and not _is_excluded(f.consultant):
                    active_consultants.add(f.consultant)
            for p in self.positions:
                if p.consultant and not _is_excluded(p.consultant):
                    active_consultants.add(p.consultant)
        
        result = []
        
        # 预计算账期参数
        avg_cycle = self.get_historical_payment_cycle()
        offer_to_payment_days_avg = self.AVG_OFFER_TO_ONBOARD_DAYS + avg_cycle
        
        def match_consultant(position_consultant, target_consultant):
            """匹配顾问名称"""
            if not position_consultant:
                return False
            if position_consultant == target_consultant:
                return True
            if position_consultant.startswith(target_consultant):
                return True
            return False
        
        # 辅助函数：获取顾问的团队信息
        def get_consultant_team(consultant_name: str) -> tuple:
            """返回 (team, team_category)"""
            # 1. 优先从 consultant_configs 中读取（顾问配置表中的 team 字段）
            if consultant_name in self.consultant_configs:
                config = self.consultant_configs[consultant_name]
                if 'team' in config and config['team']:
                    team = config['team']
                    return team, classify_team_category(team)
            
            # 2. 尝试匹配英文名/中文名的变体
            for name_key, config in self.consultant_configs.items():
                # 直接匹配或包含关系
                if (name_key == consultant_name or 
                    name_key in consultant_name or 
                    consultant_name in name_key):
                    if 'team' in config and config['team']:
                        team = config['team']
                        return team, classify_team_category(team)
            
            # 3. 从 positions 中查找（备选）
            for p in self.positions:
                if p.consultant == consultant_name or consultant_name in p.consultant or p.consultant in consultant_name:
                    if p.team:
                        return p.team, classify_team_category(p.team)
            
            # 4. 从 forecast_positions 中查找（备选）
            for f in self.forecast_positions:
                if f.consultant == consultant_name or consultant_name in f.consultant or f.consultant in consultant_name:
                    if f.team:
                        return f.team, classify_team_category(f.team)
            
            return '', 'Other'
        
        for consultant in active_consultants:
            # 获取团队信息
            team, team_category = get_consultant_team(consultant)
            
            # ========== 1. 实际已回款（累计贡献） ==========
            # 优先使用 invoiceassignment 的顾问回款数据（更准确）
            actual_collected_90d = 0
            actual_collected_total = 0  # 累计实际回款总额
            
            # 尝试从 consultant_collections（invoice 表）获取顾问真实回款
            has_invoice_data = False
            if hasattr(self, 'consultant_collections') and self.consultant_collections:
                for coll_name, coll_data in self.consultant_collections.items():
                    if match_consultant(coll_name, consultant):
                        actual_collected_total = coll_data.get('total_received', 0)
                        # 90天内回款：consultant_collections 是近1年的累计
                        # 作为近似，全部计入 90 天（因为近期回款占主要部分）
                        actual_collected_90d = actual_collected_total
                        has_invoice_data = True
                        break
            
            # ========== 2. Offer未回款（预期贡献） ==========
            # 优先使用 invoiceassignment 的个人分配金额（更准）
            offer_pending_total = 0
            has_invoice_assignment = False
            if hasattr(self, 'consultant_invoice_assignments') and self.consultant_invoice_assignments:
                for ia_name, ia_list in self.consultant_invoice_assignments.items():
                    if match_consultant(ia_name, consultant):
                        has_invoice_assignment = True
                        for ia in ia_list:
                            # 排除已回款和已作废的发票
                            if ia['invoice_status'] not in ['Received', '回款完成', 'Reject']:
                                offer_pending_total += ia['assigned_amount']
            
            # fallback：从 positions 累加（尚未开票的 offer）
            # 只有当 consultant_invoice_assignments 中没有该顾问的任何数据时才 fallback
            # （避免发票已Reject但positions中仍显示未回款的重复计算）
            if offer_pending_total == 0 and not has_invoice_assignment:
                for p in self.positions:
                    if not match_consultant(p.consultant, consultant) or not p.is_successful:
                        continue
                    if p.payment_status not in ['已回款', '部分回款', '回款完成'] and p.offer_date and p.fee_amount > 0:
                        offer_pending_total += p.fee_amount
            
            # 90天内Offer待回：暂用全部（因为 invoiceassignment 没有回款日期）
            offer_pending_90d = offer_pending_total
            
            # ========== 3. Forecast预期（纯预期） ==========
            forecast_90d = 0
            forecast_total = 0
            for f in self.forecast_positions:
                if not match_consultant(f.consultant, consultant):
                    continue
                if f.expected_payment_date is None and f.expected_close_date:
                    f.expected_payment_date = f.expected_close_date + timedelta(days=offer_to_payment_days_avg)
                
                if f.expected_payment_date:
                    forecast_total += f.weighted_revenue
                    if today <= f.expected_payment_date <= forecast_end:
                        forecast_90d += f.weighted_revenue
            
            # ========== 4. 成本计算（实时：年初至今） ==========
            period_start = datetime(2026, 1, 1)
            period_end = today
            period_cost = self._get_consultant_period_cost(consultant, period_start, period_end)
            
            if consultant in self.consultant_configs:
                monthly_salary = self.consultant_configs[consultant].get('monthly_salary', 15000)
            else:
                monthly_salary = self.config.get('consultant_monthly_salary', 15000)
            
            multiplier = self.config.get('salary_multiplier', 3.0)
            # 当前月份数（用于fallback计算）
            current_month = max(1, today.month)
            
            # ========== 4. 状态判断与成本计算 ==========
            # 优先从数据库获取状态（更准确）
            db_status_code, db_status_label, db_join_date, db_leave_date = self._get_db_status(consultant)
            
            # 回退到 consultant_configs（Excel配置）
            in_configs_exact = consultant in self.consultant_configs
            in_configs_fuzzy = False
            config_active = True
            matched_cfg = None
            for cfg_name, cfg in self.consultant_configs.items():
                if cfg_name == consultant or cfg_name.startswith(consultant) or consultant.startswith(cfg_name):
                    in_configs_fuzzy = True
                    config_active = cfg.get('is_active', True)
                    matched_cfg = cfg
                    break
            
            is_in_configs = in_configs_exact or in_configs_fuzzy
            
            # 使用数据库状态（优先）或配置状态
            if db_status_code is not None:
                status_code = db_status_code
                status_label = db_status_label
                join_date = db_join_date
                leave_date = db_leave_date
            elif is_in_configs:
                status_code = 2 if config_active else 1
                status_label = '在职' if config_active else '已离职'
                join_date = None
                leave_date = matched_cfg.get('leave_date') if matched_cfg else None
            else:
                status_code = 0
                status_label = '未配置'
                join_date = None
                leave_date = None
            
            # 成本计算：按实际在岗月份核算
            if period_cost > 0:
                # 使用实际成本记录（最高优先级）
                cost = period_cost
            elif status_code == 2 and join_date:
                # 在职且有入职日期：计算本年度实际在岗月数
                active_months = self._calc_consultant_active_months(
                    join_date, None, 
                    datetime(2026, 1, 1), today
                )
                cost = monthly_salary * multiplier * active_months
            elif status_code == 2:
                # 在职但无入职日期：按当前月份计算
                cost = monthly_salary * multiplier * current_month
            elif status_code == 1 and leave_date:
                # 已离职且有离职日期：计算到离职日期的在岗月数
                active_months = self._calc_consultant_active_months(
                    join_date if join_date else datetime(2026, 1, 1),
                    leave_date,
                    datetime(2026, 1, 1), today
                )
                cost = monthly_salary * multiplier * active_months
            elif status_code == 1:
                # 已离职但无离职日期：无法确定何时离职，不计算成本（避免误算）
                cost = 0
            else:
                # 未配置人员：成本为0
                cost = 0
            
            # ========== 5. 计算核心指标 ==========
            # 指标1：回款利润率 = (累计回款 - 累计成本) / 累计回款
            actual_profit = actual_collected_total - cost
            actual_margin_str = self._calc_margin_str(actual_collected_total, cost)
            
            # 指标2：Offer业绩余粮（月数）= 累计Offer未回款 / 月成本
            monthly_cost = monthly_salary * multiplier
            offer_reserve_months = offer_pending_total / monthly_cost if monthly_cost > 0 else 0
            
            # 指标3：Forecast覆盖率 = (累计Offer未回款 + 未来3个月Forecast) / 6个月成本
            future_6m_cost = monthly_cost * 6
            forecast_coverage = ((offer_pending_total + forecast_90d) / future_6m_cost) if future_6m_cost > 0 else 0
            
            # ========== 6. 风险评级 ==========
            # 只有在职人员做风险评级，已离职/未配置人员不评级
            if status_code != 2:
                risk_level = ''  # 已离职或未配置，不显示评级
            elif actual_profit < 0 and offer_reserve_months < 3:
                risk_level = '🔴 亏损且余粮不足'
            elif actual_profit < 0:
                risk_level = '🟡 当前亏损但有余粮'
            elif forecast_coverage < 0.5:
                risk_level = '🟡 当前盈利但Pipeline不足'
            else:
                risk_level = '🟢 健康'
            
            result.append({
                '顾问': consultant,
                '团队': team,
                '团队大类': team_category,
                # 实际回款（利润口径）— 指标1：累计回款
                '已回款': actual_collected_total,
                '累计实际回款': actual_collected_total,
                '累计成本': cost,
                '月成本': monthly_cost,
                '回款利润': actual_profit,
                '回款利润率': actual_margin_str,
                # Offer业绩余粮 — 指标2：累计Offer未回款
                '90天Offer待回': offer_pending_total,
                '累计Offer待回': offer_pending_total,
                'Offer余粮(月)': round(offer_reserve_months, 1),
                # Forecast Pipeline覆盖 — 指标3：Offer+Forecast / 6个月成本
                '90天Forecast': forecast_90d,
                '累计Forecast': forecast_total,
                '未来6个月成本': future_6m_cost,
                'Forecast覆盖率': f"{forecast_coverage*100:.0f}%",
                'Forecast覆盖数值': forecast_coverage,
                # 其他
                '风险评级': risk_level,
                '月薪': monthly_salary,
                '状态': status_label,
                '状态码': status_code,
            })
        
        df = pd.DataFrame(result)
        # 去除未配置人员（只保留在职和已离职）
        df = df[df['状态码'] > 0].copy()
        # 排序：在职(2) > 已离职(1)，同状态按回款利润降序
        return df.sort_values(['状态码', '回款利润'], ascending=[False, False])
    
    def _calc_margin_str(self, revenue: float, cost: float) -> str:
        """计算利润率字符串，亏损时显示'-'"""
        profit = revenue - cost
        if profit < 0:
            return '-'
        elif revenue > 0:
            return f'{(profit / revenue * 100):.1f}%'
        return '-'
    
    # ============ 现金流日历 ============
    
    def _build_auto_cashflow_events(self):
        """基于职位数据和成本配置，自动生成现金流事件（保留用户手动上传的事件）"""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # 清除之前自动生成的事件，保留用户手动上传的
        self.cashflow_events = [
            e for e in self.cashflow_events 
            if not e.event_id.startswith('AUTO_')
        ]
        
        # 预计算账期参数
        avg_cycle = self.get_historical_payment_cycle()
        offer_to_payment_days = self.AVG_OFFER_TO_ONBOARD_DAYS + avg_cycle
        
        # 1. 从实际职位生成回款流入事件
        # 包括：已确认回款日期的 + 已成单但未回款的（根据offer推算）
        for p in self.positions:
            if not p.is_successful:
                continue
            
            if p.payment_date and p.payment_date >= today:
                # 已确认回款日期
                event = CashFlowEvent(
                    event_id=f'AUTO_IN_P_{p.position_id}',
                    event_date=p.payment_date,
                    event_type='流入',
                    category='已确认回款',
                    amount=p.actual_payment,
                    probability=100,
                    related_position_id=p.position_id
                )
                self.cashflow_events.append(event)
            elif p.offer_date and not p.payment_date and p.fee_amount > 0:
                # 已成单但未回款，根据offer推算回款日期
                # 使用职位级别的账期（如果有设置）
                payment_cycle = self.get_position_payment_cycle(p)
                offer_to_payment_days = self.AVG_OFFER_TO_ONBOARD_DAYS + payment_cycle
                estimated_payment_date = p.offer_date + timedelta(days=offer_to_payment_days)
                if estimated_payment_date >= today:
                    event = CashFlowEvent(
                        event_id=f'AUTO_IN_P_EST_{p.position_id}',
                        event_date=estimated_payment_date,
                        event_type='流入',
                        category='预期回款-成单未回',
                        amount=p.fee_amount,  # 使用fee_amount作为预期金额
                        probability=80,  # 成单未回的确定性较高
                        related_position_id=p.position_id
                    )
                    self.cashflow_events.append(event)
        
        # 2. 从 forecast 生成预期回款流入事件
        for f in self.forecast_positions:
            if f.expected_payment_date is None and f.expected_close_date:
                f.expected_payment_date = f.expected_close_date + timedelta(days=offer_to_payment_days)
            
            if f.expected_payment_date and f.expected_payment_date >= today:
                # 用 estimated_fee 作为金额，success_rate 作为概率
                # 避免 weighted_revenue * success_rate 的双重加权
                event = CashFlowEvent(
                    event_id=f'AUTO_IN_F_{f.forecast_id}',
                    event_date=f.expected_payment_date,
                    event_type='流入',
                    category='预期回款',
                    amount=f.estimated_fee,
                    probability=f.success_rate,
                    related_position_id=f.forecast_id
                )
                self.cashflow_events.append(event)
        
        # 3. 生成每日成本流出事件（按月度总成本平摊到每天）
        monthly_cost = self.estimate_monthly_cost()
        daily_cost = monthly_cost / 30
        
        # 生成未来180天的固定成本流出
        for i in range(180):
            date = today + timedelta(days=i)
            event = CashFlowEvent(
                event_id=f'AUTO_OUT_COST_{date.strftime("%Y%m%d")}',
                event_date=date,
                event_type='流出',
                category='顾问及运营成本',
                amount=daily_cost,
                probability=100
            )
            self.cashflow_events.append(event)
    
    def generate_cashflow_calendar(self, days: int = 90, cash_reserve: float = 0) -> pd.DataFrame:
        """生成现金流日历（未来N天）- 自动生成流入流出事件"""
        # 确保事件已生成
        self._build_auto_cashflow_events()
        
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        dates = [today + timedelta(days=i) for i in range(days)]
        
        calendar_data = []
        running_balance = cash_reserve  # 初始余额 = 现金储备
        
        for date in dates:
            date_str = date.strftime('%Y-%m-%d')
            
            # 流入
            inflow_events = [e for e in self.cashflow_events 
                           if e.event_date.date() == date.date() and e.event_type == '流入']
            inflow_confirmed = sum(e.amount for e in inflow_events if e.probability >= 100)
            inflow_expected = sum(e.expected_amount for e in inflow_events)
            
            # 流出
            outflow_events = [e for e in self.cashflow_events 
                            if e.event_date.date() == date.date() and e.event_type == '流出']
            outflow_confirmed = sum(e.amount for e in outflow_events if e.probability >= 100)
            outflow_expected = sum(e.expected_amount for e in outflow_events)
            
            # 净现金流
            net_confirmed = inflow_confirmed - outflow_confirmed
            net_expected = inflow_expected - outflow_expected
            
            running_balance += net_expected
            
            # 预警（红线 = 5个月储备金）
            warning = ""
            monthly_cost = self.estimate_monthly_cost()
            red_line = 5 * monthly_cost  # 5个月储备金红线
            if running_balance < 0:
                warning = "🔴 资金缺口"
            elif running_balance < red_line:
                months_left = running_balance / monthly_cost if monthly_cost > 0 else 999
                warning = f"🟡 低于安全线({months_left:.1f}个月)"
            
            calendar_data.append({
                '日期': date_str,
                '星期': ['一', '二', '三', '四', '五', '六', '日'][date.weekday()],
                '确认流入': inflow_confirmed,
                '预期流入': inflow_expected,
                '确认流出': outflow_confirmed,
                '预期流出': outflow_expected,
                '净现金流(确认)': net_confirmed,
                '净现金流(预期)': net_expected,
                '累计余额': running_balance,
                '预警': warning,
            })
        
        return pd.DataFrame(calendar_data)
    
    def generate_monthly_cashflow_calendar(self, months: int = 6, cash_reserve: float = 0) -> pd.DataFrame:
        """生成月度现金流日历（按月汇总）"""
        # 先生成每日数据
        days = months * 31  # 足够多的天数覆盖目标月份
        daily_calendar = self.generate_cashflow_calendar(days=days, cash_reserve=cash_reserve)
        
        # 转换为DataFrame
        df = pd.DataFrame(daily_calendar)
        df['日期'] = pd.to_datetime(df['日期'])
        df['月份'] = df['日期'].dt.to_period('M')
        
        # 按月汇总
        monthly = df.groupby('月份').agg({
            '确认流入': 'sum',
            '预期流入': 'sum',
            '确认流出': 'sum',
            '预期流出': 'sum',
            '净现金流(确认)': 'sum',
            '净现金流(预期)': 'sum',
        }).reset_index()
        
        # 计算累计余额
        monthly['累计余额'] = monthly['净现金流(预期)'].cumsum()
        
        # 格式化月份显示
        monthly['月份'] = monthly['月份'].astype(str)
        
        return monthly
    
    def generate_biweekly_cashflow_calendar(self, periods: int = 12, cash_reserve: float = 0) -> pd.DataFrame:
        """生成半月现金流日历（每15天汇总）- 用于90天/180天现金流明细展示"""
        # 先生成每日数据（足够覆盖periods个半月周期）
        days = periods * 15 + 5  # 加5天缓冲
        daily_calendar = self.generate_cashflow_calendar(days=days, cash_reserve=cash_reserve)
        
        # 转换为DataFrame
        df = pd.DataFrame(daily_calendar)
        df['日期'] = pd.to_datetime(df['日期'])
        
        # 创建半月分组标识
        # 每15天为一个周期：第1-15天为第一个半月，第16-30天为第二个半月，以此类推
        df['周期序号'] = ((df.index) // 15)
        df['周期开始'] = df.groupby('周期序号')['日期'].transform('min')
        df['周期结束'] = df.groupby('周期序号')['日期'].transform('max')
        df['周期标签'] = df['周期开始'].dt.strftime('%m/%d') + '-' + df['周期结束'].dt.strftime('%m/%d')
        
        # 按半月汇总
        biweekly = df.groupby(['周期序号', '周期标签']).agg({
            '确认流入': 'sum',
            '预期流入': 'sum',
            '确认流出': 'sum',
            '预期流出': 'sum',
            '净现金流(确认)': 'sum',
            '净现金流(预期)': 'sum',
        }).reset_index()
        
        # 计算累计余额
        biweekly['累计余额'] = biweekly['净现金流(预期)'].cumsum()
        
        # 选择需要的列并重命名
        biweekly = biweekly[['周期标签', '确认流入', '预期流入', '确认流出', '预期流出', 
                             '净现金流(确认)', '净现金流(预期)', '累计余额']]
        biweekly.columns = ['时间段', '确认流入', '预期流入', '确认流出', '预期流出',
                           '净现金流(确认)', '净现金流(预期)', '累计余额']
        
        return biweekly
    
    def get_cashflow_summary(self, start_date: datetime = None, end_date: datetime = None) -> Dict:
        """现金流汇总分析"""
        events = self.cashflow_events
        if start_date:
            events = [e for e in events if e.event_date >= start_date]
        if end_date:
            events = [e for e in events if e.event_date <= end_date]
        
        inflow = sum(e.expected_amount for e in events if e.event_type == '流入')
        outflow = sum(e.expected_amount for e in events if e.event_type == '流出')
        
        # 按类别统计
        by_category = defaultdict(float)
        for e in events:
            by_category[e.category] += e.expected_amount
        
        return {
            'total_inflow': inflow,
            'total_outflow': outflow,
            'net_cashflow': inflow - outflow,
            'inflow_by_category': dict(by_category),
            'event_count': len(events),
        }
    
    # ============ 三速差分析 ============
    
    def get_velocity_dashboard(self) -> Dict:
        """三速差仪表盘 - 职位流速度、顾问产能、现金周转"""
        
        # 1. 职位流速度
        successful_positions = [p for p in self.positions if p.is_successful]
        
        offer_cycles = [p.to_offer_days for p in successful_positions 
                        if p.to_offer_days is not None]
        avg_offer_cycle = np.mean(offer_cycles) if offer_cycles else 0
        payment_cycles = [p.to_payment_days for p in successful_positions 
                          if p.to_payment_days is not None]
        avg_payment_cycle = np.mean(payment_cycles) if payment_cycles else 0
        
        stage_distribution = defaultdict(int)
        for p in self.positions:
            stage_distribution[p.current_stage] += 1
        
        position_velocity = {
            'avg_offer_cycle': avg_offer_cycle,
            'avg_payment_cycle': avg_payment_cycle,
            'total_pipeline': len(self.positions),
            'stage_distribution': dict(stage_distribution),
            'velocity_score': max(0, 100 - avg_offer_cycle) if avg_offer_cycle else 50,
        }
        
        # 2. 顾问产能速度
        consultant_velocity = self._calculate_consultant_velocity()
        avg_utilization = np.mean([v.capacity_utilization for v in consultant_velocity]) if consultant_velocity else 0
        avg_deals_per_month = np.mean([v.deals_per_month for v in consultant_velocity]) if consultant_velocity else 0
        
        consultant_speed = {
            'consultant_count': len(consultant_velocity),
            'avg_capacity_utilization': avg_utilization,
            'avg_deals_per_month': avg_deals_per_month,
            'bottleneck_consultants': [v.consultant_name for v in consultant_velocity 
                                      if v.capacity_utilization > 90][:3],  # 产能瓶颈
        }
        
        # 3. 现金周转速度
        cash_turnover = self._calculate_cash_turnover()
        
        return {
            'position_velocity': position_velocity,
            'consultant_speed': consultant_speed,
            'cash_turnover': cash_turnover,
            'health_score': self._calculate_health_score(position_velocity, consultant_speed, cash_turnover),
        }
    
    def _calculate_consultant_velocity(self) -> List[ConsultantVelocity]:
        """计算顾问产能速度"""
        consultant_data = defaultdict(lambda: {
            'positions': [], 'offers': 0, 'deals': 0, 'revenue': 0, 'mc': 0,
            'offer_cycles': [], 'payment_cycles': [], 'team': ''
        })
        
        for p in self.positions:
            d = consultant_data[p.consultant]
            d['positions'].append(p)
            d['team'] = p.team
            if p.offer_date:
                d['offers'] += 1
                if p.to_offer_days:
                    d['offer_cycles'].append(p.to_offer_days)
            if p.is_successful:
                d['deals'] += 1
                d['revenue'] += p.actual_payment
                cost = p.get_direct_cost(self.config, self.consultant_configs)
                d['mc'] += (p.actual_payment - cost)
                if p.to_payment_days:
                    d['payment_cycles'].append(p.to_payment_days)
        
        result = []
        for name, data in consultant_data.items():
            active_count = len([p for p in data['positions'] if p.status != '已关闭' or not p.payment_date])
            avg_offer_cycle = np.mean(data['offer_cycles']) if data['offer_cycles'] else 0
            avg_payment_cycle = np.mean(data['payment_cycles']) if data['payment_cycles'] else 0
            
            # 计算月均数据（假设数据周期为3个月）
            months = 3
            
            cv = ConsultantVelocity(
                consultant_name=name,
                team=data['team'],
                active_positions=active_count,
                avg_offer_cycle=avg_offer_cycle,
                avg_payment_cycle=avg_payment_cycle,
                positions_per_month=len(data['positions']) / months,
                offers_per_month=data['offers'] / months,
                deals_per_month=data['deals'] / months,
                revenue_per_month=data['revenue'] / months,
                mc_per_month=data['mc'] / months,
            )
            result.append(cv)
        
        return result
    
    def _calculate_cash_turnover(self) -> Dict:
        """计算现金周转速度"""
        if not self.positions:
            return {'avg_collection_period': 0, 'cash_gap_days': 0, 'runway_days': 180}
        
        # 平均回款周期
        payment_cycles = [p.to_payment_days for p in self.positions 
                         if p.to_payment_days is not None]
        avg_collection_period = np.mean(payment_cycles) if payment_cycles else 0
        
        # 现金流缺口天数（从签约到回款）
        cash_gaps = []
        for p in self.positions:
            if p.signed_date and p.payment_date:
                gap = (p.payment_date - p.signed_date).days
                cash_gaps.append(gap)
        avg_cash_gap = np.mean(cash_gaps) if cash_gaps else 0
        
        # 现金跑道（基于当前预测）
        calendar = self.generate_cashflow_calendar(days=180)
        negative_dates = calendar[calendar['累计余额'] < 0]
        if not negative_dates.empty:
            first_negative_date = pd.to_datetime(negative_dates.iloc[0]['日期'])
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            runway_days = max(0, (first_negative_date - today).days)
        else:
            runway_days = 180
        
        return {
            'avg_collection_period': avg_collection_period,
            'cash_gap_days': avg_cash_gap,
            'runway_days': runway_days,
            'weekly_burn_rate': self.config['fixed_monthly_expense'] / 4,
        }
    
    def _calculate_health_score(self, pos_vel: Dict, con_speed: Dict, cash: Dict) -> Dict:
        """计算综合健康度评分"""
        # 职位流健康度（0-100）
        position_score = pos_vel.get('velocity_score', 50)
        
        # 顾问产能健康度
        utilization = con_speed.get('avg_capacity_utilization', 0)
        utilization_score = 100 - abs(80 - utilization)  # 80%利用率最理想
        
        # 现金健康度
        runway = cash.get('runway_days', 0)
        cash_score = min(100, runway / 3)  # 90天跑道=100分
        
        # 综合评分
        overall = position_score * 0.3 + utilization_score * 0.3 + cash_score * 0.4
        
        return {
            'overall': overall,
            'position_flow': position_score,
            'consultant_capacity': utilization_score,
            'cash_health': cash_score,
            'status': '健康' if overall >= 70 else '预警' if overall >= 50 else '危险',
        }
    
    # ============ 预警与决策建议 ============
    
    def get_alerts(self) -> List[Dict]:
        """获取经营预警信息"""
        alerts = []
        
        # 1. 现金流预警
        calendar = self.generate_cashflow_calendar(days=30)
        negative_in_30 = calendar[calendar['累计余额'] < 0]
        if not negative_in_30.empty:
            first_negative = negative_in_30.iloc[0]
            alerts.append({
                'level': '🔴 紧急',
                'category': '现金流',
                'message': f"预计 {first_negative['日期']} 出现资金缺口 {first_negative['累计余额']:,.0f} 元",
                'action': '立即催收应收账款或暂停非必要支出',
            })
        
        # 2. 顾问产能预警
        velocity_data = self._calculate_consultant_velocity()
        overloaded = [v for v in velocity_data if v.capacity_utilization > 95]
        for v in overloaded:
            alerts.append({
                'level': '🟡 警告',
                'category': '顾问产能',
                'message': f"{v.consultant_name} 产能利用率 {v.capacity_utilization:.0f}%，已超负荷",
                'action': '考虑分配部分职位给其他顾问或招聘新人',
            })
        
        underutilized = [v for v in velocity_data if v.capacity_utilization < 30]
        for v in underutilized:
            alerts.append({
                'level': '🟡 警告',
                'category': '顾问产能',
                'message': f"{v.consultant_name} 产能利用率仅 {v.capacity_utilization:.0f}%，资源闲置",
                'action': '增加职位分配或进行技能培训',
            })
        
        # 3. 职位周期预警
        slow_positions = [p for p in self.positions 
                         if p.cycle_days > 90 and p.status == '进行中']
        for p in slow_positions[:3]:  # 只显示前3个
            alerts.append({
                'level': '🟡 警告',
                'category': '职位周期',
                'message': f"{p.position_name}({p.client_name}) 已进行 {p.cycle_days} 天未结案",
                'action': '评估客户质量，考虑是否继续投入',
            })
        
        # 4. 边际贡献预警
        loss_positions = []
        for p in self.positions:
            cost = p.get_direct_cost(self.config, self.consultant_configs)
            if (p.actual_payment - cost) < 0:
                loss_positions.append(p)
        if len(loss_positions) > 3:
            total_loss = sum((p.actual_payment - p.get_direct_cost(self.config, self.consultant_configs)) for p in loss_positions)
            alerts.append({
                'level': '🔴 紧急',
                'category': '盈利能力',
                'message': f"有 {len(loss_positions)} 个职位边际贡献为负，累计亏损 {total_loss:,.0f} 元",
                'action': '审查高成本低产出职位的投入策略',
            })
        
        return alerts
    
    def get_decision_recommendations(self) -> List[Dict]:
        """获取决策建议"""
        recommendations = []
        
        # 基于数据给出经营建议
        mc_summary = self.get_mc_summary()
        velocity = self.get_velocity_dashboard()
        
        # 1. 客户策略建议
        client_mc = self._get_mc_by_client()
        low_value_clients = client_mc[client_mc['平均MC'] < client_mc['平均MC'].median()]
        if not low_value_clients.empty:
            recommendations.append({
                'category': '客户策略',
                'suggestion': f"考虑减少 {len(low_value_clients)} 个低价值客户的投入",
                'impact': f"可释放顾问产能约 {len(low_value_clients) * 2:.0f} 个职位",
                'priority': '高',
            })
        
        # 2. 人员配置建议
        consultant_vel = self._calculate_consultant_velocity()
        avg_mc = np.mean([v.mc_per_month for v in consultant_vel]) if consultant_vel else 0
        low_performers = [v for v in consultant_vel if v.mc_per_month < avg_mc * 0.5]
        if len(low_performers) >= 2:
            recommendations.append({
                'category': '人员优化',
                'suggestion': f"{len(low_performers)} 位顾问边际贡献低于平均水平50%，需培训或调整",
                'impact': '提升人均产能，降低固定成本分摊',
                'priority': '中',
            })
        
        # 3. 现金流管理建议
        cash = self._calculate_cash_turnover()
        if cash['runway_days'] < 60:
            recommendations.append({
                'category': '现金流管理',
                'suggestion': '现金跑道不足60天，需加速回款或控制支出',
                'impact': f"当前回款周期 {cash['avg_collection_period']:.0f} 天，目标缩短至 {cash['avg_collection_period'] * 0.8:.0f} 天",
                'priority': '高',
            })
        
        return recommendations
    
    def _get_mc_by_client(self) -> pd.DataFrame:
        """按客户统计边际贡献"""
        client_data = defaultdict(lambda: {'count': 0, 'mc': 0, 'revenue': 0})
        for p in self.positions:
            cost = p.get_direct_cost(self.config, self.consultant_configs)
            client_data[p.client_name]['count'] += 1
            client_data[p.client_name]['mc'] += (p.actual_payment - cost)
            client_data[p.client_name]['revenue'] += p.actual_payment
        
        result = []
        for client, data in client_data.items():
            result.append({
                '客户': client,
                '职位数': data['count'],
                '总MC': data['mc'],
                '平均MC': data['mc'] / data['count'] if data['count'] > 0 else 0,
                '总收入': data['revenue'],
            })
        return pd.DataFrame(result)

    
    # ============ 情景模拟器 (What-if Analysis) ============
    
    def simulate_headcount_change(self, change_count: int, monthly_salary: float = 20000, 
                                  effective_days: int = 0, forecast_days: int = 180) -> Dict:
        """
        模拟人员变动对现金流的影响
        
        Args:
            change_count: 变动人数（正数=新增，负数=减少）
            monthly_salary: 人均月薪
            effective_days: 生效天数（0=立即生效）
            forecast_days: 预测天数（90或180）
        
        Returns:
            模拟结果字典
        """
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # 获取基础数据
        base_result = self.get_cash_safety_analysis(current_balance=self.config.get('cash_reserve', 3000000))
        
        # 计算变动影响
        multiplier = self.config.get('salary_multiplier', 3.0)
        monthly_cost_change = change_count * monthly_salary * multiplier
        
        # 计算生效时间点的累计影响
        effective_date = today + timedelta(days=effective_days)
        months_affected = max(0, (forecast_days - effective_days) / 30)
        total_cost_impact = monthly_cost_change * months_affected
        
        # 调整后的余额
        if forecast_days <= 90:
            base_balance = base_result['balance_90d']
        else:
            base_balance = base_result['balance_180d']
        
        adjusted_balance = base_balance - total_cost_impact
        
        return {
            'change_count': change_count,
            'monthly_salary': monthly_salary,
            'monthly_cost_change': monthly_cost_change,
            'effective_days': effective_days,
            'months_affected': months_affected,
            'total_cost_impact': total_cost_impact,
            'base_balance': base_balance,
            'adjusted_balance': adjusted_balance,
            'impact_percent': (total_cost_impact / base_balance * 100) if base_balance > 0 else 0,
            'break_even_months': abs(base_balance / monthly_cost_change) if monthly_cost_change != 0 else float('inf'),
            'recommendation': '可行' if adjusted_balance > 0 else '风险较高',
        }
    
    def simulate_payment_cycle_change(self, client_keyword: str, new_cycle_days: int,
                                     forecast_days: int = 180) -> Dict:
        """
        模拟客户账期调整对现金流的影响
        
        Args:
            client_keyword: 客户名称关键词（如"诺华"）
            new_cycle_days: 新账期天数
            forecast_days: 预测天数
        
        Returns:
            模拟结果字典
        """
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # 找到匹配客户的未成单
        affected_positions = []
        for p in self.positions:
            if not p.is_successful or p.payment_date or not p.offer_date:
                continue
            if client_keyword.lower() in p.client_name.lower():
                affected_positions.append(p)
        
        if not affected_positions:
            old_cycle = self.get_historical_payment_cycle()
            return {
                'client_keyword': client_keyword,
                'affected_count': 0,
                'affected_amount': 0,
                'old_cycle_days': old_cycle,
                'new_cycle_days': new_cycle_days,
                'cycle_diff_days': 0,
                'impact_description': '未找到匹配客户',
                'cash_flow_impact': '无影响',
                'recommendation': '请检查客户名称',
            }
        
        # 计算原账期和新账期的差异
        old_cycle = self.get_historical_payment_cycle()
        cycle_diff = new_cycle_days - old_cycle  # 正数=回款变慢，负数=回款加快
        
        total_amount = sum(p.fee_amount for p in affected_positions)
        
        # 计算影响（账期每增加30天，相当于该笔回款晚到账30天，影响当月现金流）
        days_impact = cycle_diff
        
        return {
            'client_keyword': client_keyword,
            'affected_count': len(affected_positions),
            'affected_amount': total_amount,
            'old_cycle_days': old_cycle,
            'new_cycle_days': new_cycle_days,
            'cycle_diff_days': cycle_diff,
            'impact_description': f'回款{"延迟" if cycle_diff > 0 else "提前"} {abs(cycle_diff)} 天',
            'cash_flow_impact': f'影响约 {total_amount:,.0f} 元的回款时间点',
            'recommendation': '谨慎' if cycle_diff > 30 else '可接受',
        }
    
    def simulate_collection_acceleration(self, acceleration_rate: float = 0.3,
                                         days_ahead: int = 30,
                                         forecast_days: int = 180) -> Dict:
        """
        模拟回款加速对现金流的改善效果
        
        Args:
            acceleration_rate: 加速回款比例（如0.3表示30%的逾期款提前收回）
            days_ahead: 提前天数（如30天）
            forecast_days: 预测天数
        
        Returns:
            模拟结果字典
        """
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # 获取逾期款
        overdue_positions = []
        avg_cycle = self.get_historical_payment_cycle()
        offer_to_payment_days = self.AVG_OFFER_TO_ONBOARD_DAYS + avg_cycle
        
        for p in self.positions:
            if not p.is_successful or p.payment_date or not p.offer_date:
                continue
            
            expected_amount = p.actual_payment if p.actual_payment > 0 else p.fee_amount
            if expected_amount <= 0:
                continue
            
            payment_cycle = self.get_position_payment_cycle(p)
            offer_to_payment = self.AVG_OFFER_TO_ONBOARD_DAYS + payment_cycle
            est_payment_date = p.offer_date + timedelta(days=offer_to_payment)
            days_until = (est_payment_date - today).days
            
            if days_until < 0:  # 已逾期
                overdue_positions.append({
                    'position': p,
                    'amount': expected_amount,
                    'days_overdue': abs(days_until),
                })
        
        if not overdue_positions:
            return {
                'overdue_total': 0,
                'acceleration_rate': acceleration_rate,
                'improved_amount': 0,
                'impact': '无逾期款项',
            }
        
        # 计算改善效果
        total_overdue = sum(o['amount'] for o in overdue_positions)
        improved_amount = total_overdue * acceleration_rate
        
        # 获取基础余额
        base_result = self.get_cash_safety_analysis(current_balance=self.config.get('cash_reserve', 3000000))
        if forecast_days <= 90:
            base_balance = base_result['balance_90d']
        else:
            base_balance = base_result['balance_180d']
        
        new_balance = base_balance + improved_amount
        
        return {
            'overdue_count': len(overdue_positions),
            'overdue_total': total_overdue,
            'acceleration_rate': acceleration_rate,
            'days_ahead': days_ahead,
            'improved_amount': improved_amount,
            'base_balance': base_balance,
            'new_balance': new_balance,
            'improvement_percent': (improved_amount / base_balance * 100) if base_balance > 0 else 0,
            'monthly_cost_cover': improved_amount / self.estimate_monthly_cost() if self.estimate_monthly_cost() > 0 else 0,
            'recommendation': '强烈推荐' if acceleration_rate >= 0.5 else '建议执行' if acceleration_rate >= 0.3 else '可尝试',
        }
    
    def get_whatif_summary(self) -> Dict:
        """获取情景模拟的综合摘要"""
        return {
            'headcount_simulation': {
                'add_one': self.simulate_headcount_change(1),
                'reduce_one': self.simulate_headcount_change(-1),
            },
            'collection_acceleration': self.simulate_collection_acceleration(),
        }

    
    # ============ 智能预警系统 ============
    
    def get_cashflow_alerts(self, days: int = 30, current_balance: float = None) -> List[Dict]:
        """
        获取现金流相关预警
        
        Args:
            days: 预测天数
            current_balance: 当前实际现金余额（默认使用config中的值）
        
        Returns:
            预警列表，按优先级排序
        """
        if current_balance is None:
            current_balance = self.config.get('cash_reserve', 3000000)
        
        alerts = []
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # 1. 现金余额危险预警（红线 = 5个月储备金）
        safety = self.get_cash_safety_analysis(current_balance=current_balance)
        monthly_cost = safety['monthly_cost']
        red_line = 5 * monthly_cost  # 5个月储备金红线
        
        # 90天余额危险
        if safety['balance_90d'] < 0:
            alerts.append({
                'level': 'danger',
                'level_text': '🔴 紧急',
                'category': '现金流',
                'title': '90天现金流缺口',
                'message': f"预计90天内出现资金缺口 {abs(safety['balance_90d']):,.0f} 元",
                'action': '立即催收逾期款项，暂停非必要支出',
                'responsible': '财务总监/CEO',
                'due_date': (today + timedelta(days=7)).strftime('%Y-%m-%d'),
            })
        elif safety['balance_90d'] < red_line:
            months_left = safety['balance_90d'] / monthly_cost if monthly_cost > 0 else 999
            gap = red_line - safety['balance_90d']
            alerts.append({
                'level': 'warning',
                'level_text': '🟡 警告',
                'category': '现金流',
                'title': '90天现金流低于安全线',
                'message': f"90天预测余额 {safety['balance_90d']:,.0f} 元，仅{months_left:.1f}个月成本，低于5个月红线（缺口{gap:,.0f}元）",
                'action': '加强回款催收，控制支出，补充现金储备',
                'responsible': '财务经理',
                'due_date': (today + timedelta(days=14)).strftime('%Y-%m-%d'),
            })
        
        # 2. 资金缺口日期预警
        calendar_df = self.generate_cashflow_calendar(days=days, cash_reserve=current_balance)
        # 转换为字典列表以便遍历
        calendar = calendar_df.to_dict('records')
        negative_periods = [c for c in calendar if c['累计余额'] < 0]
        
        if negative_periods:
            first_negative = negative_periods[0]
            alerts.append({
                'level': 'danger',
                'level_text': '🔴 紧急',
                'category': '现金流',
                'title': '资金缺口预警',
                'message': f"预计 {first_negative['日期']} 首次出现资金缺口 {first_negative['累计余额']:,.0f} 元",
                'action': '提前安排融资或加速回款',
                'responsible': '财务总监',
                'due_date': first_negative['日期'],
            })
        
        return alerts
    
    def _get_collection_alerts_from_invoices(self, today: datetime) -> List[Dict]:
        """
        基于真实发票数据生成回款预警（更准确）
        """
        alerts = []
        
        if not hasattr(self, 'overdue_invoices_detail') or self.overdue_invoices_detail.empty:
            return alerts
        
        df = self.overdue_invoices_detail
        
        # 已逾期
        overdue_items = []
        for _, row in df.iterrows():
            overdue_items.append({
                'position_id': row.get('joborder_id', ''),
                'client': row.get('client_name', ''),
                'position': row.get('position_name', ''),
                'consultant': row.get('consultant', ''),
                'amount': row.get('pending_amount', 0),
                'est_date': row.get('due_date', ''),
                'days': -(row.get('overdue_days', 0)),
            })
        
        if overdue_items:
            total_overdue = sum(i['amount'] for i in overdue_items)
            max_overdue_days = max(abs(i['days']) for i in overdue_items)
            alerts.append({
                'level': 'danger',
                'level_text': '🔴 紧急',
                'category': '回款催收',
                'title': f'已逾期回款 {len(overdue_items)} 笔',
                'message': f"合计 {total_overdue:,.0f} 元，最长逾期 {max_overdue_days} 天",
                'action': '立即电话催收，必要时发律师函',
                'responsible': '对应顾问 + 财务',
                'due_date': today.strftime('%Y-%m-%d'),
                'items': overdue_items
            })
        
        return alerts
    
    def get_collection_alerts(self) -> List[Dict]:
        """
        获取回款相关预警
        优先使用真实发票数据（invoice表），如果没有则回退到offer日期推算
        """
        alerts = []
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # 优先使用真实发票逾期数据（如果已同步）
        if hasattr(self, 'overdue_invoices_detail') and not self.overdue_invoices_detail.empty:
            return self._get_collection_alerts_from_invoices(today)
        
        # 回退：使用offer日期推算（可能不准确）
        avg_cycle = self.get_historical_payment_cycle()
        offer_to_payment_days = self.AVG_OFFER_TO_ONBOARD_DAYS + avg_cycle
        
        overdue_items = []
        due_7d_items = []
        due_30d_items = []
        
        for p in self.positions:
            if not p.is_successful:
                continue
            # 已回款或部分回款的不算逾期
            if p.payment_status in ['已回款', '部分回款', '回款完成']:
                continue
            if not p.offer_date:
                continue
            
            expected_amount = p.actual_payment if p.actual_payment > 0 else p.fee_amount
            if expected_amount <= 0:
                continue
            
            payment_cycle = self.get_position_payment_cycle(p)
            otp_days = self.AVG_OFFER_TO_ONBOARD_DAYS + payment_cycle
            est_date = p.offer_date + timedelta(days=otp_days)
            days_until = (est_date - today).days
            
            item = {
                'position_id': p.position_id,
                'client': p.client_name,
                'position': p.position_name,
                'consultant': p.consultant,
                'amount': expected_amount,
                'est_date': est_date.strftime('%Y-%m-%d'),
                'days': days_until
            }
            
            if days_until < 0:
                overdue_items.append(item)
            elif days_until <= 7:
                due_7d_items.append(item)
            elif days_until <= 30:
                due_30d_items.append(item)
        
        # 已逾期预警
        if overdue_items:
            total_overdue = sum(i['amount'] for i in overdue_items)
            alerts.append({
                'level': 'danger',
                'level_text': '🔴 紧急',
                'category': '回款催收',
                'title': f'已逾期回款 {len(overdue_items)} 笔',
                'message': f"合计 {total_overdue:,.0f} 元，最长逾期 {abs(min(i['days'] for i in overdue_items))} 天",
                'action': '立即电话催收，必要时发律师函',
                'responsible': '对应顾问 + 财务',
                'due_date': today.strftime('%Y-%m-%d'),
                'items': overdue_items  # 所有逾期项目
            })
        
        # 7天内到期预警
        if due_7d_items:
            total_7d = sum(i['amount'] for i in due_7d_items)
            alerts.append({
                'level': 'warning',
                'level_text': '🟡 警告',
                'category': '回款催收',
                'title': f'7天内到期回款 {len(due_7d_items)} 笔',
                'message': f"合计 {total_7d:,.0f} 元",
                'action': '提前联系客户确认回款时间',
                'responsible': '对应顾问',
                'due_date': (today + timedelta(days=7)).strftime('%Y-%m-%d'),
                'items': due_7d_items
            })
        
        return alerts
    
    def get_consultant_alerts(self) -> List[Dict]:
        """
        获取顾问相关预警（只包含在职顾问）
        """
        alerts = []
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # 计算90天盈亏预测
        forecast_df = self.get_consultant_profit_forecast(forecast_days=90)
        
        if not forecast_df.empty:
            # 只保留在职顾问（状态码=2），排除已离职人员
            active_df = forecast_df[forecast_df['状态码'] == 2].copy()
            
            # 亏损顾问预警（只统计在职顾问）
            loss_consultants = active_df[active_df['回款利润'] < -50000]  # 亏损超5万
            for _, row in loss_consultants.iterrows():
                alerts.append({
                    'level': 'warning',
                    'level_text': '🟡 警告',
                    'category': '顾问绩效',
                    'title': f"顾问 {row['顾问']} Q1实际回款亏损",
                    'message': f"回款利润 {row['回款利润']:,.0f} 元，成本 {row['累计成本']:,.0f} 元",
                    'action': '评估是否需要PIP或优化',
                    'responsible': '团队负责人',
                    'due_date': (today + timedelta(days=30)).strftime('%Y-%m-%d'),
                })
            
            # 零回款顾问预警（只统计在职顾问）
            zero_revenue = active_df[
                (active_df['已回款'] == 0) & 
                (active_df['90天Offer待回'] == 0) &
                (active_df['90天Forecast'] == 0)
            ]
            for _, row in zero_revenue.iterrows():
                alerts.append({
                    'level': 'info',
                    'level_text': '🔵 提示',
                    'category': '顾问绩效',
                    'title': f"顾问 {row['顾问']} 未来90天无预期回款",
                    'message': f"实际回款、Offer待回、Forecast均为0，需关注该顾问的在途单推进情况",
                    'action': '检查Pipeline并跟进Offer进度',
                    'responsible': '团队负责人',
                    'due_date': (today + timedelta(days=14)).strftime('%Y-%m-%d'),
                })
        
        return alerts
    
    def get_all_alerts(self, current_balance: float = None) -> Dict[str, List[Dict]]:
        """
        获取所有预警分类
        
        Args:
            current_balance: 当前实际现金余额（用于现金流预警）
        """
        return {
            'cashflow': self.get_cashflow_alerts(current_balance=current_balance),
            'collection': self.get_collection_alerts(),
            'consultant': self.get_consultant_alerts(),
        }
    
    def get_alert_summary(self, current_balance: float = None) -> Dict:
        """
        获取预警汇总统计
        
        Args:
            current_balance: 当前实际现金余额（用于现金流预警）
        """
        all_alerts = self.get_all_alerts(current_balance=current_balance)
        
        danger_count = sum(
            1 for alerts in all_alerts.values() 
            for a in alerts if a['level'] == 'danger'
        )
        warning_count = sum(
            1 for alerts in all_alerts.values() 
            for a in alerts if a['level'] == 'warning'
        )
        info_count = sum(
            1 for alerts in all_alerts.values() 
            for a in alerts if a['level'] == 'info'
        )
        
        return {
            'danger': danger_count,
            'warning': warning_count,
            'info': info_count,
            'total': danger_count + warning_count + info_count,
            'by_category': {k: len(v) for k, v in all_alerts.items()},
        }

    
    def get_consultant_profit_details(self, consultant_name: str, forecast_days: int = 90) -> Dict:
        """
        获取顾问盈亏核算明细（用于与顾问沟通）
        
        Returns:
            包含以下明细的字典：
            - 90天回款明细列表
            - 90天Forecast明细列表  
            - 成本计算明细
            - 盈亏计算过程
        """
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        forecast_end = today + timedelta(days=forecast_days)
        
        # 顾问匹配函数
        def match_consultant(position_consultant, target_consultant):
            if not position_consultant:
                return False
            if position_consultant == target_consultant:
                return True
            if position_consultant.startswith(target_consultant):
                return True
            return False
        
        avg_cycle = self.get_historical_payment_cycle()
        offer_to_payment_days_avg = self.AVG_OFFER_TO_ONBOARD_DAYS + avg_cycle
        
        # 1. 90天回款明细（拆分：实际已回款 vs Offer未回款）
        actual_collection_details = []  # 实际已回款
        offer_pending_details = []  # Offer未回款
        
        for p in self.positions:
            if not match_consultant(p.consultant, consultant_name) or not p.is_successful:
                continue
            
            if p.payment_date:
                # 实际已回款
                expected_amount = p.actual_payment
                payment_date = p.payment_date
                status = "已确认回款"
                
                if today <= payment_date <= forecast_end:
                    actual_collection_details.append({
                        'position_id': p.position_id,
                        'client': p.client_name,
                        'position': p.position_name,
                        'expected_amount': expected_amount,
                        'payment_date': payment_date.strftime('%Y-%m-%d'),
                        'days_until': (payment_date - today).days,
                        'status': status
                    })
            elif p.offer_date and p.fee_amount > 0:
                # Offer未回款
                expected_amount = p.fee_amount
                payment_cycle = self.get_position_payment_cycle(p)
                offer_to_payment_days = self.AVG_OFFER_TO_ONBOARD_DAYS + payment_cycle
                payment_date = p.offer_date + timedelta(days=offer_to_payment_days)
                status = "已成单未回款"
                
                if today <= payment_date <= forecast_end:
                    offer_pending_details.append({
                        'position_id': p.position_id,
                        'client': p.client_name,
                        'position': p.position_name,
                        'expected_amount': expected_amount,
                        'payment_date': payment_date.strftime('%Y-%m-%d'),
                        'days_until': (payment_date - today).days,
                        'status': status
                    })
        
        # 合并用于展示（区分状态）
        collection_details = actual_collection_details + offer_pending_details
        
        # 2. Forecast明细
        forecast_details = []
        for f in self.forecast_positions:
            if not match_consultant(f.consultant, consultant_name):
                continue
            
            if f.expected_payment_date is None and f.expected_close_date:
                f.expected_payment_date = f.expected_close_date + timedelta(days=offer_to_payment_days_avg)
            
            if f.expected_payment_date and today <= f.expected_payment_date <= forecast_end:
                forecast_details.append({
                    'forecast_id': f.forecast_id,
                    'client': f.client_name,
                    'position': f.position_name,
                    'estimated_fee': f.estimated_fee,
                    'success_rate': f.success_rate,
                    'weighted_revenue': f.weighted_revenue,
                    'expected_payment_date': f.expected_payment_date.strftime('%Y-%m-%d'),
                    'days_until': (f.expected_payment_date - today).days,
                    'stage': f.stage
                })
        
        # 3. 成本计算（实时：年初至今实际在岗成本）
        period_start = datetime(2026, 1, 1)
        period_end = today
        period_cost = self._get_consultant_period_cost(consultant_name, period_start, period_end)
        
        if consultant_name in self.consultant_configs:
            monthly_salary = self.consultant_configs[consultant_name].get('monthly_salary', 15000)
        else:
            monthly_salary = self.config.get('consultant_monthly_salary', 15000)
        
        multiplier = self.config.get('salary_multiplier', 3.0)
        monthly_cost = monthly_salary * multiplier
        current_month = max(1, today.month)
        cost = period_cost if period_cost > 0 else monthly_cost * current_month  # fallback 年初至今
        
        # 4. 汇总计算（累计口径：全部实际回款 vs 全部Offer待回 vs 90天Forecast）
        # 全部实际已回款（优先使用 consultant_collections，更准）
        actual_collection = 0
        if hasattr(self, 'consultant_collections') and self.consultant_collections:
            for coll_name, coll_data in self.consultant_collections.items():
                if match_consultant(coll_name, consultant_name):
                    actual_collection = coll_data.get('total_received', 0)
                    break
        # fallback：从 positions 累加
        if actual_collection == 0:
            actual_collection = sum(p.actual_payment for p in self.positions 
                                   if match_consultant(p.consultant, consultant_name) 
                                   and p.is_successful 
                                   and p.payment_status in ['已回款', '部分回款', '回款完成'])
        # 全部Offer未回款：优先使用 invoiceassignment 的个人分配金额
        offer_pending = 0
        if hasattr(self, 'consultant_invoice_assignments') and self.consultant_invoice_assignments:
            for ia_name, ia_list in self.consultant_invoice_assignments.items():
                if match_consultant(ia_name, consultant_name):
                    for ia in ia_list:
                        # 排除已回款和已作废的发票
                        if ia['invoice_status'] not in ['Received', '回款完成', 'Reject']:
                            offer_pending += ia['assigned_amount']
        
        # fallback：从 positions 累加（尚未开票的 offer）
        if offer_pending == 0:
            offer_pending = sum(p.fee_amount for p in self.positions 
                               if match_consultant(p.consultant, consultant_name) 
                               and p.is_successful 
                               and p.payment_status not in ['已回款', '部分回款', '回款完成']
                               and p.offer_date and p.fee_amount > 0)
        total_collection = actual_collection + offer_pending
        total_forecast = sum(d['weighted_revenue'] for d in forecast_details)
        total_revenue = total_collection + total_forecast
        
        # 指标1：回款利润率 = (累计回款 - 累计成本) / 累计回款
        actual_profit = actual_collection - cost
        actual_margin_str = self._calc_margin_str(actual_collection, cost)
        
        # 指标2：Offer业绩余粮 = 累计Offer未回款 / 月成本
        offer_reserve_months = offer_pending / monthly_cost if monthly_cost > 0 else 0
        
        # 指标3：Forecast覆盖率 = (累计Offer未回款 + 未来3个月Forecast) / 6个月成本
        future_6m_cost = monthly_cost * 6
        forecast_coverage = ((offer_pending + total_forecast) / future_6m_cost) if future_6m_cost > 0 else 0
        
        return {
            'consultant_name': consultant_name,
            'forecast_days': forecast_days,
            'period': f"{today.strftime('%Y-%m-%d')} 至 {forecast_end.strftime('%Y-%m-%d')}",
            
            # 成本明细
            'cost_details': {
                'monthly_salary': monthly_salary,
                'salary_multiplier': multiplier,
                'monthly_cost': monthly_cost,
                'period_cost': cost,
                'calculation': f"累计实际成本 = {cost:,.0f}元 (月薪 {monthly_salary:,.0f} × {multiplier} × 年初至今{max(1, today.month)}个月)"
            },
            
            # 回款明细（拆分）
            'actual_collection_details': sorted(actual_collection_details, key=lambda x: x['days_until']),
            'actual_collection_count': len(actual_collection_details),
            'actual_collection': actual_collection,
            
            'offer_pending_details': sorted(offer_pending_details, key=lambda x: x['days_until']),
            'offer_pending_count': len(offer_pending_details),
            'offer_pending': offer_pending,
            
            'collection_details': sorted(collection_details, key=lambda x: x['days_until']),
            'collection_count': len(collection_details),
            'total_collection': total_collection,
            
            # Forecast明细
            'forecast_details': sorted(forecast_details, key=lambda x: x['days_until']),
            'forecast_count': len(forecast_details),
            'total_forecast': total_forecast,
            
            # 汇总（新口径）
            'actual_collection': actual_collection,
            'actual_profit': actual_profit,
            'actual_margin': actual_margin_str,
            
            'offer_pending': offer_pending,
            'offer_reserve_months': offer_reserve_months,
            
            'total_forecast': total_forecast,
            'future_6m_cost': future_6m_cost,
            'forecast_coverage': forecast_coverage,
            
            'period_cost': cost,
            
            # 计算过程
            'calculation_process': [
                f"【利润核算（指标1：回款利润率）】",
                f"  累计实际回款: {actual_collection:,.0f}元",
                f"  累计成本: {cost:,.0f}元",
                f"  利润: {actual_collection:,.0f} - {cost:,.0f} = {actual_profit:,.0f}元",
                f"  利润率: {actual_margin_str}",
                f"",
                f"【Offer业绩余粮（指标2：中期缓冲）】",
                f"  累计Offer未回款: {offer_pending:,.0f}元",
                f"  月成本: {monthly_cost:,.0f}元",
                f"  余粮: {offer_pending:,.0f} / {monthly_cost:,.0f} = {offer_reserve_months:.1f}个月",
                f"",
                f"【Forecast Pipeline覆盖（指标3：短中长期）】",
                f"  累计Offer未回款: {offer_pending:,.0f}元",
                f"  未来3个月Forecast: {len(forecast_details)}笔，合计 {total_forecast:,.0f}元",
                f"  覆盖分子 (Offer+Forecast): {offer_pending + total_forecast:,.0f}元",
                f"  未来6个月成本: {future_6m_cost:,.0f}元",
                f"  覆盖率: {forecast_coverage*100:.0f}%"
            ]
        }


    # ============ 财务状况分析模块 ============
    
    def get_position_real_mc_analysis(self) -> pd.DataFrame:
        """单职位真实边际贡献分析（使用财务数据）"""
        if not self.positions or not self.real_cost_records:
            return pd.DataFrame(columns=[
                '职位ID', '客户', '职位', '顾问', '回款', '真实工资', '真实报销',
                '真实固定', '直接成本', '真实总成本', '真实边际贡献', '周期天数'
            ])
        
        active_consultants = set()
        for name, config in self.consultant_configs.items():
            if config.get('is_active', True):
                active_consultants.add(name)
        if not active_consultants:
            active_consultants = set(p.consultant for p in self.positions if p.consultant)
        active_count = max(1, len(active_consultants))
        
        name_map = self._build_consultant_name_map()
        
        data = []
        for p in self.positions:
            end_date = p.payment_date or p.closed_date or datetime.now()
            aliases = []
            if p.consultant and p.consultant in name_map:
                aliases.append(name_map[p.consultant])
            costs = calculate_position_real_costs(
                position_id=p.position_id,
                consultant_name=p.consultant,
                client_name=p.client_name,
                start_date=p.created_date or end_date,
                end_date=end_date,
                all_records=self.real_cost_records,
                active_consultant_count=active_count,
                consultant_aliases=aliases
            )
            data.append({
                '职位ID': p.position_id,
                '客户': p.client_name,
                '职位': p.position_name,
                '顾问': p.consultant,
                '回款': p.actual_payment,
                '真实工资': costs['salary'],
                '真实报销': costs['reimburse'],
                '真实固定': costs['fixed'],
                '直接成本': costs['direct'],
                '真实总成本': costs['total'],
                '真实边际贡献': p.actual_payment - costs['total'],
                '周期天数': p.cycle_days,
            })
        
        return pd.DataFrame(data)
    
    def get_consultant_real_profit_analysis(self) -> pd.DataFrame:
        """顾问真实盈亏分析（使用财务数据）"""
        if not self.positions:
            return pd.DataFrame()
        
        active_consultants = []
        for name, config in self.consultant_configs.items():
            if config.get('is_active', True):
                active_consultants.append(name)
        if not active_consultants:
            active_consultants = list(set(p.consultant for p in self.positions if p.consultant))
        
        # 复用 get_consultant_profit_forecast 中的累计实际回款逻辑（含 payment_status 过滤和模糊匹配）
        profit_forecast_df = self.get_consultant_profit_forecast(forecast_days=3650)
        revenue_map = {}
        if not profit_forecast_df.empty and '累计实际回款' in profit_forecast_df.columns:
            revenue_map = dict(zip(profit_forecast_df['顾问'], profit_forecast_df['累计实际回款']))
        
        name_map = self._build_consultant_name_map()
        
        result = []
        for consultant in active_consultants:
            revenue = revenue_map.get(consultant, 0)
            aliases = []
            if consultant in name_map:
                aliases.append(name_map[consultant])
            costs = get_consultant_real_costs(
                consultant_name=consultant,
                all_records=self.real_cost_records,
                aliases=aliases,
            )
            total_cost = costs['total']
            profit = revenue - total_cost
            margin = (profit / revenue * 100) if revenue > 0 else 0
            
            result.append({
                '顾问': consultant,
                '累计回款': revenue,
                '真实工资': costs['salary'],
                '真实报销': costs['reimburse'],
                '真实总成本': total_cost,
                '真实利润': profit,
                '真实利润率': f"{margin:.1f}%" if revenue > 0 else '-',
            })
        
        return pd.DataFrame(result).sort_values('真实利润', ascending=False)
    
    def get_monthly_real_summary_df(self) -> pd.DataFrame:
        """月度财务状况汇总表"""
        if not self.positions:
            return pd.DataFrame()
        
        # 收集所有涉及的年月
        months = set()
        for p in self.positions:
            if p.payment_date:
                months.add((p.payment_date.year, p.payment_date.month))
        for r in self.real_cost_records:
            months.add((r.date.year, r.date.month))
        
        if not months:
            return pd.DataFrame()
        
        # 按月汇总回款
        monthly_revenue = defaultdict(float)
        for p in self.positions:
            if p.payment_date:
                monthly_revenue[(p.payment_date.year, p.payment_date.month)] += p.actual_payment
        
        data = []
        for ym in sorted(months):
            summary = calculate_monthly_real_summary(ym, self.real_cost_records)
            operating_cost = summary['salary'] + summary['reimburse'] + summary['fixed']
            data.append({
                '年月': f"{ym[0]}-{ym[1]:02d}",
                '回款': monthly_revenue.get(ym, 0),
                '真实工资': summary['salary'],
                '真实报销': summary['reimburse'],
                '真实固定': summary['fixed'],
                '年度奖金': summary['annual_bonus_2025'],
                '真实总成本': summary['total'],
                '经营总成本(不含奖金)': operating_cost,
                '真实利润': monthly_revenue.get(ym, 0) - summary['total'],
                '经营利润(不含奖金)': monthly_revenue.get(ym, 0) - operating_cost,
            })
        
        return pd.DataFrame(data)
    
    def get_real_cost_summary(self) -> Dict:
        """财务状况数据汇总"""
        if not self.real_cost_records:
            return {
                'has_data': False,
                'salary': 0,
                'reimburse': 0,
                'fixed': 0,
                'total': 0,
            }
        
        salary = sum(r.amount for r in self.real_cost_records if r.category == 'salary')
        reimburse = sum(r.amount for r in self.real_cost_records if r.category == 'reimburse')
        fixed = sum(r.amount for r in self.real_cost_records if r.category == 'fixed' and r.sub_category != 'annual_bonus_2025')
        annual_bonus_2025 = sum(r.amount for r in self.real_cost_records if r.sub_category == 'annual_bonus_2025')
        operating_total = salary + reimburse + fixed
        
        return {
            'has_data': True,
            'salary': salary,
            'reimburse': reimburse,
            'fixed': fixed,
            'annual_bonus_2025': annual_bonus_2025,
            'operating_total': operating_total,
            'total': operating_total + annual_bonus_2025,
            'record_count': len(self.real_cost_records),
        }
