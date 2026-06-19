import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Bot
    TOKEN: str = os.getenv("DISCORD_TOKEN", "")
    PREFIX: str = os.getenv("BOT_PREFIX", "!")
    OWNER_IDS: list[int] = [int(x) for x in os.getenv("OWNER_IDS", "").split(",") if x.strip().isdigit()]

    # MongoDB
    MONGODB_URI: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    DATABASE_NAME: str = os.getenv("DATABASE_NAME", "discord_bot")

    # Flask
    FLASK_SECRET_KEY: str = os.getenv("FLASK_SECRET_KEY", "change-me-in-production")
    FLASK_HOST: str = os.getenv("FLASK_HOST", "0.0.0.0")
    FLASK_PORT: int = int(os.getenv("FLASK_PORT", "5000"))

    # Discord OAuth2
    DISCORD_CLIENT_ID: str = os.getenv("DISCORD_CLIENT_ID", "")
    DISCORD_CLIENT_SECRET: str = os.getenv("DISCORD_CLIENT_SECRET", "")
    DISCORD_REDIRECT_URI: str = os.getenv("DISCORD_REDIRECT_URI", "http://localhost:5000/callback")

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", "logs/bot.log")

    # Links
    SUPPORT_SERVER: str = os.getenv("SUPPORT_SERVER", "")
    BOT_INVITE: str = os.getenv("BOT_INVITE", "")

    # Colors
    COLOR_SUCCESS: int = 0x2ECC71
    COLOR_ERROR: int = 0xE74C3C
    COLOR_WARNING: int = 0xF39C12
    COLOR_INFO: int = 0x3498DB
    COLOR_PRIMARY: int = 0x5865F2

    # Economy
    DAILY_AMOUNT: int = 250
    WORK_MIN: int = 50
    WORK_MAX: int = 300
    STARTING_BALANCE: int = 1000

    # Leveling
    XP_PER_MESSAGE: int = 15
    XP_COOLDOWN: int = 60  # seconds
    LEVEL_MULTIPLIER: float = 1.5

    # Automod
    SPAM_THRESHOLD: int = 5       # messages per interval
    SPAM_INTERVAL: int = 5        # seconds
    MENTION_LIMIT: int = 5
    CAPS_PERCENT: float = 0.7     # 70% caps = trigger

    # Starboard
    STAR_THRESHOLD: int = 3

    # Giveaway
    GIVEAWAY_EMOJI: str = "🎉"

config = Config()
