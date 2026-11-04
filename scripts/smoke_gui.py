"""Exercise actual Tk widgets and the worker loop (run under Xvfb on Linux CI)."""
from pathlib import Path
import tempfile
import time
import tkinter as tk

from audiopod.books import load_book
from audiopod.gui import App

root = tk.Tk()
app = App(root)
app.set_book(load_book(Path(__file__).resolve().parents[1] / 'examples/first-listen.md'))
root.update()
assert app.chapters.size() == 2
assert len(app.chapters.curselection()) == 2
assert 'workshop' in app.preview.get('1.0', tk.END).lower()
app.chapters.selection_clear(0, tk.END)
app.chapters.selection_set(1)
app.chapters.activate(1)
app.preview_text()
assert 'clouds' in app.preview.get('1.0', tk.END)
with tempfile.TemporaryDirectory() as temp:
    player = Path(temp) / 'listen.html'
    player.write_text('<p>Test</p>')
    app.start(lambda: player)
    deadline = time.monotonic() + 10
    while app.busy and time.monotonic() < deadline:
        root.update()
        time.sleep(.02)
    assert not app.busy and app.player == player
    assert str(app.listen['state']) == 'normal'
    assert app.root.winfo_width() >= 800
root.destroy()
print('Tk import, selection, preview, worker completion and listening control passed.')
