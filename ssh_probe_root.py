import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("118.190.96.172", port=9998, username="root", password="Tstar2026!", timeout=30)

# Try root login to MySQL
cmd = "mysql -u root --password='Tstar2026!' -e 'SELECT user, host FROM mysql.user'"
stdin, stdout, stderr = client.exec_command(cmd)
out = stdout.read().decode()
err = stderr.read().decode()
print("=== MySQL Users ===")
print(out)
if err:
    print("ERR:", err)

client.close()
