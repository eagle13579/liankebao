#!/usr/bin/env python3
"""
链客宝 — 技术债扫描与代码健康度自动化工具
=============================================
扫描 Python 代码库，分析技术债务、代码复杂度、安全风险等指标，
输出 JSON / Markdown / HTML 多格式报告。

用法:
    python scripts/tech_debt_scanner.py [--config CONFIG_PATH] [--output-dir DIR]
    python scripts/tech_debt_scanner.py --ci          # CI 模式，失败时非零退出

依赖:
    - Python 3.10+
    - radon (pip install radon)  # 可选，用于圈复杂度分析
    - pyyaml (pip install pyyaml) # 可选，用于 YAML 配置

路径说明:
    本脚本设计在 BACKEND 根目录运行（即 D:\\chainke-full\\backend）。
    所有扫描路径相对于 BACKEND 根目录，不包含 "backend/" 前缀。
"""

from __future__ import annotations

import ast
import json
import os
import re
import sys
import time
from collections import defaultdict, Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


# ==============================================================================
# 类型定义 & 数据结构
# ==============================================================================


@dataclass
class FileMetrics:
    """单个文件的扫描指标"""
    path: str
    line_count: int
    code_line_count: int
    comment_line_count: int
    blank_line_count: int
    function_count: int
    class_count: int
    avg_function_length: float = 0.0
    max_function_length: int = 0
    long_functions: List[Dict[str, Any]] = field(default_factory=list)
    complexity: float = 0.0     # 圈复杂度 (平均)
    max_complexity: float = 0.0
    high_complexity_functions: List[Dict[str, Any]] = field(default_factory=list)
    todo_count: int = 0
    fixme_count: int = 0
    hack_count: int = 0
    imports: List[str] = field(default_factory=list)
    security_issues: List[Dict[str, Any]] = field(default_factory=list)
    unsafe_functions: List[Dict[str, Any]] = field(default_factory=list)
    sql_injection_risks: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ScanReport:
    """完整的扫描报告"""
    project_name: str = "链客宝"
    scan_time: str = ""
    scan_duration_seconds: float = 0.0

    # 代码统计
    total_files: int = 0
    total_lines: int = 0
    total_code_lines: int = 0
    total_comment_lines: int = 0
    total_blank_lines: int = 0
    avg_lines_per_file: float = 0.0
    avg_code_lines_per_file: float = 0.0

    # 分布
    dir_distribution: Dict[str, int] = field(default_factory=dict)
    file_type_distribution: Dict[str, int] = field(default_factory=dict)

    # 超大文件 / 超长函数
    large_files: List[Dict[str, Any]] = field(default_factory=list)
    total_long_functions: int = 0

    # 标记
    total_todo: int = 0
    total_fixme: int = 0
    total_hack: int = 0
    marker_files: List[Dict[str, Any]] = field(default_factory=list)

    # 复杂度
    high_risk_files: List[Dict[str, Any]] = field(default_factory=list)
    complexity_ranking: List[Dict[str, Any]] = field(default_factory=list)
    average_complexity: float = 0.0
    max_complexity_overall: float = 0.0

    # 依赖
    dependency_graph: Dict[str, List[str]] = field(default_factory=dict)
    circular_dependencies: List[List[str]] = field(default_factory=list)
    unused_imports: Dict[str, List[str]] = field(default_factory=dict)

    # 安全
    total_security_issues: int = 0
    total_unsafe_functions: int = 0
    total_sql_injection_risks: int = 0
    security_issue_files: List[Dict[str, Any]] = field(default_factory=list)

    # 汇总
    thresholds_breached: List[str] = field(default_factory=list)
    overall_health_score: float = 100.0
    summary: str = ""

    # 原始指标（每文件）
    file_metrics: Dict[str, FileMetrics] = field(default_factory=dict)

    config: Dict[str, Any] = field(default_factory=dict)


# ==============================================================================
# 配置加载
# ==============================================================================

DEFAULT_CONFIG = {
    # 注意：这些路径相对于 BACKEND 根目录 (D:\\chainke-full\\backend)
    # 不再包含 "backend/" 前缀，修复路径 Bug
    "scan_paths": ["app", "features", "tests", "scripts"],
    "exclude_patterns": [
        "**/__pycache__/**",
        "**/*.pyc",
        "**/.git/**",
        "**/venv/**",
        "**/.venv/**",
        "**/node_modules/**",
        "**/migrations/**",
        "**/.pytest_cache/**",
        "**/.benchmarks/**",
        "**/.eggs/**",
        "**/*.egg-info/**",
    ],
    "extensions": [".py"],
    "thresholds": {
        "cyclomatic_complexity": 10,
        "file_line_count": 1000,
        "function_line_count": 100,
        "todo_tolerance": 10,
        "max_high_risk_files": 5,
    },
    "security": {
        "secret_patterns": [
            r"password\s*[=:]\s*['\"][^'\"]+['\"]",
            r"api_key\s*[=:]\s*['\"][^'\"]+['\"]",
            r"secret\s*[=:]\s*['\"][^'\"]+['\"]",
            r"token\s*[=:]\s*['\"][^'\"]+['\"]",
            r"SK-[a-zA-Z0-9]{20,}",
            r"AKIA[0-9A-Z]{16}",
        ],
        "unsafe_functions": [
            "eval(", "exec(", "pickle.loads(", "pickle.load(",
            "marshal.load(", "marshal.loads(", "__import__(", "compile(",
        ],
        "sql_injection_patterns": [
            r"f['\"]?.*SELECT.*FROM.*WHERE.*\{",
            r"f['\"]?.*INSERT INTO.*\{",
            r"f['\"]?.*DELETE FROM.*\{",
            r"f['\"]?.*UPDATE.*SET.*\{",
            r"%s.*SELECT",
            r"\+.*SELECT.*FROM",
            r"execute\(.*f['\"]",
            r"execute\(.*\+",
        ],
    },
    "report": {
        "output_dir": "reports/tech_debt",
        "formats": ["json", "markdown", "html"],
        "fail_on_high_risk": True,
    },
    "dependencies": {
        "project_root": ".",
        "known_third_party": [
            "fastapi", "uvicorn", "pydantic", "openai",
            "python_multipart", "python_docx", "openpyxl",
            "PyPDF2", "httpx", "pytest", "dotenv",
        ],
    },
}


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """加载 YAML 配置，提供默认值兜底"""
    config = DEFAULT_CONFIG.copy()

    if config_path and Path(config_path).exists():
        try:
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                user_config = yaml.safe_load(f) or {}
            _deep_merge(config, user_config)
        except ImportError:
            print("[WARN] PyYAML 未安装，使用默认配置。pip install pyyaml 可安装。")
        except Exception as e:
            print(f"[WARN] 配置加载失败: {e}，使用默认配置。")

    return config


def _deep_merge(base: Dict, override: Dict, path: Optional[List[str]] = None) -> None:
    """深度合并两个字典"""
    if path is None:
        path = []
    for key in override:
        if key in base and isinstance(base[key], dict) and isinstance(override[key], dict):
            _deep_merge(base[key], override[key], path + [str(key)])
        else:
            base[key] = override[key]


