import uuid
import threading

from enum import Enum
from typing import Callable, Dict

class PubEvents(Enum):
    SHUTDOWN = 0
    TRANSCRIPT = 1
    CHAT_MESSAGE = 2
    WHISPER_MESSAGE = 3
    CHAT_HISTORY = 4
    BOT_FUNCTION = 5
    PAUSE_TRANSCRIPTION = 6
    RESUME_TRANSCRIPTION = 7
    STREAM_BYTES = 8


class PubSub:
    def __init__(self):
        self.subscribers: Dict[PubEvents, Dict[uuid.UUID, Callable]] = {}
        self.locks: Dict[PubEvents, threading.Lock] = {}

    def get_lock(self, event: PubEvents) -> threading.Lock:
        if event not in self.locks:
            self.locks[event] = threading.Lock()
        return self.locks[event]

    def subscribe(self, event: PubEvents, callback: Callable) -> uuid.UUID:
        with self.get_lock(event):
            # Add the event to the list of subscribers
            if event not in self.subscribers:
                self.subscribers[event] = {}

            # Generate a unique identifier for the subscription
            sub_id = uuid.uuid4()

            # Add the callback to the list of subscribers
            self.subscribers[event][sub_id] = callback
            
            # Return the subscription ID
            return sub_id

    def unsubscribe(self, event: PubEvents, sub_id: uuid.UUID):
        with self.get_lock(event):
            # Remove the callback from the list of subscribers
            if event in self.subscribers and sub_id in self.subscribers[event]:
                del self.subscribers[event][sub_id]

    def publish(self, event: PubEvents, *args, **kwargs):
        with self.get_lock(event):
            # Check if the event has subscribers
            if event in self.subscribers:

                # Call the callback for each subscriber
                for callback in self.subscribers[event].values():
                    callback(*args, **kwargs)