# 链客宝AI — 部署指南（从零到生产）

> 本文档指导您完成链客宝在阿里云 ACK (阿里云容器服务 Kubernetes 版) 上的完整部署流程。

---

## 目录

1. [部署架构概览](#1-部署架构概览)
2. [前置准备](#2-前置准备)
3. [第一步：阿里云 RAM 账号创建](#3-第一步阿里云-ram-账号创建)
4. [第二步：ACR 容器镜像仓库配置](#4-第二步acr-容器镜像仓库配置)
5. [第三步：ACK 集群创建](#5-第三步ack-集群创建)
6. [第四步：本地环境配置](#6-第四步本地环境配置)
7. [第五步：构建并推送镜像](#7-第五步构建并推送镜像)
8. [第六步：一键部署到 ACK](#8-第六步一键部署到-ack)
9. [第七步：部署后验证](#9-第七步部署后验证)
10. [CI/CD 自动化部署](#10-cicd-自动化部署)
11. [日常运维](#11-日常运维)
12. [回滚指南](#12-回滚指南)
13. [常见问题](#13-常见问题)

---

## 1. 部署架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                      用户 / 客户端                            │
└─────────────────────┬───────────────────────────────────────┘
                      │ DNS: liankebao.top
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              阿里云 SLB (负载均衡)                             │
│         ├── HTTPS 443 ──► Ingress Controller                  │
│         └── HTTP 80   ──► 301 → HTTPS                        │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                  ACK 集群 (ManagedKubernetes)                 │
│                                                              │
│  ┌───────────────┐  ┌───────────────┐  ┌─────────────────┐  │
│  │  chainke-backend │  │ chainke-frontend│  │  Microservices   │  │
│  │  (FastAPI/Python)│  │  (Next.js/React)│  │  (附加模块)      │  │
│  └───────┬───────┘  └───────┬───────┘  └────────┬────────┘  │
│          │                  │                     │          │
│          ▼                  ▼                     ▼          │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │           阿里云 RDS PostgreSQL / Redis                   │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

**核心组件:**
- **ACK (ManagedKubernetes)**: 阿里云托管 K8s 集群，免运维 Master 节点
- **ACR (Container Registry)**: 阿里云容器镜像仓库，存放 Docker 镜像
- **ALB/Nginx Ingress**: 流量入口，支持 HTTPS + 自动证书
- **cert-manager**: 自动签发 Let's Encrypt SSL 证书
- **Kustomize**: 原生 K8s 配置管理，无需 Helm

---

## 2. 前置准备

| 项目 | 要求 | 说明 |
|------|------|------|
| 阿里云账号 | 已实名认证 | [注册阿里云](https://aliyun.com) |
| 域名 | 已备案 | 主域名: `liankebao.top` |
| 本地环境 | macOS / Linux / WSL | Windows 建议使用 WSL2 |
| Docker | >= 24.x | 用于构建镜像 |
| kubectl | >= 1.28 | K8s 命令行工具 |
| kustomize | >= 5.x | K8s 配置管理 |
| aliyun CLI | 最新版 | 阿里云命令行工具 |

**安装依赖（macOS / Linux）:**

```bash
# 安装 kubectl
curl -LO "https://dl.k8s.io/release/v1.30.0/bin/linux/amd64/kubectl"
chmod +x kubectl && sudo mv kubectl /usr/local/bin/

# 安装 kustomize
curl -s "https://raw.githubusercontent.com/kubernetes-sigs/kustomize/master/hack/install_kustomize.sh" | bash
sudo mv kustomize /usr/local/bin/

# 安装 aliyun CLI
curl -sL https://aliyun-cli.alibaba.com/install.sh | bash
```

---

## 3. 第一步：阿里云 RAM 账号创建

为 CI/CD 和自动化部署创建专用的 RAM 子账号，遵循最小权限原则。

### 3.1 创建 RAM 用户

1. 登录阿里云控制台 → [RAM 访问控制](https://ram.console.aliyun.com)
2. 左侧菜单: **身份管理** → **用户** → **创建用户**
3. 填写信息:

   | 字段 | 值 |
   |------|-----|
   | 登录名称 | `chainke-deployer` |
   | 显示名称 | `链客宝部署机器人` |
   | 访问方式 | ✅ 程序访问 (OpenAPI 调用) |

4. 点击 **确定**，**务必保存 AccessKey ID 和 AccessKey Secret**
   ```
   AccessKey ID:      LTAI5t****************
   AccessKey Secret:  ************************
   ```

### 3.2 授权策略

为 RAM 用户添加以下权限:

| 权限名称 | 说明 |
|----------|------|
| `AliyunCSFullAccess` | 容器服务 (ACK) 管理权限 |
| `AliyunContainerRegistryFullAccess` | 容器镜像服务 (ACR) 管理权限 |
| `AliyunECSReadOnlyAccess` | 弹性计算服务只读 (查看节点) |
| `AliyunVPCReadOnlyAccess` | 专有网络只读 (查看 VPC) |

**授权步骤:**
1. 进入 RAM 用户详情页
2. 点击 **授权** → 选择上述策略 → 确定

### 3.3 安全建议

> ⚠️ **安全警告:** AccessKey 等同于账号密码，请妥善保管！
> - 不要将 AccessKey 硬编码在代码或配置文件中
> - 定期轮换 AccessKey (建议每 90 天)
> - 在 GitHub Secrets 中存储，不在代码中暴露
> - 生产环境建议使用 RAM Role + OIDC 代替静态 AK/SK

---

## 4. 第二步：ACR 容器镜像仓库配置

### 4.1 创建 ACR 实例

1. 登录阿里云控制台 → [容器镜像服务 (ACR)](https://cr.console.aliyun.com)
2. 选择 **个人版** 或 **企业版**:
   - **个人版**: 免费，适合测试和小规模部署
   - **企业版**: 付费，支持多区域复制、安全扫描、高并发

3. 创建仓库命名空间:

   ```bash
   # 使用 aliyun CLI 创建命名空间
   aliyun cr --region cn-hangzhou \
     CreateNamespace --Namespace "chainke"
   ```

4. 创建镜像仓库:

   ```bash
   # 创建后端镜像仓库
   aliyun cr --region cn-hangzhou \
     CreateRepo \
     --RepoNamespace "chainke" \
     --RepoName "backend" \
     --Summary "链客宝后端服务" \
     --RepoType "PRIVATE"

   # 创建前端镜像仓库
   aliyun cr --region cn-hangzhou \
     CreateRepo \
     --RepoNamespace "chainke" \
     --RepoName "frontend" \
     --Summary "链客宝前端应用" \
     --RepoType "PRIVATE"
   ```

### 4.2 配置 ACR 访问凭证

**方式一：使用 RAM 用户 AK/SK (推荐)**

ACR 支持直接用 RAM 用户的 AccessKey 作为 Docker 登录凭证:

```bash
# 登录 ACR (使用 RAM 用户 AK/SK)
echo "<AccessKey-Secret>" | docker login \
  --username=<AccessKey-ID> \
  --password-stdin \
  registry.cn-hangzhou.aliyuncs.com
```

**方式二：使用专用密码**

1. ACR 控制台 → **访问凭证** → **设置固定密码**
2. 记录用户名和密码

### 4.3 验证 ACR 连通性

```bash
# 拉取测试镜像验证
docker pull hello-world
docker tag hello-world registry.cn-hangzhou.aliyuncs.com/chainke/hello-test
docker push registry.cn-hangzhou.aliyuncs.com/chainke/hello-test
echo "✅ ACR 配置完成"
```

---

## 5. 第三步：ACK 集群创建

### 5.1 通过控制台创建 (推荐新手)

1. 登录阿里云控制台 → [容器服务 ACK](https://cs.console.aliyun.com)
2. 点击 **创建集群** → **标准版集群 (ManagedKubernetes)**
3. 配置参数:

   | 配置项 | 推荐值 | 说明 |
   |--------|--------|------|
   | 集群名称 | `chainke-prod` | 生产环境集群 |
   | 地域 | `华东1（杭州）` | 选择离用户最近的区域 |
   | Kubernetes 版本 | `1.30.x` | 最新稳定版 |
   | 容器运行时 | `containerd` | 推荐 |
   | VPC | 自动创建或选择已有 | 建议新建 VPC |
   | 网络插件 | `Flannel` 或 `Terway` | Terway 性能更好 |
   | Service CIDR | `172.17.0.0/20` | 不与 VPC 冲突 |
   | 节点规格 | `ecs.g6.large` (2C8G) | 按需选择 |
   | 节点数量 | `3` | 生产建议 >=3 |
   | 系统盘 | `ESSD 120GB` | 高效云盘 |
   | 公网访问 API Server | ✅ 启用 | 方便 CI/CD 连接 |
   | 安全组 | 放行 6443 端口 | API Server 端口 |

4. 点击 **创建集群**，等待约 5-15 分钟

### 5.2 通过 aliyun CLI 创建 (推荐脚本化)

```bash
# 配置 aliyun CLI
aliyun configure set \
  --profile chainke \
  --access-key-id "<Your-AccessKey-ID>" \
  --access-key-secret "<Your-AccessKey-Secret>" \
  --region cn-hangzhou

# 创建托管版集群
aliyun cs POST /clusters \
  --region cn-hangzhou \
  --profile chainke \
  --header "Content-Type=application/json" \
  --body '{
    "name": "chainke-prod",
    "cluster_type": "ManagedKubernetes",
    "profile": "Default",
    "region_id": "cn-hangzhou",
    "container_cidr": "172.16.0.0/16",
    "service_cidr": "172.17.0.0/20",
    "num_of_nodes": 3,
    "instance_types": ["ecs.g6.large"],
    "system_disk_category": "cloud_essd",
    "system_disk_size": 120,
    "charge_type": "PostPaid",
    "worker_instance_charge_type": "PostPaid",
    "snat_entry": true,
    "endpoint_public_access": true
  }' | jq .
```

### 5.3 验证集群状态

```bash
# 查看集群列表
aliyun cs GET /clusters \
  --region cn-hangzhou \
  --profile chainke \
  --output json | jq '.clusters[] | {name, cluster_id, state, region_id}'

# 获取集群 kubeconfig
aliyun cs GET /k8s/<cluster-id>/user_config \
  --region cn-hangzhou \
  --profile chainke \
  --output json | jq -r '.config' | base64 -d > ~/.kube/config

# 验证连接
kubectl cluster-info
kubectl get nodes
```

---

## 6. 第四步：本地环境配置

### 6.1 克隆项目

```bash
git clone https://github.com/<your-org>/chainke.git
cd chainke
```

项目 K8s 配置结构:

```
deploy/k8s/
├── kustomization.yaml           # Kustomize 入口
├── namespace.yaml               # 命名空间定义
├── configmap.yaml               # 通用配置
├── secrets.yaml                 # Secret 模板 (勿填入真实值)
├── backend-deployment.yaml      # 后端 Deployment
├── backend-service.yaml         # 后端 Service
├── frontend-deployment.yaml     # 前端 Deployment
├── frontend-service.yaml        # 前端 Service
├── ingress.yaml                 # Ingress + TLS
├── hpa.yaml                     # 水平自动伸缩
├── deploy-ack.sh                # ✅ 一键部署到 ACK
├── post-deploy-check.sh         # ✅ 部署后健康检查
├── deploy-multi-region.sh       # 多区域部署
└── microservices/               # 微服务模块
    ├── user-service.yaml
    ├── matching-service.yaml
    ├── payment-service.yaml
    ├── notification-service.yaml
    └── ...
```

### 6.2 配置 kubectl 访问 ACK 集群

```bash
# 使用 aliyun CLI 获取 kubeconfig
CLUSTER_ID=$(aliyun cs GET /clusters \
  --region cn-hangzhou \
  --profile chainke \
  --query "clusters[?name=='chainke-prod'].cluster_id | [0]" \
  --output json | tr -d '"')

aliyun cs GET /k8s/${CLUSTER_ID}/user_config \
  --region cn-hangzhou \
  --profile chainke \
  --output json | jq -r '.config' | base64 -d > ~/.kube/config

chmod 600 ~/.kube/config

# 验证
kubectl cluster-info
kubectl get nodes -o wide
```

### 6.3 创建命名空间

```bash
kubectl apply -f deploy/k8s/namespace.yaml
# 或
kubectl create namespace chainke
```

### 6.4 配置 Secrets

```bash
# 方式一：从环境变量创建 (推荐)
export PG_PASSWORD="your-secure-password"
export SECRET_KEY="your-jwt-secret"
export GEMINI_API_KEY="your-gemini-key"

kubectl create secret generic chainke-secret --namespace=chainke \
  --from-literal=PG_USER='chainke' \
  --from-literal=PG_PASSWORD="${PG_PASSWORD}" \
  --from-literal=SECRET_KEY="${SECRET_KEY}" \
  --from-literal=ENCRYPTION_KEY="${ENCRYPTION_KEY:-}" \
  --from-literal=GEMINI_API_KEY="${GEMINI_API_KEY:-}"

# 方式二：从文件创建
kubectl apply -f deploy/k8s/secrets.yaml  # 先填入 base64 编码的值
```

---

## 7. 第五步：构建并推送镜像

### 7.1 登录 ACR

```bash
# 使用 RAM 用户的 AccessKey 登录 (推荐)
echo "<Your-AccessKey-Secret>" | docker login \
  --username="<Your-AccessKey-ID>" \
  --password-stdin \
  registry.cn-hangzhou.aliyuncs.com
```

### 7.2 构建并推送

```bash
# 设置版本号
VERSION=v1.0.0

# 构建后端
docker build \
  -t registry.cn-hangzhou.aliyuncs.com/chainke/backend:${VERSION} \
  -t registry.cn-hangzhou.aliyuncs.com/chainke/backend:latest \
  --target backend \
  --build-arg BUILD_VERSION=${VERSION} \
  --build-arg BUILD_TIMESTAMP=$(date -u +'%Y%m%d%H%M%S') \
  -f Dockerfile .

# 构建前端
docker build \
  -t registry.cn-hangzhou.aliyuncs.com/chainke/frontend:${VERSION} \
  -t registry.cn-hangzhou.aliyuncs.com/chainke/frontend:latest \
  --target frontend \
  --build-arg BUILD_VERSION=${VERSION} \
  --build-arg BUILD_TIMESTAMP=$(date -u +'%Y%m%d%H%M%S') \
  -f Dockerfile .

# 推送镜像
docker push registry.cn-hangzhou.aliyuncs.com/chainke/backend:${VERSION}
docker push registry.cn-hangzhou.aliyuncs.com/chainke/backend:latest
docker push registry.cn-hangzhou.aliyuncs.com/chainke/frontend:${VERSION}
docker push registry.cn-hangzhou.aliyuncs.com/chainke/frontend:latest
```

---

## 8. 第六步：一键部署到 ACK

### 方式一：使用部署脚本 (推荐)

```bash
# 先配置环境变量
export ALICLOUD_REGION=cn-hangzhou
export ACK_CLUSTER_NAME=chainke-prod
export ACR_REGISTRY=registry.cn-hangzhou.aliyuncs.com/chainke

# 一键部署
cd deploy/k8s && chmod +x deploy-ack.sh
./deploy-ack.sh --version v1.0.0
```

脚本会自动完成:
1. ✅ 检查前置依赖 (aliyun CLI, kubectl, kustomize)
2. ✅ 检查 ACK 集群是否存在，不存在则自动创建
3. ✅ 获取并配置 kubeconfig
4. ✅ 创建命名空间
5. ✅ 配置 Secrets (从环境变量)
6. ✅ 通过 Kustomize 部署所有资源
7. ✅ 等待 Deployment 就绪
8. ✅ 执行健康检查

### 方式二：手动部署 (分步执行)

```bash
# 1. 更新镜像标签
cd deploy/k8s
kustomize edit set image \
  registry.cn-hangzhou.aliyuncs.com/chainke/backend=v1.0.0 \
  registry.cn-hangzhou.aliyuncs.com/chainke/frontend=v1.0.0

# 2. 部署全部资源
kustomize build . | kubectl apply -f -

# 3. 等待就绪
kubectl -n chainke wait --for=condition=Available deployment/chainke-backend --timeout=180s
kubectl -n chainke wait --for=condition=Available deployment/chainke-frontend --timeout=180s

# 4. 查看状态
kubectl -n chainke get pods,deployments,services,ingress,hpa -o wide
```

---

## 9. 第七步：部署后验证

### 9.1 运行健康检查脚本

```bash
# 基本检查
bash deploy/k8s/post-deploy-check.sh

# 详细检查 + 等待就绪 + 端点测试
bash deploy/k8s/post-deploy-check.sh --verbose --wait --endpoint-check

# 如果检查失败，返回非零退出码 (可用于 CI/CD)
bash deploy/k8s/post-deploy-check.sh --fail-on-error
```

检查内容:
- ✅ Namespace 存在
- ✅ 所有 Pod 处于 Running 状态
- ✅ Deployment 可用 (readyReplicas == replicas)
- ✅ Service 配置正确
- ✅ Ingress 已分配地址
- ✅ HPA 指标正常
- ✅ ConfigMap / Secret 存在
- ✅ 端点可达性 (集群内 HTTP 测试)

### 9.2 手动验证

```bash
# 查看所有资源
kubectl -n chainke get all -o wide

# 查看 Pod 日志
kubectl -n chainke logs -l app=chainke --tail=20

# 查看事件
kubectl -n chainke get events --sort-by='.lastTimestamp'

# 测试 Ingress
curl -k https://api.liankebao.top/health

# 测试 Service (集群内)
kubectl -n chainke run test-curl --image=curlimages/curl -it --rm -- \
  curl -s http://chainke-backend/health
```

---

## 10. CI/CD 自动化部署

### 10.1 GitHub Secrets 配置

在 GitHub 仓库的 Settings → Secrets and variables → Actions 中添加:

| Secret 名称 | 必填 | 说明 |
|------------|------|------|
| `ALIYUN_ACCESS_KEY` | ✅ | RAM 用户 AccessKey ID |
| `ALIYUN_ACCESS_KEY_SECRET` | ✅ | RAM 用户 AccessKey Secret |
| `ACR_REGISTRY` | ✅ | 镜像仓库地址 (如 `registry.cn-hangzhou.aliyuncs.com/chainke`) |
| `ACK_CLUSTER_ID` | ✅ | ACK 集群 ID |
| `ALIYUN_REGION` | 选填 | 阿里云区域 (默认: cn-hangzhou) |

### 10.2 工作流程

CI/CD 配置文件: `.github/workflows/k8s-deploy.yml`

**自动触发条件:**
- 向 `master` / `main` 分支推送代码
- 手动触发 (Workflow Dispatch)

**工作流程:**
```
1. 计算版本号
   └── 从 git tag / commit SHA / 手动输入
       └── 输出: version, timestamp

2. Docker 构建 + 推送 (并行构建前后端)
   ├── 后端: Docker build → push ACR
   ├── 前端: Docker build → push ACR
   └── 多架构: linux/amd64 + linux/arm64

3. K8s 部署
   ├── 模式A: 通过 aliyun CLI 获取 ACK kubeconfig (直连)
   ├── 模式B: 通过 SSH 堡垒机 (降级)
   ├── 更新镜像标签
   ├── kubectl apply -k 部署
   └── 健康检查
```

### 10.3 手动触发部署

```bash
# 在 GitHub Actions 页面手动运行
# 或使用 gh CLI:
gh workflow run k8s-deploy.yml \
  --ref main \
  --field version=v1.2.3 \
  --field environment=production
```

### 10.4 扩展: 使用 OIDC 代替静态 AK/SK (生产推荐)

阿里云支持 GitHub Actions OIDC 身份认证，无需配置静态 AccessKey:

1. 创建 RAM Role，信任 GitHub OIDC Provider
2. 配置 GitHub Actions 使用 `aliyun/configure-aliyun-credentials@v2`
3. 参考文档: [阿里云 GitHub Actions OIDC](https://www.alibabacloud.com/help/en/ram/user-guide/use-oidc-to-access-aliyun-by-using-github-actions)

---

## 11. 日常运维

### 11.1 查看部署状态

```bash
# 常用命令速查
kubectl -n chainke get pods                    # 查看 Pod
kubectl -n chainke get deployments             # 查看部署
kubectl -n chainke get services                # 查看服务
kubectl -n chainke get ingress                 # 查看入口
kubectl -n chainke get hpa                     # 查看自动伸缩
kubectl -n chainke get events --sort-by='.lastTimestamp'  # 查看事件
kubectl -n chainke top pods                    # 查看资源使用
kubectl -n chainke logs deployment/chainke-backend  # 查看日志
```

### 11.2 扩容与缩容

```bash
# 手动扩缩
kubectl -n chainke scale deployment/chainke-backend --replicas=5

# 查看 HPA 状态
kubectl -n chainke describe hpa chainke-hpa

# 更新 HPA 配置 (修改 hpa.yaml 后重新 apply)
kubectl apply -f deploy/k8s/hpa.yaml
```

### 11.3 更新配置

```bash
# 更新 ConfigMap (滚动更新)
kubectl apply -f deploy/k8s/configmap.yaml

# 更新后重启 Pod (如需)
kubectl -n chainke rollout restart deployment/chainke-backend
kubectl -n chainke rollout restart deployment/chainke-frontend
```

### 11.4 查看日志

```bash
# 实时日志
kubectl -n chainke logs -f deployment/chainke-backend

# 带时间戳
kubectl -n chainke logs --tail=100 --timestamps deployment/chainke-backend

# 多 Pod 聚合 (需 stern)
stern -n chainke backend
```

---

## 12. 回滚指南

### 12.1 回滚到上一版本

```bash
# 查看部署历史
kubectl -n chainke rollout history deployment/chainke-backend

# 回滚到上一版本
kubectl -n chainke rollout undo deployment/chainke-backend

# 回滚到指定版本
kubectl -n chainke rollout undo deployment/chainke-backend --to-revision=3

# 查看回滚状态
kubectl -n chainke rollout status deployment/chainke-backend
```

### 12.2 通过镜像标签回滚

```bash
# 指定旧版本镜像重新部署
cd deploy/k8s
kustomize edit set image \
  registry.cn-hangzhou.aliyuncs.com/chainke/backend=v1.0.0 \
  registry.cn-hangzhou.aliyuncs.com/chainke/frontend=v1.0.0
kustomize build . | kubectl apply -f -
```

---

## 13. 常见问题

### Q: aliyun CLI 报错 "The specified cluster is not found"

**原因:** 集群 ID 或名称错误，或区域不匹配。

**解决:**
```bash
# 列出所有集群
aliyun cs GET /clusters --region cn-hangzhou --profile chainke | jq '.clusters[] | {name, cluster_id, region_id}'
```

### Q: kubectl 连接超时

**原因:** API Server 公网端点未启用，或安全组未放行。

**解决:**
1. ACK 控制台 → 集群详情 → **基本信息** → **启用公网 API Server**
2. 安全组放行 6443 端口 (源: 0.0.0.0/0 或 CI/CD 出口 IP)

### Q: Pod 一直处于 Pending 状态

**原因:** 资源不足 (CPU/内存) 或 PVC 未绑定。

**解决:**
```bash
kubectl -n chainke describe pod <pod-name>
# 查看 Events 部分，通常会有明确错误信息
# 常见原因: 节点资源不足 → 扩容节点或减少副本数
```

### Q: 镜像拉取失败 (ImagePullBackOff)

**原因:** ACR 登录凭证未配置，或镜像标签错误。

**解决:**
```bash
# 检查镜像拉取凭证
kubectl -n chainke get secrets

# 创建或更新 ACR 拉取凭证
kubectl -n chainke create secret docker-registry acr-secret \
  --docker-server=registry.cn-hangzhou.aliyuncs.com \
  --docker-username=<RAM-User-AK> \
  --docker-password=<RAM-User-SK>

# 在 deployment 中指定 imagePullSecrets
```

### Q: Ingress 未分配地址

**原因:** Ingress Controller 未部署或类型不匹配。

**解决:**
```bash
# 部署 Nginx Ingress Controller
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/cloud/deploy.yaml

# 或使用阿里云 ALB Ingress Controller
# 参考: https://cs.console.aliyun.com → 组件管理 → alb-ingress-controller
```

### Q: cert-manager 证书签发失败

**原因:** DNS 解析未指向 Ingress Controller 地址，或 ACME 挑战失败。

**解决:**
```bash
# 查看证书状态
kubectl get certificate -n chainke
kubectl describe certificate chainke-tls -n chainke

# 确保 DNS A 记录指向 Ingress Controller 的公网 IP
# 需要配置:
#   liankebao.top    → <Ingress-IP>
#   api.liankebao.top → <Ingress-IP>
#   cdn.liankebao.top → <Ingress-IP>
```

---

## 附录

### A. 文件清单

| 文件 | 说明 |
|------|------|
| `deploy/k8s/deploy-ack.sh` | 一键部署到阿里云 ACK |
| `deploy/k8s/post-deploy-check.sh` | 部署后健康检查 |
| `deploy/k8s/deploy-multi-region.sh` | 多区域部署脚本 |
| `deploy/k8s/kustomization.yaml` | Kustomize 入口配置 |
| `deploy/k8s/namespace.yaml` | 命名空间定义 |
| `deploy/k8s/configmap.yaml` | 通用配置 |
| `deploy/k8s/secrets.yaml` | Secret 模板 |
| `deploy/k8s/ingress.yaml` | Ingress + cert-manager |
| `deploy/k8s/hpa.yaml` | 水平自动伸缩 |
| `.github/workflows/k8s-deploy.yml` | GitHub Actions CI/CD |

### B. 相关链接

- [阿里云 ACK 文档](https://help.aliyun.com/product/85222.html)
- [阿里云 ACR 文档](https://help.aliyun.com/product/60790.html)
- [阿里云 CLI 文档](https://help.aliyun.com/document_detail/90765.html)
- [Kubernetes 官方文档](https://kubernetes.io/docs/)
- [Kustomize 文档](https://kubectl.docs.kubernetes.io/)
- [cert-manager 文档](https://cert-manager.io/docs/)

### C. 快速参考 (Cheat Sheet)

```bash
# === 日常命令速查 ===

# 部署
./deploy-ack.sh --version v1.0.0

# 健康检查
./post-deploy-check.sh --verbose --wait --endpoint-check

# 查看资源
kubectl -n chainke get pods,deploy,svc,ing,hpa -o wide

# 日志
kubectl -n chainke logs -f deployment/chainke-backend

# 回滚
kubectl -n chainke rollout undo deployment/chainke-backend

# 强制重启
kubectl -n chainke rollout restart deployment/chainke-backend

# 进入 Pod
kubectl -n chainke exec -it deployment/chainke-backend -- /bin/sh

# 端口转发 (本地调试)
kubectl -n chainke port-forward service/chainke-backend 8001:8001
```
