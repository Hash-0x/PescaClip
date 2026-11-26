# Avisos de terceros

El código de Pescaclip (`app.py`, `core.py` y scripts) tiene licencia [MIT](LICENSE).
El archivo `Pescaclip.exe` distribuido en las releases incluye además estos componentes, cada uno con su propia licencia.

## FFmpeg y FFprobe (GPL v3)

`Pescaclip.exe` incluye `ffmpeg.exe`, `ffprobe.exe` y sus DLL sin modificar.
Pescaclip los ejecuta como **programas independientes**; no forman parte de su código.

- Versión: 9.0.2, compilación «full shared» de [gyan.dev](https://www.gyan.dev/ffmpeg/builds/)
- Licencia: GNU GPL v3. Texto completo en [licenses/FFmpeg-GPLv3.txt](licenses/FFmpeg-GPLv3.txt)
- **Código fuente correspondiente:** https://github.com/FFmpeg/FFmpeg/commit/946fcce07b
- Configuración de la compilación y bibliotecas externas: [licenses/FFmpeg-build-info.txt](licenses/FFmpeg-build-info.txt)

Si necesitas el código fuente de esta versión exacta y no puedes obtenerlo en los enlaces anteriores, abre una *issue* en este repositorio y te lo facilitaremos durante al menos 3 años desde la publicación de la release.

## Bibliotecas de Python incluidas en el .exe

| Componente | Licencia |
|---|---|
| [Python](https://www.python.org) y Tcl/Tk | PSF License · licencia BSD de Tcl/Tk |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Unlicense (dominio público) |
| [yt-dlp-ejs](https://github.com/yt-dlp/ejs) | Unlicense, MIT e ISC |
| [requests](https://github.com/psf/requests) | Apache-2.0 |
| [urllib3](https://github.com/urllib3/urllib3), [charset-normalizer](https://github.com/jawah/charset_normalizer), [brotli](https://github.com/google/brotli) | MIT |
| [idna](https://github.com/kjd/idna), [websockets](https://github.com/python-websockets/websockets) | BSD-3-Clause |
| [certifi](https://github.com/certifi/python-certifi) | MPL-2.0 |
| [pycryptodomex](https://github.com/Legrandin/pycryptodome) | BSD / dominio público |
| [PyInstaller](https://pyinstaller.org) (cargador del .exe) | GPL v2 con excepción que permite distribuir los ejecutables con cualquier licencia |

## Otros

- La captura del README muestra el título de *Big Buck Bunny*, © Blender Foundation, con licencia [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/).
- «YouTube» es una marca de Google LLC. Pescaclip no está afiliado a YouTube ni a Google.
