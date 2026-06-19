import discord
from discord import app_commands
from discord.ext import commands
import datetime
import platform
import logging
from config import config
from utils import primary_embed, info_embed, error_embed

logger = logging.getLogger(__name__)


class Utility(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.start_time = datetime.datetime.utcnow()

    utility_group = app_commands.Group(name="utility", description="Utility commands")

    @utility_group.command(name="avatar", description="Get a user's avatar")
    @app_commands.describe(member="Member to get avatar for")
    async def avatar(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        embed = primary_embed(f"🖼️ {target.display_name}'s Avatar")
        embed.set_image(url=target.display_avatar.with_size(1024).url)
        formats = []
        for fmt in ["png", "jpg", "webp"]:
            url = target.display_avatar.with_format(fmt).url
            formats.append(f"[{fmt.upper()}]({url})")
        if target.display_avatar.is_animated():
            formats.append(f"[GIF]({target.display_avatar.with_format('gif').url})")
        embed.add_field(name="Download", value=" | ".join(formats))
        await interaction.response.send_message(embed=embed)

    @utility_group.command(name="banner", description="Get a user's banner")
    @app_commands.describe(member="Member to get banner for")
    async def banner(self, interaction: discord.Interaction, member: discord.Member = None):
        await interaction.response.defer()
        target = member or interaction.user
        user = await self.bot.fetch_user(target.id)
        if not user.banner:
            await interaction.followup.send(embed=error_embed("No Banner", f"**{target.display_name}** has no banner."))
            return
        embed = primary_embed(f"🖼️ {target.display_name}'s Banner")
        embed.set_image(url=user.banner.with_size(1024).url)
        await interaction.followup.send(embed=embed)

    @utility_group.command(name="userinfo", description="Get information about a user")
    @app_commands.describe(member="Member to get info for")
    async def userinfo(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        embed = primary_embed(f"👤 {target}", "")
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Username", value=str(target), inline=True)
        embed.add_field(name="ID", value=target.id, inline=True)
        embed.add_field(name="Nickname", value=target.nick or "None", inline=True)
        embed.add_field(name="Account Created", value=discord.utils.format_dt(target.created_at, "F"), inline=True)
        embed.add_field(name="Joined Server", value=discord.utils.format_dt(target.joined_at, "F") if target.joined_at else "Unknown", inline=True)
        embed.add_field(name="Bot", value="✅ Yes" if target.bot else "❌ No", inline=True)
        roles = [r.mention for r in reversed(target.roles) if r != target.guild.default_role]
        embed.add_field(name=f"Roles ({len(roles)})", value=", ".join(roles[:15]) or "None", inline=False)
        perms = []
        if target.guild_permissions.administrator:
            perms.append("Administrator")
        elif target.guild_permissions.manage_guild:
            perms.append("Manage Server")
        if target.guild_permissions.manage_messages:
            perms.append("Manage Messages")
        if target.guild_permissions.ban_members:
            perms.append("Ban Members")
        embed.add_field(name="Key Permissions", value=", ".join(perms) or "None", inline=False)
        await interaction.response.send_message(embed=embed)

    @utility_group.command(name="serverinfo", description="Get information about the server")
    async def serverinfo(self, interaction: discord.Interaction):
        guild = interaction.guild
        embed = primary_embed(f"🏠 {guild.name}", guild.description or "")
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        if guild.banner:
            embed.set_image(url=guild.banner.url)
        embed.add_field(name="Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=True)
        embed.add_field(name="ID", value=guild.id, inline=True)
        embed.add_field(name="Created", value=discord.utils.format_dt(guild.created_at, "D"), inline=True)
        embed.add_field(name="Members", value=guild.member_count, inline=True)
        embed.add_field(name="Channels", value=f"💬 {len(guild.text_channels)} | 🔊 {len(guild.voice_channels)} | 📁 {len(guild.categories)}", inline=True)
        embed.add_field(name="Roles", value=len(guild.roles), inline=True)
        embed.add_field(name="Boost Level", value=f"Level {guild.premium_tier} ({guild.premium_subscription_count} boosts)", inline=True)
        embed.add_field(name="Emojis", value=f"{len(guild.emojis)}/{guild.emoji_limit}", inline=True)
        embed.add_field(name="Verification", value=str(guild.verification_level).title(), inline=True)
        await interaction.response.send_message(embed=embed)

    @utility_group.command(name="roleinfo", description="Get information about a role")
    @app_commands.describe(role="Role to get info for")
    async def roleinfo(self, interaction: discord.Interaction, role: discord.Role):
        embed = primary_embed(f"🎭 {role.name}", "")
        embed.color = role.color
        embed.add_field(name="ID", value=role.id, inline=True)
        embed.add_field(name="Color", value=str(role.color), inline=True)
        embed.add_field(name="Members", value=len(role.members), inline=True)
        embed.add_field(name="Mentionable", value="✅" if role.mentionable else "❌", inline=True)
        embed.add_field(name="Hoisted", value="✅" if role.hoist else "❌", inline=True)
        embed.add_field(name="Managed", value="✅" if role.managed else "❌", inline=True)
        embed.add_field(name="Created", value=discord.utils.format_dt(role.created_at, "D"), inline=True)
        embed.add_field(name="Position", value=str(role.position), inline=True)
        key_perms = [p.replace("_", " ").title() for p, v in role.permissions if v and p in (
            "administrator", "manage_guild", "manage_channels", "manage_roles",
            "manage_messages", "ban_members", "kick_members", "moderate_members",
        )]
        embed.add_field(name="Key Permissions", value=", ".join(key_perms) or "None", inline=False)
        await interaction.response.send_message(embed=embed)

    @utility_group.command(name="membercount", description="Get the server's member count")
    async def membercount(self, interaction: discord.Interaction):
        guild = interaction.guild
        bots = sum(1 for m in guild.members if m.bot)
        humans = guild.member_count - bots
        online = sum(1 for m in guild.members if m.status != discord.Status.offline)
        embed = info_embed("👥 Member Count", f"**{guild.name}**")
        embed.add_field(name="Total", value=f"{guild.member_count:,}", inline=True)
        embed.add_field(name="Humans", value=f"{humans:,}", inline=True)
        embed.add_field(name="Bots", value=f"{bots:,}", inline=True)
        embed.add_field(name="Online", value=f"{online:,}", inline=True)
        await interaction.response.send_message(embed=embed)

    @utility_group.command(name="ping", description="Check the bot's latency")
    async def ping(self, interaction: discord.Interaction):
        ws_latency = round(self.bot.latency * 1000)
        start = datetime.datetime.utcnow()
        await interaction.response.defer()
        end = datetime.datetime.utcnow()
        api_latency = round((end - start).total_seconds() * 1000)
        embed = info_embed("🏓 Pong!")
        embed.add_field(name="WebSocket", value=f"`{ws_latency}ms`", inline=True)
        embed.add_field(name="API", value=f"`{api_latency}ms`", inline=True)
        quality = "🟢 Excellent" if ws_latency < 100 else "🟡 Good" if ws_latency < 200 else "🔴 Poor"
        embed.add_field(name="Quality", value=quality, inline=True)
        await interaction.followup.send(embed=embed)

    @utility_group.command(name="uptime", description="Check how long the bot has been online")
    async def uptime(self, interaction: discord.Interaction):
        delta = datetime.datetime.utcnow() - self.start_time
        days, remainder = divmod(int(delta.total_seconds()), 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"
        embed = info_embed("⏱️ Uptime", f"Bot has been online for **{uptime_str}**")
        embed.add_field(name="Started", value=discord.utils.format_dt(self.start_time, "F"), inline=True)
        await interaction.response.send_message(embed=embed)

    @utility_group.command(name="botinfo", description="Get information about the bot")
    async def botinfo(self, interaction: discord.Interaction):
        embed = primary_embed(f"🤖 {self.bot.user.name}", f"A professional Discord bot built with discord.py 2.x")
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.add_field(name="Version", value="1.0.0", inline=True)
        embed.add_field(name="discord.py", value=discord.__version__, inline=True)
        embed.add_field(name="Python", value=platform.python_version(), inline=True)
        embed.add_field(name="Servers", value=f"{len(self.bot.guilds):,}", inline=True)
        embed.add_field(name="Users", value=f"{sum(g.member_count for g in self.bot.guilds):,}", inline=True)
        delta = datetime.datetime.utcnow() - self.start_time
        days, rem = divmod(int(delta.total_seconds()), 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)
        embed.add_field(name="Uptime", value=f"{days}d {hours}h {minutes}m {seconds}s", inline=True)
        embed.add_field(name="Commands", value=str(len(self.bot.tree.get_commands())), inline=True)
        if config.SUPPORT_SERVER:
            embed.add_field(name="Support Server", value=f"[Click Here]({config.SUPPORT_SERVER})", inline=True)
        if config.BOT_INVITE:
            embed.add_field(name="Invite", value=f"[Click Here]({config.BOT_INVITE})", inline=True)
        await interaction.response.send_message(embed=embed)

    @utility_group.command(name="invite", description="Get the bot's invite link")
    async def invite(self, interaction: discord.Interaction):
        embed = primary_embed("🔗 Invite Links")
        if config.BOT_INVITE:
            embed.add_field(name="Bot Invite", value=f"[Click Here]({config.BOT_INVITE})", inline=True)
        if config.SUPPORT_SERVER:
            embed.add_field(name="Support Server", value=f"[Click Here]({config.SUPPORT_SERVER})", inline=True)
        if not config.BOT_INVITE and not config.SUPPORT_SERVER:
            embed.description = "No invite links configured. Set `BOT_INVITE` and `SUPPORT_SERVER` in your `.env` file."
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Utility(bot))
