import discord
from discord import app_commands
from discord.ext import commands
import datetime
from database import Database, get_guild_config, update_guild_config
from utils import success_embed, error_embed, info_embed, primary_embed, is_admin, is_bot_owner
import logging

logger = logging.getLogger(__name__)


class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    admin_group = app_commands.Group(name="admin", description="Admin configuration commands")

    @admin_group.command(name="setup", description="Run the initial bot setup wizard for this server")
    @is_admin()
    async def setup(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)

        embed = primary_embed(
            "⚙️ Bot Setup",
            "Setting up the bot for your server...",
        )
        embed.add_field(name="Server", value=interaction.guild.name, inline=True)
        embed.add_field(name="Members", value=interaction.guild.member_count, inline=True)
        embed.add_field(
            name="Status",
            value="✅ Database connected\n✅ Guild configuration initialized\n✅ Ready to configure modules",
            inline=False,
        )
        embed.add_field(
            name="Next Steps",
            value=(
                "`/tickets setup` — Configure ticket system\n"
                "`/logs setup` — Configure logging system\n"
                "`/welcome setup` — Configure welcome messages\n"
                "`/automod setup` — Configure auto-moderation\n"
                "`/applications setup` — Configure application forms"
            ),
            inline=False,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        logger.info(f"Setup run in guild {interaction.guild.name} ({interaction.guild_id})")

    @admin_group.command(name="config", description="View or update bot configuration")
    @app_commands.describe(
        mod_role="Role to use as moderator role",
        admin_role="Role to use as admin role",
    )
    @is_admin()
    async def config(
        self,
        interaction: discord.Interaction,
        mod_role: discord.Role = None,
        admin_role: discord.Role = None,
    ):
        await interaction.response.defer(ephemeral=True)
        updates = {}
        if mod_role:
            cfg = await get_guild_config(interaction.guild_id)
            mod_roles = cfg.get("mod_roles", [])
            if mod_role.id not in mod_roles:
                mod_roles.append(mod_role.id)
            updates["mod_roles"] = mod_roles

        if admin_role:
            cfg = await get_guild_config(interaction.guild_id)
            admin_roles = cfg.get("admin_roles", [])
            if admin_role.id not in admin_roles:
                admin_roles.append(admin_role.id)
            updates["admin_roles"] = admin_roles

        if updates:
            await update_guild_config(interaction.guild_id, updates)
            await interaction.followup.send(embed=success_embed("Config Updated", "Configuration has been updated."), ephemeral=True)
        else:
            cfg = await get_guild_config(interaction.guild_id)
            embed = info_embed("Bot Configuration", f"Server: **{interaction.guild.name}**")
            mod_roles = [interaction.guild.get_role(r) for r in cfg.get("mod_roles", []) if interaction.guild.get_role(r)]
            admin_roles = [interaction.guild.get_role(r) for r in cfg.get("admin_roles", []) if interaction.guild.get_role(r)]
            embed.add_field(name="Mod Roles", value=", ".join(r.mention for r in mod_roles) or "None", inline=False)
            embed.add_field(name="Admin Roles", value=", ".join(r.mention for r in admin_roles) or "None", inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @admin_group.command(name="view", description="View all bot settings for this server")
    @is_admin()
    async def view(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)

        embed = info_embed("📋 Server Configuration", f"**{interaction.guild.name}**")

        def get_channel(cid):
            if not cid:
                return "Not set"
            ch = interaction.guild.get_channel(cid)
            return ch.mention if ch else f"Deleted ({cid})"

        def get_roles(ids):
            if not ids:
                return "None"
            roles = [interaction.guild.get_role(r) for r in ids]
            return ", ".join(r.mention for r in roles if r) or "None"

        embed.add_field(name="Ticket Category", value=get_channel(cfg.get("ticket_category_id")), inline=True)
        embed.add_field(name="Ticket Log", value=get_channel(cfg.get("ticket_log_channel_id")), inline=True)
        embed.add_field(name="Log Category", value=get_channel(cfg.get("log_category_id")), inline=True)
        embed.add_field(name="Welcome Channel", value=get_channel(cfg.get("welcome_channel_id")), inline=True)
        embed.add_field(name="Mod Roles", value=get_roles(cfg.get("mod_roles", [])), inline=True)
        embed.add_field(name="Admin Roles", value=get_roles(cfg.get("admin_roles", [])), inline=True)
        embed.add_field(name="Auto-roles", value=get_roles(cfg.get("auto_roles", [])), inline=True)
        embed.add_field(name="AutoMod", value="✅ Enabled" if cfg.get("automod_enabled") else "❌ Disabled", inline=True)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @admin_group.command(name="reset", description="Reset all bot data for this server")
    @is_admin()
    async def reset(self, interaction: discord.Interaction):
        from views.confirm import ConfirmView
        view = ConfirmView(interaction.user.id)
        await interaction.response.send_message(
            embed=discord.Embed(
                title="⚠️ Reset Server Data",
                description="This will **permanently delete** all bot data for this server including tickets, applications, warnings, and settings.\n\nThis action **cannot be undone**.",
                color=0xE74C3C,
            ),
            view=view,
            ephemeral=True,
        )
        await view.wait()
        if view.value:
            guild_id = interaction.guild_id
            await Database.db.guilds.delete_one({"guild_id": guild_id})
            await Database.db.tickets.delete_many({"guild_id": guild_id})
            await Database.db.applications.delete_many({"guild_id": guild_id})
            await Database.db.moderation.delete_many({"guild_id": guild_id})
            await Database.db.warnings.delete_many({"guild_id": guild_id})
            await Database.db.economy.delete_many({"guild_id": guild_id})
            await Database.db.levels.delete_many({"guild_id": guild_id})
            await Database.db.embeds.delete_many({"guild_id": guild_id})
            await Database.db.reaction_roles.delete_many({"guild_id": guild_id})
            await Database.db.custom_commands.delete_many({"guild_id": guild_id})
            await interaction.edit_original_response(
                embed=success_embed("Reset Complete", "All server data has been deleted."), view=None
            )
            logger.warning(f"Data reset in guild {interaction.guild.name} by {interaction.user}")

    @admin_group.command(name="reload", description="Reload a bot extension (owner only)")
    @app_commands.describe(extension="Extension name to reload (e.g. cogs.moderation)")
    @is_bot_owner()
    async def reload(self, interaction: discord.Interaction, extension: str):
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.reload_extension(extension)
            await interaction.followup.send(embed=success_embed("Reloaded", f"Extension `{extension}` reloaded."), ephemeral=True)
            logger.info(f"Reloaded extension: {extension}")
        except commands.ExtensionError as e:
            await interaction.followup.send(embed=error_embed("Reload Failed", str(e)), ephemeral=True)
            logger.error(f"Failed to reload {extension}: {e}")

    @staticmethod
    @admin_group.error
    async def admin_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, (app_commands.MissingPermissions, app_commands.CheckFailure)):
            await interaction.response.send_message(
                embed=error_embed("No Permission", "You don't have permission to use admin commands."),
                ephemeral=True,
            )
        else:
            logger.error(f"Admin command error: {error}", exc_info=True)
            await interaction.response.send_message(embed=error_embed("Error", str(error)), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
