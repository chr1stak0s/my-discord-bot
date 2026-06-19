import discord
import datetime
import humanize
from config import config


def success_embed(title: str, description: str = None, **kwargs) -> discord.Embed:
    embed = discord.Embed(
        title=f"✅ {title}",
        description=description,
        color=config.COLOR_SUCCESS,
        timestamp=datetime.datetime.utcnow(),
        **kwargs,
    )
    return embed


def error_embed(title: str, description: str = None, **kwargs) -> discord.Embed:
    embed = discord.Embed(
        title=f"❌ {title}",
        description=description,
        color=config.COLOR_ERROR,
        timestamp=datetime.datetime.utcnow(),
        **kwargs,
    )
    return embed


def warning_embed(title: str, description: str = None, **kwargs) -> discord.Embed:
    embed = discord.Embed(
        title=f"⚠️ {title}",
        description=description,
        color=config.COLOR_WARNING,
        timestamp=datetime.datetime.utcnow(),
        **kwargs,
    )
    return embed


def info_embed(title: str, description: str = None, **kwargs) -> discord.Embed:
    embed = discord.Embed(
        title=f"ℹ️ {title}",
        description=description,
        color=config.COLOR_INFO,
        timestamp=datetime.datetime.utcnow(),
        **kwargs,
    )
    return embed


def primary_embed(title: str, description: str = None, **kwargs) -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description,
        color=config.COLOR_PRIMARY,
        timestamp=datetime.datetime.utcnow(),
        **kwargs,
    )
    return embed


def format_dt(dt: datetime.datetime, style: str = "F") -> str:
    return discord.utils.format_dt(dt, style=style)


def relative_time(dt: datetime.datetime) -> str:
    return humanize.naturaltime(datetime.datetime.utcnow() - dt)


def truncate(text: str, max_len: int = 1024) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


def paginate(items: list, page: int, per_page: int = 10) -> tuple[list, int]:
    total_pages = max(1, (len(items) + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    return items[start:start + per_page], total_pages


def ordinal(n: int) -> str:
    suffix = ["th", "st", "nd", "rd"]
    val = n % 100
    return f"{n}{suffix[val - 20 if 3 < val < 20 else val % 10 if val % 10 < 4 else 0]}"


def calculate_level(xp: int) -> int:
    level = 0
    while xp >= xp_for_level(level + 1):
        xp -= xp_for_level(level + 1)
        level += 1
    return level


def xp_for_level(level: int) -> int:
    return int(100 * (level ** 1.5) * config.LEVEL_MULTIPLIER)


def xp_progress(xp: int) -> tuple[int, int, int]:
    level = 0
    remaining = xp
    while remaining >= xp_for_level(level + 1):
        remaining -= xp_for_level(level + 1)
        level += 1
    return level, remaining, xp_for_level(level + 1)


async def get_or_fetch_member(guild: discord.Guild, user_id: int) -> discord.Member | None:
    member = guild.get_member(user_id)
    if not member:
        try:
            member = await guild.fetch_member(user_id)
        except discord.NotFound:
            return None
    return member


async def send_dm(user: discord.User, embed: discord.Embed) -> bool:
    try:
        await user.send(embed=embed)
        return True
    except (discord.Forbidden, discord.HTTPException):
        return False
