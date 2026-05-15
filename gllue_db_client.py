"""
Gllue 数据库直连客户端
用于绕过 REST API 限制，直接从 MySQL 读取业绩报表数据

支持两种连接方式：
1. 直接连接：应用部署在数据库同一服务器时使用
2. SSH 隧道：远程连接时使用（通过 paramiko 执行 SQL）
"""

import pandas as pd
from datetime import datetime
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from io import StringIO
import time


@dataclass
class GllueDBConfig:
    """数据库配置"""
    db_type: str = "mysql"
    host: str = "localhost"
    port: int = 3306
    database: str = "gllue"
    username: str = ""
    password: str = ""
    # SSH 配置（用于远程连接）
    use_ssh: bool = False
    ssh_host: str = ""
    ssh_port: int = 22
    ssh_user: str = "root"
    ssh_password: str = ""
    ssh_timeout: int = 45
    ssh_banner_timeout: int = 60
    ssh_auth_timeout: int = 45
    ssh_retries: int = 2


class GllueDBClient:
    """Gllue 数据库直连客户端"""
    
    def __init__(self, config: GllueDBConfig):
        self.config = config
        self._engine = None
        self._ssh_client = None
        self._ssh_connected = False
    
    def _get_engine(self):
        """获取 SQLAlchemy engine（懒加载）"""
        if self._engine is None:
            if self.config.db_type == "mysql":
                from sqlalchemy import create_engine
                conn_str = (
                    f"mysql+pymysql://{self.config.username}:{self.config.password}"
                    f"@{self.config.host}:{self.config.port}/{self.config.database}"
                    f"?charset=utf8mb4"
                )
                self._engine = create_engine(conn_str, pool_pre_ping=True)
            elif self.config.db_type == "postgresql":
                from sqlalchemy import create_engine
                conn_str = (
                    f"postgresql+psycopg2://{self.config.username}:{self.config.password}"
                    f"@{self.config.host}:{self.config.port}/{self.config.database}"
                )
                self._engine = create_engine(conn_str, pool_pre_ping=True)
            else:
                raise ValueError(f"不支持的数据库类型: {self.config.db_type}")
        return self._engine
    
    def _get_ssh_client(self):
        """获取或创建 SSH 连接（复用连接）"""
        if self._ssh_client is None or not self._ssh_connected:
            import paramiko
            last_error = None
            retries = max(int(self.config.ssh_retries or 1), 1)
            for attempt in range(retries):
                try:
                    self._ssh_client = paramiko.SSHClient()
                    self._ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    self._ssh_client.connect(
                        self.config.ssh_host,
                        port=int(self.config.ssh_port),
                        username=self.config.ssh_user,
                        password=self.config.ssh_password,
                        timeout=int(self.config.ssh_timeout or 45),
                        banner_timeout=int(self.config.ssh_banner_timeout or 60),
                        auth_timeout=int(self.config.ssh_auth_timeout or 45),
                        look_for_keys=False,
                        allow_agent=False,
                    )
                    self._ssh_connected = True
                    break
                except Exception as exc:
                    last_error = exc
                    self._ssh_connected = False
                    if self._ssh_client:
                        try:
                            self._ssh_client.close()
                        except Exception:
                            pass
                    self._ssh_client = None
                    if attempt + 1 < retries:
                        time.sleep(2)
            if not self._ssh_connected:
                raise RuntimeError(
                    "SSH tunnel connection failed. "
                    f"host={self.config.ssh_host}, port={self.config.ssh_port}. "
                    "Please verify the SSH host/port is reachable and that the port is an SSH service. "
                    f"Original error: {last_error}"
                ) from last_error
        return self._ssh_client
    
    def query(self, sql: str, params: Optional[Dict] = None) -> pd.DataFrame:
        """执行 SQL 查询并返回 DataFrame"""
        if self.config.use_ssh:
            return self._query_via_ssh(sql)
        engine = self._get_engine()
        return pd.read_sql(sql, engine, params=params)
    
    def _query_via_ssh(self, sql: str) -> pd.DataFrame:
        """通过 SSH 执行 SQL 查询（复用 SSH 连接）"""
        import uuid
        
        client = self._get_ssh_client()
        
        # Write SQL to temp file to avoid quote escaping issues
        tmp_file = f"/tmp/gllue_query_{uuid.uuid4().hex}.sql"
        sftp = client.open_sftp()
        with sftp.file(tmp_file, "w") as f:
            f.write(sql)
        sftp.close()
        
        cmd = (
            f"mysql -u {self.config.username} "
            f"--password='{self.config.password}' "
            f"-D {self.config.database} "
            f"-B "  # Batch mode: tab-separated, no borders
            f"< {tmp_file}"
        )
        
        stdin, stdout, stderr = client.exec_command(cmd)
        out = stdout.read().decode('utf-8', errors='replace')
        err = stderr.read().decode('utf-8', errors='replace')
        
        # Clean up temp file
        client.exec_command(f"rm -f {tmp_file}")
        
        if err and "Warning" not in err and "warning" not in err:
            raise RuntimeError(f"MySQL error: {err}")
        
        # Parse tab-separated output to DataFrame
        if not out.strip():
            return pd.DataFrame()
        
        df = pd.read_csv(StringIO(out), sep='\t', engine='python', on_bad_lines='skip')
        return df
    
    def close(self):
        """关闭连接"""
        if self._ssh_client and self._ssh_connected:
            self._ssh_client.close()
            self._ssh_connected = False
            self._ssh_client = None
        if self._engine:
            self._engine.dispose()
            self._engine = None
    
    def test_connection(self) -> bool:
        """测试数据库连接"""
        try:
            if self.config.use_ssh:
                df = self._query_via_ssh("SELECT 1 AS connected")
                return not df.empty and df.iloc[0, 0] == 1
            else:
                engine = self._get_engine()
                with engine.connect() as conn:
                    result = conn.execute("SELECT 1")
                    return result.scalar() == 1
        except Exception as e:
            print(f"Connection test failed: {e}")
            return False
    
    def test_connection_and_tables(self) -> tuple:
        """测试连接并返回表数量"""
        try:
            if self.config.use_ssh:
                df = self._query_via_ssh("SELECT 1 AS connected")
                if df.empty or df.iloc[0, 0] != 1:
                    return False, 0
                tables = self._query_via_ssh("SHOW TABLES")
                return True, len(tables)
            else:
                engine = self._get_engine()
                with engine.connect() as conn:
                    result = conn.execute("SELECT 1")
                    if result.scalar() != 1:
                        return False, 0
                    tables = pd.read_sql("SHOW TABLES", engine)
                    return True, len(tables)
        except Exception as e:
            print(f"Connection test failed: {e}")
            return False, 0
    
    # ==================== Schema 探测 ====================
    
    def list_tables(self) -> pd.DataFrame:
        """列出数据库中的所有表"""
        if self.config.db_type == "mysql":
            return self.query("SHOW TABLES")
        elif self.config.db_type == "postgresql":
            return self.query(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
            )
        return pd.DataFrame()
    
    def describe_table(self, table_name: str) -> pd.DataFrame:
        """查看表结构"""
        if self.config.db_type == "mysql":
            return self.query(f"DESCRIBE `{table_name}`")
        elif self.config.db_type == "postgresql":
            return self.query(
                f"""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = '{table_name}'
                """
            )
        return pd.DataFrame()
    
    def detect_schema(self) -> Dict[str, pd.DataFrame]:
        """
        自动探测 Gllue 数据库的关键表结构
        返回关键表的字段信息
        """
        tables = self.list_tables()
        key_tables = ['offersign', 'invoice', 'invoiceassignment', 'joborder', 
                      'jobsubmission', 'candidate', 'user', 'team', 'client',
                      'onboard', 'forecast', 'forecastassignment']
        
        result = {}
        for table in key_tables:
            if self.config.db_type == "mysql":
                col = tables.columns[0]
                matching = tables[tables[col].str.lower() == table.lower()]
                if not matching.empty:
                    actual_name = matching.iloc[0, 0]
                    result[table] = self.describe_table(actual_name)
            else:
                matching = tables[tables['table_name'].str.lower() == table.lower()]
                if not matching.empty:
                    actual_name = matching.iloc[0]['table_name']
                    result[table] = self.describe_table(actual_name)
        
        return result
    
    # ==================== 业绩报表查询 ====================
    
    def get_offers_with_finance(self, start_date: str = "2026-01-01", 
                                 end_date: str = "2026-12-31") -> pd.DataFrame:
        """
        获取带财务数据的 Offer 列表
        
        关键字段：
        - annualSalary: 年薪（数据库中有真实值，API 返回 0）
        - revenue: 佣金收入
        - hunterFee: 猎头费
        - joborder_id: 用于关联 invoice 表判断回款状态
        """
        sql = f"""
        SELECT 
            os.id AS offer_id,
            os.signDate AS offer_date,
            c.name AS client_name,
            CONCAT(IFNULL(cd.englishName, ''), ' ', IFNULL(cd.chineseName, '')) AS candidate_name,
            jo.id AS joborder_id,
            jo.jobTitle AS position_name,
            CONCAT(IFNULL(u.englishName, ''), ' ', IFNULL(u.chineseName, '')) AS consultant,
            os.annualSalary AS annual_salary,
            os.revenue AS fee_amount,
            os.hunterFee AS hunter_fee,
            os.offerStatus AS status,
            os.onboardDate AS onboard_date,
            os.dateAdded AS date_added
        FROM offersign os
        LEFT JOIN jobsubmission js ON os.jobsubmission_id = js.id
        LEFT JOIN joborder jo ON js.joborder_id = jo.id
        LEFT JOIN client c ON jo.client_id = c.id
        LEFT JOIN candidate cd ON js.candidate_id = cd.id
        LEFT JOIN user u ON os.user_id = u.id
        WHERE os.signDate >= '{start_date}' 
          AND os.signDate <= '{end_date}'
          AND os.active = 1
        ORDER BY os.signDate DESC
        """
        return self.query(sql)
    
    def get_invoices_with_finance(self, start_date: str = "2026-01-01",
                                   end_date: str = "2026-12-31") -> pd.DataFrame:
        """
        获取发票/收款数据
        """
        sql = f"""
        SELECT 
            i.id AS invoice_id,
            i.invoiceAmount AS invoice_amount,
            i.paymentReceived AS payment_received,
            i.status,
            i.sentDate AS sent_date,
            i.paymentReceivedDate AS payment_received_date,
            i.estimatepaymentReceivedDate AS estimated_payment_date,
            i.revenue_confirm_date,
            i.payment_days,
            c.name AS client_name,
            jo.jobTitle AS position_name,
            CONCAT(IFNULL(u.englishName, ''), ' ', IFNULL(u.chineseName, '')) AS consultant
        FROM invoice i
        LEFT JOIN joborder jo ON i.joborder_id = jo.id
        LEFT JOIN client c ON i.client_id = c.id
        LEFT JOIN user u ON i.user_id = u.id
        WHERE i.dateAdded >= '{start_date}'
          AND i.dateAdded <= '{end_date}'
        ORDER BY i.dateAdded DESC
        """
        return self.query(sql)
    
    def get_invoice_collection_by_consultant(self, start_date: str = "") -> pd.DataFrame:
        """
        获取每个顾问的已回款金额（基于 invoice + invoiceassignment 表）
        
        Args:
            start_date: 回款日期起始（默认近1年）
            
        Returns:
            DataFrame: consultant, total_received
        """
        if not start_date:
            start_date = (datetime.now() - pd.Timedelta(days=365)).strftime('%Y-%m-%d')
        
        sql = f"""
        SELECT 
            CONCAT(IFNULL(u.englishName, ''), ' ', IFNULL(u.chineseName, '')) AS consultant,
            ia.user_id,
            COUNT(DISTINCT i.id) AS invoice_count,
            SUM(ia.revenue) AS total_received
        FROM invoice i
        JOIN invoiceassignment ia ON ia.invoice_id = i.id
        JOIN user u ON ia.user_id = u.id
        WHERE i.status = 'Received'
          AND i.paymentReceivedDate >= '{start_date}'
        GROUP BY ia.user_id
        ORDER BY total_received DESC
        """
        return self.query(sql)
    
    def get_invoice_assignment_by_consultant(self, start_date: str = "") -> pd.DataFrame:
        """
        获取每个顾问的发票分配明细（包括已回款和未回款）
        用于计算"已Offer未回款"的个人分配金额
        
        已回款：按 paymentReceivedDate 过滤（近1年实际回款，与过程数据口径一致）
        未回款：包含所有未回款发票（不限创建时间，但限制 sentDate 在近两年内）
        
        Returns:
            DataFrame: consultant, user_id, invoice_id, assigned_amount, role, invoice_status, joborder_id
        """
        if not start_date:
            start_date = (datetime.now() - pd.Timedelta(days=365)).strftime('%Y-%m-%d')
        # 未回款发票限制为近两年（即start_date往前再推1年）
        unbilled_start = (datetime.now() - pd.Timedelta(days=730)).strftime('%Y-%m-%d')
        
        sql = f"""
        SELECT 
            CONCAT(IFNULL(u.englishName, ''), ' ', IFNULL(u.chineseName, '')) AS consultant,
            ia.user_id,
            ia.invoice_id,
            ia.revenue AS assigned_amount,
            ia.assignment_role AS role,
            i.status AS invoice_status,
            i.joborder_id,
            i.invoiceAmount,
            i.paymentReceived,
            jo.jobTitle AS position_name,
            c.name AS client_name
        FROM invoiceassignment ia
        JOIN invoice i ON ia.invoice_id = i.id
        JOIN user u ON ia.user_id = u.id
        LEFT JOIN joborder jo ON i.joborder_id = jo.id
        LEFT JOIN client c ON jo.client_id = c.id
        WHERE (
            -- 近1年已回款（与推荐/面试/Offer等过程数据口径一致）
            (i.status = 'Received' AND i.paymentReceivedDate >= '{start_date}')
            OR
            -- 未回款（近两年内发送的发票，避免历史数据干扰）
            (i.status != 'Received' AND (i.sentDate >= '{unbilled_start}' OR i.sendDate >= '{unbilled_start}' OR i.dateAdded >= '{unbilled_start}'))
        )
        ORDER BY ia.user_id, i.dateAdded DESC
        """
        return self.query(sql)
    
    def get_invoice_status_by_joborder(self, year: int = 2026) -> pd.DataFrame:
        """
        获取每个 joborder 的发票回款状态
        
        Args:
            year: 计算该年度的回款金额（用于本年已回款统计）
        
        Returns:
            DataFrame: joborder_id, total_invoiced, total_received, received_year, payment_date
        """
        sql = f"""
        SELECT 
            i.jobOrder_id AS joborder_id,
            SUM(i.invoiceAmount) AS total_invoiced,
            SUM(i.paymentReceived) AS total_received,
            SUM(CASE WHEN i.paymentReceivedDate >= '{year}-01-01' AND i.paymentReceivedDate < '{year+1}-01-01' THEN i.paymentReceived ELSE 0 END) AS received_year,
            MAX(i.paymentReceivedDate) AS payment_date
        FROM invoice i
        WHERE i.jobOrder_id IS NOT NULL
        GROUP BY i.jobOrder_id
        """
        return self.query(sql)
    
    def _get_payment_terms_from_contract(self, client_id, reference_date) -> int:
        """
        从客户合同获取真实账期天数
        
        优先查找覆盖 reference_date 的有效合同，取最新合同的 payment_terms。
        支持加密字符串映射（Gllue系统中的固定选项编码）。
        
        Args:
            client_id: 客户ID
            reference_date: 参考日期（用于判断合同是否有效）
            
        Returns:
            账期天数，默认60天
        """
        if client_id is None or pd.isna(client_id):
            return 60
        
        ref_str = pd.to_datetime(reference_date).strftime('%Y-%m-%d')
        
        sql = f"""
        SELECT payment_terms
        FROM clientcontract
        WHERE client_id = {client_id}
          AND (is_deleted = 0 OR is_deleted IS NULL)
          AND (invalid != 1 OR invalid IS NULL)
          AND startDate <= '{ref_str}'
          AND (expireDate >= '{ref_str}' OR expireDate IS NULL)
        ORDER BY startDate DESC
        LIMIT 1
        """
        try:
            df = self.query(sql)
        except Exception:
            return 60
        
        if df.empty:
            return 60
        
        terms = df['payment_terms'].iloc[0]
        if pd.isna(terms) or terms is None:
            return 60
        
        # 尝试直接解析数字
        try:
            return int(float(terms))
        except (ValueError, TypeError):
            pass
        
        # 加密字符串映射（Gllue系统中的固定选项编码）
        encrypted_map = {
            'FXWBwWyR7sRFX6tGCh': 120,  # 诺华截图显示 120 days
            '_fdjDbWRqUypygU6nR': 90,   # 泰格旧合同，estimated_days≈92
        }
        return encrypted_map.get(str(terms).strip(), 60)
    
    def get_overdue_invoices_amount(self, cutoff_date: datetime = None) -> float:
        """
        获取逾期未回款金额（基于 invoice 表，按真实合同账期判断）
        
        逾期双标准：
        1. Invoice Added 状态：超过35天未寄出（dateAdded + 35天 < 截止日期）
        2. Sent 状态：超过合同账期未回款（sentDate + 真实账期 < 截止日期）
        - 且未完全回款（paymentReceived < invoiceAmount）
        
        Args:
            cutoff_date: 截止日期，默认为今天
            
        Returns:
            逾期未回款总金额
        """
        if cutoff_date is None:
            cutoff_date = datetime.now()
        
        sql = """
        SELECT 
            i.id, i.status, i.invoiceAmount, i.paymentReceived,
            i.sentDate, i.dateAdded, i.estimatepaymentReceivedDate,
            jo.client_id, c.name as client_name
        FROM invoice i
        LEFT JOIN joborder jo ON i.joborder_id = jo.id
        LEFT JOIN client c ON jo.client_id = c.id
        WHERE i.status IN ('Sent', 'Invoice Added')
          AND (i.paymentReceived IS NULL OR i.paymentReceived < i.invoiceAmount)
        """
        df = self.query(sql)
        if df.empty:
            return 0.0
        
        overdue_total = 0.0
        for _, row in df.iterrows():
            status = row['status']
            invoice_amount = row['invoiceAmount']
            payment_received = row['paymentReceived']
            
            if pd.isna(invoice_amount) or invoice_amount is None:
                continue
            invoice_amount = float(invoice_amount)
            
            if pd.isna(payment_received) or payment_received is None:
                payment_received = 0.0
            else:
                payment_received = float(payment_received)
            
            pending = invoice_amount - payment_received
            if pending <= 0 or pd.isna(pending):
                continue
            
            # 确定到期日 due_date
            due_date = None
            
            if status == 'Invoice Added':
                # 标准1：超过35天未寄出
                added_date = row['dateAdded']
                if not pd.isna(added_date) and added_date is not None:
                    due_date = pd.to_datetime(added_date) + pd.Timedelta(days=35)
            
            elif status == 'Sent':
                # 标准2：超过合同账期未回款
                sent_date = row['sentDate']
                if not pd.isna(sent_date) and sent_date is not None:
                    client_id = row['client_id']
                    payment_days = self._get_payment_terms_from_contract(
                        client_id, 
                        pd.to_datetime(sent_date)
                    )
                    due_date = pd.to_datetime(sent_date) + pd.Timedelta(days=payment_days)
            
            if due_date is not None and due_date.date() < cutoff_date.date():
                overdue_total += pending
        
        return float(overdue_total)
    
    def get_client_payment_stats(self) -> pd.DataFrame:
        """
        获取客户历史账期统计（用于催款参考和信用评估）
        
        计算每个客户的：
        - 历史平均实际回款天数
        - 历史平均合同账期
        - 发票数量、逾期次数、逾期率
        
        Returns:
            DataFrame: 客户历史账期统计
        """
        sql = """
        SELECT 
            jo.client_id,
            c.name as client_name,
            COUNT(*) as invoice_count,
            AVG(DATEDIFF(i.paymentReceivedDate, i.sentDate)) as avg_actual_days,
            AVG(i.payment_days) as avg_contract_terms,
            SUM(CASE WHEN DATEDIFF(i.paymentReceivedDate, i.sentDate) > 
                COALESCE(i.payment_days, 60) THEN 1 ELSE 0 END) as overdue_count
        FROM invoice i
        JOIN joborder jo ON i.joborder_id = jo.id
        LEFT JOIN client c ON jo.client_id = c.id
        WHERE i.status = 'Received'
          AND i.sentDate IS NOT NULL
          AND i.paymentReceivedDate IS NOT NULL
        GROUP BY jo.client_id, c.name
        HAVING invoice_count >= 1
        ORDER BY avg_actual_days DESC
        """
        df = self.query(sql)
        if df.empty:
            return df
        
        df['avg_actual_days'] = df['avg_actual_days'].fillna(0).round(0).astype(int)
        df['avg_contract_terms'] = df['avg_contract_terms'].fillna(0).round(0).astype(int)
        df['overdue_count'] = df['overdue_count'].fillna(0).astype(int)
        df['overdue_rate'] = (df['overdue_count'] / df['invoice_count'] * 100).round(1)
        return df
    
    def get_overdue_invoices_detail(self, cutoff_date: datetime = None) -> pd.DataFrame:
        """
        获取逾期发票明细（用于催款提醒）
        
        包含：客户、项目、负责人、合同账期、历史平均账期、逾期天数
        
        Args:
            cutoff_date: 截止日期，默认为今天
            
        Returns:
            DataFrame: 逾期发票明细
        """
        if cutoff_date is None:
            cutoff_date = datetime.now()
        
        # 先获取客户历史账期（用于展示参考）
        hist_stats = self.get_client_payment_stats()
        hist_map = {}
        if not hist_stats.empty:
            for _, row in hist_stats.iterrows():
                hist_map[int(row['client_id'])] = {
                    'avg_actual_days': row['avg_actual_days'],
                    'avg_contract_terms': row['avg_contract_terms'],
                    'overdue_rate': row['overdue_rate']
                }
        
        sql = """
        SELECT 
            i.id as invoice_id,
            i.status,
            i.invoiceAmount,
            i.paymentReceived,
            i.sentDate,
            i.dateAdded,
            i.estimatepaymentReceivedDate,
            jo.client_id,
            c.name as client_name,
            jo.jobTitle as job_title,
            GROUP_CONCAT(DISTINCT CONCAT(IFNULL(u.englishName, ''), ' ', IFNULL(u.chineseName, '')) SEPARATOR ', ') as consultants
        FROM invoice i
        LEFT JOIN joborder jo ON i.joborder_id = jo.id
        LEFT JOIN client c ON jo.client_id = c.id
        LEFT JOIN invoiceassignment ia ON i.id = ia.invoice_id
        LEFT JOIN user u ON ia.user_id = u.id
        WHERE i.status IN ('Sent', 'Invoice Added')
          AND (i.paymentReceived IS NULL OR i.paymentReceived < i.invoiceAmount)
        GROUP BY i.id, i.status, i.invoiceAmount, i.paymentReceived,
                 i.sentDate, i.dateAdded, i.estimatepaymentReceivedDate,
                 jo.client_id, c.name, jo.jobTitle
        ORDER BY i.id
        """
        df = self.query(sql)
        if df.empty:
            return df
        
        results = []
        for _, row in df.iterrows():
            status = row['status']
            invoice_amount = float(row['invoiceAmount']) if not pd.isna(row['invoiceAmount']) and row['invoiceAmount'] is not None else 0
            payment_received = float(row['paymentReceived']) if not pd.isna(row['paymentReceived']) and row['paymentReceived'] is not None else 0
            pending = invoice_amount - payment_received
            if pending <= 0:
                continue
            
            client_id = row['client_id']
            if pd.isna(client_id) or client_id is None:
                client_id = 0
            else:
                client_id = int(client_id)
            
            due_date = None
            contract_terms = None
            overdue_days = 0
            
            if status == 'Invoice Added':
                added_date = row['dateAdded']
                if not pd.isna(added_date) and added_date is not None:
                    due_date = pd.to_datetime(added_date) + pd.Timedelta(days=35)
                    contract_terms = 35
            elif status == 'Sent':
                sent_date = row['sentDate']
                if not pd.isna(sent_date) and sent_date is not None:
                    contract_terms = self._get_payment_terms_from_contract(
                        client_id, pd.to_datetime(sent_date)
                    )
                    due_date = pd.to_datetime(sent_date) + pd.Timedelta(days=contract_terms)
            
            is_overdue = False
            if due_date is not None:
                overdue_days = (cutoff_date.date() - due_date.date()).days
                is_overdue = overdue_days > 0
            
            if is_overdue:
                hist = hist_map.get(client_id, {})
                results.append({
                    'invoice_id': row['invoice_id'],
                    'status': status,
                    'client_name': row['client_name'] or '',
                    'job_title': row['job_title'] or '',
                    'consultants': row['consultants'] or '',
                    'invoice_amount': invoice_amount,
                    'payment_received': payment_received,
                    'pending_amount': pending,
                    'contract_terms': contract_terms,
                    'hist_avg_days': hist.get('avg_actual_days', 'N/A'),
                    'hist_overdue_rate': hist.get('overdue_rate', 'N/A'),
                    'due_date': due_date.date() if due_date else None,
                    'overdue_days': overdue_days,
                })
        
        return pd.DataFrame(results)
    
    def get_invoice_assignments(self, start_date: str = "2026-01-01",
                                 end_date: str = "2026-12-31") -> pd.DataFrame:
        """
        获取发票分配数据（顾问维度佣金）
        """
        sql = f"""
        SELECT 
            ia.invoice_id,
            ia.user_id,
            CONCAT(IFNULL(u.englishName, ''), ' ', IFNULL(u.chineseName, '')) AS consultant,
            u.team_id,
            ia.revenue,
            ia.tax_included_revenue,
            ia.undertaken_tax,
            ia.assignment_role,
            i.invoiceAmount AS invoice_amount,
            i.paymentReceived AS payment_received,
            i.status,
            i.paymentReceivedDate AS payment_received_date,
            c.name AS client_name,
            jo.jobTitle AS position_name
        FROM invoiceassignment ia
        JOIN invoice i ON ia.invoice_id = i.id
        LEFT JOIN joborder jo ON i.joborder_id = jo.id
        LEFT JOIN client c ON i.client_id = c.id
        LEFT JOIN user u ON ia.user_id = u.id
        WHERE i.dateAdded >= '{start_date}'
          AND i.dateAdded <= '{end_date}'
        ORDER BY i.dateAdded DESC
        """
        return self.query(sql)
    
    def get_onboards(self, start_date: str = "2026-01-01",
                     end_date: str = "2026-12-31") -> pd.DataFrame:
        """
        获取入职数据
        """
        sql = f"""
        SELECT 
            o.id AS onboard_id,
            o.onboardDate AS onboard_date,
            o.probationDate AS probation_date,
            o.warrantyDate AS warranty_date,
            o.contractType AS contract_type,
            o.staffType AS staff_type,
            CONCAT(IFNULL(u.englishName, ''), ' ', IFNULL(u.chineseName, '')) AS consultant,
            u.team_id,
            c.name AS client_name,
            jo.jobTitle AS position_name,
            CONCAT(IFNULL(cd.englishName, ''), ' ', IFNULL(cd.chineseName, '')) AS candidate_name,
            os.annualSalary AS annual_salary,
            os.revenue AS fee_amount
        FROM onboard o
        LEFT JOIN jobsubmission js ON o.jobsubmission_id = js.id
        LEFT JOIN joborder jo ON js.joborder_id = jo.id
        LEFT JOIN client c ON jo.client_id = c.id
        LEFT JOIN candidate cd ON js.candidate_id = cd.id
        LEFT JOIN user u ON o.user_id = u.id
        LEFT JOIN offersign os ON js.id = os.jobsubmission_id AND os.active = 1
        WHERE o.onboardDate >= '{start_date}'
          AND o.onboardDate <= '{end_date}'
          AND o.active = 1
        ORDER BY o.onboardDate DESC
        """
        return self.query(sql)
    
    def get_forecast_pipeline(self, start_date: str = "2026-01-01",
                              end_date: str = "2026-12-31",
                              active_only: bool = True) -> pd.DataFrame:
        """
        获取 Forecast / Pipeline 数据（在途单）
        按 forecastassignment 级别返回，和 Gllue 系统"进行中"视图一致
        
        Args:
            start_date: 预计成交开始日期
            end_date: 预计成交结束日期
            active_only: 是否只显示"进行中"的forecast（jobStatus='Live'且stage不为空）
        """
        sql = f"""
        SELECT 
            fa.id AS assignment_id,
            f.id AS forecast_id,
            jo.id AS joborder_id,
            jo.jobTitle AS position_name,
            c.name AS client_name,
            f.charge_package,
            f.fee_rate,
            f.forecast_fee,
            f.forecast_fee_after_tax,
            f.forecast_one_hundred_percent,
            f.close_date,
            f.last_stage AS stage,
            -- 按阶段计算成功率（根据 Gllue 系统设置）
            CASE 
                WHEN f.last_stage LIKE '%Shortlist%' OR f.last_stage LIKE '%简历推荐%' OR f.last_stage LIKE '%Longlist%' THEN 10
                WHEN f.last_stage LIKE '%CCM 1st%' OR f.last_stage LIKE '%客户1面%' OR f.last_stage LIKE '%1st%' THEN 25
                WHEN f.last_stage LIKE '%CCM 2nd%' OR f.last_stage LIKE '%客户2面%' OR f.last_stage LIKE '%2nd%' THEN 30
                WHEN f.last_stage LIKE '%CCM 3rd%' OR f.last_stage LIKE '%客户3面%' OR f.last_stage LIKE '%3rd%' THEN 40
                WHEN f.last_stage LIKE '%Final%' OR f.last_stage LIKE '%终面%' THEN 50
                WHEN f.last_stage LIKE '%Offer%' AND f.last_stage NOT LIKE '%签署%' THEN 80
                WHEN f.last_stage LIKE '%Onboard%' OR f.last_stage LIKE '%入职%' THEN 100
                WHEN f.last_stage LIKE '%加入项目%' OR f.last_stage LIKE '%New%' THEN 5
                ELSE 10
            END AS success_rate,
            f.tax_rate,
            f.dateAdded AS date_added,
            f.lastUpdateDate AS last_update_date,
            f.note,
            -- forecastassignment 字段
            fa.role AS assignment_role,
            fa.ratio AS assignment_ratio,
            fa.amount_after_tax AS assignment_amount,
            fa.amount_before_tax AS assignment_amount_before_tax,
            fa.amount_one_hundred_percent AS assignment_amount_100,
            -- 顾问信息
            CONCAT(IFNULL(ua.englishName, ''), ' ', IFNULL(ua.chineseName, '')) AS consultant,
            -- 添加人/更新人
            CONCAT(IFNULL(ub.englishName, ''), ' ', IFNULL(ub.chineseName, '')) AS added_by,
            CONCAT(IFNULL(uc.englishName, ''), ' ', IFNULL(uc.chineseName, '')) AS last_update_by,
            -- joborder 额外信息
            jo.openDate AS job_open_date,
            jo.effective_candidate_count,
            jo.jobStatus AS job_status
        FROM forecastassignment fa
        JOIN forecast f ON fa.forecast_id = f.id
        LEFT JOIN joborder jo ON f.job_order_id = jo.id
        LEFT JOIN client c ON jo.client_id = c.id
        LEFT JOIN user ua ON fa.user_id = ua.id
        LEFT JOIN user ub ON f.addedBy_id = ub.id
        LEFT JOIN user uc ON f.lastUpdateBy_id = uc.id
        WHERE f.close_date >= '{start_date}'
          AND f.close_date <= '{end_date}'
        """
        
        if active_only:
            sql += """
          AND jo.jobStatus = 'Live'
          AND f.last_stage IS NOT NULL
          AND f.last_stage != ''
        """
        
        sql += "ORDER BY f.close_date DESC"
        
        return self.query(sql)
    
    def get_performance_report_2026(self, start_date: str = "2026-01-01",
                                     end_date: str = "2026-12-31") -> pd.DataFrame:
        """
        获取 2026 业绩报表数据（团队/顾问维度）
        """
        sql = f"""
        SELECT 
            'offer_sign' AS metric_type,
            CONCAT(IFNULL(u.englishName, ''), ' ', IFNULL(u.chineseName, '')) AS consultant,
            u.team_id,
            COUNT(os.id) AS deal_count,
            SUM(os.annualSalary) AS total_salary,
            SUM(os.revenue) AS total_revenue,
            DATE_FORMAT(os.signDate, '%Y-%m') AS month
        FROM offersign os
        LEFT JOIN user u ON os.user_id = u.id
        WHERE os.signDate >= '{start_date}'
          AND os.signDate <= '{end_date}'
          AND os.active = 1
        GROUP BY u.id, DATE_FORMAT(os.signDate, '%Y-%m')
        
        UNION ALL
        
        SELECT 
            'invoice_received' AS metric_type,
            CONCAT(IFNULL(u.englishName, ''), ' ', IFNULL(u.chineseName, '')) AS consultant,
            u.team_id,
            COUNT(DISTINCT ia.invoice_id) AS deal_count,
            NULL AS total_salary,
            SUM(ia.revenue) AS total_revenue,
            DATE_FORMAT(i.paymentReceivedDate, '%Y-%m') AS month
        FROM invoiceassignment ia
        JOIN invoice i ON ia.invoice_id = i.id
        LEFT JOIN user u ON ia.user_id = u.id
        WHERE i.paymentReceivedDate >= '{start_date}'
          AND i.paymentReceivedDate <= '{end_date}'
          AND i.status = 'Received'
        GROUP BY u.id, DATE_FORMAT(i.paymentReceivedDate, '%Y-%m')
        
        UNION ALL
        
        SELECT 
            'onboard' AS metric_type,
            CONCAT(IFNULL(u.englishName, ''), ' ', IFNULL(u.chineseName, '')) AS consultant,
            u.team_id,
            COUNT(o.id) AS deal_count,
            NULL AS total_salary,
            NULL AS total_revenue,
            DATE_FORMAT(o.onboardDate, '%Y-%m') AS month
        FROM onboard o
        LEFT JOIN user u ON o.user_id = u.id
        WHERE o.onboardDate >= '{start_date}'
          AND o.onboardDate <= '{end_date}'
          AND o.active = 1
        GROUP BY u.id, DATE_FORMAT(o.onboardDate, '%Y-%m')
        
        ORDER BY month DESC, total_revenue DESC
        """
        return self.query(sql)
    
    def sync_to_finance_analyzer(self, analyzer, start_date: str = "", 
                                  end_date: str = "") -> Dict:
        """
        同步数据到财务分析器（数据库直连版）
        顾问配置保持手动添加，只同步成单数据和Forecast数据
        """
        if not start_date:
            start_date = "2026-01-01"
        if not end_date:
            end_date = "2026-12-31"
        
        stats = {
            'offers_fetched': 0,
            'invoices_fetched': 0,
            'onboards_fetched': 0,
            'forecasts_fetched': 0,
            'source': 'database'
        }
        
        # 1. 获取 Offer 数据（带财务字段）
        offers_df = self.get_offers_with_finance(start_date, end_date)
        stats['offers_fetched'] = len(offers_df)
        
        # 2. 获取 Forecast 数据
        forecasts_df = self.get_forecast_pipeline(start_date, end_date)
        stats['forecasts_fetched'] = len(forecasts_df)
        
        # 3. 从 invoice 表获取回款状态（覆盖 offersign 的不准确状态）
        try:
            invoice_status_df = self.get_invoice_status_by_joborder()
            consultant_collection_df = self.get_invoice_collection_by_consultant()
            consultant_invoice_assignment_df = self.get_invoice_assignment_by_consultant()
            stats['invoices_fetched'] = len(invoice_status_df)
        except Exception:
            invoice_status_df = pd.DataFrame()
            consultant_collection_df = pd.DataFrame()
            consultant_invoice_assignment_df = pd.DataFrame()
        
        # 4. 加载到分析器 —— 列名映射
        if not offers_df.empty and hasattr(analyzer, 'load_positions_from_dataframe'):
            # 列名映射：让数据库字段匹配 load_positions_from_dataframe 期望的列名
            df = offers_df.copy()
            # 日期字段映射
            if 'date_added' in df.columns:
                df['created_date'] = df['date_added']
            if 'offer_date' in df.columns:
                df['deal_date'] = df['offer_date']
            
            # 佣金状态映射：优先用 invoice 表的真实回款状态
            if not invoice_status_df.empty and 'joborder_id' in df.columns:
                # Merge invoice status into offers
                df = df.merge(
                    invoice_status_df[['joborder_id', 'total_received', 'total_invoiced', 'received_year', 'payment_date']],
                    on='joborder_id',
                    how='left'
                )
                # 判断回款状态：基于全部历史回款（判断该offer总体是否已回款）
                def _get_payment_status(row):
                    received = pd.to_numeric(row.get('total_received'), errors='coerce')
                    invoiced = pd.to_numeric(row.get('total_invoiced'), errors='coerce')
                    if pd.notna(received) and received > 0:
                        if pd.notna(invoiced) and received >= invoiced * 0.99:
                            return '已回款'
                        else:
                            return '部分回款'
                    return '未回款'
                
                df['payment_status'] = df.apply(_get_payment_status, axis=1)
                # 设置回款日期（从invoice的最近回款日期）
                if 'payment_date' in df.columns:
                    df['payment_date'] = pd.to_datetime(df['payment_date'], errors='coerce')
                # actual_payment：按 joborder 只分配给最新签单的 offersign（避免重复计算）
                df['actual_payment'] = 0.0
                df['offer_date'] = pd.to_datetime(df['offer_date'], errors='coerce')
                if 'joborder_id' in df.columns and df['joborder_id'].notna().any():
                    # 按 joborder_id 分组，找到 signDate 最大的行索引
                    for jid, group in df[df['joborder_id'].notna()].groupby('joborder_id'):
                        if len(group) > 1:
                            # 多个 offersign 时，只保留最新签单的 actual_payment
                            latest_idx = group['offer_date'].idxmax()
                            df.loc[latest_idx, 'actual_payment'] = group['received_year'].iloc[0] if pd.notna(group['received_year'].iloc[0]) else 0
                        else:
                            df.loc[group.index[0], 'actual_payment'] = group['received_year'].iloc[0] if pd.notna(group['received_year'].iloc[0]) else 0
                # 清理临时列
                df = df.drop(columns=['total_received', 'total_invoiced', 'received_year'], errors='ignore')
            else:
                # Fallback：用 offersign 的 status（不准确）
                if 'status' in df.columns:
                    df['payment_status'] = df['status'].apply(
                        lambda x: '已回款' if str(x).lower() in ['received', 'paid'] else 
                                  ('已开票' if str(x).lower() in ['sent', 'invoiced'] else '未回款')
                    )
            
            analyzer.load_positions_from_dataframe(df, clear_existing=True)
        
        # 存储顾问回款数据（用于盈亏分析）
        if hasattr(analyzer, 'consultant_configs'):
            # 先清空旧数据，避免重复累积
            analyzer.consultant_collections = {}
            analyzer.consultant_invoice_assignments = {}
        
        if not consultant_collection_df.empty and hasattr(analyzer, 'consultant_configs'):
            for _, row in consultant_collection_df.iterrows():
                consultant_name = str(row.get('consultant', '')).strip()
                if consultant_name:
                    analyzer.consultant_collections[consultant_name] = {
                        'total_received': float(row.get('total_received', 0) or 0),
                        'invoice_count': int(row.get('invoice_count', 0) or 0)
                    }
        
        # 存储顾问发票分配明细（用于计算个人"已Offer未回款"）
        if not consultant_invoice_assignment_df.empty and hasattr(analyzer, 'consultant_configs'):
            for _, row in consultant_invoice_assignment_df.iterrows():
                consultant_name = str(row.get('consultant', '')).strip()
                if consultant_name:
                    if consultant_name not in analyzer.consultant_invoice_assignments:
                        analyzer.consultant_invoice_assignments[consultant_name] = []
                    analyzer.consultant_invoice_assignments[consultant_name].append({
                        'invoice_id': int(row.get('invoice_id', 0) or 0),
                        'assigned_amount': float(row.get('assigned_amount', 0) or 0),
                        'role': str(row.get('role', '') or ''),
                        'invoice_status': str(row.get('invoice_status', '') or ''),
                        'joborder_id': int(row.get('joborder_id', 0) or 0),
                        'position_name': str(row.get('position_name', '') or ''),
                        'client_name': str(row.get('client_name', '') or ''),
                    })
        
        if not forecasts_df.empty and hasattr(analyzer, 'load_forecast_from_dataframe'):
            # 列名映射：让数据库字段匹配 load_forecast_from_dataframe 期望的列名
            df = forecasts_df.copy()
            if 'forecast_fee' in df.columns:
                df['estimated_fee'] = df['forecast_fee']
            if 'close_rate' in df.columns:
                # close_rate 是字符串如 '80%'，需要解析
                df['success_rate'] = df['close_rate'].apply(
                    lambda x: float(str(x).replace('%', '')) if pd.notna(x) and str(x).replace('%', '').replace('.', '').isdigit() else 0.0
                )
            if 'close_date' in df.columns:
                df['expected_close_date'] = df['close_date']
            if 'job_open_date' in df.columns:
                df['start_date'] = df['job_open_date']
            if 'date_added' in df.columns:
                df['created_date'] = df['date_added']
            if 'charge_package' in df.columns:
                df['estimated_salary'] = df['charge_package']
            analyzer.load_forecast_from_dataframe(df, clear_existing=True)
        
        # 5. 获取基于 invoice 表的逾期回款金额（覆盖错误的 Offer 推算逻辑）
        try:
            overdue_amount = self.get_overdue_invoices_amount()
            if hasattr(analyzer, 'overdue_from_invoices'):
                analyzer.overdue_from_invoices = overdue_amount
            stats['overdue_from_invoices'] = overdue_amount
            
            # 同时同步逾期明细（用于催收提醒展示）
            overdue_detail = self.get_overdue_invoices_detail()
            analyzer.overdue_invoices_detail = overdue_detail
            stats['overdue_count'] = len(overdue_detail) if not overdue_detail.empty else 0
        except Exception as e:
            stats['overdue_from_invoices'] = 0
            stats['overdue_count'] = 0
        
        return stats
