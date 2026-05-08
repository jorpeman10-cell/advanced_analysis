"""
Mapping 组织架构图分析模块
提供节点分类、质量评分、录入人排名等分析能力
"""

import json
import pandas as pd
import numpy as np
import re
from collections import defaultdict


def classify_node(text, note):
    """对 Mapping 节点进行分类"""
    text = str(text).strip() if text else ''
    note = str(note).strip() if note else ''
    
    if not text or len(text) < 2:
        return '空节点', '文本为空或太短'
    
    lower = text.lower()
    if lower in ['subtopic', 'topic', 'children', 'root', 'mindmap', 'untitled']:
        return '低质数据-模板残留', '包含模板默认关键词如Subtopic/Topic'
    
    if re.match(r'^[\d\s\W]+$', text):
        return '低质数据-纯符号', '无有效文字内容'
    
    if re.match(r'^[A-Z]{2,6}$', text.strip()):
        return '职位缩写', '纯大写缩写如 RSM/DSM/RA'
    
    dept_keywords = ['部', '组', '中心', '委员会', '事业部', '研究院', '实验室', '科室', '办公室']
    if any(k in text for k in dept_keywords) and len(text) < 20:
        return '部门节点', '包含部门关键词'
    
    if len(text) > 40:
        return '描述性文字', '长度过长（>40字），疑似说明文字'
    
    if re.match(r'^[A-Za-z\s]+$', text) and len(text) > 10:
        if any(w in lower for w in ['manager', 'director', 'head', 'lead', 'specialist', 'president']):
            return '英文职位', '纯英文职位描述'
    
    if re.search(r'\d+\s*[\+\-]?\s*(员工|人|团队)', text):
        return '团队规模说明', '包含人数统计如"300+员工"'
    
    has_chinese = bool(re.search(r'[^\x00-\x7F]', text))
    has_english = bool(re.search(r'[A-Za-z]{2,}', text))
    
    if has_chinese:
        cn_chars = re.findall(r'[^\x00-\x7F]', text)
        if len(cn_chars) <= 8:
            return '人名-中英文', '符合人名长度特征'
        else:
            return '职位描述', '中文过多，疑似职位描述'
    elif has_english:
        words = text.split()
        if 1 <= len(words) <= 4:
            return '人名-纯英文', '英文单词数符合人名特征'
        else:
            return '英文描述', '英文单词过多'
    
    return '其他', '无法分类'


def generate_recommendation(categories, low_quality_count, desc_count):
    """根据问题类型生成整改建议"""
    recs = []
    cat_set = set(categories)
    
    if '低质数据-模板残留' in cat_set:
        recs.append("删除所有 'Subtopic' / 'Topic' 等模板默认节点，替换为实际人名或职位")
    if '低质数据-纯符号' in cat_set:
        recs.append("删除纯数字/纯符号节点，补充完整人名信息")
    if desc_count > 0:
        recs.append(f"将 {desc_count} 个过长描述节点拆分为：人名 + 职位（分开两个节点）")
    if '低质数据-描述性' in cat_set:
        recs.append("避免在节点中粘贴大段说明文字，建议放入备注(note)字段")
    if '职位缩写' in cat_set:
        recs.append("职位缩写节点建议补充完整：如'RSM'改为'张三 RSM'，便于后续人才匹配")
    if '英文职位' in cat_set or '职位描述' in cat_set:
        recs.append("纯职位描述节点建议补充具体人名，或标注'待补充'状态")
    if '团队规模说明' in cat_set:
        recs.append("团队规模信息建议放入根节点备注，不要作为独立子节点")
    
    if not recs:
        recs.append("数据质量良好，继续保持")
    
    return "；".join(recs)


