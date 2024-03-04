import time
import random

from api.twitch import TwitchAPI
from api.chat import ChatAPI
from api.shazam import ShazamAPI
from utils.models import Config, Memory, Message
from utils.functions import check_banned_words
from utils.pubsub import PubSub, PubEvents

from twitchAPI.chat import WhisperEvent, ChatUser

BOT_FUNCTIONS = [
    {
        "name": "recognize_song",
        "description": "Recognize/identify/detect the song currently playing in the stream",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        } 
    }
]

class BotAPI:
    config: Config
    pubsub: PubSub
    memory: Memory
    twitch_api: TwitchAPI
    chat_api: ChatAPI
    shazam_api: ShazamAPI

    # Strings
    command_help: str = ""
    react_string: str = ""

    # Bot state
    message_count: int = 0
    processed_segment_starts: list = []
    ignored_message_threshold: int = 50
    length_message_threshold: int = 50


    def __init__(self, config: Config, pubsub: PubSub, memory: Memory, twitch_api: TwitchAPI, chat_api: ChatAPI):
        self.config = config
        self.pubsub = pubsub
        self.memory = memory
        self.twitch_api = twitch_api
        self.chat_api = chat_api
        self.shazam_api = ShazamAPI(config)

        # Subscribe to events
        self.pubsub.subscribe(PubEvents.CHAT_MESSAGE, self.process_message)
        self.pubsub.subscribe(PubEvents.WHISPER_MESSAGE, self.handle_command)
        self.pubsub.subscribe(PubEvents.TRANSCRIPT, self.check_verbal_mention)
        self.pubsub.subscribe(PubEvents.BOT_FUNCTION, self.bot_functions_callback)

        # Set bot functions 
        self.chat_api.add_functions(BOT_FUNCTIONS) 

        # Setup strings 
        self.setup_strings()
    

    # Setup constant strings
    def setup_strings(self):
        self.command_help = f"Must be {self.config.target_channel} or a Mod. Commands: timeout [username] [seconds] | reset [username] | cooldown [minutes] | ban [username] | unban [username] | slowmode [seconds] | banword [word] | unbanword [word]"
        self.react_string = f"Respond or react to the last thing {self.config.target_channel} said based only on the live captions and (if provided) the image for context."


    # Process messages received from the Twitch API
    def process_message(self, chat_message: Message):
        username = chat_message.username
        message = chat_message.text
        
        # ignore short messages
        if len(message.split(" ")) <= 3:
            return

        if self.mentioned(username, message) and self.moderation(username):
            self.send_response(chat_message)
            if self.memory.slow_mode_seconds > 0:
                time.sleep(self.memory.slow_mode_seconds)

        elif self.react() and self.moderation():
            chat_message.text = self.react_string
            self.send_response(chat_message, react=True)
            self.memory.reaction_time = time.time() + random.randint(300, 600)  # 10-15 minutes

        elif self.engage(message) and self.moderation(username):
            chat_message.text = f"@{self.config.target_channel} {message}"
            self.send_response(chat_message)
            if self.memory.slow_mode_seconds > 0:
                time.sleep(self.memory.slow_mode_seconds)

        else:
            self.message_count += 1


    # Check if the user has the privilege to use special commands
    def has_priviege(self, user: ChatUser) -> bool:
        return user.mod or user.name == self.config.target_channel.lower() or user.name == self.config.admin_username.lower()    


    # Send the intro message
    def send_intro(self):
        intro_message = f"Hi, I'm back <3 for mod commands checkout my channel pannels or whisper me."
        self.twitch_api.send_message(intro_message)


    # Get the message count
    def get_message_count(self):
        return self.message_count


    # Check if moderation allows the bot to respond
    def moderation(self, username: str = "") -> bool:
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
    def send_response(self, chat_message: Message, react: bool = False, respond: bool = False):
        bot_response = None
        username = chat_message.username
        message = chat_message.text
        
        # Check if the message contains any banned words
        found = check_banned_words(message, self.memory.banned_words)
        if found:
            bot_response = f"@{username} Ignored message containing banned word: '{found}'"
        
        elif react:
            ai_response = self.chat_api.get_ai_response_with_image(chat_message)
            if ai_response:
                bot_response = f"{ai_response}"
                self.chat_api.clear_user_conversation(username)

        elif respond:
            ai_response = self.chat_api.get_ai_response(
                chat_message, no_audio_context=True)
            if ai_response:
                bot_response = f"@{username} {ai_response}"
                self.chat_api.clear_user_conversation(username)

        else:
            ai_response = self.chat_api.get_ai_response(chat_message)
            if ai_response:
                bot_response = f"@{username} {ai_response}"

        if bot_response:
            self.twitch_api.send_message(bot_response)
            self.message_count = 0


    # Callback for when the transcript is received
    def check_verbal_mention(self, transcript: list):
        # filter out already reacted segments by start time
        transcript = [segment for segment in transcript if segment['start'] not in self.processed_segment_starts]

        # loop through the transcript except the last two segments
        for segment in transcript[:-2]:
            # check if the bot was mentioned
            if self.mentioned(self.config.target_channel, segment['text']):
                # get all the text from the transcript
                captions = "".join([segment['text'] for segment in transcript[:-2]])

                # send a response to the chat
                message = f"{self.config.target_channel} talked to/about you ({self.config.bot_username}) in the following captions: '{captions}' only respond to what they said to/about you ({self.config.bot_username})"
                chat_message = Message(self.config.target_channel, message)
                self.send_response(chat_message, respond=True)
                
                # add the start time to the processed list
                self.processed_segment_starts.append(segment['start'])
                
                # stop the loop
                break


    # Callback for when the ai calls a function
    def bot_functions_callback(self, function_name: str, chat_message: Message) -> str:
        if function_name == "recognize_song":
            self.twitch_api.send_message(f"@{chat_message.username} I'm listening... give me ~10 seconds") 
            return self.recognize_song()
        
        elif function_name == "ignore_user":
            self.memory.banned_users.append(chat_message.username)
            return "I'll ignore you from now on"
                
        return "Error"
    

    # Recognize the song currently playing in the stream
    def recognize_song(self):
        # Pause transcription for resource optimization
        self.pubsub.publish(PubEvents.PAUSE_TRANSCRIPTION)

        # Get the result from the shazam API
        result = self.shazam_api.detect_song()

        # Resume transcription
        self.pubsub.publish(PubEvents.RESUME_TRANSCRIPTION)

        # Check if the request was successful
        if result == "Error":
            return "I encountered an error while trying to detect the song"
        elif result == "No matches found":
            return "I couldn't recognize the song"
        else:
            return f"I think the song playing is {result}"
        

    # Handles commands sent to the bot
    def handle_command(self, whisper: WhisperEvent) -> None:
        command_not_found: bool = False
        input: str = whisper.message

        # Check if the user has the privilege to use whisper commands
        if not self.has_priviege(whisper.user):
            self.twitch_api.send_whisper(whisper.user, "You don't have the privilege to use whisper commands.")
            return

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
            username: str = input.split(" ")[1].lower()
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
        elif input.startswith("op "):
            message: str = input.split(" ", 1)[1]
            self.twitch_api.send_message(f"(operator): {message}")

        # set-imt <number> - sets the ignored message threshold
        elif input.startswith("set-emt "):
            self.ignored_message_threshold = int(input.split(" ")[1])

        # set-lmt <number> - sets the length message threshold
        elif input.startswith("set-elmt "):
            self.length_message_threshold = int(input.split(" ")[1])

        # test-msg <message> - sends a message as the test user
        elif input.startswith("test-msg "):
            username = "testuser"
            message = input.split(" ", 1)[1]
            chat_message = Message(username=username, text=message)
            self.send_response(chat_message)

        # add-det-word <word> - adds a word to the detection words
        elif input.startswith("add-det-word "):
            word = input.split(" ", 1)[1]
            self.config.detection_words.append(word)

        # send-intro - sends the intro message
        elif input == ("intro"):
            self.send_intro()

        # react - manually trigger a reaction
        elif input == ("react"):   
            chat_message = Message(username=self.config.target_channel, text=self.react_string)
            self.send_response(chat_message, react=True)
            self.memory.reaction_time = time.time() + random.randint(300, 600)
        
        # command not found
        else:
            command_not_found = True

        # Respond to whisper
        if command_not_found:
            self.twitch_api.send_whisper(whisper.user, f"Command not found! {self.command_help}")
        else:
            self.twitch_api.send_whisper(whisper.user, f"Command executed!")