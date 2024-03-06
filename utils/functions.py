import os
import re
import sys
import json
import dataclasses

from utils.models import Config, Memory

# Remove quotations from the message
def remove_quotations(text: str):
    while text.startswith('"') and text.endswith('"'):
        text = str(text[1:-1])
    return str(text)


# Remove mentions from the message
def remove_mentions(text: str, username: str, bot_username: str):
    text = text.replace("@User", "").replace("@user", "").replace(f"@{bot_username}", "").replace(
        f"@{username}:", "").replace(f"@{username}", "").replace(f"{bot_username}:", "")
    return text


# Remove links from the message
def remove_links(text: str):
    link_regex = r"\b[a-zA-Z]+\.[a-zA-Z]+\b"
    links = re.findall(link_regex, text)
    # Replace links with a placeholder
    for link in links:
        text = text.replace(link, '***')

    return text


# Remove hashtags from the message
def remove_hashtags(text: str):
    # Define the regex pattern to match hashtags
    pattern = r'#\w+'

    # Use the sub() function from the re module to remove the hashtags
    cleaned_text = re.sub(pattern, '', text)

    return cleaned_text


# Remove unwanted charachters from the message
def clean_message(message: str, username: str, finish_reason: str, bot_username: str):
    message = remove_mentions(message, username, bot_username)
    message = remove_hashtags(message)
    message = remove_links(message)
    message = message.replace("\n", " ")
    message = remove_quotations(message)
    if finish_reason == "length":
        message = f"{message}..."
    return message


# Check if the message contains any banned words
def check_banned_words(message: str, banned_words: list):
    return next((word for word in banned_words if word.lower() in message.lower()), None)


# Remove image messages from the messages list
def remove_image_messages(messages: list):
    filtered_messages = [msg for msg in messages if not (
        isinstance(msg.get("content"), list) and any(
            sub_msg.get("type") == "image_url" for sub_msg in msg["content"]
        )
    )]

    return filtered_messages


# Set the environment variables
def set_environ(config: Config):
    # For each key, value pair in the config, set them as environment variables
    for key, value in dataclasses.asdict(config).items():
        os.environ[key] = str(value)


# Load config from json file
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


# Save config to json file
def save_config(config: Config) -> None:
    # update the config form the environment variables
    for key, value in os.environ.items():
        if key in dataclasses.fields(Config):
            setattr(config, key, value)

    with open("config.json", "w") as outfile:
        json.dump(dataclasses.asdict(config), outfile, indent=4)


# Load memory from json file
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


# Save memory to json file
def save_memory(memory: Memory) -> None:
    with open("memory.json", "w") as outfile:
        json.dump(dataclasses.asdict(memory), outfile, indent=4)