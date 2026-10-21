"""Convertify desktop app.

    gui.pyw                         open the app
    gui.pyw FILE [FILE...]          open the app with these files (Send To / "Open in Convertify")
    gui.pyw --convert TARGET FILE   convert one file right away (the right-click menu), small popup only
"""
import multiprocessing as mp
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import winreg
from pathlib import Path
from tkinter import filedialog, ttk

MARK, MARK_INK = "#C6F432", "#12151C"
SHORT = {"pdf-split": "pages", "ocr-pdf": "searchable .pdf", "ocr-txt": "text",
         "merge-pdf": "one .pdf", "images-pdf": "one .pdf", "images-gif": "one .gif", "zip": "one .zip",
         "pdf-compress": "smaller .pdf", "pdf-rotate": "rotated .pdf", "pdf-protect": "locked .pdf",
         "pdf-unlock": "unlocked .pdf", "pdf-watermark": "watermarked", "pdf-numbers": "numbered .pdf",
         "pdf-images": "pictures", "mp4-small": "smaller .mp4", "jpg-frame": "thumbnail", "mute": "no sound",
         "norm": "even volume", "unzip": "files"}
NO_PAGES = {"pdf-compress", "pdf-protect", "pdf-unlock", "pdf-numbers"}  # these always work on every page


def system_is_dark():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


class UiQueue:
    """Tkinter isn't thread-safe: worker threads hand UI updates to the main thread through this."""

    def __init__(self, root):
        self.q, self.root = queue.Queue(), root
        self._poll()

    def __call__(self, fn, *args):
        self.q.put((fn, args))

    def _poll(self):
        try:
            while True:
                fn, args = self.q.get_nowait()
                fn(*args)
        except queue.Empty:
            pass
        self.root.after(80, self._poll)


def near_pointer(w, h, offset=16):
    """Top-left corner for a w x h window just below-right of the mouse, kept inside that
    monitor's work area (so it never lands off-screen or under the taskbar)."""
    import ctypes
    from ctypes import wintypes

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    pt = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
    monitor = ctypes.windll.user32.MonitorFromPoint(pt, 2)  # 2 = nearest monitor
    ctypes.windll.user32.GetMonitorInfoW(monitor, ctypes.byref(info))
    work = info.rcWork
    x, y = pt.x + offset, pt.y + offset
    if x + w > work.right:
        x = pt.x - w - offset  # no room on the right: open to the left of the mouse
    if y + h > work.bottom:
        y = pt.y - h - offset  # no room below: open above the mouse
    return max(work.left, min(x, work.right - w)), max(work.top, min(y, work.bottom - h))


def show_in_folder(path):
    subprocess.Popen(["explorer", "/select,", str(path)])


def setup_window(root, title):
    import sv_ttk
    from core import HERE
    root.title(title)
    try:
        root.iconbitmap(default=str(HERE / "assets" / "icon.ico"))
    except tk.TclError:
        pass
    sv_ttk.set_theme("dark" if system_is_dark() else "light")


# ------------------------------------------------------------------ right-click popup
def quick_convert(target, path):
    import converters
    import core
    root = tk.Tk()
    setup_window(root, "Convertify")
    root.resizable(False, False)
    root.attributes("-topmost", True)
    src = Path(path)
    conv = converters.MAP.get(converters.ext_of(src.name), {}).get(target)
    label = conv.label if conv else target

    frame = ttk.Frame(root, padding=18)
    frame.pack(fill="both", expand=True)
    title = ttk.Label(frame, text=f"Converting {src.name}", font=("Segoe UI Variable Display", 13, "bold"),
                      wraplength=360)
    title.pack(anchor="w")
    detail = ttk.Label(frame, text=f"to {label}", wraplength=360)
    detail.pack(anchor="w", pady=(2, 10))
    bar = ttk.Progressbar(frame, mode="indeterminate", length=360)
    bar.pack(fill="x")
    bar.start(12)
    buttons = ttk.Frame(frame)
    buttons.pack(fill="x", pady=(12, 0))

    # Next to the mouse (where you right-clicked), staggered so several conversions don't stack exactly.
    root.update_idletasks()
    w, h = 400, root.winfo_reqheight() + 40
    slot = os.getpid() % 5
    x, y = near_pointer(w, h, offset=16 + slot * 28)
    root.geometry(f"{w}x{h}+{x}+{y}")

    def finished(saved=None, error=None):
        bar.stop()
        bar.pack_forget()
        if error:
            title.config(text=f"Couldn't convert {src.name}")
            detail.config(text=error, foreground="#D9534F")
            ttk.Button(buttons, text="Close", command=root.destroy).pack(side="right")
            return
        title.config(text="Done")
        detail.config(text=f"Saved as {Path(saved).name}")
        ttk.Button(buttons, text="Close", command=root.destroy).pack(side="right")
        ttk.Button(buttons, text="Open", command=lambda: (os.startfile(saved), root.destroy())).pack(side="right", padx=6)
        ttk.Button(buttons, text="Show in folder", style="Accent.TButton",
                   command=lambda: (show_in_folder(saved), root.destroy())).pack(side="right")
        root.after(12000, root.destroy)

    ui = UiQueue(root)

    def work():
        try:
            ui(finished, core.convert([src], target))
        except Exception as e:
            ui(finished, None, str(e))

    threading.Thread(target=work, daemon=True).start()
    root.mainloop()


