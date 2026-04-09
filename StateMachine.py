import time
import signal
import sys
import json
import os
from datetime import datetime
from gpiozero import Button
from openai import OpenAI
import sounddevice as sd
import numpy as np
import scipy.io.wavfile as wav
import whisper


# -----------------------
# CONFIG
# -----------------------
LINES_CONFIG_PATH = "lines.json"
GPIO_PIN = 27
SAMPLE_RATE = 16000
RECORDING_DURATION = 5      # seconds per recording chunk
GAP_TIMEOUT = 0.3           # seconds between pulses to end a digit
NUMBER_TIMEOUT = 2.0        # seconds after last digit to trigger call

# -----------------------
# LOAD LINE CONFIG
# -----------------------
def load_lines(path: str) -> dict:
    """Load the lines config from JSON. Edit lines.json to add or change lines."""
    with open(path) as f:
        return json.load(f)


# -----------------------
# AUDIO / STT
# -----------------------
_whisper_model = None

def get_whisper_model():
    """Lazy-load Whisper so startup is fast."""
    global _whisper_model
    if _whisper_model is None:
        print("Loading Whisper model...")
        _whisper_model = whisper.load_model("tiny")
    return _whisper_model

def record_audio() -> np.ndarray:
    print("  [mic] Listening...")
    audio = sd.rec(
        int(RECORDING_DURATION * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
    )
    sd.wait()
    return audio

def save_audio(audio: np.ndarray, filename: str = "temp.wav"):
    wav.write(filename, SAMPLE_RATE, audio)

def transcribe(filename: str = "temp.wav") -> str:
    result = get_whisper_model().transcribe(filename)
    return result["text"].strip()

def speak(text: str, voice: str = "en"):
    """Text-to-speech via espeak. Swap this out for piper/mimic for better quality."""
    safe = text.replace('"', '\\"')
    os.system(f'espeak -v {voice} "{safe}"')


# -----------------------
# INFO HANDLERS
# -----------------------
def handle_info_time():
    now = datetime.now().strftime("%H:%M")
    message = f"The time is {now}"
    print(f"  [info] {message}")
    speak(message)

def handle_info_speaking_clock():
    now = datetime.now()
    h = now.strftime("%I").lstrip("0")
    m = now.strftime("%M")
    period = now.strftime("%p")
    if m == "00":
        message = f"At the third stroke, the time will be {h} o'clock {period}."
    else:
        message = f"At the third stroke, the time will be {h} {m} {period}."
    print(f"  [clock] {message}")
    speak(message)
    speak("beep. beep. beep.")

INFO_HANDLERS = {
    "time": handle_info_time,
    "speaking_clock": handle_info_speaking_clock,
}


# -----------------------
# LINE HANDLER (AI lines)
# -----------------------
class LineHandler:
    """
    Handles one AI phone line. Each line has its own system prompt
    (loaded from lines.json) but shares the same record→STT→LLM→TTS loop.
    """

    def __init__(self, config: dict):
        self.name = config.get("name", "Assistant")
        self.system_prompt = config.get(
            "system_prompt", "You are a helpful assistant. Keep responses brief."
        )
        self.voice = config.get("voice", "en")
        self.model = config.get("model", "gpt-3.5-turbo")
        self.client = OpenAI()  # reads OPENAI_API_KEY from env

    def run(self):
        print(f"\n  [call] Connected to '{self.name}'")
        speak(f"You are connected to {self.name}.", voice=self.voice)

        messages = []

        while True:
            try:
                audio = record_audio()
                save_audio(audio)

                print("  [stt] Transcribing...")
                user_text = transcribe()

                if not user_text:
                    print("  [stt] Nothing heard, listening again...")
                    continue

                print(f"  [user] {user_text}")

                messages.append({"role": "user", "content": user_text})

                response = self.client.chat.completions.create(
                    model=self.model,
                    max_tokens=256,
                    messages=[{"role": "system", "content": self.system_prompt}] + messages,
                )

                reply_text = response.choices[0].message.content
                print(f"  [{self.name}] {reply_text}")

                messages.append({"role": "assistant", "content": reply_text})

                speak(reply_text, voice=self.voice)

            except KeyboardInterrupt:
                print("  [call] Caller hung up.")
                break
            except Exception as e:
                print(f"  [error] {e}")
                speak("Sorry, there was a problem. Please try again.", voice=self.voice)
                break


# -----------------------
# ROUTER
# -----------------------
def dispatch(number: str, lines: dict):
    """Look up the dialled number in lines.json and run the right handler."""
    config = lines.get(number)

    if config is None:
        print(f"  [router] No line for number '{number}'")
        speak("Number not recognised. Please try again.")
        return

    line_type = config.get("type", "ai")
    print(f"  [router] Routing to: {config.get('name', number)} (type={line_type})")

    if line_type == "info":
        # Info lines call a named Python function
        handler_name = config.get("handler", "time")
        handler_fn = INFO_HANDLERS.get(handler_name, handle_info_time)
        handler_fn()

    elif line_type == "ai":
        handler = LineHandler(config)
        handler.run()

    else:
        speak(f"Line type {line_type} is not supported.")


# -----------------------
# STATE MACHINE
# -----------------------
IDLE = "IDLE"
DIALING = "DIALING"
PROCESSING = "PROCESSING"
IN_CALL = "IN_CALL"


class Switchboard:
    def __init__(self):
        self.state = IDLE
        self.lines = load_lines(LINES_CONFIG_PATH)

        self.pulse_count = 0
        self.last_pulse_time = time.time()
        self.dialled_number = ""
        self.last_digit_time = time.time()

        self.gpio = Button(GPIO_PIN, pull_up=False)
        self.gpio.when_pressed = self._on_pulse

        signal.signal(signal.SIGINT, self._cleanup)
        signal.signal(signal.SIGTERM, self._cleanup)

        print(f"Switchboard ready. {len(self.lines)} line(s) loaded:")
        for num, cfg in self.lines.items():
            print(f"  Dial {num}  ->  {cfg.get('name', '?')}  -  {cfg.get('description', '')}")

    # ---- GPIO ----

    def _on_pulse(self):
        self.pulse_count += 1
        self.last_pulse_time = time.time()
        if self.state == IDLE:
            self.state = DIALING

    # ---- Main loop ----

    def run(self):
        while True:
            self._tick()
            time.sleep(0.02)

    def _tick(self):
        now = time.time()

        # Decode a digit once the inter-pulse gap has expired
        if self.pulse_count > 0 and (now - self.last_pulse_time > GAP_TIMEOUT):
            digit = 0 if (self.pulse_count - 1) == 10 else (self.pulse_count - 1) 
            self.dialled_number += str(digit)
            self.last_digit_time = now
            print(f"  [dial] digit={digit}  number so far={self.dialled_number}")
            self.pulse_count = 0

        # Commit the number once dialling has gone quiet
        if (
            self.state == DIALING
            and self.dialled_number
            and (now - self.last_digit_time > NUMBER_TIMEOUT)
        ):
            self.state = PROCESSING

        # Dispatch
        if self.state == PROCESSING:
            print(f"\n[switchboard] Dialled: {self.dialled_number}")
            self.state = IN_CALL
            dispatch(self.dialled_number, self.lines)
            self._reset()

    def _reset(self):
        self.dialled_number = ""
        self.pulse_count = 0
        self.state = IDLE
        print("\n[switchboard] Ready.\n")

    # ---- Cleanup ----

    def _cleanup(self, sig=None, frame=None):
        print("\n[switchboard] Shutting down...")
        self.gpio.close()
        sys.exit(0)


# -----------------------
# ENTRY POINT
# -----------------------
if __name__ == "__main__":
    board = Switchboard()
    board.run()
