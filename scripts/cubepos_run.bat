@echo off
REM 큐브포스 로컬 수집기 실행 래퍼 (서버노트북 작업 스케줄러용)
REM 로그: repo 루트의 cubepos_local.log
chcp 65001 >nul
cd /d "%~dp0.."
py scripts\cubepos_local.py >> "%~dp0..\cubepos_local.log" 2>&1
