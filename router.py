from ai_handler import AIHandler
from info_handler import InfoHandler


class Router:
    def __init__(self, lines: dict):
        self.lines = lines

    def connect(self, number: str, hangup_event):
        config = self.lines.get(number)

        if config is None:
            print(f"  [router] No line configured for number {number}")
            return

        line_type = config.get("type")

        if line_type == "ai":
            handler = AIHandler(config)
        elif line_type == "info":
            handler = InfoHandler(config)
        else:
            print(f"  [router] Unknown line type: {line_type!r}")
            return

        handler.run(hangup_event)
