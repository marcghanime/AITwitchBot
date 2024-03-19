import time
import signal
import threading

from api.bot import BotAPI

from utils.stream import Stream
from utils.models import Config, Memory
from utils.pubsub import PubSub, PubEvents
from utils.deepgram_transcription import TranscriptionServer
from utils.functions import load_config, save_config, load_memory, save_memory, set_environ


class CLI:
    config: Config
    memory: Memory
    pubsub: PubSub
    bot_api: BotAPI

    stop_event = threading.Event()
    audio_captions: str = ""

    def __init__(self):
        # Register shutdown handler
        signal.signal(signal.SIGINT, self.shutdown_handler)

        # Create the PubSub
        self.pubsub = PubSub()

        # Subscribe to events
        self.pubsub.subscribe(PubEvents.TRANSCRIPT, self.update_captions)
        self.pubsub.subscribe(PubEvents.SHUTDOWN, self.shutdown)

        # Load config from file
        self.config = load_config()
        
        # Set the environment variables
        set_environ(self.config)
        
        # Load memory from file
        self.memory = load_memory()
        
        # Initialize the bot API
        self.bot_api = BotAPI(self.pubsub, self.memory)

        # Initialize the stream
        self.stream = Stream(self.pubsub)

        # Initialize the transcription server
        self.transcription = TranscriptionServer(self.pubsub)
        
        # Start the main thread, stream and transcription
        self.stream.start()
        self.transcription.start()
        self.start()

    

    # Start the main thread.
    def start(self):
        old_message_count = self.bot_api.get_message_count()
        old_captions = ""

        last_time = time.time()

        while not self.stop_event.is_set():
            # update the reaction time
            time_to_reaction = self.memory.reaction_time - time.time()
            
            # check for new infos to print 
            if old_message_count != self.bot_api.get_message_count() or old_captions != self.audio_captions or time.time() - last_time > 10:
                print(f"\nCounter: {self.bot_api.get_message_count()} | Time to reaction: {time_to_reaction}\nCaptions:\n{self.audio_captions}")

                old_message_count = self.bot_api.get_message_count()
                old_captions = self.audio_captions

                last_time = time.time()

            # sleep for 2.5 seconds
            time.sleep(2.5)


    # Callable for audio transcript
    def update_captions(self, transcript: list):
        # Extract the text from the transcript
        text = map(lambda x: x['text'], transcript)

        # Join the text
        transcript_text = "".join(text)

        # Update the captions
        self.audio_captions = transcript_text


    # Shutdown handler for when a shutdown signal is received
    def shutdown_handler(self, *args, **kwargs):
        print('[INFO]: Shutting down...')
        self.pubsub.publish(PubEvents.SHUTDOWN)


    # Shutdown the main thread and save the config and memory
    def shutdown(self):
        print('[INFO]: Stopping main thread...')
        self.stop_event.set()
        
        print('[INFO]: Saving config...')
        save_config(self.config)

        print('[INFO]: Saving memory...')
        save_memory(self.memory)


if __name__ == '__main__':
    cli = CLI()
