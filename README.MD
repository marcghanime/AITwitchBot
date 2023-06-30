# TwitchBot

## :warning: Warning
I only tested this on windows so I don't know if it works on other operating systems. But it should.

## Requirements
- Python 3.6+ [Download](https://www.python.org/downloads/)
- Tesseract [Installation](https://tesseract-ocr.github.io/tessdoc/Installation.html)

## Setup
1. Install the requirements `pip install -r requirements.txt`
2. For the First time run `python main.py` and it will create a config file.
3. Fill out the config file. See [Config File](#Config-File) for detailed info.

## Running
1. Run `python main.py`
2. To get audio captions in the script [enable captions in Chrome browser](https://support.google.com/chrome/answer/10538231) and the script should auto detect the window called Live Caption and use text recognition from that window to get the captions.
- To input a command just start typing in the console and press enter.

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