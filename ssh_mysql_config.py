import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("118.190.96.172", port=9998, username="root", password="Tstar2026!", timeout=30)

files = [
    "/root/.my.cnf",
    "/etc/mysql/my.cnf",
    "/etc/my.cnf",
    "/etc/mysql/debian.cnf",
]

for f in files:
    cmd = f"cat {f} 2>/dev/null || echo FILE_NOT_FOUND"
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode()
    print(f"\n=== {f} ===")
    print(out[:2000] if out != "FILE_NOT_FOUND\n" else "NOT FOUND")

client.close()
