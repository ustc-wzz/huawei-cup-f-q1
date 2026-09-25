@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -3 -c "import sys; sys.exit(sys.version_info[:2] < (3,8))" >nul 2>&1
if not errorlevel 1 (
  py -3 -X utf8 "%~dp0run_all.py" %*
  goto finish
)
python -c "import sys; sys.exit(sys.version_info[:2] < (3,8))" >nul 2>&1
if not errorlevel 1 (
  python -X utf8 "%~dp0run_all.py" %*
  goto finish
)
echo 请先安装可用的Python 3.8或更新版本。复现所需环境会自动准备。
pause
exit /b 1
:finish
set "result=%errorlevel%"
if not "%result%"=="0" echo 运行未完成，请查看上方错误。首次准备环境需要联网，修复后可重复运行。
pause
exit /b %result%
