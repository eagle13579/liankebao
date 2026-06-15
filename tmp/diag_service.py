#!/usr/bin/env python3
"""Diagnose and fix service failure."""
import paramiko

HOST = "47.116.116.87"
USER = "root"
PASSWORD = "DYY545782kkz"
DEPLOY_DIR = "/var/www/liankebao"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASSWORD, timeout=15)
print("✅ SSH connected\n")

# Check logs first
cmds = [
    f"journalctl -u chainke-backend --no-pager -n 40 2>&1",
    f"cd {DEPLOY_DIR}/backend && cat service_8001.log 2>/dev/null | tail -30",
    f"ls -la {DEPLOY_DIR}/backend/.venv/bin/python*",
]

for cmd in cmds:
    print(f"> {cmd[:80]}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=15)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    if out:
        for line in out.strip().split("\n")[-30:]:
            print(f"  {line}")
    if err:
        for line in err.strip().split("\n")[-5:]:
            print(f"  [ERR] {line}")
    print()

client.close()
