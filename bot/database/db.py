import logging
from motor.motor_asyncio import AsyncIOMotorClient
from config import config

logger = logging.getLogger(__name__)

class Database:
    client: AsyncIOMotorClient = None
    db = None

    @classmethod
    async def connect(cls):
        logger.info("Connecting to MongoDB...")
        cls.client = AsyncIOMotorClient(config.MONGODB_URI)
        cls.db = cls.client[config.DATABASE_NAME]
        await cls._ensure_indexes()
        logger.info(f"Connected to MongoDB database: {config.DATABASE_NAME}")

    @classmethod
    async def disconnect(cls):
        if cls.client:
            cls.client.close()
            logger.info("Disconnected from MongoDB")

    @classmethod
    async def _ensure_indexes(cls):
        db = cls.db
        await db.guilds.create_index("guild_id", unique=True)
        await db.tickets.create_index([("guild_id", 1), ("channel_id", 1)])
        await db.tickets.create_index("ticket_id")
        await db.applications.create_index([("guild_id", 1), ("message_id", 1)])
        await db.moderation.create_index([("guild_id", 1), ("user_id", 1)])
        await db.economy.create_index([("guild_id", 1), ("user_id", 1)], unique=True)
        await db.levels.create_index([("guild_id", 1), ("user_id", 1)], unique=True)
        await db.warnings.create_index([("guild_id", 1), ("user_id", 1)])
        await db.embeds.create_index([("guild_id", 1), ("name", 1)])
        await db.custom_commands.create_index([("guild_id", 1), ("name", 1)], unique=True)
        await db.giveaways.create_index("message_id")
        await db.polls.create_index("message_id")
        await db.suggestions.create_index([("guild_id", 1), ("suggestion_id", 1)])
        await db.starboard.create_index([("guild_id", 1), ("original_id", 1)])
        await db.afk.create_index([("guild_id", 1), ("user_id", 1)], unique=True)
        await db.reaction_roles.create_index([("guild_id", 1), ("message_id", 1)])
        logger.info("Database indexes ensured")


async def get_guild_config(guild_id: int) -> dict:
    doc = await Database.db.guilds.find_one({"guild_id": guild_id})
    if not doc:
        doc = {"guild_id": guild_id}
        await Database.db.guilds.insert_one(doc)
    return doc


async def update_guild_config(guild_id: int, data: dict):
    await Database.db.guilds.update_one(
        {"guild_id": guild_id},
        {"$set": data},
        upsert=True
    )
