#!/bin/bash
# Phase 0 deploy script - upload and restart brochure API + card API
set -e

SRV="root@47.116.116.87"
LOCAL="/mnt/d/chainke-full/backend"
REMOTE="/var/www/liankebao/backend"

echo "=== 1. Upload digital_brochure_api.py ==="
scp "$LOCAL/digital_brochure_api.py" "$SRV:$REMOTE/digital_brochure_api.py"

echo "=== 2. Upload business_card router ==="
scp "$LOCAL/app/routers/business_card.py" "$SRV:$REMOTE/app/routers/business_card.py"

echo "=== 3. Upload six_degrees models ==="
scp -r "$LOCAL/app/models/six_degrees.py" "$SRV:$REMOTE/app/models/" 2>/dev/null || true

echo "=== 4. Upload seed data script ==="
scp "$LOCAL/seed_trust_network.py" "$SRV:$REMOTE/seed_trust_network.py"

echo "=== 5. Restart brochure API ==="
ssh "$SRV" "systemctl restart brochure-api && sleep 2 && systemctl status brochure-api --no-pager | head -5"

echo "=== 6. Restart main API ==="
ssh "$SRV" "systemctl restart liankebao-api 2>/dev/null || systemctl restart chainke-api 2>/dev/null || supervisorctl restart liankebao 2>/dev/null || echo 'check main service name'; ps aux | grep -i 'uvicorn\|gunicorn\|fastapi' | grep -v grep | head -3"

echo "=== 7. Verify brochure API ==="
sleep 2
curl -s "https://liankebao.top/api/v1/health" | head -1
echo ""
curl -s "https://liankebao.top/api/v1/common-connections?brochure_user_id=u_admin001&viewer_user_id=u_buyer001" | head -1

echo ""
echo "=== 8. Verify brochure_user_id in card API ==="
card_id=$(ssh "$SRV" "sqlite3 /var/www/liankebao/backend/data/chainke.db 'SELECT id FROM business_cards LIMIT 1'" 2>/dev/null || echo "1")
curl -s "https://liankebao.top/api/card/$card_id" | python3 -c "import sys,json; d=json.load(sys.stdin); print('brochure_user_id:', d.get('data',{}).get('brochure_user_id','NOT FOUND'))" 2>/dev/null || echo "Need to restart main service"

echo ""
echo "=== Done ==="