# ------------------------------------------------------------------ main window
class App:
    def __init__(self, files):
        import converters
        import shell
        from converters.tools import status
        from tkinterdnd2 import DND_FILES, TkinterDnD
        self.converters, self.shell = converters, shell
        self.formats = converters.MAP
        self.tools = status()

        self.root = root = TkinterDnD.Tk()
        setup_window(root, "Convertify")
        root.geometry("820x700")
        root.minsize(480, 560)
        self.items = {}  # tree row id -> {"path", "ext", "state", "saved"}
        self.dest = None  # None = next to each file
        self.busy = False
        self.ui = UiQueue(root)

        outer = ttk.Frame(root, padding=(24, 16, 24, 16))
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)

        # top bar
        top = ttk.Frame(outer)
        top.grid(row=0, column=0, sticky="ew")
        from core import HERE
        self.logo = tk.PhotoImage(file=str(HERE / "assets" / "icon.png")).subsample(8)
        ttk.Label(top, image=self.logo, text="  Convertify", compound="left",
                  font=("Segoe UI Variable Display", 11, "bold")).pack(side="left")
        self.theme_btn = ttk.Button(top, command=self.toggle_theme)
        self.theme_btn.pack(side="right")

        # the one loud thing: the live "from -> to" line
        self.route = tk.Frame(outer)
        self.route.grid(row=1, column=0, sticky="w", pady=(10, 14))
        big = ("Segoe UI Variable Display", 34, "bold")
        self.r_from = tk.Label(self.route, font=big)
        self.r_arrow = tk.Label(self.route, text=" → ", font=("Segoe UI Variable Display", 34))
        self.r_to = tk.Label(self.route, font=big, padx=4)
        for w in (self.r_from, self.r_arrow, self.r_to):
            w.pack(side="left")

        # missing programs
        self.warn = ttk.Frame(outer)
        self.warn.grid(row=2, column=0, sticky="ew")
        for t in self.tools.values():
            if not t["found"]:
                row = ttk.Frame(self.warn)
                row.pack(fill="x", pady=2)
                ttk.Label(row, text=f"{t['name']} isn't installed, so its formats are off. Install with:").pack(side="left")
                e = ttk.Entry(row, width=48)
                e.insert(0, t["install"])
                e.config(state="readonly")
                e.pack(side="left", padx=6)

        # drop zone
        drop = ttk.Frame(outer, style="Card.TFrame", padding=(20, 16))
        drop.grid(row=3, column=0, sticky="ew", pady=(4, 12))
        self.drop_title = ttk.Label(drop, text="Drop files here", font=("Segoe UI Variable Display", 15, "bold"))
        self.drop_title.pack(side="left")
        ttk.Button(drop, text="Add files…", command=self.browse).pack(side="right")
        root.drop_target_register(DND_FILES)
        root.dnd_bind("<<Drop>>", self.on_drop)
        root.dnd_bind("<<DropEnter>>", lambda e: (self.drop_title.config(text="Release to add"), e.action)[1])
        root.dnd_bind("<<DropLeave>>", lambda e: (self.drop_title.config(text="Drop files here"), e.action)[1])

        # controls
        ctl = ttk.Frame(outer)
        ctl.grid(row=4, column=0, sticky="ew")
        ctl.columnconfigure(0, weight=1)
        ttk.Label(ctl, text="Convert to").grid(row=0, column=0, sticky="w")
        ttk.Label(ctl, text="Save to").grid(row=0, column=1, sticky="w", padx=(12, 0))
        self.target = ttk.Combobox(ctl, state="readonly")
        self.target.grid(row=1, column=0, sticky="ew")
        self.target.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        self.save_to = ttk.Combobox(ctl, state="readonly", width=26, values=["Next to each file", "Choose folder…"])
        self.save_to.current(0)
        self.save_to.grid(row=1, column=1, padx=(12, 0))
        self.save_to.bind("<<ComboboxSelected>>", self.pick_dest)
        self.go = ttk.Button(ctl, text="Convert", style="Accent.TButton", command=self.start)
        self.go.grid(row=1, column=2, padx=(12, 0))
        self.hint = ttk.Label(outer, foreground="gray")
        self.hint.grid(row=5, column=0, sticky="w", pady=(6, 0))

        # options, shown only when they apply
        self.opts_frame = ttk.Frame(outer)
        self.opts_frame.grid(row=6, column=0, sticky="w", pady=(6, 0))
        self.vars = {"pages": tk.StringVar(), "quality": tk.IntVar(value=90), "max_size": tk.StringVar(value="Keep original"),
                     "resolution": tk.StringVar(value="Keep original"), "lang": tk.StringVar(value="eng"),
                     "angle": tk.StringVar(value="90"), "password": tk.StringVar(), "text": tk.StringVar(value="DRAFT"),
                     "start": tk.StringVar(), "end": tk.StringVar()}
        self.opt_widgets = {}

        def opt(key, label, widget):
            f = ttk.Frame(self.opts_frame)
            ttk.Label(f, text=label).pack(anchor="w")
            widget(f).pack(anchor="w")
            self.opt_widgets[key] = f
        opt("pages", "Pages (e.g. 1-3, 5)", lambda f: ttk.Entry(f, textvariable=self.vars["pages"], width=16))

        def quality(f):
            box = ttk.Frame(f)
            ttk.Scale(box, from_=40, to=100, variable=self.vars["quality"], length=140,
                      command=lambda v: self.vars["quality"].set(round(float(v)))).pack(side="left")
            ttk.Label(box, textvariable=self.vars["quality"], width=4).pack(side="left", padx=6)
            return box
        opt("quality", "Quality", quality)
        opt("max_size", "Longest side (px)", lambda f: ttk.Combobox(
            f, textvariable=self.vars["max_size"], state="readonly", width=14,
            values=["Keep original", "3840", "1920", "1280", "800", "256"]))
        opt("resolution", "Video height", lambda f: ttk.Combobox(
            f, textvariable=self.vars["resolution"], state="readonly", width=14,
            values=["Keep original", "1080", "720", "480", "360"]))
        opt("lang", "Text language", lambda f: ttk.Entry(f, textvariable=self.vars["lang"], width=12))
        opt("angle", "Turn clockwise by", lambda f: ttk.Combobox(
            f, textvariable=self.vars["angle"], state="readonly", width=8, values=["90", "180", "270"]))
        opt("password", "Password", lambda f: ttk.Entry(f, textvariable=self.vars["password"], width=18, show="•"))
        opt("text", "Watermark text", lambda f: ttk.Entry(f, textvariable=self.vars["text"], width=20))
        opt("start", "Start at (e.g. 0:30)", lambda f: ttk.Entry(f, textvariable=self.vars["start"], width=10))
        opt("end", "End at (empty = to the end)", lambda f: ttk.Entry(f, textvariable=self.vars["end"], width=10))

        # file list
        lst = ttk.Frame(outer)
        lst.grid(row=7, column=0, sticky="nsew", pady=(14, 0))
        outer.rowconfigure(7, weight=1)
        self.tree = ttk.Treeview(lst, columns=("status", "saved"), selectmode="extended")
        self.tree.heading("#0", text="File", anchor="w")
        self.tree.heading("status", text="Status", anchor="w")
        self.tree.heading("saved", text="Saved as", anchor="w")
        self.tree.column("#0", width=260, stretch=True)
        self.tree.column("status", width=230, stretch=True)
        self.tree.column("saved", width=200, stretch=True)
        self.tree.tag_configure("done", foreground="#2E9E5B")
        self.tree.tag_configure("failed", foreground="#D9534F")
        sb = ttk.Scrollbar(lst, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self.open_result)
        self.tree.bind("<Delete>", lambda e: self.remove_selected())

        # bottom bar
        bottom = ttk.Frame(outer)
        bottom.grid(row=8, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(bottom, text="Remove selected", command=self.remove_selected).pack(side="left")
        ttk.Button(bottom, text="Clear list", command=self.clear).pack(side="left", padx=8)
        self.menu_var = tk.BooleanVar(value=shell.is_installed())
        ttk.Checkbutton(bottom, text="Show in right-click menu", style="Switch.TCheckbutton",
                        variable=self.menu_var, command=self.toggle_menu).pack(side="right")
        ttk.Label(outer, text="Convertify runs only on this computer. Nothing is uploaded, and your original files are never changed. "
                              "Double-click a finished file to show it.",
                  foreground="gray", wraplength=740).grid(row=9, column=0, sticky="w", pady=(10, 0))

        self.apply_theme_colors()
        self.add_files(files)
        self.refresh()

    # ---------- files
    def add_files(self, paths):
        for p in paths:
            p = Path(p)
            if p.is_dir():
                self.add_files(sorted(x for x in p.iterdir() if x.is_file()))
                continue
            ext = self.converters.ext_of(p.name)
            ok = ext in self.formats
            iid = self.tree.insert("", "end", text=p.name,
                                   values=("Waiting" if ok else f"Failed: .{ext or '?'} files aren't supported", ""),
                                   tags=() if ok else ("failed",))
            self.items[iid] = {"path": p, "ext": ext, "state": "waiting" if ok else "unsupported", "saved": None}
        self.refresh()

    def browse(self):
        self.add_files(filedialog.askopenfilenames(title="Add files to convert"))

    def on_drop(self, event):
        self.drop_title.config(text="Drop files here")
        self.add_files(self.root.tk.splitlist(event.data))
        return event.action

    def remove_selected(self):
        for iid in self.tree.selection():
            if self.items[iid]["state"] != "working":
                self.tree.delete(iid)
                del self.items[iid]
        self.refresh()

    def clear(self):
        for iid in list(self.items):
            if self.items[iid]["state"] != "working":
                self.tree.delete(iid)
                del self.items[iid]
        self.refresh()

    def open_result(self, event):
        iid = self.tree.identify_row(event.y)
        if iid and self.items[iid]["saved"]:
            show_in_folder(self.items[iid]["saved"])

    def pick_dest(self, event=None):
        choice = self.save_to.get()
        if choice == "Choose folder…":
            folder = filedialog.askdirectory(title="Save converted files in")
            if folder:
                self.dest = Path(folder)
                self.save_to.config(values=["Next to each file", str(self.dest), "Choose folder…"])
        elif choice == "Next to each file":
            self.dest = None
        else:
            self.dest = Path(choice)
        self.save_to.set(str(self.dest) if self.dest else "Next to each file")

    # ---------- what the files can become
    def pending(self):
        return [i for i in self.items.values() if i["state"] in ("waiting", "failed")]

    def choices(self):
        exts = list(dict.fromkeys(i["ext"] for i in self.pending()))
        if not exts:
            return []
        common = list(self.formats[exts[0]].items())
        for e in exts[1:]:
            common = [(k, c) for k, c in common if k in self.formats[e]]
        multi = []
        if len(self.pending()) > 1:
            multi = [(k, c) for k, c in self.converters.MULTI.items()
                     if all(e in self.converters.MULTI_ACCEPTS[k] for e in exts)]
        out = []
        for k, c in multi + common:
            missing = [self.tools[t]["name"] for t in c.needs if not self.tools[t]["found"]]
            out.append((k, c.label + (f"  (needs {', '.join(missing)})" if missing else ""), not missing))
        return out

    def refresh(self):
        opts = self.choices()
        self._choice_ids = [k for k, _, _ in opts]
        labels = [label for _, label, _ in opts]
        current = self.target.get()
        self.target.config(values=labels)
        usable = [label for _, label, ok in opts if ok]
        if current not in usable:
            self.target.set(usable[0] if usable else "")
        target = self.target_id()
        exts = list(dict.fromkeys(i["ext"] for i in self.pending()))

        n = len(self.pending())
        self.hint.config(text=(
            "" if not self.items else
            "Add more files to convert again." if not n else
            "These files have no format in common. Convert them in separate batches." if not opts else
            f"All {n} files go into {SHORT[target]}, in the order listed." if target in self.converters.MULTI else
            "Showing only the formats every file here can become." if len(exts) > 1 else ""))
        self.go.config(state="normal" if (not self.busy and target and n) else "disabled")

        if exts and target:
            self.r_from.config(text=f"{len(exts)} types" if len(exts) > 2 else " + ".join("." + e for e in exts))
            self.r_to.config(text=SHORT.get(target, "." + target))
            self.r_to.config(bg=MARK, fg=MARK_INK)
            self.r_from.config(fg=self.fg)
        else:
            self.r_from.config(text="Any file", fg="gray")
            self.r_to.config(text="anything", bg=self.bg, fg="gray")

        images = set(self.converters.IMAGES)
        media = bool(exts) and set(exts) <= set(self.converters.VIDEO + self.converters.AUDIO)
        show = {
            "pages": bool(target) and "pdf" in exts and target not in self.converters.MULTI and target not in NO_PAGES,
            "quality": target in ("jpg", "webp", "avif", "heic"),
            "max_size": bool(images & set(exts)) and (target in images or target in ("pdf", "images-pdf", "images-gif")),
            "resolution": media and target in ("mp4", "webm", "mov", "mkv", "gif", "mp4-small"),
            "lang": bool(target and target.startswith("ocr")),
            "angle": target == "pdf-rotate",
            "password": target in ("pdf-protect", "pdf-unlock"),
            "text": target == "pdf-watermark",
            "start": media and bool(target),
            "end": media and bool(target),
        }
        for key, frame in self.opt_widgets.items():
            frame.pack_forget()
            if show[key]:
                frame.pack(side="left", padx=(0, 18))

    def target_id(self):
        labels = list(self.target.cget("values"))
        if self.target.get() in labels:
            return self._choice_ids[labels.index(self.target.get())]
        return None

    def options(self):
        o = {}
        for key, frame in self.opt_widgets.items():
            if frame.winfo_manager():
                v = str(self.vars[key].get())
                v = v if key == "password" else v.strip()  # spaces can be part of a password
                if v and v != "Keep original":
                    o[key] = v
        return o

    # ---------- converting
    def set_row(self, iid, status, tag=None, saved=""):
        if self.tree.exists(iid):
            self.tree.item(iid, values=(status, saved), tags=(tag,) if tag else ())

    def start(self):
        import core
        target, opts, dest = self.target_id(), self.options(), self.dest
        batch = [iid for iid, i in self.items.items() if i["state"] in ("waiting", "failed")]
        if not target or not batch:
            return
        groups = [batch] if target in self.converters.MULTI else [[iid] for iid in batch]
        self.busy = True
        for iid in batch:
            self.items[iid]["state"] = "working"
            self.set_row(iid, "Waiting…")
        self.refresh()

        def work():
            for group in groups:
                for iid in group:
                    self.ui(self.set_row, iid, "Converting…")
                try:
                    saved = core.convert([self.items[i]["path"] for i in group], target, opts, dest)
                    for n, iid in enumerate(group):
                        self.items[iid].update(state="done", saved=saved)
                        self.ui(self.set_row, iid, "Done" if n == 0 else "Done (included)",
                                        "done", Path(saved).name)
                except Exception as e:
                    for iid in group:
                        self.items[iid]["state"] = "failed"
                        self.ui(self.set_row, iid, f"Failed: {e}", "failed")
            self.busy = False
            self.ui(self.refresh)

        threading.Thread(target=work, daemon=True).start()

    # ---------- settings
    def toggle_menu(self):
        try:
            self.shell.install() if self.menu_var.get() else self.shell.uninstall()
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("Convertify", f"Couldn't change the right-click menu: {e}")
        self.menu_var.set(self.shell.is_installed())

    def toggle_theme(self):
        import sv_ttk
        sv_ttk.set_theme("light" if sv_ttk.get_theme() == "dark" else "dark")
        self.apply_theme_colors()
        self.refresh()

    def apply_theme_colors(self):
        import sv_ttk
        style = ttk.Style()
        self.bg = style.lookup("TFrame", "background") or self.root.cget("bg")
        self.fg = style.lookup("TLabel", "foreground") or "black"
        for w in (self.route, self.r_from, self.r_arrow):
            w.config(bg=self.bg)
        self.r_arrow.config(fg="gray")
        self.theme_btn.config(text="Light mode" if sv_ttk.get_theme() == "dark" else "Dark mode")


def main():
    try:  # sharp text on high-DPI screens; must happen before the first window
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    args = sys.argv[1:]
    if len(args) >= 3 and args[0] == "--convert":
        quick_convert(args[1], args[2])
    else:
        App(args).root.mainloop()


if __name__ == "__main__":
    mp.freeze_support()  # lets the .exe start its own conversion worker processes
    sys.path.insert(0, str(Path(__file__).parent))
    main()
