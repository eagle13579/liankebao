#!/usr/bin/env python3
"""Verify data pipeline and test files exist"""
import os

def check(path, label):
    exists = os.path.exists(path)
    size = os.path.getsize(path) if exists else 0
    print(f"  {label}: {'✅' if exists else '❌'} ({size:,}B)" if exists else f"  {label}: ❌")
    return exists

print("=== 数据管道模块 ===")
dp = r'D:\chainke-full\backend\features\data_pipeline'
check(os.path.join(dp, '__init__.py'), '__init__.py')
check(os.path.join(dp, 'config.py'), 'config.py')
check(os.path.join(dp, 'collector.py'), 'collector.py')
check(os.path.join(dp, 'analyzer.py'), 'analyzer.py')
check(os.path.join(dp, 'pipeline.py'), 'pipeline.py')

print("\n=== 技术债扫描 ===")
check(r'D:\chainke-full\backend\scripts\tech_debt_scanner.py', 'tech_debt_scanner.py')
check(r'D:\chainke-full\backend\tech_debt_config.yaml', 'tech_debt_config.yaml')

print("\n=== 测试文件 ===")
tests = r'D:\chainke-full\backend\tests'
count = 0
for f in sorted(os.listdir(tests)):
    if f.endswith('.py'):
        fp = os.path.join(tests, f)
        count += 1
        if count <= 70:
            check(fp, f)
print(f"\n总测试文件数: {count}")
