import discord
from discord import app_commands
from discord.ext import commands, tasks
import datetime
import logging
from database import Database, get_guild_config, update_guild_config
from utils import success_embed, error_embed, info_embed, primary_embed, is_admin

logger = logging.getLogger(__name__)


def _pct(value: int, total: int) -> str:
    if total <= 0:
        return "0%"
    return f"{round(value / total * 100, 1)}%"


def _bar(value: int, total: int, width: int = 16) -> str:
    if total <= 0:
        return "[" + " " * width + "]"
    filled = round((value / total) * width)
    return "[" + "█" * filled + "░" * (width - filled) + "]"


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

          # guild_id → datetime of last successful update this session
        self._last_updated: dict[int, datetime.datetime] = {}
        self.auto_update.start()
    def cog_unload(self):
        self.auto_update.cancel()
    # ─── Background task ───────────────────────────────────────────────────────
    @tasks.loop(minutes=5)
    async def auto_update(self):
        """Refresh every guild's stat channels every 5 minutes."""
        try:
             docs = await Database.db.guilds.find(
                {"serverstats.category_id": {"$exists": True, "$ne": None}}
            ).to_list(length=None)
        except Exception as exc:
            logger.error(f"serverstats auto_update: failed to query DB: {exc}")
            return
        for doc in docs:
            guild = self.bot.get_guild(doc["guild_id"])
            if guild is None:
                continue
            await self._push_stats(guild, doc.get("serverstats", {}))
    @auto_update.before_loop
    async def _before_auto_update(self):
        await self.bot.wait_until_ready()
    @auto_update.error
    async def _auto_update_error(self, error: Exception):
        logger.error(f"serverstats auto_update task crashed: {error}", exc_info=True)
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
            embed.add_field(name="⚠️ Failed Channels", value=", ".join(failed_keys), inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    stats_group = app_commands.Group(name="serverstats", description="Server statistics commands")

    @stats_group.command(name="summary", description="Display detailed statistics about this server")
    @app_commands.guild_only()
    async def serverstats(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send(embed=error_embed("Guild Required", "This command must be used in a server."), ephemeral=True)
            return

        total_members = guild.member_count
        bots = sum(1 for m in guild.members if m.bot)
        humans = total_members - bots
        online = sum(1 for m in guild.members if not m.bot and m.status != discord.Status.offline)
        boosts = guild.premium_subscription_count or 0
        boosters = [m for m in guild.members if m.premium_since]

        embed = primary_embed("📊 Server Statistics", f"**{guild.name}**")
        embed.add_field(name="Total Members", value=f"**{total_members:,}**", inline=True)
        embed.add_field(name="Humans", value=f"**{humans:,}**", inline=True)
        embed.add_field(name="Bots", value=f"**{bots:,}**", inline=True)
        embed.add_field(name="Online", value=f"**{online:,}**", inline=True)
        embed.add_field(name="Boosts", value=f"**{boosts:,}**", inline=True)

        if boosters:
            recent = sorted(boosters, key=lambda m: m.premium_since or datetime.datetime.utcnow(), reverse=True)[:10]
            names = "\n".join(
                f"**{m.display_name}** — since {discord.utils.format_dt(m.premium_since, 'D') if m.premium_since else 'Unknown'}"
                for m in recent
            )
            embed.add_field(name=f"🌟 Recent Boosters ({len(recent)})", value=names, inline=False)
        else:
            embed.add_field(name="🌟 Boosters", value="*No boosters yet. Be the first!*", inline=False)

        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        await interaction.followup.send(embed=embed)

    @stats_group.command(name="emojis", description="Emoji and sticker statistics")
    async def emojis(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send(embed=error_embed("Guild Required", "This command must be used in a server."), ephemeral=True)
            return

        emojis = guild.emojis
        stickers = guild.stickers
        animated = [e for e in emojis if e.animated]
        static = [e for e in emojis if not e.animated]

        embed = primary_embed("😀 Emoji & Sticker Statistics", f"**{guild.name}**")
        embed.add_field(name="Total Emojis", value=f"**{len(emojis)}/{guild.emoji_limit}**", inline=True)
        embed.add_field(name="Static", value=f"**{len(static)}**", inline=True)
        embed.add_field(name="Animated", value=f"**{len(animated)}**", inline=True)

        emoji_limit = guild.emoji_limit
        used_pct = _pct(len(emojis), emoji_limit)
        progress = _bar(len(emojis), emoji_limit)
        embed.add_field(name="Usage", value=f"`{progress}` {len(emojis)}/{emoji_limit} ({used_pct} used)", inline=False)
        embed.add_field(name="Stickers", value=f"**{len(stickers)}/{guild.sticker_limit}**", inline=True)
        embed.add_field(name="Slots Remaining", value=f"**{emoji_limit - len(emojis)}** emoji · **{guild.sticker_limit - len(stickers)}** sticker", inline=True)

        if emojis:
            sample = " ".join(str(e) for e in emojis[:20])
            embed.add_field(name="Sample Emojis", value=sample or "—", inline=False)

        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        await interaction.followup.send(embed=embed)

    @stats_group.command(name="growth", description="Recent joins — newest members of the server")
    async def growth(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send(embed=error_embed("Guild Required", "This command must be used in a server."), ephemeral=True)
            return

        members_sorted = sorted(
            [m for m in guild.members if not m.bot and m.joined_at],
            key=lambda m: m.joined_at,
            reverse=True,
        )

        now = datetime.datetime.now(datetime.timezone.utc)
        joined_24h = sum(1 for m in members_sorted if m.joined_at and (now - m.joined_at).days < 1)
        joined_7d = sum(1 for m in members_sorted if m.joined_at and (now - m.joined_at).days < 7)
        joined_30d = sum(1 for m in members_sorted if m.joined_at and (now - m.joined_at).days < 30)

        embed = primary_embed("📈 Server Growth", f"**{guild.name}**")
        embed.add_field(name="Joined in last 24h", value=f"**{joined_24h:,}**", inline=True)
        embed.add_field(name="Joined in last 7d", value=f"**{joined_7d:,}**", inline=True)
        embed.add_field(name="Joined in last 30d", value=f"**{joined_30d:,}**", inline=True)

        recent = members_sorted[:12]
        if recent:
            lines = [
                f"`{i+1:>2}.` **{m.display_name}** — {discord.utils.format_dt(m.joined_at, 'R') if m.joined_at else '?'}"
                for i, m in enumerate(recent)
            ]
            embed.add_field(name="Newest Members", value="\n".join(lines), inline=False)

        oldest = sorted(
            [m for m in guild.members if not m.bot and m.joined_at],
            key=lambda m: m.joined_at,
        )[:5]
        if oldest:
            lines = [
                f"`{i+1}.` **{m.display_name}** — {discord.utils.format_dt(m.joined_at, 'D') if m.joined_at else '?'}"
                for i, m in enumerate(oldest)
            ]
            embed.add_field(name="Original Members (OGs)", value="\n".join(lines), inline=False)

        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        await interaction.followup.send(embed=embed)

    @stats_group.command(name="activity", description="Live activity breakdown — what members are doing right now")
    async def activity(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send(embed=error_embed("Guild Required", "This command must be used in a server."), ephemeral=True)
            return

        humans = [m for m in guild.members if not m.bot]
        playing = [m for m in humans if any(isinstance(a, discord.Game) for a in m.activities)]
        streaming = [m for m in humans if any(isinstance(a, discord.Streaming) for a in m.activities)]
        listening = [m for m in humans if any(isinstance(a, discord.Spotify) for a in m.activities)]
        watching = [m for m in humans if any(isinstance(a, discord.Activity) and a.type == discord.ActivityType.watching for a in m.activities)]
        competing = [m for m in humans if any(isinstance(a, discord.Activity) and a.type == discord.ActivityType.competing for a in m.activities)]
        in_voice = [m for m in guild.members if m.voice is not None and not m.bot]

        total_humans = len(humans)
        embed = primary_embed("🎮 Live Activity", f"**{guild.name}** — {total_humans:,} human members")

        embed.add_field(name="Playing a Game", value=f"**{len(playing):,}** ({_pct(len(playing), total_humans)})", inline=True)
        embed.add_field(name="Listening to Spotify", value=f"**{len(listening):,}** ({_pct(len(listening), total_humans)})", inline=True)
        embed.add_field(name="Watching", value=f"**{len(watching):,}** ({_pct(len(watching), total_humans)})", inline=True)
        embed.add_field(name="Streaming", value=f"**{len(streaming):,}** ({_pct(len(streaming), total_humans)})", inline=True)
        embed.add_field(name="Competing", value=f"**{len(competing):,}** ({_pct(len(competing), total_humans)})", inline=True)
        embed.add_field(name="In Voice Channels", value=f"**{len(in_voice):,}** ({_pct(len(in_voice), total_humans)})", inline=True)

        if in_voice:
            vc_counts: dict[str, int] = {}
            for m in in_voice:
                if m.voice and m.voice.channel:
                    vc_counts[m.voice.channel.name] = vc_counts.get(m.voice.channel.name, 0) + 1
            top_vc = sorted(vc_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            lines = [f"**{name}** — {count} member(s)" for name, count in top_vc]
            embed.add_field(name="Most Populated Voice Channels", value="\n".join(lines), inline=False)

        if playing:
            game_counts: dict[str, int] = {}
            for m in playing:
                for a in m.activities:
                    if isinstance(a, discord.Game):
                        game_counts[a.name] = game_counts.get(a.name, 0) + 1
            top_games = sorted(game_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            lines = [f"**{name}** — {count} player(s)" for name, count in top_games]
            embed.add_field(name="Most Played Games", value="\n".join(lines), inline=False)

        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        embed.set_footer(text="Snapshot taken at command invocation · Updates on next use")
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerStatsCog(bot))
