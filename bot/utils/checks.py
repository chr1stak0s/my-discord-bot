import discord
from discord import app_commands
from database import get_guild_config


def is_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        cfg = await get_guild_config(interaction.guild_id)
        admin_roles = cfg.get("admin_roles", [])
        user_role_ids = [r.id for r in interaction.user.roles]
        if any(r in user_role_ids for r in admin_roles):
            return True
        raise app_commands.MissingPermissions(["administrator"])
    return app_commands.check(predicate)


def is_moderator():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        if interaction.user.guild_permissions.moderate_members:
            return True
        cfg = await get_guild_config(interaction.guild_id)
        mod_roles = cfg.get("mod_roles", [])
        user_role_ids = [r.id for r in interaction.user.roles]
        if any(r in user_role_ids for r in mod_roles):
            return True
        raise app_commands.MissingPermissions(["moderate_members"])
    return app_commands.check(predicate)


def is_ticket_staff():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        cfg = await get_guild_config(interaction.guild_id)
        staff_roles = cfg.get("ticket_staff_roles", [])
        user_role_ids = [r.id for r in interaction.user.roles]
        if any(r in user_role_ids for r in staff_roles):
            return True
        raise app_commands.CheckFailure("You don't have permission to manage tickets.")
    return app_commands.check(predicate)


def is_application_reviewer():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        cfg = await get_guild_config(interaction.guild_id)
        reviewer_roles = cfg.get("application_reviewer_roles", [])
        user_role_ids = [r.id for r in interaction.user.roles]
        if any(r in user_role_ids for r in reviewer_roles):
            return True
        raise app_commands.CheckFailure("You don't have permission to review applications.")
    return app_commands.check(predicate)


def is_bot_owner():
    async def predicate(interaction: discord.Interaction) -> bool:
        from config import config
        if interaction.user.id in config.OWNER_IDS:
            return True
        raise app_commands.CheckFailure("This command is restricted to the bot owner.")
    return app_commands.check(predicate)
