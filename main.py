import signal
import threading
import sys
import json
import time
import dataclasses
import argparse
from argparse import Namespace
from ChatAPI import ChatAPI
from TwitchAPI import TwitchAPI
from BotAPI import BotAPI
from AudioAPI import AudioAPI
from ImageAPI import ImageAPI
from models import Config, Memory

TRANSCRIPTION_MISTAKES = {
    "libs": ["lips", "looks", "lib's", "lib", "lipsh"],
    "gpt": ["gpc", "gpg", "gbc", "gbt", "shupiti"]
}

class CLI:
    config: Config
    memory: Memory

    image_api: ImageAPI
    audio_api: AudioAPI
    twitch_api: TwitchAPI
    chat_api: ChatAPI
    bot_api: BotAPI

    stop_event = threading.Event()

    def __init__(self, args: Namespace):
        # Register shutdown handler
        signal.signal(signal.SIGINT, self.shutdown_handler)

        # Load data
        self.config = self.load_config()
        self.memory = self.load_memory()

        # Set the first reaction time to 5 minutes from now
        self.memory.reaction_time = time.time() + 300

        # Setup
        self.add_mistakes_to_detection_words()

        # Image API
        self.image_api = ImageAPI(self.config)

        # Audio API
        self.audio_api = AudioAPI(args, self.config)

        # Twitch API
        self.twitch_api = TwitchAPI(args, self.config)

        # Chat API
        self.chat_api = ChatAPI(args, self.config, self.memory, self.audio_api, self.image_api, self.twitch_api)
        
        # Bot API
        self.bot_api = BotAPI(args, self.config, self.memory, self.audio_api, self.twitch_api, self.chat_api)

        # Start threads
        self.bot_api.start()
        self.audio_api.start()
        self.start()
    

    # Start the main thread.
    def start(self):
        old_message_count = self.bot_api.get_message_count()
        old_captions = ""
        captions = ""
        
        print(f"Message-Counter: {old_message_count}\n Captions: \n {captions}")

        while not self.stop_event.is_set():
            try:
                captions = "\n".join(self.audio_api.transcription_queue1.get(timeout=1))
            except:
                captions = old_captions

            time_to_reaction = self.memory.reaction_time - time.time()

            if old_message_count != self.bot_api.get_message_count() or old_captions != captions:
                print(
                    f"Counter: {self.bot_api.get_message_count()} | Time to reaction: {time_to_reaction}\nCaptions:\n{captions}")

                old_message_count = self.bot_api.get_message_count()
                old_captions = captions

            time.sleep(1)


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
        with open("memory.json", "w") as outfile:
            json.dump(dataclasses.asdict(self.chat_api.memory), outfile, indent=4)


    def shutdown_handler(self, signal, frame):
        print('Shutting down...')
        self.stop_event.set()
        
        print('Saving config...')
        self.save_config()

        print('Saving memory...')
        self.save_memory()

        self.bot_api.stop()
        self.audio_api.stop()
        self.twitch_api.shutdown()
        self.image_api.shutdown()

        sys.exit(0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Start the bot.')
    parser.add_argument('--lite', action='store_true', help='Use as little resources as possible.')
    parser.add_argument('--testing', action='store_true', help='Use testing mode.')
    args = parser.parse_args()
    cli = CLI(args)
