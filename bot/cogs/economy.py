import discord
from discord import app_commands
from discord.ext import commands
import datetime
import random
import logging
from database import Database, get_guild_config
from utils import success_embed, error_embed, info_embed, primary_embed, warning_embed
from config import config

logger = logging.getLogger(__name__)

WORK_JOBS = [
    ("Software Engineer", "wrote some code"),
    ("Chef", "cooked a delicious meal"),
    ("Artist", "painted a masterpiece"),
    ("Driver", "delivered packages"),
    ("Teacher", "gave an amazing lesson"),
    ("Doctor", "treated patients"),
    ("Musician", "performed on stage"),
    ("Writer", "finished a chapter"),
    ("Mechanic", "fixed some engines"),
    ("Streamer", "went live and got donations"),
]


async def get_balance(guild_id: int, user_id: int) -> dict:
    doc = await Database.db.economy.find_one({"guild_id": guild_id, "user_id": user_id})
    if not doc:
        doc = {"guild_id": guild_id, "user_id": user_id, "wallet": config.STARTING_BALANCE, "bank": 0, "last_daily": None, "last_work": None}
        await Database.db.economy.insert_one(doc)
    return doc


async def update_balance(guild_id: int, user_id: int, wallet_delta: int = 0, bank_delta: int = 0):
    await Database.db.economy.update_one(
        {"guild_id": guild_id, "user_id": user_id},
        {"$inc": {"wallet": wallet_delta, "bank": bank_delta}},
        upsert=True,
    )


