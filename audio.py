import sys
import threading
import subprocess
import asyncio
from pathlib import Path

import numpy as np
import scipy.io.wavfile as wav
import scipy.signal as signal
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

# The USB microphone records reliably at 48000 Hz.
# Whisper expects 16000 Hz audio, so we resample before transcription.
RECORD_SAMPLE_RATE = 48000
WHISPER_SAMPLE_RATE = 16000
SAMPLE_RATE = RECORD_SAMPLE_RATE
FRAME_DURATION = 30
FRAME_SIZE = int(SAMPLE_RATE * FRAME_DURATION / 1000)
SILENCE_TIMEOUT = 1.2
VAD_AGGRESSIVENESS = 2

# USB microphone device number from sounddevice.query_devices()
# Set to None to use the system default.
MIC_DEVICE = 1

# Your USB audio device reports 2 input channels.
# We record both and convert them to mono so the correct mic channel is not missed.
MIC_CHANNELS = 2

# Level-based speech detection.
# From your test, background RMS was often around 25-60 and speech/noise spikes were much higher.
# Raise MIC_START_RMS if it triggers too easily. Lower it if it misses your voice.
MIC_START_RMS = 120
MIC_CONTINUE_RMS = 80
MIC_MAX_UTTERANCE_SECONDS = 8
MIC_LEVEL_DEBUG = True

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
    print(f"  [mic] Using input device {MIC_DEVICE}:")
    print(sd.query_devices(MIC_DEVICE))

    frames_per_second = 1000 // FRAME_DURATION
    silence_frames_needed = int(SILENCE_TIMEOUT * frames_per_second)
    max_frames = max_duration * frames_per_second
    max_utterance_frames = int(MIC_MAX_UTTERANCE_SECONDS * frames_per_second)

    audio_buffer = []
    pre_roll = []
    silence_count = 0
    speech_started = False
    speech_frames = 0

    # Keep a small amount of audio from just before speech starts,
    # so the first word is not clipped.
    pre_roll_frames = int(0.30 * frames_per_second)

    level_print_interval = frames_per_second
    frames_seen = 0

    with sd.RawInputStream(
        device=MIC_DEVICE,
        samplerate=SAMPLE_RATE,
        channels=MIC_CHANNELS,
        dtype="int16",
        blocksize=FRAME_SIZE
    ) as stream:
        for _ in range(max_frames):
            if hangup_event.is_set():
                return None

            raw, _ = stream.read(FRAME_SIZE)
            samples = np.frombuffer(bytes(raw), dtype=np.int16)

            if MIC_CHANNELS > 1:
                samples = samples.reshape(-1, MIC_CHANNELS)
                channel_rms = np.sqrt(np.mean(samples.astype(np.float32) ** 2, axis=0))
                best_channel = int(np.argmax(channel_rms))
                mono = samples[:, best_channel].astype(np.int16)
            else:
                mono = samples.astype(np.int16)

            peak = int(np.max(np.abs(mono))) if mono.size else 0
            rms = float(np.sqrt(np.mean(mono.astype(np.float32) ** 2))) if mono.size else 0.0

            frames_seen += 1
            if MIC_LEVEL_DEBUG and frames_seen % level_print_interval == 0:
                status = "speech" if speech_started else "waiting"
                print(f"  [mic] Level peak={peak}, rms={rms:.1f}, status={status}")

            if not speech_started:
                pre_roll.append(mono.copy())
                if len(pre_roll) > pre_roll_frames:
                    pre_roll.pop(0)

                # Start recording when the RMS level rises above the speech threshold.
                if rms >= MIC_START_RMS:
                    print(f"  [mic] Speech detected, peak={peak}, rms={rms:.1f}")
                    speech_started = True
                    audio_buffer.extend(pre_roll)
                    pre_roll.clear()
                    audio_buffer.append(mono.copy())
                    speech_frames = 1

                continue

            # Speech has started. Keep recording.
            audio_buffer.append(mono.copy())
            speech_frames += 1

            # Stop if the user has been talking/noisy for too long.
            # This prevents the call from getting stuck listening forever.
            if speech_frames >= max_utterance_frames:
                print("  [mic] Max utterance length reached -- processing audio")
                break

            # End once the level has stayed low long enough.
            if rms < MIC_CONTINUE_RMS:
                silence_count += 1
                if silence_count >= silence_frames_needed:
                    print("  [mic] Silence detected -- end of utterance")
                    break
            else:
                silence_count = 0

    if not audio_buffer:
        print("  [mic] No speech captured")
        return None

    return np.concatenate(audio_buffer)


def resample_for_whisper(audio: np.ndarray) -> np.ndarray:
    """
    The USB mic records at 48000 Hz, but Whisper expects 16000 Hz.
    Convert before transcription so speech is not interpreted at the wrong speed.
    """
    if RECORD_SAMPLE_RATE == WHISPER_SAMPLE_RATE:
        return audio.astype(np.int16)

    audio_float = audio.astype(np.float32)
    resampled = signal.resample_poly(audio_float, WHISPER_SAMPLE_RATE, RECORD_SAMPLE_RATE)
    resampled = np.clip(resampled, -32768, 32767)
    return resampled.astype(np.int16)


def save_audio(audio: np.ndarray, filename: str = "temp.wav"):
    # Save the version Whisper will actually hear.
    audio_16k = resample_for_whisper(audio)
    wav.write(filename, WHISPER_SAMPLE_RATE, audio_16k)


def transcribe_audio(audio: np.ndarray, language: str | None = None, prompt: str | None = None) -> str:
    # Convert 48 kHz mic audio to 16 kHz before giving it to Whisper.
    audio_16k = resample_for_whisper(audio)
    audio_float = audio_16k.astype(np.float32) / 32768.0

    # Helpful debug file. You can play this after a failed call:
    #   aplay last_caller_audio.wav
    try:
        wav.write("last_caller_audio.wav", WHISPER_SAMPLE_RATE, audio_16k)
        print("  [stt] Saved captured audio to last_caller_audio.wav")
    except Exception as e:
        print(f"  [stt] Could not save debug audio: {clean_text(str(e))}")

    duration = len(audio_16k) / WHISPER_SAMPLE_RATE if len(audio_16k) else 0
    peak = int(np.max(np.abs(audio_16k))) if len(audio_16k) else 0
    rms = float(np.sqrt(np.mean(audio_16k.astype(np.float32) ** 2))) if len(audio_16k) else 0.0
    print(f"  [stt] Audio for Whisper: {duration:.2f}s, peak={peak}, rms={rms:.1f}")

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
