from gpiozero import Button
import time

# GPIO17 (pin 11)
pulse_input = Button(17, pull_up=False)

count = 0

def pulse_detected():
    global count
    count += 1

# rising edge (change to when_released for falling edge)
pulse_input.when_pressed = pulse_detected

print("Counting pulses...")

while True:
    count = 0
    start = time.time()

    # 5-second window
    while time.time() - start < 3.5:
        time.sleep(0.01)

    if count > 0:
        print(f"You have dialed number: {count - 1}")
