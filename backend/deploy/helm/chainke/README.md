# =============================================================================
# 链客宝 Backend — Helm Chart 使用说明
# =============================================================================

# 安装
helm install chainke-backend ./deploy/helm/chainke \
  --namespace chainke-prod \
  --create-namespace \
  -f my-values.yaml

# 升级
helm upgrade chainke-backend ./deploy/helm/chainke \
  --namespace chainke-prod \
  -f my-values.yaml

# 回滚
helm rollback chainke-backend 1 \
  --namespace chainke-prod

# 删除
helm uninstall chainke-backend \
  --namespace chainke-prod

# 渲染模板 (调试)
helm template chainke-backend ./deploy/helm/chainke \
  --namespace chainke-prod \
  -f my-values.yaml

# 先创建必需的 Secret:
# kubectl create namespace chainke-prod
# kubectl create secret generic chainke-secret \
#   --namespace chainke-prod \
#   --from-literal=JWT_SECRET='$(openssl rand -hex 32)' \
#   --from-literal=DATABASE_URL='postgresql+asyncpg://chainke:password@postgres:5432/chainke' \
#   --from-literal=REDIS_PASSWORD='redispass' \
#   --from-literal=DEEPSEEK_API_KEY='sk-...'
# kubectl create secret tls chainke-tls-secret \
#   --namespace chainke-prod \
#   --cert=./certs/tls.crt \
#   --key=./certs/tls.key

# 默认 values.yaml 中的所有 config 项都可以通过 --set 覆盖:
# helm install chainke-backend ./deploy/helm/chainke \
#   --set image.tag=v1.2.3 \
#   --set backend.replicaCount=5 \
#   --set autoscaling.enabled=true \
#   --set autoscaling.minReplicas=3 \
#   --set autoscaling.maxReplicas=20
