import requests, json, re, time, tiktoken
from typing import List
from TwitchAPI import TwitchAPI
from AudioAPI import AudioAPI
from dataclasses import dataclass, field

AI_API_KEY = "XlKzyLCsDTFnvqBgOKluKYAQfNVGggLYDdaYIgdgEadIYiUu"
LINK_REGEX = r"\b[\w.-]+\.[\w.-]+\b"
MAX_TOKENS = 4096

prompt = "Act like an AI twitch chatter with the username LibsGPT. You cannot act as someone else! Keep your messages short, sweet and funny. The following are some info about the stream you're watching: - About streamer: Name is Skylibs/Libs/bibs, She/Her, Scottish, 21, 5'3, fourth year Aeronautical Engineering student. Loves birds and baking. Favorite fast food place is Taco Bell. - Artwork: Bit badges by Spisky. Sub badges KoyLiang on Etsy. pfp by Jupiem. Emotes by lilypips."

@dataclass
class Memory:
    total_tokens: int = 0
    conversations: dict = field(default_factory=dict) #Dict[str, list]


class ChatAPI:
    twitch_api: TwitchAPI = None
    audio_api: AudioAPI = None
    memory: Memory = None
    status400Count = 0
    TESTING: bool = False

    def __init__(self, memory: Memory, twitch_api: TwitchAPI, audio_api: AudioAPI, testing: bool):
        self.twitch_api = twitch_api
        self.audio_api = audio_api
        self.memory = memory
        self.TESTING = testing

    def get_response_AI(self, username: str, message: str, retrying: bool = False):
        url = 'https://api.pawan.krd/v1/chat/completions'

        headers = {
            'Authorization': f'Bearer pk-{AI_API_KEY}',
            'Content-Type': 'application/json'
        }

        if not retrying: self.add_message_to_conversation(username, message, role="user")

        data = {
            "model": "gpt-3.5-turbo",
            "max_tokens": 200,
            "messages": self.memory.conversations[username]
        }

        response = requests.post(url, headers=headers, data=json.dumps(data))

        # Check the response
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
                    self.log_error(response.json(), username, message)
                    del self.memory.conversations[username][-1]
                    return None

                case "content_filter":
                    self.log_error(response.json(), username, message)
                    del self.memory.conversations[username][-1]
                    return "Omitted response due to a flag from content filters"
                
                case "error":
                    self.log_error(response.json(), username, message)
                    return None

        # Retry 5 times if status code is 400
        elif response.status_code == 400:
            self.status400Count += 1
            time.sleep(5)
            self.reset_ip()

            if self.status400Count > 5:
                self.log_error(response.json(), username, message)
                return None
            else:
                self.get_response_AI(username, message, retrying=True)
        
        # Other Errors handling
        else:
            self.log_error(response.json(), username, message)
            return None
        

    def log_error(self, response, username: str, message: str):
        data = {
            "date": time.ctime(),
            "username": username,
            "message": message,
            "response": response
        }

        with open("logs.json", "a") as f:
            json.dump(data, f)


    def handle_successfull_response(self, result, username: str, message: str):
            message = result['choices'][0]['message']['content']
            cleaned_message = self.clean_message(message, username)
            self.add_message_to_conversation("LibsGPT", cleaned_message, role="assistant")
            return cleaned_message

    def init_conversation(self, username: str):
        self.memory.conversations[username] = [
            {
                "role": "system",
                "content": prompt
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

        twitch_chat_history = self.twitch_api.get_chat_history().copy()
        captions = self.audio_api.get_audio_context().copy()

        new_prompt = self.generate_prompt(stream_info_string, twitch_chat_history, captions)
        self.memory.conversations[username][0]["content"] = new_prompt

                
        while self.num_tokens_from_messages(self.memory.conversations[username]) > 3800:
            twitch_chat_history.pop(0)
            captions.pop(0)

            new_prompt = self.generate_prompt(stream_info_string, twitch_chat_history, captions)
            self.memory.conversations[username][0]["content"] = new_prompt
    

    def generate_prompt(self, stream_info_string: str, twitch_chat_history: List[str], captions: List[str]):
        twitch_chat_history_string = f"- Recents messages in Twitch chat: {' | '.join(twitch_chat_history)}"
        caption_string = f"- Live captions of what is being said: '{' '.join(captions)}'"
        return prompt + stream_info_string + caption_string + twitch_chat_history_string


    def add_message_to_conversation(self, username: str, message: str, role: str):
        if username not in self.memory.conversations:
            self.init_conversation(username)

        if len(self.memory.conversations[username]) > 9:
            self.memory.conversations[username].pop(1)

        self.memory.conversations[username].append({
            "role": role,
            "name": username,
            "content": message
        })

        self.update_prompt(username)


    def reset_ip(self):
        print("Resetting IP")
        url = 'https://api.pawan.krd/resetip'
        headers = {
            'Authorization':  f'Bearer pk-{AI_API_KEY}'
        }
        requests.post(url, headers=headers)


    # Remove unwanted charachters from the message
    def clean_message(self, message, username):
        message = self.remove_mentions(message, username)
        message = self.remove_hashtags(message)
        message = self.remove_links(message)
        message = message.replace("\n", " ")
        return message


    def remove_mentions(self, text: str, username: str):
        text = text.replace("@User", "").replace("@user", "").replace("@LibsGPT", "").replace(f"@{username}:", "").replace(f"@{username}", "").replace("LibsGPT:", "")
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
    def num_tokens_from_messages(messages, model="gpt-3.5-turbo-0301"):
        try:
            encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            encoding = tiktoken.get_encoding("cl100k_base")
        if model == "gpt-3.5-turbo-0301":  # note: future models may deviate from this
            num_tokens = 0
            for message in messages:
                num_tokens += 4  # every message follows <im_start>{role/name}\n{content}<im_end>\n
                for key, value in message.items():
                    num_tokens += len(encoding.encode(value))
                    if key == "name":  # if there's a name, the role is omitted
                        num_tokens += -1  # role is always required and always 1 token
            num_tokens += 2  # every reply is primed with <im_start>assistant
            return num_tokens
        else:
            raise NotImplementedError(f"""num_tokens_from_messages() is not presently implemented for model {model}.""")