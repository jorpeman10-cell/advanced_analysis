import paramiko
import time

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("118.190.96.172", port=9998, username="root", password="Tstar2026!", timeout=30)

# Interactive MySQL login
cmd = "mysql -u root -p -e 'SELECT 1'"
stdin, stdout, stderr = client.exec_command(cmd)

# Wait for password prompt
time.sleep(1)

# Try sending password
stdin.write("Tstar2026!\n")
stdin.flush()

time.sleep(2)

out = stdout.read().decode()
err = stderr.read().decode()
print("OUT:", out)
print("ERR:", err)

client.close()
