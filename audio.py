import os
import numpy as np
import scipy.io.wavfile as wav
import sounddevice as sd
import whisper
from gtts import gTTS

SAMPLE_RATE = 16000
RECORDING_DURATION = 5  # seconds per recording chunk

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
    """TTS via gTTS — much more natural than espeak."""
    print(f"  [tts] {text}")
    tts = gTTS(text=text, lang="en", tld="com.au")
    tts.save("speech.mp3")
    os.system("mpg123 speech.mp3")
