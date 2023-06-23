import signal, threading, sys, queue, os, msvcrt, json
from ChatAPI import get_response_AI, clear_user_conversation
from TwitchAPI import CHAT_NICKNAME, TWITCH_CHANNEL, initialize_twitch_api, close_socket, listen_to_messages, send_message, stop_listening_to_whispers
import pygetwindow, pyautogui, pytesseract, time
from PIL import Image
from typing import Dict
from uuid import UUID

TESTING = True

# Thread variables
listening_thread = None
processing_thread = None
audio_context_thread = None
stop_event = threading.Event()
print_event = threading.Event()

message_count = 0

# Moderation variables
mod_list = ["000kennedy000", "eridinn", "fingerlickinflashback", "itztwistedxd", "lilypips", "losoz", "mysticarchive", "realyezper", "revenjl", TWITCH_CHANNEL]
banned_users: list = []
timedout_users: Dict[str, float] = {}
cooldown_time: float = 0
command_help = "Must be Libs or a Mod, usage: whisper me [command] or !LibsGPT [command] in chat || timeout [username] [duration in seconds] | reset [username] | cooldown [duration in minutes] | ban [username] | unban [username]"

#TODO add emote support
#TODO check username lower()
#TODO persistent memory
#TODO print thread
#TODO spotify integration
#TODO longer live captions
#TODO add commands to prompt
#TODO add slow mode commands


# create a queue to hold the messages
message_queue = queue.Queue()
IGNORED_MESSAGE_THRESHOLD = 50
LENGTH_MESSAGE_THRESHOLD = 50

# Audio context thread variables
audio_context: str = ""
SLEEP_TIME = 2.5


def main():
    signal.signal(signal.SIGINT, shutdown_handler)
    initialize_twitch_api(callback_whisper)
    start_threads()
    #send_intro()

    while True: 
        # Check if there is input available on stdin
        if msvcrt.kbhit():
            print_event.clear()
            user_input = input("Enter something: ")
            handle_commands(user_input, external=False)
        else:
            # Clear the pause event to resume the worker thread
            print_event.set()


def handle_commands(input: str, external: bool = True):
    global banned_users, timedout_users, cooldown_time
    
    input = input.lower().replace("!libsgpt ", "").replace("!libsgpt", "")
    
    # clear <username> - clears the conversation memory with the given username
    if input.startswith("reset "):
        username = input.split(" ")[1]
        clear_user_conversation(username)
        if not TESTING: send_message(f"Conversation with {username} has been reset.")

    # ban <username> - bans the user, so that the bot will not respond to them
    elif input.startswith("ban "):
        username = input.split(" ")[1]
        clear_user_conversation(username)
        banned_users.append(username)
        if not TESTING: send_message(f"{username} will be ignored.")

    # unban <username> - unbans the user
    elif input.startswith("unban "):
        username = input.split(" ")[1]
        if username in banned_users:
            banned_users.remove(username)
            if not TESTING: send_message(f"{username} will no longer be ignored.")

    # timeout <username> <duration in seconds> - times out the bot for the given user
    elif input.startswith("timout "):
        username = input.split(" ")[1]
        duration = input.split(" ")[2]
        out_time = time.time() + int(duration)
        timedout_users[username] = out_time
        clear_user_conversation(username)
        if not TESTING: send_message(f"{username} will be ignored for {duration} seconds.")
    
    # cooldown <duration in minutes> - puts the bot in cooldown for the given duration
    elif input.startswith("cooldown "):
        out_time = input.split(" ")[1]
        cooldown_time = time.time() + int(out_time * 60)
        if not TESTING: send_message(f"Going in Cooldown for {out_time} minutes!")

    # op <message> - sends a message as the operator
    elif input.startswith("op ") and not external:
        message = input.split(" ", 1)[1]
        if not TESTING: send_message(f"(operator): {message}")
        else: print(f"(operator): {message}")

    # set-imt <number> - sets the ignored message threshold    
    elif input.startswith("set-imt ") and not external:
        global IGNORED_MESSAGE_THRESHOLD
        IGNORED_MESSAGE_THRESHOLD = int(input.split(" ")[1])

    # set-lmt <number> - sets the length message threshold
    elif input.startswith("set-lmt ") and not external:
        global LENGTH_MESSAGE_THRESHOLD
        LENGTH_MESSAGE_THRESHOLD = int(input.split(" ")[1])


def send_intro():
    intro_message = f"Hiya, I'm back!"
    if not TESTING: send_message(intro_message)


def start_threads():
    global listening_thread, processing_thread, audio_context_thread

    print("Starting threads...")
    listening_thread = threading.Thread(target=listen_to_messages, args=(message_queue, stop_event))
    listening_thread.daemon = True
    listening_thread.start()

    processing_thread = threading.Thread(target=process_messages)
    processing_thread.daemon = True
    processing_thread.start()

    audio_context_thread = threading.Thread(target=get_audio_context)
    audio_context_thread.daemon = True
    audio_context_thread.start()


def get_audio_context():
    path = "result.png"
    global audio_context

    while not stop_event.is_set():
        titles = pygetwindow.getAllTitles()
        if "Live Caption" in titles:
            window = pygetwindow.getWindowsWithTitle("Live Caption")[0]
            left, top = window.topleft
            pyautogui.screenshot(path, region=(left + 20, top + 40, window.width - 40, window.height - 80))
            text: str = pytesseract.image_to_string(Image.open(path))
            audio_context = text.replace("\n", " ")
            time.sleep(SLEEP_TIME)


def process_messages():
    global message_count
    while not stop_event.is_set():
        # get the next message from the queue (this will block until a message is available)
        entry = message_queue.get()
        username = entry.get('username')
        message = entry.get('message')

        if message.lower().startswith("!libsgpt"):
            if username in mod_list:
                if message.lower() == "!libsgpt" and not TESTING:
                    send_message(command_help)
                else:
                    handle_commands(message)

        elif should_respond(username, message):
            send_response(username, message)
        
        else:
            message_count += 1

        print_event.wait()
        os.system('cls')
        print(f"Counter: {message_count}")


def should_respond(username: str, message: str):
    # Moderation
    if TESTING: return False
    if username in banned_users: return False
    if time.time() < cooldown_time: return False
    if username in timedout_users and time.time() < timedout_users[username]: return False
    
    mentioned = username != CHAT_NICKNAME.lower() and CHAT_NICKNAME.lower() in message.lower()
    ignored = message_count > IGNORED_MESSAGE_THRESHOLD and len(message) > LENGTH_MESSAGE_THRESHOLD
    return mentioned or ignored


def send_response(username: str, message: str):
    global message_count, audio_context
    ai_response = get_response_AI(username, f"{username}: {message}", audio_context)

    if ai_response:
        bot_response = f"@{username} {ai_response}"
        if not TESTING: send_message(bot_response)
        message_count = 0


async def callback_whisper(uuid: UUID, data: dict) -> None:
    try: 
        data = json.loads(data.get("data"))
        message = data["body"]
        username = data["tags"]["login"]

        if username in mod_list:
            handle_commands(message)

    except: return


def shutdown_handler(signal, frame):
    stop_event.set()
    print_event.set()
    
    print('Shutting down...')

    if processing_thread: processing_thread.join()
    print('Processing thread stopped')

    if audio_context_thread: audio_context_thread.join()
    print('Audio context thread stopped')

    if listening_thread: listening_thread.join()
    print('Listening thread stopped')

    stop_listening_to_whispers()
    print('Whisper listener stopped')
    
    close_socket()
    sys.exit(0)



if __name__ == '__main__':
    main()
