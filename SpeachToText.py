import sounddevice as sd
import numpy as np
import scipy.io.wavfile as wav
import whisper

# Settings
SAMPLE_RATE = 16000
DURATION = 5  # seconds per recording

model = whisper.load_model("tiny")

def record_audio():
    print("Listening...")
    audio = sd.rec(int(DURATION * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype='int16')
    sd.wait()
    return audio

def save_audio(audio, filename="temp.wav"):
    wav.write(filename, SAMPLE_RATE, audio)

def transcribe(filename="temp.wav"):
    result = model.transcribe(filename)
    return result["text"]

try:
    while True:
        audio = record_audio()
        save_audio(audio)

        print("Processing...")
        text = transcribe()

        print("You said:", text)

except KeyboardInterrupt:
    print("\nStopped.")
