import requests, socket, queue, re, datetime
from emoji import demojize

CLIENT_ID = "0n2wpprouphucbxx48ctqamgbfoiwc"
CLIENT_SECRET = "mdsmfgeknu8iypsmpou7b5xzxj98id"
TWITCH_API_ACCESS_TOKEN = ""

TWITCH_CHANNEL = 'skylibs'

CHAT_SERVER = 'irc.chat.twitch.tv'
CHAT_PORT = 6667
CHAT_TOKEN = 'oauth:89tnhmu65sqaqx3vi3euhqa69w0d9p' # get at https://twitchapps.com/tmi/
CHAT_NICKNAME = 'LibsGPT'
CHAT_CHANNEL = f'#{TWITCH_CHANNEL}'

sock = socket.socket()
regex = r'^:(?P<user>[a-zA-Z0-9_]{4,25})!\1@\1\.tmi\.twitch\.tv PRIVMSG #(?P<channel>[a-zA-Z0-9_]{4,25}) :(?P<message>.+)$'


def initialize_socket():
    sock.connect((CHAT_SERVER, CHAT_PORT))
    sock.send(f"PASS {CHAT_TOKEN}\n".encode('utf-8'))
    sock.send(f"NICK {CHAT_NICKNAME}\n".encode('utf-8'))
    sock.send(f"JOIN {CHAT_CHANNEL}\n".encode('utf-8'))


def close_socket():
    sock.close()


def listen_to_messages(message_queue: queue.Queue, running: bool):
    while running:
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


def get_twitch_oath_token():
    global TWITCH_API_ACCESS_TOKEN
    url = 'https://id.twitch.tv/oauth2/token'
    params = {'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 'grant_type': 'client_credentials'}
    response = requests.post(url, params=params)
    TWITCH_API_ACCESS_TOKEN = response.json()["access_token"]

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