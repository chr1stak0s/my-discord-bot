import discord
from discord import app_commands
from discord.ext import commands, tasks
import datetime
import logging
from database import Database, get_guild_config, update_guild_config
from utils import success_embed, error_embed, info_embed, primary_embed, is_admin

logger = logging.getLogger(__name__)

# ─── Stat channel definitions ──────────────────────────────────────────────────
# Each entry: (mongo_key, name_template, emoji_label)
STAT_CHANNELS: list[tuple[str, str, str]] = [
    ("members", "👥 Members: {value}", "👥 Members"),
    ("online",  "🟢 Online: {value}",  "🟢 Online"),
    ("bots",    "🤖 Bots: {value}",    "🤖 Bots"),
    ("voice",   "🔊 In Voice: {value}", "🔊 In Voice"),
    ("boosts",  "🚀 Boosts: {value}",  "🚀 Boosts"),
    ("created", "📅 Created: {value}", "📅 Created"),
]


def _collect_stats(guild: discord.Guild) -> dict[str, str]:
    """Return the current live stats for a guild."""
    bots    = sum(1 for m in guild.members if m.bot)
    online  = sum(1 for m in guild.members if not m.bot and m.status != discord.Status.offline)
    in_vc   = sum(1 for m in guild.members if m.voice is not None)
    boosts  = guild.premium_subscription_count or 0
    created = guild.created_at.strftime("%b %d %Y")
    return {
        "members": f"{guild.member_count:,}",
        "online":  f"{online:,}",
        "bots":    f"{bots:,}",
        "voice":   f"{in_vc:,}",
        "boosts":  f"{boosts:,}",
        "created": created,
    }


