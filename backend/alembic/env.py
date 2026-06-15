from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app.models  # noqa: F401 - ensure all models are registered
from app.database import DB_TYPE, Base

# 注册多租户模型（仅 PostgreSQL 模式）
if DB_TYPE == "postgres":
    import app.tenant  # noqa: F401

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def get_url():
    """从应用配置获取数据库 URL"""
    if DB_TYPE == "postgres":
        PG_URL = os.environ.get("PG_URL", "")
        if PG_URL:
            return PG_URL
        PG_HOST = os.environ.get("PG_HOST", "localhost")
        PG_PORT = os.environ.get("PG_PORT", "5432")
        PG_USER = os.environ.get("PG_USER", "")
        PG_PASSWORD = os.environ.get("PG_PASSWORD", "")
        PG_DATABASE = os.environ.get("PG_DATABASE", "")
        if all([PG_USER, PG_PASSWORD, PG_DATABASE]):
            return f"postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DATABASE}"
    # Fallback to ini or SQLite
    return config.get_main_option("sqlalchemy.url")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    # Override sqlalchemy.url with the runtime URL
    url = get_url()
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = url

    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
