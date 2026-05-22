# 链客宝 SSL/域名部署指南

> 域名: `www.liankebao.top` / `liankebao.top`
> 服务器: 阿里云 ECS, IP 47.100.160.250

---

## 1. DNS 解析验证

在配置 SSL 之前，确保域名已正确解析到服务器 IP：

```bash
# 检查 A 记录解析
dig liankebao.top A +short

# 检查 CNAME / www 子域名解析
dig www.liankebao.top A +short

# 使用 nslookup 验证
nslookup liankebao.top

# 查看完整 DNS 记录
dig liankebao.top ANY +noall +answer
```

预期输出应为：`47.100.160.250`

> **注意**：DNS 修改后需要等待生效（通常 10 分钟 ~ 24 小时）。可以使用 https://dnschecker.org 全球检查。

---

## 2. 阿里云安全组配置

登录阿里云 ECS 控制台，配置安全组规则：

| 安全组 ID | sg-uf6emb0g3ud0a5yrc2to |
|-----------|-------------------------|

### 添加入方向规则

| 协议 | 端口 | 授权对象 | 描述 |
|------|------|---------|------|
| TCP  | 80   | 0.0.0.0/0 | HTTP |
| TCP  | 443  | 0.0.0.0/0 | HTTPS |
| TCP  | 22   | 0.0.0.0/0 | SSH（建议限制IP） |

```bash
# 使用阿里云 CLI 添加规则（可选）
aliyun ecs AuthorizeSecurityGroup \
  --RegionId cn-shanghai \
  --SecurityGroupId sg-uf6emb0g3ud0a5yrc2to \
  --IpProtocol tcp \
  --PortRange 80/80 \
  --SourceCidrIp 0.0.0.0/0 \
  --Description "HTTP"

aliyun ecs AuthorizeSecurityGroup \
  --RegionId cn-shanghai \
  --SecurityGroupId sg-uf6emb0g3ud0a5yrc2to \
  --IpProtocol tcp \
  --PortRange 443/443 \
  --SourceCidrIp 0.0.0.0/0 \
  --Description "HTTPS"
```

> 查看当前规则：阿里云控制台 > ECS > 安全组 > sg-uf6emb0g3ud0a5yrc2to > 入方向

---

## 3. Nginx 配置检查

确保 nginx 已安装且运行中：

```bash
# 检查 nginx 状态
sudo systemctl status nginx

# 检查 nginx 配置
sudo nginx -t

# 重载配置
sudo nginx -s reload
```

确认 `nginx.conf` 中的 server_name 配置正确：

```nginx
server_name liankebao.top www.liankebao.top;
```

---

## 4. Certbot 一键申请 SSL 证书（Let's Encrypt）

### 安装 Certbot

```bash
# Ubuntu / Debian
sudo apt update
sudo apt install -y certbot python3-certbot-nginx

# CentOS / Rocky / Alibaba Cloud Linux
sudo yum install -y certbot python3-certbot-nginx
```

### 申请证书

```bash
# 一键申请 + 自动配置 nginx（推荐）
sudo certbot --nginx -d liankebao.top -d www.liankebao.top

# 如果只需申请证书（手动配置 nginx）
sudo certbot certonly --nginx -d liankebao.top -d www.liankebao.top
```

执行后按提示：
1. 输入邮箱（用于紧急续期通知）
2. 同意服务条款（A）
3. 选择是否将 HTTP 重定向到 HTTPS（推荐选 2）

### 成功后的效果

```
Congratulations! You have successfully enabled HTTPS!

https://liankebao.top
https://www.liankebao.top
```

证书文件位置：
- 证书: `/etc/letsencrypt/live/liankebao.top/fullchain.pem`
- 私钥: `/etc/letsencrypt/live/liankebao.top/privkey.pem`

---

## 5. 证书自动续期

Let's Encrypt 证书有效期为 90 天，需定期续期。

### 测试续期

```bash
# 模拟续期（不实际修改）
sudo certbot renew --dry-run
```

### 自动续期（已默认配置）

Certbot 安装后会在 `/etc/cron.d/certbot` 或 systemd timer 中添加自动续期任务。

```bash
# 检查定时任务
sudo systemctl list-timers | grep certbot
# 或
cat /etc/cron.d/certbot
```

手动强制续期：

```bash
sudo certbot renew
sudo nginx -s reload
```

> 建议每月手动检查一次：`sudo certbot renew --dry-run`

---

## 6. 验证 HTTPS

### 浏览器测试
- 访问 https://liankebao.top
- 访问 https://www.liankebao.top
- 检查地址栏的小锁标志 ✓

### CLI 测试
```bash
# 测试 HTTPS 可用性
curl -I https://liankebao.top

# 测试 HTTP 到 HTTPS 重定向
curl -I http://liankebao.top

# 测试 SSL 证书信息
openssl s_client -connect liankebao.top:443 -servername liankebao.top < /dev/null 2>/dev/null | openssl x509 -noout -dates
```

### 在线工具
- https://www.ssllabs.com/ssltest/analyze.html?d=liankebao.top
- https://check-your-website.aliyun.com

---

## 7. 本地测试方案（域名未解析时）

如果域名尚未完成 DNS 解析，可以通过修改 `hosts` 文件在本地测试。

### Windows
以管理员身份编辑 `C:\Windows\System32\drivers\etc\hosts`，添加：

```
47.100.160.250  liankebao.top
47.100.160.250  www.liankebao.top
```

### macOS / Linux
```bash
sudo nano /etc/hosts
# 添加：
47.100.160.250  liankebao.top
47.100.160.250  www.liankebao.top
```

### 生效后测试
```bash
ping liankebao.top
curl -I http://liankebao.top
```

> 测试完成后记得删除 hosts 中的测试条目，避免影响真实 DNS 解析。

---

## 8. 常见问题排查

| 问题 | 原因 | 解决 |
|------|------|------|
| certbot 报 DNS 解析失败 | 域名未解析到服务器 | 先确认 `dig` 返回正确 IP |
| 安全组 80/443 端口不通 | 安全组未添加规则 | 检查 sg-uf6emb0g3ud0a5yrc2to 入方向 |
| nginx 配置报 `server_name` 不匹配 | nginx.conf 域名配置错误 | 确认 `server_name` 包含两个域名 |
| 证书续期失败 | 端口 80 被占用 | 先停止占用 80 端口的服务 |
| HTTPS 访问显示不安全 | 证书链未完整 | 检查 `fullchain.pem` 是否包含中间证书 |
