#!/bin/bash
# 链客宝技术债扫描执行脚本
set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUTPUT_DIR="${DIR}/reports/tech_debt"
mkdir -p "$OUTPUT_DIR"
python "${DIR}/scripts/tech_debt_scanner.py" --output "$OUTPUT_DIR"
echo "报告已生成: ${OUTPUT_DIR}/"