class MappingAnalyzer:
    """Mapping 组织架构图分析器"""
    
    def __init__(self, db_client=None):
        self.db_client = db_client
        self._nodes_df = None
        self._org_stats = None
        self._loaded = False  # 标记是否已加载
    
    def load_from_db(self):
        """从数据库加载 Mapping 数据"""
        if self.db_client is None:
            return
        
        # 如果已经加载过，跳过
        if self._loaded:
            return
        
        mappings = self.db_client.query("""
            SELECT m.content, co.name as org_name, co.client_name, co.id as org_id,
                   co.addedBy_id, co.dateAdded, co.lastUpdateDate,
                   CONCAT(IFNULL(u.englishName, ''), ' ', IFNULL(u.chineseName, '')) as creator_name
            FROM companyorganizationmapping m
            JOIN companyorganization co ON m.organization_id = co.id
            LEFT JOIN user u ON co.addedBy_id = u.id
            WHERE m.is_current = 1 AND m.is_deleted = 0 AND co.is_deleted = 0
        """)
        
        all_nodes = []
        org_records = []
        
        for _, row in mappings.iterrows():
            org_id = row['org_id']
            org_name = row['org_name']
            client_name = row['client_name']
            creator = row['creator_name']
            
            try:
                data = json.loads(row['content'])
            except:
                continue
            
            def extract_nodes(node, depth=0):
                text = node.get('text', '').strip()
                note = node.get('note', '').strip()
                if text or note:
                    cat, reason = classify_node(text, note)
                    all_nodes.append({
                        'org_id': org_id,
                        'org_name': org_name,
                        'client_name': client_name,
                        'creator': creator,
                        'text': text,
                        'note': note,
                        'category': cat,
                        'reason': reason,
                        'depth': depth,
                    })
                for child in node.get('children', []):
                    extract_nodes(child, depth + 1)
            
            for root in data.get('roots', []):
                extract_nodes(root)
            
            # Org-level stats
            org_df = pd.DataFrame([n for n in all_nodes if n['org_id'] == org_id])
            if len(org_df) > 0:
                total = len(org_df)
                low_q = len(org_df[org_df['category'].str.startswith('低质数据')])
                desc = len(org_df[org_df['category'] == '描述性文字'])
                person = len(org_df[org_df['category'].isin(['人名-中英文', '人名-纯英文'])])
                cats = org_df['category'].tolist()
                
                org_records.append({
                    'org_id': org_id,
                    'org_name': org_name,
                    'client_name': client_name,
                    'creator': creator,
                    'total_nodes': total,
                    'person_nodes': person,
                    'low_quality_nodes': low_q,
                    'desc_nodes': desc,
                    'quality_score': max(0, 100 - low_q * 5 - desc * 2),
                    'recommendation': generate_recommendation(cats, low_q, desc),
                })
        
        self._nodes_df = pd.DataFrame(all_nodes)
        self._org_stats = pd.DataFrame(org_records)
        self._loaded = True
    
    def get_summary(self):
        """获取整体统计摘要"""
        if self._nodes_df is None or self._org_stats is None:
            return {}
        
        total_nodes = len(self._nodes_df)
        person_nodes = len(self._nodes_df[self._nodes_df['category'].isin(['人名-中英文', '人名-纯英文'])])
        low_q = len(self._nodes_df[self._nodes_df['category'].str.startswith('低质数据')])
        desc = len(self._nodes_df[self._nodes_df['category'] == '描述性文字'])
        
        return {
            'total_orgs': len(self._org_stats),
            'total_nodes': total_nodes,
            'person_nodes': person_nodes,
            'person_ratio': round(person_nodes / total_nodes * 100, 1) if total_nodes > 0 else 0,
            'low_quality_nodes': low_q,
            'desc_nodes': desc,
            'avg_quality_score': round(self._org_stats['quality_score'].mean(), 1),
            'need_fix': len(self._org_stats[self._org_stats['quality_score'] < 60]),
        }
    
    def get_org_stats(self):
        """获取每张 Mapping 的统计"""
        return self._org_stats.copy() if self._org_stats is not None else pd.DataFrame()
    
    def get_creator_ranking(self):
        """获取录入人质量排名"""
        if self._org_stats is None or self._org_stats.empty:
            return pd.DataFrame()
        
        result = []
        for creator in self._org_stats['creator'].dropna().unique():
            c_df = self._org_stats[self._org_stats['creator'] == creator]
            result.append({
                '录入人': creator,
                'Mapping数量': len(c_df),
                '平均质量分': round(c_df['quality_score'].mean(), 1),
                '最低质量分': c_df['quality_score'].min(),
                '低质Mapping数': len(c_df[c_df['quality_score'] < 60]),
                '总节点数': int(c_df['total_nodes'].sum()),
                '人名节点数': int(c_df['person_nodes'].sum()),
                '待整改建议': '；'.join(c_df[c_df['quality_score'] < 60]['recommendation'].unique()[:2]),
            })
        
        return pd.DataFrame(result).sort_values('平均质量分')
    
    def get_category_distribution(self):
        """获取节点类型分布"""
        if self._nodes_df is None or self._nodes_df.empty:
            return pd.DataFrame()
        
        dist = self._nodes_df['category'].value_counts().reset_index()
        dist.columns = ['节点类型', '数量']
        dist['占比'] = (dist['数量'] / len(self._nodes_df) * 100).round(1)
        return dist
    
    def get_low_quality_list(self):
        """获取低质量 Mapping 清单"""
        if self._org_stats is None:
            return pd.DataFrame()
        return self._org_stats[self._org_stats['quality_score'] < 60].sort_values('quality_score')
    
    def get_nodes_by_org(self, org_id):
        """获取指定 Mapping 的所有节点"""
        if self._nodes_df is None:
            return pd.DataFrame()
        return self._nodes_df[self._nodes_df['org_id'] == org_id].copy()
