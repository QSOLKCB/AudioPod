"""Exercise actual Tk widgets and the worker loop (run under Xvfb on Linux CI)."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import time
import tkinter as tk
from unittest.mock import patch

from audiopod import AudioPodError
from audiopod.books import load_book
from audiopod.gui import App
from audiopod.preferences import load_preferences
from audiopod.render import Settings
from audiopod.prosody import NATURAL, ORIGINAL


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
    assert app.profile.get() == 'Natural' and str(app.pause_control['state']) == 'readonly'
    app.pause_scale.set('1.25')
    app.resize_text(3)
    assert load_preferences()['threads'] == 2
    assert load_preferences()['font_size'] == 14
    assert load_preferences()['profile'] == NATURAL and load_preferences()['pause_scale'] == 1.25
    app.profile.set('Original')
    assert app.pause_scale.get() == '1.0' and str(app.pause_control['state']) == 'disabled'
    # Large reading text must not enlarge or hide the narration controls.
    for _ in range(12):
        app.resize_text(1)
    root.update()
    assert app.reading_font.cget('size') == 24
    assert app.stop.winfo_rooty() + app.stop.winfo_height() < root.winfo_rooty() + root.winfo_height()
    preview_folder = Path(temp) / 'preview'
    preview_folder.mkdir()
    player = preview_folder / 'listen.html'
    player.write_text('<p>Test</p>')
    app.start(lambda: player)
    finish_worker(root, app)
    assert not app.busy and app.player == player
    assert str(app.listen['state']) == 'normal'
    assert str(app.pause_control['state']) == 'disabled'  # Worker completion respects Original.
    # A new source must never leave Listen pointing at the previous book.
    app.start(lambda: book, result_kind='book')
    finish_worker(root, app)
    assert app.player is None and str(app.listen['state']) == 'disabled'
    # Restoring another job after a preview must reset both listening/output targets.
    app.start(lambda: player)
    finish_worker(root, app)
    assert app.player == player and str(app.listen['state']) == 'normal'
    original_output = app.output.get()
    with patch('audiopod.gui.filedialog.askdirectory', return_value=''):
        app.restore_job()
    assert app.player == player and app.output.get() == original_output
    folder = Path(temp) / 'saved-job'
    folder.mkdir()
    with patch('audiopod.gui.filedialog.askdirectory', return_value=str(folder)), patch('audiopod.gui.resume_options', side_effect=AudioPodError('Invalid saved job')), patch('audiopod.gui.messagebox.showerror') as error:
        app.restore_job()
    error.assert_called_once()
    assert app.player == player and app.output.get() == original_output
    assert str(app.listen['state']) == 'normal'
    saved = Settings(speed=1.25, threads=2, format='wav', pause_scale=1.5)
    with patch('audiopod.gui.filedialog.askdirectory', return_value=str(folder)), patch('audiopod.gui.resume_options', return_value=(book, saved, [1])):
        app.restore_job()
    assert app.chapters.curselection() == (1,)
    assert app.resume.get() and app.output.get() == str(folder)
    assert app.speed.get() == '1.25' and app.threads.get() == '2'
    assert app.profile.get() == 'Natural' and app.pause_scale.get() == '1.5'
    assert str(app.pause_control['state']) == 'readonly'
    assert app.player is None and app.render_output is None
    assert str(app.listen['state']) == 'disabled'
    with patch('audiopod.gui.webbrowser.open') as browser:
        app.open_player()
    browser.assert_not_called()
    with patch('audiopod.gui.os.startfile', create=True) as startfile, patch('audiopod.gui.subprocess.Popen') as popen:
        app.open_output()
    if sys.platform == 'win32':
        startfile.assert_called_once_with(folder)
        popen.assert_not_called()
    else:
        popen.assert_called_once_with(['open' if sys.platform == 'darwin' else 'xdg-open', str(folder)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        startfile.assert_not_called()
    # A successful verify/render completion enables Listen for the restored job.
    restored_player = folder / 'listen.html'
    restored_player.write_text('<p>Restored job</p>')
    app.start(lambda: restored_player)
    finish_worker(root, app)
    assert app.player == restored_player and str(app.listen['state']) == 'normal'
    with patch('audiopod.gui.webbrowser.open') as browser:
        app.open_player()
    browser.assert_called_once_with(restored_player.resolve().as_uri())
    with patch('audiopod.gui.filedialog.askdirectory', return_value=str(folder)), patch('audiopod.gui.resume_options', return_value=(book, Settings(profile=ORIGINAL), [0])):
        app.restore_job()
    assert app.profile.get() == 'Original' and app.pause_scale.get() == '1.0'
    assert str(app.pause_control['state']) == 'disabled'
    app.help()
    root.update()
    assert any(isinstance(child, tk.Toplevel) for child in root.winfo_children())
    root.destroy()
print('Tk selection, reading size, delivery/pause preferences, workers, restored targets/settings and help passed.')
