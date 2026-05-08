import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("118.190.96.172", port=9998, username="root", password="Tstar2026!", timeout=30)

# Check mysql client
cmd = "which mysql || echo NOT_FOUND"
stdin, stdout, stderr = client.exec_command(cmd)
print("mysql:", stdout.read().decode().strip())

# Check pymysql
cmd = "python -c 'import pymysql; print(\"OK\")' 2>&1 || echo PYMYSQL_MISSING"
stdin, stdout, stderr = client.exec_command(cmd)
print("pymysql:", stdout.read().decode().strip())

client.close()
