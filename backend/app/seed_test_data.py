"""
链客宝AI 数字名片测试数据种子脚本
===================================
为 P0 Feature 插入测试名片数据：
  - vCard导出  GET /api/card/{id}/vcard
  - OG预览     GET /api/card/{id}/share-preview
  - 邮件签名   GET /api/card/{id}/email-signature
  - 匹配引擎v2 POST /api/card/match

用法: python seed_test_data.py
"""

import json
import secrets
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


# ============================================================
# 数据库路径探测
# ============================================================
def _find_db() -> Path:
    """按优先级查找 chainke.db"""
    candidates = [
        Path("D:/链客宝/backend/data/chainke.db"),
        Path("D:/链客宝/backend/app/data/chainke.db"),
        Path(__file__).resolve().parent / ".." / "data" / "chainke.db",
        Path(__file__).resolve().parent / "data" / "chainke.db",
    ]
    for p in candidates:
        resolved = p.resolve() if not p.is_absolute() else p
        if resolved.exists():
            return resolved
    raise FileNotFoundError(
        "未找到 chainke.db！请确认数据库路径。\n已搜索: " + "\n        ".join(str(p) for p in candidates)
    )


# ============================================================
# 测试名片数据（5个不同行业）
# ============================================================
TEST_CARDS = [
    {
        "user_id": 1,  # admin (链客宝科技)
        "fields": {
            "name": "陈明远",
            "position": "CEO",
            "company": "康健医疗科技有限公司",
            "phone": "13912340001",
            "email": "chenmy@kangjianmed.com",
            "wechat": "chenmingyuan_kj",
            "address": "上海市浦东新区张江高科技园区药谷路88号",
            "website": "https://www.kangjianmed.com",
            "industry": "大健康/医疗",
            "bio": "专注医疗健康领域20年，提供智慧医疗整体解决方案",
            "tags": "医疗器械,智慧医疗,大健康,远程诊疗",
            "products": "智能血压计,远程问诊系统,医疗SaaS平台",
        },
        "cover_image": "https://picsum.photos/seed/kangjian-card/800/400",
        "view_count": 128,
    },
    {
        "user_id": 2,  # buyer1 (创新科技有限公司)
        "fields": {
            "name": "林志远",
            "position": "销售副总裁",
            "company": "智汇企业服务集团有限公司",
            "phone": "13912340002",
            "email": "linzy@zhihui-es.com",
            "wechat": "linzhiyuan_zh",
            "address": "北京市海淀区中关村大街1号银谷大厦20层",
            "website": "https://www.zhihui-es.com",
            "industry": "企业服务/SaaS",
            "bio": "为企业提供数字化转型升级一站式解决方案",
            "tags": "SaaS,企业管理,数字化转型,云计算,ERP",
            "products": "智汇CRM,智能OA系统,企业数据中台",
        },
        "cover_image": "https://picsum.photos/seed/zhihui-card/800/400",
        "view_count": 256,
    },
    {
        "user_id": 3,  # promoter1 (推广联盟)
        "fields": {
            "name": "张思远",
            "position": "技术总监",
            "company": "深蓝人工智能科技有限公司",
            "phone": "13912340003",
            "email": "zhangsy@deepblue-ai.com",
            "wechat": "zhangsiyuan_db",
            "address": "广东省深圳市南山区科技园南路1号AI创新中心",
            "website": "https://www.deepblue-ai.com",
            "industry": "科技/人工智能",
            "bio": "深耕NLP与计算机视觉，用AI赋能产业智能化升级",
            "tags": "人工智能,大模型,机器学习,计算机视觉,NLP",
            "products": "AI智能客服,视觉质检系统,知识图谱平台",
        },
        "cover_image": "https://picsum.photos/seed/deepblue-card/800/400",
        "view_count": 64,
    },
    {
        "user_id": 4,  # supplier1 (供应链集团)
        "fields": {
            "name": "李婉秋",
            "position": "创始人兼CEO",
            "company": "博雅教育科技集团有限公司",
            "phone": "13912340004",
            "email": "liwq@boya-edu.com",
            "wechat": "liwanqiu_by",
            "address": "浙江省杭州市西湖区文三路478号华星科技大厦12层",
            "website": "https://www.boya-edu.com",
            "industry": "教育培训",
            "bio": "致力于AI+教育，为千万学习者提供个性化学习体验",
            "tags": "在线教育,AI教育,职业教育,K12,终身学习",
            "products": "AI自适应学习系统,在线课程平台,教育大数据分析",
        },
        "cover_image": "https://picsum.photos/seed/boya-card/800/400",
        "view_count": 192,
    },
    {
        "user_id": 1,  # admin (链客宝科技)
        "fields": {
            "name": "王子轩",
            "position": "电商事业部总经理",
            "company": "好物优选电子商务有限公司",
            "phone": "13912340005",
            "email": "wangzx@haowuyouxuan.com",
            "wechat": "wangzixuan_hw",
            "address": "广东省广州市天河区珠江新城华夏路16号富力中心30楼",
            "website": "https://www.haowuyouxuan.com",
            "industry": "消费品/电商",
            "bio": "专注优质消费品供应链整合，让好产品直达消费者",
            "tags": "电商,消费品,供应链,直播带货,新零售",
            "products": "社区团购平台,社交电商SaaS,供应链管理系统",
        },
        "cover_image": "https://picsum.photos/seed/haowu-card/800/400",
        "view_count": 320,
    },
]


