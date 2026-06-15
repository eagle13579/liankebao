#!/usr/bin/env python3
"""Check server structure."""
import paramiko

HOST = "47.116.116.87"
USER = "root"
PASSWORD = "DYY545782kkz"
DEPLOY_DIR = "/var/www/liankebao"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASSWORD, timeout=15)

commands = [
    f"ls -la {DEPLOY_DIR}/",
    f"find {DEPLOY_DIR} -name 'requirements.txt' -o -name 'pyproject.toml' 2>/dev/null",
    f"cd {DEPLOY_DIR} && ls backend/",
    f"cd {DEPLOY_DIR} && cat backend/requirements.txt 2>/dev/null || echo 'No backend/requirements.txt'",
    "systemctl status chainke-backend 2>&1 | head -20",
]

for cmd in commands:
    print(f"\n> {cmd[:100]}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=15)
    exit_code = stdout.channel.recv_exit_status()
    output = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    if output:
        for line in output.strip().split("\n")[-20:]:
            print(f"  {line}")
    if err:
        for line in err.strip().split("\n")[-5:]:
            print(f"  [ERR] {line}")

client.close()
