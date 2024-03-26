import os
import logging

from typing import List
from openai import OpenAI

from api.image import ImageAPI

from utils.models import Memory, Message
from utils.pubsub import PubSub, PubEvents
from utils.functions import clean_message, clean_conversation

class ChatAPI:
    pubsub: PubSub
    memory: Memory
    openai_api: OpenAI
    image_api: ImageAPI
    system_prompt: str

    logger = logging.getLogger("chat_api")

    audio_transcript: str = ""
    twitch_chat_history: List[str] = []

    # Define the functions that the AI can call
    functions = [
        {
            "type": "function",
            "function":{
                "name": "image_input",
                "description": "Use a screenshot of the stream to get more context/information on what is shown/happening",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                }
            }
        }
    ]

    def __init__(self, pubsub: PubSub, memory: Memory):
        self.pubsub = pubsub
        self.memory = memory
        self.openai_api = OpenAI(api_key=os.environ["openai_api_key"])
        self.image_api = ImageAPI(pubsub)

        # Subscribe to events
        self.pubsub.subscribe(PubEvents.TRANSCRIPT, self.update_transcript)
        self.pubsub.subscribe(PubEvents.CHAT_HISTORY, self.update_twitch_chat_history)

        # Set the system prompt
        self.system_prompt = f"You are an AI twitch bot, you can hear the stream through the given audio captions and you can see the stream through the given screenshot (if not mentioned just use them as context). You can also identify songs by using the shazam API and search the web using the google API. You were created by the user {os.environ['admin_username']}. Keep your messages short and under 20 words. Be non verbose, sweet and sometimes funny. For context some information about the stream are given between the two <<context>> <</context>> delimiters with each message."


    # Callback for the chat history event
    def update_twitch_chat_history(self, chat_history: List[str]):
        self.twitch_chat_history = chat_history


    # Callback for the transcript event
    def update_transcript(self, transcript: list):
        # Extract the text from the transcript
        text = map(lambda x: x['text'], transcript)

        # Join the text
        transcript_text = "".join(text)

        # Update the transcript
        self.audio_transcript = transcript_text


    # Get a response from the AI
    def get_ai_response(self, chat_message: Message, with_tools=True):
        username = chat_message.username

        # Add the user message to the conversation
        self.create_user_message(chat_message, with_twitch_chat=True, with_audio_transcript=True, with_image=False)

        try:
            # Get a response from the AI with the users conversation
            response = self.openai_api.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=self.memory.conversations[username],
                max_tokens=300,
                tools=self.functions,
                tool_choice="auto" if with_tools else "none"
            )

            # Get the first choice
            choice = response.choices[0]

            self.logger.debug(f"OpenAI response: {response}")

            # Check if the response contains a function call
            if choice.message.tool_calls:
                self.handle_function_call(choice.message.tool_calls[0].function.name, choice.message.tool_calls[0].function.arguments, chat_message)

            # Check if the response contains a message
            elif choice.message.content:
                response_text = clean_message(choice.message.content, username, choice.finish_reason, os.environ["bot_username"])
            
                # Add the response to the conversation
                self.add_response_to_conversation(username, response_text)

                # Return the response text
                return response_text
        
        # Log any errors
        except Exception as error:
            self.logger.error(f"Error getting AI response: {error}")
            return None


    # Add a function to the list of functions
    def add_functions(self, functions: list):
        # Append functions to the list
        self.functions.extend(functions)


    # Handle a function call from the AI
    def handle_function_call(self, function_name: str, arguments: str, chat_message: Message):
        if function_name == "image_input":
            self.get_ai_response_with_image(chat_message)
        else:
            self.pubsub.publish(PubEvents.BOT_FUNCTION, function_name, arguments, chat_message)


    # Initialize a conversation with the user
    def init_conversation(self, username: str):
        self.memory.conversations[username] = [
            {
                "role": "system",
                "content": self.system_prompt
            }
        ]


    # Update the system prompt
    def update_system_prompt(self, username: str):
        self.memory.conversations[username][0]["content"] = self.system_prompt


    # Generate extra context for the message prompt
    def generate_prompt_context(self, with_twitch_chat: bool, with_audio_transcript: bool):
        twitch_chat_history_string = ""
        transcript_string = ""
        channel_description_string = ""

        # Add the channel description to the prompt
        if "channel_description" in os.environ.keys():
            channel_description_string = f"\n- Channel description: {os.environ['channel_description']}"

        # Add the twitch chat history to the prompt
        if with_twitch_chat and len(self.twitch_chat_history) > 0:
            twitch_chat = '\n'.join(self.twitch_chat_history)
            twitch_chat_history_string = f"\n- Twitch chat history: '{twitch_chat}'"

        # Add the audio transcript to the prompt
        if with_audio_transcript and len(self.audio_transcript) > 0:
            transcript_string = f"\n- Audio transcript: {self.audio_transcript}"

        # Return the updated prompt
        return f"<<context>> {channel_description_string} {twitch_chat_history_string} {transcript_string} <</context>>"


    # Add the user message to the conversation
    def create_user_message(
            self,
            chat_message: Message,
            with_twitch_chat: bool,
            with_audio_transcript: bool,
            with_image: bool):
        
        # Get the message information
        username = chat_message.username
        message = chat_message.text

        # Initialize the conversation if it doesn't exist
        if username not in self.memory.conversations:
            self.init_conversation(username)

        # Update the system prompt
        self.update_system_prompt(username)

        # Generate extra context for the prompt
        extra_context = self.generate_prompt_context(with_twitch_chat, with_audio_transcript)            

        # Add the message with context to the conversation
        prompt = f"{extra_context}\nReply to the following chat message '{username}: {message}'"

        if with_image:
            # Pause transcription for resource optimization
            self.pubsub.publish(PubEvents.PAUSE_TRANSCRIPTION)

            # Get a base64 screenshot of the stream
            base64_image = self.image_api.get_base64_screenshot()

            # Resume transcription
            self.pubsub.publish(PubEvents.RESUME_TRANSCRIPTION)

            # Add the prompt to the conversation with the image
            self.memory.conversations[username].append({
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
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
            # Add the prompt to the conversation
            self.memory.conversations[username].append({
                "role": "user",
                "content": prompt
            })


    # Add the response from the AI to the conversation
    def add_response_to_conversation(
            self,
            username: str,
            response: str):
        
        # Check if the conversation exists
        if username not in self.memory.conversations:
            return
        
        # Add the response to the conversation
        self.memory.conversations[username].append({
            "role": "assistant",
            "content": response
        })

        # keep only the last 10 messages
        while len(self.memory.conversations[username]) > 10:
            self.memory.conversations[username].pop(1)
        
        # remove images and old context messages from the conversation
        self.memory.conversations[username] = clean_conversation(self.memory.conversations[username])


    # Clear the conversation with the user from the memory
    def clear_user_conversation(self, username: str):
        if username in self.memory.conversations:
            del self.memory.conversations[username]


    # Use a screenshot of the stream to get more context/information on what is shown/happening
    def get_ai_response_with_image(self, chat_message: Message):
        
        # Add the user message to the conversation
        self.create_user_message(chat_message, with_twitch_chat=False, with_audio_transcript=True, with_image=True)

        # Get a response from the AI
        response = self.openai_api.chat.completions.create(
            model="gpt-4-vision-preview",
            messages=self.memory.conversations[chat_message.username],
            max_tokens=300
        )

        # Get the response text
        text = response.choices[0].message.content

        # Add the response to the conversation
        self.add_response_to_conversation(chat_message.username, text)

        return text
