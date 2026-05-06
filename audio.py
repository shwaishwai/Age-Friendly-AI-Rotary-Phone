import sys
import threading
import subprocess
import asyncio
from pathlib import Path

import numpy as np
import scipy.io.wavfile as wav
import sounddevice as sd
import whisper

try:
    import webrtcvad
except ImportError:
    import webrtcvad_wheels as webrtcvad

from openai import OpenAI

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SAMPLE_RATE = 16000
FRAME_DURATION = 30
FRAME_SIZE = int(SAMPLE_RATE * FRAME_DURATION / 1000)
SILENCE_TIMEOUT = 1.2
VAD_AGGRESSIVENESS = 2

_whisper_model = None
_tts_client = None
_vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)


def clean_text(text: str) -> str:
    if not text:
        return ""

    replacements = {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\xa0": " ",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)

    return " ".join(text.split())


def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        print("Loading Whisper model...")
        # base is better than tiny for Irish/Gaeilge. Use tiny if the Pi is too slow.
        _whisper_model = whisper.load_model("base")
    return _whisper_model


def get_tts_client():
    global _tts_client
    if _tts_client is None:
        _tts_client = OpenAI()
    return _tts_client


def record_until_silence(hangup_event: threading.Event, max_duration: int = 30) -> np.ndarray | None:
    print("  [mic] Listening...")

    frames_per_second = 1000 // FRAME_DURATION
    silence_frames_needed = int(SILENCE_TIMEOUT * frames_per_second)
    max_frames = max_duration * frames_per_second

    audio_buffer = []
    silence_count = 0
    speech_started = False

    with sd.RawInputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        blocksize=FRAME_SIZE
    ) as stream:
        for _ in range(max_frames):
            if hangup_event.is_set():
                return None

            raw, _ = stream.read(FRAME_SIZE)
            frame = bytes(raw)
            is_speech = _vad.is_speech(frame, SAMPLE_RATE)

            if is_speech:
                if not speech_started:
                    print("  [mic] Speech detected")
                    speech_started = True
                silence_count = 0
                audio_buffer.append(np.frombuffer(frame, dtype=np.int16))

            elif speech_started:
                audio_buffer.append(np.frombuffer(frame, dtype=np.int16))
                silence_count += 1
                if silence_count >= silence_frames_needed:
                    print("  [mic] Silence detected -- end of utterance")
                    break

    if not audio_buffer:
        return None

    return np.concatenate(audio_buffer)


def save_audio(audio: np.ndarray, filename: str = "temp.wav"):
    wav.write(filename, SAMPLE_RATE, audio)


def transcribe_audio(audio: np.ndarray, language: str | None = None, prompt: str | None = None) -> str:
    audio_float = audio.astype(np.float32) / 32768.0

    kwargs = {"fp16": False}
    if language:
        kwargs["language"] = language
    if prompt:
        kwargs["initial_prompt"] = prompt

    try:
        result = get_whisper_model().transcribe(audio_float, **kwargs)
    except ValueError as e:
        if "Unsupported language" in str(e):
            print(f"  [stt] Language {language!r} not supported, falling back to auto-detect.")
            kwargs.pop("language", None)
            result = get_whisper_model().transcribe(audio_float, **kwargs)
        else:
            raise

    return clean_text(result["text"].strip())


def _play_mp3(path: Path):
    subprocess.run(["mpg123", "-q", str(path)], check=False)


def speak_openai(text: str, voice: str = "alloy", model: str = "gpt-4o-mini-tts"):
    out_path = Path("speech.mp3")
    client = get_tts_client()

    with client.audio.speech.with_streaming_response.create(
        model=model,
        voice=voice,
        input=text,
    ) as response:
        response.stream_to_file(out_path)

    _play_mp3(out_path)


async def _edge_tts_to_file(text: str, voice: str, out_path: Path):
    import edge_tts
    communicate = edge_tts.Communicate(text=text, voice=voice)
    await communicate.save(str(out_path))


def speak_edge(text: str, voice: str = "en-IE-EmilyNeural"):
    """
    Edge TTS can sometimes fail with NoAudioReceived if a voice is unavailable,
    the network hiccups, or Edge rejects a parameter.

    Do not crash the call thread. Try the requested voice first, then fall back
    to a safe UK voice, then to OpenAI TTS if available.
    """
    out_path = Path("speech.mp3")
    fallback_voice = "en-GB-RyanNeural"

    try:
        asyncio.run(_edge_tts_to_file(text, voice, out_path))
        _play_mp3(out_path)
        return

    except Exception as e:
        print(f"  [edge-tts error] Voice {voice!r} failed: {clean_text(str(e))}")

    if voice != fallback_voice:
        try:
            print(f"  [edge-tts fallback] Trying {fallback_voice}")
            asyncio.run(_edge_tts_to_file(text, fallback_voice, out_path))
            _play_mp3(out_path)
            return

        except Exception as e:
            print(f"  [edge-tts fallback error] {clean_text(str(e))}")

    try:
        print("  [tts fallback] Trying OpenAI TTS")
        speak_openai(text, voice="alloy", model="gpt-4o-mini-tts")

    except Exception as e:
        print(f"  [tts failed] {clean_text(str(e))}")


def speak(
    text: str,
    voice: str = "alloy",
    model: str = "gpt-4o-mini-tts",
    tts_engine: str = "openai",
):
    text = clean_text(text)
    engine = (tts_engine or "openai").lower().strip()

    print(f"  [tts:{engine}:{voice}] {text}")

    if not text:
        return

    if engine == "edge":
        speak_edge(text, voice=voice)
    else:
        speak_openai(text, voice=voice, model=model)
