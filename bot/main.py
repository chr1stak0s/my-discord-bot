"""
Professional Discord Bot — Main Entry Point
"""
import asyncio
import os
import sys
import logging
import discord
from discord import app_commands
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
    "cogs.botperms",
]


class CustomCommandTree(app_commands.CommandTree):
    """
    Global role-permission check.
    Runs before EVERY slash command. If an admin has assigned roles to a
    command via /bot users, only those roles (+ administrators) may use it.
    """
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild_id:
            return True
        # Administrators always bypass
        if interaction.user.guild_permissions.administrator:
            return True
        cmd = interaction.command
        if cmd is None:
            return True
        # Build "group.name" or "_top.name" key
        parent = getattr(cmd, "parent", None)
        if parent and parent.parent is None:
            # subcommand under a group
            key = f"{parent.name}.{cmd.name}"
        elif parent is None:
            # top-level command
            key = f"_top.{cmd.name}"
        else:
            # subcommand under a subgroup — skip custom check
            return True
        from database import get_guild_config
        cfg      = await get_guild_config(interaction.guild_id)
        role_ids = cfg.get("command_roles", {}).get(key)
        if not role_ids:
            return True  # no restriction configured → use command's own check
        user_role_ids = {r.id for r in interaction.user.roles}
        if user_role_ids & set(role_ids):
            return True
        raise discord.app_commands.CheckFailure(
            f"You don't have a required role to use `/{key.replace('_top.', '').replace('.', ' ')}`."
        )


class DiscordBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(
            command_prefix=config.PREFIX,
            intents=intents,
            help_command=None,
            case_insensitive=True,
            tree_cls=CustomCommandTree,
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

              # Also push commands to every guild the bot is already in.
        # Global commands can take up to 1 hour to propagate; guild-level
        # commands appear instantly. This fixes "commands visible but broken"
        # in servers that were joined while the bot was offline.
        for guild in self.guilds:
            try:
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
                logger.info(f"Synced commands to existing guild: {guild.name} ({guild.id})")
            except Exception as e:
                logger.warning(f"Could not sync to guild {guild.name} ({guild.id}): {e}")

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
                 name="Built by xrhstaras",
            ),
            status=discord.Status.do_not_disturb,
        )

    async def on_guild_join(self, guild: discord.Guild):
        logger.info(f"Joined guild: {guild.name} ({guild.id}) | Members: {guild.member_count}")
        # Copy global commands into this guild so they appear instantly
        # without waiting for Discord's global propagation delay (up to 1h)
        try:
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info(f"Synced commands to new guild: {guild.name}")
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
