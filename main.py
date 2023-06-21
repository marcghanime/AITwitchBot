import signal, threading, sys, queue, os, msvcrt
from ChatAPI import get_response_AI, clear_user_conversation
from TwitchAPI import CHAT_NICKNAME, initialize_socket, close_socket, listen_to_messages, send_message, get_twitch_oath_token
import pygetwindow, pyautogui, pytesseract, time
from PIL import Image
from typing import Dict

TESTING = True

# Thread variables
listening_thread = None
processing_thread = None
audio_context_thread = None
stop_event = threading.Event()
print_event = threading.Event()

message_count = 0

# Moderation variables
banned_users: list = ["LeibnizDisciple"]
timedout_users: Dict[str, float] = {}
cooldown_time: float = 0

#TODO add emote support

# create a queue to hold the messages
message_queue = queue.Queue()

# Audio context thread variables
audio_context: str = ""
SLEEP_TIME = 2.5


def main():
    signal.signal(signal.SIGINT, shutdown_handler)
    get_twitch_oath_token()
    initialize_socket()
    #send_intro()
    start_threads()
    while True: 
        # Check if there is input available on stdin
        if msvcrt.kbhit():
            print_event.clear()
            user_input = input("Enter something: ")
            handle_commands(user_input)
        else:
            # Clear the pause event to resume the worker thread
            print_event.set()


def handle_commands(input: str):
    global banned_users, timedout_users, cooldown_time
    # clear <username>
    if input.startswith("clear"):
        username = input.split(" ")[1]
        clear_user_conversation(username)

    # ban <username>
    elif input.startswith("ban"):
        username = input.split(" ")[1]
        clear_user_conversation(username)
        banned_users.append(username)

    # message <message>
    elif input.startswith("message"):
        message = input.split(" ", 1)[1]
        if not TESTING: send_message(f"(operator): {message}")
        else: print(f"(operator): {message}")

    # timeout <username> <duration in seconds>
    elif input.startswith("timout"):
        username = input.split(" ")[1]
        duration = input.split(" ")[2]
        out_time = time.time() + int(duration)
        timedout_users[username] = out_time
        clear_user_conversation(username)
    
    # cooldown <duration in minutes>
    elif input.startswith("cooldown"):
        out_time = input.split(" ")[1]
        cooldown_time = time.time() + int(out_time * 60)
        send_message(f"Going in Cooldown for {out_time} minutes!")


def send_intro():
    intro_message = f"Hiya, I'm back!"
    if not TESTING: send_message(intro_message)
    else: print(intro_message)


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

        if should_respond(username, message):
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
    
    mentioned = username.lower() != CHAT_NICKNAME.lower() and CHAT_NICKNAME.lower() in message.lower()
    ignored = message_count > 50 and len(message) > 50
    return mentioned or ignored


def send_response(username: str, message: str):
    global message_count, audio_context
    message = message.replace(f"@{CHAT_NICKNAME}", "").replace(f"@{CHAT_NICKNAME.lower()}", "")
    ai_response = get_response_AI(username, f"@{username}: {message}", audio_context)

    if ai_response:
        bot_response = f"@{username} {ai_response}"

        if not TESTING: send_message(bot_response)
        else: print(bot_response)
        
        message_count = 0


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
    
    close_socket()
    sys.exit(0)



if __name__ == '__main__':
    main()
