@echo off
setlocal

REM Wrapper to start Lake Shore logger on Windows
REM Uses a specific Python interpreter and default settings

REM Adjust these paths as needed for your system
set "PY=C:\Users\qris\winPython\WPy64-31241\python-3.12.4.amd64\python.exe"
set "DB=C:\Users\qris\py_automations\data_log\master-log.sqlite3"
set "INTERVAL=15"

REM Export configuration for logger.py
set "LAKESHORE_DB=%DB%"
set "LAKESHORE_INTERVAL=%INTERVAL%"

"%PY%" "%~dp0logger.py" %*

endlocal

