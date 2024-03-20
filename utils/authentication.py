import asyncio
import logging

from models import Config

from utils.functions import load_config, save_config

from twitchAPI.twitch import Twitch
from twitchAPI.oauth import UserAuthenticator, refresh_access_token
from twitchAPI.type import AuthScope, UnauthorizedException, InvalidRefreshTokenException

from models import Config
import json
import dataclasses
import asyncio

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

def save_config(config: Config) -> None:
    with open("config.json", "w") as outfile:
        json.dump(dataclasses.asdict(config), outfile, indent=4)
 
# Authenticate Twitch API
async def authenticate():
    config: Config = load_config()

    # Initialize Twitch API
    twitch = Twitch(config.twitch_api_client_id,
                            config.twitch_api_client_secret)

    # Get tokens from config
    twitch_user_token: str = config.twitch_user_token
    refresh_token: str = config.twitch_user_refresh_token

    # Set scope
    scope = [AuthScope.CHAT_READ, AuthScope.CHAT_EDIT, AuthScope.WHISPERS_READ, AuthScope.WHISPERS_EDIT, AuthScope.USER_MANAGE_WHISPERS]

    # Check if refresh is needed
    try:
        # Refresh access token
        twitch_user_token, refresh_token = await refresh_access_token(
                refresh_token, config.twitch_api_client_id, config.twitch_api_client_secret)
    except (UnauthorizedException, InvalidRefreshTokenException):
        # Start authentication flow
        auth = UserAuthenticator(twitch, scope, force_verify=True)
        try:
            twitch_user_token, refresh_token = await auth.authenticate()
        except Exception as e:
            logging.error(f"Authentication failed: {e}")
            return

    # Set user authentication
    await twitch.set_user_authentication(twitch_user_token, scope, refresh_token)

    # Set tokens in config
    config.twitch_user_token = twitch_user_token
    config.twitch_user_refresh_token = refresh_token

    # Save config
    save_config(config)

if __name__ == "__main__":
    asyncio.run(authenticate())