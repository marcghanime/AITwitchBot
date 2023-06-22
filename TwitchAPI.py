import requests, socket, queue, re, datetime, threading, asyncio
from emoji import demojize
from typing import Callable
from twitchAPI.pubsub import PubSub
from twitchAPI.twitch import Twitch
from twitchAPI.oauth import UserAuthenticator
from twitchAPI.types import AuthScope
from twitchAPI.helper import first
from uuid import UUID


CLIENT_ID = "0n2wpprouphucbxx48ctqamgbfoiwc"
CLIENT_SECRET = "mdsmfgeknu8iypsmpou7b5xzxj98id"
TWITCH_API_ACCESS_TOKEN = ""
USER_TOKEN = "" #could also get at https://twitchapps.com/tmi/

TWITCH_CHANNEL = 'skylibs'

CHAT_SERVER = 'irc.chat.twitch.tv'
CHAT_PORT = 6667
CHAT_NICKNAME = 'LibsGPT'
CHAT_CHANNEL = f'#{TWITCH_CHANNEL}'

twitch: Twitch = None
pubsub: PubSub = None
uuid: UUID = None

sock = socket.socket()
regex = r'^:(?P<user>[a-zA-Z0-9_]{4,25})!\1@\1\.tmi\.twitch\.tv PRIVMSG #(?P<channel>[a-zA-Z0-9_]{4,25}) :(?P<message>.+)$'


def initialize_socket():
    sock.connect((CHAT_SERVER, CHAT_PORT))
    sock.send(f"PASS oauth:{USER_TOKEN}\n".encode('utf-8'))
    sock.send(f"NICK {CHAT_NICKNAME}\n".encode('utf-8'))
    sock.send(f"JOIN {CHAT_CHANNEL}\n".encode('utf-8'))


def close_socket():
    sock.close()


def listen_to_messages(message_queue: queue.Queue, stop_event: threading.Event):
    while not stop_event.is_set():
        resp = sock.recv(2048).decode('utf-8')
        if resp.startswith('PING'):
            sock.send("PONG\n".encode('utf-8'))

        elif resp.startswith(':tmi.twitch.tv') or resp.startswith(':libsgpt'):
            pass

        elif len(resp) > 0:
            messages = resp.split("\n")
            for message in messages:
                if len(message) > 0:
                    message_queue.put(parse_message(message))


def parse_message(string: str):
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


def send_message(message: str):
    sock.send(f"PRIVMSG {CHAT_CHANNEL} :{message}\n".encode('utf-8'))


def get_stream_info():
    url = 'https://api.twitch.tv/helix/streams'
    params = {'user_login': [TWITCH_CHANNEL]}
    headers = {
        'Authorization': f'Bearer {TWITCH_API_ACCESS_TOKEN}',
        'Client-Id': CLIENT_ID
    }

    response = requests.get(url, params=params, headers=headers)
    
    data = response.json()['data'][0]
    game_name = data['game_name']
    viewer_count = data['viewer_count']
    title = data['title']

    # Get live time
    started_at = data['started_at']
    total_seconds = (datetime.datetime.utcnow() - datetime.datetime.strptime(started_at, '%Y-%m-%dT%H:%M:%SZ')).total_seconds()
    time_live = str(datetime.timedelta(seconds=total_seconds)).split('.')[0]
    
    return {
        'game_name': game_name,
        'viewer_count': viewer_count,
        'title': title,
        'time_live': time_live
    }


def initialize_twitch_api(callback_whisper: Callable[[UUID, dict], None]):
    print("Initializing Twitch API...")
    asyncio.run(get_user_oauth_token())
    get_twitch_oath_token()
    initialize_socket()
    asyncio.run(subscribe_to_whispers(callback_whisper))
    print("Twitch API Initialized")


def get_twitch_oath_token():
    global TWITCH_API_ACCESS_TOKEN
    url = 'https://id.twitch.tv/oauth2/token'
    params = {'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 'grant_type': 'client_credentials'}
    response = requests.post(url, params=params)
    TWITCH_API_ACCESS_TOKEN = response.json()["access_token"]


async def get_user_oauth_token():
    global twitch, USER_TOKEN
    twitch = Twitch(CLIENT_ID, CLIENT_SECRET)
    auth = UserAuthenticator(twitch, [AuthScope.WHISPERS_READ, AuthScope.CHAT_READ, AuthScope.CHAT_EDIT], force_verify=False)
    USER_TOKEN, refresh_token = await auth.authenticate()
    await twitch.set_user_authentication(USER_TOKEN, [AuthScope.WHISPERS_READ, AuthScope.CHAT_READ, AuthScope.CHAT_EDIT], refresh_token)


def stop_listening_to_whispers():
    asyncio.run(unsubscribe_from_whispers())


async def subscribe_to_whispers(callback_whisper: Callable[[UUID, dict], None]):
    global twitch, pubsub, uuid

    user = await first(twitch.get_users(logins=[CHAT_NICKNAME]))
    # starting up PubSub
    pubsub = PubSub(twitch)
    pubsub.start()
    # you can either start listening before or after you started pubsub.
    uuid = await pubsub.listen_whispers(user.id, callback_whisper)


async def unsubscribe_from_whispers():
    await pubsub.unlisten(uuid)
    pubsub.stop()
    await twitch.close()


# def get_twitch_emotes():
#     url = f"https://api.twitch.tv/helix/chat/emotes/global"
#     headers = {
#         'Authorization': f'Bearer {TWITCH_API_ACCESS_TOKEN}',
#         'Client-Id': CLIENT_ID
#     }

#     response = requests.get(url, headers=headers)
#     global_emotes = response.json()["data"].foreach(lambda emote: emote["name"])

#     url = f"https://api.twitch.tv/helix/chat/emotes"
#     params = {'broadcaster_id': TWITCH_CHANNEL}

#     response = requests.get(url, params=params, headers=headers)

#     channel_emotes = response.json()["data"].foreach(lambda emote: emote["name"])
#     return global_emotes + channel_emotes