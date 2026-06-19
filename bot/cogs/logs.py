import discord
from discord import app_commands
from discord.ext import commands
import datetime
import logging
from database import get_guild_config, update_guild_config
from utils import success_embed, error_embed, info_embed, primary_embed, is_admin

logger = logging.getLogger(__name__)

LOG_CHANNELS = [
    "member-logs", "message-logs", "moderation-logs",
    "ticket-logs", "application-logs", "role-logs",
    "channel-logs", "voice-logs", "server-logs",
]


class Logs(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    logs_group = app_commands.Group(name="logs", description="Logging system commands")

    @logs_group.command(name="setup", description="Setup the logging system (creates category and log channels)")
    @app_commands.describe(category_name="Name for the logs category")
    @is_admin()
    async def setup(self, interaction: discord.Interaction, category_name: str = "📋 Server Logs"):
        await interaction.response.defer(ephemeral=True)

        existing_cat_id = (await get_guild_config(interaction.guild_id)).get("log_category_id")
        if existing_cat_id:
            existing = interaction.guild.get_channel(existing_cat_id)
            if existing:
                await interaction.followup.send(
                    embed=error_embed("Already Setup", f"Logs are already configured. Category: {existing.mention}\nUse `/logs reset` to reset."),
                    ephemeral=True,
                )
                return

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        cfg = await get_guild_config(interaction.guild_id)
        for role_id in cfg.get("admin_roles", []) + cfg.get("mod_roles", []):
            role = interaction.guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, read_message_history=True)

        category = await interaction.guild.create_category(category_name, overwrites=overwrites)
        channel_ids = {}
        for ch_name in LOG_CHANNELS:
            channel = await category.create_text_channel(ch_name)
            channel_ids[ch_name.replace("-", "_") + "_id"] = channel.id

        updates = {"log_category_id": category.id, "logs_enabled": True, **{f"log_{k}": v for k, v in channel_ids.items()}}
        await update_guild_config(interaction.guild_id, updates)

        embed = success_embed("Logging System Setup", f"Created category **{category_name}** with {len(LOG_CHANNELS)} log channels.")
        embed.add_field(name="Channels Created", value="\n".join(f"• #{ch}" for ch in LOG_CHANNELS), inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)
        logger.info(f"Log system setup in {interaction.guild.name}")

    @logs_group.command(name="reset", description="Remove all log channels and category")
    @is_admin()
    async def reset(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        category_id = cfg.get("log_category_id")
        if category_id:
            category = interaction.guild.get_channel(category_id)
            if category:
                for ch in category.channels:
                    try:
                        await ch.delete(reason="Log system reset")
                    except discord.HTTPException:
                        pass
                try:
                    await category.delete(reason="Log system reset")
                except discord.HTTPException:
                    pass

        reset_keys = {"log_category_id": None, "logs_enabled": False}
        for ch_name in LOG_CHANNELS:
            reset_keys[f"log_{ch_name.replace('-', '_')}_id"] = None
        await update_guild_config(interaction.guild_id, reset_keys)
        await interaction.followup.send(embed=success_embed("Logs Reset", "Log system has been reset."), ephemeral=True)

    @logs_group.command(name="view", description="View the current log channel configuration")
    @is_admin()
    async def view(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        embed = info_embed("📋 Log Configuration", f"**Status:** {'✅ Enabled' if cfg.get('logs_enabled') else '❌ Disabled'}")
        for ch_name in LOG_CHANNELS:
            key = f"log_{ch_name.replace('-', '_')}_id"
            ch_id = cfg.get(key)
            ch = interaction.guild.get_channel(ch_id) if ch_id else None
            embed.add_field(name=f"#{ch_name}", value=ch.mention if ch else "Not set", inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @logs_group.command(name="test", description="Send a test log message to all log channels")
    @is_admin()
    async def test(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        sent = 0
        for ch_name in LOG_CHANNELS:
            key = f"log_{ch_name.replace('-', '_')}_id"
            ch_id = cfg.get(key)
            ch = interaction.guild.get_channel(ch_id) if ch_id else None
            if ch:
                try:
                    await ch.send(embed=info_embed("Test Log", f"This is a test message for **#{ch_name}**.\nLogging is working correctly! ✅"))
                    sent += 1
                except discord.Forbidden:
                    pass
        await interaction.followup.send(embed=success_embed("Test Sent", f"Sent test messages to **{sent}** log channels."), ephemeral=True)

    async def get_log_channel(self, guild_id: int, log_type: str) -> discord.TextChannel | None:
        cfg = await get_guild_config(guild_id)
        if not cfg.get("logs_enabled"):
            return None
        key = f"log_{log_type}_id"
        ch_id = cfg.get(key)
        if not ch_id:
            return None
        guild = self.bot.get_guild(guild_id)
        return guild.get_channel(ch_id) if guild else None

    # ─── Member Events ───
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        channel = await self.get_log_channel(member.guild.id, "member_logs")
        if not channel:
            return
        embed = discord.Embed(title="👋 Member Joined", color=0x2ECC71, timestamp=datetime.datetime.utcnow())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="User", value=f"{member.mention} ({member.id})", inline=False)
        embed.add_field(name="Account Created", value=discord.utils.format_dt(member.created_at, "R"), inline=True)
        embed.add_field(name="Member Count", value=str(member.guild.member_count), inline=True)
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        channel = await self.get_log_channel(member.guild.id, "member_logs")
        if not channel:
            return
        embed = discord.Embed(title="👋 Member Left", color=0xE74C3C, timestamp=datetime.datetime.utcnow())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="User", value=f"{member.mention} ({member.id})", inline=False)
        roles = [r.mention for r in member.roles if r != member.guild.default_role]
        embed.add_field(name="Roles", value=", ".join(roles) or "None", inline=False)
        await channel.send(embed=embed)

    # ─── Message Events ───
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        channel = await self.get_log_channel(message.guild.id, "message_logs")
        if not channel:
            return
        embed = discord.Embed(title="🗑️ Message Deleted", color=0xE74C3C, timestamp=datetime.datetime.utcnow())
        embed.add_field(name="Author", value=f"{message.author.mention} ({message.author.id})", inline=True)
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        if message.content:
            embed.add_field(name="Content", value=message.content[:1024], inline=False)
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or before.author.bot or before.content == after.content:
            return
        channel = await self.get_log_channel(before.guild.id, "message_logs")
        if not channel:
            return
        embed = discord.Embed(title="✏️ Message Edited", color=0xF39C12, timestamp=datetime.datetime.utcnow())
        embed.add_field(name="Author", value=f"{before.author.mention} ({before.author.id})", inline=True)
        embed.add_field(name="Channel", value=before.channel.mention, inline=True)
        embed.add_field(name="Before", value=before.content[:1024] or "Empty", inline=False)
        embed.add_field(name="After", value=after.content[:1024] or "Empty", inline=False)
        embed.add_field(name="Jump", value=f"[Click here]({after.jump_url})", inline=True)
        await channel.send(embed=embed)

    # ─── Role Events ───
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.roles != after.roles:
            channel = await self.get_log_channel(before.guild.id, "role_logs")
            if channel:
                added = [r for r in after.roles if r not in before.roles]
                removed = [r for r in before.roles if r not in after.roles]
                embed = discord.Embed(title="🎭 Roles Updated", color=0x3498DB, timestamp=datetime.datetime.utcnow())
                embed.add_field(name="Member", value=f"{after.mention} ({after.id})", inline=False)
                if added:
                    embed.add_field(name="Added", value=", ".join(r.mention for r in added), inline=True)
                if removed:
                    embed.add_field(name="Removed", value=", ".join(r.mention for r in removed), inline=True)
                await channel.send(embed=embed)

        if before.nick != after.nick:
            channel = await self.get_log_channel(before.guild.id, "member_logs")
            if channel:
                embed = discord.Embed(title="📝 Nickname Changed", color=0x9B59B6, timestamp=datetime.datetime.utcnow())
                embed.add_field(name="Member", value=f"{after.mention} ({after.id})", inline=False)
                embed.add_field(name="Before", value=before.nick or "None", inline=True)
                embed.add_field(name="After", value=after.nick or "None", inline=True)
                await channel.send(embed=embed)

    # ─── Guild Events ───
    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        log_ch = await self.get_log_channel(channel.guild.id, "channel_logs")
        if not log_ch:
            return
        embed = discord.Embed(title="📢 Channel Created", color=0x2ECC71, timestamp=datetime.datetime.utcnow())
        embed.add_field(name="Name", value=channel.mention, inline=True)
        embed.add_field(name="Type", value=str(channel.type), inline=True)
        await log_ch.send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        log_ch = await self.get_log_channel(channel.guild.id, "channel_logs")
        if not log_ch:
            return
        embed = discord.Embed(title="📢 Channel Deleted", color=0xE74C3C, timestamp=datetime.datetime.utcnow())
        embed.add_field(name="Name", value=f"#{channel.name}", inline=True)
        embed.add_field(name="Type", value=str(channel.type), inline=True)
        try:
            await log_ch.send(embed=embed)
        except discord.NotFound:
            logger.warning(
                "Channel delete log target no longer exists; clearing stale config for guild %s",
                channel.guild.id,
            )
            await update_guild_config(channel.guild.id, {"log_channel_logs_id": None})
        except discord.Forbidden:
            logger.warning(
                "Missing permission to send channel delete log in guild %s",
                channel.guild.id,
            )
        except Exception:
            logger.error("Failed to send channel delete log message", exc_info=True)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        if before.name == after.name:
            return
        log_ch = await self.get_log_channel(before.guild.id, "channel_logs")
        if not log_ch:
            return
        embed = discord.Embed(title="📢 Channel Updated", color=0xF39C12, timestamp=datetime.datetime.utcnow())
        embed.add_field(name="Channel", value=after.mention, inline=False)
        embed.add_field(name="Before", value=f"#{before.name}", inline=True)
        embed.add_field(name="After", value=f"#{after.name}", inline=True)
        await log_ch.send(embed=embed)

    # ─── Voice Events ───
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        channel = await self.get_log_channel(member.guild.id, "voice_logs")
        if not channel:
            return
        if before.channel == after.channel:
            return
        if not before.channel and after.channel:
            embed = discord.Embed(title="🔊 Voice Channel Joined", color=0x2ECC71, timestamp=datetime.datetime.utcnow())
            embed.add_field(name="Member", value=f"{member.mention} ({member.id})", inline=True)
            embed.add_field(name="Channel", value=after.channel.mention, inline=True)
        elif before.channel and not after.channel:
            embed = discord.Embed(title="🔇 Voice Channel Left", color=0xE74C3C, timestamp=datetime.datetime.utcnow())
            embed.add_field(name="Member", value=f"{member.mention} ({member.id})", inline=True)
            embed.add_field(name="Channel", value=before.channel.mention, inline=True)
        else:
            embed = discord.Embed(title="🔀 Voice Channel Moved", color=0xF39C12, timestamp=datetime.datetime.utcnow())
            embed.add_field(name="Member", value=f"{member.mention} ({member.id})", inline=True)
            embed.add_field(name="From", value=before.channel.mention, inline=True)
            embed.add_field(name="To", value=after.channel.mention, inline=True)
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        channel = await self.get_log_channel(guild.id, "moderation_logs")
        if not channel:
            return
        embed = discord.Embed(title="🔨 Member Banned", color=0xE74C3C, timestamp=datetime.datetime.utcnow())
        embed.add_field(name="User", value=f"{user.mention} ({user.id})", inline=False)
        embed.set_thumbnail(url=user.display_avatar.url)
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        channel = await self.get_log_channel(guild.id, "moderation_logs")
        if not channel:
            return
        embed = discord.Embed(title="✅ Member Unbanned", color=0x2ECC71, timestamp=datetime.datetime.utcnow())
        embed.add_field(name="User", value=f"{user.mention} ({user.id})", inline=False)
        await channel.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Logs(bot))
