@echo off
for /f %%i in ('find /v /c "" ^< "D:\chainke-full\顶层架构扫描与全球对标报告.md"') do set lines=%%i
echo Report line count: %lines%
