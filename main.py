import signal, threading, sys, queue, os, msvcrt, json, time, dataclasses, random
from ChatAPI import ChatAPI, Memory
from TwitchAPI import TwitchAPI
from AudioAPI_V1 import AudioAPI
from models import Config, Memory

TESTING: bool = True

# Thread variables
listening_thread = None
processing_thread = None
audio_context_thread = None
stop_event = threading.Event()

message_count: int = 0

# TODO make these dynamic
command_help: str = "Must be Libs or a Mod. Usage: !LibsGPT [command] in chat || timeout [username] [seconds] | reset [username] | cooldown [minutes] | ban [username] | unban [username] | slowmode [seconds]"
prompt = "Act like an AI twitch chatter with the username LibsGPT. Try to keep your messages short and under 20 words. Be non verbose, sweet and sometimes funny. The following are some info about the stream you're watching: - About streamer: Name is Skylibs/Libs/bibs, She/Her, Scottish, 21, 5'3, fourth year Aeronautical Engineering student. Loves birds and baking. Favorite fast food place is Taco Bell. - Artwork: Bit badges by Spisky. Sub badges KoyLiang on Etsy. pfp by Jupiem. Emotes by lilypips."

#TODO add banned words list
#TODO add emote support
#TODO spotify integration


twitch_api: TwitchAPI
chat_api: ChatAPI
audio_api: AudioAPI
config: Config
memory: Memory

# create a queue to hold the messages
message_queue = queue.Queue()
IGNORED_MESSAGE_THRESHOLD: int = 50
LENGTH_MESSAGE_THRESHOLD: int = 50


def main():
    global twitch_api, chat_api, audio_api, config, memory
    
    signal.signal(signal.SIGINT, shutdown_handler)
    
    # Twitch API
    config = load_config()
    twitch_api = TwitchAPI(config, testing=TESTING)

    # Audio API
    audio_api = AudioAPI()

    # Chat API
    memory = load_memory()
    memory.reaction_time = time.time() + 300 #set the first reaction time to 10 minutes from now
    chat_api = ChatAPI(config, memory, twitch_api, audio_api, prompt, testing=TESTING)
    
    start_threads()
    cli()


def handle_commands(input: str, external: bool = True) -> None:
    global memory
    
    input = input.lower().replace("!libsgpt ", "").replace("!libsgpt", "")
    
    # reset <username> - clears the conversation memory with the given username
    if input.startswith("reset "):
        username: str = input.split(" ")[1]
        chat_api.clear_user_conversation(username)
        twitch_api.send_message(f"Conversation with {username} has been reset.")

    # ban <username> - bans the user, so that the bot will not respond to them
    elif input.startswith("ban "):
        username: str = input.split(" ")[1]
        chat_api.clear_user_conversation(username)
        memory.banned_users.append(username)
        twitch_api.send_message(f"{username} will be ignored.")

    # unban <username> - unbans the user
    elif input.startswith("unban "):
        username: str = input.split(" ")[1]
        if username in memory.banned_users:
            memory.banned_users.remove(username)
            twitch_api.send_message(f"{username} will no longer be ignored.")

    # timeout <username> <duration in seconds> - times out the bot for the given user
    elif input.startswith("timout "):
        username: str = input.split(" ")[1]
        duration: int = int(input.split(" ")[2])
        out_time: float = time.time() + int(duration)
        memory.timed_out_users[username] = out_time
        chat_api.clear_user_conversation(username)
        twitch_api.send_message(f"{username} will be ignored for {duration} seconds.")
    
    # cooldown <duration in minutes> - puts the bot in cooldown for the given duration
    elif input.startswith("cooldown "):
        out_time: float = float(input.split(" ")[1])
        memory.cooldown_time = time.time() + float(out_time * 60)
        twitch_api.send_message(f"Going in Cooldown for {out_time} minutes!")

    # slowmode <duration in seconds> - sets the slow mode for the bot
    elif input.startswith("slowmode "):
        sleep_time: int = int(input.split(" ")[1])
        memory.slow_mode_seconds = sleep_time
        twitch_api.send_message(f"Slow mode set to {sleep_time} seconds!")

    # op <message> - sends a message as the operator
    elif input.startswith("op ") and not external:
        message: str = input.split(" ", 1)[1]
        twitch_api.send_message(f"(operator): {message}")

    # set-imt <number> - sets the ignored message threshold    
    elif input.startswith("set-emt ") and not external:
        global IGNORED_MESSAGE_THRESHOLD
        IGNORED_MESSAGE_THRESHOLD = int(input.split(" ")[1])

    # set-lmt <number> - sets the length message threshold
    elif input.startswith("set-elmt ") and not external:
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
    intro_message = f"Hiya, I'm back <3 !LibsGPT for mod commands or checkout my channel pannels."
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
            if username in twitch_api.moderators:
                if message.lower() == "!libsgpt":
                    twitch_api.send_message(command_help)
                else:
                    handle_commands(message)
        
        elif mentioned(username, message) and moderation(username):
            send_response(username, message)
            if memory.slow_mode_seconds > 0: time.sleep(memory.slow_mode_seconds)

        elif react() and moderation(""):
            send_response(config.twitch_channel, f"repond or react to the last things {config.twitch_channel} said based on the captions")
            memory.reaction_time = time.time() + random.randint(300, 900) # 5-15 minutes

        elif engage(message) and moderation(username):
            send_response(username, f"@{config.twitch_channel} {message}")
            if memory.slow_mode_seconds > 0: time.sleep(memory.slow_mode_seconds)

        else:
            message_count += 1


