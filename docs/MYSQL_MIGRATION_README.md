# ============================================================
# 链客宝 MySQL 迁移就绪检查清单
# 生成日期: 2026-05-27
# 目标: 从 SQLite 迁移到 MySQL 8.0 (localhost:3306)
# ============================================================

## 现状

- MySQL 8.0 运行状态: ✅ (mysqladmin ping: alive)
- 数据库 liankebao 已创建: ✅ (CREATE DATABASE IF NOT EXISTS liankebao)
- MySQL 用户 liankebao 已创建: ✅ (密码: CHANGE_ME_PLEASE)
- Alembic 迁移框架已配置: ✅
- 现有迁移版本: 2 个 (initial_schema, add_soft_delete_fields)
- 迁移脚本已就绪: ✅ (one_click_migrate.py, migrate_to_mysql.py)

## 迁移步骤 (SQLite → MySQL)

### 1. 设置 MySQL 连接信息

推荐创建一个安全的环境变量文件:

```bash
# /var/www/liankebao/backend/.env.mysql
DB_TYPE=mysql
DATABASE_URL=mysql+pymysql://liankebao:CHANGE_ME_PLEASE@127.0.0.1:3306/liankebao?charset=utf8mb4
```

⚠️ 请先修改 MySQL 用户密码:
```sql
ALTER USER 'liankebao'@'localhost' IDENTIFIED BY '你的安全密码';
FLUSH PRIVILEGES;
```

### 2. 执行一键迁移

```bash
cd /var/www/liankebao/backend
python scripts/one_click_migrate.py --to mysql -y
```

### 3. 验证数据一致性

```bash
python scripts/one_click_migrate.py --to mysql --verify-only
```

### 4. 切换应用数据库

修改后端 .env 文件:
```bash
# backend/.env
DB_TYPE=mysql
DATABASE_URL=mysql+pymysql://liankebao:你的密码@127.0.0.1:3306/liankebao?charset=utf8mb4
BACKEND_PORT=8001
```

### 5. 重启后端服务

```bash
sudo systemctl restart chainke
sudo journalctl -u chainke -n 50 --no-pager
```

### 6. 回滚方案

如需切回 SQLite，修改 .env 中:
```bash
DB_TYPE=sqlite
```

并重启后端即可。所有 SQLite 数据保留在 backend/data/chainke.db。

## Alembic 迁移管理

### 生成新的迁移版本
```bash
cd /var/www/liankebao/backend
alembic revision --autogenerate -m "描述变更"
```

### 应用迁移
```bash
alembic upgrade head
```

### 回滚迁移
```bash
alembic downgrade -1
```

### 查看状态
```bash
alembic current
alembic history
```

## 注意事项

1. ⚠️ **生产环境迁移前请先备份 SQLite 数据库:**
   ```bash
   cp /var/www/liankebao/backend/data/chainke.db /var/www/liankebao/backend/data/chainke.db.bak
   ```

2. MySQL 连接默认使用 pymysql (已在 requirements.txt 中)

3. 迁移不会删除 SQLite 数据，可以随时切回

4. 大表迁移建议在低峰期进行

5. 迁移后建议在 Nginx 或应用层检查 API 响应是否正常
