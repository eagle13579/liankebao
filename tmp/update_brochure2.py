import sqlite3
conn = sqlite3.connect('D:/向海容的知识库/wiki/wiki/记忆宫殿/L5孵化室/产品开发/AI数字名片/code/backend/digital_brochure.db')
c = conn.cursor()

# Fix page sort_order properly
pages = [
    (0, 'cover', '链客宝\n企业家的AI营销朋友圈', 'https://images.unsplash.com/photo-1517245386807-bb43f82c33c4?w=600&h=800&fit=crop', '', 1),
    (1, 'text', '六大核心产品模块\n\n产品池 - 精选优质货源\n推广中心 - 赚取高额分润\n人脉管理 - 高效触达客户\n订单管理 - 全流程追踪\n供需匹配 - AI精准对接\n数据洞察 - 生意增长分析', 'https://images.unsplash.com/photo-1552664730-d307ca884978?w=600&h=800&fit=crop', '', 2),
    (2, 'image', 'AI数字名片 - 翻页图册', 'https://images.unsplash.com/photo-1611532736597-de2d4265fba3?w=600&h=800&fit=crop', '一键生成电子画册，微信扫码即看', 3),
    (3, 'image', 'GEO诊断 - AI搜索可见度分析', 'https://images.unsplash.com/photo-1589829545856-d10d557cf95f?w=600&h=800&fit=crop', '诊断品牌在AI搜索引擎中的可见度', 4),
    (4, 'image', '你的AI数智员工军团', 'https://images.unsplash.com/photo-1558002038-1055907df827?w=600&h=800&fit=crop', '102名数智员工 - 8大部门 - 7x24在线', 5),
]

for sort_order, content_type, content, image_url, ai_summary, pid in pages:
    c.execute('UPDATE pages SET sort_order=?, content_type=?, content=?, image_url=?, ai_summary=? WHERE id=?',
              (sort_order, content_type, content, image_url, ai_summary, pid))

c.execute('UPDATE brochures SET pages_count=5, updated_at=datetime("now") WHERE id=1')
conn.commit()

c.execute('SELECT id, sort_order, content_type FROM pages WHERE brochure_id=1 ORDER BY sort_order')
for row in c.fetchall():
    print(f'  Page {row[0]}: order={row[1]} type={row[2]}')
conn.close()
print('Done')
