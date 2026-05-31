#!/usr/bin/env python3
import shutil
import os

for p in ["D:/链客宝/backend/.ruff_cache", "D:/链客宝/payment_sdk/.ruff_cache"]:
    if os.path.isdir(p):
        shutil.rmtree(p)
        print(f"Removed: {p}")
os.remove("D:/链客宝/_finalize.py")
print("Done.")
