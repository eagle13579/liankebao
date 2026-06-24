@echo off
REM ============================================================
REM 链客宝AI SQLite → PostgreSQL 一键迁移脚本 (Windows)
REM ============================================================
REM 用法:
REM   auto_migrate.bat              — 完整迁移: 建表+数据迁移+验证
REM   auto_migrate.bat --verify     — 仅验证数据一致性
REM   auto_migrate.bat --dry-run    — 预览迁移内容，不实际写入
REM   auto_migrate.bat --truncate   — 迁移前清空 PG 表
REM ============================================================

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"
echo ============================================================
echo  链客宝AI SQLite → PostgreSQL 迁移
echo  时间: %DATE% %TIME%
echo  目录: %CD%
echo ============================================================
echo.

REM 检查 Python
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [错误] 未找到 Python，请确保已安装并添加到 PATH
    exit /b 1
)

REM 检查环境变量
if "%PG_HOST%"=="" set "PG_HOST=localhost"
if "%PG_PORT%"=="" set "PG_PORT=5432"
if "%PG_USER%"=="" set "PG_USER=chainke"
if "%PG_PASSWORD%"=="" set "PG_PASSWORD=chainke_pg_2026"
if "%PG_DATABASE%"=="" set "PG_DATABASE=chainke"

echo [信息] PostgreSQL 目标: %PG_USER%@%PG_HOST%:%PG_PORT%/%PG_DATABASE%
echo [信息] 使用 Python: 
python --version
echo.

REM 步骤 1: 检查 PG 连接
echo [步骤 1/4] 检查 PostgreSQL 连接...
python scripts/check_pg_connection.py
if %ERRORLEVEL% neq 0 (
    echo [错误] PostgreSQL 连接失败，请检查 PG 服务是否运行
    exit /b 1
)
echo.

REM 步骤 2: Alembic 迁移（生成 PG 表结构）
echo [步骤 2/4] 执行 Alembic 迁移（建表）...
set DB_TYPE=postgres
set USE_POSTGRES=1
alembic upgrade head
if %ERRORLEVEL% neq 0 (
    echo [警告] Alembic 迁移部分失败，尝试直接通过 SQLAlchemy 创建表...
    python -c "
import os
os.environ['DB_TYPE'] = 'postgres'
os.environ['USE_POSTGRES'] = '1'
from app.database import engine, Base
import app.models
Base.metadata.create_all(bind=engine)
print('表结构创建完成')
"
)
echo.

REM 步骤 3: 数据迁移
echo [步骤 3/4] 迁移数据从 SQLite 到 PostgreSQL...
set "PYTHONPATH=%CD%;%PYTHONPATH%"
python data_migration.py %*
if %ERRORLEVEL% neq 0 (
    echo [错误] 数据迁移失败
    exit /b 1
)
echo.

REM 步骤 4: 验证
echo [步骤 4/4] 验证数据一致性...
python data_migration.py --verify
if %ERRORLEVEL% neq 0 (
    echo [警告] 验证发现不一致，请检查上方详情
) else (
    echo [成功] 所有表数据一致！
)

echo.
echo ============================================================
echo  迁移完成报告
echo ============================================================
echo  源数据库: SQLite (backend/data/chainke.db)
echo  目标数据库: PostgreSQL (%PG_HOST%:%PG_PORT%/%PG_DATABASE%)
echo  时间: %DATE% %TIME%
echo.
echo  后续切换:
echo   - 切换到 PG: 设置 USE_POSTGRES=1 (或 DB_TYPE=postgres)
echo   - 切换回 SQLite: 设置 USE_POSTGRES=0 (或删除该变量)
echo ============================================================

endlocal
exit /b 0
