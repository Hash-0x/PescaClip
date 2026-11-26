"""Pescaclip: interfaz Tkinter. El trabajo pesado está en core.py y corre en hilos."""
import json
import os
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import core

APP_NAME = "Pescaclip"
CONFIG = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Pescaclip", "config.json")
FFMPEG_HELP = (
    "No se encuentra {faltan}. Hace falta para convertir los archivos.\n\n"
    "Para instalarlo en Windows 11:\n"
    "1. Abre PowerShell y ejecuta:\n      winget install Gyan.FFmpeg\n"
    "2. Cierra y vuelve a abrir esta aplicación.\n\n"
    "También puedes copiar ffmpeg.exe y ffprobe.exe en la misma carpeta que la aplicación.")


def downloads_dir():
    d = os.path.join(os.path.expanduser("~"), "Downloads")
    return d if os.path.isdir(d) else os.path.expanduser("~")


def load_config():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    try:
        os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
        with open(CONFIG, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False)
    except OSError:
        pass  # recordar la carpeta es una comodidad; no debe impedir usar la aplicación


def fmt_duration(sec):
    if not sec:
        return "desconocida"
    sec = int(sec)
    h, m, s = sec // 3600, sec // 60 % 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class App:
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()
        self.info = None
        self.cancel = None
        self.busy = False
        self.result = None
        cfg = load_config()
        folder = cfg.get("folder")
        self.folder = tk.StringVar(value=folder if folder and os.path.isdir(folder) else downloads_dir())

        root.title(APP_NAME)
        root.minsize(620, 0)
        main = ttk.Frame(root, padding=14)
        main.pack(fill="both", expand=True)
        main.columnconfigure(1, weight=1)

        ttk.Label(main, text="Enlace de YouTube").grid(row=0, column=0, sticky="w")
        self.url = tk.StringVar()
        self.url_entry = ttk.Entry(main, textvariable=self.url)
        self.url_entry.grid(row=0, column=1, sticky="ew", padx=6)
        self.url_entry.bind("<Return>", lambda e: self.analyze())
        self.btn_paste = ttk.Button(main, text="Pegar", command=self.paste)
        self.btn_paste.grid(row=0, column=2)
        self.btn_analyze = ttk.Button(main, text="Analizar", command=self.analyze)
        self.btn_analyze.grid(row=0, column=3, padx=(6, 0))

        self.msg = ttk.Label(main, text="Pega un enlace (normal, youtu.be o Shorts) y pulsa «Analizar».",
                             wraplength=580, foreground="#444")
        self.msg.grid(row=1, column=0, columnspan=4, sticky="w", pady=(8, 4))

        info = ttk.LabelFrame(main, text="Vídeo", padding=8)
        info.grid(row=2, column=0, columnspan=4, sticky="ew", pady=4)
        info.columnconfigure(1, weight=1)
        self.title_lbl = ttk.Label(info, text="—", wraplength=520)
        self.dur_lbl = ttk.Label(info, text="—")
        self.q_lbl = ttk.Label(info, text="—")
        for r, (name, w) in enumerate((("Título:", self.title_lbl), ("Duración:", self.dur_lbl),
                                       ("Calidades:", self.q_lbl))):
            ttk.Label(info, text=name).grid(row=r, column=0, sticky="nw", padx=(0, 6))
            w.grid(row=r, column=1, sticky="w")

        opts = ttk.LabelFrame(main, text="Formato", padding=8)
        opts.grid(row=3, column=0, columnspan=4, sticky="ew", pady=4)
        self.mode = tk.StringVar(value="Audio")
        self.fmt = tk.StringVar(value="MP3")
        self.bitrate = tk.StringVar(value="192 kbps")
        self.res = tk.StringVar()
        self.rb_audio = ttk.Radiobutton(opts, text="Audio", value="Audio", variable=self.mode, command=self.on_mode)
        self.rb_video = ttk.Radiobutton(opts, text="Vídeo", value="Vídeo", variable=self.mode, command=self.on_mode)
        self.rb_audio.grid(row=0, column=0, sticky="w")
        self.rb_video.grid(row=0, column=1, sticky="w", padx=(12, 0))
        ttk.Label(opts, text="Formato:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.cb_fmt = ttk.Combobox(opts, textvariable=self.fmt, state="readonly", width=10)
        self.cb_fmt.grid(row=1, column=1, sticky="w", padx=(12, 0), pady=(6, 0))
        self.cb_fmt.bind("<<ComboboxSelected>>", lambda e: self.on_mode())
        self.opt_lbl = ttk.Label(opts, text="Calidad:")
        self.opt_lbl.grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.cb_bitrate = ttk.Combobox(opts, textvariable=self.bitrate, state="readonly", width=10,
                                       values=[f"{b} kbps" for b in core.MP3_BITRATES])
        self.cb_res = ttk.Combobox(opts, textvariable=self.res, state="readonly", width=10)
        for cb in (self.cb_bitrate, self.cb_res):
            cb.grid(row=2, column=1, sticky="w", padx=(12, 0), pady=(6, 0))

        dest = ttk.LabelFrame(main, text="Destino", padding=8)
        dest.grid(row=4, column=0, columnspan=4, sticky="ew", pady=4)
        dest.columnconfigure(0, weight=1)
        ttk.Entry(dest, textvariable=self.folder, state="readonly").grid(row=0, column=0, sticky="ew")
        self.btn_folder = ttk.Button(dest, text="Cambiar carpeta…", command=self.pick_folder)
        self.btn_folder.grid(row=0, column=1, padx=(6, 0))
        self.name_lbl = ttk.Label(dest, text="Nombre previsto: —", wraplength=560)
        self.name_lbl.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))

        act = ttk.Frame(main)
        act.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        act.columnconfigure(2, weight=1)
        self.btn_dl = ttk.Button(act, text="Descargar", command=self.start_download)
        self.btn_dl.grid(row=0, column=0)
        self.btn_cancel = ttk.Button(act, text="Cancelar", command=self.do_cancel)
        self.btn_cancel.grid(row=0, column=1, padx=6)
        self.bar = ttk.Progressbar(act, maximum=100)
        self.bar.grid(row=0, column=2, sticky="ew")
        self.status = ttk.Label(act, text="", width=24)
        self.status.grid(row=0, column=3, padx=(6, 0))

        self.done = ttk.Frame(main)
        self.done.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        self.done.columnconfigure(0, weight=1)
        self.path_lbl = ttk.Label(self.done, text="", wraplength=560)
        self.path_lbl.grid(row=0, column=0, columnspan=3, sticky="w")
        self.btn_play = ttk.Button(self.done, text="Reproducir archivo", command=lambda: os.startfile(self.result))
        self.btn_open = ttk.Button(self.done, text="Abrir carpeta", command=self.open_folder)
        self.btn_play.grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.btn_open.grid(row=1, column=1, sticky="w", pady=(4, 0), padx=6)
        self.done.grid_remove()

        self.on_mode()
        self.refresh()
        root.after(100, self.poll)
        self.url_entry.focus_set()
        faltan = core.missing_tools()
        if faltan:
            root.after(200, lambda: messagebox.showwarning(APP_NAME, FFMPEG_HELP.format(faltan=" y ".join(faltan))))

    # ----- utilidades de interfaz -----
    def say(self, text, error=False):
        self.msg.config(text=text, foreground="#b00020" if error else "#444")

    def refresh(self):
        ready = self.info is not None and not self.busy
        tools = not core.missing_tools()
        for w in (self.btn_paste, self.btn_analyze, self.btn_folder):
            w.state(["disabled"] if self.busy else ["!disabled"])
        self.url_entry.state(["disabled"] if self.busy else ["!disabled"])
        for w in (self.rb_audio, self.rb_video):
            w.state(["!disabled"] if ready else ["disabled"])
        for w in (self.cb_fmt, self.cb_bitrate, self.cb_res):
            w.state(["readonly", "!disabled"] if ready else ["disabled"])
        self.btn_dl.state(["!disabled"] if ready and tools else ["disabled"])
        self.btn_cancel.state(["!disabled"] if self.busy and self.cancel else ["disabled"])
        self.update_name()

    def on_mode(self):
        audio = self.mode.get() == "Audio"
        values = core.AUDIO_FORMATS if audio else core.VIDEO_FORMATS
        self.cb_fmt.config(values=values)
        if self.fmt.get() not in values:
            self.fmt.set(values[0])
        self.cb_bitrate.grid_remove()
        self.cb_res.grid_remove()
        if audio and self.fmt.get() == "MP3":
            self.opt_lbl.config(text="Calidad:")
            self.cb_bitrate.grid()
        elif audio:
            self.opt_lbl.config(text="Calidad: la mejor disponible" + (" (sin pérdida)" if self.fmt.get() == "WAV" else ""))
        else:
            self.opt_lbl.config(text="Resolución:")
            self.cb_res.grid()
        self.update_name()

    def update_name(self):
        if not self.info:
            self.name_lbl.config(text="Nombre previsto: —")
            return
        path = core.unique_path(self.folder.get(), core.safe_basename(self.info.get("title")),
                                core.EXT[self.fmt.get()])
        self.name_lbl.config(text="Nombre previsto: " + os.path.basename(path))

    def set_progress(self, pct):
        if pct is None:
            if str(self.bar.cget("mode")) != "indeterminate":
                self.bar.config(mode="indeterminate")
                self.bar.start(12)
        else:
            if str(self.bar.cget("mode")) != "determinate":
                self.bar.stop()
                self.bar.config(mode="determinate")
            self.bar["value"] = pct

    # ----- acciones -----
    def paste(self):
        try:
            self.url.set(self.root.clipboard_get().strip())
        except tk.TclError:
            self.say("El portapapeles no contiene texto.", error=True)

    def analyze(self):
        if self.busy:
            return
        try:
            url = core.normalize_youtube_url(self.url.get())
        except core.UserError as e:
            self.say(str(e), error=True)
            return
        self.busy, self.cancel, self.info = True, None, None
        self.done.grid_remove()
        self.say("Analizando el enlace…")
        self.set_progress(None)
        self.status.config(text="Analizando…")
        self.refresh()
        threading.Thread(target=self._work, args=(lambda: ("analyzed", core.analyze(url)),), daemon=True).start()

    def pick_folder(self):
        d = filedialog.askdirectory(initialdir=self.folder.get(), title="Elige la carpeta de destino")
        if d:
            self.folder.set(os.path.normpath(d))
            save_config({"folder": self.folder.get()})
            self.update_name()

    def start_download(self):
        if self.busy or not self.info:
            return
        target = self.fmt.get()
        height = None
        if target in core.VIDEO_FORMATS and self.res.get().endswith("p"):
            height = int(self.res.get()[:-1])
        bitrate = int(self.bitrate.get().split()[0])
        self.busy, self.cancel = True, threading.Event()
        self.done.grid_remove()
        self.say("Preparando la descarga…")
        self.refresh()
        info, folder, cancel = self.info, self.folder.get(), self.cancel
        report = lambda ph, pct, txt: self.q.put(("progress", ph, pct, txt))
        job = lambda: ("done", core.download(info, target, height, bitrate, folder, cancel, report))
        threading.Thread(target=self._work, args=(job,), daemon=True).start()

    def do_cancel(self):
        if self.cancel:
            self.cancel.set()
            self.status.config(text="Cancelando…")
            self.btn_cancel.state(["disabled"])

    def open_folder(self):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(self.result)])

    # ----- hilos -----
    def _work(self, job):
        """Corre en segundo plano; solo se comunica con Tkinter a través de la cola."""
        try:
            self.q.put(job())
        except core.Cancelled:
            self.q.put(("cancelled",))
        except core.UserError as e:
            self.q.put(("error", str(e)))
        except Exception as e:  # cualquier fallo inesperado se muestra en vez de cerrar la app
            self.q.put(("error", core.explain_error(e)))

    def poll(self):
        try:
            while True:
                self.handle(self.q.get_nowait())
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def handle(self, m):
        kind = m[0]
        if kind == "progress":
            _, phase, pct, text = m
            if not self.cancel.is_set():
                self.set_progress(pct)
                self.status.config(text=phase + (f" {pct:.0f} %" if pct is not None else ""))
                self.say(text)
            return
        self.busy = False
        self.set_progress(0)
        if kind == "analyzed":
            self.info = info = m[1]
            heights = core.video_heights(info)
            self.title_lbl.config(text=info.get("title") or "(sin título)")
            self.dur_lbl.config(text=fmt_duration(info.get("duration")))
            self.q_lbl.config(text=", ".join(f"{h}p" for h in heights) if heights else "solo audio")
            self.cb_res.config(values=[f"{h}p" for h in heights] or ["Mejor disponible"])
            self.res.set((self.cb_res.cget("values") or ["Mejor disponible"])[0])
            self.say("Vídeo analizado. Elige el formato y pulsa «Descargar».")
            self.status.config(text="")
        elif kind == "done":
            self.result = m[1]
            self.set_progress(100)
            self.status.config(text="Completado")
            self.say("Descarga completada.")
            self.path_lbl.config(text="Guardado en: " + self.result)
            self.done.grid()
        elif kind == "cancelled":
            self.status.config(text="Cancelado")
            self.say("Operación cancelada. No se ha guardado ningún archivo nuevo.")
        elif kind == "error":
            self.status.config(text="Error")
            self.say(m[1], error=True)
        self.cancel = None
        self.refresh()


def main():
    try:  # texto nítido en pantallas con escalado (Windows)
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
