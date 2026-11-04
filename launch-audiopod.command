#!/bin/sh
# macOS Finder launcher; run the one-time installation first.
cd -- "$(dirname -- "$0")" || exit 1
# Finder's shell may omit Homebrew and uv's usual installation directories.
PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
export PATH
if ! uv run --offline --locked audiopod gui; then
    printf '\nAudioPod could not start. See docs/INSTALLATION.md for setup instructions.\n'
    printf 'Press Enter to close. '
    read -r answer
    exit 1
fi
