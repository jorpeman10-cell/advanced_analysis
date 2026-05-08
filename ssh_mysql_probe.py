import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("118.190.96.172", port=9998, username="root", password="Tstar2026!", timeout=30)

pw = "IfUntY7bQZN5kDsk"

# Show all tables
cmd = f"mysql -u debian-sys-maint --password='{pw}' -D gllue -e 'SHOW TABLES'"
stdin, stdout, stderr = client.exec_command(cmd)
out = stdout.read().decode()
err = stderr.read().decode()
print("=== TABLES ===")
print(out)
if err:
    print("ERR:", err)

# Describe key tables
tables = ['offersign', 'invoice', 'invoiceassignment', 'joborder', 'user', 'placement', 'candidate', 'company', 'clientcontact']
for t in tables:
    cmd = f"mysql -u debian-sys-maint --password='{pw}' -D gllue -e 'DESCRIBE {t}'"
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode()
    err = stderr.read().decode()
    print(f"\n=== {t} ===")
    print(out)
    if err:
        print("ERR:", err)

client.close()
