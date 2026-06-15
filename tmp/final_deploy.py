#!/usr/bin/env python3
"""Final deploy: pip install, restart, verify."""
import paramiko
import sys
import time

HOST = "47.116.116.87"
USER = "root"
PASSWORD = "DYY545782kkz"
DEPLOY_DIR = "/var/www/liankebao"

print("=" * 60)
print("🚀 Final deployment steps")
print("=" * 60)

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASSWORD, timeout=15)
print("✅ SSH connected")

commands = [
    (f"cd {DEPLOY_DIR} && pip install --break-system-packages -r requirements.txt 2>&1 | tail -15", 120),
    ("systemctl restart chainke-backend 2>&1", 30),
    ("sleep 5 && curl -s http://127.0.0.1:8001/api/products 2>&1 | head -c 300", 15),
    ("curl -s http://127.0.0.1:8001/health 2>&1", 10),
    ("curl -s http://127.0.0.1:8001/docs 2>&1 | head -c 200", 10),
]

for cmd, timeout in commands:
    print(f"\n> {cmd[:80]}")
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
    status = "✅" if exit_code == 0 else "⚠️"
    print(f"  {status} exit: {exit_code}")

client.close()
print("\n" + "=" * 60)
print("🎉 Deployment complete!")
print("=" * 60)
