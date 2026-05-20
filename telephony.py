import subprocess
import threading
import time
from pathlib import Path

try:
    import simpleaudio as sa
except ImportError:
    sa = None


SOUNDS_DIR = Path(__file__).parent / "sounds"


class LoopingSound:
    def __init__(self, filename: str):
        self.path = SOUNDS_DIR / filename
        self._stop_event = threading.Event()
        self._thread = None
        self._process = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return

        if not self.path.exists():
            print(f"[telephony] Missing sound: {self.path}")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()

        process = self._process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except Exception:
                pass

        self._process = None

    def _run(self):
        while not self._stop_event.is_set():
            try:
                process = subprocess.Popen(
                    ["aplay", "-q", str(self.path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

                self._process = process

                while not self._stop_event.is_set():
                    current = self._process
                    if current is None:
                        break

                    if current.poll() is not None:
                        break

                    time.sleep(0.02)

                if self._stop_event.is_set():
                    try:
                        process.terminate()
                    except Exception:
                        pass

            except Exception as e:
                print(f"[telephony] Looping sound failed: {e}")
                time.sleep(0.5)

        self._process = None


_dial_tone = LoopingSound("dialtone.wav")
_ringback = LoopingSound("ringback.wav")

_pulse_click = None
_pickup_sound = None
_hangup_sound = None


def _load_wave(filename: str):
    if sa is None:
        return None

    path = SOUNDS_DIR / filename

    if not path.exists():
        print(f"[telephony] Missing sound: {path}")
        return None

    try:
        return sa.WaveObject.from_wave_file(str(path))
    except Exception as e:
        print(f"[telephony] Could not load {filename}: {e}")
        return None


def _play_wave(wave, filename: str):
    if wave is None:
        play_one_shot_aplay(filename)
        return

    try:
        wave.play()
    except Exception as e:
        print(f"[telephony] Could not play {filename}: {e}")


def preload_sounds():
    global _pulse_click, _pickup_sound, _hangup_sound

    _pulse_click = _load_wave("pulse_click.wav")
    _pickup_sound = _load_wave("pickup.wav")
    _hangup_sound = _load_wave("hangup.wav")


def play_one_shot_aplay(filename: str):
    path = SOUNDS_DIR / filename

    if not path.exists():
        print(f"[telephony] Missing sound: {path}")
        return

    try:
        subprocess.Popen(
            ["aplay", "-q", str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        print(f"[telephony] Failed to play {filename}: {e}")


def start_dial_tone():
    _dial_tone.start()


def stop_dial_tone():
    _dial_tone.stop()


def start_ringback():
    _ringback.start()


def stop_ringback():
    _ringback.stop()


def play_pulse_click():
    global _pulse_click

    if _pulse_click is None:
        _pulse_click = _load_wave("pulse_click.wav")

    _play_wave(_pulse_click, "pulse_click.wav")


def play_pickup():
    global _pickup_sound

    if _pickup_sound is None:
        _pickup_sound = _load_wave("pickup.wav")

    _play_wave(_pickup_sound, "pickup.wav")


def play_hangup():
    global _hangup_sound

    if _hangup_sound is None:
        _hangup_sound = _load_wave("hangup.wav")

    _play_wave(_hangup_sound, "hangup.wav")


def stop_all_telephony_sounds():
    stop_dial_tone()
    stop_ringback()
