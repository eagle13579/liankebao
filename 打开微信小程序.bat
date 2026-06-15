@echo off
chcp 65001 >nul
echo ========================================
echo   链客宝AI微信小程序 - 开发者工具启动
echo ========================================
echo.
echo 正在打开微信开发者工具...
start "" "D:\微信web开发者工具\cli.bat" open --project "D:\链客宝AI\liankebao-miniapp"
echo.
echo 如果上面命令没反应，试试手动操作：
echo 1. 打开微信开发者工具
echo 2. 导入项目
echo 3. 目录: D:\链客宝AI\liankebao-miniapp
echo 4. AppID: wxb4f6d89904200fd2
echo.
pause
