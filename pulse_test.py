from gpiozero import Button
from signal import pause
import time
from threading import Timer

PIN = 27

ARM_DELAY = 0.15        # ignore pulses immediately after first movement
PULSE_GAP = 0.25        # gap after last valid pulse means digit is complete
NUMBER_TIMEOUT = 3.5

pulse_count = 0
number_buffer = ""
last_digit_time = 0

dial_active = False
armed_time = 0
digit_timer = None

dial = Button(PIN, pull_up=True, bounce_time=0.01)


def finish_digit():
    global pulse_count, number_buffer, last_digit_time, dial_active

    if pulse_count == 0:
        dial_active = False
        return

    now = time.time()

    if last_digit_time and now - last_digit_time > NUMBER_TIMEOUT:
        number_buffer = ""

    digit = "0" if pulse_count == 10 else str(pulse_count)

    number_buffer += digit
    last_digit_time = now

    print(f"Digit: {digit}")
    print(f"Number so far: {number_buffer}")
    print("---")

    pulse_count = 0
    dial_active = False


def pulse_detected():
    global pulse_count, digit_timer, dial_active, armed_time

    now = time.time()

    # First edge: assume this is caused by pulling the dial.
    # Start arming window but do not count it.
    if not dial_active:
        dial_active = True
        armed_time = now + ARM_DELAY
        print("Dial movement detected, arming...")
        return

    # Ignore early false pulse caused by pulling/settling
    if now < armed_time:
        print("Ignored early pulse")
        return

    pulse_count += 1
    print(f"Pulse {pulse_count}")

    if digit_timer:
        digit_timer.cancel()

    digit_timer = Timer(PULSE_GAP, finish_digit)
    digit_timer.start()


dial.when_pressed = pulse_detected

print("Listening on GPIO 27...")
pause()
