#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
文件夹自动监控与导入模块
支持轮询检测 watched/ 目录下的 Excel/CSV 文件并自动导入
"""

import os
import json
import hashlib
import pandas as pd
from datetime import datetime
from typing import List, Dict, Optional


# 支持的文件扩展名
SUPPORTED_EXTS = ('.xlsx', '.xls', '.csv')

# 导入日志文件名
IMPORT_LOG_NAME = 'import_log.json'

# 目录 -> 数据类型映射（用于路径匹配）
DIR_TYPE_MAP = {
    'deals': 'deals',
    'deal': 'deals',
    '成单': 'deals',
    'orders': 'deals',
    'consultants': 'consultants',
    'consultant': 'consultants',
    '顾问': 'consultants',
    '人员': 'consultants',
    'forecast': 'forecast',
    '预测': 'forecast',
    'real_finance': 'real_finance',
    'real': 'real_finance',
    '真实财务': 'real_finance',
    '财务状况': 'real_finance',
    'finance': 'real_finance',
    'salary': 'salary',
    '工资': 'salary',
    'reimburse': 'reimburse',
    '报销': 'reimburse',
    'fixed': 'fixed',
    '固定': 'fixed',
    'financial_statements': 'financial_statements',
    'financial': 'financial_statements',
    'statements': 'financial_statements',
    '财务报表': 'financial_statements',
    '财报': 'financial_statements',
}

# 文件名关键词 -> 子类型映射（用于文件名匹配）
FILENAME_SUBTYPE_KEYWORDS = {
    'salary': 'salary',
    '工资': 'salary',
    '薪资': 'salary',
    '薪酬': 'salary',
    'payroll': 'salary',
    'reimburse': 'reimburse',
    '报销': 'reimburse',
    '费用': 'reimburse',
    'expense': 'reimburse',
    'fixed': 'fixed',
    '固定': 'fixed',
    '奖金': 'fixed',
    'bonus': 'fixed',
    '房租': 'fixed',
    'rent': 'fixed',
    'admin': 'fixed',
    '行政': 'fixed',
    'deal': 'deals',
    '成单': 'deals',
    '订单': 'deals',
    'placement': 'deals',
    'consultant': 'consultants',
    '顾问': 'consultants',
    '人员': 'consultants',
    'forecast': 'forecast',
    '预测': 'forecast',
    '资产负债表': 'financial_statements',
    'balance_sheet': 'financial_statements',
    '利润表': 'financial_statements',
    'income_statement': 'financial_statements',
    'profit_loss': 'financial_statements',
    '现金流量表': 'financial_statements',
    'cash_flow': 'financial_statements',
}


def _get_file_fingerprint(path: str) -> str:
    """基于文件大小和修改时间生成简单指纹"""
    stat = os.stat(path)
    return f"{stat.st_size}_{stat.st_mtime}"


def _detect_file_type(rel_path: str) -> Optional[str]:
    """
    根据相对路径和文件名判断文件类型
    返回: deals | consultants | forecast | salary | reimburse | fixed | None
    """
    lower_path = rel_path.lower()
    parts = lower_path.replace('\\', '/').split('/')
    filename = parts[-1] if parts else ''
    
    # 1. 先根据文件名关键词判断（优先级最高）
    for keyword, subtype in FILENAME_SUBTYPE_KEYWORDS.items():
        if keyword in filename:
            return subtype
    
    # 2. 根据目录名判断
    for part in parts[:-1]:
        for dir_key, dir_type in DIR_TYPE_MAP.items():
            if dir_key in part:
                if dir_type == 'real_finance':
                    # 真实财务目录下如果没有文件名关键词，无法确定子类型
                    return None
                return dir_type
    
    return None


def _load_import_log(base_path: str) -> Dict:
    """加载导入日志"""
    log_path = os.path.join(base_path, IMPORT_LOG_NAME)
    if os.path.exists(log_path):
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {'files': {}}


def _save_import_log(base_path: str, log: Dict):
    """保存导入日志"""
    log_path = os.path.join(base_path, IMPORT_LOG_NAME)
    try:
        with open(log_path, 'w', encoding='utf-8') as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存导入日志失败: {e}")


def _is_file_locked(path: str) -> bool:
    """检查文件是否被其他进程锁定（尝试重命名到临时名）"""
    import tempfile
    tmp_path = path + '.tmpcheck'
    try:
        os.rename(path, tmp_path)
        os.rename(tmp_path, path)
        return False
    except (PermissionError, OSError):
        return True


def _read_dataframe(path: str) -> Optional[pd.DataFrame]:
    """读取 Excel 或 CSV 文件为 DataFrame"""
    try:
        lower = path.lower()
        if lower.endswith('.csv'):
            # 尝试多种编码
            for encoding in ['utf-8-sig', 'gbk', 'gb2312', 'utf-8']:
                try:
                    return pd.read_csv(path, encoding=encoding)
                except Exception:
                    continue
            return None
        else:
            return pd.read_excel(path)
    except Exception as e:
        print(f"读取文件失败 {path}: {e}")
        return None


def scan_and_import(analyzer, base_path: str) -> List[Dict]:
    """
    扫描 watched 目录并自动导入新文件
    
    Args:
        analyzer: AdvancedRecruitmentAnalyzer 实例
        base_path: watched 目录的绝对路径
    
    Returns:
        导入结果列表，每个元素包含 file, type, status, message
    """
    results = []
    
    if not os.path.exists(base_path):
        os.makedirs(base_path, exist_ok=True)
    
    # 首先扫描财务报表（special handling）
    fs_results = scan_financial_statements(base_path)
    results.extend(fs_results)
    
    log = _load_import_log(base_path)
    
    # 遍历所有文件
    for root, dirs, files in os.walk(base_path):
        # 跳过 backup 目录和 financial_statements 目录（已在上面单独处理）
        dirs[:] = [d for d in dirs if d.lower() not in ('backup', 'financial_statements')]
        files = [f for f in files if f != IMPORT_LOG_NAME and not f.startswith('~$') and f.lower().endswith(SUPPORTED_EXTS)]
        # 跳过已知的旧汇总/无效文件
        files = [f for f in files if '预算' not in f and '实际' not in f]
        
        for filename in files:
            full_path = os.path.join(root, filename)
            rel_path = os.path.relpath(full_path, base_path)
            fingerprint = _get_file_fingerprint(full_path)
            
            # 检查文件是否被锁定
            if _is_file_locked(full_path):
                results.append({
                    'file': rel_path,
                    'type': 'unknown',
                    'status': 'skipped',
                    'message': '文件正被其他程序使用中，请关闭后重试'
                })
                continue
            
            # 检查是否已经导入过且未变化
            existing = log['files'].get(rel_path, {})
            if existing.get('fingerprint') == fingerprint:
                continue
            
            file_type = _detect_file_type(rel_path)
            if not file_type:
                results.append({
                    'file': rel_path,
                    'type': 'unknown',
                    'status': 'skipped',
                    'message': '无法识别文件类型，请确认文件名或存放目录'
                })
                continue
            
            df = _read_dataframe(full_path)
            if df is None or df.empty:
                results.append({
                    'file': rel_path,
                    'type': file_type,
                    'status': 'failed',
                    'message': '文件读取失败或为空'
                })
                continue
            
            # 执行导入
            try:
                if file_type == 'deals':
                    analyzer.load_positions_from_dataframe(df)
                elif file_type == 'consultants':
                    analyzer.consultant_configs = {}
                    for idx, row in df.iterrows():
                        name = row.get('name')
                        if pd.notna(name):
                            salary = float(row['base_salary']) if pd.notna(row.get('base_salary')) else 20000
                            is_active = bool(row.get('is_active', True))
                            avg_positions = 6
                            if pd.notna(row.get('avg_positions')):
                                try:
                                    avg_positions = int(row['avg_positions'])
                                except Exception:
                                    pass
                            
                            join_date = None
                            for col in ['join_date', '入职日期', '入职时间', 'onboard_date']:
                                if col in row and pd.notna(row[col]):
                                    try:
                                        join_date = pd.to_datetime(row[col]).to_pydatetime()
                                    except Exception:
                                        pass
                                    if join_date:
                                        break
                            
                            leave_date = None
                            for col in ['leave_date', '离职日期', '离职时间', 'offboard_date']:
                                if col in row and pd.notna(row[col]):
                                    try:
                                        leave_date = pd.to_datetime(row[col]).to_pydatetime()
                                    except Exception:
                                        pass
                                    if leave_date:
                                        break
                            
                            analyzer.consultant_configs[name] = {
                                'monthly_salary': salary,
                                'is_active': is_active,
                                'salary_multiplier': 3.0,
                                'avg_positions': avg_positions,
                                'join_date': join_date,
                                'leave_date': leave_date,
                            }
                elif file_type == 'forecast':
                    analyzer.load_forecast_from_dataframe(df)
                elif file_type == 'salary':
                    from real_finance import load_real_salary_from_dataframe
                    records = load_real_salary_from_dataframe(df)
                    analyzer.real_cost_records.extend(records)
                elif file_type == 'reimburse':
                    from real_finance import load_real_reimburse_from_dataframe
                    records = load_real_reimburse_from_dataframe(df)
                    analyzer.real_cost_records.extend(records)
                elif file_type == 'fixed':
                    from real_finance import load_real_fixed_from_dataframe
                    records = load_real_fixed_from_dataframe(df)
                    analyzer.real_cost_records.extend(records)
                
                # 更新日志
                log['files'][rel_path] = {
                    'fingerprint': fingerprint,
                    'type': file_type,
                    'imported_at': datetime.now().isoformat(),
                    'rows': len(df)
                }
                
                results.append({
                    'file': rel_path,
                    'type': file_type,
                    'status': 'success',
                    'message': f'成功导入 {len(df)} 条记录'
                })
                
            except Exception as e:
                results.append({
                    'file': rel_path,
                    'type': file_type,
                    'status': 'failed',
                    'message': f'导入失败: {str(e)[:100]}'
                })
    
    if results:
        _save_import_log(base_path, log)
    
    return results


def get_import_history(base_path: str) -> List[Dict]:
    """获取导入历史记录"""
    log = _load_import_log(base_path)
    history = []
    for rel_path, info in log.get('files', {}).items():
        history.append({
            'file': rel_path,
            'type': info.get('type', 'unknown'),
            'imported_at': info.get('imported_at', ''),
            'rows': info.get('rows', 0)
        })
    # 按时间倒序
    history.sort(key=lambda x: x['imported_at'], reverse=True)
    return history


def clear_import_log(base_path: str):
    """清空导入日志（允许重新导入所有文件）"""
    log_path = os.path.join(base_path, IMPORT_LOG_NAME)
    if os.path.exists(log_path):
        try:
            os.remove(log_path)
        except Exception as e:
            print(f"清除导入日志失败: {e}")


def ensure_watched_dirs(base_path: str):
    """确保 watched 目录结构存在"""
    subdirs = [
        'deals',
        'consultants',
        'forecast',
        'real_finance/salary',
        'real_finance/reimburse',
        'real_finance/fixed',
        'financial_statements',  # 财务报表目录
    ]
    for sub in subdirs:
        os.makedirs(os.path.join(base_path, sub), exist_ok=True)


def _is_financial_statement_file(filename: str) -> bool:
    """判断是否为财务报表文件（资产负债表/利润表/现金流量表）"""
    lower = filename.lower()
    keywords = [
        '资产负债表', 'balance_sheet', 'balance sheet',
        '利润表', 'income_statement', 'income statement', 'profit_loss', 'profit loss',
        '现金流量表', 'cash_flow', 'cash flow',
        '财报', 'financial_statement', 'financial statement',
    ]
    for kw in keywords:
        if kw in lower:
            return True
    # 年份+季度模式 (如 2024Q4, 202312)
    import re
    if re.search(r'20\d{2}[qQ]?\d{1,2}', lower):
        return True
    return False


def _parse_year_from_filename(filename: str) -> str:
    """从文件名解析年份"""
    import re
    # 匹配 2023, 2024, 2025 等年份
    match = re.search(r'(20\d{2})', filename)
    if match:
        return match.group(1)
    return None


def _normalize_account_name(name: str, statement_type: str = None) -> str:
    """
    标准化会计科目名称
    
    Args:
        name: 原始科目名称
        statement_type: 报表类型
    
    Returns:
        标准化后的科目名称
    """
    if not name:
        return name
    
    # 清理名称（去除所有前导空格和尾部空格）
    import re
    name_original = name
    name = name.strip()
    # 去除所有前导空格（包括全角空格）
    name = re.sub(r'^[\s　]+', '', name)
    
    # 利润表科目映射
    pl_mapping = {
        # 收入类
        '营业收入': ['营业收入', '一、营业收入', '主营业务收入', '营收'],
        '营业成本': ['营业成本', '减：营业成本', '主营业务成本'],
        '税金及附加': ['税金及附加', '营业税金及附加', '税金'],
        # 费用类
        '销售费用': ['销售费用', '销售费', '营业费用'],
        '管理费用': ['管理费用', '管理费', '管理成本'],
        '财务费用': ['财务费用', '财务费', '利息费用'],
        # 利润类
        '营业利润': ['营业利润', '三、营业利润', '营业收益'],
        '营业外收入': ['营业外收入', '加：营业外收入'],
        '营业外支出': ['营业外支出', '减：营业外支出'],
        '利润总额': ['利润总额', '四、利润总额', '税前利润'],
        '所得税费用': ['所得税费用', '减：所得税费用', '所得税'],
        '净利润': ['净利润', '五、净利润', '净收益', '税后利润', '四、净利润', '净利润（净亏损）', '净亏损'],
        # 其他收益
        '其他收益': ['其他收益', '加：其他收益'],
        '投资收益': ['投资收益', '投资净收益'],
        '资产减值损失': ['资产减值损失', '信用减值损失'],
    }
    
    # 资产负债表科目映射
    bs_mapping = {
        # 资产类
        '货币资金': ['货币资金'],
        '应收账款': ['应收账款', '应收帐款'],
        '预付款项': ['预付款项', '预付账款'],
        '其他应收款': ['其他应收款', '其他应收帐款'],
        '存货': ['存货'],
        '流动资产合计': ['流动资产合计'],
        '固定资产': ['固定资产'],
        '非流动资产合计': ['非流动资产合计'],
        '资产总计': ['资产总计', '资产合计', '总资产', '资产总计'],
        # 负债类
        '短期借款': ['短期借款'],
        '应付账款': ['应付账款', '应付帐款'],
        '应付职工薪酬': ['应付职工薪酬', '应付工资'],
        '应交税费': ['应交税费', '应交税金'],
        '其他应付款': ['其他应付款', '其他应付帐款'],
        '流动负债合计': ['流动负债合计'],
        '非流动负债合计': ['非流动负债合计'],
        '负债合计': ['负债合计', '负债总计', '总负债'],
        # 权益类
        '实收资本': ['实收资本', '注册资本'],
        '资本公积': ['资本公积'],
        '盈余公积': ['盈余公积'],
        '未分配利润': ['未分配利润'],
        '所有者权益合计': ['所有者权益合计', '所有者权益总计', '股东权益', '净资产'],
    }
    
    # 选择映射表
    mapping = pl_mapping if statement_type == 'profit_loss' else bs_mapping
    
    # 查找匹配 - 使用部分匹配，但优先匹配更长的变体
    # 按变体长度降序排序，确保优先匹配更具体的名称
    all_variants = []
    for standard_name, variants in mapping.items():
        for variant in variants:
            all_variants.append((len(variant), variant, standard_name))
    
    # 按长度降序排序
    all_variants.sort(reverse=True)
    
    for length, variant, standard_name in all_variants:
        # 变体是名称的子串，且变体长度大于2（避免单个字匹配）
        if len(variant) >= 2 and variant in name:
            return standard_name
    
    # 如果没有匹配到，返回清理后的名称
    return name


def _parse_financial_statement(df: pd.DataFrame, statement_type: str = None) -> Dict:
    """
    解析财务报表数据
    
    支持多种格式：
    1. 上下结构
    2. 左右结构（资产在左，负债权益在右）
    
    Args:
        df: 财务报表DataFrame
        statement_type: 报表类型 (balance_sheet, profit_loss, cash_flow)
    
    Returns:
        解析后的财务数据字典
    """
    import re
    result = {}
    num_cols = len(df.columns)
    
    # 检测文件格式
    # 检测1：左右结构（第4列是否有科目名称）
    is_left_right = False
    if num_cols >= 6:
        for idx in range(min(10, len(df))):
            row = df.iloc[idx]
            if pd.notna(row.iloc[0]) and pd.notna(row.iloc[4]):
                right_content = str(row.iloc[4]).strip()
                if len(right_content) > 2 and any('\u4e00' <= c <= '\u9fff' for c in right_content):
                    is_left_right = True
                    break
    
    # 检测2：数值列起始位置
    # 2023格式：第1列=期末，第2列=年初
    # 2024/2025格式：第2列=期末，第3列=年初
    left_end_col = 1  # 默认
    for idx in range(min(10, len(df))):
        row = df.iloc[idx]
        if pd.notna(row.iloc[0]):
            # 尝试第1列
            if pd.notna(row.iloc[1]):
                try:
                    v = float(row.iloc[1])
                    if v > 1000:  # 找到大额数值
                        left_end_col = 1
                        break
                except:
                    pass
            # 尝试第2列
            if pd.notna(row.iloc[2]):
                try:
                    v = float(row.iloc[2])
                    if v > 1000:
                        left_end_col = 2
                        break
                except:
                    pass
    
    left_begin_col = left_end_col + 1
    
    for idx, row in df.iterrows():
        # ===== 解析左栏 =====
        if pd.notna(row.iloc[0]):
            name = str(row.iloc[0])
            name_clean = re.sub(r'^[\s　]+', '', name)
            
            # 跳过标题
            skip_list = ['资产', '负债', '所有者权益', '公司名称', '编制单位']
            if name_clean in skip_list:
                continue
            skip_keywords = ['单位', '元', '项目', '科目', '行次', '期末余额', '年初余额']
            if any(kw in name_clean for kw in skip_keywords) and len(name_clean) < 10:
                continue
            
            standard = _normalize_account_name(name, statement_type)
            
            # 读取数值
            try:
                if statement_type == 'profit_loss':
                    # 利润表：检测哪一列是本年累计金额
                    val1 = None
                    val2 = None
                    
                    if num_cols > left_end_col and pd.notna(row.iloc[left_end_col]):
                        try:
                            val1 = float(row.iloc[left_end_col])
                        except:
                            pass
                    
                    if num_cols > left_begin_col and pd.notna(row.iloc[left_begin_col]):
                        try:
                            val2 = float(row.iloc[left_begin_col])
                        except:
                            pass
                    
                    # 选择较大的数值作为本期金额（本年累计）
                    if val1 is not None and val2 is not None:
                        if abs(val2) > abs(val1) * 5:  # 第2列比第1列大5倍以上
                            current = val2
                            prev = None
                        else:
                            current = val1
                            prev = val2
                    elif val1 is not None:
                        current = val1
                        prev = None
                    else:
                        continue
                    
                    result[standard] = {'本期金额': current, '上期金额': prev}
                else:
                    end = float(row.iloc[left_end_col])
                    begin = float(row.iloc[left_begin_col]) if num_cols > left_begin_col and pd.notna(row.iloc[left_begin_col]) else None
                    result[standard] = {'期末余额': end, '年初余额': begin}
            except:
                pass
        
        # ===== 解析右栏 =====
        if is_left_right and num_cols >= 6 and pd.notna(row.iloc[4]):
            name = str(row.iloc[4])
            name_clean = re.sub(r'^[\s　]+', '', name)
            
            # 跳过标题
            skip_list = ['负债', '所有者权益', '负债和所有者权益', '流动负债', '非流动负债']
            if name_clean in skip_list:
                continue
            skip_keywords = ['单位', '元', '项目', '科目', '行次', '期末余额', '年初余额']
            if any(kw in name_clean for kw in skip_keywords) and len(name_clean) < 15:
                continue
            
            standard = _normalize_account_name(name, statement_type)
            
            # 读取数值（右栏数值在第6、7列，索引5、6，跳过第5列的行号）
            try:
                end = None
                begin = None
                
                # 第5列（索引4）是行号，跳过
                # 第6列（索引5）可能是金额或行号
                if num_cols > 5 and pd.notna(row.iloc[5]):
                    try:
                        v = float(row.iloc[5])
                        if abs(v) > 100:  # 大于100才认为是金额
                            end = v
                    except:
                        pass
                
                # 如果第6列不是金额，尝试第7列
                if end is None and num_cols > 6 and pd.notna(row.iloc[6]):
                    end = float(row.iloc[6])
                
                # 读取年初余额
                if num_cols > 6 and pd.notna(row.iloc[6]):
                    try:
                        v = float(row.iloc[6])
                        if v != end:
                            begin = v
                    except:
                        pass
                
                if begin is None and num_cols > 7 and pd.notna(row.iloc[7]):
                    begin = float(row.iloc[7])
                
                if end is not None and standard not in result:
                    result[standard] = {'期末余额': end, '年初余额': begin}
            except:
                pass
    
    return result


def _update_financial_statements_summary(base_path: str, year: str, statement_type: str, data: Dict):
    """
    更新财务数据汇总文件
    
    Args:
        base_path: watched 目录路径
        year: 年份 (如 '2025')
        statement_type: 报表类型 ('balance_sheet' 或 'profit_loss')
        data: 解析后的财务数据
    """
    import json
    
    summary_path = os.path.join(base_path, 'financial_statements', 'multi_year_fs_summary.json')
    
    # 加载现有数据
    summary = {'years': {}}
    if os.path.exists(summary_path):
        try:
            with open(summary_path, 'r', encoding='utf-8') as f:
                summary = json.load(f)
        except:
            pass
    
    if 'years' not in summary:
        summary['years'] = {}
    
    if year not in summary['years']:
        summary['years'][year] = {
            'balance_sheet': {},
            'profit_loss': {},
            'metrics': {}
        }
    
    # 更新数据 - 转换格式以兼容原有结构
    if statement_type == 'balance_sheet':
        # 资产负债表：转换为统一格式
        formatted_data = {}
        for item_name, values in data.items():
            formatted_data[item_name] = {
                '期末余额': values.get('期末余额'),
                '年初余额': values.get('年初余额')
            }
        summary['years'][year]['balance_sheet'] = formatted_data
    elif statement_type == 'profit_loss':
        # 利润表：转换为统一格式
        formatted_data = {}
        for item_name, values in data.items():
            formatted_data[item_name] = {
                '本期金额': values.get('本期金额'),
                '上期金额': values.get('上期金额')
            }
        summary['years'][year]['profit_loss'] = formatted_data
    
    # 计算核心指标
    try:
        bs = summary['years'][year]['balance_sheet']
        pl = summary['years'][year]['profit_loss']
        
        # 资产负债率
        total_assets = 0
        if '资产总计' in bs:
            total_assets = bs['资产总计'].get('期末余额', 0) or 0
        total_liabilities = 0
        if '负债合计' in bs:
            total_liabilities = bs['负债合计'].get('期末余额', 0) or 0
        if total_assets:
            summary['years'][year]['metrics']['资产负债率'] = (total_liabilities / total_assets) * 100
        
        # 流动比率
        current_assets = 0
        if '流动资产合计' in bs:
            current_assets = bs['流动资产合计'].get('期末余额', 0) or 0
        current_liabilities = 0
        if '流动负债合计' in bs:
            current_liabilities = bs['流动负债合计'].get('期末余额', 0) or 0
        if current_liabilities:
            summary['years'][year]['metrics']['流动比率'] = current_assets / current_liabilities
        
        # 毛利率
        revenue = 0
        if '营业收入' in pl:
            revenue = pl['营业收入'].get('本期金额', 0) or 0
        cost = 0
        if '营业成本' in pl:
            cost = pl['营业成本'].get('本期金额', 0) or 0
        if revenue:
            summary['years'][year]['metrics']['毛利率'] = ((revenue - cost) / revenue) * 100
        
        # 销售净利率
        net_profit = 0
        if '净利润' in pl:
            net_profit = pl['净利润'].get('本期金额', 0) or 0
        if revenue:
            summary['years'][year]['metrics']['销售净利率'] = (net_profit / revenue) * 100
        
        # ROE (简化计算)
        equity = 0
        if '所有者权益合计' in bs:
            equity = bs['所有者权益合计'].get('期末余额', 0) or 0
        if equity:
            summary['years'][year]['metrics']['净资产收益率_ROE'] = (net_profit / equity) * 100
        
    except Exception as e:
        print(f"计算财务指标失败: {e}")
    
    # 保存更新后的汇总文件
    try:
        os.makedirs(os.path.dirname(summary_path), exist_ok=True)
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存财务汇总失败: {e}")


def scan_financial_statements(base_path: str) -> List[Dict]:
    """
    扫描 financial_statements 目录并解析财报文件
    
    Args:
        base_path: watched 目录的绝对路径
    
    Returns:
        解析结果列表
    """
    results = []
    fs_path = os.path.join(base_path, 'financial_statements')
    
    if not os.path.exists(fs_path):
        return results
    
    # 获取导入日志
    log_path = os.path.join(fs_path, 'import_log.json')
    log = {'files': {}}
    if os.path.exists(log_path):
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                log = json.load(f)
        except:
            pass
    
    for root, dirs, files in os.walk(fs_path):
        # 跳过 backup 目录和临时文件
        dirs[:] = [d for d in dirs if d.lower() != 'backup']
        files = [f for f in files if not f.startswith('~$') and f.lower().endswith(SUPPORTED_EXTS)]
        
        for filename in files:
            full_path = os.path.join(root, filename)
            rel_path = os.path.relpath(full_path, fs_path)
            fingerprint = _get_file_fingerprint(full_path)
            
            # 检查是否已经导入过且未变化
            existing = log.get('files', {}).get(rel_path, {})
            if existing.get('fingerprint') == fingerprint:
                continue
            
            # 检查是否为财务报表文件
            if not _is_financial_statement_file(filename):
                continue
            
            df = _read_dataframe(full_path)
            if df is None or df.empty:
                results.append({
                    'file': f'financial_statements/{rel_path}',
                    'type': 'financial_statements',
                    'status': 'failed',
                    'message': '文件读取失败或为空'
                })
                continue
            
            try:
                # 解析年份
                year = _parse_year_from_filename(filename)
                if not year:
                    year = 'unknown'
                
                # 判断报表类型
                lower_name = filename.lower()
                if any(kw in lower_name for kw in ['资产负债', 'balance_sheet', 'balance sheet']):
                    statement_type = 'balance_sheet'
                elif any(kw in lower_name for kw in ['利润表', 'income', 'profit_loss', 'profit loss']):
                    statement_type = 'profit_loss'
                else:
                    # 根据内容判断（简化版：看是否有"营业收入"等利润表特有科目）
                    text_content = ' '.join(df.astype(str).values.flatten())
                    if '营业收入' in text_content or '营业成本' in text_content:
                        statement_type = 'profit_loss'
                    else:
                        statement_type = 'balance_sheet'
                
                # 解析报表数据
                parsed_data = _parse_financial_statement(df, statement_type)
                
                # 更新汇总文件
                _update_financial_statements_summary(base_path, year, statement_type, parsed_data)
                
                # 更新日志
                log['files'][rel_path] = {
                    'fingerprint': fingerprint,
                    'type': statement_type,
                    'year': year,
                    'imported_at': datetime.now().isoformat(),
                    'rows': len(parsed_data)
                }
                
                results.append({
                    'file': f'financial_statements/{rel_path}',
                    'type': f'financial_statements/{statement_type}',
                    'status': 'success',
                    'message': f'成功解析 {year}年 {statement_type}，共 {len(parsed_data)} 个科目'
                })
                
            except Exception as e:
                results.append({
                    'file': f'financial_statements/{rel_path}',
                    'type': 'financial_statements',
                    'status': 'failed',
                    'message': f'解析失败: {str(e)[:100]}'
                })
    
    # 保存日志
    if results:
        try:
            os.makedirs(fs_path, exist_ok=True)
            with open(log_path, 'w', encoding='utf-8') as f:
                json.dump(log, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存财务导入日志失败: {e}")
    
    return results
