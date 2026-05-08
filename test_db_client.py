"""测试数据库客户端"""
from gllue_db_client import GllueDBConfig, GllueDBClient

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

# 测试连接
print("测试连接...")
result = client.test_connection()
print(f"连接结果: {result}")

# 测试查询
print("\n测试查询 offersign...")
df = client.get_offers_with_finance("2026-01-01", "2026-12-31")
print(f"Offer 数量: {len(df)}")
if not df.empty:
    print(df.head(3).to_string())

print("\n测试查询 invoice...")
df = client.get_invoices_with_finance("2026-01-01", "2026-12-31")
print(f"Invoice 数量: {len(df)}")

print("\n测试查询 onboard...")
df = client.get_onboards("2026-01-01", "2026-12-31")
print(f"Onboard 数量: {len(df)}")

print("\n测试查询 forecast...")
df = client.get_forecast_pipeline("2026-01-01", "2026-12-31")
print(f"Forecast 数量: {len(df)}")

print("\n测试查询 performance report...")
df = client.get_performance_report_2026("2026-01-01", "2026-12-31")
print(f"Report 数量: {len(df)}")
if not df.empty:
    print(df.head(10).to_string())
