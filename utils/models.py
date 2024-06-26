from dataclasses import dataclass, field


@dataclass
class Config:
    target_channel: str = ""
    bot_username: str = ""
    admin_username: str = ""
    twitch_api_client_id: str = ""
    twitch_api_client_secret: str = ""
    twitch_user_token: str = ""
    twitch_user_refresh_token: str = ""
    openai_api_key: str = ""
    shazam_api_key: str = ""
    deepgram_api_key: str = ""
    google_api_key: str = ""
    google_cse_id: str = ""


@dataclass
class Memory:
    cooldown_time: float = 0.0
    slow_mode_seconds: int = 0
    reaction_time: float = 0.0
    banned_words: list = field(default_factory=list)
    banned_users: list = field(default_factory=list)
    timed_out_users: dict = field(default_factory=dict)  # Dict[str, float]
    conversations: dict = field(default_factory=dict)  # Dict[str, list]


@dataclass
class Message:
    username: str = ""
    text: str = ""
    mod: bool = False