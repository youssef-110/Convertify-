@echo off
rem Removes the right-click menu, Send To and Start Menu entries. Your files are not touched.
cd /d "%~dp0"
".venv\Scripts\python.exe" shell.py uninstall
echo You can now delete this folder.
pause
