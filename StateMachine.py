import time
import signal
import sys
from gpiozero import Button
import os
from datetime import datetime

# -----------------------
# GPIO SETUP
# -----------------------
pulse_input = Button(27, pull_up=False)

# -----------------------
# STATE MACHINE
# -----------------------
IDLE = "IDLE"
DIALING = "DIALING"
PROCESSING = "PROCESSING"
IN_CALL = "IN_CALL"

state = IDLE

# -----------------------
# PULSE VARIABLES
# -----------------------
count = 0
last_pulse_time = time.time()

GAP_TIMEOUT = 0.3
NUMBER_TIMEOUT = 2

number = ""
last_digit_time = time.time()

# -----------------------
# ACTIONS (ROUTES)
# -----------------------
def tell_time():
    now = datetime.now().strftime("%H:%M")
    print(f"The time is {now}")
    os.system(f'espeak "The time is {now}"')

def tell_weather():
    os.system('espeak "Weather service not ready"')

def chatgpt_mode():
    os.system('espeak "Chat mode not ready"')

ROUTES = {
    "1": tell_time,
    "2": tell_weather,
    "3": chatgpt_mode,
}

# -----------------------
# CLEANUP
# -----------------------
def cleanup(sig=None, frame=None):
    print("\nCleaning up GPIO...")
    pulse_input.close()
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

# -----------------------
# PULSE HANDLER
# -----------------------
def pulse_detected():
    global count, last_pulse_time, state

    count += 1
    last_pulse_time = time.time()

    if state == IDLE:
        state = DIALING

pulse_input.when_pressed = pulse_detected

# -----------------------
# MAIN LOOP
# -----------------------
print("Switchboard running...")

while True:
    time.sleep(0.01)

    # -----------------------
    # DIGIT DETECTION
    # -----------------------
    if count > 0 and (time.time() - last_pulse_time > GAP_TIMEOUT):

        # decode digit
        if count == 11:
            digit = 0
        else:
            digit = count - 1

        number += str(digit)
        last_digit_time = time.time()

        print(f"Digit: {digit} | Number: {number}")

        count = 0

    # -----------------------
    # NUMBER COMPLETE
    # -----------------------
    if state == DIALING and number and (time.time() - last_digit_time > NUMBER_TIMEOUT):
        state = PROCESSING

    # -----------------------
    # PROCESS NUMBER
    # -----------------------
    if state == PROCESSING:

        print(f"\nFinal number: {number}")

        if number in ROUTES:
            state = IN_CALL
            ROUTES[number]()
        else:
            os.system('espeak "Number not recognised"')
            state = IDLE

        number = ""

    # -----------------------
    # RETURN TO IDLE
    # -----------------------
    if state == IN_CALL:
        # For now, return immediately after action
        # Later: wait for hang-up detection
        state = IDLE
