#!/bin/bash
# 链客宝AI后端 API 综合测试 — 充值/支付端点
BASE="http://localhost:8000"

echo "=============================================="
echo "  链客宝AI后端 API 综合测试"
echo "=============================================="
echo ""

# === Step 1: Register test user ===
echo "--- [1/15] 注册测试用户 ---"
REG=$(curl -s -X POST $BASE/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"apitest","password":"test12345","name":"API Test","phone":"13900139000"}')
echo "$REG" | python -m json.tool 2>&1
echo ""

# === Step 2: Login ===
echo "--- [2/15] 登录获取 Token ---"
LOGIN=$(curl -s -X POST $BASE/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"apitest","password":"test12345"}')
TOKEN=$(echo "$LOGIN" | python -c "import sys, json; print(json.load(sys.stdin)['data']['access_token'])" 2>/dev/null)
echo "Token: ${TOKEN:0:30}..."
echo ""

if [ -z "$TOKEN" ]; then
  echo "ERROR: 登录失败!"
  exit 1
fi

AUTH="Authorization: Bearer $TOKEN"

# === Step 3: GET /api/recharge/balance ===
echo "--- [3/15] GET /api/recharge/balance ---"
curl -s $BASE/api/recharge/balance -H "$AUTH" | python -m json.tool 2>&1
echo ""

# === Step 4: POST /api/recharge/precreate (wxpay) ===
echo "--- [4/15] POST /api/recharge/precreate (wxpay, 10元) ---"
PRE1=$(curl -s -X POST $BASE/api/recharge/precreate \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"amount":10,"platform":"wxpay"}')
echo "$PRE1" | python -m json.tool 2>&1
ORDER_NO=$(echo "$PRE1" | python -c "import sys, json; print(json.load(sys.stdin)['data']['order_no'])" 2>/dev/null)
echo "OrderNo: $ORDER_NO"
echo ""

# === Step 5: POST /api/recharge/precreate (alipay - expect failure) ===
echo "--- [5/15] POST /api/recharge/precreate (alipay - should fail) ---"
curl -s -X POST $BASE/api/recharge/precreate \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"amount":50,"platform":"alipay"}' | python -m json.tool 2>&1
echo ""

# === Step 6: GET /api/recharge/list ===
echo "--- [6/15] GET /api/recharge/list ---"
curl -s "$BASE/api/recharge/list?page=1&limit=10" -H "$AUTH" | python -m json.tool 2>&1
echo ""

# === Step 7: GET /api/recharge/query/{order_no} ===
echo "--- [7/15] GET /api/recharge/query (pending order) ---"
curl -s "$BASE/api/recharge/query/$ORDER_NO" -H "$AUTH" | python -m json.tool 2>&1
echo ""

# === Step 8: POST /api/recharge/callback/mock ===
echo "--- [8/15] POST /api/recharge/callback/mock ---"
curl -s -X POST $BASE/api/recharge/callback/mock \
  -H "Content-Type: application/json" \
  -d "{\"out_trade_no\":\"$ORDER_NO\",\"transaction_id\":\"mock_tx_apitest\"}" | python -m json.tool 2>&1
echo ""

# === Step 9: GET /api/recharge/balance (after callback) ===
echo "--- [9/15] GET /api/recharge/balance (after payment) ---"
curl -s $BASE/api/recharge/balance -H "$AUTH" | python -m json.tool 2>&1
echo ""

# === Step 10: GET /api/recharge/query (after callback) ===
echo "--- [10/15] GET /api/recharge/query (paid order) ---"
curl -s "$BASE/api/recharge/query/$ORDER_NO" -H "$AUTH" | python -m json.tool 2>&1
echo ""

# === Step 11: Create a product order for payment test ===
echo "--- [11/15] POST /api/orders (create product order) ---"
ORDER_RESP=$(curl -s -X POST $BASE/api/orders \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"product_id":5,"quantity":1}')
echo "$ORDER_RESP" | python -m json.tool 2>&1
ORDER_ID=$(echo "$ORDER_RESP" | python -c "import sys, json; d=json.load(sys.stdin); print(d.get('data',{}).get('id',''))" 2>/dev/null)
echo "OrderID: $ORDER_ID"
echo ""

if [ -n "$ORDER_ID" ]; then
  # === Step 12: POST /api/payment/wxpay/unified-order ===
  echo "--- [12/15] POST /api/payment/wxpay/unified-order ---"
  curl -s -X POST $BASE/api/payment/wxpay/unified-order \
    -H "Content-Type: application/json" -H "$AUTH" \
    -d "{\"order_id\":$ORDER_ID,\"openid\":\"test_openid_123\"}" | python -m json.tool 2>&1
  echo ""

  # === Step 13: POST /api/payment/alipay/unified-order ===
  echo "--- [13/15] POST /api/payment/alipay/unified-order ---"
  curl -s -X POST $BASE/api/payment/alipay/unified-order \
    -H "Content-Type: application/json" -H "$AUTH" \
    -d "{\"order_id\":$ORDER_ID}" | python -m json.tool 2>&1
  echo ""
fi

# === Step 14: GET /api/payment/config ===
echo "--- [14/15] GET /api/payment/config ---"
curl -s $BASE/api/payment/config | python -m json.tool 2>&1
echo ""

# === Step 15: POST /api/recharge/adjust (test admin endpoint) ===
echo "--- [15/15] POST /api/recharge/adjust (try admin - expect 403) ---"
curl -s -X POST $BASE/api/recharge/adjust \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"user_id":8,"amount":100,"remark":"test"}' | python -m json.tool 2>&1
echo ""

echo "=============================================="
echo "  测试完成"
echo "=============================================="
