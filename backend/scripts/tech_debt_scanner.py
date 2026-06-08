#!/usr/bin/env python3
"""链客宝技术债扫描工具 — 代码健康度自动化审计"""
import os, re, json, ast, sys
from collections import defaultdict
from datetime import datetime

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

def scan_python_files(root_dir):
    py_files = []
    for root, dirs, files in os.walk(root_dir):
        if any(skip in root for skip in ['__pycache__', 'venv', 'node_modules', '.git', 'migrations']):
            continue
        for f in files:
            if f.endswith('.py'):
                py_files.append(os.path.join(root, f))
    return py_files

def count_lines(files):
    stats = {'total_files': len(files), 'total_lines': 0, 'total_code': 0, 'total_empty': 0, 'total_comment': 0}
    dir_stats = defaultdict(lambda: {'files': 0, 'lines': 0})
    large_files = []
    for fp in files:
        with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        lines = content.split('\n')
        code_lines = sum(1 for l in lines if l.strip() and not l.strip().startswith('#'))
        empty = sum(1 for l in lines if not l.strip())
        comments = sum(1 for l in lines if l.strip().startswith('#'))
        stats['total_lines'] += len(lines)
        stats['total_code'] += code_lines
        stats['total_empty'] += empty
        stats['total_comment'] += comments
        dname = os.path.relpath(os.path.dirname(fp), BACKEND)
        dir_stats[dname]['files'] += 1
        dir_stats[dname]['lines'] += len(lines)
        if len(lines) > 1000:
            large_files.append((os.path.basename(fp), len(lines), fp))
    return stats, dict(dir_stats), large_files

def find_long_functions(files):
    long_funcs = []
    for fp in files:
        with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
            try:
                tree = ast.parse(f.read())
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        line_count = node.end_lineno - node.lineno
                        if line_count > 100:
                            long_funcs.append({
                                'file': os.path.basename(fp),
                                'function': node.name,
                                'lines': line_count,
                                'start_line': node.lineno
                            })
            except:
                pass
    return long_funcs

def find_todos(files):
    todos = []
    for fp in files:
        with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
            for i, line in enumerate(f, 1):
                if re.search(r'\b(TODO|FIXME|HACK|XXX)\b', line):
                    todos.append({'file': os.path.basename(fp), 'line': i, 'text': line.strip(), 'type': re.search(r'(TODO|FIXME|HACK|XXX)', line).group(1)})
    return todos

def security_scan(files):
    findings = []
    patterns = {
        'hardcoded_key': [r'(?:api_key|apikey|secret|password|token)\s*[=:]\s*["\'][A-Za-z0-9_\-]{16,}'],
        'unsafe_func': [r'\b(eval|exec|pickle\.loads|marshal\.loads)\('],
        'sql_injection': [r'execute\s*\(\s*f["\']'],
    }
    for fp in files:
        with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        for category, pats in patterns.items():
            for pat in pats:
                for m in re.finditer(pat, content, re.IGNORECASE):
                    line_num = content[:m.start()].count('\n') + 1
                    findings.append({'file': os.path.basename(fp), 'line': line_num, 'type': category, 'match': m.group()[:60]})
    return findings

def check_import_cycles(files):
    imports = {}
    for fp in files:
        with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
            try:
                tree = ast.parse(f.read())
                name = os.path.splitext(os.path.basename(fp))[0]
                deps = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            deps.append(alias.name.split('.')[0])
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            deps.append(node.module.split('.')[0])
                imports[name] = deps
            except:
                pass
    cycles = []
    visited = set()
    path_stack = []
    def dfs(node, path):
        if node in path_stack:
            cycle = path_stack[path_stack.index(node):] + [node]
            cycles.append(' -> '.join(cycle))
            return
        if node in visited:
            return
        visited.add(node)
        path_stack.append(node)
        for dep in imports.get(node, []):
            if dep in imports:
                dfs(dep, path + [dep])
        path_stack.pop()
    for n in imports:
        dfs(n, [n])
    return cycles

def run_scan(output_dir=None):
    files = scan_python_files(BACKEND)
    stats, dir_stats, large_files = count_lines(files)
    long_funcs = find_long_functions(files)
    todos = find_todos(files)
    sec_findings = security_scan(files)
    cycles = check_import_cycles(files)

    # Health score
    score = 100
    score -= len(large_files) * 5
    score -= len(long_funcs) * 3
    score -= len(todos)
    score -= len(sec_findings) * 10
    score -= len(cycles) * 8
    score = max(0, min(100, score))

    report = {
        'scan_time': datetime.now().isoformat(),
        'project': '链客宝',
        'backend_dir': BACKEND,
        'code_stats': stats,
        'dir_stats': dir_stats,
        'large_files': [{'name': n, 'lines': l, 'path': p} for n, l, p in large_files],
        'long_functions': long_funcs,
        'todos': todos,
        'security_findings': sec_findings,
        'import_cycles': cycles,
        'health_score': score
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report

if __name__ == '__main__':
    output_dir = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == '--output' else None
    run_scan(output_dir)
