@echo off
REM 큐브포스 로컬 수집기 실행 래퍼 (서버노트북 작업 스케줄러용)
REM 로그: repo 루트의 cubepos_local.log (UTF-8)
chcp 65001 >nul
REM 리다이렉트 시에도 파이썬 stdout/stderr을 UTF-8로 강제(안 하면 cp949로 깨짐)
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0.."
py scripts\cubepos_local.py >> "%~dp0..\cubepos_local.log" 2>&1
