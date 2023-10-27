import signal
import threading
import sys
import os
import msvcrt
import json
import time
import dataclasses
from ChatAPI import ChatAPI
from TwitchAPI import TwitchAPI
from BotAPI import BotAPI
from AudioAPI import AudioAPI
from models import Config, Memory


TESTING: bool = False

TRANSCRIPTION_MISTAKES = {
    "libs": ["lips", "looks", "lib's", "lib", "lipsh"],
    "gpt": ["gpc", "gpg", "gbc", "gbt", "shupiti"]
}

class CLI:
    config: Config
    memory: Memory

    audio_api: AudioAPI
    twitch_api: TwitchAPI
    chat_api: ChatAPI
    bot_api: BotAPI

    stop_event = threading.Event()

    def __init__(self):
        # Register shutdown handler
        signal.signal(signal.SIGINT, self.shutdown_handler)

        # Load data
        self.config = self.load_config()
        self.memory = self.load_memory()

        # Set the first reaction time to 5 minutes from now
        self.memory.reaction_time = time.time() + 300

        # Setup
        self.add_mistakes_to_detection_words()

        # Audio API
        self.audio_api = AudioAPI(self.config)

        # Twitch API
        self.twitch_api = TwitchAPI(self.config, TESTING)

        # Chat API
        self.chat_api = ChatAPI(self.config, self.memory, self.audio_api, self.twitch_api, TESTING)
        
        # Bot API
        self.bot_api = BotAPI(self.config, self.memory, self.audio_api, self.twitch_api, self.chat_api, TESTING)

        # Start threads
        self.bot_api.start()
        self.audio_api.start()
        self.start()
    

    # Start the main thread.
    def start(self):
        old_message_count = self.bot_api.get_message_count()
        old_captions = ""
        captions = ""

        os.system('cls')
        print(
            f"Message-Counter: {old_message_count}\n Captions: \n {captions}")

        while not self.stop_event.is_set():
            try:
                captions = " ".join(self.audio_api.transcription_queue1.get(timeout=1))
            except:
                captions = old_captions

            time_to_reaction = self.memory.reaction_time - time.time()

            # Check if there is input available on stdin
            if msvcrt.kbhit():
                user_input = input("Enter something: ")
                self.bot_api.handle_commands(user_input, external=False)

            elif old_message_count != self.bot_api.get_message_count() or old_captions != captions:
                os.system('cls')
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

        self.bot_api.stop()
        self.audio_api.stop()
        self.twitch_api.shutdown()

        print('Saving config...')
        self.save_config()

        print('Saving memory...')
        self.save_memory()

        sys.exit(0)


if __name__ == '__main__':
    cli = CLI()
