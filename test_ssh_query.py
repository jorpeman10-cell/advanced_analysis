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

# Test simple query
df = client.query("SELECT COUNT(*) AS cnt FROM forecast")
print(f"Total forecast: {df}")

# Test with date filter
df = client.query("SELECT COUNT(*) AS cnt FROM forecast WHERE close_date = '2026-03-01'")
print(f"Date eq: {df}")

# Test with date range
df = client.query("SELECT COUNT(*) AS cnt FROM forecast WHERE close_date >= '2026-01-01' AND close_date <= '2026-12-31'")
print(f"Date range: {df}")

# Test new forecast query (simplified)
df = client.query("""
SELECT 
    fa.id AS assignment_id,
    f.id AS forecast_id,
    f.last_stage AS stage,
    f.close_date,
    fa.role,
    fa.ratio
FROM forecastassignment fa
JOIN forecast f ON fa.forecast_id = f.id
WHERE f.close_date >= '2026-01-01'
LIMIT 5
""")
print(f"Join query: {len(df)} rows")
print(df.to_string())
