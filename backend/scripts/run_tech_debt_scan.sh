#!/bin/bash
# ==============================================================================
# 链客宝技术债扫描 — 执行脚本
# 用法:
#   bash scripts/run_tech_debt_scan.sh [options]
#
# 选项:
#   --ci         CI 模式，失败时非零退出
#   --output    报告输出目录 (默认: reports/tech_debt)
#   --help      显示帮助
#
# 路径说明:
#   此脚本应位于 BACKEND/scripts/ 目录下。
#   它自动定位 BACKEND 根目录并切换到该目录运行扫描器。
#   所有路径相对于 BACKEND 根目录。
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "========================================================"
echo "  链客宝技术债扫描工具"
echo "========================================================"
echo "项目路径: $PROJECT_ROOT"
echo ""

# 切换到项目根目录
cd "$PROJECT_ROOT"

# 检查 Python
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON="$cmd"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "[ERROR] 找不到 Python 解释器"
    exit 1
fi

echo "Python: $($PYTHON --version 2>&1)"
echo ""

# 检查/安装依赖
echo "[依赖检查]..."

if ! $PYTHON -c "import radon" 2>/dev/null; then
    echo "  [WARN] radon 未安装 — 跳过圈复杂度分析"
    echo "         pip install radon 以启用复杂度分析"
else
    echo "  [OK] radon 已安装"
fi

echo ""

# 解析参数
CI_FLAG=""
OUTPUT_DIR=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --ci)
            CI_FLAG="--ci"
            shift
            ;;
        --output)
            if [[ -n "${2:-}" ]]; then
                OUTPUT_DIR="$2"
                shift 2
            else
                echo "[ERROR] --output 需要参数"
                exit 1
            fi
            ;;
        --help|-h)
            echo "用法: $0 [--ci] [--output DIR]"
            echo ""
            echo "选项:"
            echo "  --ci           CI 模式，失败时非零退出"
            echo "  --output DIR   报告输出目录 (默认: reports/tech_debt)"
            echo "  --help         显示此帮助"
            exit 0
            ;;
        *)
            echo "[ERROR] 未知参数: $1"
            exit 1
            ;;
    esac
done

# 创建输出目录
REPORT_DIR="reports/tech_debt"
if [ -n "$OUTPUT_DIR" ]; then
    REPORT_DIR="$OUTPUT_DIR"
fi
mkdir -p "$REPORT_DIR"

echo "========================================================"
echo "  开始扫描..."
echo "========================================================"
echo ""

# 执行扫描
$PYTHON "$SCRIPT_DIR/tech_debt_scanner.py" \
    --config "tech_debt_config.yaml" \
    $CI_FLAG \
    ${OUTPUT_DIR:+--output-dir "$OUTPUT_DIR"}

SCAN_EXIT_CODE=$?

echo ""
echo "========================================================"

if [ $SCAN_EXIT_CODE -eq 0 ]; then
    echo "  扫描完成 ✅"
else
    echo "  扫描完成 ❌ (退出码: $SCAN_EXIT_CODE)"
fi

echo "========================================================"

# 列出报告文件
echo ""
echo "生成的报告:"
for f in "$REPORT_DIR"/*; do
    if [ -f "$f" ]; then
        echo "  • $f"
    fi
done

exit $SCAN_EXIT_CODE
