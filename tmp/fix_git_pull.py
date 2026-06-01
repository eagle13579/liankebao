#!/usr/bin/env python3
"""Fix git pull on remote server."""
import paramiko
import sys

HOST = "47.116.116.87"
USER = "root"
PASSWORD = "DYY545782kkz"
DEPLOY_DIR = "/var/www/liankebao"

print("=" * 60)
print(f"SSH to {USER}@{HOST} - fix git pull...")
print("=" * 60)

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    client.connect(HOST, username=USER, password=PASSWORD, timeout=15)
    print("✅ SSH connected")
except Exception as e:
    print(f"❌ SSH connection failed: {e}")
    sys.exit(1)

# Fix git divergent branches - use merge strategy
commands = [
    f"cd {DEPLOY_DIR} && git config pull.rebase false",
    f"cd {DEPLOY_DIR} && git pull origin master 2>&1",
    f"cd {DEPLOY_DIR} && git log --oneline -3",
]

for cmd in commands:
    print(f"\n> {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
    exit_code = stdout.channel.recv_exit_status()
    output = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    if output:
        for line in output.strip().split("\n"):
            print(f"  {line}")
    if err:
        for line in err.strip().split("\n"):
            print(f"  [ERR] {line}")
    print(f"  → exit: {exit_code}")

client.close()
print("\n✅ Git pull fix complete")
