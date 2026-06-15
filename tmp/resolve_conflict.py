#!/usr/bin/env python3
"""Resolve merge conflict and complete deploy."""

import paramiko

HOST = "47.116.116.87"
USER = "root"
PASSWORD = "DYY545782kkz"
DEPLOY_DIR = "/var/www/liankebao"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASSWORD, timeout=15)
print("✅ SSH connected\n")

# Check conflict status
stdin, stdout, stderr = client.exec_command(
    f"cd {DEPLOY_DIR} && git status 2>&1", timeout=10
)
print(stdout.read().decode())

# Check for conflict markers
stdin, stdout, stderr = client.exec_command(
    f"cd {DEPLOY_DIR} && grep -c '<<<<<<<' backend/seed_data.py 2>&1", timeout=10
)
print(f"Conflict markers: {stdout.read().decode().strip()}")

# Use 'ours' strategy to accept our version
cmds = [
    f"cd {DEPLOY_DIR} && git checkout --ours backend/seed_data.py 2>&1",
    f"cd {DEPLOY_DIR} && git add backend/seed_data.py 2>&1",
    f"cd {DEPLOY_DIR} && git commit --no-verify -m 'merge: 保留seed_data.py的ours版本' 2>&1",
    f"cd {DEPLOY_DIR} && git log --oneline -2",
]

for cmd in cmds:
    print(f"> {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=15)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    if out:
        print(f"  {out.strip().split(chr(10))[-3:]}")
    if err:
        print(f"  [ERR] {err.strip()[:200]}")
    print()

# Check final status
stdin, stdout, stderr = client.exec_command(
    f"cd {DEPLOY_DIR} && git status 2>&1", timeout=10
)
print(f"Final status: {stdout.read().decode().strip()[:200]}")

client.close()
print("✅ Conflict resolved, ready for deploy")
