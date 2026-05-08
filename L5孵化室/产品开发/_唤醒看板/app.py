#!/usr/bin/env python3
"""北极星产品唤醒看板 — Flask 主程序 (端口5030)"""

from flask import Flask, render_template, jsonify
from skybridge import PRODUCTS

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True


@app.route("/")
def index():
    """渲染唤醒看板主页"""
    return render_template("index.html")


@app.route("/api/products")
def api_products():
    """返回所有产品的JSON数据"""
    return jsonify(PRODUCTS)


@app.route("/api/resolve/<keyword>")
def api_resolve(keyword: str):
    """通过快捷唤醒词查询产品"""
    from skybridge import resolve
    result = resolve(keyword)
    if result:
        return jsonify(result)
    return jsonify({"error": f"未找到唤醒词「{keyword}」"}), 404


if __name__ == "__main__":
    print("✨ 北极星产品唤醒看板启动中...")
    print("   📍 http://localhost:5030")
    print("   📡 API: http://localhost:5030/api/products")
    app.run(host="0.0.0.0", port=5030, debug=True)
