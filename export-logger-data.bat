@echo off
setlocal

REM Wrapper to export Lake Shore logger data to CSV on Windows

set "PY=C:\Users\qris\winPython\WPy64-31241\python-3.12.4.amd64\python.exe"

"%PY%" "%~dp0export_to_csv.py" %*

endlocal
