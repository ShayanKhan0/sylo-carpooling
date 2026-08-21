@echo off
echo ================================================================================
echo SmartCarpoolingApp Backend - Quick Verification
echo ================================================================================
echo.

cd /d "%~dp0"

echo Testing backend...
.\.venv\Scripts\python.exe comprehensive_test.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ================================================================================
    echo SUCCESS! Backend is ready for use.
    echo ================================================================================
    echo.
    echo To start the server:
    echo   .\.venv\Scripts\uvicorn app.main:app --reload
    echo.
    echo API Documentation:
    echo   http://localhost:8000/docs
    echo.
) else (
    echo.
    echo ================================================================================
    echo FAILED! Please check errors above.
    echo ================================================================================
)

pause
