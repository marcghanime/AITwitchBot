import signal
import threading
import sys
import json
import time
import dataclasses

from api.chat import ChatAPI
from api.twitch import TwitchAPI
from api.bot import BotAPI
from api.audio import AudioAPI

from utils.models import Config, Memory
from utils.pubsub import PubSub, PubEvents

TRANSCRIPTION_MISTAKES = {
    "libs": ["lips", "looks", "lib's", "lib", "lipsh"],
    "gpt": ["gpc", "gpg", "gbc", "gbt", "shupiti"]
}

class CLI:
    config: Config
    memory: Memory
    pubsub: PubSub

    audio_api: AudioAPI
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

        # Load data
        self.config = self.load_config()
        self.memory = self.load_memory()

        # Set the first reaction time to 5 minutes from now
        self.memory.reaction_time = time.time() + 300

        # Setup
        self.add_mistakes_to_detection_words()

        # Audio API
        self.audio_api = AudioAPI(self.config, self.pubsub)

        # Twitch API
        self.twitch_api = TwitchAPI(self.config, self.pubsub)

        # Chat API
        self.chat_api = ChatAPI(self.config, self.pubsub, self.memory)
        
        # Bot API
        self.bot_api = BotAPI(self.config, self.pubsub, self.memory, self.twitch_api, self.chat_api)

        # Start threads
        self.audio_api.start()
        self.start()
    

    # Start the main thread.
    def start(self):
        old_message_count = self.bot_api.get_message_count()
        old_captions = ""

        while not self.stop_event.is_set():
            # update the reaction time
            time_to_reaction = self.memory.reaction_time - time.time()
            
            # check for new infos to print 
            if old_message_count != self.bot_api.get_message_count() or old_captions != self.audio_captions:
                print(f"\nCounter: {self.bot_api.get_message_count()} | Time to reaction: {time_to_reaction}\nCaptions:\n{self.audio_captions}")

                old_message_count = self.bot_api.get_message_count()
                old_captions = self.audio_captions

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


    # Adds all possible transcription mistakes to the detection words
    def add_mistakes_to_detection_words(self):
        for correct, wrong_list in TRANSCRIPTION_MISTAKES.items():
            word_list = filter(lambda x: correct in x, self.config.detection_words)
            for word in word_list:
                index = self.config.detection_words.index(word)
                wrong_words = list(
                    map(lambda wrong: word.replace(correct, wrong), wrong_list))
                wrong_words = list(
                    filter(lambda word: word not in self.config.detection_words, wrong_words))
                self.config.detection_words[index + 1: index + 1] = wrong_words


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


    def save_config(self) -> None:
        with open("config.json", "w") as outfile:
            json.dump(dataclasses.asdict(self.config), outfile, indent=4)


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
