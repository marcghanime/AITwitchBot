import signal
import threading
import sys
import queue
import os
import msvcrt
import json
import time
import dataclasses
import random
from ChatAPI import ChatAPI
from TwitchAPI import TwitchAPI
from AudioAPI import AudioAPI
from models import Config, Memory
from twitchAPI.chat import ChatMessage
from typing import List

TESTING: bool = False

TRANSCRIPTION_MISTAKES = {
    "libs": ["lips", "looks", "lib's", "lib", "lipsh"],
    "gpt": ["gpc", "gpg", "gbc", "gbt", "shupiti"]
}

# Thread variables
processing_thread = None
audio_context_thread = None
stop_event = threading.Event()

message_count: int = 0

command_help: str = ""
prompt = ""
react_string = ""

# TODO add emote support
# TODO spotify integration


twitch_api: TwitchAPI
chat_api: ChatAPI
audio_api: AudioAPI
config: Config
memory: Memory

# create a queue to hold the messages
message_queue: queue.Queue[ChatMessage] = queue.Queue()
IGNORED_MESSAGE_THRESHOLD: int = 50
LENGTH_MESSAGE_THRESHOLD: int = 50


def main():
    global twitch_api, chat_api, audio_api, config, memory

    signal.signal(signal.SIGINT, shutdown_handler)

    # Load data
    config = load_config()
    memory = load_memory()
    # set the first reaction time to 5 minutes from now
    memory.reaction_time = time.time() + 300

    # Setup
    setup_strings()
    add_mistakes_to_detection_words()

    # Twitch API
    twitch_api = TwitchAPI(config, message_queue, testing=TESTING)

    # Audio API
    audio_api = AudioAPI(config, mentioned_verbally)

    # Chat API
    chat_api = ChatAPI(config, memory, twitch_api,
                       audio_api, prompt, testing=TESTING)

    start_threads()
    cli()


def setup_strings():
    global command_help, prompt, react_string

    command_help = f"Must be {config.twitch_channel} or a Mod. Usage: !{config.bot_nickname} [command] in chat || timeout [username] [seconds] | reset [username] | cooldown [minutes] | ban [username] | unban [username] | slowmode [seconds] | banword [word] | unbanword [word]"

    prompt = f"You are an AI twitch chatter. Keep your messages short, under 20 words and don't put usernames in the message. Be non verbose, sweet and sometimes funny. The following are some info about the stream you're watching: "
    prompt += config.prompt_extras

    react_string = f"repond or react to the last thing {config.twitch_channel} said based only on the provided live captions"


def handle_commands(input: str, external: bool = True) -> None:
    global memory

    input = input.lower().replace(f"!{config.bot_nickname.lower()} ", "").replace(
        f"!{config.bot_nickname.lower()}", "")

    # reset <username> - clears the conversation memory with the given username
    if input.startswith("reset "):
        username: str = input.split(" ")[1]
        chat_api.clear_user_conversation(username)
        twitch_api.send_message(
            f"Conversation with {username} has been reset.")

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
        twitch_api.send_message(
            f"{username} will be ignored for {duration} seconds.")

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

    elif input.startswith("banword "):
        word = input.split(" ", 1)[1]
        memory.banned_words.append(word)
        twitch_api.send_message(f"'{word}' added to banned words.")

    elif input.startswith("unbanword "):
        word = input.split(" ", 1)[1]
        if word in memory.banned_words:
            memory.banned_words.remove(word)
        twitch_api.send_message(f"'{word}' removed from banned words.")

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
        if TESTING:
            send_response(username, message)

    # add-det-word <word> - adds a word to the detection words
    elif input.startswith("add-det-word ") and not external:
        word = input.split(" ", 1)[1]
        config.detection_words.append(word)

    elif input == ("intro") and not external:
        if not TESTING:
            send_intro()

    elif input == ("exit") and not external:
        shutdown_handler(None, None)


def send_intro():
    intro_message = f"Hiya, I'm back <3 !{config.bot_nickname} for mod commands or checkout my channel pannels."
    twitch_api.send_message(intro_message)


def start_threads():
    global processing_thread, audio_context_thread

    print("Starting threads...")
    processing_thread = threading.Thread(target=process_messages)
    processing_thread.daemon = True
    processing_thread.start()

    audio_context_thread = threading.Thread(
        target=audio_api.listen_to_audio, args=(stop_event,))
    audio_context_thread.daemon = True
    audio_context_thread.start()


def process_messages():
    global message_count
    while not stop_event.is_set():
        # get the next message from the queue (this will block until a message is available or 2.5 seconds have passed)
        try:
            entry = message_queue.get(timeout=2.5)
        except queue.Empty:
            continue

        username = entry.user.name
        message = entry.text

        if message.lower().startswith(f"!{config.bot_nickname.lower()}"):
            if entry.user.mod or entry.user.name == config.twitch_channel.lower():
                if message.lower() == f"!{config.bot_nickname.lower()}":
                    twitch_api.send_message(command_help)
                else:
                    handle_commands(message)

        elif mentioned(username, message) and moderation(username):
            send_response(username, message)
            if memory.slow_mode_seconds > 0:
                time.sleep(memory.slow_mode_seconds)

        elif react() and moderation(""):
            send_response(config.twitch_channel, react_string, react=True)
            memory.reaction_time = time.time() + random.randint(300, 600)  # 10-15 minutes

        elif engage(message) and moderation(username):
            send_response(username, f"@{config.twitch_channel} {message}")
            if memory.slow_mode_seconds > 0:
                time.sleep(memory.slow_mode_seconds)

        else:
            message_count += 1


