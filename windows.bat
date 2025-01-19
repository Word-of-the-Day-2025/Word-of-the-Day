@echo off
setlocal

REM Change directory to the src folder
cd %~dp0

REM Set the path to the dat directory
set DAT_DIR=%~dp0dat

REM Set the path to the BIN directory
set BIN_DIR=%~dp0BIN

REM Run the main application (Word of the Day bot)
python src\main.py

endlocal
pause