"""
app.py — AI灵魂觉醒引擎 Flask主程序
路由：首页 / API觉醒 / 员工管理
端口：5015
数据存储：SQLite (soul_engine.db)
"""

import os
import sys
import sqlite3
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, render_template

# Add current dir to path for soul_engine import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from soul_engine import generate_employee

app = Flask(__name__)

# ============================================================
# Database setup
# ============================================================
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "soul_engine.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            subtitle TEXT DEFAULT '',
            role TEXT NOT NULL,
            role_description TEXT DEFAULT '',
            source_url TEXT DEFAULT '',
            source_description TEXT DEFAULT '',
            skills TEXT DEFAULT '[]',
            mind_models TEXT DEFAULT '[]',
            emotion_anchors TEXT DEFAULT '[]',
            soul_architecture TEXT DEFAULT '{}',
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT ''
        )
    """)
    conn.commit()
    conn.close()


def employee_to_dict(row):
    """Convert a sqlite Row to a dict with JSON fields parsed"""
    import json
    return {
        "id": row["id"],
        "name": row["name"],
        "subtitle": row["subtitle"],
        "role": row["role"],
        "role_description": row["role_description"],
        "source_url": row["source_url"],
        "source_description": row["source_description"],
        "skills": json.loads(row["skills"]) if row["skills"] else [],
        "mind_models": json.loads(row["mind_models"]) if row["mind_models"] else [],
        "emotion_anchors": json.loads(row["emotion_anchors"]) if row["emotion_anchors"] else [],
        "soul_architecture": json.loads(row["soul_architecture"]) if row["soul_architecture"] else {},
        "status": row["status"],
        "created_at": row["created_at"],
    }


# ============================================================
# Routes
# ============================================================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/awaken", methods=["POST"])
def awaken():
    """接收文本/URL，模拟蒸馏，返回生成的员工JSON"""
    data = request.get_json() or {}
    name = data.get("name", "")
    description = data.get("description", "")
    source_url = data.get("source_url", "")

    if not description and not source_url:
        return jsonify({"error": "请提供知识库描述或URL"}), 400

    # Generate employee using soul_engine
    employee = generate_employee(name, description, source_url)
    employee_id = str(uuid.uuid4())[:8]
    employee["id"] = employee_id

    # Save to database
    import json
    conn = get_db()
    conn.execute(
        """INSERT INTO employees 
           (id, name, subtitle, role, role_description, source_url, source_description,
            skills, mind_models, emotion_anchors, soul_architecture, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            employee_id,
            employee["name"],
            employee["subtitle"],
            employee["role"],
            employee["role_description"],
            employee["source_url"],
            employee["source_description"],
            json.dumps(employee["skills"], ensure_ascii=False),
            json.dumps(employee["mind_models"], ensure_ascii=False),
            json.dumps(employee["emotion_anchors"], ensure_ascii=False),
            json.dumps(employee["soul_architecture"], ensure_ascii=False),
            employee["status"],
            employee["created_at"],
        ),
    )
    conn.commit()
    conn.close()

    return jsonify({"success": True, "employee": employee}), 201


@app.route("/api/employees", methods=["GET"])
def list_employees():
    """返回已创建员工列表"""
    conn = get_db()
    rows = conn.execute("SELECT * FROM employees ORDER BY created_at DESC").fetchall()
    conn.close()
    employees = [employee_to_dict(row) for row in rows]
    return jsonify({"employees": employees})


@app.route("/api/employees/<employee_id>", methods=["DELETE"])
def delete_employee(employee_id):
    """删除员工"""
    conn = get_db()
    cursor = conn.execute("DELETE FROM employees WHERE id = ?", (employee_id,))
    conn.commit()
    deleted = cursor.rowcount
    conn.close()
    if deleted:
        return jsonify({"success": True, "message": f"员工 {employee_id} 已移除"})
    return jsonify({"error": "员工不存在"}), 404


@app.route("/api/employees/<employee_id>", methods=["GET"])
def get_employee(employee_id):
    """获取单个员工详情"""
    conn = get_db()
    row = conn.execute("SELECT * FROM employees WHERE id = ?", (employee_id,)).fetchone()
    conn.close()
    if row:
        return jsonify({"employee": employee_to_dict(row)})
    return jsonify({"error": "员工不存在"}), 404


@app.route("/api/templates", methods=["GET"])
def list_templates():
    """返回所有角色模板信息"""
    from soul_engine import list_role_templates
    return jsonify({"templates": list_role_templates()})


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    init_db()
    print("=" * 60)
    print("  AI灵魂觉醒引擎 v0.1")
    print("  AI Soul Awakening Engine")
    print("=" * 60)
    print(f"  启动于 http://0.0.0.0:5015")
    print(f"  DB路径: {DB_PATH}")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5015, debug=True)
