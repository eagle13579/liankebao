#!/usr/bin/env python3
"""Full deploy: pull, install, restart, verify."""

import paramiko

HOST = "47.116.116.87"
USER = "root"
PASSWORD = "DYY545782kkz"
DEPLOY_DIR = "/var/www/liankebao"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASSWORD, timeout=15)
print("✅ SSH connected\n")

steps = [
    (
        f"cd {DEPLOY_DIR} && git config pull.rebase false && git pull origin master 2>&1",
        60,
        "Git pull",
    ),
    (
        f"cd {DEPLOY_DIR}/backend && .venv/bin/pip install --break-system-packages -r requirements.txt 2>&1 | tail -10",
        120,
        "pip install",
    ),
    (
        f"cd {DEPLOY_DIR}/backend && .venv/bin/pip install --break-system-packages -e . 2>&1 | tail -10",
        120,
        "pip install -e .",
    ),
    ("systemctl restart chainke-backend 2>&1", 15, "Restart service"),
    (
        "sleep 6 && curl -s http://127.0.0.1:8001/api/products 2>&1 | head -c 300",
        15,
        "Verify /api/products",
    ),
    ("curl -s http://127.0.0.1:8001/health 2>&1 | head -c 300", 10, "Verify /health"),
]

for cmd, timeout, label in steps:
    print(f"--- {label} ---")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    output = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    if output:
        for line in output.strip().split("\n")[-10:]:
            print(f"  {line}")
    if err:
        for line in err.strip().split("\n")[-5:]:
            print(f"  [ERR] {line}")
    status = "✅" if exit_code == 0 else "❌"
    print(f"  {status} exit={exit_code}\n")

client.close()
print("=" * 60)
print("🎉 Deployment complete!")
print("=" * 60)
