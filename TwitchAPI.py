import socket
import queue
import re
import datetime
import threading
import asyncio

import requests
from emoji import demojize
from twitchAPI.twitch import Twitch
from twitchAPI.oauth import UserAuthenticator, refresh_access_token
from twitchAPI.types import AuthScope

from models import Config


class TwitchAPI:
    config: Config
    twitch: Twitch
    chat_history = []
    moderators = []
    TESTING: bool = False
    sock = socket.socket()

    def __init__(self, config: Config, testing: bool):
        self.config = config
        self.TESTING = testing
        self.sock.settimeout(5)

        print("Initializing Twitch API...")
        asyncio.run(self.init_twitch())

        if config.twitch_api_oauth_token == "":
            self.get_twitch_oath_token()
        self.initialize_socket()
        print("Twitch API Initialized")

    def initialize_socket(self):
        self.sock.connect((self.config.twitch_chat_server,
                          self.config.twitch_chat_port))
        self.sock.send("CAP REQ :twitch.tv/tags\n".encode('utf-8'))
        self.sock.send(
            f"PASS oauth:{self.config.twitch_user_token}\n".encode('utf-8'))
        self.sock.send(f"NICK {self.config.bot_nickname}\n".encode('utf-8'))
        self.sock.send(f"JOIN #{self.config.twitch_channel}\n".encode('utf-8'))

    def close_socket(self):
        self.sock.close()

    def listen_to_messages(self, message_queue: queue.Queue, stop_event: threading.Event):
        while not stop_event.is_set():
            try:
                resp = self.sock.recv(2048).decode('utf-8')
            except socket.timeout:
                continue

            if ":tmi.twitch.tv NOTICE * :Login authentication failed" in resp:
                print("Login authentication failed, refreshing user token...")
                asyncio.run(self.init_twitch(force_refresh=True))

            elif resp.startswith('PING'):
                self.sock.send("PONG\n".encode('utf-8'))

            elif resp.startswith(':tmi.twitch.tv') or resp.startswith(f':{self.config.bot_nickname.lower()}'):
                pass

            elif len(resp) > 0:
                messages = resp.split("\n")
                for message in messages:
                    if not len(message) > 0:
                        continue

                    parsed_message = self.parse_message(message)
                    if not parsed_message:
                        continue

                    self.chat_history.append(
                        f"{parsed_message['username']}: {parsed_message['message']}")
                    if len(self.chat_history) > 20:
                        self.chat_history.pop(0)
                    message_queue.put(parsed_message)

    def parse_message(self, string: str):
        if "PRIVMSG" not in string:
            return None

        splitted = string.split()

        moderator = "badges=moderator/1" in splitted[0] or "badges=broadcaster/1" in splitted[0]

        string = " ".join(splitted[1:])
        regex = r'^:(?P<user>[a-zA-Z0-9_]{4,25})!\1@\1\.tmi\.twitch\.tv PRIVMSG #(?P<channel>[a-zA-Z0-9_]{4,25}) :(?P<message>.+)$'
        string = demojize(string)
        match = re.match(regex, string)
        user = ""
        message = ""

        if match:
            user = match.group('user')
            message = match.group('message').replace("\r", "")

        if moderator and user not in self.moderators:
            self.moderators.append(user)

        return {
            'username': user,
            'message': message
        }

    def send_message(self, message: str):
        if len(message) > 500:
            message = message[:475] + "..."
        if not self.TESTING:
            self.sock.send(
                f"PRIVMSG #{self.config.twitch_channel} :{message}\n".encode('utf-8'))

    def get_stream_info(self):
        url = 'https://api.twitch.tv/helix/streams'
        params = {'user_login': [self.config.twitch_channel]}
        headers = {
            'Authorization': f'Bearer {self.config.twitch_api_oauth_token}',
            'Client-Id': self.config.twitch_api_client_id
        }

        try:
            response = requests.get(
                url, params=params, headers=headers, timeout=10)
        except requests.exceptions.Timeout:
            return {
                'game_name': '',
                'viewer_count': '',
                'time_live': ''
            }

        data = response.json()['data'][0]
        game_name = data['game_name']
        viewer_count = data['viewer_count']

        # Get live time
        started_at = data['started_at']
        total_seconds = (datetime.datetime.utcnow(
        ) - datetime.datetime.strptime(started_at, '%Y-%m-%dT%H:%M:%SZ')).total_seconds()
        time_live = str(datetime.timedelta(
            seconds=total_seconds)).split('.')[0]

        return {
            'game_name': game_name,
            'viewer_count': viewer_count,
            'time_live': time_live
        }

    def get_twitch_oath_token(self):
        url = 'https://id.twitch.tv/oauth2/token'
        params = {'client_id': self.config.twitch_api_client_id,
                  'client_secret': self.config.twitch_api_client_secret, 'grant_type': 'client_credentials'}

        try:
            response = requests.post(url, params=params, timeout=20)
        except requests.exceptions.Timeout:
            return

        self.config.twitch_api_oauth_token = response.json()["access_token"]

    async def init_twitch(self, force_refresh: bool = False):
        self.twitch = Twitch(self.config.twitch_api_client_id,
                             self.config.twitch_api_client_secret)
        twitch_user_token: str = self.config.twitch_user_token
        refresh_token: str = self.config.twitch_user_refresh_token
        scope = [AuthScope.CHAT_READ, AuthScope.CHAT_EDIT]

        if self.config.twitch_user_token == "" or self.config.twitch_user_refresh_token == "" or force_refresh:
            auth = UserAuthenticator(self.twitch, scope, force_verify=False)
            auth_result = await auth.authenticate()
            if auth_result:
                twitch_user_token, refresh_token = auth_result

        else:
            twitch_user_token, refresh_token = await refresh_access_token(
                refresh_token, self.config.twitch_api_client_id, self.config.twitch_api_client_secret)

        await self.twitch.set_user_authentication(twitch_user_token, scope, refresh_token)
        self.config.twitch_user_token = twitch_user_token
        self.config.twitch_user_refresh_token = refresh_token

    def get_chat_history(self):
        return self.chat_history.copy()
