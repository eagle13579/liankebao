@echo off
REM ============================================================
REM 链客宝 PostgreSQL 启动脚本
REM 适用于 Windows 本地开发环境
REM ============================================================
echo.
echo ========================================
echo  链客宝 PostgreSQL 数据库启动脚本
echo ========================================
echo.

REM 切换到 deploy 目录
cd /d D:\链客宝\deploy

REM 启动 PostgreSQL 容器
echo [1/2] 启动 PostgreSQL 容器...
docker compose -f docker-compose.postgres.yml up -d

if %ERRORLEVEL% neq 0 (
    echo [!] Docker Compose 启动失败！
    pause
    exit /b 1
)

echo [2/2] 等待数据库就绪...
timeout /t 10 /nobreak >nul

REM 验证连接
echo.
echo 验证连接...
docker exec chainke-postgres pg_isready -U chainke -d chainke

if %ERRORLEVEL% equ 0 (
    echo.
    echo [OK] PostgreSQL 已就绪！
    echo.
    echo 连接信息:
    echo   Host:     localhost
    echo   Port:     5432
    echo   User:     chainke
    echo   Password: Chainke888!
    echo   Database: chainke
    echo.
    echo 辅助数据库:
    echo   CRM:    localhost:5433/chainke_crm
    echo   Growth: localhost:5434/chainke_growth
) else (
    echo [!] PostgreSQL 尚未就绪，请稍后检查
)

echo.
pause
