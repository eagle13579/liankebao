#!/usr/bin/env python3
"""SSH to production server and deploy latest code using paramiko."""
import paramiko
import sys
import time

HOST = "47.116.116.87"
USER = "root"
PASSWORD = "DYY545782kkz"
DEPLOY_DIR = "/var/www/liankebao"

print("=" * 60)
print(f"SSH to {USER}@{HOST} for deployment...")
print("=" * 60)

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    client.connect(HOST, username=USER, password=PASSWORD, timeout=15)
    print("✅ SSH connected")
except Exception as e:
    print(f"❌ SSH connection failed: {e}")
    sys.exit(1)

commands = [
    f"cd {DEPLOY_DIR} && pwd",
    f"cd {DEPLOY_DIR} && git pull origin master 2>&1",
    f"cd {DEPLOY_DIR} && pip install -r requirements.txt 2>&1 | tail -10",
    "systemctl restart chainke-backend 2>&1",
    "sleep 5 && echo '--- Sleep done ---'",
    "curl -s http://127.0.0.1:8001/api/products 2>&1 | head -c 500",
]

for i, cmd in enumerate(commands, 1):
    print(f"\n--- Step {i}: {cmd[:80]}...")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
    exit_code = stdout.channel.recv_exit_status()
    output = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    if output:
        for line in output.strip().split("\n")[-15:]:
            print(f"  {line}")
    if err:
        for line in err.strip().split("\n")[-5:]:
            print(f"  [ERR] {line}")
    if exit_code == 0:
        print(f"  ✅ OK (exit code: {exit_code})")
    else:
        print(f"  ⚠️  Exit code: {exit_code}")

client.close()
print("\n" + "=" * 60)
print("🎉 Deployment complete!")
print("=" * 60)
