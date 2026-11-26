# Pescaclip

Aplicación de escritorio para Windows 11 que guarda un vídeo de YouTube, o solo su audio, en MP3, M4A, WAV, MP4 o WebM.
Úsala solo con contenido propio o con permiso del titular. No usa cuentas, servidores ni telemetría, y no elude DRM ni restricciones.

## Requisitos

- **Python 3.10 o posterior**: `winget install Python.Python.3.13`
- **FFmpeg y FFprobe**: `winget install Gyan.FFmpeg`. Después cierra y vuelve a abrir la aplicación.
  Otra opción es copiar `ffmpeg.exe` y `ffprobe.exe` en la misma carpeta que la aplicación o que el `.exe`.
- Recomendado: **Node.js** o **Deno**. yt-dlp los usa para resolver los desafíos de YouTube; sin ellos puede haber menos calidades.

## Abrir la aplicación

Haz doble clic en **`Abrir Pescaclip.bat`**. La primera vez crea `.venv` e instala las dependencias de `requirements.txt` (hace falta Internet).

## Uso

1. Pega el enlace (normal, `youtu.be` o Shorts) y pulsa **Analizar**. Si el enlace incluye una lista, solo se usa el vídeo indicado.
2. Elige **Audio** (MP3 a 128, 192 o 320 kbps, M4A o WAV) o **Vídeo** (MP4 o WebM, hasta 1080p, sin reescalar).
3. Elige la carpeta. Por defecto es Descargas, y la aplicación recuerda la última que elegiste.
   Si ya existe un archivo con el mismo nombre, se crea «Título (1).ext» y el original no se toca.
4. Pulsa **Descargar**. **Cancelar** detiene la descarga y FFmpeg y borra los temporales.

En MP4 se priorizan H.264 y AAC. Las pistas que ya son compatibles se copian sin recodificar.

## Crear un .exe

Ejecuta `build_exe.bat`, que genera `dist\Pescaclip.exe` (un solo archivo de unos 200 MB, sin consola).
**FFmpeg y FFprobe van incluidos** en el .exe, así que quien lo reciba no tiene que instalar nada.
Para compilarlo, FFmpeg tiene que estar instalado en tu equipo.
El .exe tarda unos segundos en abrirse porque se descomprime.

## Pruebas

`.venv\Scripts\python test_local.py` genera clips con FFmpeg y prueba sin Internet:

- todos los formatos, comprobados con FFprobe;
- cancelar durante la descarga y durante la conversión;
- repetir una descarga con el mismo nombre;
- carpetas no válidas;
- validación de enlaces.

## Problemas frecuentes

- *Error 403 o «no eres un bot»*: actualiza yt-dlp con `.venv\Scripts\python -m pip install -U "yt-dlp[default]"`.
- Los vídeos con restricción de edad, privados o solo para miembros no se pueden descargar, porque la aplicación no inicia sesión.
