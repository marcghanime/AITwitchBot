# TwitchBot

## :warning: Warning
I only tested this on windows so I don't know if it works on other operating systems. But it should.

## Requirements
- Python 3.6+ [Download](https://www.python.org/downloads/)
- Virtual Audio Cable [Download](https://vb-audio.com/Cable/)

## Setup
1. Install the requirements `pip install -r requirements.txt`
2. For the First time run `python setup.py`. It will create a config file and download the whisper model.
3. Fill out the config file. See [Config File](#Config-File) for detailed info.

## Running
1. Run `python main.py`
- To input a [command](#Commands) just start typing in the console and press enter.

## Config File
- **twitch_channel** - The channel the bot will join
- **bot_nickname** - The bots username
- **twitch_api_client_id** - The client id for the twitch api [Get it here](https://dev.twitch.tv/console/apps)
- **twitch_api_client_secret** - The client secret for the twitch api [Get it here](https://dev.twitch.tv/console/apps)
- **twitch_api_oauth_token** `automatically filled` - The oauth token for the twitch api
- **twitch_chat_server** `has a default value` - The twitch chat server
- **twitch_chat_port** `has a default value` - The twitch chat port
- **twitch_user_token** `automatically filled` - The oauth token for the twitch user (When running the bot for the first time it will open a browser window to get the token, make sure you are logged in to the correct account)
- **twitch_user_refresh_token** `automatically filled` - The refresh token for the twitch user
- **openai_api_key** - The openai api key [Get it here](https://platform.openai.com/account/api-keys)
- **openai_api_max_tokens_total** `has a default value` - The max tokens for a single request
- **openai_api_max_tokens_response** `has a default value` - The max tokens for a single response

## Commands 
+ **timeout [*username*] [*seconds*]** the bot ignores the user for the given duration
+ **reset [*username*]** clears the conversation memory with the given user
+ **cooldown [*minutes*]** puts the bot in cooldown for the given duration (ignores all messages)
+ **ban [*username*]** bans the user, so that the bot will not respond to them
+ **unban [*username*]** unbans the user
+ **slowmode [*seconds*]** sets the slow mode for the bot