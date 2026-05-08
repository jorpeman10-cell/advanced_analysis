"""
Gllue API 客户端 - 用于从谷露系统同步数据到财务分析工具

文档参考：Gllue通用接口文档V0.7.2
"""

import sys
import requests
import hashlib
import urllib.parse
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import pandas as pd
import json
from dataclasses import dataclass


@dataclass
class GllueConfig:
    """Gllue API 配置"""
    base_url: str  # 如: https://yourcompany.gllue.com
    api_key: Optional[str] = None   # API密钥（私有化部署无API Key时可不传）
    username: Optional[str] = None  # 网页登录账号（用于浏览器自动登录获取Session）
    password: Optional[str] = None  # 网页登录密码
    private_token: Optional[str] = None  # 生成的private token
    
    def __post_init__(self):
        if not self.base_url.startswith(('http://', 'https://')):
            self.base_url = 'https://' + self.base_url
        # 去除末尾的斜杠
        self.base_url = self.base_url.rstrip('/')


class GllueAPIClient:
    """Gllue API 客户端
    
    支持两种认证模式：
    1. API Key 模式：传统 gllue_private_token 认证
    2. 浏览器登录模式：通过 Playwright 模拟网页登录获取 Session Cookie，
       然后调用 REST API（适用于私有化部署无 API Key 的场景）
    """
    
    def __init__(self, config: GllueConfig):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json; charset=UTF-8',
            'Accept': 'application/json'
        })
        self._browser_authenticated = False
    
    def _ensure_authenticated(self):
        """确保已认证：优先 API Key，否则尝试浏览器登录"""
        if self._browser_authenticated:
            return
        if self.config.api_key:
            return
        if self.config.username and self.config.password:
            self._authenticate_browser()
            return
        raise Exception("认证失败：需要提供 api_key 或 username+password")
    
    def _authenticate_browser(self):
        """使用 Playwright 浏览器登录获取 Session Cookie
        
        由于 Python 3.14 + Windows 的 asyncio 兼容性问题，Playwright 在 Streamlit
        的 event loop 中无法直接启动。我们通过 subprocess 调用独立的辅助脚本绕过此问题。
        """
        import os
        import subprocess
        import json
        
        helper_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gllue_login_helper.py")
        if not os.path.exists(helper_path):
            raise Exception(f"找不到登录辅助脚本: {helper_path}")
        
        cmd = [
            sys.executable,
            helper_path,
            self.config.base_url,
            self.config.username,
            self.config.password,
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except Exception as e:
            raise Exception(f"启动浏览器登录进程失败: {str(e)}")
        
        if result.returncode != 0:
            raise Exception(f"浏览器登录失败: {result.stderr or result.stdout}")
        
        # 解析最后一行 JSON 输出
        last_line = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
        try:
            data = json.loads(last_line)
        except json.JSONDecodeError:
            raise Exception(f"无法解析登录响应: {result.stdout}")
        
        if "error" in data:
            raise Exception(f"浏览器登录失败: {data['error']}")
        
        cookies = data.get("cookies", [])
        for c in cookies:
            self.session.cookies.set(
                c['name'], c['value'],
                domain=c.get('domain') or None,
                path=c.get('path') or "/"
            )
        
        self._browser_authenticated = True
    
    def _generate_private_token(self) -> str:
        """
        生成 Gllue Private Token
        算法：md5(api_key + timestamp)
        """
        if not self.config.api_key:
            return ""
        timestamp = str(int(datetime.now().timestamp()))
        raw_string = self.config.api_key + timestamp
        token = hashlib.md5(raw_string.encode('utf-8')).hexdigest()
        return f"{token}_{timestamp}"
    
    def _get_token(self) -> str:
        """获取当前可用的 private token"""
        if self.config.private_token:
            return self.config.private_token
        return self._generate_private_token()
    
    def _build_url(self, endpoint: str, params: Dict[str, Any] = None) -> str:
        """构建请求 URL"""
        url = f"{self.config.base_url}{endpoint}"
        if params:
            query_string = urllib.parse.urlencode(params, safe=',')
            url = f"{url}?{query_string}"
        return url
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """发送 HTTP 请求"""
        self._ensure_authenticated()
        
        if 'params' not in kwargs:
            kwargs['params'] = {}
        
        # 只有 API Key 模式才附加 gllue_private_token
        if self.config.api_key and not self._browser_authenticated:
            kwargs['params']['gllue_private_token'] = self._get_token()
        
        url = self._build_url(endpoint, kwargs.pop('params', None))
        
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"API 请求失败: {str(e)}")
        except json.JSONDecodeError as e:
            raise Exception(f"解析响应失败: {str(e)}")
    
    def _paginate_request(self, endpoint: str, gql: str = "", fields: str = "", 
                          page_size: int = 100, **kwargs) -> List[Dict]:
        """分页获取所有数据（支持 simple_list_with_ids 的关联对象合并）"""
        object_name = endpoint.split('/')[-2] if '/rest/' in endpoint else 'result'
        all_results = []
        related_cache = {}
        page = 1
        
        while True:
            params = {
                'gql': gql,
                'page': page,
                'paginate_by': page_size,
                'fields': fields,
                **kwargs
            }
            
            data = self._make_request('GET', endpoint, params=params)
            result_dict = data.get('result', {})
            results = result_dict.get(object_name, [])
            
            if not results:
                break
            
            # 缓存关联对象（如 jobsubmission, joborder, candidate, user 等）
            for key, items in result_dict.items():
                if key == object_name or not isinstance(items, list):
                    continue
                if key not in related_cache:
                    related_cache[key] = {}
                for item in items:
                    related_cache[key][item['id']] = item
            
            all_results.extend(results)
            
            # 检查是否还有下一页
            current_page = data.get('currentpage', page)
            total_pages = data.get('totalpages', current_page)
            
            if current_page >= total_pages:
                break
            
            page += 1
            
            # 防止无限循环
            if page > 1000:
                break
        
        # 将关联对象合并到主记录（递归平铺嵌套字段）
        for record in all_results:
            self._merge_related(record, related_cache)
        
        return all_results
    
    def _merge_related(self, record: Dict, related_cache: Dict):
        """迭代合并关联对象到当前记录（支持任意深度嵌套）"""
        changed = True
        while changed:
            changed = False
            for key, value in list(record.items()):
                if not isinstance(value, int):
                    continue
                # 确定关联对象名（如 candidate / joborder）
                cache_key = key
                if cache_key not in related_cache and '__' in key:
                    cache_key = key.split('__')[-1]
                if cache_key not in related_cache:
                    continue
                related_obj = related_cache[cache_key].get(value)
                if not related_obj or not isinstance(related_obj, dict):
                    continue
                prefix = key + '__' if not key.endswith(f'__{cache_key}') else key + '__'
                # 如果 key 本身就是 cache_key，prefix = key + '__'
                # 如果 key 是 jobsubmission__candidate，cache_key=candidate，prefix = key + '__' = 'jobsubmission__candidate__'
                prefix = key + '__'
                for sub_key, sub_value in related_obj.items():
                    flat_key = f"{prefix}{sub_key}"
                    if flat_key not in record:
                        record[flat_key] = sub_value
                        changed = True
    
    # ==================== 数据获取方法 ====================
    
    def get_offers(self, start_date: Optional[str] = None, 
                   end_date: Optional[str] = None,
                   status: str = "") -> pd.DataFrame:
        """
        获取 Offer 列表
        
        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            status: 状态筛选
        """
        # 构建查询条件
        conditions = []
        if start_date:
            conditions.append(f"signDate__gte={start_date}")
        if end_date:
            conditions.append(f"signDate__lte={end_date}")
        if status:
            conditions.append(f"_approval_status__s={status}")
        
        gql = "&".join(conditions) if conditions else ""
        
        # 请求字段 - 根据财务工具需要的字段
        fields = (
            "id,signDate,onboardDate,annualSalary,probationRange,"
            "jobsubmission__candidate__chineseName,jobsubmission__candidate__englishName,"
            "jobsubmission__joborder__jobTitle,jobsubmission__joborder__id,"
            "jobsubmission__joborder__bu____name__,jobsubmission__joborder__lineManager__user,"
            "jobsubmission__joborder__joborderuser_set__user____name__,user____name__"
        )
        
        results = self._paginate_request(
            '/rest/offersign/simple_list_with_ids',
            gql=gql,
            fields=fields,
            ordering='-signDate'
        )
        
        # 转换为 DataFrame
        df = pd.DataFrame(results)
        
        # 扁平化嵌套字段
        if not df.empty:
            df = self._flatten_offer_data(df)
        
        return df
    
    def get_onboards(self, start_date: Optional[str] = None,
                     end_date: Optional[str] = None) -> pd.DataFrame:
        """
        获取入职列表
        
        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
        """
        conditions = []
        if start_date:
            conditions.append(f"onboardDate__gte={start_date}")
        if end_date:
            conditions.append(f"onboardDate__lte={end_date}")
        
        gql = "&".join(conditions) if conditions else ""
        
        fields = (
            "id,onboardDate,probationDate,"
            "jobsubmission__candidate__chineseName,jobsubmission__candidate__englishName,"
            "jobsubmission__joborder__jobTitle,jobsubmission__joborder__id,"
            "jobsubmission__joborder__bu____name__,user____name__"
        )
        
        results = self._paginate_request(
            '/rest/onboard/simple_list_with_ids',
            gql=gql,
            fields=fields,
            ordering='-onboardDate'
        )
        
        df = pd.DataFrame(results)
        if not df.empty:
            df = self._flatten_onboard_data(df)
        
        return df
    
    def get_joborders(self, statuses: List[str] = None) -> pd.DataFrame:
        """
        获取职位列表
        
        Args:
            statuses: 职位状态列表，如 ['Live', 'Successful']
        """
        conditions = []
        if statuses:
            status_gql = ",".join(statuses)
            conditions.append(f"jobStatus__s={status_gql}")
        
        gql = "&".join(conditions) if conditions else ""
        
        fields = (
            "id,jobTitle,jobStatus,maxStatus,openDate,closeDate,totalCount,"
            "monthlySalary,annualSalary,feeRate,employmentType,"
            "bu____name__,lineManager__user,joborderuser_set__user____name__,"
            "addedBy__user,dateAdded"
        )
        
        results = self._paginate_request(
            '/rest/joborder/simple_list_with_ids',
            gql=gql,
            fields=fields,
            ordering='-lastUpdateDate'
        )
        
        df = pd.DataFrame(results)
        if not df.empty:
            df = self._flatten_joborder_data(df)
        
        return df
    
    def get_forecasts(self, start_date: Optional[str] = None,
                      end_date: Optional[str] = None,
                      include_statuses: List[str] = None) -> pd.DataFrame:
        """
        获取 Forecast / Pipeline 数据（在途单）
        
        从 joborder 接口拉取 jobStatus=Live 的职位，每个 Live 职位即为一个 Pipeline 条目。
        使用 maxStatus 作为阶段，annualSalary/feeRate 计算预计佣金。
        可通过 include_statuses 指定要保留的 maxStatus。
        
        Args:
            start_date: 开始日期 (YYYY-MM-DD)，按 openDate 筛选
            end_date: 结束日期 (YYYY-MM-DD)
            include_statuses: 显式指定要包含的 maxStatus，如 ['Client Interview','Offer']
        """
        conditions = ["jobStatus__s=Live"]
        if start_date:
            conditions.append(f"openDate__gte={start_date}")
        if end_date:
            conditions.append(f"openDate__lte={end_date}")
        
        # 如果用户显式传了 include_statuses，则按 maxStatus 再过滤
        if include_statuses:
            status_gql = ",".join(include_statuses)
            conditions.append(f"maxStatus__s={status_gql}")
        
        gql = "&".join(conditions)
        
        fields = (
            "id,jobTitle,jobStatus,maxStatus,openDate,closeDate,totalCount,"
            "monthlySalary,annualSalary,feeRate,"
            "bu____name__,lineManager__user,joborderuser_set__user____name__,"
            "addedBy__user,dateAdded,lastUpdateDate"
        )
        
        results = self._paginate_request(
            '/rest/joborder/simple_list_with_ids',
            gql=gql,
            fields=fields,
            ordering='-lastUpdateDate'
        )
        
        df = pd.DataFrame(results)
        if not df.empty:
            df = self._flatten_forecast_data(df)
        
        return df
    
    def get_users(self, is_active: bool = True) -> pd.DataFrame:
        """获取用户/顾问列表"""
        fields = "id,chineseName,englishName,email,mobile,isActive,dateJoined"
        
        results = self._paginate_request(
            '/rest/user/simple_list_with_ids',
            fields=fields
        )
        
        return pd.DataFrame(results)
    
    # ==================== 数据转换方法 ====================
    
    def _flatten_offer_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """扁平化 Offer 数据"""
        # 提取嵌套的候选人信息
        if 'jobsubmission__candidate__chineseName' in df.columns:
            df['候选人姓名'] = df['jobsubmission__candidate__chineseName']
        if 'jobsubmission__candidate__englishName' in df.columns:
            df['候选人英文名'] = df['jobsubmission__candidate__englishName']
        
        # 提取职位信息
        if 'jobsubmission__joborder__jobTitle' in df.columns:
            df['职位名称'] = df['jobsubmission__joborder__jobTitle']
        if 'jobsubmission__joborder__id' in df.columns:
            df['职位ID'] = df['jobsubmission__joborder__id']
        
        # 客户名称：优先 bu____name__，否则用 __name__ 或 jobTitle 兜底
        if 'jobsubmission__joborder__bu____name__' in df.columns:
            df['客户名称'] = df['jobsubmission__joborder__bu____name__']
        elif 'jobsubmission__joborder____name__' in df.columns:
            df['客户名称'] = df['jobsubmission__joborder____name__']
        elif 'jobsubmission__joborder__jobTitle' in df.columns:
            df['客户名称'] = df['jobsubmission__joborder__jobTitle']
        
        # 提取顾问信息：优先使用 offersign 的 user（即操作人），通常就是负责顾问
        if 'user__chineseName' in df.columns:
            df['顾问'] = df['user__chineseName']
        elif 'user____name__' in df.columns:
            df['顾问'] = df['user____name__']
        elif 'jobsubmission__joborder__joborderuser_set__user____name__' in df.columns:
            df['顾问'] = df['jobsubmission__joborder__joborderuser_set__user____name__']
        
        if 'user____name__' in df.columns:
            df['操作人'] = df['user____name__']
        
        # 重命名字段
        column_mapping = {
            'id': 'offer_id',
            'signDate': 'offer_date',
            'onboardDate': '预计入职日期',
            'annualSalary': '年薪',
            'probationRange': '试用期',
        }
        df = df.rename(columns=column_mapping)
        
        # 年薪空值填充为 0
        if '年薪' in df.columns:
            df['年薪'] = pd.to_numeric(df['年薪'], errors='coerce').fillna(0)
        
        return df
    
    def _flatten_forecast_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """扁平化 Forecast (Joborder Live) 数据，转换为财务工具需要的列名"""
        # 职位/客户
        if 'jobTitle' in df.columns:
            df['职位名称'] = df['jobTitle']
        if 'id' in df.columns:
            df['职位ID'] = df['id']
        if 'bu____name__' in df.columns:
            df['客户名称'] = df['bu____name__']
        
        # 顾问
        if 'joborderuser_set__user____name__' in df.columns:
            df['顾问'] = df['joborderuser_set__user____name__']
        if 'addedBy__user' in df.columns:
            df['操作人'] = df['addedBy__user']
        
        # 财务字段
        if 'annualSalary' in df.columns:
            df['预计年薪'] = pd.to_numeric(df['annualSalary'], errors='coerce').fillna(0)
        else:
            df['预计年薪'] = 0.0
        
        if 'feeRate' in df.columns:
            df['费率'] = pd.to_numeric(df['feeRate'], errors='coerce').fillna(0.2)
            # 如果费率存的是百分比(如20)，保持不变；如果是小数(如0.2)，转为百分比
            df.loc[df['费率'] < 1, '费率'] = df.loc[df['费率'] < 1, '费率'] * 100
        else:
            df['费率'] = 20.0
        
        # 计算预计佣金
        df['预计佣金'] = df['预计年薪'] * df['费率'] / 100
        
        # 阶段映射（使用 joborder 的 maxStatus）
        if 'maxStatus' in df.columns:
            df['阶段'] = df['maxStatus'].fillna('Unknown')
        else:
            df['阶段'] = '进展中'
        
        # 日期
        if 'openDate' in df.columns:
            df['开始日期'] = df['openDate']
        if 'lastUpdateDate' in df.columns:
            df['最近更新'] = df['lastUpdateDate']
        
        # 预计成交日期：用 lastUpdateDate + 60天 作为合理预估
        if 'lastUpdateDate' in df.columns:
            df['预计成交日期'] = pd.to_datetime(df['lastUpdateDate'], errors='coerce') + pd.Timedelta(days=60)
        elif 'openDate' in df.columns:
            df['预计成交日期'] = pd.to_datetime(df['openDate'], errors='coerce') + pd.Timedelta(days=90)
        
        # 成功率映射（与 advanced_analysis/models.py 中的 FORECAST_STAGE_SUCCESS_RATE 保持一致）
        stage_rate_map = {
            'apply': 5,
            'longlist': 10,
            'Submitted': 10,
            '简历推荐': 10,
            'cvsent': 15,
            'clientinterview': 30,
            'Internal Interview': 25,
            '面试': 30,
            'Client Interview': 40,
            'Final Interview': 50,
            'offersign': 70,
            'Offer': 70,
            'Negotiation': 60,
            'pendingboard': 80,
            '待入职': 80,
            'onboard': 100,
            '入职': 100,
        }
        
        def map_success_rate(stage):
            if not stage:
                return 10
            stage_str = str(stage).strip()
            if stage_str in stage_rate_map:
                return stage_rate_map[stage_str]
            for key, rate in stage_rate_map.items():
                if key in stage_str or stage_str in key:
                    return rate
            return 10
        
        df['成功率'] = df['阶段'].apply(map_success_rate)
        
        # 重命名字段为财务工具标准列名
        column_mapping = {
            'id': 'forecast_id',
            'maxStatus': 'stage',
            'openDate': 'start_date',
            'lastUpdateDate': 'last_update_date',
        }
        df = df.rename(columns=column_mapping)
        
        return df
    
    def _flatten_onboard_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """扁平化入职数据"""
        if 'jobsubmission__candidate__chineseName' in df.columns:
            df['候选人姓名'] = df['jobsubmission__candidate__chineseName']
        if 'jobsubmission__joborder__jobTitle' in df.columns:
            df['职位名称'] = df['jobsubmission__joborder__jobTitle']
        if 'jobsubmission__joborder__bu____name__' in df.columns:
            df['客户名称'] = df['jobsubmission__joborder__bu____name__']
        if 'user____name__' in df.columns:
            df['顾问'] = df['user____name__']
        
        column_mapping = {
            'id': 'onboard_id',
            'onboardDate': '入职日期',
            'probationDate': '试用期结束日期',
        }
        df = df.rename(columns=column_mapping)
        
        return df
    
    def _flatten_joborder_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """扁平化职位数据"""
        if 'bu____name__' in df.columns:
            df['客户名称'] = df['bu____name__']
        if 'lineManager__user' in df.columns:
            df['直线经理'] = df['lineManager__user']
        if 'joborderuser_set__user____name__' in df.columns:
            df['顾问'] = df['joborderuser_set__user____name__']
        if 'addedBy__user' in df.columns:
            df['创建人'] = df['addedBy__user']
        
        column_mapping = {
            'id': '职位ID',
            'jobTitle': '职位名称',
            'jobStatus': '职位状态',
            'maxStatus': '最新进展',
            'openDate': '开始日期',
            'closeDate': '结束日期',
            'totalCount': '招聘人数',
            'monthlySalary': '月薪',
            'annualSalary': '年薪',
            'feeRate': '费率',
        }
        df = df.rename(columns=column_mapping)
        
        return df
    
    # ==================== 同步到财务工具的方法 ====================
    
    def sync_to_finance_analyzer(self, analyzer, start_date: str = None, 
                                  end_date: str = None) -> Dict[str, int]:
        """
        同步数据到财务分析器
        
        Args:
            analyzer: RecruitmentFinanceAnalyzer 实例
            start_date: 开始日期，默认为 1 年前
            end_date: 结束日期，默认为今天
        
        Returns:
            同步统计信息
        """
        if not start_date:
            start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
        if not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')
        
        stats = {
            'offers_fetched': 0,
            'onboards_fetched': 0,
            'positions_added': 0,
            'forecasts_fetched': 0,
        }
        
        # 1. 获取 Offer 数据（作为成单数据）
        offers_df = self.get_offers(start_date=start_date, end_date=end_date)
        stats['offers_fetched'] = len(offers_df)
        
        # 2. 获取入职数据
        onboards_df = self.get_onboards(start_date=start_date, end_date=end_date)
        stats['onboards_fetched'] = len(onboards_df)
        
        # 3. 获取 Forecast / Pipeline 数据（在途单）
        forecasts_df = self.get_forecasts(start_date=start_date, end_date=end_date)
        stats['forecasts_fetched'] = len(forecasts_df)
        
        # 4. 转换为财务工具的数据格式并加载
        if not offers_df.empty:
            positions_df = self._convert_to_positions_format(offers_df, onboards_df)
            # 兼容根目录 models.py 的接口
            if hasattr(analyzer, 'load_from_dataframes'):
                analyzer.load_from_dataframes(deals_df=positions_df)
            elif hasattr(analyzer, 'load_positions_from_dataframe'):
                analyzer.load_positions_from_dataframe(positions_df, clear_existing=True)
            stats['positions_added'] = len(positions_df)
        
        # 5. 加载 Forecast 数据
        if not forecasts_df.empty:
            if hasattr(analyzer, 'load_forecasts_from_dataframe'):
                analyzer.load_forecasts_from_dataframe(forecasts_df)
            elif hasattr(analyzer, 'load_forecast_from_dataframe'):
                analyzer.load_forecast_from_dataframe(forecasts_df, clear_existing=True)
        
        return stats
    
    def _convert_to_positions_format(self, offers_df: pd.DataFrame, 
                                      onboards_df: pd.DataFrame) -> pd.DataFrame:
        """
        将 Gllue 数据转换为财务工具需要的 deals DataFrame 格式
        兼容 models.py 中的 load_from_dataframes
        """
        result = pd.DataFrame()
        n = len(offers_df)
        
        def safe_get(series, default=''):
            if isinstance(series, pd.Series):
                return series
            return pd.Series([default] * n)
        
        # 基础字段（中英双语，确保 load_from_dataframes 能识别）
        result['deal_id'] = safe_get(offers_df.get('offer_id', offers_df.get('职位ID')), '').astype(str)
        result['client_name'] = safe_get(offers_df.get('客户名称'), '')
        result['candidate_name'] = safe_get(offers_df.get('候选人姓名'), '')
        result['position'] = safe_get(offers_df.get('职位名称'), '')
        result['consultant'] = safe_get(offers_df.get('顾问'), '')
        result['deal_date'] = safe_get(offers_df.get('offer_date'), '')
        result['annual_salary'] = pd.to_numeric(safe_get(offers_df.get('年薪'), 0), errors='coerce').fillna(0)
        result['fee_rate'] = 20.0
        result['fee_amount'] = result['annual_salary'] * result['fee_rate'] / 100
        result['actual_payment'] = 0
        result['prior_year_collection'] = 0
        result['payment_status'] = '未回款'
        
        # 保留原始中文字段（供其他模块使用）
        result['职位ID'] = result['deal_id']
        result['客户名称'] = result['client_name']
        result['职位名称'] = result['position']
        result['顾问'] = result['consultant']
        result['成单日期'] = result['deal_date']
        result['年薪'] = result['annual_salary']
        result['费率%'] = result['fee_rate']
        result['佣金总额'] = result['fee_amount']
        result['实际回款'] = result['actual_payment']
        result['上年遗留回款'] = result['prior_year_collection']
        result['入职日期'] = safe_get(offers_df.get('预计入职日期'), '')
        result['回款日期'] = ''
        result['发票日期'] = ''
        result['是否成单'] = True
        
        return result


