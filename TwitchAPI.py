import requests, socket, queue, re, datetime, threading, asyncio
from emoji import demojize
from typing import Callable
from twitchAPI.pubsub import PubSub
from twitchAPI.twitch import Twitch
from twitchAPI.oauth import UserAuthenticator, refresh_access_token
from twitchAPI.types import AuthScope
from twitchAPI.helper import first
from uuid import UUID
from dataclasses import dataclass

@dataclass
class Config:
    client_id: str = ""
    client_secret: str = ""
    bot_nickname: str = ""
    chat_server: str = ""
    chat_port: int = 0
    twitch_channel: str = ""
    twitch_api_token: str = ""
    user_token: str = ""
    refresh_token: str = ""


class TwitchAPI:
    twitch_config: Config = None
    twitch: Twitch = None
    pubsub: PubSub = None
    uuid: UUID = None
    chat_history = []
    TESTING: bool = False
    sock = socket.socket()

    def __init__(self, config: Config, callback_whisper: Callable[[str, str], None],  testing: bool):
        self.twitch_config = config
        self.TESTING = testing
        self.sock.settimeout(2.5)
        print("Initializing Twitch API...")
        asyncio.run(self.init_twitch())
        if config.twitch_api_token == "": self.get_twitch_oath_token()
        self.initialize_socket()
        asyncio.run(self.subscribe_to_whispers(callback_whisper))
        print("Twitch API Initialized")


    def initialize_socket(self):
        self.sock.connect((self.twitch_config.chat_server, self.twitch_config.chat_port))
        self.sock.send(f"PASS oauth:{self.twitch_config.user_token}\n".encode('utf-8'))
        self.sock.send(f"NICK {self.twitch_config.bot_nickname}\n".encode('utf-8'))
        self.sock.send(f"JOIN #{self.twitch_config.twitch_channel}\n".encode('utf-8'))


    def close_socket(self):
        self.sock.close()


    def listen_to_messages(self, message_queue: queue.Queue, stop_event: threading.Event):
        while not stop_event.is_set():
            try: resp = self.sock.recv(2048).decode('utf-8')
            except socket.timeout: continue
            
            if ":tmi.twitch.tv NOTICE * :Login authentication failed" in resp:
                print("Login authentication failed, refreshing user token...")
                asyncio.run(self.init_twitch(force_refresh=True))

            elif resp.startswith('PING'):
                self.sock.send("PONG\n".encode('utf-8'))

            elif resp.startswith(':tmi.twitch.tv') or resp.startswith(':libsgpt'):
                pass

            elif len(resp) > 0:
                messages = resp.split("\n")
                for message in messages:
                    if len(message) > 0:
                        parsed_message = self.parse_message(message)
                        self.chat_history.append(f"{parsed_message['username']}: {parsed_message['message']}")
                        if len(self.chat_history) > 20: self.chat_history.pop(0)
                        message_queue.put(parsed_message)


    def parse_message(self, string: str):
        regex = r'^:(?P<user>[a-zA-Z0-9_]{4,25})!\1@\1\.tmi\.twitch\.tv PRIVMSG #(?P<channel>[a-zA-Z0-9_]{4,25}) :(?P<message>.+)$'
        string = demojize(string)
        match = re.match(regex, string)
        user = ""
        message = ""

        if match:
            user = match.group('user')
            message = match.group('message').replace("\r", "")

        return {
            'username': user,
            'message': message
        }


    def send_message(self, message: str):
        if not self.TESTING:
            self.sock.send(f"PRIVMSG #{self.twitch_config.twitch_channel} :{message}\n".encode('utf-8'))


    def get_stream_info(self):
        url = 'https://api.twitch.tv/helix/streams'
        params = {'user_login': [self.twitch_config.twitch_channel]}
        headers = {
            'Authorization': f'Bearer {self.twitch_config.twitch_api_token}',
            'Client-Id': self.twitch_config.client_id
        }

        response = requests.get(url, params=params, headers=headers)
        
        data = response.json()['data'][0]
        game_name = data['game_name']
        viewer_count = data['viewer_count']

        # Get live time
        started_at = data['started_at']
        total_seconds = (datetime.datetime.utcnow() - datetime.datetime.strptime(started_at, '%Y-%m-%dT%H:%M:%SZ')).total_seconds()
        time_live = str(datetime.timedelta(seconds=total_seconds)).split('.')[0]
        
        return {
            'game_name': game_name,
            'viewer_count': viewer_count,
            'time_live': time_live
        }


    def get_twitch_oath_token(self):
        url = 'https://id.twitch.tv/oauth2/token'
        params = {'client_id': self.twitch_config.client_id, 'client_secret': self.twitch_config.client_secret, 'grant_type': 'client_credentials'}
        response = requests.post(url, params=params)
        self.twitch_config.twitch_api_token = response.json()["access_token"]


    async def init_twitch(self, force_refresh: bool = False):
        self.twitch = Twitch(self.twitch_config.client_id, self.twitch_config.client_secret)
        user_token: str = self.twitch_config.user_token
        refresh_token: str = self.twitch_config.refresh_token
        scope = [AuthScope.WHISPERS_READ, AuthScope.CHAT_READ, AuthScope.CHAT_EDIT]

        if self.twitch_config.user_token == "" or self.twitch_config.refresh_token == "" or force_refresh:  
            auth = UserAuthenticator(self.twitch, scope, force_verify=False)
            user_token, refresh_token = await auth.authenticate()

        else:
            user_token, refresh_token = await refresh_access_token(refresh_token, self.twitch_config.client_id, self.twitch_config.client_secret)

        await self.twitch.set_user_authentication(user_token, scope, refresh_token)
        self.twitch_config.user_token = user_token
        self.twitch_config.refresh_token = refresh_token


    def stop_listening_to_whispers(self):
        asyncio.run(self.unsubscribe_from_whispers())


    async def subscribe_to_whispers(self, callback_whisper: Callable[[UUID, dict], None]):
        user = await first(self.twitch.get_users(logins=[self.twitch_config.bot_nickname]))
        # starting up PubSub
        self.pubsub = PubSub(self.twitch)
        self.pubsub.start()
        # you can either start listening before or after you started pubsub.
        self.uuid = await self.pubsub.listen_whispers(user.id, callback_whisper)


    async def unsubscribe_from_whispers(self):
        if self.pubsub: 
            await self.pubsub.unlisten(self.uuid)
            self.pubsub.stop()
        if self.twitch: await self.twitch.close()


    def get_chat_history(self):
        return self.chat_history


# def get_twitch_emotes():
#     url = f"https://api.twitch.tv/helix/chat/emotes/global"
#     headers = {
#         'Authorization': f'Bearer {twitch_config.twitch_api_token}',
#         'Client-Id': CLIENT_ID
#     }

#     response = requests.get(url, headers=headers)
#     global_emotes = response.json()["data"].foreach(lambda emote: emote["name"])

#     url = f"https://api.twitch.tv/helix/chat/emotes"
#     params = {'broadcaster_id': TWITCH_CHANNEL}

#     response = requests.get(url, params=params, headers=headers)

#     channel_emotes = response.json()["data"].foreach(lambda emote: emote["name"])
#     return global_emotes + channel_emotes