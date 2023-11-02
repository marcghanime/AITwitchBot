import queue
import asyncio
from concurrent.futures import ThreadPoolExecutor

from twitchAPI.twitch import Twitch
from twitchAPI.oauth import UserAuthenticator, refresh_access_token
from twitchAPI.type import AuthScope, UnauthorizedException, InvalidRefreshTokenException, ChatEvent
from twitchAPI.chat import Chat, ChatMessage

from models import Config


class TwitchAPI:
    config: Config
    twitch: Twitch
    chat: Chat
    message_queue: queue.Queue[ChatMessage]
    chat_history = []

    TESTING: bool = False

    def __init__(self, config: Config, testing: bool):
        self.config = config
        self.TESTING = testing

        self.message_queue = queue.Queue()

        print("Initializing Twitch API...")
         
        with ThreadPoolExecutor() as pool:
            pool.submit(lambda:asyncio.run(self.authenticate()))
        with ThreadPoolExecutor() as pool:
            pool.submit(lambda:asyncio.run(self.init_chat()))
        print("Twitch API Initialized")


    # API Shutdown
    def shutdown(self):
        with ThreadPoolExecutor() as pool:
            pool.submit(lambda:asyncio.run(self.chat.leave_room(self.config.twitch_channel)))
        self.chat.stop()
        with ThreadPoolExecutor() as pool:
            pool.submit(lambda:asyncio.run(self.twitch.close()))
        print("Twitch API Shutdown")


    # Initialize the chat bot
    async def init_chat(self):
        # Create chat instance
        self.chat = await Chat(self.twitch)

        # Listen to chat messages
        self.chat.register_event(ChatEvent.MESSAGE, self.on_message)

        # We are done with our setup, lets start this bot up!
        self.chat.start()

        # Join channel
        await self.chat.join_room(self.config.twitch_channel)


    # This will be called whenever a message in a channel was send by either the bot OR another user
    async def on_message(self, msg: ChatMessage):
        # Check if user is the bot itself
        if msg.user.name == self.config.bot_nickname.lower():
            return

        # Add message to chat history
        self.chat_history.append(f"{msg.user.name}: {msg.text}")

        # Keep chat history at 20 messages
        if len(self.chat_history) > 20:
            self.chat_history.pop(0)

        # Add message to message queue
        self.message_queue.put(msg)


    # Send message to chat
    def send_message(self, message: str):
        # Limit message length
        if len(message) > 500:
            message = message[:475] + "..."

        # Send message
        if not self.TESTING:
            with ThreadPoolExecutor() as pool:
                pool.submit(lambda:asyncio.run(self.chat.send_message(self.config.twitch_channel, message)))


    # Get stream information
    async def get_stream_info(self):
        target_channel = None
        target_stream = None

        # Get channel
        channels = self.twitch.get_users(logins=[self.config.twitch_channel])
        async for channel in channels:
            target_channel = channel
            break

        # Check if channel was found
        if not target_channel:
            return

        # Get stream
        streams = self.twitch.get_streams(user_id=target_channel.id)
        async for stream in streams:
            target_stream = stream
            break

        return target_stream


    # Authenticate Twitch API
    async def authenticate(self):
        # Initialize Twitch API
        self.twitch = Twitch(self.config.twitch_api_client_id,
                             self.config.twitch_api_client_secret)

        # Get tokens from config
        twitch_user_token: str = self.config.twitch_user_token
        refresh_token: str = self.config.twitch_user_refresh_token

        # Set scope
        scope = [AuthScope.CHAT_READ, AuthScope.CHAT_EDIT]

        # Check if refresh is needed
        try:
            # Refresh access token
            twitch_user_token, refresh_token = await refresh_access_token(
                    refresh_token, self.config.twitch_api_client_id, self.config.twitch_api_client_secret)
        except (UnauthorizedException, InvalidRefreshTokenException):
            # Start authentication flow
            auth = UserAuthenticator(self.twitch, scope, force_verify=True)
            auth_result = await auth.authenticate()
            if auth_result:
                twitch_user_token, refresh_token = auth_result

        # Set user authentication
        await self.twitch.set_user_authentication(twitch_user_token, scope, refresh_token)

        # Set tokens in config
        self.config.twitch_user_token = twitch_user_token
        self.config.twitch_user_refresh_token = refresh_token


    # Return chat history
    def get_chat_history(self):
        return self.chat_history.copy()
    
    # Return the message queue
    def get_message_queue(self):
        return self.message_queue
