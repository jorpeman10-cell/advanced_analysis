"""测试数据库同步到分析器"""
import sys
sys.path.append(r"C:\Users\EDY\recruiter_finance_tool\advanced_analysis")

from gllue_db_client import GllueDBConfig, GllueDBClient
from models import AdvancedRecruitmentAnalyzer

config = GllueDBConfig(
    db_type="mysql",
    host="127.0.0.1",
    port=3306,
    database="gllue",
    username="debian-sys-maint",
    password="IfUntY7bQZN5kDsk",
    use_ssh=True,
    ssh_host="118.190.96.172",
    ssh_port=9998,
    ssh_user="root",
    ssh_password="Tstar2026!"
)

client = GllueDBClient(config)
analyzer = AdvancedRecruitmentAnalyzer()

# 测试同步
stats = client.sync_to_finance_analyzer(analyzer, "2026-01-01", "2026-12-31")
print(f"同步结果: {stats}")
print(f"Positions: {len(analyzer.positions)}")
print(f"Forecast: {len(analyzer.forecast_positions)}")

if analyzer.positions:
    print("\n=== 第一个 Position ===")
    p = analyzer.positions[0]
    print(f"ID: {p.position_id}, Client: {p.client_name}, Position: {p.position_name}")
    print(f"Consultant: {p.consultant}, Team: {p.team}")
    print(f"Created: {p.created_date}, Offer: {p.offer_date}, Onboard: {p.onboard_date}")
    print(f"Annual Salary: {p.annual_salary}, Fee: {p.fee_amount}, Actual: {p.actual_payment}")

if analyzer.forecast_positions:
    print("\n=== 第一个 Forecast ===")
    f = analyzer.forecast_positions[0]
    print(f"ID: {f.forecast_id}, Client: {f.client_name}, Position: {f.position_name}")
    print(f"Consultant: {f.consultant}, Stage: {f.stage}")
    print(f"Estimated Salary: {f.estimated_salary}, Fee Rate: {f.fee_rate}, Estimated Fee: {f.estimated_fee}")
    print(f"Success Rate: {f.success_rate}")
