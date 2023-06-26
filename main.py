import signal, threading, sys, queue, os, msvcrt, json, time, dataclasses
from ChatAPI import ChatAPI, Memory
from TwitchAPI import TwitchAPI, Config
from AudioAPI import AudioAPI
from typing import Dict
from uuid import UUID

TESTING = True

# Thread variables
listening_thread = None
processing_thread = None
audio_context_thread = None
stop_event = threading.Event()

message_count = 0

# Moderation variables
mod_list = ["000kennedy000", "eridinn", "fingerlickinflashback", "itztwistedxd", "lilypips", "losoz", "mysticarchive", "realyezper", "revenjl"]
banned_users: list = []
timedout_users: Dict[str, float] = {}
cooldown_time: float = 0
slow_mode_seconds: float = 0
command_help = "Must be Libs or a Mod. Usage: whisper me [command] or !LibsGPT [command] in chat || timeout [username] [seconds] | reset [username] | cooldown [minutes] | ban [username] | unban [username] | slowmode [seconds]"

#TODO add emote support
#TODO spotify integration


twitch_api: TwitchAPI = None
chat_api: ChatAPI = None
audio_api: AudioAPI = None

# create a queue to hold the messages
message_queue = queue.Queue()
IGNORED_MESSAGE_THRESHOLD = 50
LENGTH_MESSAGE_THRESHOLD = 50


def main():
    global twitch_api, chat_api, audio_api
    
    signal.signal(signal.SIGINT, shutdown_handler)
    
    # Twtich API
    config: Config = load_config()
    twitch_api = TwitchAPI(config, callback_whisper, testing=TESTING)
    mod_list.append(config.twitch_channel)

    # Audio API
    audio_api = AudioAPI()

    # Chat API
    memory: Memory = load_memory()
    chat_api = ChatAPI(memory, twitch_api, audio_api, TESTING)
    
    start_threads()
    cli()


def handle_commands(input: str, external: bool = True):
    global banned_users, timedout_users, cooldown_time, slow_mode_seconds
    
    input = input.lower().replace("!libsgpt ", "").replace("!libsgpt", "")
    
    # reset <username> - clears the conversation memory with the given username
    if input.startswith("reset "):
        username = input.split(" ")[1]
        chat_api.clear_user_conversation(username)
        twitch_api.send_message(f"Conversation with {username} has been reset.")

    # ban <username> - bans the user, so that the bot will not respond to them
    elif input.startswith("ban "):
        username = input.split(" ")[1]
        chat_api.clear_user_conversation(username)
        banned_users.append(username)
        twitch_api.send_message(f"{username} will be ignored.")

    # unban <username> - unbans the user
    elif input.startswith("unban "):
        username = input.split(" ")[1]
        if username in banned_users:
            banned_users.remove(username)
            twitch_api.send_message(f"{username} will no longer be ignored.")

    # timeout <username> <duration in seconds> - times out the bot for the given user
    elif input.startswith("timout "):
        username = input.split(" ")[1]
        duration = input.split(" ")[2]
        out_time = time.time() + int(duration)
        timedout_users[username] = out_time
        chat_api.clear_user_conversation(username)
        twitch_api.send_message(f"{username} will be ignored for {duration} seconds.")
    
    # cooldown <duration in minutes> - puts the bot in cooldown for the given duration
    elif input.startswith("cooldown "):
        out_time = input.split(" ")[1]
        cooldown_time = time.time() + int(out_time * 60)
        twitch_api.send_message(f"Going in Cooldown for {out_time} minutes!")

    # slowmode <duration in seconds> - sets the slow mode for the bot
    elif input.startswith("slowmode "):
        sleep_time = input.split(" ")[1]
        slow_mode_seconds = sleep_time
        twitch_api.send_message(f"Slow mode set to {sleep_time} seconds!")

    # op <message> - sends a message as the operator
    elif input.startswith("op ") and not external:
        message = input.split(" ", 1)[1]
        twitch_api.send_message(f"(operator): {message}")

    # set-imt <number> - sets the ignored message threshold    
    elif input.startswith("set-imt ") and not external:
        global IGNORED_MESSAGE_THRESHOLD
        IGNORED_MESSAGE_THRESHOLD = int(input.split(" ")[1])

    # set-lmt <number> - sets the length message threshold
    elif input.startswith("set-lmt ") and not external:
        global LENGTH_MESSAGE_THRESHOLD
        LENGTH_MESSAGE_THRESHOLD = int(input.split(" ")[1])

    # test-msg <message> - sends a message as the test user
    elif input.startswith("test-msg ") and not external:
        username = "testuser"
        message = input.split(" ", 1)[1]
        if TESTING: send_response(username, message)
    
    elif input == ("intro") and not external:
        if not TESTING: send_intro()
    
    elif input == ("exit") and not external:
        shutdown_handler(None, None)


