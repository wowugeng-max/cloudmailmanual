@echo off
setlocal
chcp 65001 >nul

cd /d "%~dp0"

echo ======================================
echo Cloud Mail Web 一键启动
echo ======================================

if not exist "config.json" (
  if exist "config.example.json" (
    copy /Y "config.example.json" "config.json" >nul
    echo [*] 已从 config.example.json 生成 config.json，请先填写管理员账号后再运行。
  ) else (
    echo [ERROR] 未找到 config.json 或 config.example.json
  )
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] 未找到 .venv\Scripts\python.exe
  echo [提示] 请先手动创建虚拟环境并安装依赖：
  echo        python -m venv .venv
  echo        .venv\Scripts\python -m pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)

echo [*] 检查关键依赖...
call ".venv\Scripts\python.exe" -c "import flask, requests" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] 检测到缺少依赖（flask/requests）。
  echo [提示] 请先执行：
  echo        .venv\Scripts\python -m pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)

echo.
if "%WEB_PORT%"=="" (
  echo [*] 启动 Web 服务（端口来自 config.json/web_port 或 APP_PORT/PORT，默认 5000）
  echo [*] 按 Ctrl+C 可停止服务
  echo.
  call ".venv\Scripts\python.exe" app.py --debug
) else (
  echo [*] 启动 Web 服务: http://127.0.0.1:%WEB_PORT%
  echo [*] 按 Ctrl+C 可停止服务
  echo.
  call ".venv\Scripts\python.exe" app.py --port %WEB_PORT% --debug
)

echo.
echo [*] 服务已退出。
pause
endlocal
