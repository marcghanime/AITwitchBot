import requests, json, re, time, tiktoken
from typing import List
from TwitchAPI import TwitchAPI
from AudioAPI_V1 import AudioAPI
from models import Memory, Config 

LINK_REGEX = r"\b[\w.-]+\.[\w.-]+\b"
API_URL = "https://api.openai.com/v1/chat/completions"

class ChatAPI:
    config: Config
    memory: Memory
    twitch_api: TwitchAPI
    audio_api: AudioAPI
    prompt: str

    TESTING: bool = False

    def __init__(self, config: Config, memory: Memory, twitch_api: TwitchAPI, audio_api: AudioAPI, prompt: str, testing: bool):
        self.config = config
        self.twitch_api = twitch_api
        self.audio_api = audio_api
        self.memory = memory
        self.prompt = prompt
        self.TESTING = testing


    def get_response_AI(self, username: str, message: str):
        found = self.check_banned_words(message)
        if found: return f"Ignored message containing banned word: '{found}'"

        headers = {
            'Authorization': f'Bearer {self.config.openai_api_key}',
            'Content-Type': 'application/json'
        }

        self.add_message_to_conversation(username, message, role="user")

        data = {
            "model": "gpt-3.5-turbo",
            "max_tokens": self.config.openai_api_max_tokens_response,
            "messages": self.memory.conversations[username]
        }
        request = json.dumps(data)
        response = requests.post(API_URL, headers=headers, data=request)

        # Successful response
        if response.status_code == 200:
            result = response.json()

            # Get tokens used
            tokens_used = 0
            try:
                tokens_used = result['usage']['total_tokens']
            except: pass
            self.memory.total_tokens += tokens_used

            # Get finish reason
            try:
                finish_reason: str = result['choices'][0]['finish_reason']
            except: finish_reason = "error"

            match finish_reason:
                case "stop":
                    return self.handle_successfull_response(result, username, message)

                case "length":
                    self.log_error(response.json(), username, message, request)
                    return self.handle_successfull_response(result, username, f"{message}...")

                case "content_filter":
                    self.log_error(response.json(), username, message, request)
                    del self.memory.conversations[username][-1]
                    return None

                case "error":
                    self.log_error(response.json(), username, message, request)
                    return None

        # Log Errors
        else:
            self.log_error(response.json(), username, message, request)
            return None


    def check_banned_words(self, message: str):
        banned_words = self.memory.banned_words
        return next((word for word in banned_words if word.lower() in message.lower()), None)


    def log_error(self, response, username: str, message: str, request: str):
        data = {
            "date": time.ctime(),
            "username": username,
            "message": message,
            "response": response,
            "request": request
        }

        # Load the existing JSON file
        try:
            with open("logs.json", "r") as f:
                logs = json.load(f)
        except json.decoder.JSONDecodeError:
            logs = []

        # Append the new log to the existing JSON array
        logs.append(data)

        # Write the updated JSON back to the file
        with open("logs.json", "w") as f:
            json.dump(logs, f, indent=4)


    def handle_successfull_response(self, result, username: str, message: str):
            message = result['choices'][0]['message']['content']
            cleaned_message = self.clean_message(message, username)
            self.add_message_to_conversation(username, cleaned_message, role="assistant")
            return cleaned_message


    def init_conversation(self, username: str):
        self.memory.conversations[username] = [
            {
                "role": "system",
                "content": self.prompt
            }
        ]


    def update_prompt(self, username: str):
        stream_info = None
        stream_info_string = ""

        if not self.TESTING: stream_info = self.twitch_api.get_stream_info()
        if stream_info:
            game_name = stream_info.get("game_name")
            viewer_count = stream_info.get("viewer_count")
            time_live = stream_info.get("time_live")
            stream_info_string = f"- Stream info: Game: {game_name}, Viewer Count: {viewer_count}, Time Live: {time_live}"

        twitch_chat_history = [] if username == self.config.twitch_channel else self.twitch_api.get_chat_history()
        captions = self.audio_api.get_transcription()

        new_prompt = self.generate_prompt_extras(stream_info_string, twitch_chat_history, captions)
        self.memory.conversations[username][0]["content"] = new_prompt

        limit: int = self.config.openai_api_max_tokens_total - self.config.openai_api_max_tokens_response - 100 # 100 is a buffer

        try:
            while self.num_tokens_from_messages(self.memory.conversations[username]) > limit:
                if len(twitch_chat_history) == 0 and len(captions) == 0: break
                
                if len(twitch_chat_history) != 0:  twitch_chat_history.pop(0)
                if len(captions) != 0: captions.pop(0)

                new_prompt = self.generate_prompt_extras(stream_info_string, twitch_chat_history, captions)
                self.memory.conversations[username][0]["content"] = new_prompt
        except:
            while len("".join(map(lambda x: x["content"], self.memory.conversations[username]))) > 4 * limit:
                if len(twitch_chat_history) == 0 and len(captions) == 0: break
                
                if len(twitch_chat_history) != 0:  twitch_chat_history.pop(0)
                if len(captions) != 0: captions.pop(0)

                new_prompt = self.generate_prompt_extras(stream_info_string, twitch_chat_history, captions)
                self.memory.conversations[username][0]["content"] = new_prompt


    def generate_prompt_extras(self, stream_info_string: str, twitch_chat_history: List[str], captions: List[str]):
        twitch_chat_history_string = f"- Recents messages in Twitch chat: {' | '.join(twitch_chat_history)}"
        caption_string = f"- Live captions of what {self.config.twitch_channel} is currently saying: '{' '.join(captions)}'"
        return self.prompt + stream_info_string + caption_string + twitch_chat_history_string


    def add_message_to_conversation(self, username: str, message: str, role: str):
        if username not in self.memory.conversations:
            self.init_conversation(username)

        if len(self.memory.conversations[username]) > 9:
            self.memory.conversations[username].pop(1)

        message = f"{username}: {message}" if role == "user" else message

        self.memory.conversations[username].append({
            "role": role,
            "content": message
        })

        self.update_prompt(username)


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
        text = text.replace("@User", "").replace("@user", "").replace(f"@{self.config.bot_nickname}", "").replace(f"@{username}:", "").replace(f"@{username}", "").replace(f"{self.config.bot_nickname}:", "")
        return text


    def remove_links(self, text: str):
        links = re.findall(LINK_REGEX, text)
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


    def get_total_tokens(self):
        return self.memory.total_tokens


    # Returns the number of tokens used by a list of messages.
    def num_tokens_from_messages(self, messages):
        encoding = tiktoken.get_encoding("cl100k_base")
        num_tokens = 0
        for message in messages:
            num_tokens += 4  # every message follows <im_start>{role/name}\n{content}<im_end>\n
            for key, value in message.items():
                num_tokens += len(encoding.encode(value))
                if key == "name":  # if there's a name, the role is omitted
                    num_tokens += -1  # role is always required and always 1 token
        num_tokens += 2  # every reply is primed with <im_start>assistant
        return num_tokens