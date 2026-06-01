#!/usr/bin/env python3
"""Reset and deploy cleanly."""

import paramiko

HOST = "47.116.116.87"
USER = "root"
PASSWORD = "DYY545782kkz"
DEPLOY_DIR = "/var/www/liankebao"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASSWORD, timeout=15)
print("✅ SSH connected\n")

cmds = [
    f"cd {DEPLOY_DIR} && git reset --hard origin/master 2>&1",
    f"cd {DEPLOY_DIR} && git clean -fd 2>&1",
    f"cd {DEPLOY_DIR} && git pull origin master 2>&1",
    f"cd {DEPLOY_DIR} && git log --oneline -3",
    f"cd {DEPLOY_DIR}/backend && .venv/bin/pip install --break-system-packages -r requirements.txt 2>&1 | tail -5",
    "systemctl restart chainke-backend 2>&1",
    "sleep 8",
    "curl -s http://127.0.0.1:8001/api/products 2>&1 | head -c 300",
    "curl -s http://127.0.0.1:8001/health 2>&1 | head -c 300",
]

for cmd in cmds:
    print(f"> {cmd[:80]}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    if out:
        for line in out.strip().split("\n")[-5:]:
            print(f"  {line}")
    if err:
        for line in err.strip().split("\n")[-3:]:
            print(f"  [E] {line}")
    print(f"  → exit={exit_code}\n")

client.close()
print("=" * 50)
print("🎉 Done!")
