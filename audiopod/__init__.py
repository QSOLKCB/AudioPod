"""AudioPod: local books, local voices, local audio."""

import os

# ORT reads this at native-library initialization, before its Python API can run.
# Force the lifetime opt-out before importing Piper/ONNX Runtime anywhere in the app.
os.environ["ORT_DISABLE_TELEMETRY"] = "1"

__version__ = "0.1.0"


class AudioPodError(Exception):
    """An actionable input, setup, or rendering error."""


class Cancelled(AudioPodError):
    """Rendering stopped at a safe boundary."""
