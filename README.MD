# AI Twitch Bot

This is a twitch ai bot that is able to read chat, listen and see the stream. This started as a fun project but i if you want to contribute feel free :)

## :warning: Warning
- The twitch account for the bot needs to have a verified phone number to be able to send whispers.

## Requirements
- Python 3.11+ [Download](https://www.python.org/downloads/)
- ffmpeg [Get](https://www.ffmpeg.org/download.html)

## Setup
1. Install the requirements `pip install -r requirements.txt`
2. If no `config.json` file is present in root, run `python main.py` to create one.
2. Fill out the config file. See [Config File](#config-file) for detailed info.
3. Authenticate with twitch by running `python utils/authentication.py`. It will open a browser window for you to login and authorize the bot.

## Running
1. Run `python main.py`
- To input a [command](#commands) send a whisper to the bot through twitch.

## TODO
- [ ] Auto start the bot on stream start
- [ ] Add other deepgram keywords option
- [ ] Run pubsub callback asynchronously
- [ ] Add stream category to the context
- [ ] Fix slow mode
- [ ] Implement RAG for chat history and transcripts
- [ ] Add 7tv emote support
- [ ] Revamp authentication method
- [ ] Add following and other common commands as bot functions

## Config File
| Entry | Type | Description |
| --- | --- | --- |
| **target_channel** | must fill | The channel the bot will join |
| **bot_username** | must fill | The bots username |
| **admin_username** | optional | The username of the person running the bot |
| **twitch_api_client_id** | must fill | The client id for the twitch api [Get it here](https://dev.twitch.tv/console/apps) |
| **twitch_api_client_secret** | must fill | The client secret for the twitch api [Get it here](https://dev.twitch.tv/console/apps) |
| **twitch_user_token** | automatically filled | The oauth token for the twitch user |
| **twitch_user_refresh_token** | automatically filled | The refresh token for the twitch user |
| **openai_api_key** | must fill | The openai api key [Get it here](https://platform.openai.com/account/api-keys) |
| **shazam_api_key** | must fill | The shazam api key [Get it here](https://rapidapi.com/apidojo/api/shazam) |
| **deepgram_api_key** | must fill | The deepgram api key [Get it here](https://console.deepgram.com) |
| **google_api_key** | must fill | The google api key [Get it here](https://console.cloud.google.com/apis/credentials) |
| **google_cse_id** | must fill | The google custom search engine id [Get it here](https://cse.google.com/cse/all) |

## Commands 
The following commands are available to **admin**, **streamer** and **mods** via twitch whispers to the bot:
+ **timeout [*username*] [*seconds*]** - the bot ignores the user for the given duration
+ **reset [*username*]** - clears the conversation memory with the given user
+ **cooldown [*minutes*]** - puts the bot in cooldown for the given duration (ignores all messages)
+ **ban [*username*]** - bans the user, so that the bot will not respond to them
+ **unban [*username*]** - unbans the user
+ **slowmode [*seconds*]** - sets the slow mode for the bot
+ **banword [*word*]** - ignotes all messages containing the given word
+ **unbanword [*word*]** - unbans the word
+ **op [*message*]** - sends a message in chat as (operator)
+ **set-emt [*count*]** - (**E**ngage **M**essage **T**hreshold) sets the amount of chats the bot will receive before it will engage without being mentioned
+ **set-elmt [*count*]** - sets the minimum length of the message the bot will engage with when EMT is reached
+ **test-msg [*message*]** - sends a message to the OpenAI model to test the response
+ **intro** - sends the intro message to chat
+ **react** - trigger a reaction from the bot
+ **exit** - exits the script
