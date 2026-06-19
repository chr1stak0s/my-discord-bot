import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import logging
from utils import success_embed, error_embed, info_embed, primary_embed, is_admin

logger = logging.getLogger(__name__)


class DM(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="dm", description="Send a direct message to a specific server member (admin only)")
    @app_commands.describe(
        member="The member to DM",
        message="The message to send",
    )
    @is_admin()
    async def dm(self, interaction: discord.Interaction, member: discord.Member, message: str):
        await interaction.response.defer(ephemeral=True)

        embed = discord.Embed(
            title=f"📩 Message from {interaction.guild.name}",
            description=message,
            color=0x5865F2,
        )
        embed.set_footer(text=f"Sent by {interaction.user.display_name} • {interaction.guild.name}")
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)

        try:
            await member.send(embed=embed)
            result = success_embed("DM Sent", f"Your message was sent to {member.mention}.")
            result.add_field(name="Recipient", value=f"{member} ({member.id})", inline=True)
            result.add_field(name="Preview", value=message[:200], inline=False)
            await interaction.followup.send(embed=result, ephemeral=True)
            logger.info(f"{interaction.user} sent DM to {member} in {interaction.guild.name}")
        except discord.Forbidden:
            await interaction.followup.send(
                embed=error_embed("DM Failed", f"{member.mention} has DMs disabled or has blocked the bot."),
                ephemeral=True,
            )
        except discord.HTTPException as e:
            await interaction.followup.send(
                embed=error_embed("DM Failed", f"An error occurred: {e}"),
                ephemeral=True,
            )

    @app_commands.command(name="dmall", description="Send a DM to all server members (admin only, requires confirmation)")
    @app_commands.describe(
        message="The message to broadcast to all members",
        include_bots="Also send to bots (default: No)",
        role="Only DM members with this role (leave empty for everyone)",
    )
    @is_admin()
    async def dmall(
        self,
        interaction: discord.Interaction,
        message: str,
        role: discord.Role = None,
        include_bots: bool = False,
    ):
        await interaction.response.defer(ephemeral=True)

        if role:
            members = [m for m in role.members if (not m.bot or include_bots) and m.id != self.bot.user.id]
            target_label = f"members with **@{role.name}**"
        else:
            members = [m for m in interaction.guild.members if (not m.bot or include_bots) and m.id != self.bot.user.id]
            target_label = "**all members**"

        if not members:
            await interaction.followup.send(embed=error_embed("No Recipients", "No members matched the selected criteria."), ephemeral=True)
            return

        confirm_embed = discord.Embed(
            title="⚠️ Mass DM Confirmation",
            description=(
                f"You are about to DM {target_label} — **{len(members)} member(s)**.\n\n"
                f"**Message preview:**\n>>> {message[:400]}\n\n"
                "⚠️ This **cannot be undone**. Proceed?"
            ),
            color=0xF39C12,
        )
        confirm_embed.add_field(name="Estimated time", value=f"~{len(members)} seconds (rate-limited)", inline=True)

        from views.confirm import ConfirmView
        view = ConfirmView(interaction.user.id, timeout=60.0)
        await interaction.followup.send(embed=confirm_embed, view=view, ephemeral=True)
        await view.wait()

        if not view.value:
            await interaction.edit_original_response(
                embed=info_embed("Cancelled", "Mass DM was cancelled."),
                view=None,
            )
            return

        await interaction.edit_original_response(
            embed=primary_embed(
                "📨 Sending DMs...",
                f"Sending to **{len(members)} member(s)**. Please wait — this may take a while.",
            ),
            view=None,
        )

        dm_embed = discord.Embed(
            title=f"📩 Message from {interaction.guild.name}",
            description=message,
            color=0x5865F2,
        )
        dm_embed.set_footer(text=f"Sent by {interaction.user.display_name} • {interaction.guild.name}")
        if interaction.guild.icon:
            dm_embed.set_thumbnail(url=interaction.guild.icon.url)

        sent = 0
        failed = 0
        for member in members:
            try:
                await member.send(embed=dm_embed)
                sent += 1
            except (discord.Forbidden, discord.HTTPException):
                failed += 1
            await asyncio.sleep(1.0)

        result = success_embed(
            "📨 Mass DM Complete",
            f"✅ **Sent:** {sent}\n❌ **Failed (DMs closed):** {failed}\n👥 **Total attempted:** {len(members)}",
        )
        if role:
            result.add_field(name="Role", value=role.mention, inline=True)
        await interaction.edit_original_response(embed=result, view=None)
        logger.info(
            f"Mass DM by {interaction.user} in {interaction.guild.name}: "
            f"sent={sent}, failed={failed}, total={len(members)}"
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(DM(bot))
