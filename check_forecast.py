import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("118.190.96.172", port=9998, username="root", password="Tstar2026!", timeout=30)

pw = "IfUntY7bQZN5kDsk"

# Check forecast table sample
queries = [
    ("forecast_sample", "SELECT id, job_order_id, charge_package, fee_rate, forecast_fee, close_date, close_rate, last_stage, dateAdded FROM forecast LIMIT 5"),
    ("forecast_close_rate_values", "SELECT DISTINCT close_rate FROM forecast WHERE close_date >= '2026-01-01' LIMIT 20"),
    ("forecastassignment_sample", "SELECT id, forecast_id, user_id, role, amount_after_tax, amount_before_tax, ratio FROM forecastassignment LIMIT 5"),
    ("forecast_with_assignment", """
SELECT 
    fa.id AS assignment_id,
    f.id AS forecast_id,
    jo.id AS joborder_id,
    jo.jobTitle AS position_name,
    c.name AS client_name,
    f.charge_package,
    f.fee_rate,
    fa.amount_after_tax AS forecast_fee,
    f.close_date,
    f.close_rate,
    f.last_stage,
    fa.ratio AS success_rate,
    fa.role,
    CONCAT(IFNULL(u.englishName, ''), ' ', IFNULL(u.chineseName, '')) AS consultant,
    f.dateAdded,
    f.lastUpdateDate
FROM forecastassignment fa
JOIN forecast f ON fa.forecast_id = f.id
LEFT JOIN joborder jo ON f.job_order_id = jo.id
LEFT JOIN client c ON jo.client_id = c.id
LEFT JOIN user u ON fa.user_id = u.id
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
