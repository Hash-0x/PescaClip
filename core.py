"""Lógica sin interfaz: validar enlaces, analizar, descargar y convertir."""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import parse_qs, urlparse

import yt_dlp
from yt_dlp.utils import sanitize_filename

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
MAX_HEIGHT = 1080
AUDIO_FORMATS = ("MP3", "M4A", "WAV")
VIDEO_FORMATS = ("MP4", "WebM")
MP3_BITRATES = (128, 192, 320)
EXT = {"MP3": "mp3", "M4A": "m4a", "WAV": "wav", "MP4": "mp4", "WebM": "webm"}
VIDEO_PREF = {"MP4": ("avc1", "h264"), "WebM": ("vp9", "vp09", "av01")}
AUDIO_PREF = {"MP4": ("mp4a", "aac"), "M4A": ("mp4a", "aac"), "WebM": ("opus", "vorbis")}
YT_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


class Cancelled(Exception):
    pass


class UserError(Exception):
    """Error con un mensaje en español listo para mostrar."""


# ---------- FFmpeg ----------

def _find_tool(name):
    # Orden: incluido en el .exe, junto al .exe/script, y por último el PATH.
    base = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
    for d in (os.path.join(getattr(sys, "_MEIPASS", base), "ffmpeg"), base):
        if os.path.isfile(os.path.join(d, name + ".exe")):
            return os.path.join(d, name + ".exe")
    return shutil.which(name)


FFMPEG = _find_tool("ffmpeg")
FFPROBE = _find_tool("ffprobe")


def missing_tools():
    return [n for n, p in (("FFmpeg", FFMPEG), ("FFprobe", FFPROBE)) if not p]


def probe(path):
    """Devuelve (streams, duración) usando FFprobe. streams = [(tipo, códec), ...]."""
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "stream=codec_type,codec_name:format=duration",
         "-of", "json", path],
        capture_output=True, text=True, creationflags=NO_WINDOW)
    if out.returncode:
        raise UserError("FFprobe no pudo leer el archivo descargado.")
    data = json.loads(out.stdout)
    streams = [(s.get("codec_type"), s.get("codec_name")) for s in data.get("streams", [])]
    try:
        duration = float(data.get("format", {}).get("duration"))
    except (TypeError, ValueError):
        duration = None
    return streams, duration


# ---------- Enlaces y errores ----------

def normalize_youtube_url(text):
    """Acepta watch, youtu.be, shorts, embed y live; descarta la lista y devuelve un enlace canónico."""
    text = (text or "").strip()
    if not text:
        raise UserError("Pega un enlace de YouTube.")
    if not re.match(r"^https?://", text, re.I):
        text = "https://" + text
    u = urlparse(text)
    host = (u.hostname or "").lower()
    parts = [p for p in u.path.split("/") if p]
    vid = None
    if host in ("youtu.be", "www.youtu.be"):
        vid = parts[0] if parts else None
    elif host in YT_HOSTS:
        if parts[:1] == ["watch"]:
            vid = parse_qs(u.query).get("v", [None])[0]
        elif parts[:1] and parts[0] in ("shorts", "embed", "live", "v") and len(parts) > 1:
            vid = parts[1]
        elif parts[:1] == ["playlist"]:
            raise UserError("Es el enlace de una lista, no de un vídeo. Abre el vídeo que quieras y copia su enlace.")
    else:
        raise UserError("El enlace no es de YouTube. Usa un enlace de youtube.com o youtu.be.")
    if not vid or not _VIDEO_ID.match(vid):
        raise UserError("No se encuentra el identificador del vídeo en el enlace. Comprueba que esté completo.")
    return f"https://www.youtube.com/watch?v={vid}"


