"""
Extra features: Reaction Roles, Verification, Giveaways, Polls, Suggestions,
Starboard, AFK System, Custom Commands, Leveling System.
"""
import discord
from discord import app_commands
from discord.ext import commands
import datetime
import random
import asyncio
import io
import logging
from database import Database, get_guild_config, update_guild_config
from utils import success_embed, error_embed, info_embed, primary_embed, warning_embed, xp_progress, xp_for_level
from config import config
from views.giveaway import GiveawayView
from views.polls import PollView
from views.panel_customizer import build_panel_embed, VerifyPanelCustomizerView

logger = logging.getLogger(__name__)

# Per-user XP grant cooldowns: {(guild_id, user_id): datetime}
XP_COOLDOWNS: dict[tuple[int, int], datetime.datetime] = {}


class Extra(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ═══════════════════════════════════════════════════════════════════════════
    # SINGLE on_message LISTENER — handles XP, AFK removal, and AFK mention alerts
    # ═══════════════════════════════════════════════════════════════════════════

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        # ── 1. AFK: check if author was AFK and clear it ────────────────────
        afk = await Database.db.afk.find_one({"guild_id": message.guild.id, "user_id": message.author.id})
        if afk:
            await Database.db.afk.delete_one({"guild_id": message.guild.id, "user_id": message.author.id})
            try:
                nick = message.author.display_name.replace("[AFK] ", "", 1)
                await message.author.edit(nick=nick if nick != message.author.name else None)
            except discord.Forbidden:
                pass
            try:
                since = afk.get("since", datetime.datetime.utcnow())
                elapsed = datetime.datetime.utcnow() - since
                hours, rem = divmod(int(elapsed.total_seconds()), 3600)
                minutes = rem // 60
                reply = await message.channel.send(
                    embed=success_embed("Welcome Back!", f"Your AFK has been removed. (Away for {hours}h {minutes}m)")
                )
                await asyncio.sleep(5)
                await reply.delete()
            except discord.HTTPException:
                pass

        # ── 2. AFK: alert sender if they mentioned an AFK member ─────────────
        for mention in message.mentions:
            if mention.bot or mention.id == message.author.id:
                continue
            afk_data = await Database.db.afk.find_one({"guild_id": message.guild.id, "user_id": mention.id})
            if afk_data:
                since = afk_data.get("since", datetime.datetime.utcnow())
                elapsed = datetime.datetime.utcnow() - since
                hours, rem = divmod(int(elapsed.total_seconds()), 3600)
                minutes = rem // 60
                try:
                    alert = await message.channel.send(
                        embed=warning_embed(
                            f"{mention.display_name} is AFK",
                            f"**Reason:** {afk_data.get('reason', 'AFK')}\n**Since:** {hours}h {minutes}m ago",
                        )
                    )
                    await asyncio.sleep(8)
                    await alert.delete()
                except discord.HTTPException:
                    pass

        # ── 3. XP / Leveling ─────────────────────────────────────────────────
        key = (message.guild.id, message.author.id)
        now = datetime.datetime.utcnow()
        last_xp = XP_COOLDOWNS.get(key)
        if last_xp and (now - last_xp).total_seconds() < config.XP_COOLDOWN:
            return
        XP_COOLDOWNS[key] = now

        cfg = await get_guild_config(message.guild.id)
        if not cfg.get("leveling_enabled", True):
            return

        xp_gain = random.randint(max(1, config.XP_PER_MESSAGE - 5), config.XP_PER_MESSAGE + 5)
        doc = await Database.db.levels.find_one({"guild_id": message.guild.id, "user_id": message.author.id}) or {
            "xp": 0, "level": 0, "messages": 0
        }

        old_level = doc.get("level", 0)
        new_xp = doc.get("xp", 0) + xp_gain
        new_level, _, _ = xp_progress(new_xp)

        await Database.db.levels.update_one(
            {"guild_id": message.guild.id, "user_id": message.author.id},
            {"$set": {"xp": new_xp, "level": new_level}, "$inc": {"messages": 1}},
            upsert=True,
        )

        if new_level > old_level:
            level_up_channel_id = cfg.get("level_up_channel_id")
            channel = message.guild.get_channel(level_up_channel_id) if level_up_channel_id else message.channel
            try:
                embed = discord.Embed(
                    title="🎉 Level Up!",
                    description=f"Congratulations {message.author.mention}! You reached **Level {new_level}**!",
                    color=0xF1C40F,
                )
                embed.set_thumbnail(url=message.author.display_avatar.url)
                await channel.send(embed=embed)
            except discord.Forbidden:
                pass

            # Level role rewards
            level_roles = cfg.get("level_roles", {})
            role_id = level_roles.get(str(new_level))
            if role_id:
                role = message.guild.get_role(role_id)
                if role:
                    try:
                        await message.author.add_roles(role, reason=f"Level {new_level} reward")
                    except discord.Forbidden:
                        pass

    # ═══════════════════════════ LEVELING COMMANDS ════════════════════════════

    level_group = app_commands.Group(name="level", description="Leveling system commands")

    @level_group.command(name="rank", description="Check your or another member's rank")
    @app_commands.describe(member="Member to check rank for")
    async def rank(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        doc = await Database.db.levels.find_one({"guild_id": interaction.guild_id, "user_id": target.id}) or {
            "xp": 0, "level": 0, "messages": 0
        }

        level, current_xp, needed_xp = xp_progress(doc.get("xp", 0))
        bar_fill = int((current_xp / needed_xp) * 20) if needed_xp else 0
        bar = "█" * bar_fill + "░" * (20 - bar_fill)

        rank_pos = await Database.db.levels.count_documents(
            {"guild_id": interaction.guild_id, "xp": {"$gt": doc.get("xp", 0)}}
        ) + 1

        embed = primary_embed(f"📊 {target.display_name}'s Rank")
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Level", value=str(level), inline=True)
        embed.add_field(name="Rank", value=f"#{rank_pos}", inline=True)
        embed.add_field(name="Messages", value=f"{doc.get('messages', 0):,}", inline=True)
        embed.add_field(name="XP Progress", value=f"`{bar}` {current_xp:,}/{needed_xp:,} XP", inline=False)
        await interaction.response.send_message(embed=embed)

    @level_group.command(name="leaderboard", description="View the server XP leaderboard")
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer()
        entries = await Database.db.levels.find({"guild_id": interaction.guild_id}).sort("xp", -1).limit(10).to_list(10)
        embed = primary_embed("🏆 XP Leaderboard", f"**{interaction.guild.name}**")
        medals = ["🥇", "🥈", "🥉"]
        for i, entry in enumerate(entries):
            member = interaction.guild.get_member(entry["user_id"])
            name = member.display_name if member else f"Unknown ({entry['user_id']})"
            level, _, _ = xp_progress(entry.get("xp", 0))
            medal = medals[i] if i < 3 else f"{i + 1}."
            embed.add_field(name=f"{medal} {name}", value=f"**Level {level}** — {entry.get('xp', 0):,} XP", inline=False)
        if not entries:
            embed.description = "No XP data yet! Start chatting!"
        await interaction.followup.send(embed=embed)

    @level_group.command(name="setlevel", description="Set a member's level (admin only)")
    @app_commands.describe(member="Member", level="Level to set")
    @app_commands.default_permissions(administrator=True)
    async def setlevel(self, interaction: discord.Interaction, member: discord.Member, level: int):
        if level < 0:
            await interaction.response.send_message(embed=error_embed("Invalid", "Level must be 0 or higher."), ephemeral=True)
            return
        total_xp = sum(xp_for_level(i + 1) for i in range(level))
        await Database.db.levels.update_one(
            {"guild_id": interaction.guild_id, "user_id": member.id},
            {"$set": {"xp": total_xp, "level": level}},
            upsert=True,
        )
        await interaction.response.send_message(
            embed=success_embed("Level Set", f"Set {member.mention}'s level to **{level}**."),
            ephemeral=True,
        )

    @level_group.command(name="toggle", description="Enable or disable the leveling system")
    @app_commands.describe(enabled="Whether to enable leveling")
    @app_commands.default_permissions(administrator=True)
    async def toggle(self, interaction: discord.Interaction, enabled: bool):
        await update_guild_config(interaction.guild_id, {"leveling_enabled": enabled})
        state = "enabled" if enabled else "disabled"
        await interaction.response.send_message(
            embed=success_embed("Leveling System", f"Leveling has been **{state}**."),
            ephemeral=True,
        )

    # ═══════════════════════════════ GIVEAWAYS ════════════════════════════════

    giveaway_group = app_commands.Group(name="giveaway", description="Giveaway commands")

    @giveaway_group.command(name="start", description="Start a giveaway")
    @app_commands.describe(
        prize="Prize description",
        duration="Duration in minutes",
        winners="Number of winners",
        channel="Channel to host the giveaway in",
        color="Embed color as hex (e.g. #FF0000)",
        image="Large image URL for the embed",
        thumbnail="Thumbnail image URL",
        description="Custom description (use {prize} {winners} {ends})",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def giveaway_start(
        self,
        interaction: discord.Interaction,
        prize: str,
        duration: int,
        winners: int = 1,
        channel: discord.TextChannel = None,
        color: str = None,
        image: str = None,
        thumbnail: str = None,
        description: str = None,
    ):
        await interaction.response.defer(ephemeral=True)
        if duration < 1:
            await interaction.followup.send(embed=error_embed("Invalid", "Duration must be at least 1 minute."), ephemeral=True)
            return
        target = channel or interaction.channel
        ends_at = discord.utils.utcnow() + datetime.timedelta(minutes=duration)

        try:
            embed_color = int(color.lstrip("#"), 16) if color else 0xF1C40F
        except ValueError:
            embed_color = 0xF1C40F

        default_desc = f"Click the button below to enter!\n\n**Winners:** {winners}\n**Ends:** {discord.utils.format_dt(ends_at, 'R')}"
        embed_desc = (description or default_desc).replace("{prize}", prize).replace("{winners}", str(winners)).replace("{ends}", discord.utils.format_dt(ends_at, 'R'))

        embed = discord.Embed(
            title=f"🎉 GIVEAWAY — {prize}",
            description=embed_desc,
            color=embed_color,
            timestamp=ends_at,
        )
        if image:
            embed.set_image(url=image)
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        embed.set_footer(text="Ends at • 0 participants")
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)

        view = GiveawayView()
        msg = await target.send(embed=embed, view=view)

        await Database.db.giveaways.insert_one({
            "guild_id": interaction.guild_id,
            "channel_id": target.id,
            "message_id": msg.id,
            "prize": prize,
            "winners": winners,
            "participants": [],
            "ended": False,
            "created_by": interaction.user.id,
            "ends_at": ends_at,
        })

        await interaction.followup.send(embed=success_embed("Giveaway Started!", f"Giveaway started in {target.mention}!"), ephemeral=True)
        self.bot.loop.create_task(self._end_giveaway_after(duration * 60, msg.id, interaction.guild_id))

    async def _end_giveaway_after(self, delay: float, message_id: int, guild_id: int):
        await asyncio.sleep(delay)
        await self._end_giveaway(message_id, guild_id)

    async def _end_giveaway(self, message_id: int, guild_id: int):
        doc = await Database.db.giveaways.find_one({"message_id": message_id, "ended": False})
        if not doc:
            return
        await Database.db.giveaways.update_one({"message_id": message_id}, {"$set": {"ended": True}})
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        channel = guild.get_channel(doc["channel_id"])
        if not channel:
            return

        participants = doc.get("participants", [])
        winner_count = min(doc.get("winners", 1), len(participants))

        if not participants:
            embed = discord.Embed(
                title=f"🎉 GIVEAWAY ENDED — {doc['prize']}",
                description="No one entered the giveaway!",
                color=0xE74C3C,
                timestamp=discord.utils.utcnow(),
            )
            await channel.send(embed=embed)
        else:
            winners = random.sample(participants, winner_count)
            winner_mentions = " ".join(f"<@{w}>" for w in winners)
            embed = discord.Embed(
                title=f"🎉 GIVEAWAY ENDED — {doc['prize']}",
                description=f"**Winner{'s' if len(winners) > 1 else ''}:** {winner_mentions}\n**Participants:** {len(participants)}",
                color=0x2ECC71,
                timestamp=discord.utils.utcnow(),
            )
            await channel.send(content=winner_mentions, embed=embed)

    @giveaway_group.command(name="end", description="End a giveaway early")
    @app_commands.describe(message_id="Message ID of the giveaway")
    @app_commands.default_permissions(manage_guild=True)
    async def giveaway_end(self, interaction: discord.Interaction, message_id: str):
        await interaction.response.defer(ephemeral=True)
        try:
            mid = int(message_id)
        except ValueError:
            await interaction.followup.send(embed=error_embed("Invalid", "Invalid message ID."), ephemeral=True)
            return
        doc = await Database.db.giveaways.find_one({"message_id": mid, "guild_id": interaction.guild_id})
        if not doc:
            await interaction.followup.send(embed=error_embed("Not Found", "Giveaway not found."), ephemeral=True)
            return
        await self._end_giveaway(mid, interaction.guild_id)
        await interaction.followup.send(embed=success_embed("Ended", "Giveaway ended."), ephemeral=True)

    @giveaway_group.command(name="reroll", description="Reroll a giveaway winner")
    @app_commands.describe(message_id="Message ID of the ended giveaway")
    @app_commands.default_permissions(manage_guild=True)
    async def giveaway_reroll(self, interaction: discord.Interaction, message_id: str):
        await interaction.response.defer()
        try:
            mid = int(message_id)
        except ValueError:
            await interaction.followup.send(embed=error_embed("Invalid", "Invalid message ID."))
            return
        doc = await Database.db.giveaways.find_one({"message_id": mid, "guild_id": interaction.guild_id})
        if not doc:
            await interaction.followup.send(embed=error_embed("Not Found", "Giveaway not found."))
            return
        participants = doc.get("participants", [])
        if not participants:
            await interaction.followup.send(embed=error_embed("No Participants", "No one entered this giveaway."))
            return
        winner = random.choice(participants)
        await interaction.followup.send(
            embed=success_embed("Rerolled!", f"New winner: <@{winner}>! 🎉")
        )

    # ═══════════════════════════════ POLLS ═══════════════════════════════════

    poll_group = app_commands.Group(name="poll", description="Poll commands")

    @poll_group.command(name="create", description="Create a poll")
    @app_commands.describe(
        question="Poll question",
        options="Choices separated by | (2–5)",
        color="Embed color as hex (e.g. #FF0000)",
        image="Large image URL for the embed",
        thumbnail="Thumbnail URL",
    )
    async def poll_create(
        self,
        interaction: discord.Interaction,
        question: str,
        options: str,
        color: str = None,
        image: str = None,
        thumbnail: str = None,
    ):
        await interaction.response.defer()
        option_list = [o.strip() for o in options.split("|") if o.strip()][:5]
        if len(option_list) < 2:
            await interaction.followup.send(embed=error_embed("Too Few Options", "Provide at least 2 options separated by `|`."))
            return

        try:
            embed_color = int(color.lstrip("#"), 16) if color else 0x5865F2
        except ValueError:
            embed_color = 0x5865F2

        embed = discord.Embed(title=f"📊 {question}", color=embed_color, timestamp=discord.utils.utcnow())
        if image:
            embed.set_image(url=image)
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        for opt in option_list:
            embed.add_field(name=opt, value="`░░░░░░░░░░` 0% (0 votes)", inline=False)
        embed.set_footer(text=f"Poll by {interaction.user.display_name} • Total votes: 0")

        view = PollView(option_list)
        await interaction.followup.send(embed=embed, view=view)

        actual_msg = await interaction.original_response()
        await Database.db.polls.insert_one({
            "guild_id": interaction.guild_id,
            "message_id": actual_msg.id,
            "channel_id": interaction.channel_id,
            "question": question,
            "options": option_list,
            "votes": {},
            "created_by": interaction.user.id,
            "created_at": discord.utils.utcnow(),
        })

    @poll_group.command(name="end", description="End a poll and show final results")
    @app_commands.describe(message_id="Message ID of the poll")
    @app_commands.default_permissions(manage_messages=True)
    async def poll_end(self, interaction: discord.Interaction, message_id: str):
        await interaction.response.defer(ephemeral=True)
        try:
            mid = int(message_id)
        except ValueError:
            await interaction.followup.send(embed=error_embed("Invalid", "Invalid message ID."), ephemeral=True)
            return
        doc = await Database.db.polls.find_one({"message_id": mid, "guild_id": interaction.guild_id})
        if not doc:
            await interaction.followup.send(embed=error_embed("Not Found", "Poll not found."), ephemeral=True)
            return
        votes = doc.get("votes", {})
        total = len(votes)
        options = doc.get("options", [])
        counts = [sum(1 for v in votes.values() if v == i) for i in range(len(options))]
        winner_idx = counts.index(max(counts)) if counts and total > 0 else 0

        embed = discord.Embed(title=f"📊 Poll Ended: {doc['question']}", color=0x2ECC71, timestamp=discord.utils.utcnow())
        for i, (opt, count) in enumerate(zip(options, counts)):
            pct = (count / total * 100) if total else 0
            bar_fill = int(pct / 10)
            bar = "█" * bar_fill + "░" * (10 - bar_fill)
            winner_tag = " 🏆" if i == winner_idx and total > 0 else ""
            embed.add_field(name=f"{opt}{winner_tag}", value=f"`{bar}` {pct:.1f}% ({count} votes)", inline=False)
        embed.set_footer(text=f"Total votes: {total}")

        try:
            channel = interaction.guild.get_channel(doc["channel_id"])
            if channel:
                msg = await channel.fetch_message(mid)
                await msg.edit(embed=embed, view=None)
        except discord.NotFound:
            pass
        await interaction.followup.send(embed=success_embed("Poll Ended", "Results have been finalized."), ephemeral=True)

    # ═══════════════════════════ SUGGESTIONS ════════════════════════════════

    suggestion_group = app_commands.Group(name="suggestions", description="Suggestion commands")

    @suggestion_group.command(name="setup", description="Configure the suggestion channel")
    @app_commands.describe(channel="Channel for suggestions")
    @app_commands.default_permissions(administrator=True)
    async def suggestion_setup(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await update_guild_config(interaction.guild_id, {"suggestion_channel_id": channel.id})
        await interaction.response.send_message(
            embed=success_embed("Suggestions Configured", f"Suggestions will be sent to {channel.mention}."),
            ephemeral=True,
        )

    @suggestion_group.command(name="submit", description="Submit a suggestion")
    @app_commands.describe(suggestion="Your suggestion")
    async def suggestion_submit(self, interaction: discord.Interaction, suggestion: str):
        cfg = await get_guild_config(interaction.guild_id)
        channel_id = cfg.get("suggestion_channel_id")
        if not channel_id:
            await interaction.response.send_message(
                embed=error_embed("Not Configured", "Ask an admin to run `/suggestions setup` first."),
                ephemeral=True,
            )
            return
        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            await interaction.response.send_message(embed=error_embed("Error", "Suggestion channel not found."), ephemeral=True)
            return

        count = await Database.db.suggestions.count_documents({"guild_id": interaction.guild_id}) + 1
        embed = discord.Embed(
            title=f"💡 Suggestion #{count}",
            description=suggestion,
            color=0x5865F2,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text=f"Suggestion ID: {count}")
        embed.add_field(name="Status", value="⏳ Pending", inline=True)

        msg = await channel.send(embed=embed)
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")

        await Database.db.suggestions.insert_one({
            "guild_id": interaction.guild_id,
            "suggestion_id": count,
            "user_id": interaction.user.id,
            "content": suggestion,
            "message_id": msg.id,
            "status": "pending",
            "created_at": discord.utils.utcnow(),
        })
        await interaction.response.send_message(
            embed=success_embed("Suggestion Submitted!", f"Your suggestion has been posted! (#**{count}**)"),
            ephemeral=True,
        )

    @suggestion_group.command(name="approve", description="Approve a suggestion")
    @app_commands.describe(suggestion_id="Suggestion ID", reason="Reason")
    @app_commands.default_permissions(manage_messages=True)
    async def suggestion_approve(self, interaction: discord.Interaction, suggestion_id: int, reason: str = "No reason provided"):
        await self._update_suggestion(interaction, suggestion_id, "approved", reason, 0x2ECC71, "✅")

    @suggestion_group.command(name="deny", description="Deny a suggestion")
    @app_commands.describe(suggestion_id="Suggestion ID", reason="Reason")
    @app_commands.default_permissions(manage_messages=True)
    async def suggestion_deny(self, interaction: discord.Interaction, suggestion_id: int, reason: str = "No reason provided"):
        await self._update_suggestion(interaction, suggestion_id, "denied", reason, 0xE74C3C, "❌")

    async def _update_suggestion(self, interaction: discord.Interaction, sid: int, status: str, reason: str, color: int, emoji: str):
        doc = await Database.db.suggestions.find_one({"guild_id": interaction.guild_id, "suggestion_id": sid})
        if not doc:
            await interaction.response.send_message(embed=error_embed("Not Found", f"Suggestion #{sid} not found."), ephemeral=True)
            return
        await Database.db.suggestions.update_one({"suggestion_id": sid, "guild_id": interaction.guild_id}, {"$set": {"status": status}})
        cfg = await get_guild_config(interaction.guild_id)
        channel = interaction.guild.get_channel(cfg.get("suggestion_channel_id"))
        if channel:
            try:
                msg = await channel.fetch_message(doc["message_id"])
                if msg.embeds:
                    embed = discord.Embed.from_dict(msg.embeds[0].to_dict())
                    embed.color = color
                    for i, field in enumerate(embed.fields):
                        if field.name == "Status":
                            embed.set_field_at(i, name="Status", value=f"{emoji} {status.title()}", inline=True)
                            break
                    embed.add_field(name="Review Reason", value=reason, inline=False)
                    embed.add_field(name="Reviewed by", value=interaction.user.mention, inline=True)
                    await msg.edit(embed=embed)
            except discord.NotFound:
                pass
        await interaction.response.send_message(
            embed=success_embed(f"Suggestion {status.title()}", f"Suggestion #{sid} has been {status}."),
            ephemeral=True,
        )

    # ═══════════════════════════════ STARBOARD ══════════════════════════════

    starboard_group = app_commands.Group(name="starboard", description="Starboard commands")

    @starboard_group.command(name="setup", description="Configure the starboard")
    @app_commands.describe(channel="Starboard channel", threshold="Stars needed")
    @app_commands.default_permissions(administrator=True)
    async def starboard_setup(self, interaction: discord.Interaction, channel: discord.TextChannel, threshold: int = 3):
        await update_guild_config(interaction.guild_id, {"starboard_channel_id": channel.id, "starboard_threshold": threshold})
        await interaction.response.send_message(
            embed=success_embed("Starboard Configured", f"Starboard set to {channel.mention} — **{threshold}** ⭐ required."),
            ephemeral=True,
        )

    @starboard_group.command(name="view", description="View starboard configuration")
    async def starboard_view(self, interaction: discord.Interaction):
        cfg = await get_guild_config(interaction.guild_id)
        ch = interaction.guild.get_channel(cfg.get("starboard_channel_id"))
        embed = info_embed("⭐ Starboard", "")
        embed.add_field(name="Channel", value=ch.mention if ch else "Not set", inline=True)
        embed.add_field(name="Threshold", value=f"{cfg.get('starboard_threshold', config.STAR_THRESHOLD)} ⭐", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        if user.bot or str(reaction.emoji) != "⭐":
            return
        if not reaction.message.guild:
            return

        cfg = await get_guild_config(reaction.message.guild.id)
        channel_id = cfg.get("starboard_channel_id")
        if not channel_id:
            return

        threshold = cfg.get("starboard_threshold", config.STAR_THRESHOLD)
        if reaction.count < threshold:
            return

        existing = await Database.db.starboard.find_one({
            "guild_id": reaction.message.guild.id,
            "original_id": reaction.message.id,
        })
        star_channel = reaction.message.guild.get_channel(channel_id)
        if not star_channel:
            return

        if existing:
            try:
                star_msg = await star_channel.fetch_message(existing["star_message_id"])
                if star_msg.embeds:
                    embed = discord.Embed.from_dict(star_msg.embeds[0].to_dict())
                    embed.set_footer(text=f"⭐ {reaction.count} | #{reaction.message.channel.name}")
                    await star_msg.edit(embed=embed)
            except discord.NotFound:
                pass
            return

        if star_channel.id == reaction.message.channel.id:
            return

        msg = reaction.message
        embed = discord.Embed(description=msg.content or "", color=0xF1C40F, timestamp=msg.created_at)
        embed.set_author(name=str(msg.author), icon_url=msg.author.display_avatar.url)
        if msg.attachments:
            embed.set_image(url=msg.attachments[0].url)
        embed.add_field(name="Source", value=f"[Jump to message]({msg.jump_url})", inline=False)
        embed.set_footer(text=f"⭐ {reaction.count} | #{msg.channel.name}")

        star_msg = await star_channel.send(embed=embed)
        await Database.db.starboard.insert_one({
            "guild_id": reaction.message.guild.id,
            "original_id": msg.id,
            "star_message_id": star_msg.id,
            "channel_id": channel_id,
        })

    # ═══════════════════════════════ AFK SYSTEM ══════════════════════════════

    afk_group = app_commands.Group(name="afk", description="AFK system commands")

    @afk_group.command(name="set", description="Set your AFK status")
    @app_commands.describe(reason="Reason for being AFK")
    async def afk_set(self, interaction: discord.Interaction, reason: str = "AFK"):
        await Database.db.afk.update_one(
            {"guild_id": interaction.guild_id, "user_id": interaction.user.id},
            {"$set": {"reason": reason, "since": discord.utils.utcnow()}},
            upsert=True,
        )
        try:
            if not interaction.user.display_name.startswith("[AFK]"):
                await interaction.user.edit(nick=f"[AFK] {interaction.user.display_name}"[:32])
        except discord.Forbidden:
            pass
        await interaction.response.send_message(embed=success_embed("AFK Set", f"You're now AFK: **{reason}**"), ephemeral=True)

    # ═══════════════════════════ REACTION ROLES ════════════════════════════

    rr_group = app_commands.Group(name="reactionroles", description="Reaction role commands")

    @rr_group.command(name="add", description="Add a reaction role to a message")
    @app_commands.describe(message_id="Message ID", emoji="Emoji to react with", role="Role to assign")
    @app_commands.default_permissions(administrator=True)
    async def rr_add(self, interaction: discord.Interaction, message_id: str, emoji: str, role: discord.Role):
        await interaction.response.defer(ephemeral=True)
        try:
            mid = int(message_id)
            msg = await interaction.channel.fetch_message(mid)
        except (ValueError, discord.NotFound):
            await interaction.followup.send(embed=error_embed("Not Found", "Message not found in this channel."), ephemeral=True)
            return
        try:
            await msg.add_reaction(emoji)
        except discord.HTTPException:
            await interaction.followup.send(embed=error_embed("Invalid Emoji", "Could not add that emoji."), ephemeral=True)
            return
        await Database.db.reaction_roles.update_one(
            {"guild_id": interaction.guild_id, "message_id": mid},
            {"$set": {f"roles.{emoji}": role.id}},
            upsert=True,
        )
        await interaction.followup.send(embed=success_embed("Reaction Role Added", f"React with {emoji} to get {role.mention}."), ephemeral=True)

    @rr_group.command(name="remove", description="Remove a reaction role from a message")
    @app_commands.describe(message_id="Message ID", emoji="Emoji to remove")
    @app_commands.default_permissions(administrator=True)
    async def rr_remove(self, interaction: discord.Interaction, message_id: str, emoji: str):
        try:
            mid = int(message_id)
        except ValueError:
            await interaction.response.send_message(embed=error_embed("Invalid", "Invalid message ID."), ephemeral=True)
            return
        await Database.db.reaction_roles.update_one(
            {"guild_id": interaction.guild_id, "message_id": mid},
            {"$unset": {f"roles.{emoji}": ""}},
        )
        await interaction.response.send_message(embed=success_embed("Removed", f"Reaction role for {emoji} removed."), ephemeral=True)

    @rr_group.command(name="list", description="List reaction roles for a message")
    @app_commands.describe(message_id="Message ID")
    async def rr_list(self, interaction: discord.Interaction, message_id: str):
        try:
            mid = int(message_id)
        except ValueError:
            await interaction.response.send_message(embed=error_embed("Invalid", "Invalid message ID."), ephemeral=True)
            return
        doc = await Database.db.reaction_roles.find_one({"guild_id": interaction.guild_id, "message_id": mid})
        if not doc or not doc.get("roles"):
            await interaction.response.send_message(embed=info_embed("No Reaction Roles", "No reaction roles on that message."), ephemeral=True)
            return
        embed = info_embed("Reaction Roles", f"Message ID: `{mid}`")
        for emoji, role_id in doc["roles"].items():
            role = interaction.guild.get_role(role_id)
            embed.add_field(name=emoji, value=role.mention if role else f"Deleted ({role_id})", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return
        doc = await Database.db.reaction_roles.find_one({"guild_id": payload.guild_id, "message_id": payload.message_id})
        if not doc:
            return
        role_id = doc.get("roles", {}).get(str(payload.emoji))
        if not role_id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id)
        role = guild.get_role(role_id)
        if member and role:
            try:
                await member.add_roles(role, reason="Reaction role")
            except discord.Forbidden:
                pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return
        doc = await Database.db.reaction_roles.find_one({"guild_id": payload.guild_id, "message_id": payload.message_id})
        if not doc:
            return
        role_id = doc.get("roles", {}).get(str(payload.emoji))
        if not role_id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id)
        role = guild.get_role(role_id)
        if member and role:
            try:
                await member.remove_roles(role, reason="Reaction role removed")
            except discord.Forbidden:
                pass

    # ═══════════════════════════ VERIFICATION ════════════════════════════════

    verify_group = app_commands.Group(name="verification", description="Verification system commands")

    @verify_group.command(name="setup", description="Quick setup: send a default verification panel")
    @app_commands.describe(channel="Verification channel", role="Role to give on verification", message="Message shown to users")
    @app_commands.default_permissions(administrator=True)
    async def verify_setup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        role: discord.Role,
        message: str = "Click the button below to verify and gain access to the server.",
    ):
        await update_guild_config(interaction.guild_id, {
            "verification_channel_id": channel.id,
            "verification_role_id": role.id,
        })
        cfg_data = await get_guild_config(interaction.guild_id)
        panel_data = cfg_data.get("verify_panel", {})
        if panel_data:
            embed = build_panel_embed(panel_data)
        else:
            embed = discord.Embed(title="✅ Verification", description=message, color=0x5865F2)
        view = VerifyView(role.id)
        await channel.send(embed=embed, view=view)
        await interaction.response.send_message(
            embed=success_embed("Verification Setup", f"Verification panel sent to {channel.mention}.\nUse `/verification customize` to design the embed."),
            ephemeral=True,
        )

    @verify_group.command(name="customize", description="Open the interactive verification panel customizer")
    @app_commands.default_permissions(administrator=True)
    async def verify_customize(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        data = cfg.get("verify_panel", {
            "title": "✅ Verification",
            "description": "Click the button below to verify and gain access to the server.",
            "color": 0x5865F2,
        })
        view = VerifyPanelCustomizerView(interaction.user.id, data)
        embed = primary_embed("✅ Verification Panel Customizer", view._summary())
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    # ═══════════════════════════ CUSTOM COMMANDS ══════════════════════════════

    cc_group = app_commands.Group(name="customcmd", description="Custom command management")

    @cc_group.command(name="add", description="Add a custom command")
    @app_commands.describe(name="Command name (no spaces, no slashes)", response="Response text")
    @app_commands.default_permissions(administrator=True)
    async def cc_add(self, interaction: discord.Interaction, name: str, response: str):
        name = name.lower().replace(" ", "-").lstrip("/")
        existing = await Database.db.custom_commands.find_one({"guild_id": interaction.guild_id, "name": name})
        if existing:
            await interaction.response.send_message(embed=error_embed("Exists", f"Custom command `{name}` already exists."), ephemeral=True)
            return
        await Database.db.custom_commands.insert_one({
            "guild_id": interaction.guild_id,
            "name": name,
            "response": response,
            "uses": 0,
        })
        await interaction.response.send_message(embed=success_embed("Command Added", f"Custom command `{name}` added."), ephemeral=True)

    @cc_group.command(name="remove", description="Remove a custom command")
    @app_commands.describe(name="Command name")
    @app_commands.default_permissions(administrator=True)
    async def cc_remove(self, interaction: discord.Interaction, name: str):
        result = await Database.db.custom_commands.delete_one({"guild_id": interaction.guild_id, "name": name.lower()})
        if result.deleted_count == 0:
            await interaction.response.send_message(embed=error_embed("Not Found", f"No custom command `{name}` found."), ephemeral=True)
            return
        await interaction.response.send_message(embed=success_embed("Removed", f"Custom command `{name}` removed."), ephemeral=True)

    @cc_group.command(name="list", description="List all custom commands")
    async def cc_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cmds = await Database.db.custom_commands.find({"guild_id": interaction.guild_id}).to_list(50)
        if not cmds:
            await interaction.followup.send(embed=info_embed("Custom Commands", "No custom commands set up."), ephemeral=True)
            return
        embed = info_embed("Custom Commands", f"**{len(cmds)}** custom commands:")
        for cmd in cmds[:25]:
            embed.add_field(
                name=f"/{cmd['name']}",
                value=f"{cmd['response'][:80]}\n*Used {cmd.get('uses', 0)} times*",
                inline=False,
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.application_command:
            return
        if not interaction.guild_id:
            return
        name = interaction.data.get("name", "")
        doc = await Database.db.custom_commands.find_one({"guild_id": interaction.guild_id, "name": name})
        if not doc:
            return
        if interaction.response.is_done():
            return
        response = doc["response"].replace("{user}", interaction.user.mention).replace("{server}", interaction.guild.name)
        await Database.db.custom_commands.update_one({"_id": doc["_id"]}, {"$inc": {"uses": 1}})
        await interaction.response.send_message(embed=primary_embed("", response))


class VerifyView(discord.ui.View):
    def __init__(self, role_id: int = None):
        super().__init__(timeout=None)
        self.role_id = role_id

    @discord.ui.button(label="Verify", style=discord.ButtonStyle.success, emoji="✅", custom_id="verify:button")
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await get_guild_config(interaction.guild_id)
        role_id = self.role_id or cfg.get("verification_role_id")
        if not role_id:
            await interaction.response.send_message(embed=error_embed("Not Configured", "Verification role not set."), ephemeral=True)
            return
        role = interaction.guild.get_role(role_id)
        if not role:
            await interaction.response.send_message(embed=error_embed("Error", "Verification role not found."), ephemeral=True)
            return
        if role in interaction.user.roles:
            await interaction.response.send_message(embed=warning_embed("Already Verified", "You are already verified!"), ephemeral=True)
            return
        await interaction.user.add_roles(role, reason="Verification")
        await interaction.response.send_message(
            embed=success_embed("Verified!", f"You've been verified and given **{role.name}**!"),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Extra(bot))
