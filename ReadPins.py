from gpiozero import Button
import time
import signal
import sys

pulse_input = Button(17, pull_up=False)

count = 0
last_pulse_time = time.time()

GAP_TIMEOUT = 0.3  # seconds
number = ""

def pulse_detected():
    global count, last_pulse_time
    count += 1
    last_pulse_time = time.time()

pulse_input.when_pressed = pulse_detected

# ✅ cleanup function
def cleanup(sig=None, frame=None):
    print("\nCleaning up GPIO...")
    pulse_input.close()
    sys.exit(0)

# catch Ctrl+C and termination
signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

print("Listening for pulse bursts... (Ctrl+C to exit)")

while True:
    time.sleep(0.01)

    # detect end of burst
    if count > 0 and (time.time() - last_pulse_time > GAP_TIMEOUT):

        # decode digit
        if count == 11:
            digit = 0
        else:
            digit = count - 1

        number += str(digit)

        print(f"Digit: {digit} | Number so far: {number}")

        # reset for next burst
        count = 0
