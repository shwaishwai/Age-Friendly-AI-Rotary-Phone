import json
import threading
import time
import random
from pathlib import Path

from gpiozero import Button

from router import Router
from telephony import (
    preload_sounds,
    start_dial_tone,
    stop_dial_tone,
    start_ringback,
    stop_ringback,
    play_pulse_click,
    play_pickup,
    play_hangup,
    stop_all_telephony_sounds,
)


# Correct pins for your current wiring
PULSE_PIN = 27
HOOK_PIN = 22

# HIGH = off-hook / handset lifted
# LOW  = on-hook / handset down
HOOK_ACTIVE_HIGH = True

PULSE_EDGE = "pressed"
PULSE_BOUNCE_SECONDS = 0.003

DIAL_ARM_DELAY_SECONDS = 0.15
DIGIT_GAP_SECONDS = 0.5
NUMBER_GAP_SECONDS = 2.5
HOOK_IGNORE_AFTER_PULSE_SECONDS = 0.75
HOOK_HANGUP_CONFIRM_SECONDS = 0.60


class Switchboard:
    def __init__(self, lines_path="lines.json"):
        preload_sounds()

        self.lines = self._load_lines(lines_path)
        self.router = Router(self.lines)

        self.state = "ON_HOOK"
        self.number = ""
        self.pulse_count = 0
        self.last_pulse_at = None
        self.last_digit_at = None
        self.last_dial_activity_at = None
        self.dial_active = False
        self.dial_armed_at = None
        self.lock = threading.Lock()

        self.hangup_event = threading.Event()
        self.call_thread = None
        self.hook_check_active = False

        self.hook = Button(
            HOOK_PIN,
            pull_up=False,
            bounce_time=0.03,
        )

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

        if self.hook.is_pressed:
            self._handset_lifted()
        else:
            self._handset_down_confirmed()

    def _load_lines(self, path):
        p = Path(path)
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _dial_activity_in_progress(self):
        now = time.monotonic()

        with self.lock:
            if self.state == "DIALING":
                return True

            if self.dial_active:
                return True

            if self.last_pulse_at is not None:
                return True

            if (
                self.last_dial_activity_at is not None
                and now - self.last_dial_activity_at < HOOK_IGNORE_AFTER_PULSE_SECONDS
            ):
                return True

        return False

    # -----------------------------
    # Hook handling
    # -----------------------------

    def _handset_lifted(self):
        self.hook_check_active = False

        if self.state != "ON_HOOK":
            return

        print("\n[switchboard] Handset lifted")

        # Physical receiver pickup sound
        play_pickup()

        print("[switchboard] Waiting for number...")

        self.state = "WAITING_FOR_NUMBER"
        self.number = ""
        self.pulse_count = 0
        self.last_pulse_at = None
        self.last_digit_at = None
        self.last_dial_activity_at = None
        self.dial_active = False
        self.dial_armed_at = None
        self.hangup_event.clear()

        # Start dial tone after receiver is lifted
        start_dial_tone()

    def _possible_handset_down(self):
        if self._dial_activity_in_progress():
            print("[switchboard] Ignored hook drop during dialing")
            return

        if self.hook_check_active:
            return

        self.hook_check_active = True
        threading.Thread(target=self._confirm_handset_down, daemon=True).start()

    def _confirm_handset_down(self):
        time.sleep(HOOK_HANGUP_CONFIRM_SECONDS)

        self.hook_check_active = False

        if self._dial_activity_in_progress():
            print("[switchboard] Ignored hook drop because dialing is active")
            return

        if self.hook.is_pressed:
            print("[switchboard] Ignored brief hook drop")
            return

        self._handset_down_confirmed()

    def _handset_down_confirmed(self):
        stop_all_telephony_sounds()

        if self.state != "ON_HOOK":
            print("\n[switchboard] Handset down - reset")
            play_hangup()
        else:
            print("[switchboard] On hook")

        self.hangup_event.set()

        self.state = "ON_HOOK"
        self.number = ""
        self.pulse_count = 0
        self.last_pulse_at = None
        self.last_digit_at = None
        self.last_dial_activity_at = None
        self.dial_active = False
        self.dial_armed_at = None

    # -----------------------------
    # Pulse handling
    # -----------------------------

    def _pulse_event(self):
        with self.lock:
            if self.state not in ("WAITING_FOR_NUMBER", "DIALING", "NUMBER_PENDING"):
                return

            now = time.monotonic()
            self.last_dial_activity_at = now

            if self.state == "NUMBER_PENDING":
                self.state = "DIALING"

            if not self.dial_active:
                self.dial_active = True
                self.dial_armed_at = now + DIAL_ARM_DELAY_SECONDS

                if self.state == "WAITING_FOR_NUMBER":
                    self.state = "DIALING"

                print("[dial] Dial movement detected, arming...")

                # Stop dial tone as soon as the caller begins dialing
                stop_dial_tone()
                return

            if self.dial_armed_at is not None and now < self.dial_armed_at:
                print("[dial] Ignored early pulse")
                return

            self.pulse_count += 1
            self.last_pulse_at = now
            self.last_dial_activity_at = now

            # Low-latency mechanical click per accepted pulse
            play_pulse_click()

            print(f"[dial] Pulse count: {self.pulse_count}")

    def _finish_digit_if_ready(self):
        with self.lock:
            if self.state != "DIALING":
                return

            if self.pulse_count <= 0 or self.last_pulse_at is None:
                return

            elapsed = time.monotonic() - self.last_pulse_at
            if elapsed < DIGIT_GAP_SECONDS:
                return

            raw_count = self.pulse_count
            self.pulse_count = 0
            self.last_pulse_at = None
            self.dial_active = False
            self.dial_armed_at = None

            digit = "0" if raw_count == 10 else str(raw_count)

            self.number += digit
            now = time.monotonic()
            self.last_digit_at = now
            self.last_dial_activity_at = now
            self.state = "NUMBER_PENDING"

            print(f"[dial] Digit received: {digit} from raw pulse count {raw_count}")
            print(f"[dial] Number so far: {self.number}")
            print(f"[dial] Waiting {NUMBER_GAP_SECONDS}s for another digit...")

    def _connect_number_if_ready(self):
        with self.lock:
            if self.state != "NUMBER_PENDING":
                return

            if not self.number or self.last_digit_at is None:
                return

            elapsed = time.monotonic() - self.last_digit_at
            if elapsed < NUMBER_GAP_SECONDS:
                return

            number = self.number

            if number not in self.lines:
                print(f"[switchboard] No line configured for number: {number}")
                print("[switchboard] Waiting for number...")
                self.number = ""
                self.last_digit_at = None
                self.state = "WAITING_FOR_NUMBER"

                # Return to dial tone for another attempt
                start_dial_tone()
                return

        self._connect_number(number)

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

        def connect_with_ringback():
            start_ringback()
            time.sleep(random.uniform(2.0, 5.0))
            stop_ringback()

            if self.hangup_event.is_set():
                return

            # “Answered” sound before the handler begins
            play_pickup()

            self.router.connect(number, self.hangup_event)

        self.call_thread = threading.Thread(
            target=connect_with_ringback,
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

            print(
                f"{number:<6} -> {name} ({line_type}) "
                f"| voice={voice} | tts={tts_engine}{extra}"
            )

        print("-" * 72)

    # -----------------------------
    # Main loop
    # -----------------------------

    def run(self):
        print("Switchboard running - telephony sound build")
        self._print_available_lines()
        print("Dial tone / ringback / pulse click / pickup / hangup enabled")
        print(f"HOOK_PIN = {HOOK_PIN}")
        print(f"PULSE_PIN = {PULSE_PIN}")
        print("Hook logic: HIGH = off-hook, LOW = on-hook")
        print(f"PULSE_EDGE = {PULSE_EDGE}")
        print(f"DIAL_ARM_DELAY_SECONDS = {DIAL_ARM_DELAY_SECONDS}")
        print(f"DIGIT_GAP_SECONDS = {DIGIT_GAP_SECONDS}")
        print(f"NUMBER_GAP_SECONDS = {NUMBER_GAP_SECONDS}")
        print(f"HOOK_IGNORE_AFTER_PULSE_SECONDS = {HOOK_IGNORE_AFTER_PULSE_SECONDS}")
        print(f"HOOK_HANGUP_CONFIRM_SECONDS = {HOOK_HANGUP_CONFIRM_SECONDS}")

        try:
            while True:
                self._finish_digit_if_ready()
                self._connect_number_if_ready()
                time.sleep(0.01)
        except KeyboardInterrupt:
            self.hangup_event.set()
            stop_all_telephony_sounds()
            print("\n[switchboard] Shutting down")


if __name__ == "__main__":
    board = Switchboard(lines_path="lines.json")
    board.run()
