from gpiozero import AngularServo
from time import sleep, monotonic

# =========================
# USER SETTINGS
# =========================

GPIO_PIN = 6              # BCM GPIO number, not physical pin number

CENTER_ANGLE = 110         # Middle/rest position in degrees
SWING_DEGREES = 50        # Total movement range, e.g. 30 means +/-15 degrees

STRIKE_FREQUENCY_HZ = 5   # Start with 5. Try 10. 20 may be too fast for SG90.

RUN_TIME_SECONDS = 10     # How long to ring for

MIN_SERVO_ANGLE = 0
MAX_SERVO_ANGLE = 180

MIN_PULSE_WIDTH = 0.0005  # 0.5 ms
MAX_PULSE_WIDTH = 0.0024  # 2.4 ms

# =========================
# CALCULATED VALUES
# =========================

half_swing = SWING_DEGREES / 2

LEFT_ANGLE = CENTER_ANGLE - half_swing
RIGHT_ANGLE = CENTER_ANGLE + half_swing

HALF_PERIOD_SECONDS = 1 / (STRIKE_FREQUENCY_HZ * 2)

# Safety check
if LEFT_ANGLE < MIN_SERVO_ANGLE or RIGHT_ANGLE > MAX_SERVO_ANGLE:
    raise ValueError("Servo angle range is outside safe limits.")

# =========================
# SERVO SETUP
# =========================

servo = AngularServo(
    GPIO_PIN,
    min_angle=MIN_SERVO_ANGLE,
    max_angle=MAX_SERVO_ANGLE,
    min_pulse_width=MIN_PULSE_WIDTH,
    max_pulse_width=MAX_PULSE_WIDTH
)

try:
    print("Starting bell servo...")
    print(f"Moving between {LEFT_ANGLE}° and {RIGHT_ANGLE}°")
    print(f"Strike frequency: {STRIKE_FREQUENCY_HZ} Hz")

    start_time = monotonic()

    while monotonic() - start_time < RUN_TIME_SECONDS:
        servo.angle = LEFT_ANGLE
        sleep(HALF_PERIOD_SECONDS)

        servo.angle = RIGHT_ANGLE
        sleep(HALF_PERIOD_SECONDS)

finally:
    print("Stopping servo.")
    servo.angle = CENTER_ANGLE
    sleep(0.5)
    servo.detach()
