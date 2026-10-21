@echo off
rem Optional: builds dist\Convertify\Convertify.exe (no Python needed to run it).
rem LibreOffice, Pandoc, FFmpeg and Tesseract are NOT bundled: they must still be installed.
cd /d "%~dp0"
".venv\Scripts\python.exe" -m pip install -q pyinstaller || exit /b 1
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --windowed --name Convertify ^
    --icon assets\icon.ico --add-data "assets;assets" ^
    --collect-submodules converters --hidden-import shell ^
    --collect-all tkinterdnd2 --collect-all sv_ttk --collect-all pdf2docx ^
    --collect-all pillow_heif --collect-all pymupdf ^
    gui.pyw || exit /b 1
echo.
echo Built: dist\Convertify\Convertify.exe
echo Open it and switch on "Show in right-click menu" to point the menu at the .exe.
pause