# ==============================================================================
# 文件发现
# ==============================================================================


def find_python_files(
    scan_paths: List[str],
    exclude_patterns: List[str],
    extensions: List[str],
    project_root: Path,
) -> List[Path]:
    """递归发现所有符合扩展名的文件"""
    import fnmatch

    files: List[Path] = []
    seen: Set[Path] = set()

    for sp in scan_paths:
        base_path = project_root / sp
        if not base_path.exists():
            print(f"  [SKIP] 扫描路径不存在: {base_path}")
            continue
        if base_path.is_file():
            if base_path.suffix in extensions and base_path not in seen:
                files.append(base_path)
                seen.add(base_path)
            continue
        for root, dirs, filenames in os.walk(base_path):
            # 排除模式过滤 (目录级)
            rel_root = Path(root).relative_to(project_root)
            dirs[:] = [
                d for d in dirs
                if not any(fnmatch.fnmatch(str(rel_root / d), pat) for pat in exclude_patterns)
            ]
            for fn in filenames:
                fpath = Path(root) / fn
                if fpath.suffix in extensions and fpath not in seen:
                    rel_path = str(fpath.relative_to(project_root))
                    if any(fnmatch.fnmatch(rel_path, pat) for pat in exclude_patterns):
                        continue
                    files.append(fpath)
                    seen.add(fpath)

    return sorted(files)


# ==============================================================================
# 代码统计 (stdlib AST + tokenize)
# ==============================================================================


def count_lines(content: str) -> Tuple[int, int, int, int]:
    """统计行数: 总行, 代码行, 注释行, 空行"""
    lines = content.splitlines()
    total = len(lines)
    code = 0
    comments = 0
    blanks = 0

    in_multiline_comment = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            blanks += 1
            continue
        if in_multiline_comment:
            comments += 1
            if '"""' in stripped or "'''" in stripped:
                in_multiline_comment = False
            continue
        if stripped.startswith('#'):
            comments += 1
            continue
        if stripped.startswith('"""') or stripped.startswith("'''"):
            comments += 1
            if stripped.count('"""') == 1 and stripped.count("'''") == 1:
                in_multiline_comment = True
            continue
        code += 1

    return total, code, comments, blanks


def analyze_function_lengths(tree: ast.AST) -> Tuple[int, int, int, List[Dict[str, Any]]]:
    """分析函数长度: 函数数, 平均长度, 最大长度, 超长函数列表"""
    functions = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_name = node.name
            start_line = node.lineno
            end_line = getattr(node, 'end_lineno', start_line)
            if hasattr(node, 'body') and node.body:
                body_start = node.body[0].lineno
                body_end = getattr(node.body[-1], 'end_lineno', node.body[-1].lineno)
                func_length = body_end - body_start + 1
            else:
                func_length = end_line - start_line + 1
            functions.append({
                "name": func_name,
                "line": start_line,
                "length": func_length,
                "type": "async" if isinstance(node, ast.AsyncFunctionDef) else "def",
            })

    if not functions:
        return 0, 0.0, 0, []

    total_funcs = len(functions)
    total_length = sum(f["length"] for f in functions)
    avg_length = total_length / total_funcs
    max_length = max(f["length"] for f in functions)

    return total_funcs, avg_length, max_length, functions


def count_classes(tree: ast.AST) -> int:
    """统计类数"""
    return sum(1 for node in ast.walk(tree) if isinstance(node, ast.ClassDef))


def count_markers(content: str) -> Tuple[int, int, int]:
    """统计 TODO / FIXME / HACK 标记数"""
    todo = len(re.findall(r'(?i)#\s*TODO\b', content))
    fixme = len(re.findall(r'(?i)#\s*FIXME\b', content))
    hack = len(re.findall(r'(?i)#\s*HACK\b', content))
    return todo, fixme, hack


def extract_imports(tree: ast.AST) -> List[str]:
    """提取所有 import"""
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module.split(".")[0])
    return imports


def scan_file_metrics(filepath: Path, project_root: Path, config: Dict) -> Optional[FileMetrics]:
    """扫描单个文件的完整指标"""
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        print(f"  [SKIP] 无法读取 {filepath}: {e}")
        return None

    rel_path = str(filepath.relative_to(project_root))
    total, code, comments, blanks = count_lines(content)

    # AST 解析
    long_functions_list = []
    function_count = 0
    class_count = 0
    avg_func_len = 0.0
    max_func_len = 0
    imports = []

    try:
        tree = ast.parse(content, filename=str(filepath))
        function_count, avg_func_len, max_func_len, functions = analyze_function_lengths(tree)
        class_count = count_classes(tree)
        imports = extract_imports(tree)

        func_threshold = config["thresholds"]["function_line_count"]
        for f in functions:
            if f["length"] > func_threshold:
                long_functions_list.append(f)

    except SyntaxError as e:
        print(f"  [WARN] 语法错误 {rel_path}: {e}")

    todo, fixme, hack = count_markers(content)

    return FileMetrics(
        path=rel_path,
        line_count=total,
        code_line_count=code,
        comment_line_count=comments,
        blank_line_count=blanks,
        function_count=function_count,
        class_count=class_count,
        avg_function_length=avg_func_len,
        max_function_length=max_func_len,
        long_functions=long_functions_list,
        todo_count=todo,
        fixme_count=fixme,
        hack_count=hack,
        imports=imports,
    )


# ==============================================================================
# 复杂度分析 (radon)
# ==============================================================================


def analyze_complexity_with_radon(
    filepath: Path, project_root: Path, config: Dict
) -> Tuple[float, float, List[Dict[str, Any]]]:
    """使用 radon 计算圈复杂度"""
    high_complexity_funcs = []
    avg_complexity = 0.0
    max_complexity = 0.0

    try:
        from radon.complexity import cc_visit, cc_rank
    except ImportError:
        print("  [INFO] radon 未安装，跳过圈复杂度分析。pip install radon 以启用。")
        return avg_complexity, max_complexity, high_complexity_funcs

    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
        blocks = cc_visit(content)

        if not blocks:
            return avg_complexity, max_complexity, high_complexity_funcs

        complexities = [b.complexity for b in blocks]
        avg_complexity = sum(complexities) / len(complexities)
        max_complexity = max(complexities)

        threshold = config["thresholds"]["cyclomatic_complexity"]
        for block in blocks:
            if block.complexity > threshold:
                func_type = "method" if getattr(block, 'is_method', False) or getattr(block, 'classname', None) else block.__class__.__name__
                high_complexity_funcs.append({
                    "name": block.fullname if hasattr(block, 'fullname') else block.name,
                    "type": func_type,
                    "line": block.lineno,
                    "complexity": block.complexity,
                    "rank": cc_rank(block.complexity),
                })

        high_complexity_funcs.sort(key=lambda x: x["complexity"], reverse=True)

    except Exception as e:
        rel_path = str(filepath.relative_to(project_root))
        print(f"  [WARN] 复杂度分析失败 {rel_path}: {e}")

    return avg_complexity, max_complexity, high_complexity_funcs


# ==============================================================================
# 安全扫描
# ==============================================================================


