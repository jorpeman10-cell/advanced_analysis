import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("118.190.96.172", port=9998, username="root", password="Tstar2026!", timeout=30)

pw = "IfUntY7bQZN5kDsk"

queries = [
    ("id_eq", "SELECT COUNT(*) AS cnt FROM forecast WHERE id = 1"),
    ("date_gt", "SELECT COUNT(*) AS cnt FROM forecast WHERE close_date > '2025-01-01'"),
    ("date_gt2", "SELECT COUNT(*) AS cnt FROM forecast WHERE close_date > '2026-01-01'"),
    ("date_strcmp", "SELECT COUNT(*) AS cnt FROM forecast WHERE STRCMP(close_date, '2026-03-01') = 0"),
    ("date_year", "SELECT COUNT(*) AS cnt FROM forecast WHERE YEAR(close_date) = 2026"),
    ("date_format", "SELECT COUNT(*) AS cnt FROM forecast WHERE DATE_FORMAT(close_date, '%Y-%m-%d') = '2026-03-01'"),
    ("show_create", "SHOW CREATE TABLE forecast"),
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
