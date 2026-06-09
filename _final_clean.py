#!/usr/bin/env python3
import shutil
import os

for p in ["D:/链客宝AI/backend/.ruff_cache", "D:/链客宝AI/payment_sdk/.ruff_cache"]:
    if os.path.isdir(p):
        shutil.rmtree(p)
        print(f"Removed: {p}")
os.remove("D:/链客宝AI/_finalize.py")
print("Done.")
