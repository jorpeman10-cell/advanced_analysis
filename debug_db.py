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

# Debug: show raw output
import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("118.190.96.172", port=9998, username="root", password="Tstar2026!", timeout=30)

cmd = "mysql -u debian-sys-maint --password='IfUntY7bQZN5kDsk' -D gllue -e 'SHOW TABLES LIMIT 5'"
stdin, stdout, stderr = ssh.exec_command(cmd)
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')

print("=== STDOUT ===")
print(repr(out))
print("=== STDERR ===")
print(repr(err))

# Also test the client's query method
df = client.query("SHOW TABLES LIMIT 5")
print("=== DataFrame ===")
print(df)
print(f"Rows: {len(df)}")

ssh.close()
