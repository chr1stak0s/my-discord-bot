import discord
from discord import app_commands
from discord.ext import commands
import datetime
import logging
from utils import primary_embed, error_embed

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


class ServerStats(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

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
    await bot.add_cog(ServerStats(bot))