def cli():
    old_message_count = message_count
    old_token_count = chat_api.get_total_tokens()

    last_captions = audio_api.get_transcription()[-1]
    os.system('cls')
    print(f"Message-Counter: {message_count} | Total-Tokens: {chat_api.get_total_tokens()}\n Last Captions: {last_captions}")

    while True: 
    # Check if there is input available on stdin
        if msvcrt.kbhit():
            user_input = input("Enter something: ")
            handle_commands(user_input, external=False)
        
        elif old_message_count != message_count or old_token_count != chat_api.get_total_tokens():
            last_captions = audio_api.get_transcription()[-1]
            os.system('cls')
            print(f"Counter: {message_count} | Total-Token: {chat_api.get_total_tokens()} \n Last Captions: {last_captions}")
            
            old_message_count = message_count
            old_token_count = chat_api.get_total_tokens()
            
            time.sleep(1)


def moderation(username: str) -> bool:
    if TESTING: return False
    if username in memory.banned_users: return False
    if time.time() < memory.cooldown_time: return False
    if username in memory.timed_out_users and time.time() < memory.timed_out_users[username]: return False
    if username in memory.timed_out_users: del memory.timed_out_users[username] # remove if time is up
    return True


def mentioned(username: str, message: str) -> bool:
    return username != config.bot_nickname.lower() and config.bot_nickname.lower() in message.lower()


def engage(message: str) -> bool:
    return message_count > IGNORED_MESSAGE_THRESHOLD and len(message) > LENGTH_MESSAGE_THRESHOLD

def react() -> bool:
    return time.time() > memory.reaction_time


def send_response(username: str, message: str):
    global message_count
    ai_response = chat_api.get_response_AI(username, message)

    if ai_response and username == config.twitch_channel and message == f"repond or react to the last things {config.twitch_channel} said based on the captions":
        bot_response = f"{ai_response}"
        twitch_api.send_message(bot_response)
        message_count = 0
        
        # remove the last 2 messages from the memory to prevent the bot from influencing itself
        memory.conversations[config.twitch_channel].pop(-1)
        memory.conversations[config.twitch_channel].pop(-1)
    
    elif ai_response:
        bot_response = f"@{username} {ai_response}"
        twitch_api.send_message(bot_response)
        message_count = 0


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
        json.dump(dataclasses.asdict(config), outfile, indent=4)


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
    
    twitch_api.close_socket()

    print('Saving config...')
    save_config()

    print('Saving memory...')
    save_memory()

    sys.exit(0)



if __name__ == '__main__':
    main()
