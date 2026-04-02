import RPi.GPIO as GPIO
import time

PIN = 7  # change if needed

GPIO.setmode(GPIO.BCM)
GPIO.setup(PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

pulse_count = 0
last_pulse_time = 0

DIGIT_TIMEOUT = 0.7  # seconds: gap that signals end of a digit

def pulse_callback(channel):
    global pulse_count, last_pulse_time
    pulse_count += 1
    last_pulse_time = time.time()

GPIO.add_event_detect(PIN, GPIO.FALLING, callback=pulse_callback, bouncetime=5)

print("Ready to dial...")

try:
    while True:
        if pulse_count > 0:
            # wait until pulses stop
            if time.time() - last_pulse_time > DIGIT_TIMEOUT:
                digit = pulse_count if pulse_count < 10 else 0
                print(f"Dialed digit: {digit}")
                pulse_count = 0

        time.sleep(0.01)

except KeyboardInterrupt:
    GPIO.cleanup()
