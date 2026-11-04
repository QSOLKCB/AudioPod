"""Small native desktop front end; workers never touch Tk widgets."""

from dataclasses import replace
from pathlib import Path
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import font as tkfont
from tkinter import filedialog, messagebox, ttk
import webbrowser

from . import AudioPodError, Cancelled
from .books import Chapter, load_book
from .render import Settings, render_book, resume_options
from .preferences import load_preferences, save_preferences, suggested_output
from .voices import data_home, default_model, install_voice


class App:
    def __init__(self, root, cancelled=None):
        self.root, self.book, self.player = root, None, None
        self.events, self.cancel = queue.Queue(), cancelled if cancelled is not None else threading.Event()
        self.busy, self.closing = False, False
        self.preferences = load_preferences()
        self.render_output = None
        self.started_at = None
        root.title("AudioPod — turn a book into a listen")
        root.geometry("1120x820")
        root.minsize(900, 720)
        self.body_font = tkfont.nametofont("TkDefaultFont")
        self.body_font.configure(size=11)
        self.reading_font = self.body_font.copy()
        self.reading_font.configure(size=self.preferences["font_size"])
        root.option_add("*Font", "TkDefaultFont")
        self.heading_font = self.body_font.copy()
        self.heading_font.configure(size=26, weight="bold")
        self.controls = []
        frame = ttk.Frame(root, padding=20)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(3, weight=1)
        ttk.Label(frame, text="AudioPod", font=self.heading_font).grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text="Your books. A local voice. Listen at your own pace.").grid(row=1, column=0, sticky="w", pady=(0, 15))
        toolbar = ttk.Frame(frame)
        toolbar.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        self.button(toolbar, "Open book…", self.open_book).pack(side="left")
        self.button(toolbar, "Paste text…", self.paste).pack(side="left", padx=8)
        self.button(toolbar, "Select all", lambda: self.select_sections(True)).pack(side="left")
        self.button(toolbar, "Select none", lambda: self.select_sections(False)).pack(side="left", padx=6)
        self.button(toolbar, "Resume folder…", self.restore_job).pack(side="left")
        self.info = tk.StringVar(value="Open a DRM-free EPUB, TXT or Markdown file to begin.")
        ttk.Label(frame, textvariable=self.info).grid(row=3, column=0, sticky="nw")
        panes = ttk.Panedwindow(frame, orient="horizontal")
        panes.grid(row=3, column=0, sticky="nsew", pady=(28, 0))
        left, right = ttk.Frame(panes), ttk.Frame(panes)
        panes.add(left, weight=2)
        panes.add(right, weight=3)
        ttk.Label(left, text="Sections to narrate · Ctrl/Shift to select").pack(anchor="w")
        self.chapters = tk.Listbox(left, selectmode="extended", exportselection=False, activestyle="dotbox", font=self.reading_font)
        scroll = ttk.Scrollbar(left, command=self.chapters.yview)
        self.chapters.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.chapters.pack(fill="both", expand=True, padx=(0, 10))
        self.chapters.bind("<<ListboxSelect>>", self.preview_text)
        self.controls.append(self.chapters)
        ttk.Label(right, text="Text preview · narration preserves the imported words").pack(anchor="w")
        self.preview = tk.Text(right, wrap="word", state="disabled", padx=12, pady=12, width=40, height=10, font=self.reading_font)
        preview_scroll = ttk.Scrollbar(right, command=self.preview.yview)
        self.preview.configure(yscrollcommand=preview_scroll.set)
        preview_scroll.pack(side="right", fill="y")
        self.preview.pack(fill="both", expand=True)
        options = ttk.LabelFrame(frame, text="Narration", padding=10)
        options.grid(row=4, column=0, sticky="ew", pady=12)
        options.columnconfigure(1, weight=1)
        self.title, self.author = tk.StringVar(), tk.StringVar()
        self.model = tk.StringVar(value=self.preferences["model"])
        self.output = tk.StringVar(value=str(suggested_output(self.preferences["output_parent"], "my-book")))
        for row, (label, variable) in enumerate((("Book title", self.title), ("Author", self.author), ("Local voice (.onnx)", self.model), ("Output folder", self.output))):
            ttk.Label(options, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
            entry = ttk.Entry(options, textvariable=variable)
            entry.grid(row=row, column=1, sticky="ew", pady=3)
            self.controls.append(entry)
        self.button(options, "Choose voice…", self.choose_model).grid(row=2, column=2, padx=8)
        self.button(options, "Choose folder…", self.choose_output).grid(row=3, column=2, padx=8)
        bottom = ttk.Frame(options)
        bottom.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        self.speed = tk.StringVar(value=str(self.preferences["speed"]))
        self.format = tk.StringVar(value=self.preferences["format"])
        self.speaker = tk.StringVar(value=str(self.preferences["speaker"]))
        self.threads = tk.StringVar(value=str(self.preferences["threads"]))
        for label, variable, values, width in (("Voice speed", self.speed, ("0.75", "0.9", "1.0", "1.1", "1.25", "1.5"), 6), ("Output", self.format, ("wav", "mp3", "m4b"), 6)):
            ttk.Label(bottom, text=label).pack(side="left", padx=(0, 5))
            combo = ttk.Combobox(bottom, textvariable=variable, values=values, state="readonly", width=width)
            combo.pack(side="left", padx=(0, 15))
            self.controls.append(combo)
        ttk.Label(bottom, text="Speaker ID").pack(side="left")
        speaker = ttk.Spinbox(bottom, from_=0, to=999, textvariable=self.speaker, width=4)
        speaker.pack(side="left", padx=6)
        self.controls.append(speaker)
        ttk.Label(bottom, text="CPU threads").pack(side="left", padx=(8, 0))
        threads = ttk.Spinbox(bottom, from_=1, to=32, textvariable=self.threads, width=4)
        threads.pack(side="left", padx=6)
        self.controls.append(threads)
        self.resume = tk.BooleanVar()
        check = ttk.Checkbutton(options, text="Resume this folder", variable=self.resume)
        check.grid(row=5, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self.controls.append(check)
        row = ttk.Frame(frame)
        row.grid(row=5, column=0, sticky="ew")
        self.button(row, "Install Cori voice…", self.install).pack(side="left")
        self.button(row, "Voice preview", lambda: self.render(preview=True)).pack(side="left", padx=8)
        self.button(row, "Create audiobook", self.render).pack(side="left")
        self.stop = ttk.Button(row, text="Cancel", command=self.cancel.set, state="disabled")
        self.stop.pack(side="left", padx=8)
        self.listen = ttk.Button(row, text="Listen", command=self.open_player, state="disabled")
        self.listen.pack(side="right")
        self.button(row, "Open output", self.open_output).pack(side="right", padx=8)
        self.status = tk.StringVar(value="One-time voice setup needs internet. Narration stays on this computer.")
        self.progress = ttk.Progressbar(frame, maximum=1)
        self.progress.grid(row=6, column=0, sticky="ew", pady=(12, 5))
        ttk.Label(frame, textvariable=self.status, wraplength=980).grid(row=7, column=0, sticky="w")
        menu = tk.Menu(root)
        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label="Getting started", command=self.help)
        help_menu.add_command(label="Check setup", command=self.check_setup)
        help_menu.add_separator()
        help_menu.add_command(label="Larger reading text", command=lambda: self.resize_text(1))
        help_menu.add_command(label="Smaller reading text", command=lambda: self.resize_text(-1))
        menu.add_cascade(label="Help & accessibility", menu=help_menu)
        root.configure(menu=menu)
        self.speed.trace_add("write", lambda *args: self.update_selection())
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Control-o>", lambda e: self.open_book() if not self.busy else None)
        root.bind("<Escape>", lambda e: self.cancel.set() if self.busy else None)
        root.after(100, self.poll)

    def button(self, parent, label, command):
        button = ttk.Button(parent, text=label, command=command)
        self.controls.append(button)
        return button

    def set_book(self, book):
        self.book = book
        self.title.set(book.title)
        self.author.set(book.author)
        self.chapters.delete(0, tk.END)
        for i, chapter in enumerate(book.chapters):
            self.chapters.insert(tk.END, f"{i + 1}. {chapter.title}")
        self.chapters.selection_set(0, tk.END)
        self.output.set(str(suggested_output(self.preferences["output_parent"], book.title)))
        self.resume.set(False)
        self.player = self.render_output = None
        self.listen.configure(state="disabled")
        self.update_selection()
        self.preview_text()

    def update_selection(self):
        if self.book:
            selected = self.chapters.curselection()
            words = sum(self.book.chapters[i].words for i in selected)
            try:
                speed = float(self.speed.get())
                if not 0.5 <= speed <= 2:
                    speed = 1
            except ValueError:
                speed = 1
            minutes = max(1, round(words / (160 * speed))) if words else 0
            self.info.set(f"{len(selected)}/{len(self.book.chapters)} sections · {words:,} words · about {minutes} min of audio (estimate)")

    def select_sections(self, all_sections):
        if all_sections:
            self.chapters.selection_set(0, tk.END)
        else:
            self.chapters.selection_clear(0, tk.END)
        self.preview_text()

    def open_book(self):
        if self.busy:
            return
        filename = filedialog.askopenfilename(filetypes=[("Books and text", "*.epub *.txt *.md *.markdown"), ("All files", "*")])
        if filename:
            self.status.set("Importing book…")
            self.start(lambda: load_book(filename), result_kind="book")

    def paste(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Paste text")
        dialog.geometry("700x480")
        ttk.Label(dialog, text="Paste the words you want to hear. No text is uploaded.").pack(pady=8)
        text = tk.Text(dialog, wrap="word", padx=12, pady=12)
        text.pack(fill="both", expand=True)
        def use():
            with tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "Pasted text.txt"
                path.write_text(text.get("1.0", "end-1c"), encoding="utf-8")
                try:
                    self.set_book(load_book(path))
                    dialog.destroy()
                except AudioPodError as exc:
                    messagebox.showerror("Could not use text", str(exc), parent=dialog)
        ttk.Button(dialog, text="Use this text", command=use).pack(pady=8)
        dialog.transient(self.root)
        dialog.grab_set()
        text.focus_set()

    def preview_text(self, event=None):
        self.update_selection()
        if self.book and self.chapters.curselection():
            selected = self.chapters.curselection()
            active = self.chapters.index(tk.ACTIVE)
            index = active if active in selected else selected[0]
            self.preview.configure(state="normal")
            self.preview.delete("1.0", tk.END)
            self.preview.insert("1.0", self.book.chapters[index].text)
            self.preview.configure(state="disabled")
        elif self.book:
            self.preview.configure(state="normal")
            self.preview.delete("1.0", tk.END)
            self.preview.configure(state="disabled")

    def restore_job(self):
        if not self.book:
            messagebox.showinfo("Open the source", "Open the original book, then choose its saved output folder.")
            return
        folder = filedialog.askdirectory(title="Choose the saved audiobook folder")
        if not folder:
            return
        try:
            book, settings, selected = resume_options(self.book, folder)
            self.book = book
            self.title.set(book.title)
            self.author.set(book.author)
            for variable, value in ((self.speed, settings.speed), (self.format, settings.format), (self.speaker, settings.speaker), (self.threads, settings.threads)):
                variable.set(str(value))
            self.chapters.selection_clear(0, tk.END)
            for index in selected:
                self.chapters.selection_set(index)
            self.output.set(folder)
            self.resume.set(True)
            self.preview_text()
            self.status.set("Saved settings restored. Choose the original voice, then Create audiobook to verify and resume.")
        except AudioPodError as exc:
            messagebox.showerror("Could not restore job", str(exc))

    def choose_model(self):
        filename = filedialog.askopenfilename(filetypes=[("Piper voice", "*.onnx")])
        if filename:
            self.model.set(filename)

    def choose_output(self):
        folder = filedialog.askdirectory(mustexist=False)
        if folder:
            self.output.set(folder)

    def start(self, work, result_kind="done"):
        self.busy = True
        self.cancel.clear()
        self.progress["value"] = 0
        self.started_at = time.monotonic()
        for widget in self.controls:
            widget.configure(state="disabled")
        self.stop.configure(state="normal")
        def run():
            try:
                result = work()
                if result_kind == "book" and self.cancel.is_set():
                    raise Cancelled("Book import cancelled.")
                self.events.put((result_kind, result))
            except Exception as exc:
                self.events.put(("error", exc))
        threading.Thread(target=run, name="audiopod-worker", daemon=False).start()

    def install(self):
        if messagebox.askokcancel("Install Cori voice", "Download about 61 MiB from Hugging Face?\n\nCori is a UK English voice. Its upstream model card lists a public-domain LibriVox dataset. AudioPod verifies pinned file hashes. Your text is never sent.\n\nPiper and voice notices are in THIRD_PARTY.md."):
            self.start(lambda: install_voice(lambda s: self.events.put(("progress", {"message": s, "fraction": 0})), self.cancel.is_set))

    def render(self, preview=False):
        if not self.book:
            messagebox.showinfo("Open a book", "Choose a book or paste text first.")
            return
        selected = list(self.chapters.curselection())
        if not selected:
            messagebox.showinfo("Select sections", "Select at least one section to narrate.")
            return
        try:
            settings = Settings(float(self.speed.get()), int(self.speaker.get()), int(self.threads.get()), "wav" if preview else self.format.get())
            settings.validate()
        except (ValueError, AudioPodError) as exc:
            messagebox.showerror("Narration settings", str(exc))
            return
        book = replace(self.book, title=self.title.get().strip() or self.book.title, author=self.author.get().strip())
        output, resume = self.output.get(), self.resume.get()
        if not output.strip():
            messagebox.showerror("Output folder", "Choose an output folder.")
            return
        if preview:
            from .books import split_text
            text = next(split_text(book.chapters[selected[0]].text, 400))
            book = replace(book, chapters=(Chapter("Voice preview", text),))
            selected, resume = [0], False
            previews = data_home() / "previews"
            previews.mkdir(parents=True, exist_ok=True)
            output = tempfile.mkdtemp(prefix="listen-", dir=previews)
        model = Path(self.model.get()).expanduser()
        self.render_output = None if preview else Path(output).expanduser().absolute()
        self.remember_settings()
        self.start(lambda: render_book(book, model, Path(output).expanduser(), settings, selected, resume,
                                      lambda e: self.events.put(("progress", e)), self.cancel.is_set))

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "progress":
                    elapsed = int(time.monotonic() - self.started_at) if self.started_at else 0
                    self.status.set(f"{value['message']} · elapsed {elapsed // 60}:{elapsed % 60:02d}")
                    self.progress["value"] = value["fraction"]
                else:
                    self.busy = False
                    for widget in self.controls:
                        widget.configure(state="readonly" if isinstance(widget, ttk.Combobox) else "normal")
                    self.stop.configure(state="disabled")
                    if kind == "book":
                        self.set_book(value)
                        self.status.set("Book imported. Check the selected sections, then preview the voice.")
                    elif kind == "diagnostics":
                        from .diagnostics import format_diagnostics
                        self.show_text("Setup check", format_diagnostics(value))
                    elif kind == "done":
                        if Path(value).suffix == ".html":
                            self.player = Path(value)
                            self.listen.configure(state="normal")
                            self.status.set(f"Ready to listen · {self.player.parent}")
                        else:
                            self.model.set(str(value))
                            self.status.set("Cori is installed. Choose Voice preview or Create audiobook.")
                    elif isinstance(value, Cancelled):
                        self.status.set(str(value))
                    else:
                        self.status.set(str(value))
                        if not self.closing:
                            messagebox.showerror("AudioPod", str(value))
                    if self.render_output and (self.render_output / "audiopod.json").is_file():
                        self.resume.set(True)
                        player = self.render_output / "listen.html"
                        if player.is_file():
                            self.player = player
                            self.listen.configure(state="normal")
                    self.render_output = None
        except queue.Empty:
            pass
        if self.closing and not self.busy:
            self.root.destroy()
            return
        self.root.after(100, self.poll)

    def open_player(self):
        if self.player:
            webbrowser.open(self.player.resolve().as_uri())

    def open_output(self):
        path = self.player.parent if self.player else Path(self.output.get()).expanduser().absolute()
        if not path.is_dir():
            messagebox.showinfo("Output folder", "The output folder will be created when narration starts.")
            return
        try:
            if sys.platform == "win32":
                os.startfile(path)
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            messagebox.showinfo("Output folder", str(path))

    def remember_settings(self):
        try:
            self.preferences.update(model=self.model.get(), output_parent=str(Path(self.output.get()).expanduser().absolute().parent),
                                    speed=float(self.speed.get()), speaker=int(self.speaker.get()), threads=int(self.threads.get()),
                                    format=self.format.get(), font_size=int(self.reading_font.cget("size")))
            save_preferences(self.preferences)
        except (ValueError, OSError):
            pass  # Invalid optional preferences must not discard a book or stop audio.

    def resize_text(self, delta):
        self.reading_font.configure(size=max(10, min(24, int(self.reading_font.cget("size")) + delta)))
        self.remember_settings()

    def show_text(self, title, content):
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry("800x540")
        body = ttk.Frame(dialog)
        body.pack(fill="both", expand=True)
        text = tk.Text(body, wrap="word", padx=16, pady=16, font=self.reading_font)
        scroll = ttk.Scrollbar(body, command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        text.pack(fill="both", expand=True)
        text.insert("1.0", content)
        text.configure(state="disabled")
        ttk.Button(dialog, text="Close", command=dialog.destroy).pack(pady=8)

    def check_setup(self):
        if not self.busy:
            from .diagnostics import diagnose
            model = Path(self.model.get()).expanduser()
            self.status.set("Checking local setup…")
            self.start(lambda: diagnose(model), result_kind="diagnostics")

    def help(self):
        self.show_text("Getting started", "1. Use Help & accessibility → Check setup. Install the Cori voice once if needed.\n\n"
                       "2. Open an EPUB, TXT or Markdown book, or paste text. Check the text preview. Select all, none, or use Ctrl/Shift to choose sections.\n\n"
                       "3. Choose Voice preview, then Listen. Names and pronunciation may need human review.\n\n"
                       "4. Pick WAV (no FFmpeg needed), MP3 chapters, or M4B with chapter markers. Check the suggested output folder. Create audiobook.\n\n"
                       "5. Cancel or Escape stops safely. Completed chapters remain playable. To continue later, reopen the original book and use Resume folder.\n\n"
                       "6. Listen opens the portable player. Keep listen.html beside its chapter audio; book.m4b can travel alone. Open output shows the files.\n\n"
                       "Voice, speed, format, CPU threads, text size and output-parent preferences stay local. Book text is never saved in preferences.\n\n"
                       "Detailed guides: docs/INSTALLATION.md, docs/GETTING_STARTED.md and docs/TROUBLESHOOTING.md in the AudioPod checkout.")

    def close(self):
        self.remember_settings()
        if self.busy:
            self.closing = True
            self.cancel.set()
            self.status.set("Stopping safely; the window will close when the current audio chunk or download read finishes…")
        else:
            self.root.destroy()


def launch(cancelled=None):
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise AudioPodError(f"Desktop could not open: {exc}. Use the CLI in headless sessions.") from exc
    App(root, cancelled)
    root.mainloop()
    return 0
