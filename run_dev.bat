@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo TreeTranslate virtual environment not found.
    echo Expected: %CD%\.venv\Scripts\python.exe
    pause
    exit /b 1
)

".venv\Scripts\python.exe" main.py
set "TREETRANSLATE_EXIT_CODE=%ERRORLEVEL%"

if not "%TREETRANSLATE_EXIT_CODE%"=="0" (
    echo.
    echo TreeTranslate exited with code %TREETRANSLATE_EXIT_CODE%.
    pause
)

exit /b %TREETRANSLATE_EXIT_CODE%
