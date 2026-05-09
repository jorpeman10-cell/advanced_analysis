# Recruiter Finance Tool / Advanced Analysis

Streamlit entrypoint:

```bash
streamlit run app_v2.py
```

## Local Run

```bash
pip install -r requirements.txt
streamlit run app_v2.py --server.port 8503
```

Local database settings are stored in `config/db_config.json`, which must not be committed.

## GitHub Checklist

Before pushing:

```bash
git status --short
```

Commit source files only. Do not commit:

- `config/*.json`
- `cache/`
- `reports/`
- `.streamlit/secrets.toml`
- screenshots, exported PDFs, or temporary data files

## Streamlit Cloud

1. Push this folder to GitHub.
2. In Streamlit Cloud, create a new app from the repo.
3. Set the main file path to:

```text
advanced_analysis/app_v2.py
```

If this folder becomes the repo root, use:

```text
app_v2.py
```

4. Add secrets in Streamlit Cloud using the format in `.streamlit/secrets.example.toml`.

Example:

```toml
[gllue_db]
host = "127.0.0.1"
port = 3306
database = "gllue"
username = "your_db_user"
password = "your_db_password"
use_ssh = true
ssh_host = "your_ssh_host"
ssh_port = 22
ssh_user = "your_ssh_user"
ssh_password = "your_ssh_password"

[consultant_salaries]
"Lucy Wang" = 15000
"Vivien Zhao" = 19000
"Shawn Bian" = 36500
```

If the database is behind SSH, make sure Streamlit Cloud can reach the SSH host and the database host allows the connection path.

For salary data, `consultant_salaries` is a monthly salary mapping. If you do not upload a salary file in the app, v2 reads this Secrets section automatically after every reboot.
