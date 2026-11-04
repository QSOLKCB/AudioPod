"""Small native desktop front end; workers never touch Tk widgets."""

from dataclasses import replace
from pathlib import Path
import queue
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser

from . import AudioPodError, Cancelled
from .books import Chapter, load_book
from .render import Settings, render_book
from .voices import data_home, default_model, install_voice


class App:
    def __init__(self, root):
        self.root, self.book, self.player = root, None, None
        self.events, self.cancel = queue.Queue(), threading.Event()
        self.busy, self.closing = False, False
        root.title("AudioPod — turn a book into a listen")
        root.geometry("1060x780")
        root.minsize(800, 650)
        root.option_add("*Font", "{TkDefaultFont} 11")
        self.controls = []
        frame = ttk.Frame(root, padding=20)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(3, weight=1)
        ttk.Label(frame, text="AudioPod", font=("TkDefaultFont", 26, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text="Your books. A local voice. Listen at your own pace.").grid(row=1, column=0, sticky="w", pady=(0, 15))
        toolbar = ttk.Frame(frame)
        toolbar.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        self.button(toolbar, "Open book…", self.open_book).pack(side="left")
        self.button(toolbar, "Paste text…", self.paste).pack(side="left", padx=8)
        self.button(toolbar, "Select all", lambda: self.chapters.selection_set(0, tk.END)).pack(side="left")
        self.info = tk.StringVar(value="Open a DRM-free EPUB, TXT or Markdown file to begin.")
        ttk.Label(toolbar, textvariable=self.info).pack(side="left", padx=10)
        panes = ttk.Panedwindow(frame, orient="horizontal")
        panes.grid(row=3, column=0, sticky="nsew")
        left, right = ttk.Frame(panes), ttk.Frame(panes)
        panes.add(left, weight=2)
        panes.add(right, weight=3)
        ttk.Label(left, text="Sections to narrate · Ctrl/Shift to select").pack(anchor="w")
        self.chapters = tk.Listbox(left, selectmode="extended", exportselection=False, activestyle="dotbox")
        scroll = ttk.Scrollbar(left, command=self.chapters.yview)
        self.chapters.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.chapters.pack(fill="both", expand=True, padx=(0, 10))
        self.chapters.bind("<<ListboxSelect>>", self.preview_text)
        self.controls.append(self.chapters)
        ttk.Label(right, text="Text preview · narration preserves the imported words").pack(anchor="w")
        self.preview = tk.Text(right, wrap="word", state="disabled", padx=12, pady=12, width=40, height=10)
        preview_scroll = ttk.Scrollbar(right, command=self.preview.yview)
        self.preview.configure(yscrollcommand=preview_scroll.set)
        preview_scroll.pack(side="right", fill="y")
        self.preview.pack(fill="both", expand=True)
        options = ttk.LabelFrame(frame, text="Narration", padding=10)
        options.grid(row=4, column=0, sticky="ew", pady=12)
        options.columnconfigure(1, weight=1)
        self.title, self.author = tk.StringVar(), tk.StringVar()
        self.model, self.output = tk.StringVar(value=str(default_model())), tk.StringVar(value=str(Path.home() / "AudioPod" / "my-audiobook"))
        for row, (label, variable) in enumerate((("Book title", self.title), ("Author", self.author), ("Local voice (.onnx)", self.model), ("Output folder", self.output))):
            ttk.Label(options, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
            entry = ttk.Entry(options, textvariable=variable)
            entry.grid(row=row, column=1, sticky="ew", pady=3)
            self.controls.append(entry)
        self.button(options, "Choose voice…", self.choose_model).grid(row=2, column=2, padx=8)
        self.button(options, "Choose folder…", self.choose_output).grid(row=3, column=2, padx=8)
        bottom = ttk.Frame(options)
        bottom.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        self.speed, self.format, self.speaker = tk.StringVar(value="1.0"), tk.StringVar(value="mp3"), tk.StringVar(value="0")
        for label, variable, values, width in (("Voice speed", self.speed, ("0.75", "0.9", "1.0", "1.1", "1.25", "1.5"), 6), ("Output", self.format, ("wav", "mp3", "m4b"), 6)):
            ttk.Label(bottom, text=label).pack(side="left", padx=(0, 5))
            combo = ttk.Combobox(bottom, textvariable=variable, values=values, state="readonly", width=width)
            combo.pack(side="left", padx=(0, 15))
            self.controls.append(combo)
        ttk.Label(bottom, text="Speaker ID").pack(side="left")
        speaker = ttk.Spinbox(bottom, from_=0, to=999, textvariable=self.speaker, width=4)
        speaker.pack(side="left", padx=6)
        self.controls.append(speaker)
        self.resume = tk.BooleanVar()
        check = ttk.Checkbutton(bottom, text="Resume this folder", variable=self.resume)
        check.pack(side="left", padx=10)
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
        self.status = tk.StringVar(value="One-time voice setup needs internet. Narration stays on this computer.")
        self.progress = ttk.Progressbar(frame, maximum=1)
        self.progress.grid(row=6, column=0, sticky="ew", pady=(12, 5))
        ttk.Label(frame, textvariable=self.status, wraplength=980).grid(row=7, column=0, sticky="w")
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
        self.info.set(f"{book.words:,} words · {len(book.chapters)} sections")
        self.preview_text()

    def open_book(self):
        filename = filedialog.askopenfilename(filetypes=[("Books and text", "*.epub *.txt *.md *.markdown"), ("All files", "*")])
        if filename:
            try:
                self.set_book(load_book(filename))
            except AudioPodError as exc:
                messagebox.showerror("Could not open book", str(exc))

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
        if self.book and self.chapters.curselection():
            selected = self.chapters.curselection()
            active = self.chapters.index(tk.ACTIVE)
            index = active if active in selected else selected[0]
            self.preview.configure(state="normal")
            self.preview.delete("1.0", tk.END)
            self.preview.insert("1.0", self.book.chapters[index].text)
            self.preview.configure(state="disabled")

    def choose_model(self):
        filename = filedialog.askopenfilename(filetypes=[("Piper voice", "*.onnx")])
        if filename:
            self.model.set(filename)

    def choose_output(self):
        folder = filedialog.askdirectory(mustexist=False)
        if folder:
            self.output.set(folder)

    def start(self, work):
        self.busy = True
        self.cancel.clear()
        self.progress["value"] = 0
        for widget in self.controls:
            widget.configure(state="disabled")
        self.stop.configure(state="normal")
        def run():
            try:
                result = work()
                self.events.put(("done", result))
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
            settings = Settings(float(self.speed.get()), int(self.speaker.get()), 4, "wav" if preview else self.format.get())
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
        self.start(lambda: render_book(book, model, Path(output).expanduser(), settings, selected, resume,
                                      lambda e: self.events.put(("progress", e)), self.cancel.is_set))

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "progress":
                    self.status.set(value["message"])
                    self.progress["value"] = value["fraction"]
                else:
                    self.busy = False
                    for widget in self.controls:
                        widget.configure(state="readonly" if isinstance(widget, ttk.Combobox) else "normal")
                    self.stop.configure(state="disabled")
                    if kind == "done":
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
        except queue.Empty:
            pass
        if self.closing and not self.busy:
            self.root.destroy()
            return
        self.root.after(100, self.poll)

    def open_player(self):
        if self.player:
            webbrowser.open(self.player.resolve().as_uri())

    def close(self):
        if self.busy:
            self.closing = True
            self.cancel.set()
            self.status.set("Stopping safely; the window will close when the current audio chunk or download read finishes…")
        else:
            self.root.destroy()


def launch():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise AudioPodError(f"Desktop could not open: {exc}. Use the CLI in headless sessions.") from exc
    App(root)
    root.mainloop()
    return 0
