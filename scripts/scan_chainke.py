#!/usr/bin/env python3
"""链客宝项目结构扫描 — Phase 1 KFD分析"""
import os, json

CHAINKE = r'D:\chainke-full'
results = {}

# 顶层结构
top = [d for d in os.listdir(CHAINKE) if os.path.isdir(os.path.join(CHAINKE, d)) and not d.startswith('_') and d not in ('node_modules', 'venv', '__pycache__')]
results['顶层目录'] = sorted(top)

# 后端app模块
backend_app = os.path.join(CHAINKE, 'backend', 'app')
results['后端app模块'] = sorted([d for d in os.listdir(backend_app) if os.path.isdir(os.path.join(backend_app, d))]) if os.path.exists(backend_app) else []

# 后端modules
backend_mods = os.path.join(CHAINKE, 'backend', 'modules')
results['后端modules'] = sorted([d for d in os.listdir(backend_mods) if os.path.isdir(os.path.join(backend_mods, d))]) if os.path.exists(backend_mods) else []

# 前端pages
src_pages = os.path.join(CHAINKE, 'src', 'pages')
results['前端pages'] = sorted([d for d in os.listdir(src_pages) if os.path.isdir(os.path.join(src_pages, d))]) if os.path.exists(src_pages) else []

# 前端screens
src_screens = os.path.join(CHAINKE, 'src', 'screens')
results['前端screens'] = sorted([d for d in os.listdir(src_screens) if os.path.isdir(os.path.join(src_screens, d))]) if os.path.exists(src_screens) else []

# 前端components
src_comp = os.path.join(CHAINKE, 'src', 'components')
results['前端components'] = sorted([d for d in os.listdir(src_comp) if os.path.isdir(os.path.join(src_comp, d))])[:25] if os.path.exists(src_comp) else []

# 后端数据安全
data_sec = os.path.join(CHAINKE, 'backend', 'data_security')
results['data_security'] = sorted(os.listdir(data_sec))[:20] if os.path.exists(data_sec) else []

# 代码统计
total_py_files = 0
total_py_lines = 0
for root, dirs, files in os.walk(CHAINKE):
    if 'node_modules' in root or 'venv' in root or '__pycache__' in root:
        continue
    for f in files:
        if f.endswith('.py'):
            total_py_files += 1
            fp = os.path.join(root, f)
            try:
                total_py_lines += sum(1 for _ in open(fp, 'rb'))
            except:
                pass
results['代码统计'] = {'py文件数': total_py_files, 'py总行数': total_py_lines}

# 主要Python文件规模
major_files = []
for root, dirs, files in os.walk(os.path.join(CHAINKE, 'backend', 'app')):
    if '__pycache__' in root:
        continue
    for f in files:
        if f.endswith('.py'):
            fp = os.path.join(root, f)
            sz = os.path.getsize(fp)
            if sz > 10000:
                major_files.append((f, sz))
major_files.sort(key=lambda x: -x[1])
results['大型py文件'] = [(f, f'{s:,}B') for f, s in major_files[:20]]

# Config
config_dir = os.path.join(CHAINKE, 'backend', 'config')
config_files = sorted(os.listdir(config_dir)) if os.path.exists(config_dir) else []
results['config'] = config_files[:15]

print(json.dumps(results, ensure_ascii=False, indent=2))