_ERRORS = [
    (("not a bot",), "YouTube pide verificar que no eres un bot. Espera un rato e inténtalo de nuevo."),
    (("private video",), "El vídeo es privado."),
    (("confirm your age", "age-restricted", "age restricted", "inappropriate for some users"),
     "El vídeo tiene restricción de edad y exige iniciar sesión. Esta aplicación no usa cuentas."),
    (("members-only", "join this channel", "members only"), "El vídeo es solo para miembros del canal."),
    (("drm",), "El vídeo está protegido con DRM y no se puede descargar."),
    (("live event will begin", "premieres in", "is upcoming"), "El vídeo aún no se ha estrenado."),
    (("video unavailable", "has been removed", "not available", "unavailable", "does not exist", "http error 404"),
     "El vídeo no está disponible: puede haber sido eliminado, ser privado o estar bloqueado en tu país."),
    (("http error 403",), "YouTube ha rechazado la descarga (error 403). Prueba a actualizar yt-dlp."),
    (("getaddrinfo", "urlopen error", "timed out", "timeout", "connection", "network", "unable to download",
      "failed to resolve", "name resolution", "ssl", "unreachable"),
     "No se pudo conectar con YouTube. Revisa tu conexión a Internet e inténtalo de nuevo."),
    (("unsupported url", "is not a valid url"), "El enlace no es válido."),
]


def explain_error(exc):
    low = str(exc).lower()
    for keys, msg in _ERRORS:
        if any(k in low for k in keys):
            return msg
    return "No se pudo procesar el vídeo: " + re.sub(r"^ERROR:\s*(\[[^\]]+\]\s*)?", "", str(exc))[:300]


# ---------- yt-dlp ----------

class _QuietLogger:
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


def _ydl_opts(**extra):
    opts = dict(quiet=True, no_warnings=True, noprogress=True, noplaylist=True, logger=_QuietLogger(),
                socket_timeout=20, retries=3, fixup="never", color="no_color",
                # Node suele estar instalado en Windows; deno es el predeterminado de yt-dlp.
                js_runtimes={"deno": {}, "node": {}})
    opts.update(extra)
    return opts


def analyze(url, enable_file_urls=False):
    try:
        with yt_dlp.YoutubeDL(_ydl_opts(enable_file_urls=enable_file_urls)) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:  # yt-dlp lanza DownloadError y otros; todos se explican en español
        raise UserError(explain_error(e)) from e
    if info.get("_type") == "playlist":
        raise UserError("El enlace apunta a una lista. Copia el enlace de un vídeo concreto.")
    if info.get("is_live"):
        raise UserError("Es una emisión en directo; esta versión solo descarga vídeos ya publicados.")
    return info


def _usable(info):
    return [f for f in info.get("formats") or []
            if f.get("format_id") and f.get("ext") != "mhtml" and not f.get("has_drm")]


def video_heights(info):
    """Alturas disponibles hasta 1080p, de mayor a menor."""
    hs = {f["height"] for f in _usable(info) if f.get("vcodec") != "none" and f.get("height")}
    return sorted((h for h in hs if h <= MAX_HEIGHT), reverse=True)


def _starts(codec, prefixes):
    return bool(codec) and bool(prefixes) and codec.lower().startswith(prefixes)


