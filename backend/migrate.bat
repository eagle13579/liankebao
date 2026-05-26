@echo off
REM ============================================================
REM 链客宝 一键数据库迁移 — Windows CMD/PowerShell
REM ============================================================
REM 用法:
REM   migrate.bat mysql    — 迁移到 MySQL
REM   migrate.bat postgres — 迁移到 PostgreSQL
REM   migrate.bat verify mysql    — 仅校验 MySQL
REM   migrate.bat verify postgres — 仅校验 PostgreSQL
REM ============================================================

setlocal enabledelayedexpansion

REM 获取脚本所在目录（backend/）
set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR%.."
cd /d "%PROJECT_DIR%"

REM 检查 Python
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo 错误: 未找到 Python，请确保 Python 已安装并添加到 PATH
    exit /b 1
)

REM 解析参数
set "MODE=migrate"
set "TARGET=%1"

if "%1"=="verify" (
    set "MODE=verify"
    set "TARGET=%2"
)

if "%TARGET%"=="" (
    echo ============================================================
    echo 链客宝 一键数据库迁移工具
    echo ============================================================
    echo.
    echo 用法:
    echo   migrate.bat mysql        迁移到 MySQL
    echo   migrate.bat postgres     迁移到 PostgreSQL
    echo   migrate.bat verify mysql  仅校验 MySQL
    echo.
    echo 环境变量配置:
    echo   MySQL: 设置 DATABASE_URL
    echo   PostgreSQL: 设置 PG_HOST PG_USER PG_PASSWORD PG_DATABASE
    echo.
    echo 示例:
    echo   set DATABASE_URL=mysql+pymysql://root:pass@localhost:3306/chainke?charset=utf8mb4
    echo   migrate.bat mysql
    echo ============================================================
    exit /b 1
)

echo ============================================================
echo 链客宝 SQLite ^-> %TARGET% 迁移
echo 模式: %MODE%
echo 项目目录: %PROJECT_DIR%
echo ============================================================
echo.

if "%MODE%"=="verify" (
    python scripts/one_click_migrate.py --to %TARGET% --verify-only
) else (
    python scripts/one_click_migrate.py --to %TARGET%
)

if %ERRORLEVEL% neq 0 (
    echo.
    echo 迁移执行失败，请检查上方错误信息。
    exit /b 1
)

echo.
echo 执行成功!
exit /b 0
