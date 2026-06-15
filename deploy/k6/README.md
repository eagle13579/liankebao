# 链客宝AI — k6 性能测试

## 概述

基于 [k6](https://k6.io/) 的性能测试套件，包含烟雾测试和压力测试，用于验证链客宝AI后端 API 的性能和稳定性。

## 目录结构

```
deploy/k6/
├── scripts/
│   ├── smoke_test.js          # 烟雾测试（10 并发，30s）
│   └── stress_test.js         # 压力测试（10→200 阶梯，2min）
├── results/                   # 测试结果存放目录
│   └── README.md              # 结果说明
├── CI_GUIDE.md                # GitHub Actions CI 集成指南
└── README.md                  # 本文件
```

## 安装 k6

### Windows

**方式一：通过 winget（推荐）**
```powershell
winget install k6
```

**方式二：通过 Chocolatey**
```powershell
choco install k6
```

**方式三：手动下载**
1. 访问 https://k6.io/docs/get-started/installation/
2. 下载 Windows 版本的 .msi 或 .exe
3. 安装后将 k6.exe 所在目录加入系统 PATH

### macOS

**通过 Homebrew（推荐）**
```bash
brew install k6
```

### Linux

**Debian / Ubuntu**
```bash
sudo apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
echo "deb https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update
sudo apt-get install k6
```

**CentOS / RHEL / Fedora**
```bash
sudo yum install https://dl.k6.io/rpm/repo.rpm
sudo yum install k6
```

**Alpine**
```bash
apk add k6
```

**通过 npm（跨平台）**
```bash
npm install -g k6
```

### Docker

```bash
docker run --rm -i grafana/k6 run - <scripts/smoke_test.js
```

### 验证安装

```bash
k6 version
```

## 运行测试

### 烟雾测试 (Smoke Test)

快速验证核心 API 的基本可用性：

```bash
# 默认地址 http://localhost:8001
k6 run deploy/k6/scripts/smoke_test.js

# 指定目标地址
k6 run -e BASE_URL=http://localhost:8001 deploy/k6/scripts/smoke_test.js
```

### 压力测试 (Stress Test)

评估系统在高并发下的性能表现：

```bash
# 基本运行
k6 run deploy/k6/scripts/stress_test.js

# 带详细百分位统计
k6 run --summary-trend-stats="min,avg,med,p(50),p(95),p(99),max" \
  deploy/k6/scripts/stress_test.js

# 指定目标地址和账号
k6 run -e BASE_URL=http://staging.example.com \
  -e TEST_USER=testuser \
  -e TEST_PASS=testpass \
  deploy/k6/scripts/smoke_test.js
```

### 输出 JSON 报告

```bash
k6 run --summary-export=deploy/k6/results/report.json deploy/k6/scripts/smoke_test.js
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `BASE_URL` | `http://localhost:8001` | 被测服务地址 |
| `TEST_USER` | `admin` | 测试用户名（仅 smoke_test） |
| `TEST_PASS` | `password123` | 测试密码（仅 smoke_test） |
