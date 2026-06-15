"""
密码重置功能 — 数据库迁移脚本
==============================
为 users 表添加 password_reset_token 和 password_reset_expires 字段。

SQLite:
  ALTER TABLE users ADD COLUMN password_reset_token TEXT;
  ALTER TABLE users ADD COLUMN password_reset_expires DATETIME;

MySQL:
  ALTER TABLE users ADD COLUMN password_reset_token VARCHAR(255) DEFAULT NULL;
  ALTER TABLE users ADD COLUMN password_reset_expires DATETIME DEFAULT NULL;

PostgreSQL:
  ALTER TABLE users ADD COLUMN password_reset_token VARCHAR(255) DEFAULT NULL;
  ALTER TABLE users ADD COLUMN password_reset_expires TIMESTAMP DEFAULT NULL;
"""