def choose_formats(info, target, height=None):
    """Devuelve los format_id a descargar: [audio], [vídeo, audio] o [progresivo]."""
    fmts = _usable(info)
    audio_only = [f for f in fmts if f.get("vcodec") == "none" and f.get("acodec") != "none"]
    apref = AUDIO_PREF.get(target, ())
    # Estéreo, sin DRC (volumen comprimido) y por HTTPS antes que 5.1/HLS; luego el códec que evita recodificar.
    https = lambda f: f.get("protocol") in ("https", "http", "file")
    akey = lambda f: ((f.get("audio_channels") or 2) <= 2, "drc" not in f["format_id"], https(f),
                      _starts(f.get("acodec"), apref), f.get("abr") or f.get("tbr") or 0)
    if target in AUDIO_FORMATS:
        pool = audio_only or [f for f in fmts if f.get("acodec") != "none"]
        if not pool:
            raise UserError("El vídeo no tiene ninguna pista de audio disponible.")
        return [max(pool, key=akey)["format_id"]]

    vpref = VIDEO_PREF[target]
    fits = (lambda f: f.get("height") == height) if height else (lambda f: (f.get("height") or 0) <= MAX_HEIGHT)
    vkey = lambda f: (f.get("height") or 0, _starts(f.get("vcodec"), vpref), https(f), _starts(f.get("acodec"), apref),
                      f.get("fps") or 0, f.get("tbr") or 0)
    video_only = [f for f in fmts if f.get("acodec") == "none" and f.get("vcodec") != "none" and fits(f)]
    if video_only and audio_only:
        return [max(video_only, key=vkey)["format_id"], max(audio_only, key=akey)["format_id"]]
    muxed = [f for f in fmts if f.get("acodec") != "none" and f.get("vcodec") != "none" and fits(f)]
    if muxed:
        return [max(muxed, key=vkey)["format_id"]]
    raise UserError("No hay formatos de vídeo disponibles con esa calidad.")


# ---------- Nombres de archivo ----------

def safe_basename(title):
    name = sanitize_filename(title or "", restricted=False).strip(" .")
    return name[:150].strip(" .") or "video"


def unique_path(folder, base, ext):
    path = os.path.join(folder, f"{base}.{ext}")
    n = 1
    while os.path.exists(path):
        path = os.path.join(folder, f"{base} ({n}).{ext}")
        n += 1
    return path


# ---------- Conversión ----------

def build_ffmpeg_args(inputs, target, bitrate, out):
    """Elige copiar o recodificar según los códecs reales (FFprobe) de cada entrada."""
    video = audio = None
    for i, p in enumerate(inputs):
        for kind, codec in probe(p)[0]:
            if kind == "video" and video is None and codec not in ("mjpeg", "png"):
                video = (i, codec)
            elif kind == "audio" and audio is None:
                audio = (i, codec)
    args = [FFMPEG, "-hide_banner", "-nostdin", "-y", "-loglevel", "error"]
    for p in inputs:
        args += ["-i", p]
    if target in AUDIO_FORMATS:
        if not audio:
            raise UserError("El archivo descargado no contiene audio.")
        args += ["-map", f"{audio[0]}:a:0", "-vn", "-map_metadata", "-1"]
        if target == "MP3":
            args += ["-c:a", "libmp3lame", "-b:a", f"{bitrate}k", "-ac", "2"]
        elif target == "M4A":
            args += ["-c:a", "copy"] if audio[1] == "aac" else ["-c:a", "aac", "-b:a", "192k"]
        else:
            args += ["-c:a", "pcm_s16le"]
    else:
        if not video:
            raise UserError("El archivo descargado no contiene vídeo.")
        args += ["-map", f"{video[0]}:v:0"]
        if audio:
            args += ["-map", f"{audio[0]}:a:0"]
        if target == "MP4":
            args += ["-c:v", "copy"] if video[1] == "h264" else \
                ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"]
            if audio:
                args += ["-c:a", "copy"] if audio[1] == "aac" else ["-c:a", "aac", "-b:a", "192k"]
            args += ["-movflags", "+faststart"]
        else:
            args += ["-c:v", "copy"] if video[1] in ("vp9", "vp8", "av1") else \
                ["-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0", "-row-mt", "1", "-deadline", "good", "-cpu-used", "4"]
            if audio:
                args += ["-c:a", "copy"] if audio[1] in ("opus", "vorbis") else ["-c:a", "libopus", "-b:a", "160k"]
    args += ["-progress", "pipe:1", "-nostats", out]
    return args


