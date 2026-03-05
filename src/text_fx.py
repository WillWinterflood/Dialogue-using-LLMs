"""
src/text_fx.py

Small CLI effect on the text to help people read it better and for better user experience...
"""
import os
import time

DEFAULT_CHAR_DELAY_SECONDS = os.getenv("TYPEWRITER_CHAR_DELAY", "0.05")
DEFAULT_LINE_PAUSE_SECONDS = os.getenv("TYPEWRITER_LINE_PAUSE", "0.5")

def _safe_float(raw_value, fallback):
    try:
        value = float(raw_value)
    except Exception:
        value = fallback
    return max(0.0, value)

def type_line(text, char_delay=None, line_pause=None):
    """
    Print a line one character at a time.

    Use env vars to tune speed:
    - TYPEWRITER_CHAR_DELAY
    - TYPEWRITER_LINE_PAUSE
    """
    delay = _safe_float(
        DEFAULT_CHAR_DELAY_SECONDS if char_delay is None else char_delay,
        fallback=0.008,
    )
    pause = _safe_float(
        DEFAULT_LINE_PAUSE_SECONDS if line_pause is None else line_pause,
        fallback=0.03,
    )

    message = str(text)
    if delay <= 0:
        print(message)
    else:
        for ch in message:
            print(ch, end="", flush=True)
            time.sleep(delay)
        print()

    if pause > 0:
        time.sleep(pause)

