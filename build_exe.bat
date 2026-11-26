@echo off
rem Genera dist\Pescaclip.exe con PyInstaller, con FFmpeg y FFprobe incluidos (no hace falta instalarlos).
cd /d "%~dp0"
set "FF="
for /f "delims=" %%F in ('where ffmpeg 2^>nul') do if not defined FF set "FF=%%~dpF"
if not defined FF (echo No se encuentra FFmpeg. Instalalo con: winget install Gyan.FFmpeg & exit /b 1)
if not exist ".venv\Scripts\python.exe" python -m venv .venv
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt pyinstaller || exit /b 1
rem Las DLL solo existen en las compilaciones "shared" de FFmpeg; en las estaticas el comodin no encuentra nada.
set "DLLS="
if exist "%FF%*.dll" set DLLS=--add-binary "%FF%*.dll;ffmpeg"
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --onefile --windowed --name Pescaclip ^
    --collect-all yt_dlp_ejs --add-binary "%FF%ffmpeg.exe;ffmpeg" --add-binary "%FF%ffprobe.exe;ffmpeg" %DLLS% ^
    app.py || exit /b 1
echo.
echo Listo: dist\Pescaclip.exe
