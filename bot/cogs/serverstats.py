import discord
from discord import app_commands
from discord.ext import commands
import datetime
import logging
from utils import primary_embed, info_embed, error_embed

logger = logging.getLogger(__name__)


def _bar(value: int, total: int, length: int = 10) -> str:
    if total == 0:
        filled = 0
    else:
        filled = round((value / total) * length)
    return "█" * filled + "░" * (length - filled)


def _pct(value: int, total: int) -> str:
    if total == 0:
        return "0%"
    return f"{value / total * 100:.1f}%"


class ServerStats(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    stats_group = app_commands.Group(name="serverstats", description="Server statistics commands")

    # ─── /serverstats overview ────────────────────────────────────────────────

    @stats_group.command(name="overview", description="Full overview of the server")
    async def overview(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild

        bots = sum(1 for m in guild.members if m.bot)
        humans = guild.member_count - bots
        online = sum(1 for m in guild.members if m.status != discord.Status.offline and not m.bot)
        text_ch = len(guild.text_channels)
        voice_ch = len(guild.voice_channels)
        categories = len(guild.categories)
        stage_ch = len(guild.stage_channels)
        forum_ch = len(guild.forums)
        total_ch = text_ch + voice_ch + stage_ch + forum_ch

        embed = primary_embed(f"📊 {guild.name} — Overview")
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        if guild.banner:
            embed.set_image(url=guild.banner.url)

        embed.add_field(name="👑 Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=True)
        embed.add_field(name="🆔 Server ID", value=str(guild.id), inline=True)
        embed.add_field(name="📅 Created", value=discord.utils.format_dt(guild.created_at, "D"), inline=True)

        embed.add_field(name="👥 Members", value=f"{guild.member_count:,}", inline=True)
        embed.add_field(name="🟢 Online", value=f"{online:,} humans", inline=True)
        embed.add_field(name="🤖 Bots", value=f"{bots:,}", inline=True)

        embed.add_field(name="💬 Channels", value=f"{total_ch:,} ({text_ch} text · {voice_ch} voice)", inline=True)
        embed.add_field(name="🗂️ Categories", value=str(categories), inline=True)
        embed.add_field(name="🎭 Roles", value=str(len(guild.roles) - 1), inline=True)

        embed.add_field(
            name="✨ Boost Status",
            value=f"Level {guild.premium_tier} · {guild.premium_subscription_count} boost(s)",
            inline=True,
        )
        embed.add_field(name="😀 Emojis", value=f"{len(guild.emojis)}/{guild.emoji_limit}", inline=True)
        embed.add_field(name="🔒 Verification", value=str(guild.verification_level).replace("_", " ").title(), inline=True)

        if guild.description:
            embed.add_field(name="📝 Description", value=guild.description, inline=False)

        embed.set_footer(text=f"Region: {str(guild.preferred_locale)} · {len(guild.features)} features enabled")
        await interaction.followup.send(embed=embed)

    # ─── /serverstats members ─────────────────────────────────────────────────

    @stats_group.command(name="members", description="Detailed member count breakdown")
    async def members(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild

        total = guild.member_count
        bots = sum(1 for m in guild.members if m.bot)
        humans = total - bots

        online  = sum(1 for m in guild.members if not m.bot and m.status == discord.Status.online)
        idle    = sum(1 for m in guild.members if not m.bot and m.status == discord.Status.idle)
        dnd     = sum(1 for m in guild.members if not m.bot and m.status == discord.Status.do_not_disturb)
        offline = sum(1 for m in guild.members if not m.bot and m.status == discord.Status.offline)

        embed = info_embed("👥 Member Statistics", f"**{guild.name}**")

        embed.add_field(name="Total Members", value=f"**{total:,}**", inline=True)
        embed.add_field(name="Humans", value=f"**{humans:,}** ({_pct(humans, total)})", inline=True)
        embed.add_field(name="Bots", value=f"**{bots:,}** ({_pct(bots, total)})", inline=True)

        embed.add_field(name="\u200b", value="**── Status Breakdown (humans) ──**", inline=False)
        embed.add_field(
            name="🟢 Online",
            value=f"**{online:,}** ({_pct(online, humans)})\n`{_bar(online, humans)}`",
            inline=True,
        )
        embed.add_field(
            name="🟡 Idle",
            value=f"**{idle:,}** ({_pct(idle, humans)})\n`{_bar(idle, humans)}`",
            inline=True,
        )
        embed.add_field(
            name="🔴 Do Not Disturb",
            value=f"**{dnd:,}** ({_pct(dnd, humans)})\n`{_bar(dnd, humans)}`",
            inline=True,
        )
        embed.add_field(
            name="⚫ Offline",
            value=f"**{offline:,}** ({_pct(offline, humans)})\n`{_bar(offline, humans)}`",
            inline=True,
        )

        active = online + idle + dnd
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.add_field(
            name="📶 Active Right Now",
            value=f"**{active:,}** of **{humans:,}** humans ({_pct(active, humans)})",
            inline=True,
        )

        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        await interaction.followup.send(embed=embed)

    # ─── /serverstats channels ────────────────────────────────────────────────

    @stats_group.command(name="channels", description="Breakdown of all server channels")
    async def channels(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild

        text    = len(guild.text_channels)
        voice   = len(guild.voice_channels)
        cats    = len(guild.categories)
        stage   = len(guild.stage_channels)
        forums  = len(guild.forums)
        threads = len([t for t in guild.threads])
        total   = text + voice + stage + forums

        embed = info_embed("💬 Channel Statistics", f"**{guild.name}**")

        embed.add_field(name="Total Channels", value=f"**{total:,}**", inline=True)
        embed.add_field(name="🗂️ Categories", value=f"**{cats:,}**", inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)

        embed.add_field(name="💬 Text Channels", value=f"**{text:,}** ({_pct(text, total)})\n`{_bar(text, total)}`", inline=True)
        embed.add_field(name="🔊 Voice Channels", value=f"**{voice:,}** ({_pct(voice, total)})\n`{_bar(voice, total)}`", inline=True)
        embed.add_field(name="🎭 Stage Channels", value=f"**{stage:,}**", inline=True)

        embed.add_field(name="🗣️ Forum Channels", value=f"**{forums:,}**", inline=True)
        embed.add_field(name="🧵 Active Threads", value=f"**{threads:,}**", inline=True)

        news = sum(1 for c in guild.text_channels if c.is_news())
        nsfw = sum(1 for c in guild.text_channels if c.is_nsfw())
        embed.add_field(name="📢 Announcement", value=f"**{news:,}**", inline=True)

        if nsfw:
            embed.add_field(name="🔞 NSFW", value=f"**{nsfw:,}**", inline=True)

        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        await interaction.followup.send(embed=embed)

    # ─── /serverstats roles ───────────────────────────────────────────────────

    @stats_group.command(name="roles", description="List all roles with member counts")
    async def roles(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild

        roles = [r for r in guild.roles if r != guild.default_role]
        roles_sorted = sorted(roles, key=lambda r: len(r.members), reverse=True)
        total_members = guild.member_count

        embed = info_embed("🎭 Role Statistics", f"**{guild.name}** — {len(roles)} role(s)")

        top = roles_sorted[:15]
        lines = []
        for i, role in enumerate(top, 1):
            count = len(role.members)
            bar = _bar(count, total_members, 8)
            lines.append(f"`{i:>2}.` {role.mention} — **{count:,}** ({_pct(count, total_members)}) `{bar}`")

        if lines:
            embed.add_field(name="Top Roles by Members", value="\n".join(lines), inline=False)

        hoisted = sum(1 for r in roles if r.hoist)
        mentionable = sum(1 for r in roles if r.mentionable)
        managed = sum(1 for r in roles if r.managed)
        colored = sum(1 for r in roles if r.color.value != 0)

        embed.add_field(name="📌 Hoisted", value=str(hoisted), inline=True)
        embed.add_field(name="📣 Mentionable", value=str(mentionable), inline=True)
        embed.add_field(name="🤖 Managed (Bot)", value=str(managed), inline=True)
        embed.add_field(name="🎨 Colored", value=str(colored), inline=True)

        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        if len(roles) > 15:
            embed.set_footer(text=f"Showing top 15 of {len(roles)} roles by member count")
        await interaction.followup.send(embed=embed)

    # ─── /serverstats boosts ──────────────────────────────────────────────────

    @stats_group.command(name="boosts", description="Server boost statistics and boosters list")
    async def boosts(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild

        tier = guild.premium_tier
        count = guild.premium_subscription_count or 0
        boosters = guild.premium_subscribers

        tier_goals = {0: 2, 1: 15, 2: 30}
        next_goal = tier_goals.get(tier, None)

        embed = info_embed("✨ Boost Statistics", f"**{guild.name}**")

        tier_names = {0: "No Level", 1: "Level 1", 2: "Level 2", 3: "Level 3"}
        embed.add_field(name="🏆 Boost Level", value=tier_names.get(tier, f"Level {tier}"), inline=True)
        embed.add_field(name="⚡ Total Boosts", value=f"**{count:,}**", inline=True)
        embed.add_field(name="👥 Boosters", value=f"**{len(boosters):,}**", inline=True)

        if next_goal and tier < 3:
            remaining = max(0, next_goal - count)
            progress = _bar(count, next_goal)
            embed.add_field(
                name=f"📈 Progress to Level {tier + 1}",
                value=f"`{progress}` {count}/{next_goal} — **{remaining}** more needed",
                inline=False,
            )

        tier_perks = {
            0: "— No perks yet. Boost to unlock Level 1!",
            1: "✅ Custom invite splash\n✅ 50 animated emojis\n✅ 128kbps audio quality",
            2: "✅ Custom server banner\n✅ 150 animated emojis\n✅ 256kbps audio quality\n✅ 50MB upload limit",
            3: "✅ Custom vanity URL\n✅ 250 animated emojis\n✅ 384kbps audio quality\n✅ 100MB upload limit",
        }
        embed.add_field(name="🎁 Current Perks", value=tier_perks.get(tier, "—"), inline=False)

        if boosters:
            recent = sorted(boosters, key=lambda m: m.premium_since or datetime.datetime.utcnow(), reverse=True)[:10]
            names = "\n".join(
                f"**{m.display_name}** — since {discord.utils.format_dt(m.premium_since, 'D') if m.premium_since else 'Unknown'}"
                for m in recent
            )
            embed.add_field(name=f"🌟 Recent Boosters (last {len(recent)})", value=names, inline=False)
        else:
            embed.add_field(name="🌟 Boosters", value="*No boosters yet. Be the first!*", inline=False)

        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        await interaction.followup.send(embed=embed)

    # ─── /serverstats emojis ──────────────────────────────────────────────────

    @stats_group.command(name="emojis", description="Emoji and sticker statistics")
    async def emojis(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild

        emojis = guild.emojis
        stickers = guild.stickers
        animated = [e for e in emojis if e.animated]
        static = [e for e in emojis if not e.animated]

        embed = info_embed("😀 Emoji & Sticker Statistics", f"**{guild.name}**")

        embed.add_field(name="Total Emojis", value=f"**{len(emojis)}/{guild.emoji_limit}**", inline=True)
        embed.add_field(name="🖼️ Static", value=f"**{len(static)}**", inline=True)
        embed.add_field(name="🎞️ Animated", value=f"**{len(animated)}**", inline=True)

        emoji_limit = guild.emoji_limit
        used_pct = _pct(len(emojis), emoji_limit)
        progress = _bar(len(emojis), emoji_limit)
        embed.add_field(
            name="📊 Usage",
            value=f"`{progress}` {len(emojis)}/{emoji_limit} ({used_pct} used)",
            inline=False,
        )

        embed.add_field(name="🎭 Stickers", value=f"**{len(stickers)}/{guild.sticker_limit}**", inline=True)
        embed.add_field(name="Slots Remaining", value=f"**{emoji_limit - len(emojis)}** emoji · **{guild.sticker_limit - len(stickers)}** sticker", inline=True)

        if emojis:
            sample = " ".join(str(e) for e in list(emojis)[:20])
            embed.add_field(name="Sample Emojis", value=sample or "—", inline=False)

        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        await interaction.followup.send(embed=embed)

    # ─── /serverstats growth ──────────────────────────────────────────────────

    @stats_group.command(name="growth", description="Recent joins — newest members of the server")
    async def growth(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild

        members_sorted = sorted(
            [m for m in guild.members if not m.bot and m.joined_at],
            key=lambda m: m.joined_at,
            reverse=True,
        )

        now = datetime.datetime.now(datetime.timezone.utc)
        joined_24h  = sum(1 for m in members_sorted if m.joined_at and (now - m.joined_at).days < 1)
        joined_7d   = sum(1 for m in members_sorted if m.joined_at and (now - m.joined_at).days < 7)
        joined_30d  = sum(1 for m in members_sorted if m.joined_at and (now - m.joined_at).days < 30)

        embed = info_embed("📈 Server Growth", f"**{guild.name}**")
        embed.add_field(name="Joined in last 24h", value=f"**{joined_24h:,}**", inline=True)
        embed.add_field(name="Joined in last 7d", value=f"**{joined_7d:,}**", inline=True)
        embed.add_field(name="Joined in last 30d", value=f"**{joined_30d:,}**", inline=True)

        recent = members_sorted[:12]
        if recent:
            lines = [
                f"`{i+1:>2}.` **{m.display_name}** — {discord.utils.format_dt(m.joined_at, 'R') if m.joined_at else '?'}"
                for i, m in enumerate(recent)
            ]
            embed.add_field(name="🆕 Newest Members", value="\n".join(lines), inline=False)

        oldest = sorted(
            [m for m in guild.members if not m.bot and m.joined_at],
            key=lambda m: m.joined_at,
        )[:5]
        if oldest:
            lines = [
                f"`{i+1}.` **{m.display_name}** — {discord.utils.format_dt(m.joined_at, 'D') if m.joined_at else '?'}"
                for i, m in enumerate(oldest)
            ]
            embed.add_field(name="🏅 Original Members (OGs)", value="\n".join(lines), inline=False)

        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        await interaction.followup.send(embed=embed)

    # ─── /serverstats activity ────────────────────────────────────────────────

    @stats_group.command(name="activity", description="Live activity breakdown — what members are doing right now")
    async def activity(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild

        humans = [m for m in guild.members if not m.bot]

        playing   = [m for m in humans if any(isinstance(a, discord.Game) for a in m.activities)]
        streaming = [m for m in humans if any(isinstance(a, discord.Streaming) for a in m.activities)]
        listening = [m for m in humans if any(isinstance(a, discord.Spotify) for a in m.activities)]
        watching  = [m for m in humans if any(isinstance(a, discord.Activity) and a.type == discord.ActivityType.watching for a in m.activities)]
        competing = [m for m in humans if any(isinstance(a, discord.Activity) and a.type == discord.ActivityType.competing for a in m.activities)]
        in_voice  = [m for m in guild.members if m.voice is not None and not m.bot]

        total_humans = len(humans)

        embed = info_embed("🎮 Live Activity", f"**{guild.name}** — {total_humans:,} human members")

        embed.add_field(
            name="🎮 Playing a Game",
            value=f"**{len(playing):,}** ({_pct(len(playing), total_humans)})",
            inline=True,
        )
        embed.add_field(
            name="🎵 Listening to Spotify",
            value=f"**{len(listening):,}** ({_pct(len(listening), total_humans)})",
            inline=True,
        )
        embed.add_field(
            name="📺 Watching",
            value=f"**{len(watching):,}** ({_pct(len(watching), total_humans)})",
            inline=True,
        )
        embed.add_field(
            name="📡 Streaming",
            value=f"**{len(streaming):,}** ({_pct(len(streaming), total_humans)})",
            inline=True,
        )
        embed.add_field(
            name="🏆 Competing",
            value=f"**{len(competing):,}** ({_pct(len(competing), total_humans)})",
            inline=True,
        )
        embed.add_field(
            name="🔊 In Voice Channels",
            value=f"**{len(in_voice):,}** ({_pct(len(in_voice), total_humans)})",
            inline=True,
        )

        if in_voice:
            vc_counts: dict[str, int] = {}
            for m in in_voice:
                if m.voice and m.voice.channel:
                    vc_counts[m.voice.channel.name] = vc_counts.get(m.voice.channel.name, 0) + 1
            top_vc = sorted(vc_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            lines = [f"🔊 **{name}** — {count} member(s)" for name, count in top_vc]
            embed.add_field(name="Most Populated Voice Channels", value="\n".join(lines), inline=False)

        if playing:
            game_counts: dict[str, int] = {}
            for m in playing:
                for a in m.activities:
                    if isinstance(a, discord.Game):
                        game_counts[a.name] = game_counts.get(a.name, 0) + 1
            top_games = sorted(game_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            lines = [f"🎮 **{name}** — {count} player(s)" for name, count in top_games]
            embed.add_field(name="Most Played Games", value="\n".join(lines), inline=False)

        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        embed.set_footer(text="Snapshot taken at command invocation · Updates on next use")
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerStats(bot))
