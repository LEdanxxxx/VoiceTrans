@echo off
chcp 65001 >nul
cd /d E:\VoiceTrans

set PYTHON=E:\Marvis\MarvisAgent\1.0.1100.150\runtime\python311\python.exe

if not exist "%PYTHON%" (
    set PYTHON=D:\RuanJian\python\python.exe
)

if not exist "%PYTHON%" (
    echo [错误] 未找到 Python 解释器
    pause
    exit /b 1
)

echo 正在检查依赖...
"%PYTHON%" -c "import faster_whisper, requests, numpy" >nul 2>&1
if %errorlevel% neq 0 (
    echo 正在安装依赖，请稍候...
    "%PYTHON%" -m pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [错误] 依赖安装失败
        pause
        exit /b 1
    )
)

echo 正在启动 VoiceTrans...
start "" "%PYTHON%" main.py
exit