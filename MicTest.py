import sounddevice as sd
import numpy as np

def callback(indata, frames, time, status):
    volume_norm = np.linalg.norm(indata) * 10
    print(int(volume_norm))

# ✅ cleanup function
def cleanup(sig=None, frame=None):
    print("\nCleaning up GPIO...")
    pulse_input.close()
    sys.exit(0)

# catch Ctrl+C and termination
signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

print("Listening for pulse bursts... (Ctrl+C to exit)")


with sd.InputStream(callback=callback):
    print("Listening... Speak into the phone")
    while True:
        pass
