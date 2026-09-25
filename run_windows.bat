@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -3.12 -c "import sys" >nul 2>&1
if not errorlevel 1 (
  py -3.12 -X utf8 "%~dp0run_all.py" %*
  goto finish
)
py -3.13 -c "import sys" >nul 2>&1
if not errorlevel 1 (
  py -3.13 -X utf8 "%~dp0run_all.py" %*
  goto finish
)
python -X utf8 "%~dp0run_all.py" %*
:finish
set "result=%errorlevel%"
if not "%result%"=="0" echo 运行未完成。请查看上方错误；需要64位Python 3.12或3.13，首次安装依赖需联网。
pause
exit /b %result%
