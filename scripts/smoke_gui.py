"""Exercise actual Tk widgets and the worker loop (run under Xvfb on Linux CI)."""
from pathlib import Path
import os
import tempfile
import time
import tkinter as tk
from unittest.mock import patch

from audiopod.books import load_book
from audiopod.gui import App
from audiopod.preferences import load_preferences
from audiopod.render import Settings


def finish_worker(root, app):
    deadline = time.monotonic() + 10
    while app.busy and time.monotonic() < deadline:
        root.update()
        time.sleep(.02)
    assert not app.busy, 'Worker did not return to idle'


with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'AUDIOPOD_DATA_HOME': temp}):
    root = tk.Tk()
    app = App(root)
    book = load_book(Path(__file__).resolve().parents[1] / 'examples/first-listen.md')
    app.set_book(book)
    root.update()
    assert app.chapters.size() == 2
    assert len(app.chapters.curselection()) == 2
    assert 'workshop' in app.preview.get('1.0', tk.END).lower()
    app.select_sections(False)
    assert '0/2 sections' in app.info.get() and '0 min' in app.info.get()
    assert not app.preview.get('1.0', 'end-1c')
    app.chapters.selection_set(1)
    app.chapters.activate(1)
    app.preview_text()
    assert 'clouds' in app.preview.get('1.0', tk.END)
    app.threads.set('2')
    app.resize_text(3)
    assert load_preferences()['threads'] == 2
    assert load_preferences()['font_size'] == 14
    # Large reading text must not enlarge or hide the narration controls.
    for _ in range(12):
        app.resize_text(1)
    root.update()
    assert app.reading_font.cget('size') == 24
    assert app.stop.winfo_rooty() + app.stop.winfo_height() < root.winfo_rooty() + root.winfo_height()
    player = Path(temp) / 'listen.html'
    player.write_text('<p>Test</p>')
    app.start(lambda: player)
    finish_worker(root, app)
    assert not app.busy and app.player == player
    assert str(app.listen['state']) == 'normal'
    # A new source must never leave Listen pointing at the previous book.
    app.start(lambda: book, result_kind='book')
    finish_worker(root, app)
    assert app.player is None and str(app.listen['state']) == 'disabled'
    saved = Settings(speed=1.25, threads=2, format='wav')
    with patch('audiopod.gui.filedialog.askdirectory', return_value=temp), patch('audiopod.gui.resume_options', return_value=(book, saved, [1])):
        app.restore_job()
    assert app.chapters.curselection() == (1,)
    assert app.resume.get() and app.output.get() == temp
    assert app.speed.get() == '1.25' and app.threads.get() == '2'
    app.help()
    root.update()
    assert any(isinstance(child, tk.Toplevel) for child in root.winfo_children())
    root.destroy()
print('Tk selection, accessible reading size, saved preferences, workers, resume controls and help passed.')