def run_ffmpeg(args, duration, cancel, on_progress, log_path):
    with open(log_path, "wb") as log:
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=log, creationflags=NO_WINDOW)

        def watch():  # mata FFmpeg en cuanto se pide cancelar, aunque no haya salida nueva
            while proc.poll() is None:
                if cancel.wait(0.2):
                    proc.kill()
                    return
        threading.Thread(target=watch, daemon=True).start()
        for raw in proc.stdout:
            line = raw.decode("utf-8", "replace").strip()
            if line.startswith("out_time_us=") and duration:
                try:
                    on_progress(min(100.0, int(line.split("=", 1)[1]) / 1e6 / duration * 100))
                except ValueError:
                    pass
        proc.wait()
    if cancel.is_set():
        raise Cancelled()
    if proc.returncode:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            detail = f.read()[-400:].strip()
        raise UserError("FFmpeg no pudo convertir el archivo. " + detail)


def _rmtree(path):
    for _ in range(10):  # Windows puede tardar un instante en soltar los archivos de un proceso terminado
        shutil.rmtree(path, ignore_errors=True)
        if not os.path.exists(path):
            return
        time.sleep(0.3)


def download(info, target, height, bitrate, dest_dir, cancel, report, enable_file_urls=False):
    """Descarga y convierte. report(fase, porcentaje|None, texto). Devuelve la ruta final."""
    if not os.path.isdir(dest_dir):
        raise UserError(f"La carpeta de destino no existe: {dest_dir}")
    try:
        tmp = tempfile.mkdtemp(prefix=".descarga-", dir=dest_dir)
    except OSError:
        raise UserError(f"No hay permiso para escribir en la carpeta: {dest_dir}. Elige otra.")
    try:
        ids = choose_formats(info, target, height)
        labels = ["vídeo", "audio"] if len(ids) == 2 else ["audio" if target in AUDIO_FORMATS else "vídeo"]
        parts = []
        for k, fid in enumerate(ids):
            text = f"Descargando {labels[k]}" + (f" ({k + 1}/{len(ids)})" if len(ids) > 1 else "") + "…"
            report("Descargando", None, text)

            def hook(d, text=text):
                if cancel.is_set():
                    raise Cancelled()
                if d.get("status") == "downloading":
                    total = d.get("total_bytes") or d.get("total_bytes_estimate")
                    report("Descargando", d.get("downloaded_bytes", 0) * 100 / total if total else None, text)

            opts = _ydl_opts(format=fid, outtmpl=os.path.join(tmp, f"parte{k}.%(ext)s"), progress_hooks=[hook],
                             enable_file_urls=enable_file_urls, overwrites=True, continuedl=False)
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    # Reutiliza el análisis (como --load-info-json) en lugar de volver a pedirlo a YouTube.
                    ydl.process_ie_result(ydl.sanitize_info(info, True), download=True)
            except Exception as e:
                if cancel.is_set():
                    raise Cancelled()
                raise UserError(explain_error(e)) from e
            found = [p for p in glob.glob(os.path.join(tmp, f"parte{k}.*")) if not p.endswith((".part", ".ytdl"))]
            if not found:
                raise UserError("La descarga terminó sin generar ningún archivo.")
            parts.append(found[0])

        if cancel.is_set():
            raise Cancelled()
        ext = EXT[target]
        out = os.path.join(tmp, "salida." + ext)
        args = build_ffmpeg_args(parts, target, bitrate, out)
        duration = info.get("duration") or probe(parts[0])[1]
        report("Convirtiendo", None if not duration else 0, "Convirtiendo…")
        run_ffmpeg(args, duration, cancel, lambda p: report("Convirtiendo", p, "Convirtiendo…"),
                   os.path.join(tmp, "ffmpeg.log"))

        base = safe_basename(info.get("title"))
        while True:  # os.rename no sobrescribe en Windows: si alguien creó el nombre entretanto, probamos el siguiente
            final = unique_path(dest_dir, base, ext)
            try:
                os.rename(out, final)
                break
            except FileExistsError:
                continue
        report("Completado", 100, "Completado")
        return final
    finally:
        _rmtree(tmp)