def cli():
    old_message_count = message_count
    old_captions = ""
    captions = ""

    os.system('cls')
    print(
        f"Message-Counter: {message_count}\n Captions: \n {captions}")

    while not stop_event.is_set():
        try:
            captions = " ".join(audio_api.transcription_queue1.get(timeout=1))
        except:
            captions = old_captions

        time_to_reaction = memory.reaction_time - time.time()

        # Check if there is input available on stdin
        if msvcrt.kbhit():
            user_input = input("Enter something: ")
            handle_commands(user_input, external=False)

        elif old_message_count != message_count or old_captions != captions:
            os.system('cls')
            print(
                f"Counter: {message_count} | Time to reaction: {time_to_reaction}\nCaptions:\n{captions}")

            old_message_count = message_count
            old_captions = captions

        time.sleep(1)


def moderation(username: str) -> bool:
    if TESTING:
        return False
    if username in memory.banned_users:
        return False
    if time.time() < memory.cooldown_time:
        return False
    if username in memory.timed_out_users and time.time() < memory.timed_out_users[username]:
        return False
    if username in memory.timed_out_users:
        del memory.timed_out_users[username]  # remove if time is up
    return True


def mentioned(username: str, message: str) -> bool:
    return username != config.bot_nickname.lower() and config.bot_nickname.lower() in message.lower()


def engage(message: str) -> bool:
    return message_count > IGNORED_MESSAGE_THRESHOLD and len(message) > LENGTH_MESSAGE_THRESHOLD


def react() -> bool:
    return time.time() > memory.reaction_time


def send_response(username: str, message: str, react: bool = False, respond: bool = False):
    global message_count
    bot_response = None

    if react:
        ai_response = chat_api.get_response_AI(
            username, message, no_twitch_chat=True)
        if ai_response:
            bot_response = f"{ai_response}"
            chat_api.clear_user_conversation(username)

    elif respond:
        ai_response = chat_api.get_response_AI(
            username, message, no_audio_context=True)
        if ai_response:
            bot_response = f"@{username} {ai_response}"
            chat_api.clear_user_conversation(username)

    else:
        ai_response = chat_api.get_response_AI(username, message)
        if ai_response:
            bot_response = f"@{username} {ai_response}"

    if bot_response:
        twitch_api.send_message(bot_response)
        message_count = 0


def mentioned_verbally(audio_transcription: List[str]):
    lines = audio_api.detected_lines_queue.get()
    respond: bool = False
    transctiption_index = None

    for detection_index, entry in enumerate(lines):
        line: str = entry['line']
        fixed_line: str = entry['fixed_line']
        responded: bool = entry['responded']
        
        try:
            transctiption_index = audio_transcription.index(line)
        except ValueError:
            continue
        audio_transcription[transctiption_index] = fixed_line

        if not responded and not respond:
            respond = True
            audio_api.detected_lines[detection_index]['responded'] = True

    if respond and transctiption_index:
        captions = " ".join(
            audio_transcription[transctiption_index - 2: transctiption_index + 4])
        message = f"{config.twitch_channel} talked to/about you ({config.bot_nickname}) in the following captions: '{captions}' only respond to what they said to/about you ({config.bot_nickname})"
        send_response(config.twitch_channel, message, respond=True)


# Adds all possible transcription mistakes to the detection words
def add_mistakes_to_detection_words():
    for correct, wrong_list in TRANSCRIPTION_MISTAKES.items():
        word_list = filter(lambda x: correct in x, config.detection_words)
        for word in word_list:
            index = config.detection_words.index(word)
            wrong_words = list(
                map(lambda wrong: word.replace(correct, wrong), wrong_list))
            wrong_words = list(
                filter(lambda word: word not in config.detection_words, wrong_words))
            config.detection_words[index + 1: index + 1] = wrong_words


def load_config() -> Config:
    try:
        with open("config.json", "r") as infile:
            json_data = json.load(infile)
            loaded_config = Config(**json_data)
            return loaded_config

    except FileNotFoundError:
        print("Config file not found. Creating new config file...")

        with open("config.json", "w") as outfile:
            json.dump(dataclasses.asdict(Config()), outfile, indent=4)

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
        with open("memory.json", "w") as outfile:
            json.dump(dataclasses.asdict(Memory()), outfile, indent=4)
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

    if processing_thread:
        processing_thread.join()
    print('Processing thread stopped')

    if audio_context_thread:
        audio_context_thread.join()
    print('Audio context thread stopped')

    twitch_api.shutdown()
    print('Twitch API stopped')

    print('Saving config...')
    save_config()

    print('Saving memory...')
    save_memory()

    sys.exit(0)


if __name__ == '__main__':
    main()