def _generate_share_token() -> str:
    """生成与 business_card_ai.generate_digital_card 一致的 share_token"""
    return secrets.token_urlsafe(32)


def _build_album_meta(fields: dict) -> list[dict]:
    """构建与 generate_digital_card 一致的 album_meta"""
    name = fields.get("name", "未知")
    company = fields.get("company", "")
    position = fields.get("position", "")
    subtitle_parts = [p for p in [position, company] if p]
    subtitle = " @ ".join(subtitle_parts) if subtitle_parts else ""

    contact_fields = []
    for key, label in [
        ("phone", "手机"),
        ("email", "邮箱"),
        ("wechat", "微信"),
        ("address", "地址"),
        ("website", "官网"),
    ]:
        if fields.get(key):
            contact_fields.append({"label": label, "value": fields[key]})

    return [
        {
            "page": 1,
            "type": "cover",
            "title": f"{name} 的数字名片",
            "subtitle": subtitle,
            "style": {
                "background": "linear-gradient(135deg, #0ea5e9 0%, #2563eb 50%, #7c3aed 100%)",
                "textColor": "#ffffff",
                "accentColor": "#fbbf24",
            },
        },
        {
            "page": 2,
            "type": "contact",
            "title": "联系方式",
            "fields": contact_fields,
            "style": {
                "background": "#ffffff",
                "textColor": "#1e293b",
                "accentColor": "#0ea5e9",
            },
        },
        {
            "page": 3,
            "type": "company",
            "title": "企业信息",
            "content": {
                "company": fields.get("company", ""),
                "position": fields.get("position", ""),
                "address": fields.get("address", ""),
                "website": fields.get("website", ""),
            },
            "style": {
                "background": "#f8fafc",
                "textColor": "#1e293b",
                "accentColor": "#2563eb",
            },
        },
    ]


def main():
    db_path = _find_db()
    print(f"📁 数据库路径: {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # ---- 检查是否已有数据 ----
    cur.execute("SELECT COUNT(*) as cnt FROM business_cards")
    existing = cur.fetchone()["cnt"]
    if existing > 0:
        print(f"⚠️  business_cards 表中已有 {existing} 条记录，跳过插入。")
        print("   如需重新插入，请先清空表: DELETE FROM business_cards;")
        conn.close()
        return

    # ---- 验证用户存在 ----
    cur.execute("SELECT id, username, name FROM users")
    users = {row["id"]: row for row in cur.fetchall()}
    print(f"👤 现有用户: {len(users)} 个")
    for uid, u in users.items():
        print(f"   - id={uid}: {u['name']} ({u['username']})")

    # ---- 逐条插入名片 ----
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    inserted = 0
    for card_data in TEST_CARDS:
        user_id = card_data["user_id"]
        if user_id not in users:
            print(f"   ⚠️  跳过: user_id={user_id} 不存在")
            continue

        fields_dict = card_data["fields"]
        share_token = _generate_share_token()
        album_meta = _build_album_meta(fields_dict)
        cover_image = card_data.get("cover_image")
        view_count = card_data.get("view_count", 0)

        # 从 fields 中提取部分字段放入 JSON 顶层（便于前端消费）
        # 也给 industry/tags/bio 加入 fields 但不破坏原有结构
        fields_json = json.dumps(fields_dict, ensure_ascii=False)
        album_meta_json = json.dumps(album_meta, ensure_ascii=False)

        sql = """
            INSERT INTO business_cards
                (user_id, fields, share_token, view_count, cover_image,
                 album_meta, version, created_at, updated_at,
                 is_deleted, membership_tier, match_credits)
            VALUES
                (?, ?, ?, ?, ?,
                 ?, 1, ?, ?,
                 0, 'free', 3)
        """
        cur.execute(
            sql,
            (
                user_id,
                fields_json,
                share_token,
                view_count,
                cover_image,
                album_meta_json,
                now_str,
                now_str,
            ),
        )
        card_id = cur.lastrowid
        inserted += 1
        print(
            f"   ✅ 已插入名片 id={card_id}: "
            f"{fields_dict.get('name')} @ {fields_dict.get('company')} "
            f"[{fields_dict.get('industry', '未分类')}]"
        )

    conn.commit()
    conn.close()
    print(f"\n🎉 完成！共插入 {inserted} 张测试名片。")
    print("\n可用端点测试:")
    print("  GET  /api/card/{id}              - 获取名片详情")
    print("  GET  /api/card/{id}/vcard         - vCard导出")
    print("  GET  /api/card/{id}/share-preview - OG预览")
    print("  GET  /api/card/{id}/email-signature - 邮件签名")
    print("  POST /api/card/{id}/match         - 匹配引擎")
    print("  GET  /api/card/token/{token}      - 通过token获取")
    return 0


if __name__ == "__main__":
    sys.exit(main())
