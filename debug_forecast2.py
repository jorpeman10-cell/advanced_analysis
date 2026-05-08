import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("118.190.96.172", port=9998, username="root", password="Tstar2026!", timeout=30)

pw = "IfUntY7bQZN5kDsk"

queries = [
    ("forecast_date_range", "SELECT MIN(close_date) AS min_date, MAX(close_date) AS max_date, COUNT(*) AS cnt FROM forecast"),
    ("forecast_2026", "SELECT COUNT(*) AS cnt FROM forecast WHERE close_date >= '2026-01-01' AND close_date <= '2026-12-31'"),
    ("forecastassignment_count", "SELECT COUNT(*) AS cnt FROM forecastassignment"),
    ("join_test", """
SELECT COUNT(*) AS cnt 
FROM forecastassignment fa 
JOIN forecast f ON fa.forecast_id = f.id 
WHERE f.close_date >= '2026-01-01' AND f.close_date <= '2026-12-31'
"""),
    ("sample_with_stage", """
SELECT 
    fa.id AS assignment_id,
    f.id AS forecast_id,
    f.last_stage,
    f.close_date,
    fa.role,
    fa.ratio
FROM forecastassignment fa
JOIN forecast f ON fa.forecast_id = f.id
WHERE f.close_date >= '2026-01-01'
LIMIT 5
"""),
]

for name, sql in queries:
    cmd = f"mysql -u debian-sys-maint --password='{pw}' -D gllue -e '{sql}'"
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    print(f"\n=== {name} ===")
    print(out)
    if err and "Warning" not in err:
        print("ERR:", err)

client.close()
