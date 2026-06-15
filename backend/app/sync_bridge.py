"""
# 跨环境AI同步桥 — 代码收割
sync_bridge.py — 轻量Flask桥，让飞书AI与本地AI共享sync文件

## 架构
飞书AI(阿里云) ──POST /sync──▶ sync_bridge(本地:5055) ──写入──▶ feishu_sync.yaml
飞书AI ◀──GET /status──── sync_bridge ◀──读取── local_progress.yaml

## 使用场景
任何需要两个AI在不同环境各自推进、自动对齐的项目

## 依赖
flask, pyyaml (纯Python标准库)

## 启动
python sync_bridge.py [port]
"""

import datetime
import os
import sys

import yaml
from flask import Flask, jsonify, request

HERMES = r"D:\向海容的知识库\wiki\wiki\记忆宫殿"
SYNC_FILE = os.path.join(HERMES, "L5孵化室", "产品开发", "链客宝AI", "feishu_sync.yaml")

app = Flask(__name__)


@app.route("/sync", methods=["POST"])
def sync_receive():
    """接收飞书AI的milestone→写入本地yaml"""
    data = request.get_json(silent=True) or {}
    milestone = {
        "date": data.get("date", datetime.date.today().isoformat()),
        "id": data.get("id", f"ms-{int(datetime.datetime.now().timestamp())}"),
        "milestone": data.get("milestone", ""),
        "status": data.get("status", "done"),
        "detail": data.get("detail", "")[:200],
    }
    if not milestone["milestone"]:
        return jsonify({"error": "milestone is required"}), 400

    if os.path.exists(SYNC_FILE):
        with open(SYNC_FILE, encoding="utf-8") as f:
            content = f.read()
    else:
        content = "# sync\nmilestones:\n"

    new_entry = (
        f'\n  - date: "{milestone["date"]}"\n'
        f'    id: "{milestone["id"]}"\n'
        f'    milestone: "{milestone["milestone"]}"\n'
        f"    status: {milestone['status']}\n"
        f'    detail: "{milestone["detail"]}"'
    )
    content += new_entry
    with open(SYNC_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    return jsonify({"ok": True, "milestone": milestone})


@app.route("/status")
def status():
    """飞书AI查看本地进度"""
    prog = os.path.join(HERMES, "L5孵化室", "产品开发", "链客宝AI", "local_progress.yaml")
    if os.path.exists(prog):
        with open(prog, encoding="utf-8") as f:
            return jsonify(yaml.safe_load(f))
    return jsonify({"error": "no progress"})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5055
    app.run(host="0.0.0.0", port=port, debug=False)
