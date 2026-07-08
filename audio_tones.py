"""
Audio tones for the Age Friendly AI rotary phone project.

- Solid off-hook tone while the handset is lifted and no number has started.
- UK/Ireland-style ringback tone while "calling" a line.

Requires:
    pip install numpy sounddevice
"""

import random
import threading
import time
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 44100
VOLUME = 0.25

# Solid tone heard when the phone is off the hook before dialling starts.
OFF_HOOK_TONE_FREQ = 440

# Ringback tone heard when making the call.
RINGBACK_FREQ = 400
RINGBACK_ON_1 = 0.4
RINGBACK_OFF_SHORT = 0.2
RINGBACK_ON_2 = 0.4
RINGBACK_OFF_LONG = 2.0


def _sine(freq: float, duration: float, volume: float = VOLUME) -> np.ndarray:
    samples = int(SAMPLE_RATE * duration)
    t = np.linspace(0, duration, samples, endpoint=False)
    return (volume * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _silence(duration: float) -> np.ndarray:
    return np.zeros(int(SAMPLE_RATE * duration), dtype=np.float32)


def make_solid_tone_chunk(duration: float = 0.25, volume: float = VOLUME) -> np.ndarray:
    return _sine(OFF_HOOK_TONE_FREQ, duration, volume)


def make_ringback_cycle(volume: float = VOLUME) -> np.ndarray:
    return np.concatenate([
        _sine(RINGBACK_FREQ, RINGBACK_ON_1, volume),
        _silence(RINGBACK_OFF_SHORT),
        _sine(RINGBACK_FREQ, RINGBACK_ON_2, volume),
        _silence(RINGBACK_OFF_LONG),
    ])


class TonePlayer:
    def __init__(self):
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def stop(self):
        self._stop_event.set()
        try:
            sd.stop()
        except Exception:
            pass

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)

        self._thread = None
        self._stop_event.clear()

    def start_solid_off_hook_tone(self, should_continue: Callable[[], bool]):
        """Start the solid off-hook tone in the background."""
        self.stop()

        def _worker():
            chunk = make_solid_tone_chunk(duration=0.25)
            while not self._stop_event.is_set() and should_continue():
                sd.play(chunk, SAMPLE_RATE)
                sd.wait()
            sd.stop()

        self._thread = threading.Thread(target=_worker, daemon=True)
        self._thread.start()

    def play_ringback_random(self, min_seconds: float = 2.0, max_seconds: float = 5.0):
        """Play ringback for a random length between min_seconds and max_seconds."""
        self.stop()
        self._stop_event.clear()

        duration = random.uniform(min_seconds, max_seconds)
        end_time = time.monotonic() + duration
        cycle = make_ringback_cycle()

        while time.monotonic() < end_time and not self._stop_event.is_set():
            sd.play(cycle, SAMPLE_RATE)
            sd.wait()

        sd.stop()


# Backwards-compatible helper names, useful for quick testing.
def play_off_hook_tone(duration: float = 3.0):
    start = time.monotonic()
    chunk = make_solid_tone_chunk()
    while time.monotonic() - start < duration:
        sd.play(chunk, SAMPLE_RATE)
        sd.wait()


def play_ringback(duration: Optional[float] = None):
    player = TonePlayer()
    if duration is None:
        player.play_ringback_random(2, 5)
    else:
        player.play_ringback_random(duration, duration)
