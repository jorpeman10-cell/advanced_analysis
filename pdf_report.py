"""
股东报告 PDF 生成模块
生成专业的猎头财务分析股东报告
"""

import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
from fpdf import FPDF


# ============ 字体配置 ============
FONT_PATHS = {
    'regular': r"C:\Windows\Fonts\msyh.ttc",
    'bold': r"C:\Windows\Fonts\msyhbd.ttc",
    'light': r"C:\Windows\Fonts\msyhl.ttc",
}
# 备用字体
if not os.path.exists(FONT_PATHS['regular']):
    FONT_PATHS = {
        'regular': r"C:\Windows\Fonts\simhei.ttf",
        'bold': r"C:\Windows\Fonts\simhei.ttf",
        'light': r"C:\Windows\Fonts\simhei.ttf",
    }

# Matplotlib 中文字体配置
plt.rcParams['font.family'] = ['Microsoft YaHei', 'SimHei', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False


class ShareholderReportPDF(FPDF):
    """股东报告 PDF 类"""
    
    def __init__(self):
        super().__init__(orientation='P', unit='mm', format='A4')
        self.set_auto_page_break(auto=True, margin=15)
        self._register_fonts()
        self.primary_color = (26, 54, 93)      # #1a365d
        self.secondary_color = (44, 82, 130)   # #2c5282
        self.accent_green = (5, 150, 105)      # #059669
        self.accent_red = (220, 38, 38)        # #dc2626
        self.accent_orange = (217, 119, 6)     # #d97706
        self.text_dark = (45, 55, 72)          # #2d3748
        self.text_gray = (113, 128, 150)       # #718096
        self.bg_light = (247, 250, 252)        # #f7fafc
        
    def _register_fonts(self):
        """注册中文字体"""
        try:
            self.add_font('YaHei', '', FONT_PATHS['regular'], uni=True)
            self.add_font('YaHei', 'B', FONT_PATHS['bold'], uni=True)
        except Exception as e:
            print(f"字体加载警告: {e}")
            # fpdf2 会回退到内置字体
    
    def _set_font(self, style='', size=10):
        """设置字体"""
        self.set_font('YaHei', style, size)
    
    def _color(self, r, g, b):
        """设置颜色"""
        self.set_text_color(r, g, b)
    
    def _draw_header(self, title):
        """绘制页面头部"""
        self.set_fill_color(*self.primary_color)
        self.rect(0, 0, 210, 12, style='F')
        self._set_font('', 8)
        self._color(255, 255, 255)
        self.set_xy(10, 4)
        self.cell(0, 5, f'猎头财务分析股东报告  |  {title}', ln=True)
        self._color(*self.text_dark)
        self.ln(3)
    
    def _draw_footer(self):
        """绘制页面底部"""
        self.set_y(-15)
        self._set_font('', 8)
        self._color(*self.text_gray)
        self.cell(0, 5, f'生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M")}  |   confidential - internal use only', align='C')
    
    def _section_title(self, title, subtitle=''):
        """章节标题"""
        self.ln(4)
        self._set_font('B', 14)
        self._color(*self.primary_color)
        self.cell(0, 8, title, ln=True)
        if subtitle:
            self._set_font('', 9)
            self._color(*self.text_gray)
            self.cell(0, 5, subtitle, ln=True)
        self.set_draw_color(226, 232, 240)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(3)
    
    def _kpi_box(self, x, y, w, label, value, color_type='normal', note=''):
        """绘制 KPI 卡片"""
        colors = {
            'normal': self.primary_color,
            'green': self.accent_green,
            'red': self.accent_red,
            'orange': self.accent_orange,
        }
        c = colors.get(color_type, self.primary_color)
        
        # 背景
        self.set_fill_color(247, 250, 252)
        self.rect(x, y, w, 22, style='F')
        # 顶部色条
        self.set_fill_color(*c)
        self.rect(x, y, w, 1.5, style='F')
        
        # 标签
        self.set_xy(x + 2, y + 3)
        self._set_font('', 8)
        self._color(*self.text_gray)
        self.cell(w - 4, 5, label, ln=True)
        
        # 数值
        self.set_xy(x + 2, y + 9)
        self._set_font('B', 14)
        self._color(*c)
        self.cell(w - 4, 7, value, ln=True)
        
        # 注释
        if note:
            self.set_xy(x + 2, y + 17)
            self._set_font('', 7)
            self._color(*self.text_gray)
            self.cell(w - 4, 4, note, ln=True)
    
    def _table_row(self, cols, widths, aligns=None, bold=False, fill=False, bg_color=None):
        """绘制表格行"""
        if aligns is None:
            aligns = ['L'] * len(cols)
        if bg_color:
            self.set_fill_color(*bg_color)
        
        h = 6
        start_x = self.get_x()
        start_y = self.get_y()
        
        for i, (text, w, align) in enumerate(zip(cols, widths, aligns)):
            self.set_xy(start_x + sum(widths[:i]), start_y)
            self._set_font('B' if bold else '', 8)
            if fill or bg_color:
                self.cell(w, h, str(text), border='B', align=align, fill=True)
            else:
                self.cell(w, h, str(text), border='B', align=align)
        
        self.set_xy(start_x, start_y + h)
    
    def add_cover(self, company_name='TSTAR CONSULTING', report_date=None):
        """封面页"""
        self.add_page()
        
        # 大背景色块
        self.set_fill_color(*self.primary_color)
        self.rect(0, 0, 210, 120, style='F')
        
        # 公司名
        self.set_y(45)
        self._set_font('', 12)
        self._color(160, 174, 192)
        self.cell(0, 8, company_name, align='C', ln=True)
        
        # 报告标题
        self._set_font('B', 28)
        self._color(255, 255, 255)
        self.cell(0, 15, '财务分析股东报告', align='C', ln=True)
        
        # 副标题
        self._set_font('', 11)
        self._color(144, 205, 244)
        self.cell(0, 8, '猎头业务经营分析与现金流评估', align='C', ln=True)
        
        # 日期
        if report_date is None:
            report_date = datetime.now().strftime('%Y年%m月%d日')
        self.set_y(100)
        self._set_font('', 10)
        self._color(160, 174, 192)
        self.cell(0, 8, report_date, align='C', ln=True)
        
        # 底部信息
        self.set_y(160)
        self._set_font('', 9)
        self._color(*self.text_gray)
        self.cell(0, 6, '本报告基于 Gllue 数据库实时数据生成', align='C', ln=True)
        self.cell(0, 6, '包含现金流预测、顾问绩效、回款逾期等核心经营指标', align='C', ln=True)
        self.cell(0, 6, '机密文件 - 仅供内部股东审阅', align='C', ln=True)
    
    def add_executive_summary(self, analyzer):
        """执行摘要页"""
        self.add_page()
        self._draw_header('执行摘要')
        
        today = datetime.now()
        cash_analysis = analyzer.get_cash_safety_analysis(
            analyzer.config.get('cash_reserve', 1800000)
        )
        
        # 计算关键指标
        collected = cash_analysis.get('collected_revenue', 0)
        monthly_cost = cash_analysis.get('monthly_cost', 0)
        balance_90d = cash_analysis.get('balance_90d', 0)
        runway = cash_analysis.get('runway_months', 0)
        overdue = getattr(analyzer, 'overdue_from_invoices', 0)
        
        forecast_df = analyzer.get_consultant_profit_forecast(forecast_days=90)
        total_pipeline = 0
        if not forecast_df.empty:
            total_pipeline = forecast_df['累计实际回款'].sum() + forecast_df['累计Offer待回'].sum() + forecast_df['累计Forecast'].sum()
        
        # KPI 行1
        self._kpi_box(10, 20, 45, '本年已回款', self._fmt_currency(collected), 'green')
        self._kpi_box(58, 20, 45, '90天预计余额', self._fmt_currency(balance_90d), 
                     'green' if balance_90d > monthly_cost * 3 else 'orange' if balance_90d > 0 else 'red')
        self._kpi_box(106, 20, 45, '资金跑道', f'{runway:.1f}个月', 
                     'green' if runway >= 6 else 'orange' if runway >= 3 else 'red')
        self._kpi_box(154, 20, 45, '逾期回款', self._fmt_currency(overdue), 
                     'red' if overdue > 0 else 'green')
        
        self.set_y(48)
        
        # KPI 行2
        if not forecast_df.empty:
            profit = forecast_df['回款利润'].sum()
            offer_pending = forecast_df['累计Offer待回'].sum()
            self._kpi_box(10, 48, 45, '回款总利润', self._fmt_currency(profit), 
                         'green' if profit > 0 else 'red')
            self._kpi_box(58, 48, 45, '累计Offer待回', self._fmt_currency(offer_pending), 'normal')
            self._kpi_box(106, 48, 45, 'Pipeline总计', self._fmt_currency(total_pipeline), 'normal')
            low_coverage = (forecast_df['Forecast覆盖数值'] < 0.5).sum()
            self._kpi_box(154, 48, 45, 'Pipeline不足顾问', f'{low_coverage}人', 
                         'red' if low_coverage > 0 else 'green')
        
        self.set_y(78)
        
        # 文字摘要
        self._section_title('经营摘要', '基于当前数据的综合评估')
        
        status_90d = cash_analysis.get('status_90d', '未知')
        status_text = {
            'Safe': '现金流状况良好，90天内无资金风险',
            'Below Safety Line': '现金流处于警戒区间，需关注回款进度',
            'Danger': '现金流存在缺口风险，建议立即采取催收和成本控制措施'
        }.get(status_90d, status_90d)
        
        summary_lines = [
            f'1. 现金流状况：{status_text}。当前资金跑道约 {runway:.1f} 个月。',
            f'2. 回款情况：本年已回款 {self._fmt_currency(collected)}，逾期金额 {self._fmt_currency(overdue)}。',
        ]
        
        if not forecast_df.empty:
            active_df = forecast_df[forecast_df['状态码'] == 2] if '状态码' in forecast_df.columns else forecast_df
            avg_reserve = active_df['Offer余粮(月)'].mean() if len(active_df) > 0 else 0
            summary_lines.append(f'3. 顾问储备：平均Offer余粮 {avg_reserve:.1f} 个月，{"充足" if avg_reserve >= 6 else "需关注" if avg_reserve >= 3 else "不足"}。')
            summary_lines.append(f'4. Pipeline总量：{self._fmt_currency(total_pipeline)}，包含已回款、Offer待回及Forecast预期。')
        
        for line in summary_lines:
            self._set_font('', 10)
            self._color(*self.text_dark)
            self.multi_cell(0, 6, line)
            self.ln(1)
    
    def add_cashflow_analysis(self, analyzer):
        """现金流分析页"""
        self.add_page()
        self._draw_header('现金流分析')
        
        cash_reserve = analyzer.config.get('cash_reserve', 1800000)
        cash_analysis = analyzer.get_cash_safety_analysis(cash_reserve)
        
        # KPI
        self._kpi_box(10, 20, 45, '当前现金储备', self._fmt_currency(cash_reserve), 'normal')
        self._kpi_box(58, 20, 45, '月固定成本', self._fmt_currency(cash_analysis.get('monthly_cost', 0)), 'normal')
        self._kpi_box(106, 20, 45, '90天预计余额', self._fmt_currency(cash_analysis.get('balance_90d', 0)),
                     'green' if cash_analysis.get('balance_90d', 0) > cash_analysis.get('monthly_cost', 0) * 3 else 'orange')
        self._kpi_box(154, 20, 45, '180天预计余额', self._fmt_currency(cash_analysis.get('balance_180d', 0)),
                     'green' if cash_analysis.get('balance_180d', 0) > 0 else 'red')
        
        self.set_y(50)
        self._section_title('现金流恒等式', '90天 / 180天预测')
        
        # 公式说明
        self._set_font('', 9)
        self._color(*self.text_dark)
        self.cell(0, 6, f'90天: 期初余额 {self._fmt_currency(cash_reserve)} + 90天回款 {self._fmt_currency(cash_analysis.get("future_90d_collected", 0))} + Forecast {self._fmt_currency(cash_analysis.get("forecast_90d", 0))} - 3个月成本 = {self._fmt_currency(cash_analysis.get("balance_90d", 0))}', ln=True)
        self.cell(0, 6, f'180天: 期初余额 + 180天回款 {self._fmt_currency(cash_analysis.get("future_180d_collected", 0))} + Forecast {self._fmt_currency(cash_analysis.get("forecast_180d", 0))} + 逾期 {self._fmt_currency(cash_analysis.get("overdue_collected", 0))} - 6个月成本 = {self._fmt_currency(cash_analysis.get("balance_180d", 0))}', ln=True)
        
        self.ln(3)
        
        # 半月现金流表格
        self._section_title('未来现金流明细（半月汇总）')
        biweekly = analyzer.generate_biweekly_cashflow_calendar(periods=6, cash_reserve=cash_reserve)
        if not biweekly.empty:
            self._draw_dataframe(biweekly.head(8), max_width=190)
    
    def add_collection_analysis(self, analyzer, db_client=None):
        """回款与逾期分析页"""
        self.add_page()
        self._draw_header('回款与逾期分析')
        
        today = datetime.now()
        overdue_detail = getattr(analyzer, 'overdue_invoices_detail', None)
        overdue_amount = getattr(analyzer, 'overdue_from_invoices', 0)
        
        # 尝试从数据库获取最新数据
        if overdue_detail is None or overdue_detail.empty:
            try:
                from gllue_db_client import GllueDBClient
                import db_config_manager
                if db_config_manager.has_config():
                    dbc = GllueDBClient(db_config_manager.get_gllue_db_config())
                    overdue_detail = dbc.get_overdue_invoices_detail(cutoff_date=today)
                    overdue_amount = dbc.get_overdue_invoices_amount(cutoff_date=today)
            except Exception:
                pass
        
        # KPI
        self._kpi_box(10, 20, 60, '逾期回款金额', self._fmt_currency(overdue_amount), 
                     'red' if overdue_amount > 0 else 'green')
        self._kpi_box(75, 20, 60, '逾期笔数', f'{len(overdue_detail) if overdue_detail is not None else 0}笔', 
                     'red' if (overdue_detail is not None and len(overdue_detail) > 0) else 'green')
        
        # 顾问回款统计
        collections = getattr(analyzer, 'consultant_collections', {})
        total_collected = 0
        if collections:
            for v in collections.values():
                if isinstance(v, dict):
                    total_collected += v.get('total_received', 0)
                else:
                    total_collected += v
        self._kpi_box(140, 20, 60, '已分配回款', self._fmt_currency(total_collected), 'green')
        
        self.set_y(50)
        
        if overdue_detail is not None and not overdue_detail.empty:
            self._section_title('逾期发票明细', '基于真实发票数据')
            display_cols = ['client_name', 'job_title', 'consultants', 'pending_amount', 'overdue_days']
            if all(c in overdue_detail.columns for c in display_cols):
                df_show = overdue_detail[display_cols].copy()
                df_show.columns = ['客户', '项目', '负责人', '金额', '逾期天数']
                self._draw_dataframe(df_show, max_width=190)
            else:
                self._draw_dataframe(overdue_detail.head(15), max_width=190)
        else:
            self._section_title('逾期情况')
            self._set_font('', 10)
            self._color(*self.text_gray)
            self.cell(0, 8, '✅ 当前无逾期回款（基于最新发票数据）', ln=True)
        
        # 客户历史账期统计
        self.ln(3)
        self._section_title('客户历史账期统计', '用于信用评估和催收参考')
        try:
            if db_client is None:
                from gllue_db_client import GllueDBClient
                import db_config_manager
                if db_config_manager.has_config():
                    db_client = GllueDBClient(db_config_manager.get_gllue_db_config())
            if db_client:
                stats = db_client.get_client_payment_stats()
                if stats is not None and not stats.empty:
                    self._draw_dataframe(stats.head(15), max_width=190)
        except Exception:
            self._set_font('', 9)
            self._color(*self.text_gray)
            self.cell(0, 6, '暂无客户历史账期数据', ln=True)
    
    def add_consultant_analysis(self, analyzer):
        """顾问绩效分析页"""
        self.add_page()
        self._draw_header('顾问绩效分析')
        
        forecast_df = analyzer.get_consultant_profit_forecast(forecast_days=90)
        if forecast_df.empty:
            self._set_font('', 10)
            self._color(*self.text_gray)
            self.cell(0, 8, '暂无足够顾问数据', ln=True)
            return
        
        # KPI
        actual_total = forecast_df['已回款'].sum()
        profit_total = forecast_df['回款利润'].sum()
        offer_total = forecast_df['累计Offer待回'].sum()
        active_df = forecast_df[forecast_df['状态码'] == 2] if '状态码' in forecast_df.columns else forecast_df
        avg_reserve = active_df['Offer余粮(月)'].mean() if len(active_df) > 0 else 0
        
        self._kpi_box(10, 20, 45, '已回款', self._fmt_currency(actual_total), 'green')
        self._kpi_box(58, 20, 45, '回款利润', self._fmt_currency(profit_total),
                     'green' if profit_total > 0 else 'red')
        self._kpi_box(106, 20, 45, 'Offer待回', self._fmt_currency(offer_total), 'normal')
        self._kpi_box(154, 20, 45, '平均余粮', f'{avg_reserve:.1f}月',
                     'green' if avg_reserve >= 6 else 'orange' if avg_reserve >= 3 else 'red')
        
        self.set_y(50)
        self._section_title('顾问明细')
        
        # 简化显示列
        display_cols = ['顾问', '已回款', '累计成本', '回款利润', '回款利润率', 
                       '90天Offer待回', 'Offer余粮(月)', 'Forecast覆盖率', '风险评级']
        available_cols = [c for c in display_cols if c in forecast_df.columns]
        if available_cols:
            df_show = forecast_df[available_cols].head(20).copy()
            self._draw_dataframe(df_show, max_width=190)
        else:
            self._draw_dataframe(forecast_df.head(15), max_width=190)
        
        # 风险分布
        self.ln(3)
        self._section_title('风险评级分布')
        if '风险评级' in forecast_df.columns:
            risk_counts = forecast_df['风险评级'].value_counts()
            risk_text = '  |  '.join([f"{k}: {v}人" for k, v in risk_counts.items()])
            self._set_font('', 10)
            self._color(*self.text_dark)
            self.cell(0, 8, risk_text, ln=True)
    
    def add_pipeline_analysis(self, analyzer):
        """Pipeline 分析页"""
        self.add_page()
        self._draw_header('Pipeline 与 Forecast')
        
        forecast = analyzer.get_forecast_analysis()
        if forecast.empty:
            self._set_font('', 10)
            self._color(*self.text_gray)
            self.cell(0, 8, '暂无 Forecast 数据', ln=True)
            return
        
        summary = analyzer.get_forecast_summary()
        
        self._kpi_box(10, 20, 60, '在途单总数', f"{summary.get('total_forecasts', 0)}单", 'normal')
        self._kpi_box(75, 20, 60, '预期总费用', self._fmt_currency(summary.get('total_estimated_fee', 0)), 'normal')
        self._kpi_box(140, 20, 60, '加权预期收入', self._fmt_currency(summary.get('weighted_revenue', 0)), 'green')
        
        self.set_y(50)
        self._section_title('Forecast 明细')
        self._draw_dataframe(forecast.head(15), max_width=190)
    
    def add_risk_alerts(self, analyzer):
        """风险预警页"""
        self.add_page()
        self._draw_header('风险预警汇总')
        
        cash_reserve = analyzer.config.get('cash_reserve', 1800000)
        all_alerts = analyzer.get_all_alerts(cash_reserve)
        
        # 扁平化所有预警
        flat_alerts = []
        for category, alerts in all_alerts.items():
            for alert in alerts:
                alert['_category'] = category
                flat_alerts.append(alert)
        
        total_danger = sum(1 for a in flat_alerts if a.get('level') == 'danger')
        total_warning = sum(1 for a in flat_alerts if a.get('level') == 'warning')
        
        self._kpi_box(10, 20, 60, '严重预警', f'{total_danger}项', 'red' if total_danger > 0 else 'green')
        self._kpi_box(75, 20, 60, '一般预警', f'{total_warning}项', 'orange' if total_warning > 0 else 'green')
        
        self.set_y(50)
        
        if flat_alerts:
            self._section_title('预警详情')
            for alert in flat_alerts[:25]:
                level = alert.get('level', 'info')
                colors = {'danger': self.accent_red, 'warning': self.accent_orange, 'info': self.secondary_color}
                c = colors.get(level, self.text_gray)
                
                self._set_font('B', 9)
                self._color(*c)
                title = alert.get('title', '')
                level_text = alert.get('level_text', level.upper())
                self.cell(0, 6, f"[{level_text}] {title}", ln=True)
                
                self._set_font('', 8)
                self._color(*self.text_dark)
                for item in alert.get('items', []):
                    if isinstance(item, dict):
                        # 格式化为可读字符串
                        parts = []
                        if 'client' in item:
                            parts.append(f"{item['client']}")
                        if 'position' in item:
                            parts.append(f"{item['position']}")
                        if 'consultant' in item:
                            parts.append(f"顾问:{item['consultant']}")
                        if 'amount' in item:
                            parts.append(f"金额:{self._fmt_currency(item['amount'])}")
                        if 'days' in item:
                            days = item['days']
                            parts.append(f"逾期{abs(days)}天" if days < 0 else f"还剩{days}天")
                        text = ' | '.join(parts)
                    else:
                        text = str(item)
                    self.set_x(12)
                    self.multi_cell(185, 5, f"- {text}")
                self.ln(1)
        else:
            self._section_title('预警状态')
            self._set_font('', 10)
            self._color(self.accent_green[0], self.accent_green[1], self.accent_green[2])
            self.cell(0, 8, '当前无风险预警', ln=True)
    
    def _draw_dataframe(self, df, max_width=190):
        """在 PDF 中绘制 DataFrame 表格"""
        if df.empty:
            self._set_font('', 9)
            self._color(*self.text_gray)
            self.cell(0, 6, '（无数据）', ln=True)
            return
        
        # 格式化
        df = df.copy()
        for col in df.columns:
            col_lower = str(col).lower()
            # 百分比列特殊处理
            if 'rate' in col_lower or 'rate' in col_lower:
                df[col] = df[col].apply(lambda x: f'{x:.0f}%' if pd.notna(x) else '')
            elif df[col].dtype in ['float64', 'float32']:
                df[col] = df[col].apply(lambda x: f'{x:,.0f}' if pd.notna(x) else '')
            elif df[col].dtype == 'int64':
                df[col] = df[col].apply(lambda x: f'{x:,}' if pd.notna(x) else '')
        
        # 列宽分配：基于实际文本宽度（中文字符按1.8倍宽度计算）
        self._set_font('', 8)
        widths = []
        for col in df.columns:
            header_text = str(col)
            header_width = self.get_string_width(header_text)
            max_data_width = df[col].astype(str).apply(lambda x: self.get_string_width(str(x))).max()
            needed = max(header_width, max_data_width) + 4  # 4mm padding
            widths.append(needed)
        
        # 如果总宽度超过限制，按比例压缩
        total_w = sum(widths)
        if total_w > max_width:
            scale = max_width / total_w
            widths = [w * scale for w in widths]
        
        # 表头
        self.set_fill_color(247, 250, 252)
        self._table_row(df.columns.tolist(), widths, bold=True, fill=True)
        
        # 数据行
        for _, row in df.iterrows():
            self._table_row([str(v) for v in row.values], widths)
            if self.get_y() > 270:
                self.add_page()
                self._table_row(df.columns.tolist(), widths, bold=True, fill=True)
    
    def _fmt_currency(self, value):
        """格式化金额"""
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return '¥0'
        if abs(value) >= 10000:
            return f'¥{value/10000:.1f}万'
        return f'¥{value:,.0f}'


def generate_shareholder_report(analyzer, output_path=None, include_db_data=True):
    """
    生成股东报告 PDF
    
    Args:
        analyzer: AdvancedRecruitmentAnalyzer 实例
        output_path: 输出路径，默认生成临时文件
        include_db_data: 是否尝试从数据库获取最新数据
    
    Returns:
        output_path: 生成的 PDF 路径
    """
    if output_path is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        output_path = f"股东报告_{timestamp}.pdf"
    
    pdf = ShareholderReportPDF()
    
    # 封面
    pdf.add_cover(report_date=datetime.now().strftime('%Y年%m月%d日'))
    
    # 执行摘要
    pdf.add_executive_summary(analyzer)
    
    # 现金流分析
    pdf.add_cashflow_analysis(analyzer)
    
    # 回款与逾期
    db_client = None
    if include_db_data:
        try:
            from gllue_db_client import GllueDBClient
            import db_config_manager
            if db_config_manager.has_config():
                db_client = GllueDBClient(db_config_manager.get_gllue_db_config())
        except Exception:
            pass
    pdf.add_collection_analysis(analyzer, db_client=db_client)
    
    # 顾问绩效
    pdf.add_consultant_analysis(analyzer)
    
    # Pipeline
    pdf.add_pipeline_analysis(analyzer)
    
    # 风险预警
    pdf.add_risk_alerts(analyzer)
    
    # 输出
    pdf.output(output_path)
    return output_path


if __name__ == '__main__':
    # 测试
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from models import AdvancedRecruitmentAnalyzer
    
    analyzer = AdvancedRecruitmentAnalyzer()
    path = generate_shareholder_report(analyzer)
    print(f"报告已生成: {path}")
