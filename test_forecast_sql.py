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
df = client.get_forecast_pipeline("2026-01-01", "2026-12-31")

print(f"Total rows: {len(df)}")
print(f"Columns: {df.columns.tolist()}")
print()
print("=== First 3 rows ===")
print(df.head(3).to_string())
print()
print("=== Stage distribution ===")
print(df['stage'].value_counts().head(10))
print()
print("=== Success rate sample ===")
print(df[['stage', 'success_rate', 'charge_package', 'fee_rate', 'forecast_fee', 'assignment_ratio', 'assignment_amount', 'consultant']].head(10).to_string())
