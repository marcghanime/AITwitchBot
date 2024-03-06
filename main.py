import os
import signal
import threading
import sys
import json
import time
import dataclasses

from api.chat import ChatAPI
from api.twitch import TwitchAPI
from api.bot import BotAPI

from utils.models import Config, Memory
from utils.pubsub import PubSub, PubEvents
from utils.transcription import TranscriptionServer


class CLI:
    config: Config
    memory: Memory
    pubsub: PubSub

    twitch_api: TwitchAPI
    chat_api: ChatAPI
    bot_api: BotAPI

    stop_event = threading.Event()

    audio_captions: str = ""

    def __init__(self):
        # Register shutdown handler
        signal.signal(signal.SIGINT, self.shutdown_handler)

        # Create the PubSub
        self.pubsub = PubSub()

        # Subscribe to the transcript event
        self.pubsub.subscribe(PubEvents.TRANSCRIPT, self.update_captions)
        self.pubsub.subscribe(PubEvents.SHUTDOWN, self.shutdown)

        # Load config from file
        self.config = self.load_config()
        
        # Set the environment variables
        self.set_env(self.config)
        
        # Load memory from file
        self.memory = self.load_memory()

        # Set the first reaction time to 5 minutes from now
        self.memory.reaction_time = time.time() + 300

        # Twitch API
        self.twitch_api = TwitchAPI(self.pubsub)

        # Chat API
        self.chat_api = ChatAPI(self.pubsub, self.memory)
        
        # Bot API
        self.bot_api = BotAPI(self.pubsub, self.memory, self.twitch_api, self.chat_api)

        # Initialize the whisper transcription client and start the transcription
        self.transcription_server = TranscriptionServer(self.pubsub, language="en", model="tiny.en")
        
        # Start the main thread
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

        # Keep only the last 250 words
        transcript_text = " ".join(transcript_text.split()[-250:]) 

        # Update the captions
        self.audio_captions = transcript_text


    # Set the environment variables
    def set_env(self, config: Config):
        # For each key, value pair in the config, set them as environment variables
        for key, value in dataclasses.asdict(config).items():
            os.environ[key] = str(value)


    # Load the config file
    def load_config(self) -> Config:
        try:
            with open("config.json", "r") as infile:
                json_data = json.load(infile)
                loaded_config = Config(**json_data)
                return loaded_config

        except FileNotFoundError:
            print("Config file not found. Creating new config file...")

            with open("config.json", "w") as outfile:
                json.dump(dataclasses.asdict(Config()), outfile, indent=4)

            print("Please fill out the config file and restart the bot.")
            sys.exit(0)


    # Save the config file
    def save_config(self) -> None:
        # update the config form the environment variables
        for key, value in os.environ.items():
            if key in dataclasses.fields(Config):
                setattr(self.config, key, value)

        with open("config.json", "w") as outfile:
            json.dump(dataclasses.asdict(self.config), outfile, indent=4)


    # Load the memory file
    def load_memory(self) -> Memory:
        try:
            with open("memory.json", "r") as infile:
                json_data = json.load(infile)
                loaded_memory = Memory(**json_data)
                return loaded_memory

        except FileNotFoundError:
            with open("memory.json", "w") as outfile:
                json.dump(dataclasses.asdict(Memory()), outfile, indent=4)
            with open("memory.json", "r") as infile:
                json_data = json.load(infile)
                loaded_memory = Memory(**json_data)
                return loaded_memory


    # Save the memory file
    def save_memory(self) -> None:
        memory = self.chat_api.memory
        with open("memory.json", "w") as outfile:
            json.dump(dataclasses.asdict(memory), outfile, indent=4)


    def shutdown_handler(self, *args, **kwargs):
        print('[INFO]: Shutting down...')
        self.pubsub.publish(PubEvents.SHUTDOWN)


    def shutdown(self):
        print('[INFO]: Stopping main thread...')
        self.stop_event.set()
        
        print('[INFO]: Saving config...')
        self.save_config()

        print('[INFO]: Saving memory...')
        self.save_memory()


if __name__ == '__main__':
    cli = CLI()
