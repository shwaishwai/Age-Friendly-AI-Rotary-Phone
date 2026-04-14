from datetime import datetime
from base import BaseHandler
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from audio import speak


class InfoHandler(BaseHandler):
    """
    A non-AI info line that runs a built-in function.
    Set "handler" in lines.json to pick which function to call.
    """

    # Registry of built-in info functions
    _REGISTRY: dict = {}

    def __init__(self, config: dict):
        super().__init__(config)
        self.handler_name = config.get("handler", "time")

    def run(self):
        fn = self._REGISTRY.get(self.handler_name)
        if fn is None:
            speak(f"Info handler {self.handler_name!r} is not available.")
            return
        fn(voice=self.voice)

    # ------------------------------------------------------------------
    # Registration decorator — add new info lines without editing run()
    # ------------------------------------------------------------------

    @classmethod
    def register(cls, name: str):
        """
        Decorator to register a new info function.

        Usage:
            @InfoHandler.register("weather")
            def handle_weather(voice="en"):
                speak("Weather service not ready.", voice=voice)
        """
        def decorator(fn):
            cls._REGISTRY[name] = fn
            return fn
        return decorator


# ------------------------------------------------------------------
# Built-in info handlers
# ------------------------------------------------------------------

@InfoHandler.register("time")
def _handle_time(voice: str = "en"):
    now = datetime.now().strftime("%H:%M")
    message = f"The time is {now}"
    print(f"  [info] {message}")
    speak(message, voice=voice)


@InfoHandler.register("speaking_clock")
def _handle_speaking_clock(voice: str = "en"):
    now = datetime.now()
    h = now.strftime("%I").lstrip("0")
    m = now.strftime("%M")
    period = now.strftime("%p")
    message = (
        f"At the third stroke, the time will be {h} o'clock {period}."
        if m == "00"
        else f"At the third stroke, the time will be {h} {m} {period}."
    )
    print(f"  [clock] {message}")
    speak(message, voice=voice)
    speak("beep. beep. beep.", voice=voice)
