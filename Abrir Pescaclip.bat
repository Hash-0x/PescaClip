@echo off
rem Doble clic para abrir la aplicación. La primera vez prepara el entorno de Python (necesita Internet).
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Preparando la aplicacion por primera vez...
    python -m venv .venv || (echo No se encuentra Python. Instalalo con: winget install Python.Python.3.13 & pause & exit /b 1)
    ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt || (echo Fallo al instalar dependencias. & pause & exit /b 1)
)
start "" ".venv\Scripts\pythonw.exe" app.py
