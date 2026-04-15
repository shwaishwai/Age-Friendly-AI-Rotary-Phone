import threading
from abc import ABC, abstractmethod


class BaseHandler(ABC):
    """
    Every phone line handler must implement run(hangup_event).
    The router calls handler.run(event) without knowing the concrete type.
    """

    def __init__(self, config: dict):
        self.name  = config.get("name", "Unknown Line")
        self.voice = config.get("voice", "en")

    @abstractmethod
    def run(self, hangup_event: threading.Event):
        """Connect the call and handle it until completion or hangup."""
        ...

    def __repr__(self):
        return f"<{self.__class__.__name__} name={self.name!r}>"
