import discord
from discord import app_commands
from discord.ext import commands
import re
import datetime
import logging
from collections import defaultdict, deque
from database import get_guild_config, update_guild_config
from utils import success_embed, error_embed, info_embed, warning_embed, is_admin
from config import config

logger = logging.getLogger(__name__)

# Invite regex
INVITE_PATTERN = re.compile(r"discord(?:\.gg|app\.com/invite|\.com/invite)/[a-zA-Z0-9\-]+", re.IGNORECASE)
# URL regex
URL_PATTERN = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
# Known scam links
SCAM_KEYWORDS = ["free nitro", "steam gift", "claim your prize", "click here to win", "discordnitro."]


class AutoMod(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # spam tracking: {guild_id: {user_id: deque of timestamps}}
        self._spam_tracker: dict[int, dict[int, deque]] = defaultdict(lambda: defaultdict(deque))

    automod_group = app_commands.Group(name="automod", description="AutoMod configuration commands")

    @automod_group.command(name="setup", description="Configure the automod system")
    @app_commands.describe(
        anti_spam="Enable anti-spam",
        anti_links="Enable anti-links",
        anti_invite="Enable anti-Discord-invite",
        anti_mention_spam="Enable anti-mention-spam",
        anti_caps="Enable anti-caps",
        anti_scam="Enable anti-scam detection",
        log_channel="Channel to send automod logs",
    )
    @is_admin()
    async def setup(
        self,
        interaction: discord.Interaction,
        anti_spam: bool = True,
        anti_links: bool = False,
        anti_invite: bool = True,
        anti_mention_spam: bool = True,
        anti_caps: bool = False,
        anti_scam: bool = True,
        log_channel: discord.TextChannel = None,
    ):
        await interaction.response.defer(ephemeral=True)
        updates = {
            "automod_enabled": True,
            "automod_anti_spam": anti_spam,
            "automod_anti_links": anti_links,
            "automod_anti_invite": anti_invite,
            "automod_anti_mention_spam": anti_mention_spam,
            "automod_anti_caps": anti_caps,
            "automod_anti_scam": anti_scam,
        }
        if log_channel:
            updates["automod_log_channel_id"] = log_channel.id

        await update_guild_config(interaction.guild_id, updates)

        embed = success_embed("AutoMod Configured", "The following rules have been set:")
        embed.add_field(name="Anti-Spam", value="✅" if anti_spam else "❌", inline=True)
        embed.add_field(name="Anti-Links", value="✅" if anti_links else "❌", inline=True)
        embed.add_field(name="Anti-Invite", value="✅" if anti_invite else "❌", inline=True)
        embed.add_field(name="Anti-Mention Spam", value="✅" if anti_mention_spam else "❌", inline=True)
        embed.add_field(name="Anti-Caps", value="✅" if anti_caps else "❌", inline=True)
        embed.add_field(name="Anti-Scam", value="✅" if anti_scam else "❌", inline=True)
        embed.add_field(name="Log Channel", value=log_channel.mention if log_channel else "Not set", inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @automod_group.command(name="reset", description="Disable and reset all automod settings")
    @is_admin()
    async def reset(self, interaction: discord.Interaction):
        await update_guild_config(interaction.guild_id, {
            "automod_enabled": False,
            "automod_anti_spam": False,
            "automod_anti_links": False,
            "automod_anti_invite": False,
            "automod_anti_mention_spam": False,
            "automod_anti_caps": False,
            "automod_anti_scam": False,
            "automod_log_channel_id": None,
            "automod_whitelist_roles": [],
            "automod_whitelist_channels": [],
        })
        await interaction.response.send_message(embed=success_embed("AutoMod Reset", "All automod settings have been reset."), ephemeral=True)

    @automod_group.command(name="view", description="View current automod configuration")
    @is_admin()
    async def view(self, interaction: discord.Interaction):
        cfg = await get_guild_config(interaction.guild_id)
        embed = info_embed("🛡️ AutoMod Configuration", f"**Status:** {'✅ Enabled' if cfg.get('automod_enabled') else '❌ Disabled'}")
        embed.add_field(name="Anti-Spam", value="✅" if cfg.get("automod_anti_spam") else "❌", inline=True)
        embed.add_field(name="Anti-Links", value="✅" if cfg.get("automod_anti_links") else "❌", inline=True)
        embed.add_field(name="Anti-Invite", value="✅" if cfg.get("automod_anti_invite") else "❌", inline=True)
        embed.add_field(name="Anti-Mention Spam", value="✅" if cfg.get("automod_anti_mention_spam") else "❌", inline=True)
        embed.add_field(name="Anti-Caps", value="✅" if cfg.get("automod_anti_caps") else "❌", inline=True)
        embed.add_field(name="Anti-Scam", value="✅" if cfg.get("automod_anti_scam") else "❌", inline=True)
        log_ch = interaction.guild.get_channel(cfg.get("automod_log_channel_id"))
        embed.add_field(name="Log Channel", value=log_ch.mention if log_ch else "Not set", inline=True)
        whitelist_roles = [interaction.guild.get_role(r) for r in cfg.get("automod_whitelist_roles", [])]
        embed.add_field(name="Whitelist Roles", value=", ".join(r.mention for r in whitelist_roles if r) or "None", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _is_whitelisted(self, message: discord.Message, cfg: dict) -> bool:
        whitelist_roles = cfg.get("automod_whitelist_roles", [])
        whitelist_channels = cfg.get("automod_whitelist_channels", [])
        if message.channel.id in whitelist_channels:
            return True
        if message.author.guild_permissions.administrator:
            return True
        if message.author.guild_permissions.manage_messages:
            return True
        return any(r.id in whitelist_roles for r in message.author.roles)

    async def _punish(self, message: discord.Message, reason: str, cfg: dict):
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        try:
            warn_embed = warning_embed("AutoMod", f"Your message was removed.\n**Reason:** {reason}")
            msg = await message.channel.send(content=message.author.mention, embed=warn_embed)
            import asyncio
            await asyncio.sleep(8)
            await msg.delete()
        except discord.HTTPException:
            pass

        log_channel_id = cfg.get("automod_log_channel_id")
        if log_channel_id:
            log_ch = message.guild.get_channel(log_channel_id)
            if log_ch:
                log_embed = discord.Embed(title="🛡️ AutoMod Action", color=0xF39C12, timestamp=datetime.datetime.utcnow())
                log_embed.add_field(name="User", value=f"{message.author.mention} ({message.author.id})", inline=True)
                log_embed.add_field(name="Channel", value=message.channel.mention, inline=True)
                log_embed.add_field(name="Reason", value=reason, inline=False)
                log_embed.add_field(name="Content", value=message.content[:500] or "Empty", inline=False)
                await log_ch.send(embed=log_embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        cfg = await get_guild_config(message.guild.id)
        if not cfg.get("automod_enabled"):
            return
        if await self._is_whitelisted(message, cfg):
            return

        content = message.content

        # Anti-Scam
        if cfg.get("automod_anti_scam"):
            lower = content.lower()
            if any(kw in lower for kw in SCAM_KEYWORDS):
                await self._punish(message, "Potential scam detected", cfg)
                try:
                    await message.author.timeout(
                        discord.utils.utcnow() + datetime.timedelta(minutes=60),
                        reason="AutoMod: Scam message detected",
                    )
                except discord.Forbidden:
                    pass
                return

        # Anti-Invite
        if cfg.get("automod_anti_invite"):
            if INVITE_PATTERN.search(content):
                await self._punish(message, "Discord invite links are not allowed", cfg)
                return

        # Anti-Links
        if cfg.get("automod_anti_links"):
            if URL_PATTERN.search(content):
                await self._punish(message, "Links are not allowed in this server", cfg)
                return

        # Anti-Mention Spam
        if cfg.get("automod_anti_mention_spam"):
            if len(message.mentions) > config.MENTION_LIMIT or len(message.role_mentions) > 3:
                await self._punish(message, f"Mention spam (mentioned {len(message.mentions)} users)", cfg)
                return

        # Anti-Caps
        if cfg.get("automod_anti_caps"):
            if len(content) > 15:
                upper_count = sum(1 for c in content if c.isupper())
                letter_count = sum(1 for c in content if c.isalpha())
                if letter_count > 0 and upper_count / letter_count > config.CAPS_PERCENT:
                    await self._punish(message, "Excessive use of capital letters", cfg)
                    return

        # Anti-Spam
        if cfg.get("automod_anti_spam"):
            now = datetime.datetime.utcnow()
            user_times = self._spam_tracker[message.guild.id][message.author.id]
            user_times.append(now)
            # Remove old entries
            while user_times and (now - user_times[0]).total_seconds() > config.SPAM_INTERVAL:
                user_times.popleft()

            if len(user_times) > config.SPAM_THRESHOLD:
                self._spam_tracker[message.guild.id][message.author.id].clear()
                # Delete recent messages
                try:
                    await message.channel.purge(
                        limit=config.SPAM_THRESHOLD + 1,
                        check=lambda m: m.author == message.author,
                    )
                except discord.Forbidden:
                    pass
                await self._punish(message, f"Spam detected ({len(user_times)} messages in {config.SPAM_INTERVAL}s)", cfg)
                try:
                    await message.author.timeout(
                        discord.utils.utcnow() + datetime.timedelta(minutes=5),
                        reason="AutoMod: Spam",
                    )
                except discord.Forbidden:
                    pass


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
