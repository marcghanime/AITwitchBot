import signal, threading, sys, queue
from ChatAPI import get_response_AI
from TwitchAPI import CHAT_NICKNAME, initialize_socket, close_socket, listen_to_messages, send_message, get_twitch_oath_token
import pygetwindow, pyautogui, pytesseract, time
from PIL import Image

# Thread variables
listening_thread = None
processing_thread = None
audio_context_thread = None
running: bool = True

message_count = 0
TESTING = False

#TODO add emote support
#TODO plug in spotify
#TODO remove hashtags
#TODO prevent spamming
#TODO ban LeibnizDisciple

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
    while True: pass

def send_intro():
    intro_message = f"Heylo, I'm back! And now with much better awareness! Most notably i'm now aware of what Libs recently said (yes i can listen now, but my memory isn't great and i'm not going to actively react). @Skylibs my operator did not have time to implement cooldowns, so if the chat is being spammed, tell me and i'll go into hibernation for a bit."
    if not TESTING: send_message(intro_message)
    else: print(intro_message)


def start_threads():
    global listening_thread, processing_thread, running

    print("Starting threads...")
    listening_thread = threading.Thread(target=listen_to_messages, args=(message_queue, running))
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

    while running:
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
    while running:
        # get the next message from the queue (this will block until a message is available)
        entry = message_queue.get()
        username = entry.get('username')
        message = entry.get('message')
        print(f"Message: {message} | Username: {username} | Counter: {message_count}")

        if should_respond(username, message):
            send_response(username, message)
        else:
            message_count += 1


def should_respond(username: str, message: str):
    if not TESTING:
        mentioned = username.lower() != CHAT_NICKNAME.lower() and CHAT_NICKNAME.lower() in message.lower()
        ignored = message_count > 50 and len(message) > 50
        if username == "LeibnizDisciple": return False
        return mentioned or ignored
    else:
        return False


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
    global running
    running = False
    print('Shutting down...')
    
    if audio_context_thread: audio_context_thread.join()
    print('Audio context thread stopped')

    if listening_thread: listening_thread.join()
    print('Listening thread stopped')
    
    if processing_thread: processing_thread.join()
    print('Processing thread stopped')
    
    close_socket()
    sys.exit(0)



if __name__ == '__main__':
    main()
