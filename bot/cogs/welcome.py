import discord
from discord import app_commands
from discord.ext import commands
import logging
from database import get_guild_config, update_guild_config
from utils import success_embed, error_embed, info_embed, primary_embed, is_admin
from views.embeds_builder import build_embed_from_data
from views.panel_customizer import WelcomeCustomizerView, build_panel_embed

logger = logging.getLogger(__name__)


class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    welcome_group = app_commands.Group(name="welcome", description="Welcome and leave system commands")

    @welcome_group.command(name="setup", description="Configure the welcome and leave system")
    @app_commands.describe(
        welcome_channel="Channel for welcome messages",
        leave_channel="Channel for leave messages (defaults to welcome channel)",
        welcome_message="Custom welcome message (use {user}, {server}, {count})",
        leave_message="Custom leave message",
        auto_role="Role to assign to new members",
        dm_welcome="Send a DM to new members",
    )
    @is_admin()
    async def setup(
        self,
        interaction: discord.Interaction,
        welcome_channel: discord.TextChannel = None,
        leave_channel: discord.TextChannel = None,
        welcome_message: str = None,
        leave_message: str = None,
        auto_role: discord.Role = None,
        dm_welcome: bool = False,
    ):
        await interaction.response.defer(ephemeral=True)
        updates = {}
        if welcome_channel:
            updates["welcome_channel_id"] = welcome_channel.id
        if leave_channel:
            updates["leave_channel_id"] = leave_channel.id
        if welcome_message:
            updates["welcome_message"] = welcome_message
        if leave_message:
            updates["leave_message"] = leave_message
        if auto_role:
            cfg = await get_guild_config(interaction.guild_id)
            auto_roles = cfg.get("auto_roles", [])
            if auto_role.id not in auto_roles:
                auto_roles.append(auto_role.id)
            updates["auto_roles"] = auto_roles
        updates["dm_welcome"] = dm_welcome

        await update_guild_config(interaction.guild_id, updates)

        embed = success_embed("Welcome System Configured", "Settings saved.")
        if welcome_channel:
            embed.add_field(name="Welcome Channel", value=welcome_channel.mention, inline=True)
        if leave_channel:
            embed.add_field(name="Leave Channel", value=leave_channel.mention, inline=True)
        if auto_role:
            embed.add_field(name="Auto Role", value=auto_role.mention, inline=True)
        embed.add_field(name="DM Welcome", value="✅" if dm_welcome else "❌", inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @welcome_group.command(name="preview", description="Preview the welcome/leave message")
    @app_commands.describe(type="Type of message to preview")
    @app_commands.choices(type=[
        app_commands.Choice(name="Welcome", value="welcome"),
        app_commands.Choice(name="Leave", value="leave"),
    ])
    @is_admin()
    async def preview(self, interaction: discord.Interaction, type: str = "welcome"):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        member = interaction.user

        if type == "welcome":
            embed = self._build_welcome_embed(member, cfg)
        else:
            embed = self._build_leave_embed(member, cfg)

        await interaction.followup.send(content="**Preview:**", embed=embed, ephemeral=True)

    @welcome_group.command(name="view", description="View current welcome system configuration")
    @is_admin()
    async def view(self, interaction: discord.Interaction):
        cfg = await get_guild_config(interaction.guild_id)
        embed = info_embed("👋 Welcome System Configuration")

        def get_channel(cid):
            if not cid:
                return "Not set"
            ch = interaction.guild.get_channel(cid)
            return ch.mention if ch else "Deleted"

        embed.add_field(name="Welcome Channel", value=get_channel(cfg.get("welcome_channel_id")), inline=True)
        embed.add_field(name="Leave Channel", value=get_channel(cfg.get("leave_channel_id")), inline=True)
        embed.add_field(name="DM Welcome", value="✅" if cfg.get("dm_welcome") else "❌", inline=True)

        auto_roles = [interaction.guild.get_role(r) for r in cfg.get("auto_roles", [])]
        embed.add_field(name="Auto Roles", value=", ".join(r.mention for r in auto_roles if r) or "None", inline=False)
        embed.add_field(name="Welcome Message", value=cfg.get("welcome_message") or "Default", inline=False)
        embed.add_field(name="Leave Message", value=cfg.get("leave_message") or "Default", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @welcome_group.command(name="customize", description="Open the interactive join or leave embed customizer")
    @app_commands.describe(type="Which embed to customize")
    @app_commands.choices(type=[
        app_commands.Choice(name="Join Message", value="welcome"),
        app_commands.Choice(name="Leave Message", value="leave"),
    ])
    @is_admin()
    async def customize(self, interaction: discord.Interaction, type: str = "welcome"):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        key = f"{type}_embed"
        data = cfg.get(key, {})
        view = WelcomeCustomizerView(interaction.user.id, type, data)
        embed = primary_embed(view._label() + " Customizer", view._summary())
        embed.set_footer(text="Variables: {user} {server} {count} • Use Preview to test")
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @welcome_group.command(name="reset", description="Reset the welcome system configuration")
    @is_admin()
    async def reset(self, interaction: discord.Interaction):
        await update_guild_config(interaction.guild_id, {
            "welcome_channel_id": None,
            "leave_channel_id": None,
            "welcome_message": None,
            "leave_message": None,
            "auto_roles": [],
            "dm_welcome": False,
        })
        await interaction.response.send_message(embed=success_embed("Reset", "Welcome system reset."), ephemeral=True)

    def _build_welcome_embed(self, member: discord.Member, cfg: dict) -> discord.Embed:
        data = cfg.get("welcome_embed", {})

        def replace_vars(s):
            return (s or "").replace("{user}", member.mention).replace("{server}", member.guild.name).replace("{count}", str(member.guild.member_count))

        if data:
            embed = build_panel_embed(data)
            embed.title = replace_vars(embed.title or f"👋 Welcome, {member.display_name}!")
            embed.description = replace_vars(embed.description)
            if not data.get("thumbnail"):
                embed.set_thumbnail(url=member.display_avatar.url)
        else:
            custom_msg = cfg.get("welcome_message")
            description = replace_vars(custom_msg) if custom_msg else f"Welcome to **{member.guild.name}**, {member.mention}! 🎉\nYou are our **{member.guild.member_count}th** member!"
            embed = discord.Embed(title=f"👋 Welcome, {member.display_name}!", description=description, color=0x5865F2)
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"Account created: {member.created_at.strftime('%B %d, %Y')}")
        return embed

    def _build_leave_embed(self, member: discord.Member, cfg: dict) -> discord.Embed:
        data = cfg.get("leave_embed", {})

        def replace_vars(s):
            return (s or "").replace("{user}", str(member)).replace("{server}", member.guild.name).replace("{count}", str(member.guild.member_count))

        if data:
            embed = build_panel_embed(data)
            embed.title = replace_vars(embed.title or "👋 Member Left")
            embed.description = replace_vars(embed.description)
            if not data.get("thumbnail"):
                embed.set_thumbnail(url=member.display_avatar.url)
        else:
            custom_msg = cfg.get("leave_message")
            description = replace_vars(custom_msg) if custom_msg else f"**{member}** has left the server.\nWe now have **{member.guild.member_count}** members."
            embed = discord.Embed(title="👋 Member Left", description=description, color=0xE74C3C)
            embed.set_thumbnail(url=member.display_avatar.url)
        return embed

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        cfg = await get_guild_config(member.guild.id)

        # Auto-roles
        for role_id in cfg.get("auto_roles", []):
            role = member.guild.get_role(role_id)
            if role:
                try:
                    await member.add_roles(role, reason="Auto-role on join")
                except discord.Forbidden:
                    logger.warning(f"Cannot assign auto-role {role.name} in {member.guild.name}")

        # Welcome message
        channel_id = cfg.get("welcome_channel_id")
        if channel_id:
            channel = member.guild.get_channel(channel_id)
            if channel:
                embed = self._build_welcome_embed(member, cfg)
                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    pass

        # DM welcome
        if cfg.get("dm_welcome"):
            try:
                dm_embed = discord.Embed(
                    title=f"Welcome to {member.guild.name}! 🎉",
                    description=f"Hello {member.display_name}! Thanks for joining **{member.guild.name}**.\nMake sure to read the rules and enjoy your stay!",
                    color=0x5865F2,
                )
                if member.guild.icon:
                    dm_embed.set_thumbnail(url=member.guild.icon.url)
                await member.send(embed=dm_embed)
            except discord.Forbidden:
                pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        cfg = await get_guild_config(member.guild.id)
        channel_id = cfg.get("leave_channel_id") or cfg.get("welcome_channel_id")
        if not channel_id:
            return
        channel = member.guild.get_channel(channel_id)
        if not channel:
            return
        embed = self._build_leave_embed(member, cfg)
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
