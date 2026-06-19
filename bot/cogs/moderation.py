import discord
from discord import app_commands
from discord.ext import commands
import datetime
import logging
from database import Database, get_guild_config
from utils import success_embed, error_embed, warning_embed, primary_embed, is_moderator, send_dm

logger = logging.getLogger(__name__)


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    mod_group = app_commands.Group(name="moderation", description="Moderation commands")

    async def _log_action(self, guild: discord.Guild, action: str, moderator: discord.Member, target: discord.Member | discord.User, reason: str, extra: str = ""):
        cfg = await get_guild_config(guild.id)
        log_channel_id = cfg.get("moderation_log_channel_id")
        if not log_channel_id:
            return
        channel = guild.get_channel(log_channel_id)
        if not channel:
            return
        embed = primary_embed(f"🔨 {action}", f"**Target:** {target.mention} ({target.id})\n**Moderator:** {moderator.mention}\n**Reason:** {reason or 'No reason'}{extra}")
        embed.set_thumbnail(url=target.display_avatar.url)
        await channel.send(embed=embed)

    @mod_group.command(name="ban", description="Ban a member from the server")
    @app_commands.describe(member="Member to ban", reason="Reason for ban", delete_days="Days of messages to delete (0-7)")
    @is_moderator()
    @app_commands.default_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided", delete_days: int = 0):
        await interaction.response.defer()
        if member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.followup.send(embed=error_embed("Hierarchy Error", "You cannot ban someone with an equal or higher role."), ephemeral=True)
            return
        if member.id == interaction.guild.owner_id:
            await interaction.followup.send(embed=error_embed("Cannot Ban", "You cannot ban the server owner."), ephemeral=True)
            return
        dm_embed = error_embed("You have been banned", f"**Server:** {interaction.guild.name}\n**Reason:** {reason}\n**Moderator:** {interaction.user}")
        await send_dm(member, dm_embed)
        await member.ban(reason=f"{reason} | Moderator: {interaction.user}", delete_message_days=min(delete_days, 7))
        await Database.db.moderation.insert_one({"guild_id": interaction.guild_id, "user_id": member.id, "action": "ban", "reason": reason, "moderator_id": interaction.user.id, "timestamp": datetime.datetime.utcnow()})
        await interaction.followup.send(embed=success_embed("Member Banned", f"**{member}** has been banned.\n**Reason:** {reason}"))
        await self._log_action(interaction.guild, "Member Banned", interaction.user, member, reason)

    @mod_group.command(name="unban", description="Unban a user from the server")
    @app_commands.describe(user_id="User ID to unban", reason="Reason for unban")
    @is_moderator()
    @app_commands.default_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: str = "No reason provided"):
        await interaction.response.defer()
        try:
            user = await self.bot.fetch_user(int(user_id))
        except (ValueError, discord.NotFound):
            await interaction.followup.send(embed=error_embed("Not Found", "User not found."), ephemeral=True)
            return
        try:
            await interaction.guild.unban(user, reason=f"{reason} | Moderator: {interaction.user}")
        except discord.NotFound:
            await interaction.followup.send(embed=error_embed("Not Banned", f"{user} is not banned."), ephemeral=True)
            return
        await interaction.followup.send(embed=success_embed("Member Unbanned", f"**{user}** has been unbanned.\n**Reason:** {reason}"))
        await self._log_action(interaction.guild, "Member Unbanned", interaction.user, user, reason)

    @mod_group.command(name="kick", description="Kick a member from the server")
    @app_commands.describe(member="Member to kick", reason="Reason for kick")
    @is_moderator()
    @app_commands.default_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        await interaction.response.defer()
        if member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.followup.send(embed=error_embed("Hierarchy Error", "You cannot kick someone with an equal or higher role."), ephemeral=True)
            return
        dm_embed = warning_embed("You have been kicked", f"**Server:** {interaction.guild.name}\n**Reason:** {reason}\n**Moderator:** {interaction.user}")
        await send_dm(member, dm_embed)
        await member.kick(reason=f"{reason} | Moderator: {interaction.user}")
        await Database.db.moderation.insert_one({"guild_id": interaction.guild_id, "user_id": member.id, "action": "kick", "reason": reason, "moderator_id": interaction.user.id, "timestamp": datetime.datetime.utcnow()})
        await interaction.followup.send(embed=success_embed("Member Kicked", f"**{member}** has been kicked.\n**Reason:** {reason}"))
        await self._log_action(interaction.guild, "Member Kicked", interaction.user, member, reason)

    @mod_group.command(name="timeout", description="Timeout (mute) a member")
    @app_commands.describe(member="Member to timeout", duration="Duration in minutes", reason="Reason")
    @is_moderator()
    @app_commands.default_permissions(moderate_members=True)
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, duration: int, reason: str = "No reason provided"):
        await interaction.response.defer()
        if duration < 1 or duration > 40320:
            await interaction.followup.send(embed=error_embed("Invalid Duration", "Duration must be between 1 and 40320 minutes (28 days)."), ephemeral=True)
            return
        until = discord.utils.utcnow() + datetime.timedelta(minutes=duration)
        await member.timeout(until, reason=f"{reason} | Moderator: {interaction.user}")
        await Database.db.moderation.insert_one({"guild_id": interaction.guild_id, "user_id": member.id, "action": "timeout", "reason": reason, "duration": duration, "moderator_id": interaction.user.id, "timestamp": datetime.datetime.utcnow()})
        await interaction.followup.send(embed=success_embed("Member Timed Out", f"**{member}** has been timed out for **{duration} minutes**.\n**Reason:** {reason}"))
        await self._log_action(interaction.guild, "Member Timed Out", interaction.user, member, reason, f"\n**Duration:** {duration} minutes")

    @mod_group.command(name="mute", description="Mute a member (requires muted role)")
    @app_commands.describe(member="Member to mute", reason="Reason")
    @is_moderator()
    async def mute(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        await interaction.response.defer()
        cfg = await get_guild_config(interaction.guild_id)
        muted_role_id = cfg.get("muted_role_id")
        if not muted_role_id:
            muted_role = discord.utils.get(interaction.guild.roles, name="Muted")
            if not muted_role:
                muted_role = await interaction.guild.create_role(name="Muted", color=discord.Color.dark_gray())
                for channel in interaction.guild.channels:
                    try:
                        await channel.set_permissions(muted_role, send_messages=False, speak=False, add_reactions=False)
                    except discord.Forbidden:
                        pass
            muted_role_id = muted_role.id
            from database import update_guild_config
            await update_guild_config(interaction.guild_id, {"muted_role_id": muted_role_id})
        else:
            muted_role = interaction.guild.get_role(muted_role_id)
        if muted_role in member.roles:
            await interaction.followup.send(embed=warning_embed("Already Muted", f"{member.mention} is already muted."), ephemeral=True)
            return
        await member.add_roles(muted_role, reason=f"{reason} | Moderator: {interaction.user}")
        await Database.db.moderation.insert_one({"guild_id": interaction.guild_id, "user_id": member.id, "action": "mute", "reason": reason, "moderator_id": interaction.user.id, "timestamp": datetime.datetime.utcnow()})
        await interaction.followup.send(embed=success_embed("Member Muted", f"**{member}** has been muted.\n**Reason:** {reason}"))
        await self._log_action(interaction.guild, "Member Muted", interaction.user, member, reason)

    @mod_group.command(name="unmute", description="Unmute a member")
    @app_commands.describe(member="Member to unmute", reason="Reason")
    @is_moderator()
    async def unmute(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        await interaction.response.defer()
        cfg = await get_guild_config(interaction.guild_id)
        muted_role_id = cfg.get("muted_role_id")
        if not muted_role_id:
            await interaction.followup.send(embed=error_embed("Not Configured", "No muted role configured."), ephemeral=True)
            return
        muted_role = interaction.guild.get_role(muted_role_id)
        if not muted_role or muted_role not in member.roles:
            await interaction.followup.send(embed=warning_embed("Not Muted", f"{member.mention} is not muted."), ephemeral=True)
            return
        await member.remove_roles(muted_role, reason=f"{reason} | Moderator: {interaction.user}")
        await interaction.followup.send(embed=success_embed("Member Unmuted", f"**{member}** has been unmuted."))
        await self._log_action(interaction.guild, "Member Unmuted", interaction.user, member, reason)

    @mod_group.command(name="warn", description="Warn a member")
    @app_commands.describe(member="Member to warn", reason="Reason for warning")
    @is_moderator()
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        await interaction.response.defer()
        doc = {"guild_id": interaction.guild_id, "user_id": member.id, "reason": reason, "moderator_id": interaction.user.id, "timestamp": datetime.datetime.utcnow()}
        await Database.db.warnings.insert_one(doc)
        count = await Database.db.warnings.count_documents({"guild_id": interaction.guild_id, "user_id": member.id})
        dm_embed = warning_embed("You have received a warning", f"**Server:** {interaction.guild.name}\n**Reason:** {reason}\n**Warning #{count}**")
        await send_dm(member, dm_embed)
        await interaction.followup.send(embed=success_embed("Member Warned", f"**{member}** has been warned. (Warning #{count})\n**Reason:** {reason}"))
        await self._log_action(interaction.guild, f"Member Warned (#{count})", interaction.user, member, reason)

    @mod_group.command(name="warnings", description="View warnings for a member")
    @app_commands.describe(member="Member to check warnings for")
    @is_moderator()
    async def warnings(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        warns = await Database.db.warnings.find({"guild_id": interaction.guild_id, "user_id": member.id}).sort("timestamp", -1).to_list(25)
        embed = primary_embed(f"⚠️ Warnings — {member}", f"Total warnings: **{len(warns)}**")
        embed.set_thumbnail(url=member.display_avatar.url)
        for i, w in enumerate(warns, 1):
            mod = interaction.guild.get_member(w.get("moderator_id")) or w.get("moderator_id", "Unknown")
            ts = discord.utils.format_dt(w["timestamp"], "R") if w.get("timestamp") else "Unknown"
            embed.add_field(name=f"Warning #{i}", value=f"**Reason:** {w['reason']}\n**Moderator:** {mod}\n**When:** {ts}", inline=False)
        if not warns:
            embed.description = f"**{member}** has no warnings."
        await interaction.followup.send(embed=embed, ephemeral=True)

    @mod_group.command(name="clear", description="Clear messages in the current channel")
    @app_commands.describe(amount="Number of messages to delete (1-100)", member="Only delete messages from this member")
    @is_moderator()
    @app_commands.default_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, amount: int, member: discord.Member = None):
        await interaction.response.defer(ephemeral=True)
        if not 1 <= amount <= 100:
            await interaction.followup.send(embed=error_embed("Invalid Amount", "Amount must be between 1 and 100."), ephemeral=True)
            return
        def check(m):
            return member is None or m.author == member
        deleted = await interaction.channel.purge(limit=amount, check=check)
        await interaction.followup.send(embed=success_embed("Messages Cleared", f"Deleted **{len(deleted)}** messages{f' from {member.mention}' if member else ''}."), ephemeral=True)

    @mod_group.command(name="slowmode", description="Set slowmode for a channel")
    @app_commands.describe(seconds="Slowmode delay in seconds (0 to disable)", channel="Channel to set slowmode in")
    @is_moderator()
    @app_commands.default_permissions(manage_channels=True)
    async def slowmode(self, interaction: discord.Interaction, seconds: int, channel: discord.TextChannel = None):
        target = channel or interaction.channel
        if not 0 <= seconds <= 21600:
            await interaction.response.send_message(embed=error_embed("Invalid", "Slowmode must be 0-21600 seconds."), ephemeral=True)
            return
        await target.edit(slowmode_delay=seconds)
        if seconds == 0:
            await interaction.response.send_message(embed=success_embed("Slowmode Disabled", f"Slowmode disabled in {target.mention}."))
        else:
            await interaction.response.send_message(embed=success_embed("Slowmode Set", f"Slowmode set to **{seconds}s** in {target.mention}."))

    @mod_group.command(name="lock", description="Lock a channel")
    @app_commands.describe(channel="Channel to lock", reason="Reason")
    @is_moderator()
    @app_commands.default_permissions(manage_channels=True)
    async def lock(self, interaction: discord.Interaction, channel: discord.TextChannel = None, reason: str = "No reason"):
        target = channel or interaction.channel
        await target.set_permissions(interaction.guild.default_role, send_messages=False, reason=f"{reason} | {interaction.user}")
        await interaction.response.send_message(embed=success_embed("Channel Locked", f"{target.mention} has been locked.\n**Reason:** {reason}"))

    @mod_group.command(name="unlock", description="Unlock a channel")
    @app_commands.describe(channel="Channel to unlock", reason="Reason")
    @is_moderator()
    @app_commands.default_permissions(manage_channels=True)
    async def unlock(self, interaction: discord.Interaction, channel: discord.TextChannel = None, reason: str = "No reason"):
        target = channel or interaction.channel
        await target.set_permissions(interaction.guild.default_role, send_messages=None, reason=f"{reason} | {interaction.user}")
        await interaction.response.send_message(embed=success_embed("Channel Unlocked", f"{target.mention} has been unlocked.\n**Reason:** {reason}"))

    @mod_group.command(name="nickname", description="Change a member's nickname")
    @app_commands.describe(member="Member", nickname="New nickname (leave blank to reset)")
    @is_moderator()
    @app_commands.default_permissions(manage_nicknames=True)
    async def nickname(self, interaction: discord.Interaction, member: discord.Member, nickname: str = None):
        await interaction.response.defer()
        old_nick = member.display_name
        try:
            await member.edit(nick=nickname, reason=f"Nickname changed by {interaction.user}")
        except discord.Forbidden:
            await interaction.followup.send(embed=error_embed("No Permission", "Cannot change this member's nickname."), ephemeral=True)
            return
        if nickname:
            await interaction.followup.send(embed=success_embed("Nickname Changed", f"Changed **{member.name}**'s nickname from `{old_nick}` to `{nickname}`."))
        else:
            await interaction.followup.send(embed=success_embed("Nickname Reset", f"Reset **{member.name}**'s nickname."))

    @staticmethod
    @mod_group.error
    async def mod_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, (app_commands.MissingPermissions, app_commands.CheckFailure)):
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=error_embed("No Permission", "You don't have permission to use this command."), ephemeral=True)
        else:
            logger.error(f"Moderation error: {error}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=error_embed("Error", str(error)), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