def _get_unsafe_func_name(node: ast.AST) -> Optional[str]:
    """Extract the full function name from a Call node for unsafe-function checking.

    Handles: eval(...), module.eval(...), obj.method(...)
    Returns None if not a recognized unsafe call pattern.
    """
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        # module.func(...) or obj.method(...)
        return f"{func.attr}"
    return None


def _is_sql_injection_execute(node: ast.AST) -> Optional[int]:
    """Check if an AST Call node is .execute(...) with f-string or concatenation args.

    Returns the line number if risky, None otherwise.
    """
    if not isinstance(node, ast.Call):
        return None
    # Check if the function is .execute(...)
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr != "execute":
        return None
    # Check if any argument is an f-string (JoinedStr) or concatenation (BinOp with Add)
    for arg in node.args:
        if isinstance(arg, ast.JoinedStr):
            return node.lineno
        if isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Add):
            # Check if there's a string involved in the concatenation
            return node.lineno
    for kw in node.keywords:
        if isinstance(kw.value, ast.JoinedStr):
            return node.lineno
        if isinstance(kw.value, ast.BinOp) and isinstance(kw.value.op, ast.Add):
            return node.lineno
    return None


def security_scan_file(
    content: str, rel_path: str, config: Dict
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """扫描文件的安全问题（基于AST分析，避免对字符串字面量的误报）"""
    security_issues = []
    unsafe_functions = []
    sql_injection_risks = []

    # 1. 硬编码密钥/密码（仍使用正则，但跳过字符串字面量上下文中的误报）
    secret_patterns = config["security"]["secret_patterns"]
    for pattern in secret_patterns:
        for match in re.finditer(pattern, content, re.IGNORECASE):
            start_line = content[:match.start()].count("\n") + 1
            matched_text = match.group()
            if len(matched_text) > 20:
                display = matched_text[:15] + "..." + matched_text[-5:]
            else:
                display = matched_text
            security_issues.append({
                "line": start_line,
                "pattern": pattern,
                "match": display,
                "severity": "high",
            })

    # 2. 不安全的函数调用 — 基于AST分析，仅检测实际函数调用，忽略字符串字面量
    try:
        tree = ast.parse(content, filename=rel_path)
    except SyntaxError:
        # 如果语法解析失败，回退到原始字符串匹配（有限度）
        tree = None

    unsafe_func_names = set()
    for sig in config["security"]["unsafe_functions"]:
        name = sig.rstrip("(")  # "eval(" -> "eval"
        unsafe_func_names.add(name)

    if tree is not None:
        # AST模式：遍历所有Call节点，检测实际函数调用
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func_name = _get_unsafe_func_name(node)
            if func_name and func_name in unsafe_func_names:
                unsafe_functions.append({
                    "line": node.lineno,
                    "function": func_name + "(",
                    "context": ast.unparse(node)[:120] if hasattr(ast, 'unparse') else "",
                    "severity": "high",
                })

            # SQL注入检测：.execute() 使用f-string或拼接
            risk_line = _is_sql_injection_execute(node)
            if risk_line is not None:
                sql_injection_risks.append({
                    "line": risk_line,
                    "pattern": "execute() with f-string or concatenation",
                    "context": ast.unparse(node)[:120] if hasattr(ast, 'unparse') else "",
                    "severity": "critical",
                })
    else:
        # 回退模式：对无法解析的文件使用原始字符串匹配（有限度）
        unsafe_funcs = config["security"]["unsafe_functions"]
        for func_sig in unsafe_funcs:
            idx = 0
            while True:
                idx = content.find(func_sig, idx)
                if idx == -1:
                    break
                start_line = content[:idx].count("\n") + 1
                line_start = content.rfind("\n", 0, idx) + 1
                line_end = content.find("\n", idx)
                if line_end == -1:
                    line_end = len(content)
                context = content[line_start:line_end].strip()
                # 跳过配置定义行中的字符串字面量（避免自我检测误报）
                if 'unsafe_functions' in context or 'security' in context or '"' in context or "'" in context:
                    idx += len(func_sig)
                    continue
                unsafe_functions.append({
                    "line": start_line,
                    "function": func_sig,
                    "context": context[:120],
                    "severity": "high",
                })
                idx += len(func_sig)

        # SQL注入回退匹配
        sql_patterns = config["security"]["sql_injection_patterns"]
        for pattern in sql_patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                start_line = content[:match.start()].count("\n") + 1
                line_start = content.rfind("\n", 0, match.start()) + 1
                line_end = content.find("\n", match.start())
                if line_end == -1:
                    line_end = len(content)
                context = content[line_start:line_end].strip()
                # 跳过配置定义行
                if 'sql_injection_patterns' in context or 'security' in context:
                    continue
                sql_injection_risks.append({
                    "line": start_line,
                    "pattern": pattern,
                    "context": context[:120],
                    "severity": "critical",
                })

    return security_issues, unsafe_functions, sql_injection_risks


# ==============================================================================
# 依赖分析
# ==============================================================================


def build_dependency_graph(
    file_metrics: Dict[str, FileMetrics], known_third_party: List[str]
) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    """构建依赖图并识别未使用的 import"""
    graph: Dict[str, List[str]] = {}
    unused: Dict[str, List[str]] = {}

    for rel_path, metrics in file_metrics.items():
        module_deps = []
        for imp in metrics.imports:
            if imp not in known_third_party and imp != "__future__":
                module_deps.append(imp)
        graph[rel_path] = module_deps

        unused_here = []
        for imp in metrics.imports:
            if imp in known_third_party:
                continue
            filepath = Path(rel_path)
            if filepath.exists():
                try:
                    content = filepath.read_text(encoding="utf-8", errors="replace")
                    last_part = imp.split(".")[-1]
                    lines = content.splitlines()
                    usage_found = False
                    for i, line in enumerate(lines):
                        stripped = line.strip()
                        if stripped.startswith(("import ", "from ")):
                            continue
                        if last_part in stripped and not stripped.strip().startswith("#"):
                            usage_found = True
                            break
                    if not usage_found and last_part != imp:
                        unused_here.append(imp)
                except Exception:
                    pass
        if unused_here:
            unused[rel_path] = unused_here

    return graph, unused


def detect_circular_dependencies(graph: Dict[str, List[str]]) -> List[List[str]]:
    """使用 DFS 检测循环依赖"""
    visited: Set[str] = set()
    rec_stack: Set[str] = set()
    cycles: List[List[str]] = []

    def dfs(node: str, path: List[str]) -> None:
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        for neighbor in graph.get(node, []):
            if neighbor not in graph:
                continue
            if neighbor not in visited:
                dfs(neighbor, path)
            elif neighbor in rec_stack:
                cycle_start = path.index(neighbor)
                cycle = path[cycle_start:] + [neighbor]
                cycles.append(cycle)

        path.pop()
        rec_stack.discard(node)

    for node in graph:
        if node not in visited:
            dfs(node, [])

    # 去重
    seen_cycles: Set[str] = set()
    unique_cycles: List[List[str]] = []
    for cycle in cycles:
        min_idx = cycle.index(min(cycle))
        normalized = cycle[min_idx:] + cycle[1:min_idx + 1]
        key = "->".join(normalized)
        if key not in seen_cycles:
            seen_cycles.add(key)
            unique_cycles.append(cycle)

    return unique_cycles


# ==============================================================================
# 报告生成
# ==============================================================================


def generate_json_report(report: ScanReport, output_path: Path) -> None:
    """输出 JSON 格式报告"""
    report_dict = asdict(report)
    output_path.write_text(
        json.dumps(report_dict, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8"
    )
    print(f"  JSON 报告: {output_path}")


def generate_markdown_report(report: ScanReport, output_path: Path) -> None:
    """输出 Markdown 格式报告"""
    lines = []
    lines.append(f"# 技术债扫描报告 — {report.project_name}")
    lines.append(f"*扫描时间: {report.scan_time} | 耗时: {report.scan_duration_seconds:.2f}s*")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 概览
    lines.append("## 📊 代码健康概览")
    lines.append("")
    lines.append(f"- **健康评分**: {report.overall_health_score:.1f}/100")
    lines.append(f"- **Python 文件数**: {report.total_files}")
    lines.append(f"- **总行数**: {report.total_lines:,}")
    lines.append(f"- **代码行数**: {report.total_code_lines:,}")
    lines.append(f"- **注释行数**: {report.total_comment_lines:,} ({_calc_pct(report.total_comment_lines, report.total_lines):.1f}%)")
    lines.append(f"- **空行数**: {report.total_blank_lines:,} ({_calc_pct(report.total_blank_lines, report.total_lines):.1f}%)")
    lines.append(f"- **平均每文件行数**: {report.avg_lines_per_file:.1f}")
    lines.append(f"- **平均圈复杂度**: {report.average_complexity:.2f}")
    lines.append("")

    if report.thresholds_breached:
        lines.append("### ⚠️ 门槛违规")
        lines.append("")
        for breach in report.thresholds_breached:
            lines.append(f"- 🔴 {breach}")
        lines.append("")

    lines.append("## 📁 目录分布")
    lines.append("")
    lines.append("| 目录 | 文件数 |")
    lines.append("|------|-------:|")
    for dir_name, count in sorted(report.dir_distribution.items()):
        lines.append(f"| {dir_name} | {count} |")
    lines.append("")

    if report.large_files:
        lines.append("## 🗂️ 超大文件 (>{}行)".format(
            report.config.get("thresholds", {}).get("file_line_count", 1000)))
        lines.append("")
        lines.append("| 文件 | 行数 |")
        lines.append("|------|-----:|")
        for f in report.large_files:
            lines.append(f"| `{f['path']}` | {f['line_count']} |")
        lines.append("")

    if report.total_long_functions > 0:
        lines.append("## 🧵 超长函数 (>{}行)".format(
            report.config.get("thresholds", {}).get("function_line_count", 100)))
        lines.append("")
        lines.append("| 文件 | 函数 | 行数 |")
        lines.append("|------|------|-----:|")
        for f_meta in report.file_metrics.values():
            for func in f_meta.long_functions:
                lines.append(f"| `{f_meta.path}:{func['line']}` | `{func['name']}` | {func['length']} |")
        lines.append("")

    if report.total_todo + report.total_fixme + report.total_hack > 0:
        lines.append("## 📝 代码标记统计")
        lines.append("")
        lines.append(f"- **TODO**: {report.total_todo}")
        lines.append(f"- **FIXME**: {report.total_fixme}")
        lines.append(f"- **HACK**: {report.total_hack}")
        lines.append("")
        if report.marker_files:
            lines.append("| 文件 | TODO | FIXME | HACK |")
            lines.append("|------|-----:|------:|-----:|")
            for mf in report.marker_files:
                lines.append(f"| `{mf['path']}` | {mf['todo']} | {mf['fixme']} | {mf['hack']} |")
            lines.append("")

    if report.complexity_ranking:
        lines.append("## 🔄 圈复杂度排名 (Top 20)")
        lines.append("")
        lines.append("| 文件 | 平均复杂度 | 最高复杂度 | 高风险函数数 |")
        lines.append("|------|----------:|----------:|------------:|")
        for item in report.complexity_ranking[:20]:
            lines.append(f"| `{item['path']}` | {item['avg_complexity']:.2f} | {item['max_complexity']:.2f} | {item['high_risk_count']} |")
        lines.append("")

    if report.high_risk_files:
        lines.append("## 🚨 高风险模块 (复杂度 > {})".format(
            report.config.get("thresholds", {}).get("cyclomatic_complexity", 10)))
        lines.append("")
        for hr in report.high_risk_files:
            lines.append(f"### `{hr['path']}`")
            lines.append("")
            lines.append("| 函数 | 行号 | 复杂度 | 等级 |")
            lines.append("|------|:----:|-------:|:----:|")
            for func in hr["functions"]:
                lines.append(f"| `{func['name']}` | {func['line']} | {func['complexity']} | {func['rank']} |")
            lines.append("")

    if report.circular_dependencies:
        lines.append("## 🔗 循环依赖")
        lines.append("")
        for i, cycle in enumerate(report.circular_dependencies, 1):
            lines.append(f"{i}. `{'` → `'.join(cycle)}`")
        lines.append("")

    if report.unused_imports:
        lines.append("## 🗑️ 可能未使用的 Import")
        lines.append("")
        for path, imports in report.unused_imports.items():
            lines.append(f"- `{path}`: {', '.join(imports)}")
        lines.append("")

    has_security = report.total_security_issues + report.total_unsafe_functions + report.total_sql_injection_risks > 0
    if has_security:
        lines.append("## 🔒 安全问题")
        lines.append("")
        if report.total_security_issues > 0:
            lines.append(f"### 硬编码密钥/密码 ({report.total_security_issues})")
            lines.append("")
            for sf in report.security_issue_files:
                for issue in sf.get("secrets", []):
                    lines.append(f"- `{sf['path']}:{issue['line']}` — `{issue['match']}`")
            lines.append("")
        if report.total_unsafe_functions > 0:
            lines.append(f"### 不安全函数调用 ({report.total_unsafe_functions})")
            lines.append("")
            for sf in report.security_issue_files:
                for func in sf.get("unsafe_functions", []):
                    lines.append(f"- `{sf['path']}:{func['line']}` — `{func['function']}` → `{func['context']}`")
            lines.append("")
        if report.total_sql_injection_risks > 0:
            lines.append(f"### SQL 注入风险 ({report.total_sql_injection_risks})")
            lines.append("")
            for sf in report.security_issue_files:
                for sql in sf.get("sql_injection", []):
                    lines.append(f"- `{sf['path']}:{sql['line']}` — `{sql['context']}`")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"*由链客宝技术债扫描工具自动生成*")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Markdown 报告: {output_path}")


def _calc_pct(part: float, total: float) -> float:
    return (part / total * 100) if total > 0 else 0.0


def generate_html_report(report: ScanReport, output_path: Path) -> None:
    """输出 HTML 格式报告"""
    thresholds = report.config.get("thresholds", {})
    file_line_threshold = thresholds.get("file_line_count", 1000)
    func_line_threshold = thresholds.get("function_line_count", 100)
    complexity_threshold = thresholds.get("cyclomatic_complexity", 10)

    report_json = json.dumps(asdict(report), ensure_ascii=False, default=str)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>技术债扫描报告 — {report.project_name}</title>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; line-height: 1.6; padding: 2rem; }}
