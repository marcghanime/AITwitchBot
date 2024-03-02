# TwitchBot

## :warning: Warning
- The twitch account for the bot needs to have a verified phone number to be able to send whispers.

## Requirements
- Python 3.11+ [Download](https://www.python.org/downloads/)

## Setup
1. Install the requirements `pip install -r requirements.txt`
2. For the First time run `python setup.py`. It will create a config file.
3. Fill out the config file. See [Config File](#config-file) for detailed info.
4. Authenticate with twitch by running `python utils/authentication.py`. It will open a browser window for you to login and authorize the bot.

## Running
1. In a different terminal Run `python main.py`
- To input a [command](#commands) send a whisper to the bot through twitch.

## TODO
- [ ] Fix slow mode
- [ ] Use environment variables for config
- [ ] When environment variables are setup, remove setup.py
- [ ] Set backend websocket url as an environment variable
- [ ] Replace prints with propper logging
- [ ] Better way to run whisper_live backend
- [ ] Implement RAG for chat history and transcripts
- [ ] Add 7tv emote support
- [ ] Run it in a k8s cluster
- [ ] Improve authentication process (with a frontend maybe)
- [ ] Get prompt extras from twitch about section

## Config File
| Entry | Type | Description |
| --- | --- | --- |
| **target_channel** | must fill | The channel the bot will join |
| **bot_username** | must fill | The bots username |
| **admin_username** | optional | The username of the person running the bot (used for admin commands) |
| **twitch_api_client_id** | must fill | The client id for the twitch api [Get it here](https://dev.twitch.tv/console/apps) |
| **twitch_api_client_secret** | must fill | The client secret for the twitch api [Get it here](https://dev.twitch.tv/console/apps) |
| **twitch_user_token** | automatically filled | The oauth token for the twitch user |
| **twitch_user_refresh_token** | automatically filled | The refresh token for the twitch user |
| **openai_api_key** | must fill | The openai api key [Get it here](https://platform.openai.com/account/api-keys) |
| **openai_api_max_tokens_total** | has a default value | The max tokens for a single request |
| **openai_api_max_tokens_response** | has a default value | The max tokens for a single response |
| **shazam_api_key** | must fill | The shazam api key [Get it here](https://rapidapi.com/apidojo/api/shazam) |
| **prompt_extras** | optional | Extra streamer specific info to be added to the prompt (e.g. the streamers nicknames, age, hobbies, etc.) |
| **detection_words** | automatically filled | The 'verbal' words that will trigger the bot to respond |

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

The following commands are only available to the **admin**:
+ **op [*message*]** - sends a message in chat as (operator)
+ **set-emt [*count*]** - (**E**ngage **M**essage **T**hreshold) sets the amount of chats the bot will receive before it will engage without being mentioned
+ **set-elmt [*count*]** - sets the minimum length of the message the bot will engage with when EMT is reached
+ **test-msg [*message*]** - sends a message to the OpenAI model to test the response
+ **intro** - sends the intro message to chat
+ **add-det-word [*word*]** - adds word to the list of verbal mention keywords
+ **react** - trigger a reaction from the bot
+ **exit** - exits the script
