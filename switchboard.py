import time
import signal
import sys
import json
from gpiozero import Button
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from router import Router

GPIO_PIN = 27
GAP_TIMEOUT = 0.3   # seconds between pulses to end a digit
NUMBER_TIMEOUT = 3.0  # seconds of silence after last digit to commit number

IDLE       = "IDLE"
DIALING    = "DIALING"
PROCESSING = "PROCESSING"
IN_CALL    = "IN_CALL"


class Switchboard:
    def __init__(self, lines_path: str = "lines.json"):
        self.lines = self._load_lines(lines_path)
        self.router = Router()

        self.state = IDLE
        self.pulse_count = 0
        self.last_pulse_time = time.time()
        self.dialled_number = ""
        self.last_digit_time = time.time()

        self.gpio = Button(GPIO_PIN, pull_up=False)
        self.gpio.when_pressed = self._on_pulse

        signal.signal(signal.SIGINT, self._cleanup)
        signal.signal(signal.SIGTERM, self._cleanup)

        self._print_directory()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _load_lines(self, path: str) -> dict:
        with open(path) as f:
            return json.load(f)

    def _print_directory(self):
        print(f"Switchboard ready. {len(self.lines)} line(s) loaded:")
        for num, cfg in self.lines.items():
            print(f"  Dial {num}  ->  {cfg.get('name', '?')}  -  {cfg.get('description', '')}")

    # ------------------------------------------------------------------
    # GPIO
    # ------------------------------------------------------------------

    def _on_pulse(self):
        self.pulse_count += 1
        self.last_pulse_time = time.time()
        if self.state == IDLE:
            self.state = DIALING

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self):
        print("\nListening for pulses...\n")
        while True:
            self._tick()
            time.sleep(0.02)

    def _tick(self):
        now = time.time()

        # Decode a digit once the inter-pulse gap expires
        if self.pulse_count > 0 and (now - self.last_pulse_time > GAP_TIMEOUT):
            digit = 0 if self.pulse_count == 12 else self.pulse_count - 1
            self.dialled_number += str(digit)
            self.last_digit_time = now
            print(f"  [dial] digit={digit}  number so far={self.dialled_number}")
            self.pulse_count = 0

        # Commit the number once dialling has gone quiet
        if (
            self.state == DIALING
            and self.dialled_number
            and (now - self.last_digit_time > NUMBER_TIMEOUT)
        ):
            self.state = PROCESSING

        # Dispatch to the router
        if self.state == PROCESSING:
            print(f"\n[switchboard] Dialled: {self.dialled_number}")
            self.state = IN_CALL
            self.router.dispatch(self.dialled_number, self.lines)
            self._reset()

    def _reset(self):
        self.dialled_number = ""
        self.pulse_count = 0
        self.state = IDLE
        print("\n[switchboard] Ready.\n")

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def _cleanup(self, sig=None, frame=None):
        print("\n[switchboard] Shutting down...")
        self.gpio.close()
        sys.exit(0)


if __name__ == "__main__":
    board = Switchboard(lines_path="lines.json")
    board.run()
