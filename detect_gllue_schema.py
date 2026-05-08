#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gllue 数据库表结构探测脚本
在 ECS 上运行，输出关键表的结构和样本数据
"""

import pymysql
import json
from datetime import datetime

# 数据库配置（本地 MySQL）
DB_CONFIG = {
    'host': '127.0.0.1',
    'port': 3306,
    'user': 'readonly',
    'password': 'Tstar2026!',
    'database': 'gllue',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

# 关键表列表（顺序有逻辑关系）
KEY_TABLES = [
    'offersign', 'onboard', 'invoice', 'invoiceassignment',
    'joborder', 'jobsubmission', 'candidate', 'user', 'team',
    'client', 'clientinterview', 'cvsent', 'forecast',
    'pipeline', 'position', 'careertalk', 'function',
    'industry', 'companylocation', 'contract'
]

def get_connection():
    return pymysql.connect(**DB_CONFIG)

def list_all_tables(conn):
    """列出数据库中所有表"""
    with conn.cursor() as cur:
        cur.execute("SHOW TABLES")
        return [row[f'Tables_in_{DB_CONFIG["database"]}'] for row in cur.fetchall()]

def describe_table(conn, table_name):
    """获取表结构"""
    with conn.cursor() as cur:
        try:
            cur.execute(f"DESCRIBE `{table_name}`")
            columns = cur.fetchall()
            return [
                {
                    'field': col['Field'],
                    'type': col['Type'],
                    'null': col['Null'],
                    'key': col['Key'],
                    'default': str(col['Default']) if col['Default'] is not None else None,
                    'extra': col['Extra']
                }
                for col in columns
            ]
        except Exception as e:
            return [{'error': str(e)}]

def get_sample_data(conn, table_name, limit=3):
    """获取样本数据"""
    with conn.cursor() as cur:
        try:
            cur.execute(f"SELECT * FROM `{table_name}` LIMIT {limit}")
            rows = cur.fetchall()
            # 把 datetime 转为字符串，方便 JSON 序列化
            result = []
            for row in rows:
                cleaned = {}
                for k, v in row.items():
                    if isinstance(v, datetime):
                        cleaned[k] = v.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        cleaned[k] = v
                result.append(cleaned)
            return result
        except Exception as e:
            return [{'error': str(e)}]

def get_table_count(conn, table_name):
    """获取表记录数"""
    with conn.cursor() as cur:
        try:
            cur.execute(f"SELECT COUNT(*) as cnt FROM `{table_name}`")
            return cur.fetchone()['cnt']
        except:
            return -1

def main():
    print("=" * 60)
    print("Gllue 数据库表结构探测")
    print("=" * 60)
    
    conn = get_connection()
    all_tables = list_all_tables(conn)
    print(f"\n数据库 '{DB_CONFIG['database']}' 共有 {len(all_tables)} 张表")
    print(f"所有表名: {', '.join(all_tables[:50])}{'...' if len(all_tables) > 50 else ''}")
    
    report = {
        'database': DB_CONFIG['database'],
        'total_tables': len(all_tables),
        'all_tables': all_tables,
        'key_tables': {},
        'scan_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    # 探测关键表
    for table in KEY_TABLES:
        if table.lower() in [t.lower() for t in all_tables]:
            # 找到实际表名（可能大小写不同）
            actual_name = next(t for t in all_tables if t.lower() == table.lower())
            print(f"\n[探测] 表: {actual_name}")
            
            structure = describe_table(conn, actual_name)
            sample = get_sample_data(conn, actual_name)
            count = get_table_count(conn, actual_name)
            
            print(f"  记录数: {count}")
            print(f"  字段数: {len(structure)}")
            
            report['key_tables'][actual_name] = {
                'count': count,
                'structure': structure,
                'sample': sample
            }
        else:
            print(f"\n[跳过] 表 '{table}' 不存在")
    
    conn.close()
    
    # 保存报告
    output_file = 'gllue_schema_report.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'=' * 60}")
    print(f"探测完成！报告已保存到: {output_file}")
    print(f"请把该文件发给我")
    print(f"{'=' * 60}")

if __name__ == '__main__':
    main()
