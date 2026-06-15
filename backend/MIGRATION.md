# 链客宝AI 数据库迁移指南
# ============================================================

## 概述

链客宝AI默认使用 SQLite 数据库，支持迁移到 MySQL 或 PostgreSQL。
迁移后，只需修改环境变量 `DB_TYPE` 即可切换数据库，无需修改代码。

## 快速开始

### MySQL 迁移

1. 安装依赖：
   ```
   pip install pymysql
   ```

2. 设置环境变量：
   ```bash
   # Windows CMD
   set DB_TYPE=mysql
   set DATABASE_URL=mysql+pymysql://root:password@localhost:3306/chainke?charset=utf8mb4

   # Linux/Mac/WSL
   export DB_TYPE=mysql
   export DATABASE_URL=mysql+pymysql://root:password@localhost:3306/chainke?charset=utf8mb4
   ```

3. 执行迁移（推荐一键脚本）：
   ```bash
   # Windows
   migrate.bat mysql

   # Linux/Mac
   python scripts/one_click_migrate.py --to mysql
   ```

### PostgreSQL 迁移

1. 安装依赖：
   ```
   pip install psycopg2-binary
   ```

2. 设置环境变量：
   ```bash
   export DB_TYPE=postgres
   export PG_HOST=localhost
   export PG_PORT=5432
   export PG_USER=chainke_user
   export PG_PASSWORD=your_password
   export PG_DATABASE=chainke
   ```

3. 执行迁移：
   ```bash
   # Windows
   migrate.bat postgres

   # Linux/Mac
   python scripts/one_click_migrate.py --to postgres
   ```

## 迁移流程详解

一键迁移脚本自动完成以下步骤：

1. **数据源验证** — 检查 SQLite 源数据完整性
2. **创建目标表结构** — 在目标数据库创建表（含索引）
3. **数据迁移** — 批量逐表迁移（按外键依赖顺序）
4. **数据一致性校验** — 对比源/目标数据库的行数

## 单独使用各脚本

### migrate_to_mysql.py（增强版）

```bash
# 完整迁移
python scripts/migrate_to_mysql.py

# 仅校验数据一致性
python scripts/migrate_to_mysql.py --verify

# 自动化（跳过交互确认+跳过校验）
python scripts/migrate_to_mysql.py -y --skip-verify

# 跳过预验证（强制迁移）
python scripts/migrate_to_mysql.py --skip-validate --force
```

### migrate_to_postgres.py（增强版）

```bash
# 导出 SQLite → JSON
python scripts/migrate_to_postgres.py --export

# 导入 JSON → PostgreSQL
python scripts/migrate_to_postgres.py --import

# 导出 + 导入（一步）
python scripts/migrate_to_postgres.py --export --import -y

# 验证数据一致性
python scripts/migrate_to_postgres.py --verify
```

### one_click_migrate.py（推荐）

```bash
# MySQL 迁移
python scripts/one_click_migrate.py --to mysql

# PostgreSQL 迁移
python scripts/one_click_migrate.py --to postgres

# 仅验证（不迁移）
python scripts/one_click_migrate.py --to mysql --verify-only

# 自动化（非交互）
python scripts/one_click_migrate.py --to mysql -y
```

## 配置切换

迁移完成后，切换数据库使用方式：

### 方案 A：环境变量（推荐）

```bash
# 切换到 MySQL
set DB_TYPE=mysql
set DATABASE_URL=mysql+pymysql://user:pass@localhost:3306/chainke?charset=utf8mb4

# 切换到 PostgreSQL
set DB_TYPE=postgres
set PG_HOST=localhost  PG_USER=... PG_PASSWORD=... PG_DATABASE=...

# 切换回 SQLite
set DB_TYPE=sqlite
```

### 方案 B：生产部署（.env / systemd）

在环境配置文件或 systemd unit 中设置：

```
# /etc/systemd/system/chainke.service 的 [Service] 部分
Environment=DB_TYPE=mysql
Environment=DATABASE_URL=mysql+pymysql://user:pass@localhost:3306/chainke?charset=utf8mb4
```

## 文件结构

```
backend/
├── app/
│   ├── database.py           # [已增强] 统一数据库入口（DB_TYPE 自适应）
│   ├── database_mysql.py     # [已增强] MySQL 独立引擎
│   ├── database_postgres.py  # [已增强] PostgreSQL 独立引擎（含迁移函数）
│   └── models.py             # ORM 数据模型
├── scripts/
│   ├── one_click_migrate.py  # [新增] 一键迁移工具
│   ├── migrate_to_mysql.py   # [已增强] MySQL 迁移脚本
│   └── migrate_to_postgres.py # [已增强] PostgreSQL 迁移脚本
├── migrate.bat               # [新增] Windows 迁移快捷脚本
├── .env.example              # [新增] 环境变量配置示例
└── requirements.txt          # 依赖
```

## 数据校验说明

迁移脚本在迁移前后执行数据校验：

- **迁移前校验**：检查源表是否存在、必要列是否完整、记录数
- **迁移后校验**：对比源/目标数据库各表行数

### 校验内容

| 表名        | 核验项                     |
|-------------|---------------------------|
| users       | 行数、主键列完整性        |
| products    | 行数、主键列完整性        |
| orders      | 行数、外键完整性          |
| withdrawals | 行数、外键完整性          |

## 常见问题

**Q: 迁移失败，提示表已存在？**
A: 迁移脚本使用 `TRUNCATE` 清空目标表。如需追加模式，使用 `--no-truncate` 参数。

**Q: 迁移后数据量不一致？**
A: 运行 `python scripts/one_click_migrate.py --to mysql --verify-only` 验证差异。

**Q: 迁移后应用无法启动？**
A: 确认设置了 `DB_TYPE` 环境变量并指向正确的数据库。
