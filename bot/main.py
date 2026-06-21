"""
Professional Discord Bot — Main Entry Point
"""
import asyncio
import os
import sys
import logging
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

# Ensure bot/ is in path so relative imports work
sys.path.insert(0, os.path.dirname(__file__))

from config import config
from utils.logger import setup_logger
from database import Database

logger = setup_logger("bot")

EXTENSIONS = [
    "cogs.admin",
    "cogs.moderation",
    "cogs.tickets",
    "cogs.applications",
    "cogs.logs",
    "cogs.embeds",
    "cogs.utility",
    "cogs.automod",
    "cogs.welcome",
    "cogs.economy",
    "cogs.extra",
    "cogs.help",
    "cogs.voicechannels",
    "cogs.dm",
    "cogs.privaterooms",
    "cogs.serverstats",
]


class DiscordBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(
            command_prefix=config.PREFIX,
            intents=intents,
            help_command=None,
            case_insensitive=True,
        )
        self.start_time = None

    async def setup_hook(self):
        logger.info("Running setup hook...")

        # Connect to database
        await Database.connect()

        # Register persistent views so button interactions survive restarts
        from views.vc_panel import VCPanelView
        from views.applications import ApplicationPanelView
        self.add_view(VCPanelView())
        self.add_view(ApplicationPanelView([]))

        # Load extensions
        failed = []
        for ext in EXTENSIONS:
            try:
                await self.load_extension(ext)
                logger.info(f"Loaded extension: {ext}")
            except Exception as e:
                logger.error(f"Failed to load extension {ext}: {e}", exc_info=True)
                failed.append(ext)

        if failed:
            logger.warning(f"Failed to load {len(failed)} extension(s): {', '.join(failed)}")

        # Sync application commands globally
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} application command(s) globally")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}", exc_info=True)

    async def on_ready(self):
        import datetime
        self.start_time = datetime.datetime.utcnow()

        logger.info("=" * 50)
        logger.info(f"Bot ready: {self.user} ({self.user.id})")
        logger.info(f"Guilds: {len(self.guilds)}")
        logger.info(f"Users: {sum(g.member_count for g in self.guilds):,}")
        logger.info(f"Latency: {round(self.latency * 1000)}ms")
        logger.info("=" * 50)

        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name=f"{len(self.guilds)} # AND ONLY / Built by xrhstaras",
            ),
            status=discord.Status.do_not_disturb,
        )

    async def on_guild_join(self, guild: discord.Guild):
        logger.info(f"Joined guild: {guild.name} ({guild.id}) | Members: {guild.member_count}")
        # Sync commands to new guild
        try:
            await self.tree.sync(guild=guild)
        except Exception as e:
            logger.warning(f"Failed to sync commands in {guild.name}: {e}")

    async def on_guild_remove(self, guild: discord.Guild):
        logger.info(f"Left guild: {guild.name} ({guild.id})")

    async def on_error(self, event_method: str, *args, **kwargs):
        logger.error(f"Unhandled error in {event_method}", exc_info=True)

    async def on_app_command_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
        from utils.helpers import error_embed
        import discord.app_commands as app_commands

        if isinstance(error, app_commands.CommandOnCooldown):
            msg = f"This command is on cooldown. Retry in **{error.retry_after:.1f}s**."
        elif isinstance(error, (app_commands.MissingPermissions, app_commands.CheckFailure)):
            msg = "You don't have permission to use this command."
        elif isinstance(error, app_commands.BotMissingPermissions):
            msg = f"I'm missing permissions: {', '.join(error.missing_permissions)}"
        elif isinstance(error, app_commands.CommandNotFound):
            return
        else:
            logger.error(f"Unhandled command error in /{interaction.command.name if interaction.command else 'unknown'}: {error}", exc_info=True)
            msg = f"An unexpected error occurred: {str(error)[:200]}"

        embed = error_embed("Command Error", msg)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception:
            pass

    async def close(self):
        logger.info("Shutting down bot...")
        await Database.disconnect()
        await super().close()


def validate_startup():
    errors = []
    if not config.TOKEN:
        errors.append("DISCORD_TOKEN is not set in .env")
    if not config.MONGODB_URI:
        errors.append("MONGODB_URI is not set in .env")
    if errors:
        for err in errors:
            logger.critical(f"Startup validation failed: {err}")
        sys.exit(1)
    logger.info("Startup validation passed")


async def main():
    validate_startup()

    os.makedirs("logs", exist_ok=True)

    bot = DiscordBot()
    async with bot:
        await bot.start(config.TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (KeyboardInterrupt)")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
