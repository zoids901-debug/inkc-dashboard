@echo off
:: 인크커피 야간 자동 수집 - Windows Task Scheduler 등록
:: 관리자 권한으로 실행하세요

set TASK_NAME=InkCoffee_Nightly
set NODE_PATH=C:\Program Files\nodejs\node.exe
set SCRIPT_PATH=C:\Users\zoids\inkc-dashboard\nightly.js
set RUN_TIME=23:30

echo [작업 등록 중...]

schtasks /create /tn "%TASK_NAME%" /tr "\"%NODE_PATH%\" \"%SCRIPT_PATH%\"" /sc daily /st %RUN_TIME% /ru "%USERNAME%" /f

if %errorlevel% == 0 (
    echo.
    echo [완료] 매일 %RUN_TIME%에 자동 실행됩니다.
    echo 작업 이름: %TASK_NAME%
    echo 스크립트: %SCRIPT_PATH%
) else (
    echo.
    echo [실패] 관리자 권한으로 다시 실행하세요.
)

pause
