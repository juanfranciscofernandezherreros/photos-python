"""
Prevents Windows from entering sleep mode while the pipeline is running.
Without this, if the PC is idle long enough (or the user locks it with
Win+L and the system decides to sleep per its power plan), execution pauses
midway along with the network connection to the phone.

Screen lock (Win+L) itself does NOT pause running processes — only actual
system sleep does. This module only prevents that sleep; it does not keep
the screen on or prevent the phone from locking its screen (that is a
phone-side setting).

On non-Windows systems, the functions are no-ops so the rest of the code
works the same on any platform.
"""
from __future__ import annotations

import contextlib
import sys
from typing import Iterator

# Flags de la API de Windows (kernel32.SetThreadExecutionState)
_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001


@contextlib.contextmanager
def prevent_sleep() -> Iterator[None]:
    """While this `with` block is active, asks Windows not to sleep the
    system. On exit (even on exception), it is automatically reverted so
    the PC is not left "awake forever" by accident."""
    if sys.platform != "win32":
        yield
        return

    import ctypes  # import local: solo hace falta en Windows

    try:
        ctypes.windll.kernel32.SetThreadExecutionState(  # type: ignore[attr-defined]
            _ES_CONTINUOUS | _ES_SYSTEM_REQUIRED
        )
        yield
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS)  # type: ignore[attr-defined]