.container {{ max-width: 1200px; margin: 0 auto; }}
h1 {{ font-size: 2rem; margin-bottom: 0.5rem; color: #38bdf8; }}
h2 {{ font-size: 1.4rem; margin: 2rem 0 1rem; color: #94a3b8; border-bottom: 1px solid #1e293b; padding-bottom: 0.5rem; }}
h3 {{ font-size: 1.1rem; margin: 1rem 0 0.5rem; color: #cbd5e1; }}
.meta {{ color: #64748b; font-size: 0.9rem; margin-bottom: 2rem; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin: 1rem 0; }}
.card {{ background: #1e293b; border-radius: 0.75rem; padding: 1.25rem; border: 1px solid #334155; }}
.card .label {{ font-size: 0.85rem; color: #94a3b8; }}
.card .value {{ font-size: 2rem; font-weight: 700; color: #38bdf8; }}
.card .value.warn {{ color: #fbbf24; }}
.card .value.danger {{ color: #ef4444; }}
.card .value.good {{ color: #22c55e; }}
table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; }}
th, td {{ padding: 0.6rem 0.8rem; text-align: left; border-bottom: 1px solid #1e293b; }}
th {{ color: #94a3b8; font-weight: 600; font-size: 0.85rem; }}
td {{ font-size: 0.9rem; }}
tr:hover td {{ background: #1e293b; }}
code {{ background: #0f172a; padding: 0.15rem 0.4rem; border-radius: 0.25rem; font-size: 0.85rem; }}
.warning {{ background: #451a03; color: #fbbf24; padding: 0.75rem 1rem; border-radius: 0.5rem; margin: 0.5rem 0; }}
.danger {{ background: #450a0a; color: #ef4444; padding: 0.75rem 1rem; border-radius: 0.5rem; margin: 0.5rem 0; }}
.good {{ background: #052e16; color: #22c55e; padding: 0.75rem 1rem; border-radius: 0.5rem; margin: 0.5rem 0; }}
.footer {{ margin-top: 3rem; padding-top: 1rem; border-top: 1px solid #1e293b; color: #64748b; font-size: 0.85rem; }}
.badge {{ display: inline-block; padding: 0.15rem 0.5rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; }}
.badge-high {{ background: #450a0a; color: #ef4444; }}
.badge-medium {{ background: #451a03; color: #fbbf24; }}
.badge-low {{ background: #052e16; color: #22c55e; }}
.health-score {{ font-size: 4rem; font-weight: 800; text-align: center; }}
.health-label {{ text-align: center; font-size: 1rem; color: #94a3b8; }}
</style>
</head>
<body>
<div class="container">
<h1>🔍 技术债扫描报告</h1>
<div class="meta">{report.project_name} · {report.scan_time} · 耗时 {report.scan_duration_seconds:.2f}s</div>

<div class="grid">
  <div class="card">
    <div class="label">健康评分</div>
    <div class="value {'danger' if report.overall_health_score < 60 else 'warn' if report.overall_health_score < 80 else 'good'}">{report.overall_health_score:.1f}</div>
    <div style="font-size:0.8rem;color:#64748b">/ 100</div>
  </div>
  <div class="card">
    <div class="label">Python 文件</div>
    <div class="value">{report.total_files}</div>
  </div>
  <div class="card">
    <div class="label">总代码行数</div>
    <div class="value">{report.total_code_lines:,}</div>
  </div>
  <div class="card">
    <div class="label">平均圈复杂度</div>
    <div class="value">{report.average_complexity:.2f}</div>
  </div>
</div>

<div class="grid">
  <div class="card">
    <div class="label">注释率</div>
    <div class="value">{_calc_pct(report.total_comment_lines, report.total_lines):.1f}%</div>
  </div>
  <div class="card">
    <div class="label">TODO/FIXME/HACK</div>
    <div class="value {'danger' if report.total_todo > 10 else 'warn' if report.total_todo > 0 else 'good'}">{report.total_todo + report.total_fixme + report.total_hack}</div>
  </div>
  <div class="card">
    <div class="label">高风险文件</div>
    <div class="value {'danger' if report.high_risk_files else 'good'}">{len(report.high_risk_files)}</div>
  </div>
  <div class="card">
    <div class="label">安全问题</div>
    <div class="value {'danger' if report.total_security_issues + report.total_unsafe_functions + report.total_sql_injection_risks > 0 else 'good'}">{report.total_security_issues + report.total_unsafe_functions + report.total_sql_injection_risks}</div>
  </div>
</div>
"""
    # 门槛违规
    if report.thresholds_breached:
        html += '<h2>⚠️ 门槛违规</h2>\n'
        for breach in report.thresholds_breached:
            html += f'<div class="warning">🚨 {breach}</div>\n'

    # 目录分布
    html += '<h2>📁 目录分布</h2>\n<table><thead><tr><th>目录</th><th style="text-align:right">文件数</th></tr></thead><tbody>\n'
    for dir_name, count in sorted(report.dir_distribution.items()):
        html += f'<tr><td>{dir_name}</td><td style="text-align:right">{count}</td></tr>\n'
    html += '</tbody></table>\n'

    # 超大文件
    if report.large_files:
        html += f'<h2>🗂️ 超大文件 (&gt;{file_line_threshold}行)</h2>\n<table><thead><tr><th>文件</th><th style="text-align:right">行数</th></tr></thead><tbody>\n'
        for f in report.large_files:
            html += f'<tr><td><code>{f["path"]}</code></td><td style="text-align:right">{f["line_count"]:,}</td></tr>\n'
        html += '</tbody></table>\n'

    # 超长函数
    if report.total_long_functions > 0:
        html += f'<h2>🧵 超长函数 (&gt;{func_line_threshold}行)</h2>\n<table><thead><tr><th>文件</th><th>函数</th><th style="text-align:right">行数</th></tr></thead><tbody>\n'
        for f_meta in report.file_metrics.values():
            for func in f_meta.long_functions:
                html += f'<tr><td><code>{f_meta.path}:{func["line"]}</code></td><td><code>{func["name"]}</code></td><td style="text-align:right">{func["length"]}</td></tr>\n'
        html += '</tbody></table>\n'

    # 代码标记
    if report.total_todo + report.total_fixme + report.total_hack > 0:
        html += '<h2>📝 代码标记统计</h2>\n'
        html += f'<p>TODO: {report.total_todo} | FIXME: {report.total_fixme} | HACK: {report.total_hack}</p>\n'
        if report.marker_files:
            html += '<table><thead><tr><th>文件</th><th style="text-align:right">TODO</th><th style="text-align:right">FIXME</th><th style="text-align:right">HACK</th></tr></thead><tbody>\n'
            for mf in report.marker_files:
                html += f'<tr><td><code>{mf["path"]}</code></td><td style="text-align:right">{mf["todo"]}</td><td style="text-align:right">{mf["fixme"]}</td><td style="text-align:right">{mf["hack"]}</td></tr>\n'
            html += '</tbody></table>\n'

    # 复杂度排名
    if report.complexity_ranking:
        html += '<h2>🔄 圈复杂度排名 (Top 20)</h2>\n<table><thead><tr><th>文件</th><th style="text-align:right">平均复杂度</th><th style="text-align:right">最高复杂度</th><th style="text-align:right">高风险函数</th></tr></thead><tbody>\n'
        for item in report.complexity_ranking[:20]:
            html += f'<tr><td><code>{item["path"]}</code></td><td style="text-align:right">{item["avg_complexity"]:.2f}</td><td style="text-align:right">{item["max_complexity"]:.2f}</td><td style="text-align:right">{item["high_risk_count"]}</td></tr>\n'
        html += '</tbody></table>\n'

    # 高风险模块
    if report.high_risk_files:
        html += f'<h2>🚨 高风险模块 (复杂度 &gt;{complexity_threshold})</h2>\n'
        for hr in report.high_risk_files:
            html += f'<h3><code>{hr["path"]}</code></h3>\n'
            html += '<table><thead><tr><th>函数</th><th style="text-align:right">行号</th><th style="text-align:right">复杂度</th><th>等级</th></tr></thead><tbody>\n'
            for func in hr["functions"]:
                rank_class = "badge-high" if func["rank"] in ("C", "D", "E", "F") else "badge-medium"
                html += f'<tr><td><code>{func["name"]}</code></td><td style="text-align:right">{func["line"]}</td><td style="text-align:right">{func["complexity"]}</td><td><span class="badge {rank_class}">{func["rank"]}</span></td></tr>\n'
            html += '</tbody></table>\n'

    # 循环依赖
    if report.circular_dependencies:
        html += '<h2>🔗 循环依赖</h2>\n<ul>\n'
        for cycle in report.circular_dependencies:
            html += f'<li><code>{"</code> → <code>".join(cycle)}</code></li>\n'
        html += '</ul>\n'

    # 未使用的 import
    if report.unused_imports:
        html += '<h2>🗑️ 可能未使用的 Import</h2>\n<ul>\n'
        for path, imports in report.unused_imports.items():
            html += f'<li><code>{path}</code>: {", ".join(imports)}</li>\n'
        html += '</ul>\n'

    # 安全问题
    has_security = report.total_security_issues + report.total_unsafe_functions + report.total_sql_injection_risks > 0
    if has_security:
        html += '<h2>🔒 安全问题</h2>\n'
        if report.total_security_issues > 0:
            html += f'<h3>硬编码密钥/密码 ({report.total_security_issues})</h3>\n<ul>\n'
            for sf in report.security_issue_files:
                for issue in sf.get("secrets", []):
                    html += f'<li><code>{sf["path"]}:{issue["line"]}</code> — <code>{issue["match"]}</code></li>\n'
            html += '</ul>\n'
        if report.total_unsafe_functions > 0:
            html += f'<h3>不安全函数调用 ({report.total_unsafe_functions})</h3>\n<ul>\n'
            for sf in report.security_issue_files:
                for func in sf.get("unsafe_functions", []):
                    html += f'<li><code>{sf["path"]}:{func["line"]}</code> — <code>{func["function"]}</code> → <code>{func["context"]}</code></li>\n'
            html += '</ul>\n'
        if report.total_sql_injection_risks > 0:
            html += f'<h3>SQL 注入风险 ({report.total_sql_injection_risks})</h3>\n<ul>\n'
            for sf in report.security_issue_files:
                for sql in sf.get("sql_injection", []):
                    html += f'<li><code>{sf["path"]}:{sql["line"]}</code> — <code>{sql["context"]}</code></li>\n'
            html += '</ul>\n'

    html += '<div class="footer">由 链客宝技术债扫描工具 自动生成</div>\n</div>\n</body>\n</html>'

    output_path.write_text(html, encoding="utf-8")
    print(f"  HTML 报告: {output_path}")


# ==============================================================================
# 主扫描逻辑
# ==============================================================================


def run_scan(config: Dict[str, Any], project_root: Path) -> ScanReport:
    """执行完整扫描"""
    start_time = time.time()

    print("=" * 60)
    print("  链客宝技术债扫描工具")
    print("=" * 60)
    print(f"  项目路径: {project_root}")
    print(f"  扫描路径: {config['scan_paths']}")
    print()

    # 1. 发现文件
    print("[1/5] 扫描 Python 文件...")
    python_files = find_python_files(
        config["scan_paths"],
        config["exclude_patterns"],
        config["extensions"],
        project_root,
    )
    print(f"  发现 {len(python_files)} 个 Python 文件")
    print()

    # 2. 逐文件扫描
    print("[2/5] 分析代码指标...")
    report = ScanReport(config=config)
    report.scan_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    file_metrics: Dict[str, FileMetrics] = {}
    total_lines = 0
    total_code = 0
    total_comments = 0
    total_blanks = 0
    total_funcs = 0
    total_classes = 0
    total_todo = 0
    total_fixme = 0
    total_hack = 0
    total_complexity_sum = 0.0
    total_complexity_files = 0
    max_complexity_overall = 0.0

    large_files = []
    all_long_functions = []
    marker_files = []
    high_risk_files = []
    complexity_ranking = []

    all_security_issues = 0
    all_unsafe_funcs = 0
    all_sql_risks = 0
    security_issue_files = []

    for i, fpath in enumerate(python_files, 1):
        rel_path = str(fpath.relative_to(project_root))
        print(f"  [{i:3d}/{len(python_files):3d}] {rel_path[:70]:70s}", end="\r")

        # 基础指标
        metrics = scan_file_metrics(fpath, project_root, config)
        if metrics is None:
            continue

        total_lines += metrics.line_count
        total_code += metrics.code_line_count
        total_comments += metrics.comment_line_count
        total_blanks += metrics.blank_line_count
        total_funcs += metrics.function_count
        total_classes += metrics.class_count
        total_todo += metrics.todo_count
        total_fixme += metrics.fixme_count
        total_hack += metrics.hack_count

        # 圈复杂度 (radon)
        avg_cplx, max_cplx, high_cplx_funcs = analyze_complexity_with_radon(fpath, project_root, config)
        metrics.complexity = avg_cplx
        metrics.max_complexity = max_cplx
        metrics.high_complexity_functions = high_cplx_funcs

        if avg_cplx > 0:
            total_complexity_sum += avg_cplx
            total_complexity_files += 1
        if max_cplx > max_complexity_overall:
            max_complexity_overall = max_cplx

        # 安全扫描
        try:
            content = fpath.read_text(encoding="utf-8", errors="replace")
            secrets, unsafe_funcs, sql_risks = security_scan_file(content, rel_path, config)
            metrics.security_issues = secrets
            metrics.unsafe_functions = unsafe_funcs
            metrics.sql_injection_risks = sql_risks

            if secrets or unsafe_funcs or sql_risks:
                security_issue_files.append({
                    "path": rel_path,
                    "secrets": secrets,
                    "unsafe_functions": unsafe_funcs,
                    "sql_injection": sql_risks,
                })
                all_security_issues += len(secrets)
                all_unsafe_funcs += len(unsafe_funcs)
                all_sql_risks += len(sql_risks)
        except Exception as e:
            print(f"\n  [WARN] 安全扫描失败 {rel_path}: {e}")

        file_metrics[rel_path] = metrics

        # 收集超大文件
        file_line_threshold = config["thresholds"]["file_line_count"]
        if metrics.line_count > file_line_threshold:
            large_files.append({
                "path": rel_path,
                "line_count": metrics.line_count,
            })

        # 收集超长函数
        if metrics.long_functions:
            all_long_functions.extend(
                {"path": rel_path, **f} for f in metrics.long_functions
            )

        # 收集标记文件
        if metrics.todo_count > 0 or metrics.fixme_count > 0 or metrics.hack_count > 0:
            marker_files.append({
                "path": rel_path,
                "todo": metrics.todo_count,
                "fixme": metrics.fixme_count,
                "hack": metrics.hack_count,
            })

        # 收集高风险文件
        if high_cplx_funcs:
            high_risk_files.append({
                "path": rel_path,
                "avg_complexity": round(avg_cplx, 2),
                "max_complexity": round(max_cplx, 2),
                "functions": high_cplx_funcs,
            })

        # 收集复杂度排名
        if avg_cplx > 0:
            complexity_ranking.append({
                "path": rel_path,
                "avg_complexity": round(avg_cplx, 2),
                "max_complexity": round(max_cplx, 2),
                "high_risk_count": len(high_cplx_funcs),
            })

    print()

    # 3. 依赖分析
    print()
    print("[3/5] 依赖分析...")
    known_third_party = config["dependencies"].get("known_third_party", [])
    dep_graph, unused_imports = build_dependency_graph(file_metrics, known_third_party)
    circular_deps = detect_circular_dependencies(dep_graph)
    print(f"  依赖图节点: {len(dep_graph)}")
    print(f"  循环依赖: {len(circular_deps)}")
    print(f"  可能未使用的 import: {sum(len(v) for v in unused_imports.values())}")

    # 4. 目录分布
    print()
    print("[4/5] 统计分布...")
    dir_dist: Dict[str, int] = Counter()
    for rel_path in file_metrics:
        parent = str(Path(rel_path).parent) if Path(rel_path).parent != Path(".") else "."
        dir_dist[parent] += 1

    # 5. 组装报告
    print()
    print("[5/5] 生成报告...")

    report.total_files = len(file_metrics)
    report.total_lines = total_lines
    report.total_code_lines = total_code
    report.total_comment_lines = total_comments
    report.total_blank_lines = total_blanks
    report.avg_lines_per_file = round(total_lines / len(file_metrics), 1) if file_metrics else 0.0
    report.avg_code_lines_per_file = round(total_code / len(file_metrics), 1) if file_metrics else 0.0
    report.dir_distribution = dict(dir_dist)
    report.file_metrics = file_metrics

    report.large_files = sorted(large_files, key=lambda x: x["line_count"], reverse=True)
    report.total_long_functions = len(all_long_functions)

    report.total_todo = total_todo
    report.total_fixme = total_fixme
    report.total_hack = total_hack
    report.marker_files = sorted(marker_files, key=lambda x: -(x["todo"] + x["fixme"] + x["hack"]))

    report.high_risk_files = sorted(high_risk_files, key=lambda x: x["max_complexity"], reverse=True)
    report.complexity_ranking = sorted(complexity_ranking, key=lambda x: x["max_complexity"], reverse=True)
    report.average_complexity = round(total_complexity_sum / total_complexity_files, 2) if total_complexity_files > 0 else 0.0
    report.max_complexity_overall = round(max_complexity_overall, 2)

    report.dependency_graph = dep_graph
    report.circular_dependencies = circular_deps
    report.unused_imports = unused_imports

    report.total_security_issues = all_security_issues
    report.total_unsafe_functions = all_unsafe_funcs
    report.total_sql_injection_risks = all_sql_risks
    report.security_issue_files = security_issue_files

    # 健康评分
    report.overall_health_score = calculate_health_score(report, config)
    report.thresholds_breached = check_thresholds(report, config)
    report.summary = generate_summary(report, config)

    report.scan_duration_seconds = round(time.time() - start_time, 2)

    print(f"  扫描完成，耗时 {report.scan_duration_seconds:.2f}s")
    print()

    return report


def calculate_health_score(report: ScanReport, config: Dict) -> float:
    """计算代码健康评分 (0-100)"""
    score = 100.0

    # 1. 超大文件扣分
    large_file_penalty = len(report.large_files) * 5
    score -= min(large_file_penalty, 25)

    # 2. 超长函数扣分
    func_penalty = report.total_long_functions * 2
    score -= min(func_penalty, 15)

    # 3. 高复杂度扣分
    complex_penalty = len(report.high_risk_files) * 5
    score -= min(complex_penalty, 20)

    # 4. 代码标记扣分
    todo_tolerance = config["thresholds"]["todo_tolerance"]
    total_markers = report.total_todo + report.total_fixme + report.total_hack
    if total_markers > todo_tolerance:
        marker_penalty = (total_markers - todo_tolerance) * 2
        score -= min(marker_penalty, 15)

    # 5. 安全问题扣分
    security_count = report.total_security_issues + report.total_unsafe_functions + report.total_sql_injection_risks
    security_penalty = security_count * 10
    score -= min(security_penalty, 30)

    # 6. 循环依赖扣分
    cycle_penalty = len(report.circular_dependencies) * 5
    score -= min(cycle_penalty, 10)

    # 7. 注释率奖励 (10%-30% 为佳)
    if report.total_lines > 0:
        comment_ratio = report.total_comment_lines / report.total_lines
        if 0.1 <= comment_ratio <= 0.3:
            score += 5

    # 8. 空行率奖励 (>15% 为佳)
    if report.total_lines > 0:
        blank_ratio = report.total_blank_lines / report.total_lines
        if blank_ratio > 0.15:
            score += 3

    return max(0.0, min(100.0, score))


def check_thresholds(report: ScanReport, config: Dict) -> List[str]:
    """检查门槛值，返回违规列表"""
    breached = []
    t = config["thresholds"]

    if len(report.large_files) > 0:
        breached.append(f"发现 {len(report.large_files)} 个超大文件 (阈值: ≤{t['file_line_count']}行)")

    if report.total_long_functions > 0:
        breached.append(f"发现 {report.total_long_functions} 个超长函数 (阈值: ≤{t['function_line_count']}行)")

    if len(report.high_risk_files) > t.get("max_high_risk_files", 5):
        breached.append(
            f"高风险文件数 {len(report.high_risk_files)} 超过阈值 {t['max_high_risk_files']}"
        )

    total_markers = report.total_todo + report.total_fixme + report.total_hack
    if total_markers > t["todo_tolerance"]:
        breached.append(
            f"代码标记数 {total_markers} 超过容忍值 {t['todo_tolerance']} "
            f"(TODO: {report.total_todo}, FIXME: {report.total_fixme}, HACK: {report.total_hack})"
        )

    security_count = report.total_security_issues + report.total_unsafe_functions + report.total_sql_injection_risks
    if security_count > 0:
        breached.append(
            f"发现 {security_count} 个安全问题 "
            f"(密钥: {report.total_security_issues}, "
            f"不安全函数: {report.total_unsafe_functions}, "
            f"SQL注入: {report.total_sql_injection_risks})"
        )

    if report.circular_dependencies:
        breached.append(
            f"发现 {len(report.circular_dependencies)} 个循环依赖"
        )

    return breached


def generate_summary(report: ScanReport, config: Dict) -> str:
    """生成摘要"""
    parts = []
    parts.append(f"扫描 {report.total_files} 个 Python 文件，共 {report.total_lines:,} 行代码")
    parts.append(f"健康评分: {report.overall_health_score:.1f}/100")
    parts.append(f"平均圈复杂度: {report.average_complexity:.2f}")
    parts.append(f"TODO/FIXME/HACK 标记: {report.total_todo + report.total_fixme + report.total_hack} 个")
    if report.high_risk_files:
        parts.append(f"高风险模块: {len(report.high_risk_files)} 个")
    if report.total_security_issues + report.total_unsafe_functions + report.total_sql_injection_risks > 0:
        parts.append(f"安全问题: {report.total_security_issues + report.total_unsafe_functions + report.total_sql_injection_risks} 个")
    if report.circular_dependencies:
        parts.append(f"循环依赖: {len(report.circular_dependencies)} 处")
    summary = " | ".join(parts)
    return summary


def _normalize_scan_paths(config: Dict[str, Any], project_root: Path) -> None:
    """规范化扫描路径：移除多余的 'backend/' 前缀

    当运行在 BACKEND 根目录时，如果 scan_paths 仍包含 'backend/' 前缀
    （来自旧版配置），自动修正以避免 backend/backend/ 路径重复。
    """
    backend_name = project_root.name  # e.g. "backend"
    fixed = []
    for sp in config.get("scan_paths", []):
        # 如果路径以 "backend/" 或 "backend\\" 开头，去掉这个前缀
        parts = sp.replace("\\", "/").split("/")
        if parts and parts[0] == backend_name:
            fixed.append("/".join(parts[1:]) if len(parts) > 1 else ".")
            print(f"  [FIX] 自动修正路径 '{sp}' → '{fixed[-1]}'")
        else:
            fixed.append(sp)
    config["scan_paths"] = fixed

    # 同样修正输出目录
    od = config.get("report", {}).get("output_dir", "reports/tech_debt")
    parts = od.replace("\\", "/").split("/")
    if parts and parts[0] == backend_name:
        fixed_od = "/".join(parts[1:]) if len(parts) > 1 else "."
        config["report"]["output_dir"] = fixed_od
        print(f"  [FIX] 自动修正输出目录 '{od}' → '{fixed_od}'")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="链客宝技术债扫描工具 — 代码健康度与安全分析"
    )
    parser.add_argument(
        "--config", "-c",
        default="tech_debt_config.yaml",
        help="配置文件路径 (默认: tech_debt_config.yaml)"
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=None,
        help="报告输出目录 (默认: 配置中的 output_dir)"
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="CI 模式: 检测到高风险时以非零退出码退出"
    )
    parser.add_argument(
        "--formats", "-f",
        nargs="+",
        choices=["json", "markdown", "html"],
        default=None,
        help="输出格式 (默认: 配置中的所有格式)"
    )
    parser.add_argument(
        "--project-root", "-r",
        default=".",
        help="项目根目录 (默认: 当前目录)"
    )

    args = parser.parse_args()

    # 解析项目根目录
    project_root = Path(args.project_root).resolve()
    project_root = project_root / "backend" if (project_root / "backend").exists() and (project_root / "backend" / "app").exists() else project_root

    # 切换到项目根目录
    os.chdir(project_root)
    print(f"[INFO] 项目根目录: {project_root}")

    # 加载配置 - 先尝试绝对路径，再尝试相对于项目根目录
    config_path = args.config
    config_path_obj = Path(config_path)
    if not config_path_obj.is_absolute():
        config_path_obj = project_root / config_path
    if not config_path_obj.exists():
        config_path_obj = project_root / "tech_debt_config.yaml"
    if not config_path_obj.exists():
        config_path = None
        print("[INFO] 未找到配置文件，使用默认配置")
    else:
        config_path = str(config_path_obj)
        print(f"[INFO] 使用配置: {config_path}")

    config = load_config(config_path)
    _normalize_scan_paths(config, project_root)

    # 输出目录
    output_dir = args.output_dir or config["report"]["output_dir"]
    output_path = Path(output_dir)
    if not output_path.is_absolute():
        output_path = project_root / output_dir
    output_path.mkdir(parents=True, exist_ok=True)

    # 格式
    formats = args.formats or config["report"]["formats"]

    # 执行扫描
    report = run_scan(config, project_root)

    # 输出报告到 stdout (JSON)
    report_dict = asdict(report)
    print("\n" + "=" * 60)
    print("  JSON 报告输出")
    print("=" * 60)
    json_output = json.dumps(report_dict, ensure_ascii=False, indent=2, default=str)
    print(json_output)

    # 写入报告文件
    print("\n" + "=" * 60)
    print("  写入报告文件")
    print("=" * 60)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for fmt in formats:
        fname = f"tech_debt_report_{timestamp}.{fmt}"
        fpath = output_path / fname
        try:
            if fmt == "json":
                generate_json_report(report, fpath)
            elif fmt == "markdown":
                generate_markdown_report(report, fpath)
            elif fmt == "html":
                generate_html_report(report, fpath)
        except Exception as e:
            print(f"[ERROR] 生成 {fmt} 报告失败: {e}")

    print()
    print(f"  报告目录: {output_path.resolve()}")

    # 标准输出摘要
    print("\n" + "=" * 60)
    print("  扫描结果摘要")
    print("=" * 60)
    print(f"  健康评分:   {report.overall_health_score:.1f} / 100")
    print(f"  文件数:     {report.total_files}")
    print(f"  总行数:     {report.total_lines:,}")
    print(f"  平均复杂度: {report.average_complexity:.2f}")
    print(f"  TODO/FIXME: {report.total_todo + report.total_fixme + report.total_hack}")
    print(f"  安全问题:   {report.total_security_issues + report.total_unsafe_functions + report.total_sql_injection_risks}")
    print(f"  循环依赖:   {len(report.circular_dependencies)}")
    print()

    if report.thresholds_breached:
        print("⚠️  门槛违规:")
        for b in report.thresholds_breached:
            print(f"    • {b}")
        print()

    # CI 模式
    if args.ci:
        should_fail = False
        if config["report"].get("fail_on_high_risk", True) and report.thresholds_breached:
            should_fail = True
        if should_fail:
            print("\n❌ CI 检查失败: 存在门槛违规")
            sys.exit(1)
        else:
            print("\n✅ CI 检查通过")
            sys.exit(0)


if __name__ == "__main__":
    main()
