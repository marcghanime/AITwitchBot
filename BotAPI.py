import time
import threading
import queue
import random
from argparse import Namespace

from TwitchAPI import TwitchAPI
from ChatAPI import ChatAPI
from AudioAPI import AudioAPI
from models import Config, Memory

from twitchAPI.chat import ChatMessage, WhisperEvent
from typing import List


class BotAPI:
    config: Config
    args: Namespace
    memory: Memory
    twitch_api: TwitchAPI
    chat_api: ChatAPI
    audio_api: AudioAPI

    # Thread variables
    thread: threading.Thread
    stop_event: threading.Event = threading.Event()
    message_queue: queue.Queue[ChatMessage]
    whisper_queue: queue.Queue[WhisperEvent]

    # Strings
    command_help: str = ""
    react_string: str = ""

    # Bot state
    message_count: int = 0
    ignored_message_threshold: int = 75
    length_message_threshold: int = 50

    def __init__(self, args: Namespace, config: Config, memory: Memory, audio_api: AudioAPI, twitch_api: TwitchAPI, chat_api: ChatAPI):
        self.config = config
        self.args = args
        self.memory = memory
        self.twitch_api = twitch_api
        self.chat_api = chat_api
        self.audio_api = audio_api

        # Setup
        self.message_queue = self.twitch_api.get_message_queue()
        self.whisper_queue = self.twitch_api.get_whisper_queue()   
        self.audio_api.set_verbal_mention_callback(self.mentioned_verbally)     
        self.setup_strings()
    
    # Start the bot
    def start(self):
        self.thread = threading.Thread(target=self.process_messages)
        self.thread.daemon = True
        self.thread.start()

        self.whisper_thread = threading.Thread(target=self.process_whispers)
        self.whisper_thread.daemon = True
        self.whisper_thread.start()
        print("Bot Thread Started.")

    # Stop the bot
    def stop(self):
        self.stop_event.set()
        self.thread.join()
        print("Bot Thread Stopped.")

    # Setup constant strings
    def setup_strings(self):
        self.command_help = f"Must be {self.config.target_channel} or a Mod. Commands: timeout [username] [seconds] | reset [username] | cooldown [minutes] | ban [username] | unban [username] | slowmode [seconds] | banword [word] | unbanword [word]"
        self.react_string = f"repond or react to the last thing {self.config.target_channel} said based only on the provided live captions and the image for context."

    # Thread to process messages received from the Twitch API
    def process_messages(self):
        while not self.stop_event.is_set():
            # get the next message from the queue (this will block until a message is available or 2.5 seconds have passed)
            try:
                entry = self.message_queue.get(timeout=2.5)
            except queue.Empty:
                continue

            username = entry.user.name
            message = entry.text

            if self.mentioned(username, message) and self.moderation(username):
                self.send_response(username, message)
                if self.memory.slow_mode_seconds > 0:
                    time.sleep(self.memory.slow_mode_seconds)

            elif self.react() and self.moderation(""):
                self.send_response(self.config.target_channel, self.react_string, react=True)
                self.memory.reaction_time = time.time() + random.randint(300, 600)  # 10-15 minutes

            elif self.engage(message) and self.moderation(username):
                self.send_response(username, f"@{self.config.target_channel} {message}")
                if self.memory.slow_mode_seconds > 0:
                    time.sleep(self.memory.slow_mode_seconds)

            else:
                self.message_count += 1

    def process_whispers(self):
        while not self.stop_event.is_set():
            # get the next whisper from the queue (this will block until a whisper is available or 2.5 seconds have passed)
            try:
                entry = self.whisper_queue.get(timeout=2.5)
            except queue.Empty:
                continue
            isAdmin = entry.user.name == self.config.admin_username.lower()
            if entry.user.mod or entry.user.name == self.config.target_channel.lower() or isAdmin:
                self.handle_commands(entry, isAdmin)
            

    # Send the intro message
    def send_intro(self):
        intro_message = f"Hi, I'm back <3 !{self.config.bot_username} for mod commands or checkout my channel pannels."
        self.twitch_api.send_message(intro_message)

    def get_message_count(self):
        return self.message_count

    # Check if moderation allows the bot to respond
    def moderation(self, username: str) -> bool:
        if self.args.testing:
            return False
        if username in self.memory.banned_users:
            return False
        if time.time() < self.memory.cooldown_time:
            return False
        if username in self.memory.timed_out_users and time.time() < self.memory.timed_out_users[username]:
            return False
        if username in self.memory.timed_out_users:
            del self.memory.timed_out_users[username]  # remove if time is up
        return True

    # Check if the bot was mentioned in the message
    def mentioned(self, username: str, message: str) -> bool:
        return username != self.config.bot_username.lower() and self.config.bot_username.lower() in message.lower()

    # Check if the bot should engage
    def engage(self, message: str) -> bool:
        return self.message_count > self.ignored_message_threshold and len(message) > self.length_message_threshold

    # Check if the bot should react
    def react(self) -> bool:
        return time.time() > self.memory.reaction_time

    # Send a response to the chat
    def send_response(self, username: str, message: str, react: bool = False, respond: bool = False):
        bot_response = None

        if react:
            ai_response = self.chat_api.get_response_AI(
                username, message, no_twitch_chat=True)
            if ai_response:
                bot_response = f"{ai_response}"
                self.chat_api.clear_user_conversation(username)

        elif respond:
            ai_response = self.chat_api.get_response_AI(
                username, message, no_audio_context=True)
            if ai_response:
                bot_response = f"@{username} {ai_response}"
                self.chat_api.clear_user_conversation(username)

        else:
            ai_response = self.chat_api.get_response_AI(username, message)
            if ai_response:
                bot_response = f"@{username} {ai_response}"

        if bot_response:
            self.twitch_api.send_message(bot_response)
            self.message_count = 0

    # Callback for when the bot is mentioned verbally
    def mentioned_verbally(self, audio_transcription: List[str]):
        lines = self.audio_api.detected_lines_queue.get()
        respond: bool = False
        transctiption_index = None

        for detection_index, entry in enumerate(lines):
            line: str = entry['line']
            fixed_line: str = entry['fixed_line']
            responded: bool = entry['responded']
            
            try:
                transctiption_index = audio_transcription.index(line)
            except ValueError:
                continue
            audio_transcription[transctiption_index] = fixed_line

            if not responded and not respond:
                respond = True
                self.audio_api.detected_lines[detection_index]['responded'] = True

        if respond and transctiption_index:
            captions = " ".join(
                audio_transcription[transctiption_index - 2: transctiption_index + 4])
            message = f"{self.config.target_channel} talked to/about you ({self.config.bot_username}) in the following captions: '{captions}' only respond to what they said to/about you ({self.config.bot_username})"
            self.send_response(self.config.target_channel, message, respond=True)


    # Handles commands sent to the bot
    def handle_commands(self, whisper: WhisperEvent, admin: bool = False) -> None:
        command_not_found: bool = False
        input: str = whisper.message

        # reset <username> - clears the conversation memory with the given username
        if input.startswith("reset "):
            username: str = input.split(" ")[1]
            self.chat_api.clear_user_conversation(username)
            self.twitch_api.send_message(f"Conversation with {username} has been reset.")

        # ban <username> - bans the user, so that the bot will not respond to them
        elif input.startswith("ban "):
            username: str = input.split(" ")[1]
            self.chat_api.clear_user_conversation(username)
            self.memory.banned_users.append(username)
            self.twitch_api.send_message(f"{username} will be ignored.")

        # unban <username> - unbans the user
        elif input.startswith("unban "):
            username: str = input.split(" ")[1]
            if username in self.memory.banned_users:
                self.memory.banned_users.remove(username)
                self.twitch_api.send_message(f"{username} will no longer be ignored.")

        # timeout <username> <duration in seconds> - times out the bot for the given user
        elif input.startswith("timeout "):
            username: str = input.split(" ")[1]
            duration: int = int(input.split(" ")[2])
            out_time: float = time.time() + int(duration)
            self.memory.timed_out_users[username] = out_time
            self.chat_api.clear_user_conversation(username)
            self.twitch_api.send_message(f"{username} will be ignored for {duration} seconds.")

        # cooldown <duration in minutes> - puts the bot in cooldown for the given duration
        elif input.startswith("cooldown "):
            out_time: float = float(input.split(" ")[1])
            self.memory.cooldown_time = time.time() + float(out_time * 60)
            self.twitch_api.send_message(f"Going in Cooldown for {out_time} minutes!")

        # slowmode <duration in seconds> - sets the slow mode for the bot
        elif input.startswith("slowmode "):
            sleep_time: int = int(input.split(" ")[1])
            self.memory.slow_mode_seconds = sleep_time
            self.twitch_api.send_message(f"Slow mode set to {sleep_time} seconds!")

        # banword <word> - ignores messages containing the given word
        elif input.startswith("banword "):
            word = input.split(" ", 1)[1]
            self.memory.banned_words.append(word)
            self.twitch_api.send_message(f"'{word}' added to banned words.")

        # unbanword <word> - removes the given word from the banned words
        elif input.startswith("unbanword "):
            word = input.split(" ", 1)[1]
            if word in self.memory.banned_words:
                self.memory.banned_words.remove(word)
            self.twitch_api.send_message(f"'{word}' removed from banned words.")

        # op <message> - sends a message as the operator
        elif input.startswith("op ") and admin:
            message: str = input.split(" ", 1)[1]
            self.twitch_api.send_message(f"(operator): {message}")

        # set-imt <number> - sets the ignored message threshold
        elif input.startswith("set-emt ") and admin:
            self.ignored_message_threshold = int(input.split(" ")[1])

        # set-lmt <number> - sets the length message threshold
        elif input.startswith("set-elmt ") and admin:
            self.length_message_threshold = int(input.split(" ")[1])

        # test-msg <message> - sends a message as the test user
        elif input.startswith("test-msg ") and admin:
            username = "testuser"
            message = input.split(" ", 1)[1]
            if self.args.testing:
                self.send_response(username, message)

        # add-det-word <word> - adds a word to the detection words
        elif input.startswith("add-det-word ") and admin:
            word = input.split(" ", 1)[1]
            self.config.detection_words.append(word)

        # send-intro - sends the intro message
        elif input == ("intro") and admin:
            if not self.args.testing:
                self.send_intro()

        # react - manually trigger a reaction
        elif input == ("react") and admin:
            if not self.args.testing:
                self.send_response(self.config.target_channel, self.react_string, react=True)
                self.memory.reaction_time = time.time() + random.randint(300, 600)
        
        # command not found
        else:
            command_not_found = True

        # Respond to whisper
        if command_not_found:
            self.twitch_api.send_whisper(whisper.user, f"Command not found!")
            self.twitch_api.send_whisper(whisper.user, self.command_help)
        else:
            self.twitch_api.send_whisper(whisper.user, f"Command executed!")