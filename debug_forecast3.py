import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("118.190.96.172", port=9998, username="root", password="Tstar2026!", timeout=30)

pw = "IfUntY7bQZN5kDsk"

queries = [
    ("lte_test", "SELECT COUNT(*) AS cnt FROM forecast WHERE close_date <= '2026-12-31'"),
    ("eq_test", "SELECT COUNT(*) AS cnt FROM forecast WHERE close_date = '2026-03-01'"),
    ("between_test", "SELECT COUNT(*) AS cnt FROM forecast WHERE close_date BETWEEN '2026-01-01' AND '2026-12-31'"),
    ("str_test", "SELECT COUNT(*) AS cnt FROM forecast WHERE CAST(close_date AS CHAR) <= '2026-12-31'"),
    ("null_check", "SELECT COUNT(*) AS cnt FROM forecast WHERE close_date IS NULL"),
    ("all_dates", "SELECT close_date, COUNT(*) AS cnt FROM forecast GROUP BY close_date ORDER BY close_date"),
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
