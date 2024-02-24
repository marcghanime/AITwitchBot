from typing import Callable, Dict, List
from enum import Enum


class PubEvents(Enum):
    SHUTDOWN = 0
    TRANSCRIPT = 1
    CHAT_MESSAGE = 2
    WHISPER_MESSAGE = 3
    CHAT_HISTORY = 4
    BOT_FUNCTION = 5


class PubSub:
    def __init__(self):
        self.subscribers: Dict[PubEvents, List[Callable]] = {}

    def subscribe(self, event: PubEvents, callback: Callable):
        # Add the event to the list of subscribers
        if event not in self.subscribers:
            self.subscribers[event] = []

        # Add the callback to the list of subscribers
        self.subscribers[event].append(callback)

    def publish(self, event: PubEvents, *args, **kwargs):
        # Check if the event has subscribers
        if event in self.subscribers:

            # Call the callback for each subscriber
            for callback in self.subscribers[event]:
                callback(*args, **kwargs)