import os
import re
import sys
import json
import time
import logging
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


# Clean the conversation history
def clean_conversation(messages: list):
    messages = remove_old_images(messages)
    messages = remove_old_contexts(messages)
    messages = fix_responses_format(messages)
    messages = remove_null_messages(messages)
    return messages


# Remove image messages from the messages list
def remove_old_images(messages: list):
    # iterate through the messages with index
    for i, message in enumerate(messages):
        # check if the message content is a list
        if isinstance(message.get("content"), list):
            # iterate through the sub messages
            for sub_message in message["content"]:
                # get the text from the sub message
                if sub_message.get("type") == "text":
                    # update the message content in the messages list
                    messages[i]["content"] = sub_message["text"]
                    break
                
    return messages


# Remove old contexts from the messages list (context is between two delimiter messages <<context>> <</context>>)
def remove_old_contexts(messages: list):
    # iterate through the messages with index
    for i, message in enumerate(messages):
        # skip system messages
        role = message.get("role") 
        if role == "system":
            continue

        # get the message content
        text = message.get("content")

        # use regex to find and remove the context
        text = re.sub(r"<<context>>.*<</context>>", "", text, flags=re.DOTALL)

        # update the message content in the messages list
        messages[i]["content"] = text.strip().strip("\n")

    return messages


# Remove the 'Reply to the following message' text from the start of users responses
def fix_responses_format(messages: list):
    # iterate through the messages with index
    for i, message in enumerate(messages):
        # skip non user messages
        role = message.get("role")
        if role != "user":
            continue

        # get the message content
        text: str = message.get("content")

        # remove the unwanted text from the start of the message
        text = text.replace("Reply to the following chat message ", "").strip("'")

        # update the message content in the messages list
        messages[i]["content"] = text

    return messages


def remove_null_messages(messages: list):
    return [message for message in messages if message.get("content")]


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
    # Clean all conversations
    for user, conversation in memory.conversations.items():
        memory.conversations[user] = clean_conversation(conversation)

    # Save the memory to the json file
    with open("memory.json", "w") as outfile:
        json.dump(dataclasses.asdict(memory), outfile, indent=4)


def setup_logging(level: int = logging.DEBUG):
    # Create the directory if it does not exist
    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True) 

    # Get the current time as a string
    current_time = time.strftime("%Y-%m-%d_%H-%M-%S")

    # Set up logging
    logging.basicConfig(filename=f'logs/{current_time}.log', filemode='w', level=level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')