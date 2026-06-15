#!/usr/bin/env python3
"""验证链客宝KFD化产出"""
import os

HERMES = r'D:\向海容的知识库\wiki\wiki\记忆宫殿'

print("=== Feature库 链客宝 ===")
feature_base = os.path.join(HERMES, 'L5孵化室', '五池', 'Feature库')
total_features = 0
for dim in ['审美', '体系', '创造力', '基本功', '数据', '场景']:
    d = os.path.join(feature_base, dim)
    if os.path.exists(d):
        files = [f for f in os.listdir(d) if '链客宝' in f]
        print(f'  [{dim}] {len(files)}个')
        for f in files:
            print(f'    {f}')
        total_features += len(files)
    else:
        print(f'  [{dim}] 目录不存在')
print(f'  总计: {total_features}个Feature')

print('\n=== DataPack库 链客宝 ===')
dp_dir = os.path.join(HERMES, 'L5孵化室', '五池', 'DataPack库', '产品包', '链客宝')
if os.path.exists(dp_dir):
    files = sorted(os.listdir(dp_dir))
    print(f'  总计: {len(files)}个DataPack')
    for f in files:
        sz = os.path.getsize(os.path.join(dp_dir, f))
        print(f'    {f} ({sz:,}B)')
else:
    print('  目录不存在')

print('\n=== KFD装配文档 ===')
kfd_path = r'D:\chainke-full\KFD装配文档.md'
if os.path.exists(kfd_path):
    sz = os.path.getsize(kfd_path)
    print(f'  存在: {sz:,}B')
else:
    print('  不存在')

print('\n=== 状态总览 ===')
st_path = os.path.join(HERMES, 'L0前厅', '状态总览.md')
if os.path.exists(st_path):
    with open(st_path, 'r', encoding='utf-8') as f:
        content = f.read()
    if '链客宝KFD标定' in content:
        print('  已更新 ✅')
    else:
        print('  未更新 ❌')
print('\n=== 全部验证完成 ===')
