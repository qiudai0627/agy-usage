@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==^> 正在启动 Antigravity 实时用量监控台与桌面小工具...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
if errorlevel 1 (
    echo.
    echo [提示] 请确认本机已安装 Python 3.9+ 并勾选 Add Python to PATH。
    pause
)
