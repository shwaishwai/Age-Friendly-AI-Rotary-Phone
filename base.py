class BaseHandler:
    def __init__(self, config: dict):
        self.config = config
        self.name = config.get("name", "Unknown")
        self.description = config.get("description", "")
