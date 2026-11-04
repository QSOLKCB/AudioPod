#!/bin/sh
# Linux launcher; run the one-time installation first.
cd -- "$(dirname -- "$0")" || exit 1
PATH="$HOME/.local/bin:$PATH"
export PATH
if ! uv run --offline --locked audiopod gui; then
    printf '\nAudioPod could not start. See docs/INSTALLATION.md for setup instructions.\n' >&2
    exit 1
fi
