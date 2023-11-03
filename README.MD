# TwitchBot

## :warning: Warning
I only tested this on windows so I don't know if it works on other operating systems. **But it should**.

## Requirements
- Python 3.9+ [Download](https://www.python.org/downloads/)

## Setup
1. Install the requirements `pip install -r requirements.txt`
2. For the First time run `python setup.py`. It will create a config file and download the whisper model.
3. Fill out the config file. See [Config File](#config-file) for detailed info.

## Running
1. Run `python main.py`
- To input a [command](#commands) just start typing in the console and press enter.

## TODO
- [ ] Add 7tv emote support
- [ ] Fetch the current playing song from spotify

## Config File
- `must fill` **target_channel** - The channel the bot will join
- `must fill` **bot_username** - The bots username
- `must fill` **twitch_api_client_id** - The client id for the twitch api - [Get it here](https://dev.twitch.tv/console/apps)
- `must fill` **twitch_api_client_secret** - The client secret for the twitch api - [Get it here](https://dev.twitch.tv/console/apps)
- `automatically filled` **twitch_user_token** - The oauth token for the twitch user (When running the bot for the first time it will open a browser window to get the token, make sure you are logged in to the correct account)
- `automatically filled` **twitch_user_refresh_token** - The refresh token for the twitch user
- `must fill` **openai_api_key** - The openai api key - [Get it here](https://platform.openai.com/account/api-keys)
- `has a default value` **openai_api_max_tokens_total** - The max tokens for a single request
- `has a default value` **openai_api_max_tokens_response** - The max tokens for a single response
- `must fill` **prompt_extras** - Extra streamer specific info to be added to the prompt (e.g. the streamers nicknames, age, hobbies, the about section, the art section, etc.)
- `automatically filled` **detection_words** - The 'verbal' words that will trigger the bot to respond

## Commands 
The following commands are available to the mods via !{bot_username}. They are also available from the script console:
+ **timeout [*username*] [*seconds*]** - the bot ignores the user for the given duration
+ **reset [*username*]** - clears the conversation memory with the given user
+ **cooldown [*minutes*]** - puts the bot in cooldown for the given duration (ignores all messages)
+ **ban [*username*]** - bans the user, so that the bot will not respond to them
+ **unban [*username*]** - unbans the user
+ **slowmode [*seconds*]** - sets the slow mode for the bot
+ **banword [*word*]** - ignotes all messages containing the given word
+ **unbanword [*word*]** - unbans the word

The following commands are only available from the script console:
+ **op [*message*]** - sends a message in chat as (operator)
+ **set-emt [*count*]** - (**E**ngage **M**essage **T**hreshold) sets the amount of chats the bot will receive before it will engage without being mentioned
+ **set-elmt [*count*]** - sets the minimum length of the message the bot will engage with when EMT is reached
+ **test-msg [*message*]** - sends a message to the OpenAI model to test the response
+ **intro** - sends the intro message to chat
+ **exit** - exits the script
