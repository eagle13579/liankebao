"""Seed trust_network and test brochures for Phase 0 demo"""
import sqlite3
import os

db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'digital_brochure.db')
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Check existing brochures
existing = conn.execute('SELECT COUNT(*) as c FROM brochures').fetchone()
print(f'Existing brochures: {existing["c"]}')

if existing['c'] < 4:
    # Add test brochures
    seed_brochures = [
        ('u_admin001', '{"user_id":"u_admin001","name":"管理员","company":"链客宝科技","position":"CEO"}'),
        ('u_supplier001', '{"user_id":"u_supplier001","name":"王五","company":"供应链集团","position":"销售总监"}'),
        ('u_buyer001', '{"user_id":"u_buyer001","name":"张三","company":"创新科技","position":"CEO"}'),
        ('u_partner001', '{"user_id":"u_partner001","name":"李四","company":"推广联盟","position":"高级推广员"}'),
        ('u_demo001', '{"user_id":"u_demo001","name":"赵六","company":"Demo科技","position":"产品经理"}'),
        ('u_liuliu001', '{"user_id":"u_liuliu001","name":"刘柳","company":"柳叶科技","position":"CTO"}'),
        ('u_chenqi001', '{"user_id":"u_chenqi001","name":"陈七","company":"七星科技","position":"COO"}'),
        ('u_zhouba001', '{"user_id":"u_zhouba001","name":"周八","company":"八方贸易","position":"总经理"}'),
    ]
    for bid, data in seed_brochures:
        conn.execute("INSERT OR IGNORE INTO brochures (brochure_id, data) VALUES (?, ?)", (bid, data))
    print(f'Added {len(seed_brochures)} brochures')

# Add trust relationships
trust_pairs = [
    ('u_admin001', 'u_supplier001'),
    ('u_admin001', 'u_buyer001'),
    ('u_admin001', 'u_liuliu001'),
    ('u_admin001', 'u_chenqi001'),
    ('u_supplier001', 'u_partner001'),
    ('u_supplier001', 'u_liuliu001'),
    ('u_buyer001', 'u_demo001'),
    ('u_buyer001', 'u_chenqi001'),
    ('u_partner001', 'u_zhouba001'),
    ('u_demo001', 'u_zhouba001'),
    ('u_liuliu001', 'u_chenqi001'),
]

added = 0
for from_id, to_id in trust_pairs:
    conn.execute('INSERT OR IGNORE INTO trust_network (user_id, trusted_user_id) VALUES (?, ?)', (from_id, to_id))
    added += 1

conn.commit()
print(f'Added {added} trust relationships')

# Verify
total = conn.execute('SELECT COUNT(*) as c FROM trust_network').fetchone()
print(f'Total trust_network rows: {total["c"]}')

# Demo: common connections
viewer = 'u_admin001'
owner = 'u_buyer001'
viewer_set = set(r['trusted_user_id'] for r in conn.execute(
    'SELECT trusted_user_id FROM trust_network WHERE user_id=?', (viewer,)).fetchall())
owner_set = set(r['trusted_user_id'] for r in conn.execute(
    'SELECT trusted_user_id FROM trust_network WHERE user_id=?', (owner,)).fetchall())
common = viewer_set & owner_set
print(f'\nDemo: {viewer} viewing {owner}')
print(f'  Viewer trusts: {viewer_set}')
print(f'  Owner trusts: {owner_set}')
print(f'  Common connections: {common}')

conn.close()
print('\nDone! Phase 0 seed data ready.')
