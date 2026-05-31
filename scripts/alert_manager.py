#!/usr/bin/env python3
"""链客宝告警管理器 — scripts/ 入口包装器"""

import sys
from pathlib import Path

# 将项目根目录加入 sys.path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

# 委托给 deploy/alert_manager.py
from deploy.alert_manager import main

if __name__ == "__main__":
    main()
