import json
import threading
import urllib.request
from datetime import datetime
from base import BaseHandler
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from audio import speak, clean_text


class InfoHandler(BaseHandler):
    """
    A non-AI info line that runs a built-in function.
    Set "handler" in lines.json to pick which function to call.
    """

    _REGISTRY: dict = {}

    def __init__(self, config: dict):
        super().__init__(config)
        self.config = config
        self.handler_name = config.get("handler", "time")
        self.voice = config.get("voice", "alloy")
        self.tts_engine = config.get("tts_engine", "openai")
        self.tts_model = config.get("tts_model", "gpt-4o-mini-tts")

    def run(self, hangup_event: threading.Event):
        fn = self._REGISTRY.get(self.handler_name)
        if fn is None:
            self._speak(f"Info handler {self.handler_name!r} is not available.")
            return
        fn(hangup_event=hangup_event, speak_fn=self._speak, config=self.config)

    def _speak(self, text: str):
        speak(
            text,
            voice=self.voice,
            model=self.tts_model,
            tts_engine=self.tts_engine,
        )

    @classmethod
    def register(cls, name: str):
        def decorator(fn):
            cls._REGISTRY[name] = fn
            return fn
        return decorator


def _extract_met_forecast_region(data: dict) -> dict:
    forecast = data.get("forecasts", [{}])[0]
    region_items = forecast.get("regions", [])
    flat = {}

    for item in region_items:
        if isinstance(item, dict):
            flat.update(item)

    return flat


def _fetch_met_eireann_text_forecast(region: str = "Dublin") -> dict:
    allowed_regions = {
        "national": "National",
        "dublin": "Dublin",
        "leinster": "Leinster",
        "munster": "Munster",
        "connacht": "Connacht",
        "ulster": "Ulster",
        "outlook": "Outlook",
    }

    key = region.lower().strip()
    region_file = allowed_regions.get(key, "Dublin")
    url = f"https://www.met.ie/Open_Data/json/{region_file}.json"

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Age-Friendly-AI-Phone/1.0"}
    )

    with urllib.request.urlopen(req, timeout=10) as response:
        raw = response.read().decode("utf-8")

    return _extract_met_forecast_region(json.loads(raw))


@InfoHandler.register("time")
def _handle_time(hangup_event: threading.Event = None, speak_fn=speak, config=None):
    now = datetime.now().strftime("%H:%M")
    message = f"The time is {now}"
    print(f"  [info] {message}")
    speak_fn(message)


@InfoHandler.register("speaking_clock")
def _handle_speaking_clock(hangup_event: threading.Event = None, speak_fn=speak, config=None):
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
    speak_fn(message)
    if hangup_event and not hangup_event.is_set():
        speak_fn("beep. beep. beep.")


@InfoHandler.register("met_weather")
def _handle_met_weather(hangup_event: threading.Event = None, speak_fn=speak, config=None):
    config = config or {}
    region = config.get("weather_region", "Dublin")

    try:
        forecast = _fetch_met_eireann_text_forecast(region)
        region_name = forecast.get("region", region)
        issued = forecast.get("issued", "")
        today = forecast.get("today", "")
        tonight = forecast.get("tonight", "")

        if not today:
            raise RuntimeError("No 'today' field found in Met Eireann forecast.")

        issued_text = ""
        if issued:
            issued_text = f" Issued at {issued.replace('T', ' ').replace('Z', ' UTC')}."

        message = (
            f"Good day, this is the weatherman. "
            f"Here is the Met Eireann forecast for {region_name}.{issued_text} "
            f"Today: {today}"
        )

        if tonight:
            message += f" Tonight: {tonight}"

        message = clean_text(message)
        print(f"  [weather] {message}")
        speak_fn(message)

    except Exception as e:
        print(f"  [weather error] {clean_text(str(e))}")
        speak_fn("Sorry, I could not get the Met Eireann forecast right now. Please try again later.")
