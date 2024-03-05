import os
import asyncio
from concurrent.futures import ThreadPoolExecutor

from twitchAPI.twitch import Twitch, TwitchUser
from twitchAPI.oauth import UserAuthenticator, refresh_access_token
from twitchAPI.type import AuthScope, UnauthorizedException, InvalidRefreshTokenException, ChatEvent
from twitchAPI.chat import Chat, ChatMessage, WhisperEvent
from twitchAPI.helper import first

from utils.models import Message
from utils.pubsub import PubSub, PubEvents


class TwitchAPI:
    pubsub: PubSub

    twitch: Twitch
    chat: Chat
    chat_history = []
    bot_user: TwitchUser

    def __init__(self, pubsub: PubSub):
        self.pubsub = pubsub

        # Subscribe to the shutdown event
        self.pubsub.subscribe(PubEvents.SHUTDOWN, self.shutdown)

        print("[INFO]: Initializing Twitch API...")
         
        with ThreadPoolExecutor() as pool:
            pool.submit(lambda:asyncio.run(self.authenticate()))
        with ThreadPoolExecutor() as pool:
            pool.submit(lambda:asyncio.run(self.init_chat()))

        print("[INFO]: Twitch API Initialized")


    # API Shutdown
    def shutdown(self):
        with ThreadPoolExecutor() as pool:
            pool.submit(lambda:asyncio.run(self.chat.leave_room(os.environ["target_channel"])))
        
        try:
            self.chat.stop()
        except:
            pass
        
        print("[INFO]: Twitch API Shutdown")


    # Initialize the chat bot
    async def init_chat(self):
        # Get bot user
        self.bot_user = await first(self.twitch.get_users(logins=[os.environ["bot_username"]]))

        # Create chat instance
        self.chat = await Chat(self.twitch)

        # Listen to chat messages
        self.chat.register_event(ChatEvent.MESSAGE, self.on_message)
        # Listen to whispers
        self.chat.register_event(ChatEvent.WHISPER, self.on_whisper)

        # We are done with our setup, lets start this bot up!
        self.chat.start()

        # Join channel
        await self.chat.join_room(os.environ["target_channel"])
    

    # This will be called whenever a message in a channel was send by either the bot OR another user
    async def on_message(self, msg: ChatMessage):
        # Check if user is the bot itself
        if msg.user.name == os.environ["bot_username"].lower():
            return

        # Add message to chat history
        self.chat_history.append(f"{msg.user.name}: {msg.text}")

        # Keep chat history at 20 messages
        if len(self.chat_history) > 20:
            self.chat_history.pop(0)

        # publish chat history
        self.pubsub.publish(PubEvents.CHAT_HISTORY, self.chat_history.copy())    

        # Create message object
        chat_message = Message(msg.user.name, msg.text, msg.user.mod)

        # Add message to message queue
        self.pubsub.publish(PubEvents.CHAT_MESSAGE, chat_message)


    # This will be called whenever a whisper was send to the bot
    async def on_whisper(self, whisper: WhisperEvent):
        self.pubsub.publish(PubEvents.WHISPER_MESSAGE, whisper)


    # Send message to chat
    def send_message(self, message: str):
        # Limit message length
        if len(message) > 500:
            message = message[:475] + "..."

        # Send message
        with ThreadPoolExecutor() as pool:
            pool.submit(lambda:asyncio.run(self.chat.send_message(os.environ["target_channel"], message)))


    # Send whisper to user
    def send_whisper(self, user: TwitchUser, message: str):
        with ThreadPoolExecutor() as pool:
            pool.submit(lambda:asyncio.run(self.twitch.send_whisper(self.bot_user.id, user.id, message)))


    # Get about section of target channel using the get_stream_info function
    def get_about_section(self):
        with ThreadPoolExecutor() as pool:
            target_channel: TwitchUser = pool.submit(lambda:asyncio.run(self.get_channel_info())).result()
            return target_channel.description


    # Get channel information
    async def get_channel_info(self):
        # Get channel
        target_channel = await first(self.twitch.get_users(logins=[os.environ["target_channel"]]))

        return target_channel


    # Authenticate Twitch API
    async def authenticate(self):
        # Initialize Twitch API
        self.twitch = Twitch(os.environ["twitch_api_client_id"],
                             os.environ["twitch_api_client_secret"])

        # Get tokens from config
        twitch_user_token: str = os.environ["twitch_user_token"]
        refresh_token: str = os.environ["twitch_user_refresh_token"]

        # Set scope
        scope = [AuthScope.CHAT_READ, AuthScope.CHAT_EDIT, AuthScope.WHISPERS_READ, AuthScope.WHISPERS_EDIT, AuthScope.USER_MANAGE_WHISPERS]

        # Check if refresh is needed
        try:
            # Refresh access token
            twitch_user_token, refresh_token = await refresh_access_token(
                    refresh_token, os.environ["twitch_api_client_id"], os.environ["twitch_api_client_secret"])
        except (UnauthorizedException, InvalidRefreshTokenException):
            # Start authentication flow
            auth = UserAuthenticator(self.twitch, scope, force_verify=True)
            try:
                twitch_user_token, refresh_token = await auth.authenticate()
            except:
                print("[ERROR]: Authentication failed")
                self.pubsub.publish(PubEvents.SHUTDOWN)
                return

        # Set user authentication
        await self.twitch.set_user_authentication(twitch_user_token, scope, refresh_token)

        # Set tokens in config
        os.environ["twitch_user_token"] = twitch_user_token
        os.environ["twitch_user_refresh_token"] = refresh_token
