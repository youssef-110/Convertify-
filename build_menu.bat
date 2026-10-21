@echo off
rem Rebuilds the Windows 11 menu add-on (menu\ConvertifyMenu.dll) from menu\menu.cpp.
rem Needs MinGW-w64 g++ (e.g. from MSYS2). A prebuilt DLL is already included, so this is optional.
cd /d "%~dp0menu"
g++ -shared -O2 -static -s -o ConvertifyMenu.dll menu.cpp menu.def -lole32 -luuid -lshell32 -lshlwapi || exit /b 1
echo Built menu\ConvertifyMenu.dll. Run install.bat to register it.
