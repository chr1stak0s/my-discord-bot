import discord
from discord import app_commands
from discord.ext import commands
import datetime
import logging
from database import Database, get_guild_config, update_guild_config
from utils import success_embed, error_embed, info_embed, primary_embed, is_admin, is_ticket_staff
from views.tickets import TicketPanelView, TicketControlView

logger = logging.getLogger(__name__)


class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    ticket_group = app_commands.Group(name="tickets", description="Ticket system commands")

    @ticket_group.command(name="setup", description="Setup the ticket system")
    @app_commands.describe(
        category="Category to create tickets in",
        log_channel="Channel for ticket logs",
        staff_role="Role for ticket staff",
    )
    @is_admin()
    async def setup(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel = None,
        log_channel: discord.TextChannel = None,
        staff_role: discord.Role = None,
    ):
        await interaction.response.defer(ephemeral=True)
        updates = {}
        if category:
            updates["ticket_category_id"] = category.id
        if log_channel:
            updates["ticket_log_channel_id"] = log_channel.id
        if staff_role:
            cfg = await get_guild_config(interaction.guild_id)
            staff_roles = cfg.get("ticket_staff_roles", [])
            if staff_role.id not in staff_roles:
                staff_roles.append(staff_role.id)
            updates["ticket_staff_roles"] = staff_roles

        if not updates:
            cfg = await get_guild_config(interaction.guild_id)
            cat = interaction.guild.get_channel(cfg.get("ticket_category_id"))
            log = interaction.guild.get_channel(cfg.get("ticket_log_channel_id"))
            staff = [interaction.guild.get_role(r) for r in cfg.get("ticket_staff_roles", [])]
            embed = info_embed("Ticket System Setup", "Current configuration:")
            embed.add_field(name="Category", value=cat.mention if cat else "Not set", inline=True)
            embed.add_field(name="Log Channel", value=log.mention if log else "Not set", inline=True)
            embed.add_field(name="Staff Roles", value=", ".join(r.mention for r in staff if r) or "None", inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        await update_guild_config(interaction.guild_id, updates)
        await interaction.followup.send(embed=success_embed("Ticket System Configured", "Settings saved."), ephemeral=True)

    @ticket_group.command(name="panel", description="Send a ticket panel to a channel")
    @app_commands.describe(channel="Channel to send the panel to", title="Panel title", description="Panel description")
    @is_admin()
    async def panel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        title: str = "🎫 Support Tickets",
        description: str = "Select a ticket type below to open a support ticket.",
    ):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        ticket_types = cfg.get("ticket_types", [
            {"name": "Support", "emoji": "🛠️", "description": "Get help from staff"},
            {"name": "Report", "emoji": "🚨", "description": "Report a user or issue"},
            {"name": "Purchase", "emoji": "💰", "description": "Inquire about purchases"},
        ])
        embed = primary_embed(title, description)
        embed.set_footer(text=f"{interaction.guild.name} • Ticket System")
        view = TicketPanelView(ticket_types)
        await channel.send(embed=embed, view=view)
        await interaction.followup.send(embed=success_embed("Panel Sent", f"Ticket panel sent to {channel.mention}."), ephemeral=True)

    @ticket_group.command(name="add", description="Add a user to a ticket")
    @app_commands.describe(member="Member to add")
    @is_ticket_staff()
    async def add(self, interaction: discord.Interaction, member: discord.Member):
        ticket = await Database.db.tickets.find_one({"guild_id": interaction.guild_id, "channel_id": interaction.channel_id})
        if not ticket:
            await interaction.response.send_message(embed=error_embed("Not a Ticket", "This command must be used in a ticket channel."), ephemeral=True)
            return
        await interaction.channel.set_permissions(member, view_channel=True, send_messages=True, attach_files=True)
        await interaction.response.send_message(embed=success_embed("Member Added", f"{member.mention} has been added to the ticket."))

    @ticket_group.command(name="remove", description="Remove a user from a ticket")
    @app_commands.describe(member="Member to remove")
    @is_ticket_staff()
    async def remove(self, interaction: discord.Interaction, member: discord.Member):
        ticket = await Database.db.tickets.find_one({"guild_id": interaction.guild_id, "channel_id": interaction.channel_id})
        if not ticket:
            await interaction.response.send_message(embed=error_embed("Not a Ticket", "This command must be used in a ticket channel."), ephemeral=True)
            return
        if member.id == ticket["user_id"]:
            await interaction.response.send_message(embed=error_embed("Cannot Remove", "You cannot remove the ticket owner."), ephemeral=True)
            return
        await interaction.channel.set_permissions(member, overwrite=None)
        await interaction.response.send_message(embed=success_embed("Member Removed", f"{member.mention} has been removed from the ticket."))

    @ticket_group.command(name="rename", description="Rename a ticket channel")
    @app_commands.describe(name="New channel name")
    @is_ticket_staff()
    async def rename(self, interaction: discord.Interaction, name: str):
        ticket = await Database.db.tickets.find_one({"guild_id": interaction.guild_id, "channel_id": interaction.channel_id})
        if not ticket:
            await interaction.response.send_message(embed=error_embed("Not a Ticket", "This command must be used in a ticket channel."), ephemeral=True)
            return
        await interaction.channel.edit(name=name[:100])
        await interaction.response.send_message(embed=success_embed("Renamed", f"Channel renamed to `{name}`."))

    @ticket_group.command(name="claim", description="Claim the current ticket")
    @is_ticket_staff()
    async def claim(self, interaction: discord.Interaction):
        ticket = await Database.db.tickets.find_one({"guild_id": interaction.guild_id, "channel_id": interaction.channel_id})
        if not ticket:
            await interaction.response.send_message(embed=error_embed("Not a Ticket", "This is not a ticket channel."), ephemeral=True)
            return
        if ticket.get("claimed_by"):
            m = interaction.guild.get_member(ticket["claimed_by"])
            await interaction.response.send_message(embed=error_embed("Already Claimed", f"Claimed by {m.mention if m else 'someone'}."), ephemeral=True)
            return
        await Database.db.tickets.update_one({"channel_id": interaction.channel_id}, {"$set": {"claimed_by": interaction.user.id}})
        await interaction.response.send_message(embed=success_embed("Ticket Claimed", f"{interaction.user.mention} has claimed this ticket."))

    @ticket_group.command(name="unclaim", description="Unclaim the current ticket")
    @is_ticket_staff()
    async def unclaim(self, interaction: discord.Interaction):
        ticket = await Database.db.tickets.find_one({"guild_id": interaction.guild_id, "channel_id": interaction.channel_id})
        if not ticket:
            await interaction.response.send_message(embed=error_embed("Not a Ticket", "This is not a ticket channel."), ephemeral=True)
            return
        if ticket.get("claimed_by") != interaction.user.id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(embed=error_embed("Not Claimed By You", "You didn't claim this ticket."), ephemeral=True)
            return
        await Database.db.tickets.update_one({"channel_id": interaction.channel_id}, {"$set": {"claimed_by": None}})
        await interaction.response.send_message(embed=success_embed("Ticket Unclaimed", "This ticket is no longer claimed."))

    @ticket_group.command(name="close", description="Close the current ticket")
    async def close(self, interaction: discord.Interaction):
        ticket = await Database.db.tickets.find_one({"guild_id": interaction.guild_id, "channel_id": interaction.channel_id, "status": "open"})
        if not ticket:
            await interaction.response.send_message(embed=error_embed("Not a Ticket", "This is not an open ticket channel."), ephemeral=True)
            return
        if interaction.user.id != ticket["user_id"] and not interaction.user.guild_permissions.manage_channels:
            cfg = await get_guild_config(interaction.guild_id)
            if not any(r.id in cfg.get("ticket_staff_roles", []) for r in interaction.user.roles):
                await interaction.response.send_message(embed=error_embed("No Permission", "You cannot close this ticket."), ephemeral=True)
                return
        await Database.db.tickets.update_one({"channel_id": interaction.channel_id}, {"$set": {"status": "closed", "closed_at": datetime.datetime.utcnow(), "closed_by": interaction.user.id}})
        await interaction.channel.edit(name=f"closed-{interaction.channel.name.replace('ticket-', '', 1)}")
        from views.tickets import ClosedTicketView
        view = ClosedTicketView()
        await interaction.response.send_message(embed=success_embed("Ticket Closed", f"Closed by {interaction.user.mention}.\nUse the buttons below to delete or reopen."), view=view)

    @ticket_group.command(name="delete", description="Delete a closed ticket channel")
    @is_ticket_staff()
    async def delete(self, interaction: discord.Interaction):
        ticket = await Database.db.tickets.find_one({"guild_id": interaction.guild_id, "channel_id": interaction.channel_id})
        if not ticket:
            await interaction.response.send_message(embed=error_embed("Not a Ticket", "This is not a ticket channel."), ephemeral=True)
            return
        await interaction.response.send_message(embed=primary_embed("Deleting...", "Channel will be deleted in 5 seconds."))
        import asyncio
        await asyncio.sleep(5)
        await interaction.channel.delete(reason=f"Ticket deleted by {interaction.user}")

    @ticket_group.command(name="transcript", description="Get a transcript of the current ticket")
    @is_ticket_staff()
    async def transcript(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        messages = []
        async for msg in interaction.channel.history(limit=500, oldest_first=True):
            ts = msg.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
            content = msg.content or ""
            for e in msg.embeds:
                content += f" [Embed: {e.title or 'Untitled'}: {e.description or ''}]"
            messages.append(f"[{ts}] {msg.author.name}#{msg.author.discriminator} ({msg.author.id}): {content}")
        content = "\n".join(messages)
        import io
        file = discord.File(
            io.BytesIO(content.encode()),
            filename=f"transcript-{interaction.channel.name}.txt",
        )
        await interaction.followup.send(embed=success_embed("Transcript", "Here is the transcript:"), file=file, ephemeral=True)

    @ticket_group.command(name="view", description="View ticket statistics")
    @is_admin()
    async def view(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        total = await Database.db.tickets.count_documents({"guild_id": interaction.guild_id})
        open_t = await Database.db.tickets.count_documents({"guild_id": interaction.guild_id, "status": "open"})
        closed_t = await Database.db.tickets.count_documents({"guild_id": interaction.guild_id, "status": "closed"})
        embed = info_embed("📊 Ticket Statistics", f"**Server:** {interaction.guild.name}")
        embed.add_field(name="Total Tickets", value=str(total), inline=True)
        embed.add_field(name="Open", value=str(open_t), inline=True)
        embed.add_field(name="Closed", value=str(closed_t), inline=True)
        cfg = await get_guild_config(interaction.guild_id)
        types = cfg.get("ticket_types", [])
        for t in types:
            count = await Database.db.tickets.count_documents({"guild_id": interaction.guild_id, "type": t["name"]})
            embed.add_field(name=t["name"], value=str(count), inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @ticket_group.command(name="addtype", description="Add a ticket type to the dropdown panel")
    @app_commands.describe(
        name="Ticket type name (shown in dropdown)",
        description="Short description shown under the name",
        emoji="Emoji shown next to the name",
        channel_name_pattern="Channel name pattern — use {username}, {count}, {type} (default: ticket-{username}-{count})",
    )
    @is_admin()
    async def addtype(
        self,
        interaction: discord.Interaction,
        name: str,
        description: str = "",
        emoji: str = "🎫",
        channel_name_pattern: str = "ticket-{username}-{count}",
    ):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        ticket_types = cfg.get("ticket_types", [])
        if any(t["name"].lower() == name.lower() for t in ticket_types):
            await interaction.followup.send(embed=error_embed("Already Exists", f"A ticket type named **{name}** already exists."), ephemeral=True)
            return
        ticket_types.append({
            "name": name,
            "description": description[:100],
            "emoji": emoji,
            "channel_name_pattern": channel_name_pattern,
        })
        await update_guild_config(interaction.guild_id, {"ticket_types": ticket_types})
        embed = success_embed("Ticket Type Added", f"{emoji} **{name}** added.\nRe-send `/tickets panel` to update the dropdown.")
        embed.add_field(name="Channel Pattern", value=f"`{channel_name_pattern}`", inline=False)
        embed.add_field(name="Variables", value="`{username}` `{count}` `{type}`", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @ticket_group.command(name="removetype", description="Remove a ticket type from the dropdown")
    @app_commands.describe(name="Name of the ticket type to remove")
    @is_admin()
    async def removetype(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        ticket_types = cfg.get("ticket_types", [])
        new_types = [t for t in ticket_types if t["name"].lower() != name.lower()]
        if len(new_types) == len(ticket_types):
            await interaction.followup.send(embed=error_embed("Not Found", f"No ticket type named **{name}**."), ephemeral=True)
            return
        await update_guild_config(interaction.guild_id, {"ticket_types": new_types})
        await interaction.followup.send(embed=success_embed("Removed", f"**{name}** removed.\nRe-send `/tickets panel` to update."), ephemeral=True)

    @ticket_group.command(name="listtypes", description="List all ticket types")
    @is_admin()
    async def listtypes(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        ticket_types = cfg.get("ticket_types", [])
        if not ticket_types:
            await interaction.followup.send(embed=info_embed("No Types", "No ticket types yet. Use `/tickets addtype` to add one."), ephemeral=True)
            return
        embed = primary_embed("🎫 Ticket Types", f"{len(ticket_types)} type(s):")
        for t in ticket_types:
            embed.add_field(name=f"{t.get('emoji','🎫')} {t['name']}", value=t.get("description") or "No description", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @ticket_group.command(name="customize", description="Open the interactive ticket panel customizer")
    @is_admin()
    async def customize(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        data = dict(cfg.get("ticket_panel", {}))
        if "ticket_types" not in data:
            data["ticket_types"] = cfg.get("ticket_types", [])
        from views.panel_customizer import TicketPanelCustomizerView, build_panel_embed
        from utils.helpers import primary_embed as _primary
        view = TicketPanelCustomizerView(interaction.user.id, data)
        types = data.get("ticket_types", [])
        lines = [
            f"**Title:** {data.get('title') or '*Not set*'}",
            f"**Color:** #{data.get('color', 0x5865F2):06X}" if isinstance(data.get('color'), int) else f"**Color:** {data.get('color', '#5865F2')}",
            f"**Thumbnail:** {'✅' if data.get('thumbnail') else '❌'}",
            f"**Image:** {'✅' if data.get('image') else '❌'}",
            f"**Footer:** {data.get('footer_text') or '*Not set*'}",
            f"**Types:** {', '.join(t['emoji']+' '+t['name'] for t in types) if types else '*None — add at least 1*'}",
        ]
        embed = _primary("🎫 Ticket Panel Customizer", "\n".join(lines))
        embed.set_footer(text="Use the buttons below to customize • Preview shows a live preview")
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @ticket_group.command(name="reset", description="Reset the ticket system configuration")
    @is_admin()
    async def reset(self, interaction: discord.Interaction):
        await update_guild_config(interaction.guild_id, {
            "ticket_category_id": None,
            "ticket_log_channel_id": None,
            "ticket_staff_roles": [],
            "ticket_types": [],
        })
        await interaction.response.send_message(embed=success_embed("Reset", "Ticket system configuration has been reset."), ephemeral=True)

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(TicketPanelView([
            {"name": "Support", "emoji": "🛠️"},
            {"name": "Report", "emoji": "🚨"},
            {"name": "Purchase", "emoji": "💰"},
        ]))
        self.bot.add_view(TicketControlView())
        from views.tickets import ClosedTicketView
        self.bot.add_view(ClosedTicketView())


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
