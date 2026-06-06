@echo off
chcp 65001 >nul
title VoiceTrans - 视频音频翻译工具
cd /d "%~dp0"
echo   VoiceTrans 启动中...
python -c "import faster_whisper, requests, numpy" >nul 2>&1
if errorlevel 1 (
    echo [安装依赖...]
    pip install -r requirements.txt
)
start "" python main.py