def send_intro():
    intro_message = f"Hiya, I'm back <3 !LibsGPT for mod commands."
    twitch_api.send_message(intro_message)


def start_threads():
    global listening_thread, processing_thread, audio_context_thread

    print("Starting threads...")
    listening_thread = threading.Thread(target=twitch_api.listen_to_messages, args=(message_queue, stop_event))
    listening_thread.daemon = True
    listening_thread.start()

    processing_thread = threading.Thread(target=process_messages)
    processing_thread.daemon = True
    processing_thread.start()

    audio_context_thread = threading.Thread(target=audio_api.listen_to_audio, args=(stop_event,))
    audio_context_thread.daemon = True
    audio_context_thread.start()


def process_messages():
    global message_count
    while not stop_event.is_set():
        # get the next message from the queue (this will block until a message is available or 2.5 seconds have passed)
        try: entry = message_queue.get(timeout=2.5)
        except queue.Empty: continue
        
        username = entry.get('username')
        message = entry.get('message')
            
        if message.lower().startswith("!libsgpt"):
            if username in mod_list:
                if message.lower() == "!libsgpt":
                    twitch_api.send_message(command_help)
                else:
                    handle_commands(message)
        
        elif should_respond(username, message):
            send_response(username, message)
            time.sleep(slow_mode_seconds)
        
        else:
            message_count += 1


def cli():
    old_message_count = message_count
    old_token_count = chat_api.get_total_tokens()

    os.system('cls')
    print(f"Message-Counter: {message_count} | Total-Tokens: {chat_api.get_total_tokens()}")

    while True: 
    # Check if there is input available on stdin
        if msvcrt.kbhit():
            user_input = input("Enter something: ")
            handle_commands(user_input, external=False)
        elif old_message_count != message_count or old_token_count != chat_api.get_total_tokens():
            os.system('cls')
            print(f"Counter: {message_count} | Total-Token: {chat_api.get_total_tokens()}")
            old_message_count = message_count
            old_token_count = chat_api.get_total_tokens()
            time.sleep(1)


def should_respond(username: str, message: str):
    # Moderation
    if TESTING: return False
    if username in banned_users: return False
    if time.time() < cooldown_time: return False
    if username in timedout_users and time.time() < timedout_users[username]: return False
    
    mentioned = username != twitch_api.twitch_config.bot_nickname.lower() and twitch_api.twitch_config.bot_nickname.lower() in message.lower()
    ignored = message_count > IGNORED_MESSAGE_THRESHOLD and len(message) > LENGTH_MESSAGE_THRESHOLD
    return mentioned or ignored


def send_response(username: str, message: str):
    global message_count
    ai_response = chat_api.get_response_AI(username, message)

    if ai_response:
        bot_response = f"@{username} {ai_response}"
        twitch_api.send_message(bot_response)
        message_count = 0


async def callback_whisper(uuid: UUID, data: dict) -> None:
    try: 
        data = json.loads(data.get("data"))
        message = data["body"]
        username = data["tags"]["login"]

        if username in mod_list:
            handle_commands(message)

    except: return


def load_config() -> Config:
    try:
        with open("config.json", "r") as infile:
            json_data = json.load(infile)
            loaded_config = Config(**json_data)
            return loaded_config

    except FileNotFoundError:
        print("Config file not found. Creating new config file...")    

        with open ("config.json", "w") as outfile: json.dump(dataclasses.asdict(Config()), outfile, indent=4)
        
        print("Please fill out the config file and restart the bot.")
        sys.exit(0)


def save_config() -> None:
    with open("config.json", "w") as outfile:
        json.dump(dataclasses.asdict(twitch_api.twitch_config), outfile, indent=4)


def load_memory() -> Memory:
    try:
        with open("memory.json", "r") as infile:
            json_data = json.load(infile)
            loaded_memory = Memory(**json_data)
            return loaded_memory

    except FileNotFoundError:
        with open ("memory.json", "w") as outfile: json.dump(dataclasses.asdict(Memory()), outfile, indent=4)
        with open("memory.json", "r") as infile:
            json_data = json.load(infile)
            loaded_memory = Memory(**json_data)
            return loaded_memory


def save_memory() -> None:
    with open("memory.json", "w") as outfile:
        json.dump(dataclasses.asdict(chat_api.memory), outfile, indent=4)


def shutdown_handler(signal, frame):
    stop_event.set()

    print('Shutting down...')

    if processing_thread: processing_thread.join()
    print('Processing thread stopped')

    if audio_context_thread: audio_context_thread.join()
    print('Audio context thread stopped')

    if listening_thread: listening_thread.join()
    print('Listening thread stopped')

    twitch_api.stop_listening_to_whispers()
    print('Whisper listener stopped')
    
    twitch_api.close_socket()

    print('Saving config...')
    save_config()

    print('Saving memory...')
    save_memory()

    sys.exit(0)



if __name__ == '__main__':
    main()
