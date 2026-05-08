import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("118.190.96.172", port=9998, username="root", password="Tstar2026!", timeout=30)

pw = "IfUntY7bQZN5kDsk"

queries = [
    ("offersign_count", "SELECT COUNT(*) FROM offersign WHERE signDate >= '2026-01-01'"),
    ("offersign_salary_nonzero", "SELECT COUNT(*) FROM offersign WHERE signDate >= '2026-01-01' AND annualSalary > 0"),
    ("offersign_revenue_nonzero", "SELECT COUNT(*) FROM offersign WHERE signDate >= '2026-01-01' AND revenue > 0"),
    ("offersign_hunterfee_nonzero", "SELECT COUNT(*) FROM offersign WHERE signDate >= '2026-01-01' AND hunterFee > 0"),
    ("offersign_sample", "SELECT id, annualSalary, revenue, hunterFee, signDate, offerStatus FROM offersign WHERE signDate >= '2026-01-01' LIMIT 5"),
    ("invoice_count", "SELECT COUNT(*) FROM invoice WHERE dateAdded >= '2026-01-01'"),
    ("invoice_payment_nonzero", "SELECT COUNT(*) FROM invoice WHERE dateAdded >= '2026-01-01' AND paymentReceived > 0"),
    ("invoice_sample", "SELECT id, invoiceAmount, paymentReceived, status, sentDate, paymentReceivedDate FROM invoice WHERE dateAdded >= '2026-01-01' LIMIT 5"),
    ("invoiceassignment_count", "SELECT COUNT(*) FROM invoiceassignment WHERE id IN (SELECT id FROM invoice WHERE dateAdded >= '2026-01-01')"),
    ("invoiceassignment_sample", "SELECT invoice_id, user_id, revenue, tax_included_revenue FROM invoiceassignment LIMIT 5"),
    ("onboard_count", "SELECT COUNT(*) FROM onboard WHERE onboardDate >= '2026-01-01'"),
    ("joborder_count", "SELECT COUNT(*) FROM joborder WHERE dateAdded >= '2026-01-01'"),
]

for name, sql in queries:
    cmd = f"mysql -u debian-sys-maint --password='{pw}' -D gllue -e '{sql}'"
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode()
    err = stderr.read().decode()
    print(f"\n=== {name} ===")
    print(out)
    if err and "Warning" not in err:
        print("ERR:", err)

client.close()
