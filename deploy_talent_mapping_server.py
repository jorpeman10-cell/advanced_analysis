"""Deploy Talent Mapping MCP updates to the Aliyun server.

Usage:
  python deploy_talent_mapping_server.py inspect
  python deploy_talent_mapping_server.py deploy
  python deploy_talent_mapping_server.py verify
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import posixpath
import secrets
import sys
from pathlib import Path

import paramiko


LOCAL_ROOT = Path(__file__).parent
CONFIG_FILE = LOCAL_ROOT / "config" / "db_config.json"
FILES_TO_DEPLOY = [
    "mcp_server.py",
    "talent_mapping_obsidian_exporter.py",
    "MCP_LOBE_SETUP.md",
    "skills/recruiter-finance-analysis/SKILL.md",
]
STANDALONE_FILES_TO_DEPLOY = [
    "talent_mapping_mcp_server.py",
    "talent_mapping_obsidian_exporter.py",
    "Dockerfile.talent_mapping_mcp",
    "skills/talent-mapping-llm/SKILL.md",
]
REMOTE_CANDIDATES = [
    "/root/advanced_analysis_publish",
    "/root/recruiter_finance_tool/advanced_analysis",
    "/root/recruiter-finance-tool/advanced_analysis",
    "/root/advanced_analysis",
    "/opt/advanced_analysis",
]


def connect() -> paramiko.SSHClient:
    with CONFIG_FILE.open("r", encoding="utf-8") as f:
        cfg = json.load(f)
    password = base64.b64decode(str(cfg.get("ssh_password", "")).encode()).decode()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        cfg.get("ssh_host", "118.190.96.172"),
        port=int(cfg.get("ssh_port", 9998)),
        username=cfg.get("ssh_user", "root"),
        password=password,
        timeout=30,
    )
    return client


def run(client: paramiko.SSHClient, command: str, check: bool = False) -> tuple[int, str, str]:
    stdin, stdout, stderr = client.exec_command(command)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    print(f"\n$ {command}\n{out}", end="")
    if err:
        print(err, end="", file=sys.stderr)
    if check and code != 0:
        raise RuntimeError(f"Remote command failed ({code}): {command}")
    return code, out, err


def detect_project_dir(client: paramiko.SSHClient) -> str:
    for path in REMOTE_CANDIDATES:
        code, out, _ = run(client, f"test -f {path}/mcp_server.py && echo FOUND || true")
        if "FOUND" in out:
            return path
    code, out, _ = run(
        client,
        "find /root /opt -maxdepth 4 -name mcp_server.py 2>/dev/null | head -20",
    )
    paths = [line.strip() for line in out.splitlines() if line.strip()]
    if paths:
        return posixpath.dirname(paths[0])
    raise RuntimeError("Could not find remote mcp_server.py")


def inspect() -> None:
    client = connect()
    try:
        project_dir = detect_project_dir(client)
        print(f"\nREMOTE_PROJECT_DIR={project_dir}")
        run(client, "hostname && date")
        run(client, f"cd {project_dir} && pwd && ls -la | head -40")
        run(client, "docker ps --format 'table {{.ID}}\\t{{.Names}}\\t{{.Status}}\\t{{.Ports}}' 2>/dev/null || true")
        run(client, "ps -ef | grep -E 'mcp_server.py|streamlit|lobe' | grep -v grep || true")
        run(client, "ss -lntp | grep -E ':3210|:8765' || true")
    finally:
        client.close()


def inspect_docker() -> None:
    client = connect()
    try:
        project_dir = detect_project_dir(client)
        print(f"\nREMOTE_PROJECT_DIR={project_dir}")
        run(client, "docker inspect recruiter-finance-mcp --format '{{json .Config.Image}} {{json .Mounts}} {{json .Config.Env}} {{json .HostConfig.PortBindings}} {{json .NetworkSettings.Networks}}' 2>/dev/null || true")
        run(client, "docker inspect lobehub --format '{{json .NetworkSettings.Networks}} {{json .Config.Env}}' 2>/dev/null || true")
        run(client, f"find {project_dir} -maxdepth 2 -iname '*compose*' -o -name 'Dockerfile*' | sort")
        run(client, f"cd {project_dir} && grep -R \"recruiter-finance-mcp\\|mcp_server.py\\|8765\" -n docker-compose* Dockerfile* *.yml *.yaml 2>/dev/null || true")
        run(client, "docker exec recruiter-finance-mcp sh -lc 'pwd; ls -la /app 2>/dev/null | head -40; grep -R \"export_talent_mapping_obsidian_vault\" -n /app 2>/dev/null || true' 2>/dev/null || true")
    finally:
        client.close()


def upload_file(sftp: paramiko.SFTPClient, local: Path, remote: str) -> None:
    remote_dir = posixpath.dirname(remote)
    try:
        sftp.stat(remote_dir)
    except FileNotFoundError:
        parts = remote_dir.strip("/").split("/")
        current = ""
        for part in parts:
            current += "/" + part
            try:
                sftp.stat(current)
            except FileNotFoundError:
                sftp.mkdir(current)
    sftp.put(str(local), remote)
    print(f"uploaded {local.name} -> {remote}")


def deploy() -> None:
    client = connect()
    try:
        project_dir = detect_project_dir(client)
        quoted_files = " ".join(FILES_TO_DEPLOY)
        run(
            client,
            f"cd {project_dir} && backup_dir={project_dir}/_backup_talent_mapping_$(date +%Y%m%d_%H%M%S) && "
            f"mkdir -p \"$backup_dir\" && for f in {quoted_files}; do [ -f \"$f\" ] && cp --parents \"$f\" \"$backup_dir\"/ || true; done",
            check=True,
        )
        sftp = client.open_sftp()
        try:
            for rel in FILES_TO_DEPLOY:
                upload_file(sftp, LOCAL_ROOT / rel, posixpath.join(project_dir, rel.replace("\\", "/")))
        finally:
            sftp.close()
        run(client, f"cd {project_dir} && python3 --version 2>&1 || true")
        restart_services(client, project_dir)
    finally:
        client.close()


def deploy_standalone() -> None:
    client = connect()
    try:
        project_dir = detect_project_dir(client)
        quoted_files = " ".join(STANDALONE_FILES_TO_DEPLOY)
        run(
            client,
            f"cd {project_dir} && backup_dir={project_dir}/_backup_talent_mapping_standalone_$(date +%Y%m%d_%H%M%S) && "
            f"mkdir -p \"$backup_dir\" && for f in {quoted_files}; do [ -f \"$f\" ] && cp --parents \"$f\" \"$backup_dir\"/ || true; done",
            check=True,
        )
        sftp = client.open_sftp()
        try:
            for rel in STANDALONE_FILES_TO_DEPLOY:
                upload_file(sftp, LOCAL_ROOT / rel, posixpath.join(project_dir, rel.replace("\\", "/")))
        finally:
            sftp.close()
        restart_standalone_service(client, project_dir)
    finally:
        client.close()


def restart_services(client: paramiko.SSHClient, project_dir: str) -> None:
    run(
        client,
        f"cd {project_dir} && docker build -f Dockerfile.mcp -t recruiter-finance-mcp:latest .",
        check=True,
    )
    run(
        client,
        "TOKEN=$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' recruiter-finance-mcp 2>/dev/null "
        "| awk -F= '/^RECRUITER_FINANCE_MCP_TOKEN=/{print substr($0, index($0,\"=\")+1)}'); "
        "test -n \"$TOKEN\" || TOKEN=${RECRUITER_FINANCE_MCP_TOKEN:-local-lobe-token}; "
        "docker stop recruiter-finance-mcp 2>/dev/null || true; "
        "docker rm recruiter-finance-mcp 2>/dev/null || true; "
        f"mkdir -p {project_dir}/talent_mapping_vault_lobe; "
        "docker run -d --name recruiter-finance-mcp "
        "--network lobehubaliyundeploy_lobe-network "
        "-e RECRUITER_FINANCE_MCP_TOKEN=\"$TOKEN\" "
        "-e RECRUITER_FINANCE_MCP_HOST=0.0.0.0 "
        "-e RECRUITER_FINANCE_MCP_PORT=8765 "
        "-e RECRUITER_FINANCE_MCP_PUBLIC_URL=http://recruiter-finance-mcp:8765 "
        "-e TALENT_MAPPING_OBSIDIAN_OUTPUT=/app/talent_mapping_vault_lobe "
        f"-v {project_dir}/talent_mapping_vault_lobe:/app/talent_mapping_vault_lobe "
        "recruiter-finance-mcp:latest",
        check=True,
    )
    run(client, "sleep 5; docker ps --filter name=recruiter-finance-mcp --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}'")
    run(client, "docker logs recruiter-finance-mcp --tail 60 2>&1 || true")


def restart_standalone_service(client: paramiko.SSHClient, project_dir: str) -> None:
    run(client, "pkill -f 'docker build -f Dockerfile.talent_mapping_mcp' || true")
    run(
        client,
        f"cd {project_dir} && docker build -f Dockerfile.talent_mapping_mcp -t talent-mapping-llm-mcp:latest .",
        check=True,
    )
    run(
        client,
        "TOKEN=$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' recruiter-finance-mcp 2>/dev/null "
        "| awk -F= '/^RECRUITER_FINANCE_MCP_TOKEN=/{print substr($0, index($0,\"=\")+1)}'); "
        "test -n \"$TOKEN\" || TOKEN=${TALENT_MAPPING_MCP_TOKEN:-local-lobe-token}; "
        "docker stop talent-mapping-llm-mcp 2>/dev/null || true; "
        "docker rm talent-mapping-llm-mcp 2>/dev/null || true; "
        f"mkdir -p {project_dir}/talent_mapping_llm_vault; "
        "docker run -d --name talent-mapping-llm-mcp "
        "--network lobehubaliyundeploy_lobe-network "
        "-e TALENT_MAPPING_MCP_AUTH=none "
        "-e TALENT_MAPPING_MCP_HOST=0.0.0.0 "
        "-e TALENT_MAPPING_MCP_PORT=8770 "
        "-e TALENT_MAPPING_MCP_PUBLIC_URL=http://talent-mapping-llm-mcp:8770 "
        "-e TALENT_MAPPING_OBSIDIAN_OUTPUT=/app/talent_mapping_vault "
        f"-v {project_dir}/talent_mapping_llm_vault:/app/talent_mapping_vault "
        "talent-mapping-llm-mcp:latest",
        check=True,
    )
    run(client, "sleep 5; docker ps --filter name=talent-mapping-llm-mcp --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}'")
    run(client, "docker logs talent-mapping-llm-mcp --tail 60 2>&1 || true")


def verify() -> None:
    client = connect()
    try:
        project_dir = detect_project_dir(client)
        run(client, f"cd {project_dir} && grep -R \"export_talent_mapping_obsidian_vault\" -n mcp_server.py")
        run(client, "ss -lntp | grep -E ':3210|:8765' || true")
        run(client, f"cd {project_dir} && tail -80 mcp_server.err.log 2>/dev/null || true")
    finally:
        client.close()


def verify_standalone() -> None:
    client = connect()
    try:
        project_dir = detect_project_dir(client)
        run(client, f"cd {project_dir} && grep -R \"export_talent_mapping_obsidian_vault\" -n talent_mapping_mcp_server.py skills/talent-mapping-llm/SKILL.md")
        run(client, "docker ps --filter name=talent-mapping-llm-mcp --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}'")
        run(client, "docker exec talent-mapping-llm-mcp python -m py_compile talent_mapping_mcp_server.py talent_mapping_obsidian_exporter.py")
        run(client, "docker exec talent-mapping-llm-mcp sh -lc 'python - <<\"PY\"\nimport talent_mapping_mcp_server as s\nprint(s.mcp.name if hasattr(s.mcp, \"name\") else \"talent-mapping-llm-loaded\")\nprint(s.DEFAULT_OUTPUT)\nPY'")
        run(client, f"ls -la {project_dir}/talent_mapping_llm_vault 2>/dev/null || true")
    finally:
        client.close()


def inspect_standalone() -> None:
    client = connect()
    try:
        project_dir = detect_project_dir(client)
        run(client, "ps -ef | grep -E 'docker build|talent_mapping_mcp_server|talent-mapping-llm' | grep -v grep || true")
        run(client, "docker images | grep -E 'talent-mapping|recruiter-finance' || true")
        run(client, "docker ps -a --filter name=talent-mapping-llm-mcp --format 'table {{.Names}}\\t{{.Status}}\\t{{.Image}}'")
        run(client, f"cd {project_dir} && ls -la Dockerfile.talent_mapping_mcp talent_mapping_mcp_server.py talent_mapping_obsidian_exporter.py")
        run(client, "docker logs talent-mapping-llm-mcp --tail 80 2>&1 || true")
    finally:
        client.close()


def inspect_lobe_auth() -> None:
    client = connect()
    try:
        run(client, "docker ps --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}' | grep -E 'lobehub|sandbox|mcp|e2b|code' || true")
        run(client, "docker logs lobehub --tail 200 2>&1 | grep -Ei 'auth|authorize|authorization|sandbox|mcp|plugin|tool|error|failed' || true")
        run(
            client,
            "docker inspect lobehub --format '{{range .Config.Env}}{{println .}}{{end}}' "
            "| awk -F= 'BEGIN{IGNORECASE=1} /SANDBOX|E2B|CODE|PLUGIN|MCP|AUTH|APP_URL|SSRF|KEY_VAULT|DATABASE|NEXT_PUBLIC/ "
            "{ if ($1 ~ /SECRET|KEY|TOKEN|PASSWORD|DATABASE_URL|AUTH/) print $1\"=<set>\"; else print $1\"=\"substr($0,index($0,\"=\")+1) }' || true",
        )
        run(
            client,
            "docker exec lobehub sh -lc 'node -v; printenv' 2>/dev/null "
            "| awk -F= 'BEGIN{IGNORECASE=1} /SANDBOX|E2B|CODE|PLUGIN|MCP|AUTH|APP_URL|SSRF|KEY_VAULT|DATABASE|NEXT_PUBLIC/ "
            "{ if ($1 ~ /SECRET|KEY|TOKEN|PASSWORD|DATABASE_URL|AUTH/) print $1\"=<set>\"; else print $1\"=\"substr($0,index($0,\"=\")+1) }' || true",
        )
        run(client, "docker logs talent-mapping-llm-mcp --tail 60 2>&1 || true")
    finally:
        client.close()


def inspect_lobe_compose() -> None:
    client = connect()
    try:
        run(
            client,
            "docker inspect lobehub --format "
            "'{{ index .Config.Labels \"com.docker.compose.project.working_dir\" }}|"
            "{{ index .Config.Labels \"com.docker.compose.project.config_files\" }}|"
            "{{ index .Config.Labels \"com.docker.compose.service\" }}'",
        )
        run(
            client,
            "docker inspect lobehub --format '{{range .Config.Env}}{{println .}}{{end}}' "
            "| awk -F= '$1==\"APP_URL\" || $1==\"AUTH_TRUSTED_ORIGINS\" || "
            "$1==\"AUTH_EMAIL_VERIFICATION\" {print}'",
        )
    finally:
        client.close()


def inspect_lobe_files() -> None:
    client = connect()
    try:
        run(
            client,
            "find /root /opt /srv /data -maxdepth 5 -type f "
            "\\( -name 'compose.yml' -o -name 'compose.yaml' -o "
            "-name 'docker-compose.yml' -o -name 'docker-compose.yaml' -o -name '.env' \\) "
            "-print 2>/dev/null | head -100",
        )
        run(
            client,
            "docker inspect lobehub --format "
            "'Image={{.Config.Image}} Restart={{.HostConfig.RestartPolicy.Name}} "
            "Network={{.HostConfig.NetworkMode}} Mounts={{json .Mounts}}'",
        )
    finally:
        client.close()


def inspect_lobe_deploy_config() -> None:
    client = connect()
    try:
        run(
            client,
            "cd /root/lobehub-aliyun-deploy && "
            "grep -nE '^(APP_URL|AUTH_TRUSTED_ORIGINS|AUTH_EMAIL_VERIFICATION)=' .env || true",
        )
        run(
            client,
            "cd /root/lobehub-aliyun-deploy && "
            "grep -nE 'lobehub:|image:|container_name:|APP_URL|AUTH_TRUSTED_ORIGINS|"
            "AUTH_EMAIL_VERIFICATION|ports:' docker-compose.yml",
        )
        run(
            client,
            "cd /root/lobehub-aliyun-deploy && sed -n '1,31p' docker-compose.yml "
            "| sed -E 's/(PASSWORD|SECRET|KEY|TOKEN)=.*/\\1=<redacted>/'",
        )
    finally:
        client.close()


def fix_lobe_registration() -> None:
    client = connect()
    try:
        run(
            client,
            "cd /root/lobehub-aliyun-deploy && "
            "cp .env .env.bak-registration-$(date +%Y%m%d-%H%M%S) && "
            "sed -i '/^AUTH_TRUSTED_ORIGINS=/d;/^AUTH_EMAIL_VERIFICATION=/d' .env && "
            "printf '\\nAUTH_TRUSTED_ORIGINS=https://lobe.hiijob.cn,http://118.190.96.172:3210\\n"
            "AUTH_EMAIL_VERIFICATION=0\\n' >> .env && "
            "docker-compose up -d lobe",
            check=True,
        )
        run(client, "sleep 8 && docker ps --filter name=lobehub --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}'")
        run(
            client,
            "docker inspect lobehub --format '{{range .Config.Env}}{{println .}}{{end}}' "
            "| awk -F= '$1==\"APP_URL\" || $1==\"AUTH_TRUSTED_ORIGINS\" || "
            "$1==\"AUTH_EMAIL_VERIFICATION\" {print}'",
            check=True,
        )
        run(
            client,
            "curl -sS -i -X POST http://127.0.0.1:3210/api/auth/sign-up/email "
            "-H 'Origin: http://118.190.96.172:3210' "
            "-H 'Content-Type: application/json' "
            "--data '{\"email\":\"invalid\",\"password\":\"123\"}' | head -20",
            check=True,
        )
        run(client, "docker logs lobehub --tail 80 2>&1 | grep -Ei 'invalid origin|better auth|error' || true")
    finally:
        client.close()


def verify_remote_hermes() -> None:
    client = connect()
    try:
        run(
            client,
            "docker ps -a --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}' "
            "| grep -E 'NAMES|lobehub|litellm|ollama'",
            check=True,
        )
        run(
            client,
            "docker exec lobe-ollama ollama show hermes3:8b >/dev/null && "
            "echo 'Ollama model: hermes3:8b is available'",
            check=True,
        )
        run(
            client,
            "cd /root/lobehub-aliyun-deploy && "
            "key=$(sed -n 's/^LITELLM_MASTER_KEY=//p' .env | tail -1) && "
            "test -n \"$key\" && "
            "docker exec lobe-litellm sh -lc "
            "\"curl -fsS http://127.0.0.1:4000/v1/models "
            "-H 'Authorization: Bearer $key'\" "
            "| grep -q '\"id\":\"hermes-3\"' && "
            "echo 'LiteLLM model: hermes-3 is exposed'",
            check=True,
        )
        run(
            client,
            "cd /root/lobehub-aliyun-deploy && "
            "key=$(sed -n 's/^LITELLM_MASTER_KEY=//p' .env | tail -1) && "
            "curl -fsS --max-time 600 http://127.0.0.1:4000/v1/chat/completions "
            "-H \"Authorization: Bearer $key\" "
            "-H 'Content-Type: application/json' "
            "--data '{\"model\":\"hermes-3\",\"messages\":[{\"role\":\"user\","
            "\"content\":\"Reply with exactly: HERMES_OK\"}],\"max_tokens\":32,"
            "\"temperature\":0}' "
            "| grep -o 'HERMES_OK' | head -1",
            check=True,
        )
        run(
            client,
            "docker inspect lobehub --format '{{range .Config.Env}}{{println .}}{{end}}' "
            "| awk -F= '$1==\"OPENAI_PROXY_URL\" || $1==\"OPENAI_MODEL_LIST\" "
            "{print}'",
            check=True,
        )
    finally:
        client.close()


def inspect_remote_hermes_capacity() -> None:
    client = connect()
    try:
        run(client, "nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader 2>&1 || true")
        run(client, "df -h / /var/lib/docker | tail -n +2")
        run(
            client,
            "cd /root/lobehub-aliyun-deploy && "
            "grep -nE '^  (litellm|ollama|ollama-pull-hermes):|OPENAI_PROXY_URL|"
            "OPENAI_MODEL_LIST|LITELLM_MASTER_KEY|hermes3' docker-compose.yml .env "
            "2>/dev/null || true",
        )
        run(client, "docker images --format 'table {{.Repository}}\\t{{.Tag}}\\t{{.Size}}' | grep -Ei 'REPOSITORY|ollama|litellm|hermes'")
    finally:
        client.close()


def inspect_remote_disk_usage() -> None:
    client = connect()
    try:
        run(client, "df -hT / /var/lib/docker")
        run(client, "timeout 15 docker system df || true")
        run(
            client,
            "timeout 20 du -sh /var/lib/docker /var/log /root/lobehub-aliyun-deploy "
            "/root/lobehub-build /root/talent-intelligence-service "
            "/root/az-referral-report-tool /opt/web 2>/dev/null || true",
        )
        run(
            client,
            "find /var/lib/docker/containers -name '*-json.log' -type f "
            "-printf '%s %p\\n' 2>/dev/null | sort -nr | head -20 "
            "| awk '{printf \"%.1f MB %s\\n\", $1/1048576, $2}'",
        )
        run(
            client,
            "docker ps -a --format 'table {{.Names}}\\t{{.Status}}\\t{{.Image}}'",
        )
        run(
            client,
            "docker images --format '{{.Size}}\\t{{.Repository}}:{{.Tag}}' "
            "| sort -hr | head -20",
        )
        run(
            client,
            "docker volume ls -q | while read v; do "
            "m=$(docker volume inspect -f '{{.Mountpoint}}' \"$v\"); "
            "s=$(timeout 5 du -sh \"$m\" 2>/dev/null | awk '{print $1}'); "
            "printf '%s\\t%s\\n' \"${s:-unknown}\" \"$v\"; done | sort -hr",
        )
    finally:
        client.close()


def inspect_remote_prune_candidates() -> None:
    client = connect()
    try:
        run(
            client,
            "docker images --filter dangling=true "
            "--format 'table {{.ID}}\\t{{.CreatedSince}}\\t{{.Size}}'",
        )
        run(
            client,
            "docker ps -a --filter status=exited "
            "--format 'table {{.Names}}\\t{{.Status}}\\t{{.Size}}\\t{{.Image}}'",
        )
        run(client, "journalctl --disk-usage 2>/dev/null || true")
        run(
            client,
            "du -h --max-depth=1 /var/log 2>/dev/null | sort -h | tail -15",
        )
    finally:
        client.close()


def smoke_export_standalone() -> None:
    client = connect()
    try:
        project_dir = detect_project_dir(client)
        run(
            client,
            "docker exec -i talent-mapping-llm-mcp python - <<'PY'\n"
            "from talent_mapping_mcp_server import export_talent_mapping_obsidian_vault\n"
            "result = export_talent_mapping_obsidian_vault(candidate_limit=5, mapping_limit=2)\n"
            "print(result)\n"
            "PY",
            check=True,
        )
        run(client, f"find {project_dir}/talent_mapping_llm_vault -maxdepth 2 -type f | head -30")
    finally:
        client.close()


def smoke_graph_standalone() -> None:
    client = connect()
    try:
        project_dir = detect_project_dir(client)
        run(
            client,
            "docker exec -i talent-mapping-llm-mcp python - <<'PY'\n"
            "from talent_mapping_mcp_server import export_talent_mapping_graph_view, get_talent_mapping_graph\n"
            "graph = get_talent_mapping_graph(max_nodes=80, max_edges=200)\n"
            "print(graph['stats'])\n"
            "result = export_talent_mapping_graph_view(refresh_vault=False, max_nodes=80, max_edges=200)\n"
            "print(result)\n"
            "PY",
            check=True,
        )
        run(client, f"ls -lh {project_dir}/talent_mapping_llm_vault/talent_mapping_graph.html 2>/dev/null || true")
    finally:
        client.close()


def deploy_graph_link() -> None:
    client = connect()
    try:
        project_dir = detect_project_dir(client)
        token_file = f"{project_dir}/.talent_mapping_graph_token"
        code, out, _ = run(client, f"cat {token_file} 2>/dev/null || true")
        token = out.strip()
        if not token:
            token = "tm-graph-" + secrets.token_urlsafe(18).replace("-", "").replace("_", "")
            run(client, f"printf '%s' '{token}' > {token_file} && chmod 600 {token_file}", check=True)

        run(client, f"test -f {project_dir}/talent_mapping_llm_vault/talent_mapping_graph.html || echo GRAPH_HTML_MISSING")
        run(client, "docker stop talent-mapping-graph-static 2>/dev/null || true")
        run(client, "docker rm talent-mapping-graph-static 2>/dev/null || true")
        run(
            client,
            "docker run -d --name talent-mapping-graph-static "
            "-p 8771:8771 "
            f"-v {project_dir}/talent_mapping_llm_vault:/srv/{token}:ro "
            "talent-mapping-llm-mcp:latest "
            "python -m http.server 8771 --bind 0.0.0.0 --directory /srv",
            check=True,
        )
        run(client, "sleep 3; docker ps --filter name=talent-mapping-graph-static --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}'")
        run(client, "docker logs talent-mapping-graph-static --tail 40 2>&1 || true")
        print(f"\nGRAPH_URL=http://118.190.96.172:8771/{token}/talent_mapping_graph.html")
    finally:
        client.close()


def deploy_graph_tunnel_service() -> None:
    client = connect()
    try:
        project_dir = detect_project_dir(client)
        run(client, f"test -f {project_dir}/talent_mapping_llm_vault/talent_mapping_graph.html || echo GRAPH_HTML_MISSING")
        run(client, "docker stop talent-mapping-graph-local 2>/dev/null || true")
        run(client, "docker rm talent-mapping-graph-local 2>/dev/null || true")
        run(
            client,
            "docker run -d --name talent-mapping-graph-local "
            "-p 127.0.0.1:8771:8771 "
            f"-v {project_dir}/talent_mapping_llm_vault:/srv:ro "
            "talent-mapping-llm-mcp:latest "
            "python -m http.server 8771 --bind 0.0.0.0 --directory /srv",
            check=True,
        )
        run(client, "sleep 3; docker ps --filter name=talent-mapping-graph-local --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}'")
        run(client, "curl -I --max-time 5 http://127.0.0.1:8771/talent_mapping_graph.html || true")
        print("\nLOCAL_TUNNEL_URL=http://localhost:8771/talent_mapping_graph.html")
    finally:
        client.close()


def list_tools_standalone() -> None:
    client = connect()
    try:
        run(
            client,
            "docker exec -i talent-mapping-llm-mcp python - <<'PY'\n"
            "import asyncio\n"
            "from mcp import ClientSession\n"
            "from mcp.client.streamable_http import streamablehttp_client\n"
            "async def main():\n"
            "    async with streamablehttp_client('http://127.0.0.1:8770/mcp') as (read, write, _):\n"
            "        async with ClientSession(read, write) as session:\n"
            "            await session.initialize()\n"
            "            tools = await session.list_tools()\n"
            "            for tool in tools.tools:\n"
            "                print(tool.name)\n"
            "asyncio.run(main())\n"
            "PY",
            check=True,
        )
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["inspect", "inspect-docker", "inspect-standalone", "inspect-lobe-auth", "inspect-lobe-compose", "inspect-lobe-files", "inspect-lobe-deploy-config", "fix-lobe-registration", "verify-remote-hermes", "inspect-remote-hermes-capacity", "inspect-remote-disk-usage", "inspect-remote-prune-candidates", "deploy", "deploy-standalone", "verify", "verify-standalone", "smoke-export-standalone", "smoke-graph-standalone", "deploy-graph-link", "deploy-graph-tunnel-service", "list-tools-standalone"])
    args = parser.parse_args()
    {
        "inspect": inspect,
        "inspect-docker": inspect_docker,
        "inspect-standalone": inspect_standalone,
        "inspect-lobe-auth": inspect_lobe_auth,
        "inspect-lobe-compose": inspect_lobe_compose,
        "inspect-lobe-files": inspect_lobe_files,
        "inspect-lobe-deploy-config": inspect_lobe_deploy_config,
        "fix-lobe-registration": fix_lobe_registration,
        "verify-remote-hermes": verify_remote_hermes,
        "inspect-remote-hermes-capacity": inspect_remote_hermes_capacity,
        "inspect-remote-disk-usage": inspect_remote_disk_usage,
        "inspect-remote-prune-candidates": inspect_remote_prune_candidates,
        "deploy": deploy,
        "deploy-standalone": deploy_standalone,
        "verify": verify,
        "verify-standalone": verify_standalone,
        "smoke-export-standalone": smoke_export_standalone,
        "smoke-graph-standalone": smoke_graph_standalone,
        "deploy-graph-link": deploy_graph_link,
        "deploy-graph-tunnel-service": deploy_graph_tunnel_service,
        "list-tools-standalone": list_tools_standalone,
    }[args.action]()


if __name__ == "__main__":
    main()