class ServerStatsCog(commands.Cog, name="ServerStats"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._last_updated: dict[int, datetime.datetime] = {}

    

    def cog_unload(self):
        self.auto_update.cancel()

         # ─── on_ready: bulletproof task start ─────────────────────────────────────
    # We start the task here instead of cog_load / __init__ because this
    # guarantees the bot is fully connected and the event loop is ready.
    # The is_running() guard prevents double-starts on reconnects.
    @commands.Cog.listener()
    async def on_ready(self):
        if not self.auto_update.is_running():
            self.auto_update.start()
            logger.info("[serverstats] auto_update task started")

    # ─── Background task ───────────────────────────────────────────────────────

     # Interval: 10 min — Discord allows only ~2 channel-name edits per 10 min
    # per channel. A shorter interval just causes silent rate-limit blocks.
    @tasks.loop(minutes=10)
    async def auto_update(self):
        
        try:
            docs = await Database.db.guilds.find(
                {"serverstats.category_id": {"$exists": True, "$ne": None}}
            ).to_list(1000)
        except Exception as exc:
            logger.error(f"[serverstats] DB query failed: {exc}")
            return

        for doc in docs:
            try:
                guild = self.bot.get_guild(doc["guild_id"])
                if guild is None:
                    continue
                await self._push_stats(guild, doc.get("serverstats", {}))
            except Exception as exc:
                 logger.error(
                    f"[serverstats] failed to update guild {doc.get('guild_id')}: {exc}",
                    exc_info=True,
                )


    @auto_update.error
    async def _auto_update_error(self, error: Exception):
        logger.error(f"[serverstats] task crashed: {error}", exc_info=True)
        # Wait 60 s then restart so one crash doesn't kill all future updates
        await discord.utils.sleep_until(
            discord.utils.utcnow() + datetime.timedelta(seconds=60)
        )
        if not self.auto_update.is_running():
            self.auto_update.restart()

    # ─── Core update helper ────────────────────────────────────────────────────

    async def _push_stats(self, guild: discord.Guild, cfg: dict) -> int:
        """Edit each stat channel name. Returns number of channels updated."""
        stats = _collect_stats(guild)
        channels_map: dict[str, int] = cfg.get("channels", {})
        updated = 0

        for key, template, _ in STAT_CHANNELS:
            ch_id = channels_map.get(key)
            if not ch_id:
                continue
            channel = guild.get_channel(ch_id)
            if not isinstance(channel, discord.VoiceChannel):
                continue
            new_name = template.format(value=stats[key])
            if channel.name == new_name:
                continue                             # skip — nothing changed
            try:
                await channel.edit(
                    name=new_name,
                    reason="Server Stats auto-update",
                )
                updated += 1
            except discord.HTTPException as exc:
                if exc.status == 429:
                    logger.warning(
                        f"[serverstats] rate-limited on guild {guild.id} channel {ch_id} "
                        f"— will retry next cycle"
                    )
                else:
                    logger.error(f"[serverstats] HTTP {exc.status} updating {ch_id}: {exc}")
            except Exception as exc:
                logger.error(f"[serverstats] unexpected error updating {ch_id}: {exc}")

        self._last_updated[guild.id] = datetime.datetime.utcnow()
        return updated

    # ─── Slash commands ────────────────────────────────────────────────────────

    stats_group = app_commands.Group(
        name="serverstats",
        description="Live server statistics channels",
    )

    # ── /serverstats setup ────────────────────────────────────────────────────

    @stats_group.command(
        name="setup",
        description="Create a live stats category with auto-updating voice channels",
    )
    @is_admin()
    async def setup(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        # ── Duplicate-setup guard ──────────────────────────────────────────
        cfg = await get_guild_config(guild.id)
        existing = cfg.get("serverstats", {})
        if existing.get("category_id"):
            cat = guild.get_channel(existing["category_id"])
            if cat:
                embed = error_embed(
                    "Already Configured",
                    f"Stats are already set up in **{cat.name}**.\n"
                    "Use `/serverstats remove` to start over, or `/serverstats refresh` to force an update.",
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            # Category was deleted externally — clean up and continue
            await update_guild_config(guild.id, {"serverstats": {}})

        # ── Bot permission check ──────────────────────────────────────────
        if not guild.me.guild_permissions.manage_channels:
            await interaction.followup.send(
                embed=error_embed(
                    "Missing Permission",
                    "I need **Manage Channels** permission to create stat channels.",
                ),
                ephemeral=True,
            )
            return

        # ── Create category ───────────────────────────────────────────────
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=True,
                connect=False,        # members can see but not join
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                manage_channels=True, # bot can rename channels
            ),
        }

        try:
            category = await guild.create_category(
                "📊 Server Statistics",
                overwrites=overwrites,
                reason=f"Server stats setup by {interaction.user}",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                embed=error_embed("Forbidden", "I don't have permission to create categories."),
                ephemeral=True,
            )
            return
        except discord.HTTPException as exc:
            await interaction.followup.send(
                embed=error_embed("Error", f"Failed to create category: {exc}"),
                ephemeral=True,
            )
            return

        # ── Create stat voice channels ────────────────────────────────────
        stats = _collect_stats(guild)
        channel_ids: dict[str, int] = {}
        failed_keys: list[str] = []

        for key, template, _ in STAT_CHANNELS:
            name = template.format(value=stats[key])
            try:
                ch = await category.create_voice_channel(
                    name,
                    overwrites=overwrites,
                    reason=f"Server stats setup by {interaction.user}",
                )
                channel_ids[key] = ch.id
            except Exception as exc:
                logger.error(f"[serverstats] failed to create channel '{key}': {exc}")
                failed_keys.append(key)

        # ── Persist to MongoDB ────────────────────────────────────────────
        doc = {
            "category_id": category.id,
            "channels":    channel_ids,
            "created_at":  datetime.datetime.utcnow().isoformat(),
            "created_by":  interaction.user.id,
        }
        await update_guild_config(guild.id, {"serverstats": doc})
        self._last_updated[guild.id] = datetime.datetime.utcnow()

        # ── Success response ──────────────────────────────────────────────
        embed = success_embed(
            "📊 Server Stats Created",
            f"**{len(channel_ids)}** live stat channel(s) are now active under {category.mention}.",
        )
        embed.add_field(name="Auto-Update Interval", value="Every 5 minutes", inline=True)
        embed.add_field(name="Channels Created",     value=str(len(channel_ids)), inline=True)
        if failed_keys:
            embed.add_field(
                name="⚠️ Could Not Create",
                value=", ".join(failed_keys),
                inline=False,
            )

        lines = []
        for key, _, label in STAT_CHANNELS:
            if key in channel_ids:
                ch = guild.get_channel(channel_ids[key])
                lines.append(f"• {ch.name if ch else label}")
        embed.add_field(name="Live Channels", value="\n".join(lines) or "—", inline=False)
        embed.set_footer(text="Channels update automatically every 5 min · /serverstats refresh to force-update")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /serverstats refresh ──────────────────────────────────────────────────

    @stats_group.command(
        name="refresh",
        description="Force an immediate refresh of all stat channels",
    )
    @is_admin()
    async def refresh(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        cfg = await get_guild_config(guild.id)
        serverstats = cfg.get("serverstats", {})
        if not serverstats.get("category_id"):
            await interaction.followup.send(
                embed=error_embed(
                    "Not Configured",
                    "Server stats haven't been set up yet. Use `/serverstats setup` first.",
                ),
                ephemeral=True,
            )
            return

        updated = await self._push_stats(guild, serverstats)
        stats   = _collect_stats(guild)
        last    = self._last_updated.get(guild.id)

        embed = success_embed(
            "Stats Refreshed",
            f"**{updated}** channel(s) updated with the latest values.",
        )
        embed.add_field(
            name="Last Updated",
            value=discord.utils.format_dt(last, "T") if last else "Just now",
            inline=True,
        )
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.add_field(
            name="📈 Current Snapshot",
            value=(
                f"👥 Members · **{stats['members']}**\n"
                f"🟢 Online · **{stats['online']}**\n"
                f"🤖 Bots · **{stats['bots']}**\n"
                f"🔊 In Voice · **{stats['voice']}**\n"
                f"🚀 Boosts · **{stats['boosts']}**\n"
                f"📅 Created · **{stats['created']}**"
            ),
            inline=False,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /serverstats remove ───────────────────────────────────────────────────

    @stats_group.command(
        name="remove",
        description="Delete all stat channels and remove the configuration",
    )
    @is_admin()
    async def remove(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        cfg = await get_guild_config(guild.id)
        serverstats = cfg.get("serverstats", {})
        if not serverstats.get("category_id"):
            await interaction.followup.send(
                embed=error_embed("Not Configured", "No server stats setup found to remove."),
                ephemeral=True,
            )
            return

        deleted = 0
        errors  = 0

        # Delete individual stat channels first
        for ch_id in serverstats.get("channels", {}).values():
            ch = guild.get_channel(ch_id)
            if ch:
                try:
                    await ch.delete(reason=f"Server stats removed by {interaction.user}")
                    deleted += 1
                except Exception as exc:
                    logger.error(f"[serverstats] failed to delete channel {ch_id}: {exc}")
                    errors += 1

        # Delete the category (only if empty after channel deletes)
        cat = guild.get_channel(serverstats["category_id"])
        if cat:
            try:
                await cat.delete(reason=f"Server stats removed by {interaction.user}")
            except Exception as exc:
                logger.error(f"[serverstats] failed to delete category: {exc}")

        # Wipe from MongoDB
        await update_guild_config(guild.id, {"serverstats": {}})
        self._last_updated.pop(guild.id, None)

        desc = f"Deleted **{deleted}** stat channel(s) and the category."
        if errors:
            desc += f"\n⚠️ **{errors}** channel(s) could not be deleted — remove them manually."
        await interaction.followup.send(
            embed=success_embed("Server Stats Removed", desc),
            ephemeral=True,
        )

    # ── /serverstats settings ─────────────────────────────────────────────────

    @stats_group.command(
        name="settings",
        description="View the current server stats configuration and live snapshot",
    )
    @is_admin()
    async def settings(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        cfg = await get_guild_config(guild.id)
        serverstats = cfg.get("serverstats", {})

        if not serverstats.get("category_id"):
            embed = info_embed(
                "Server Stats — Not Configured",
                "Use `/serverstats setup` to create live stat channels that auto-update every 5 minutes.",
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        cat  = guild.get_channel(serverstats["category_id"])
        last = self._last_updated.get(guild.id)

        embed = info_embed("📊 Server Stats Settings", f"**{guild.name}**")
        embed.add_field(
            name="Category",
            value=cat.mention if cat else f"⚠️ Deleted (`{serverstats['category_id']}`)",
            inline=True,
        )
        embed.add_field(name="Update Interval", value="Every 5 minutes", inline=True)
        embed.add_field(
            name="Last Updated",
            value=discord.utils.format_dt(last, "R") if last else "Not yet updated this session",
            inline=True,
        )

        # Channel status table
        channels_map: dict[str, int] = serverstats.get("channels", {})
        channel_lines = []
        for key, _, label in STAT_CHANNELS:
            ch_id = channels_map.get(key)
            if ch_id:
                ch = guild.get_channel(ch_id)
                mention = ch.mention if ch else f"⚠️ Deleted (`{ch_id}`)"
                channel_lines.append(f"{label}: {mention}")
            else:
                channel_lines.append(f"{label}: ❌ Not created")
        embed.add_field(name="Channels", value="\n".join(channel_lines), inline=False)

        # Live snapshot
        stats = _collect_stats(guild)
        embed.add_field(
            name="📈 Live Snapshot",
            value=(
                f"👥 Members · **{stats['members']}**\n"
                f"🟢 Online · **{stats['online']}**\n"
                f"🤖 Bots · **{stats['bots']}**\n"
                f"🔊 In Voice · **{stats['voice']}**\n"
                f"🚀 Boosts · **{stats['boosts']}**\n"
                f"📅 Created · **{stats['created']}**"
            ),
            inline=False,
        )

        created_by_id = serverstats.get("created_by")
        if created_by_id:
            member = guild.get_member(created_by_id)
            embed.set_footer(text=f"Set up by {member.display_name if member else f'User {created_by_id}'}")

        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerStatsCog(bot))
