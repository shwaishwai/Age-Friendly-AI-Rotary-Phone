import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from ai_handler import AIHandler
from info_handler import InfoHandler
from base import BaseHandler


# Map "type" values in lines.json to handler classes
_HANDLER_CLASSES: dict[str, type[BaseHandler]] = {
    "ai":   AIHandler,
    "info": InfoHandler,
}


class Router:
    """
    Builds a handler from a line config and calls run() on it.
    To support a new line type, add it to _HANDLER_CLASSES above.
    """

    def dispatch(self, number: str, lines: dict):
        config = lines.get(number)

        if config is None:
            print(f"  [router] No line configured for '{number}'")
            from audio import speak
            speak("Number not recognised. Please try again.")
            return

        line_type = config.get("type", "ai")
        handler_class = _HANDLER_CLASSES.get(line_type)

        if handler_class is None:
            print(f"  [router] Unknown line type '{line_type}'")
            from audio import speak
            speak(f"Line type {line_type} is not supported.")
            return

        handler = handler_class(config)
        print(f"  [router] -> {handler}")
        handler.run()