class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    economy_group = app_commands.Group(name="economy", description="Economy commands")

    @economy_group.command(name="balance", description="Check your or another member's balance")
    @app_commands.describe(member="Member to check balance for")
    async def balance(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        data = await get_balance(interaction.guild_id, target.id)
        wallet = data.get("wallet", 0)
        bank = data.get("bank", 0)
        total = wallet + bank
        embed = primary_embed(f"💰 {target.display_name}'s Balance")
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="👛 Wallet", value=f"**{wallet:,}** coins", inline=True)
        embed.add_field(name="🏦 Bank", value=f"**{bank:,}** coins", inline=True)
        embed.add_field(name="💎 Total", value=f"**{total:,}** coins", inline=True)
        await interaction.response.send_message(embed=embed)

    @economy_group.command(name="daily", description="Claim your daily reward")
    async def daily(self, interaction: discord.Interaction):
        data = await get_balance(interaction.guild_id, interaction.user.id)
        last_daily = data.get("last_daily")
        now = datetime.datetime.utcnow()
        if last_daily:
            elapsed = (now - last_daily).total_seconds()
            if elapsed < 86400:
                remaining = 86400 - elapsed
                hours, rem = divmod(int(remaining), 3600)
                minutes = rem // 60
                await interaction.response.send_message(
                    embed=warning_embed("Daily Cooldown", f"You already claimed your daily!\nCome back in **{hours}h {minutes}m**."),
                    ephemeral=True,
                )
                return

        amount = config.DAILY_AMOUNT
        # Streak bonus
        if last_daily and (now - last_daily).total_seconds() < 172800:
            streak = data.get("daily_streak", 0) + 1
            bonus = streak * 25
            amount += bonus
        else:
            streak = 1

        await Database.db.economy.update_one(
            {"guild_id": interaction.guild_id, "user_id": interaction.user.id},
            {"$inc": {"wallet": amount}, "$set": {"last_daily": now, "daily_streak": streak}},
            upsert=True,
        )
        embed = success_embed("Daily Reward Claimed!", f"You received **{amount:,}** coins!")
        embed.add_field(name="Streak", value=f"🔥 {streak} day{'s' if streak != 1 else ''}", inline=True)
        embed.add_field(name="New Balance", value=f"**{data.get('wallet', 0) + amount:,}** coins", inline=True)
        await interaction.response.send_message(embed=embed)

    @economy_group.command(name="work", description="Work to earn coins")
    async def work(self, interaction: discord.Interaction):
        data = await get_balance(interaction.guild_id, interaction.user.id)
        last_work = data.get("last_work")
        now = datetime.datetime.utcnow()
        cooldown = 3600  # 1 hour
        if last_work and (now - last_work).total_seconds() < cooldown:
            remaining = cooldown - (now - last_work).total_seconds()
            minutes = int(remaining // 60)
            seconds = int(remaining % 60)
            await interaction.response.send_message(
                embed=warning_embed("Work Cooldown", f"You're tired! Rest for **{minutes}m {seconds}s** more."),
                ephemeral=True,
            )
            return

        job, action = random.choice(WORK_JOBS)
        amount = random.randint(config.WORK_MIN, config.WORK_MAX)
        await Database.db.economy.update_one(
            {"guild_id": interaction.guild_id, "user_id": interaction.user.id},
            {"$inc": {"wallet": amount}, "$set": {"last_work": now}},
            upsert=True,
        )
        embed = success_embed("Work Complete!", f"You worked as a **{job}** and {action}.\nYou earned **{amount:,}** coins!")
        await interaction.response.send_message(embed=embed)

    @economy_group.command(name="deposit", description="Deposit coins from your wallet to your bank")
    @app_commands.describe(amount="Amount to deposit (or 'all')")
    async def deposit(self, interaction: discord.Interaction, amount: str):
        data = await get_balance(interaction.guild_id, interaction.user.id)
        wallet = data.get("wallet", 0)

        if amount.lower() == "all":
            dep_amount = wallet
        else:
            try:
                dep_amount = int(amount)
            except ValueError:
                await interaction.response.send_message(embed=error_embed("Invalid Amount", "Please enter a number or 'all'."), ephemeral=True)
                return

        if dep_amount <= 0:
            await interaction.response.send_message(embed=error_embed("Invalid Amount", "Amount must be positive."), ephemeral=True)
            return
        if dep_amount > wallet:
            await interaction.response.send_message(embed=error_embed("Insufficient Funds", f"You only have **{wallet:,}** coins in your wallet."), ephemeral=True)
            return

        await update_balance(interaction.guild_id, interaction.user.id, wallet_delta=-dep_amount, bank_delta=dep_amount)
        embed = success_embed("Deposited!", f"Deposited **{dep_amount:,}** coins to your bank.")
        embed.add_field(name="Wallet", value=f"{wallet - dep_amount:,}", inline=True)
        embed.add_field(name="Bank", value=f"{data.get('bank', 0) + dep_amount:,}", inline=True)
        await interaction.response.send_message(embed=embed)

    @economy_group.command(name="withdraw", description="Withdraw coins from your bank to your wallet")
    @app_commands.describe(amount="Amount to withdraw (or 'all')")
    async def withdraw(self, interaction: discord.Interaction, amount: str):
        data = await get_balance(interaction.guild_id, interaction.user.id)
        bank = data.get("bank", 0)

        if amount.lower() == "all":
            with_amount = bank
        else:
            try:
                with_amount = int(amount)
            except ValueError:
                await interaction.response.send_message(embed=error_embed("Invalid Amount", "Please enter a number or 'all'."), ephemeral=True)
                return

        if with_amount <= 0:
            await interaction.response.send_message(embed=error_embed("Invalid Amount", "Amount must be positive."), ephemeral=True)
            return
        if with_amount > bank:
            await interaction.response.send_message(embed=error_embed("Insufficient Funds", f"You only have **{bank:,}** coins in your bank."), ephemeral=True)
            return

        await update_balance(interaction.guild_id, interaction.user.id, wallet_delta=with_amount, bank_delta=-with_amount)
        embed = success_embed("Withdrawn!", f"Withdrew **{with_amount:,}** coins to your wallet.")
        embed.add_field(name="Wallet", value=f"{data.get('wallet', 0) + with_amount:,}", inline=True)
        embed.add_field(name="Bank", value=f"{bank - with_amount:,}", inline=True)
        await interaction.response.send_message(embed=embed)

    @economy_group.command(name="pay", description="Send coins to another member")
    @app_commands.describe(member="Member to pay", amount="Amount to send")
    async def pay(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if member.id == interaction.user.id:
            await interaction.response.send_message(embed=error_embed("Invalid", "You can't pay yourself."), ephemeral=True)
            return
        if member.bot:
            await interaction.response.send_message(embed=error_embed("Invalid", "You can't pay bots."), ephemeral=True)
            return
        if amount <= 0:
            await interaction.response.send_message(embed=error_embed("Invalid Amount", "Amount must be positive."), ephemeral=True)
            return

        data = await get_balance(interaction.guild_id, interaction.user.id)
        if data.get("wallet", 0) < amount:
            await interaction.response.send_message(embed=error_embed("Insufficient Funds", f"You only have **{data.get('wallet', 0):,}** coins."), ephemeral=True)
            return

        await update_balance(interaction.guild_id, interaction.user.id, wallet_delta=-amount)
        await update_balance(interaction.guild_id, member.id, wallet_delta=amount)
        await interaction.response.send_message(embed=success_embed("Payment Sent!", f"Sent **{amount:,}** coins to {member.mention}."))

    @economy_group.command(name="leaderboard", description="View the server economy leaderboard")
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cursor = Database.db.economy.find({"guild_id": interaction.guild_id}).sort([("wallet", -1), ("bank", -1)]).limit(10)
        entries = await cursor.to_list(10)

        embed = primary_embed("💰 Economy Leaderboard", f"**{interaction.guild.name}**")
        medals = ["🥇", "🥈", "🥉"]
        for i, entry in enumerate(entries):
            member = interaction.guild.get_member(entry["user_id"])
            name = member.display_name if member else f"Unknown ({entry['user_id']})"
            total = entry.get("wallet", 0) + entry.get("bank", 0)
            medal = medals[i] if i < 3 else f"{i+1}."
            embed.add_field(
                name=f"{medal} {name}",
                value=f"**{total:,}** coins (💼 {entry.get('wallet',0):,} | 🏦 {entry.get('bank',0):,})",
                inline=False,
            )
        if not entries:
            embed.description = "No economy data yet!"
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Economy(bot))