class GllueDataCache:
    """Gllue 数据缓存管理"""
    
    def __init__(self, cache_dir: str = ".gllue_cache"):
        self.cache_dir = cache_dir
        import os
        os.makedirs(cache_dir, exist_ok=True)
    
    def save(self, data: pd.DataFrame, name: str):
        """保存数据到缓存"""
        filepath = f"{self.cache_dir}/{name}_{datetime.now().strftime('%Y%m%d')}.csv"
        data.to_csv(filepath, index=False, encoding='utf-8-sig')
    
    def load(self, name: str, date: str = None) -> Optional[pd.DataFrame]:
        """从缓存加载数据"""
        if date is None:
            date = datetime.now().strftime('%Y%m%d')
        filepath = f"{self.cache_dir}/{name}_{date}.csv"
        import os
        if os.path.exists(filepath):
            return pd.read_csv(filepath, encoding='utf-8-sig')
        return None
    
    def get_cache_dates(self, name: str) -> List[str]:
        """获取可用缓存日期列表"""
        import os
        import glob
        pattern = f"{self.cache_dir}/{name}_*.csv"
        files = glob.glob(pattern)
        dates = []
        for f in files:
            date_str = os.path.basename(f).replace(f"{name}_", "").replace(".csv", "")
            dates.append(date_str)
        return sorted(dates, reverse=True)


# ==================== 测试代码 ====================

if __name__ == "__main__":
    # 测试配置
    config = GllueConfig(
        base_url="https://demo.gllue.com",
        api_key="your_api_key_here"
    )
    
    client = GllueAPIClient(config)
    
    # 测试生成 token
    print("生成的 Token:", client._generate_private_token())
    
    # 测试数据获取（需要真实环境）
    # offers = client.get_offers(start_date="2024-01-01")
    # print(f"获取到 {len(offers)} 条 Offer 数据")
    # print(offers.head())
