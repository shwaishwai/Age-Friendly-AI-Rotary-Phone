import json
import threading
import time
from pathlib import Path

from gpiozero import Button

from router import Router


# Correct pins for your current wiring
PULSE_PIN = 27
HOOK_PIN = 22

# Current hook logic:
# HIGH = off-hook / handset lifted
# LOW  = on-hook / handset down
HOOK_ACTIVE_HIGH = True

# Rotary dial pulse settings
PULSE_EDGE = "pressed"       # change to "released" if pulse_test.py shows that is better
PULSE_BOUNCE_SECONDS = 0.003

# Some dials send a false pulse when the dial is pulled toward a number.
# The first edge is treated as dial movement, then pulses are ignored briefly.
DIAL_ARM_DELAY_SECONDS = 0.15

# Gap after the last valid pulse before the pulse burst is considered a complete digit.
DIGIT_GAP_SECONDS = 0.35

# Gap after a completed digit before the number is treated as complete and routed.
# This allows multi-digit numbers such as 1191 to be entered before connecting.
NUMBER_GAP_SECONDS = 2.0

# Your hook line drops briefly while dialling, so do not reset immediately.
# It must stay on-hook this long before we reset.
HOOK_HANGUP_CONFIRM_SECONDS = 0.60


class Switchboard:
    def __init__(self, lines_path="lines.json"):
        self.lines = self._load_lines(lines_path)
        self.router = Router(self.lines)

        self.state = "ON_HOOK"
        self.number = ""
        self.pulse_count = 0
        self.last_pulse_at = None
        self.last_digit_at = None
        self.dial_active = False
        self.dial_armed_at = None
        self.last_digit_at = None
        self.dial_active = False
        self.dial_armed_at = None

        self.hangup_event = threading.Event()
        self.call_thread = None
        self.hook_check_active = False

        # Hook: HIGH = off-hook, LOW = on-hook
        self.hook = Button(
            HOOK_PIN,
            pull_up=False,
            bounce_time=0.03,
        )

        # Pulse: impulse contacts between GPIO 27 and GND
        self.pulse = Button(
            PULSE_PIN,
            pull_up=True,
            bounce_time=PULSE_BOUNCE_SECONDS,
        )

        self.hook.when_pressed = self._handset_lifted
        self.hook.when_released = self._possible_handset_down

        if PULSE_EDGE == "pressed":
            self.pulse.when_pressed = self._pulse_event
        elif PULSE_EDGE == "released":
            self.pulse.when_released = self._pulse_event
        else:
            raise ValueError('PULSE_EDGE must be "pressed" or "released"')

        # Start in the actual physical state
        if self.hook.is_pressed:
            self._handset_lifted()
        else:
            self._handset_down_confirmed()

    def _load_lines(self, path):
        p = Path(path)
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)

    # -----------------------------
    # Hook handling
    # -----------------------------

    def _handset_lifted(self):
        # Cancels any pending short hook-drop reset
        self.hook_check_active = False

        if self.state != "ON_HOOK":
            return

        print("\n[switchboard] Handset lifted")
        print("[switchboard] Waiting for number...")

        self.state = "WAITING_FOR_NUMBER"
        self.number = ""
        self.pulse_count = 0
        self.last_pulse_at = None
        self.last_digit_at = None
        self.dial_active = False
        self.dial_armed_at = None
        self.hangup_event.clear()

    def _possible_handset_down(self):
        if self.hook_check_active:
            return

        self.hook_check_active = True
        threading.Thread(target=self._confirm_handset_down, daemon=True).start()

    def _confirm_handset_down(self):
        time.sleep(HOOK_HANGUP_CONFIRM_SECONDS)

        self.hook_check_active = False

        # If the hook has gone high again, it was just a dial-related drop.
        if self.hook.is_pressed:
            print("[switchboard] Ignored brief hook drop")
            return

        self._handset_down_confirmed()

    def _handset_down_confirmed(self):
        if self.state != "ON_HOOK":
            print("\n[switchboard] Handset down - reset")
        else:
            print("[switchboard] On hook")

        self.hangup_event.set()

        self.state = "ON_HOOK"
        self.number = ""
        self.pulse_count = 0
        self.last_pulse_at = None
        self.last_digit_at = None
        self.dial_active = False
        self.dial_armed_at = None

    # -----------------------------
    # Pulse handling
    # -----------------------------

    def _pulse_event(self):
        if self.state not in ("WAITING_FOR_NUMBER", "DIALING", "NUMBER_PENDING"):
            return

        now = time.monotonic()

        # If another digit begins while a number is pending, keep building it.
        if self.state == "NUMBER_PENDING":
            self.state = "DIALING"

        # First edge after rest is usually caused by pulling the dial.
        # Do not count it as a real rotary return pulse.
        if not self.dial_active:
            self.dial_active = True
            self.dial_armed_at = now + DIAL_ARM_DELAY_SECONDS
            if self.state == "WAITING_FOR_NUMBER":
                self.state = "DIALING"
            print("[dial] Dial movement detected, arming...")
            return

        # Ignore any early pulse caused by pull/settling before the dial return.
        if self.dial_armed_at is not None and now < self.dial_armed_at:
            print("[dial] Ignored early pulse")
            return

        self.pulse_count += 1
        self.last_pulse_at = now

        print(f"[dial] Pulse count: {self.pulse_count}")

    def _finish_digit_if_ready(self):
        if self.state != "DIALING":
            return

        if self.pulse_count <= 0 or self.last_pulse_at is None:
            return

        if time.monotonic() - self.last_pulse_at < DIGIT_GAP_SECONDS:
            return

        raw_count = self.pulse_count
        self.pulse_count = 0
        self.last_pulse_at = None
        self.dial_active = False
        self.dial_armed_at = None

        # Rotary dial rule:
        # 1-9 pulses = digits 1-9
        # 10 pulses = digit 0
        digit = "0" if raw_count == 10 else str(raw_count)

        self.number += digit
        self.last_digit_at = time.monotonic()
        self.state = "NUMBER_PENDING"

        print(f"[dial] Digit received: {digit} from raw pulse count {raw_count}")
        print(f"[dial] Number so far: {self.number}")
        print(f"[dial] Waiting {NUMBER_GAP_SECONDS}s for another digit...")

    def _connect_number_if_ready(self):
        if self.state != "NUMBER_PENDING":
            return

        if not self.number or self.last_digit_at is None:
            return

        if time.monotonic() - self.last_digit_at < NUMBER_GAP_SECONDS:
            return

        number = self.number

        if number in self.lines:
            self._connect_number(number)
        else:
            print(f"[switchboard] No line configured for number: {number}")
            print("[switchboard] Waiting for number...")
            self.number = ""
            self.last_digit_at = None
            self.state = "WAITING_FOR_NUMBER"

    # -----------------------------
    # Routing
    # -----------------------------

    def _connect_number(self, number):
        if self.state == "CONNECTED":
            return

        line = self.lines[number]

        print(f"\n[switchboard] Matched number: {number}")
        print(f"[switchboard] Connecting to: {line.get('name', 'Unknown line')}")

        self.state = "CONNECTED"

        self.call_thread = threading.Thread(
            target=self.router.connect,
            args=(number, self.hangup_event),
            daemon=True,
        )
        self.call_thread.start()


    def _print_available_lines(self):
        print("\nAvailable lines:")
        print("-" * 72)

        for number, config in sorted(self.lines.items(), key=lambda item: item[0]):
            name = config.get("name", "Unknown")
            line_type = config.get("type", "unknown")
            voice = config.get("voice", "n/a")
            tts_engine = config.get("tts_engine", "n/a")
            handler = config.get("handler", "")

            extra = ""
            if handler:
                extra = f" | handler={handler}"

            print(f"{number:<6} -> {name} ({line_type}) | voice={voice} | tts={tts_engine}{extra}")

        print("-" * 72)

    # -----------------------------
    # Main loop
    # -----------------------------

    def run(self):
        print("Switchboard running - restored working TTS/STT build")
        self._print_available_lines()
        print("No dial tone/ringback WAV layer")
        print(f"HOOK_PIN = {HOOK_PIN}")
        print(f"PULSE_PIN = {PULSE_PIN}")
        print("Hook logic: HIGH = off-hook, LOW = on-hook")
        print(f"PULSE_EDGE = {PULSE_EDGE}")
        print(f"DIAL_ARM_DELAY_SECONDS = {DIAL_ARM_DELAY_SECONDS}")
        print(f"DIGIT_GAP_SECONDS = {DIGIT_GAP_SECONDS}")
        print(f"NUMBER_GAP_SECONDS = {NUMBER_GAP_SECONDS}")
        print(f"HOOK_HANGUP_CONFIRM_SECONDS = {HOOK_HANGUP_CONFIRM_SECONDS}")

        try:
            while True:
                self._finish_digit_if_ready()
                self._connect_number_if_ready()
                time.sleep(0.01)
        except KeyboardInterrupt:
            self.hangup_event.set()
            print("\n[switchboard] Shutting down")


if __name__ == "__main__":
    board = Switchboard(lines_path="lines.json")
    board.run()
