import json
import time
from typing import Callable, List
from argparse import Namespace

import tiktoken
from openai import OpenAI

from TwitchAPI import TwitchAPI, ChatMessage
from AudioAPI import AudioAPI
from ImageAPI import ImageAPI
from models import Memory, Config
from utils import clean_message, remove_image_messages

class ChatAPI:
    config: Config
    args: Namespace
    memory: Memory
    openai_api: OpenAI
    twitch_api: TwitchAPI
    audio_api: AudioAPI
    image_api: ImageAPI
    prompt: str
    bot_function_callback: Callable[[[str, ChatMessage]], str]

    # Define the functions that the AI can call
    functions = [
        {
            "name": "image_input",
            "description": "Use a screenshot of the stream to get more context/information on what is shown/happening",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            }
        }
    ]

    def __init__(self, args: Namespace, config: Config, memory: Memory, audio_api: AudioAPI, image_api: ImageAPI, twitch_api: TwitchAPI):
        self.config = config
        self.openai_api = OpenAI(api_key=config.openai_api_key)
        self.twitch_api = twitch_api
        self.audio_api = audio_api
        self.image_api = image_api
        self.memory = memory
        self.args = args

        self.prompt = f"You are an AI twitch chatter, you can hear the stream through the given audio captions and you can see the stream through the given image (if not mentioned just use it as context). You can also identify songs by using the shazam API. You were created by {self.config.admin_username}. Keep your messages short and under 20 words. Be non verbose, sweet and sometimes funny. The following are some info about the stream: "
        self.prompt += self.config.prompt_extras


    # Get a response from the AI
    def get_ai_response(self, chat_message: ChatMessage, no_twitch_chat: bool = False, no_audio_context: bool = False):
        username = chat_message.user.name

        # Add the user message to the conversation
        self.add_user_message(chat_message, no_twitch_chat=no_twitch_chat, no_audio_context=no_audio_context)

        try:
            # Get a response from the AI
            response = self.openai_api.chat.completions.create(
                model="gpt-3.5-turbo-1106",
                messages=self.memory.conversations[username],
                max_tokens=self.config.openai_api_max_tokens_response,
                functions=self.functions
            )

            # Get the first choice
            choice = response.choices[0]

            # Check if the response contains a function call
            if choice.message.function_call:
                response_text = self.handle_function_call(choice.message.function_call.name, chat_message)

            # Check if the response contains a message
            elif choice.message.content:
                response_text = clean_message(choice.message.content, username, choice.finish_reason, self.config.bot_username)
            
            # Add the response to the conversation
            self.add_response_to_conversation(username, response_text)

            # Return the response text
            return response_text
        
        # Log any errors
        except Exception as error:
            error_msg = f"{type(error).__name__}: {str(error)}"
            self.log_error(error_msg, username)
            return None


    # Set the callback function for bot functions
    def set_bot_functions_callback(self, callback: Callable[[[str, ChatMessage]], str], bot_functions):
        # Append the bot functions to the list of functions
        self.functions.extend(bot_functions)
        # Set the callback function
        self.bot_function_callback = callback


    # Handle a function call from the AI
    def handle_function_call(self, function_name: str, chat_message: ChatMessage) -> str:
        if function_name == "image_input":
            return self.get_ai_response_with_image(chat_message)
        else:
            return self.bot_function_callback(function_name, chat_message)


    # Log an error to the logs.json file
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


    # Initialize a conversation with the user
    def init_conversation(self, username: str):
        self.memory.conversations[username] = [
            {
                "role": "system",
                "content": self.prompt
            }
        ]


    # Update the system prompt
    def update_prompt(self, username: str, no_twitch_chat: bool, no_audio_context: bool):
        twitch_chat_history = [] if no_twitch_chat else self.twitch_api.get_chat_history()
        captions = [] if no_audio_context else self.audio_api.transcription_queue2.get()

        new_prompt = self.generate_prompt_extras(twitch_chat_history, captions)
        self.memory.conversations[username][0]["content"] = new_prompt

        limit: int = self.config.openai_api_max_tokens_total - \
            self.config.openai_api_max_tokens_response - 50  # 50 is a buffer

        try:
            while self.num_tokens_from_messages(self.memory.conversations[username]) > limit:
                if len(twitch_chat_history) == 0 and len(captions) == 0:
                    break

                if len(twitch_chat_history) != 0:
                    twitch_chat_history.pop(0)
                if len(captions) != 0:
                    captions.pop(0)

                new_prompt = self.generate_prompt_extras(twitch_chat_history, captions)
                self.memory.conversations[username][0]["content"] = new_prompt
        except Exception as error:
            error_msg = f"{type(error).__name__}: {str(error)}"
            self.log_error(error_msg, username)


    # Generate extra context for the system prompt
    def generate_prompt_extras(self, twitch_chat_history: List[str], captions: List[str]):
        twitch_chat_history_string = ""
        caption_string = ""

        # Add the twitch chat history to the prompt
        if len(twitch_chat_history) > 0:
            twitch_chat = '\n'.join(twitch_chat_history)
            twitch_chat_history_string = f" - Twitch chat history: '{twitch_chat}'"

        # Add the audio captions to the prompt
        if len(captions) > 0:
            caption_string = f" - Audio captions: {' '.join(captions)}"

        # Return the updated prompt
        return self.prompt + caption_string + twitch_chat_history_string


    # Add the user message to the conversation
    def add_user_message(
            self,
            chat_message: ChatMessage,
            no_twitch_chat: bool = False,
            no_audio_context: bool = False,
            with_image: bool = False):
        
        # Get the message information
        username = chat_message.user.name
        message = chat_message.text

        # Initialize the conversation if it doesn't exist
        if username not in self.memory.conversations:
            self.init_conversation(username)
        
        # keep only the last 10 messages
        if len(self.memory.conversations[username]) > 10:
            self.memory.conversations[username].pop(1)

        # Add the message to the conversation
        message = f"{username}: {message}"

        if with_image:
            # Get a base64 screenshot of the stream
            base64_image = self.image_api.get_base64_screenshot()

            # Add the message to the conversation with the image
            self.memory.conversations[username].append({
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": message
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}",
                            "detail": "low"
                        }
                    }
                ]
            })
        
        else:
            # Add the message to the conversation
            self.memory.conversations[username].append({
                "role": "user",
                "content": message
            })

        # Update the system prompt
        self.update_prompt(username, no_twitch_chat, no_audio_context)


    # Add the response from the AI to the conversation
    def add_response_to_conversation(
            self,
            username: str,
            response: str):
        
        # Check if the conversation exists
        if username not in self.memory.conversations:
            return
        
        # remove image from sent message
        self.memory.conversations[username] = remove_image_messages(self.memory.conversations[username])

        # Add the response to the conversation
        self.memory.conversations[username].append({
            "role": "assistant",
            "content": response
        })

        # keep only the last 10 messages
        if len(self.memory.conversations[username]) > 10:
            self.memory.conversations[username].pop(1)


    # Clear the conversation with the user from the memory
    def clear_user_conversation(self, username: str):
        if username in self.memory.conversations:
            del self.memory.conversations[username]


    # Use a screenshot of the stream to get more context/information on what is shown/happening
    def get_ai_response_with_image(self, chat_message: ChatMessage):
        
        # Add the user message to the conversation
        self.add_user_message(chat_message, with_image=True)

        # Get a response from the AI
        response = self.openai_api.chat.completions.create(
            model="gpt-4-vision-preview",
            messages=self.memory.conversations[chat_message.user.name],
            max_tokens=self.config.openai_api_max_tokens_response
        )

        return response.choices[0].message.content


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
