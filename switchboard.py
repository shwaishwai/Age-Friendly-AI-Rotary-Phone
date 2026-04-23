import time
import signal
import sys
import json
import threading
from gpiozero import Button
import os
sys.path.insert(0, os.path.dirname(__file__))
from router import Router

GPIO_PIN_PULSE = 27
GPIO_PIN_HOOK  = 22

GAP_TIMEOUT    = 0.3   # seconds between pulses to end a digit
NUMBER_TIMEOUT = 3.0   # seconds of silence after last digit to commit number

IDLE       = "IDLE"
DIALING    = "DIALING"
PROCESSING = "PROCESSING"
IN_CALL    = "IN_CALL"


class Switchboard:
    def __init__(self, lines_path: str = "lines.json"):
        self.lines = self._load_lines(lines_path)
        self.router = Router()

        self.state        = IDLE
        self.off_hook     = False
        self.hangup_event = threading.Event()
        self._hangup_timer = None             # debounce timer for on-hook

        self.pulse_count     = 0
        self.last_pulse_time = time.time()
        self.dialled_number  = ""
        self.last_digit_time = time.time()

        # Rotary dial pulse input
        self.pulse_gpio = Button(GPIO_PIN_PULSE, pull_up=False)
        self.pulse_gpio.when_pressed = self._on_pulse

        # Hook switch: pressed = handset lifted, released = handset replaced
        self.hook_gpio = Button(GPIO_PIN_HOOK, pull_up=False)
        self.hook_gpio.when_pressed  = self._on_off_hook
        self.hook_gpio.when_released = self._on_on_hook

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
        print("\nWaiting for handset to be lifted...\n")

    # ------------------------------------------------------------------
    # Hook callbacks (fire on GPIO background thread)
    # ------------------------------------------------------------------

    def _on_off_hook(self):
        """Handset lifted - cancel any pending hangup and mark as off hook."""
        if self._hangup_timer is not None:
            self._hangup_timer.cancel()
            self._hangup_timer = None
        self.off_hook = True
        self.hangup_event.clear()
        print("[hook] Off hook - ready to dial")

    def _on_on_hook(self):
        """Handset replaced - wait 100ms before committing the hangup."""
        def _commit_hangup():
            self.off_hook = False
            self.hangup_event.set()
            print("[hook] On hook - terminating call")
            self._reset()

        if self._hangup_timer is not None:
            self._hangup_timer.cancel()
        self._hangup_timer = threading.Timer(0.1, _commit_hangup)
        self._hangup_timer.start()

    # ------------------------------------------------------------------
    # Pulse callback (fires on GPIO background thread)
    # ------------------------------------------------------------------

    def _on_pulse(self):
        if not self.off_hook:
            return  # ignore pulses when on hook
        self.pulse_count += 1
        self.last_pulse_time = time.time()
        if self.state == IDLE:
            self.state = DIALING

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self):
        while True:
            self._tick()
            time.sleep(0.02)

    def _tick(self):
        now = time.time()

        # Only process dialling logic when off hook
        if not self.off_hook:
            return

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

        # Dispatch — passes hangup_event so the handler can exit early
        if self.state == PROCESSING:
            print(f"\n[switchboard] Dialled: {self.dialled_number}")
            self.state = IN_CALL
            self.router.dispatch(self.dialled_number, self.lines, self.hangup_event)
            self._reset()

    def _reset(self):
        self.dialled_number = ""
        self.pulse_count    = 0
        if self.state != IDLE:
            self.state = IDLE
            print("\n[switchboard] Ready.\n")

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def _cleanup(self, sig=None, frame=None):
        print("\n[switchboard] Shutting down...")
        if self._hangup_timer is not None:
            self._hangup_timer.cancel()
        self.pulse_gpio.close()
        self.hook_gpio.close()
        sys.exit(0)


if __name__ == "__main__":
    board = Switchboard(lines_path="lines.json")
    board.run()
