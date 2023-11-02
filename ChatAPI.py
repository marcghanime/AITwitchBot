import json
import re
import time
from typing import List

import tiktoken
import openai

from TwitchAPI import TwitchAPI
from AudioAPI import AudioAPI
from ImageAPI import ImageAPI
from models import Memory, Config


class ChatAPI:
    config: Config
    memory: Memory
    twitch_api: TwitchAPI
    audio_api: AudioAPI
    image_api: ImageAPI
    prompt: str

    TESTING: bool = False

    def __init__(self, config: Config, memory: Memory, audio_api: AudioAPI, image_api: ImageAPI, twitch_api: TwitchAPI, testing: bool):
        self.config = config
        self.twitch_api = twitch_api
        self.audio_api = audio_api
        self.image_api = image_api
        self.memory = memory
        self.TESTING = testing

        openai.api_key = config.openai_api_key
        self.prompt = f"You are an AI twitch chatter. Keep your messages short, under 20 words and don't put usernames in the message. Be non verbose, sweet and sometimes funny. The following are some info about the stream you're watching: "
        self.prompt += self.config.prompt_extras

    def get_response_AI(self, username: str, message: str, no_twitch_chat: bool = False, no_audio_context: bool = False):
        found = self.check_banned_words(message)
        if found:
            return f"Ignored message containing banned word: '{found}'"

        self.add_message_to_conversation(
            username, message, role="user", no_twitch_chat=no_twitch_chat, no_audio_context=no_audio_context)

        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                max_tokens=self.config.openai_api_max_tokens_response,
                messages=self.memory.conversations[username]
            )

            finish_reason: str = response['choices'][0]['finish_reason']
            message = response['choices'][0]['message']['content']

            message = self.clean_message(message, username)
            if finish_reason == "length":
                message = f"{message}..."

            self.add_message_to_conversation(
                username, message, role="assistant", update_prompt=False)

            return message
        except Exception as error:
            error_msg = f"{type(error).__name__}: {str(error)}"
            self.log_error(error_msg, username)
            return None


    def check_banned_words(self, message: str):
        banned_words = self.memory.banned_words
        return next((word for word in banned_words if word.lower() in message.lower()), None)

    def log_error(self, log, username: str):
        data = {
            "date": time.ctime(),
            "log": log,
            "username": username,            
        }

        # Load the existing JSON file
        try:
            with open("logs.json", "r", encoding='utf-8') as f:
                logs = json.load(f)
        except (FileNotFoundError, json.decoder.JSONDecodeError):
            logs = []

        # Append the new log to the existing JSON array
        logs.append(data)

        # Write the updated JSON back to the file
        with open("logs.json", "w", encoding='utf-8') as f:
            json.dump(logs, f, indent=4)


    def init_conversation(self, username: str):
        self.memory.conversations[username] = [
            {
                "role": "system",
                "content": self.prompt
            }
        ]

    def update_prompt(self, username: str, message: str, no_twitch_chat: bool, no_audio_context: bool):
        visual_context = self.image_api.get_visual_context(message)
        twitch_chat_history = [] if no_twitch_chat else self.twitch_api.get_chat_history()
        captions = [] if no_audio_context else self.audio_api.transcription_queue2.get()

        new_prompt = self.generate_prompt_extras(twitch_chat_history, captions, visual_context)
        self.memory.conversations[username][0]["content"] = new_prompt

        limit: int = self.config.openai_api_max_tokens_total - \
            self.config.openai_api_max_tokens_response - 100  # 100 is a buffer

        try:
            while self.num_tokens_from_messages(self.memory.conversations[username]) > limit:
                if len(twitch_chat_history) == 0 and len(captions) == 0:
                    break

                if len(twitch_chat_history) != 0:
                    twitch_chat_history.pop(0)
                if len(captions) != 0:
                    captions.pop(0)

                new_prompt = self.generate_prompt_extras(twitch_chat_history, captions, visual_context)
                self.memory.conversations[username][0]["content"] = new_prompt
        except Exception as error:
            error_msg = f"{type(error).__name__}: {str(error)}"
            self.log_error(error_msg, username)

    def generate_prompt_extras(self, twitch_chat_history: List[str], captions: List[str], visual_context: str):
        twitch_chat_history_string = ""
        caption_string = ""

        if len(twitch_chat_history) > 0:
            twitch_chat_history_string = f" - Recents messages in Twitch chat: {' | '.join(twitch_chat_history)}"

        if len(captions) > 0:
            caption_string = f" - Live captions of what {self.config.twitch_channel} is currently saying: '{' '.join(captions)}'"

        if len(visual_context) > 0:
            visual_context_string = f" - Visual context of what is shown on the stream: {visual_context}"

        return self.prompt + caption_string + twitch_chat_history_string + visual_context_string

    def add_message_to_conversation(
            self,
            username: str,
            message: str,
            role: str,
            no_twitch_chat: bool = False,
            no_audio_context: bool = False,
            update_prompt: bool = True):

        if username not in self.memory.conversations:
            self.init_conversation(username)

        if len(self.memory.conversations[username]) > 9:
            self.memory.conversations[username].pop(1)

        message = f"{username}: {message}" if role == "user" else message

        self.memory.conversations[username].append({
            "role": role,
            "content": message
        })

        if update_prompt:
            self.update_prompt(username, message, no_twitch_chat, no_audio_context)

    # Remove unwanted charachters from the message

    def clean_message(self, message, username):
        message = self.remove_mentions(message, username)
        message = self.remove_hashtags(message)
        message = self.remove_links(message)
        message = message.replace("\n", " ")
        message = self.remove_quotations(message)
        return message

    def remove_quotations(self, text: str):
        while text.startswith('"') and text.endswith('"'):
            text = str(text[1:-1])
        return str(text)

    def remove_mentions(self, text: str, username: str):
        text = text.replace("@User", "").replace("@user", "").replace(f"@{self.config.bot_nickname}", "").replace(
            f"@{username}:", "").replace(f"@{username}", "").replace(f"{self.config.bot_nickname}:", "")
        return text

    def remove_links(self, text: str):
        link_regex = r"\b[a-zA-Z]+\.[a-zA-Z]+\b"
        links = re.findall(link_regex, text)
        # Replace links with a placeholder
        for link in links:
            text = text.replace(link, '***')

        return text

    def remove_hashtags(self, text: str):
        # Define the regex pattern to match hashtags
        pattern = r'#\w+'

        # Use the sub() function from the re module to remove the hashtags
        cleaned_text = re.sub(pattern, '', text)

        return cleaned_text

    def clear_user_conversation(self, username: str):
        if username in self.memory.conversations:
            del self.memory.conversations[username]

    # Returns the number of tokens used by a list of messages.
    def num_tokens_from_messages(self, messages):
        encoding = tiktoken.get_encoding("cl100k_base")
        num_tokens = 0
        for message in messages:
            # every message follows <im_start>{role/name}\n{content}<im_end>\n
            num_tokens += 4
            for key, value in message.items():
                num_tokens += len(encoding.encode(value))
                if key == "name":  # if there's a name, the role is omitted
                    num_tokens += -1  # role is always required and always 1 token
        num_tokens += 2  # every reply is primed with <im_start>assistant
        return num_tokens
