"""Pruebas sin Internet: genera clips con FFmpeg y los pasa por el mismo flujo que usa la aplicación.
Ejecutar:  .venv\\Scripts\\python test_local.py
"""
import hashlib
import os
import pathlib
import subprocess
import tempfile
import threading
import time

import core


def make_clip(path, seconds, size, vcodec, acodec):
    subprocess.run([core.FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=30:duration={seconds}",
                    "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                    "-c:v", vcodec, "-c:a", acodec, "-shortest", path], check=True)


def streams(path):
    return sorted({k for k, _ in core.probe(path)[0]}), core.probe(path)[0]


def run(src, target, dest, height=None, bitrate=192, cancel=None, phases=None):
    info = core.analyze(pathlib.Path(src).as_uri(), enable_file_urls=True)
    info["title"] = "Clip de prueba: ñandú/á"  # comprueba también el saneado del nombre
    cancel = cancel or threading.Event()
    rep = (lambda ph, pct, txt: phases.append((ph, pct))) if phases is not None else (lambda *a: None)
    return core.download(info, target, height, bitrate, dest, cancel, rep, enable_file_urls=True)


def md5(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()


def test_urls():
    n = core.normalize_youtube_url
    ok = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    for u in ["https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL123&index=4",
              "youtu.be/dQw4w9WgXcQ?si=abc", "https://youtube.com/shorts/dQw4w9WgXcQ",
              "https://m.youtube.com/watch?feature=x&v=dQw4w9WgXcQ", "https://www.youtube.com/embed/dQw4w9WgXcQ"]:
        assert n(u) == ok, u
    for bad in ["", "https://vimeo.com/123", "https://www.youtube.com/playlist?list=PL1", "https://youtu.be/abc"]:
        try:
            n(bad)
            raise AssertionError("debería fallar: " + bad)
        except core.UserError:
            pass
    assert "conexión" in core.explain_error(Exception("ERROR: Unable to download webpage: <urlopen error [Errno 11001] getaddrinfo failed>"))
    assert "no está disponible" in core.explain_error(Exception("ERROR: [youtube] x: Video unavailable"))
    print("OK  enlaces y mensajes de error")


def main():
    test_urls()
    work = tempfile.mkdtemp(prefix="ytprueba-")
    dest = os.path.join(work, "destino")
    os.mkdir(dest)
    webm = os.path.join(work, "fuente_vp9.webm")
    mp4 = os.path.join(work, "fuente_h264.mp4")
    make_clip(webm, 5, "640x360", "libvpx-vp9", "libopus")
    make_clip(mp4, 5, "640x360", "libx264", "aac")

    # MP3
    phases = []
    mp3 = run(webm, "MP3", dest, bitrate=320, phases=phases)
    kinds, raw = streams(mp3)
    assert kinds == ["audio"] and raw[0][1] == "mp3", raw
    assert [p for p, _ in phases][-1] == "Completado" and {"Descargando", "Convirtiendo"} <= {p for p, _ in phases}
    print("OK  MP3:", os.path.basename(mp3), raw)

    # MP4 desde VP9/Opus (recodifica a H.264/AAC) y desde H.264/AAC (copia)
    for src in (webm, mp4):
        out = run(src, "MP4", dest)
        kinds, raw = streams(out)
        assert kinds == ["audio", "video"] and ("video", "h264") in raw and ("audio", "aac") in raw, raw
        print("OK  MP4 desde", os.path.basename(src), raw)

    for target, codecs in (("M4A", {("audio", "aac")}), ("WAV", {("audio", "pcm_s16le")}),
                           ("WebM", {("video", "vp9"), ("audio", "opus")})):
        out = run(mp4 if target != "WebM" else webm, target, dest)
        assert set(core.probe(out)[0]) == codecs, core.probe(out)[0]
        print(f"OK  {target}:", core.probe(out)[0])

    # Mismo nombre: no sobrescribe; crea «(1)», «(2)»…
    before = md5(mp3)
    mp3b = run(webm, "MP3", dest, bitrate=128)
    assert mp3b != mp3 and mp3b.endswith("(1).mp3") and md5(mp3) == before, mp3b
    print("OK  repetir descarga:", os.path.basename(mp3b), "(el original no cambia)")

    # Cancelar durante la conversión (clip largo VP9 -> H.264 obliga a recodificar)
    long = os.path.join(work, "largo.webm")
    make_clip(long, 120, "1280x720", "libvpx-vp9", "libopus")
    existing = sorted(os.listdir(dest))
    hashes = {f: md5(os.path.join(dest, f)) for f in existing}
    cancel = threading.Event()
    seen = []

    def rep(ph, pct, txt):
        seen.append(ph)
        if ph == "Convirtiendo" and pct and pct > 3:
            cancel.set()
    info = core.analyze(pathlib.Path(long).as_uri(), enable_file_urls=True)
    info["title"] = "Clip de prueba: ñandú/á"
    t0 = time.time()
    try:
        core.download(info, "MP4", None, 192, dest, cancel, rep, enable_file_urls=True)
        raise AssertionError("no se canceló")
    except core.Cancelled:
        pass
    ffmpeg_alive = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ffmpeg.exe"], capture_output=True, text=True).stdout
    assert sorted(os.listdir(dest)) == existing, os.listdir(dest)  # sin temporales ni archivo parcial
    assert all(md5(os.path.join(dest, f)) == h for f, h in hashes.items())
    print(f"OK  cancelar durante la conversión en {time.time() - t0:.1f}s; carpeta intacta; "
          f"ffmpeg vivo: {'ffmpeg.exe' in ffmpeg_alive}")

    # Cancelar durante la descarga
    cancel = threading.Event()
    def rep2(ph, pct, txt):
        if ph == "Descargando":
            cancel.set()
    try:
        core.download(info, "MP3", None, 192, dest, cancel, rep2, enable_file_urls=True)
        raise AssertionError("no se canceló")
    except core.Cancelled:
        pass
    assert sorted(os.listdir(dest)) == existing
    print("OK  cancelar durante la descarga; carpeta intacta")

    # Carpeta inválida
    for bad in (os.path.join(work, "no_existe"), mp4):
        try:
            run(mp4, "MP3", bad)
            raise AssertionError("debería fallar")
        except core.UserError as e:
            print("OK  carpeta inválida ->", e)
    print("\nTodas las pruebas locales han pasado. Archivos en:", dest)


if __name__ == "__main__":
    main()
