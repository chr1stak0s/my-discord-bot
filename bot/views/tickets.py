import discord
import datetime
import re
from database import Database, get_guild_config, update_guild_config
from utils.helpers import success_embed, error_embed, primary_embed


def _build_channel_name(pattern: str, username: str, count: int, type_name: str) -> str:
    """Resolve a channel name pattern to an actual name."""
    name = pattern or "ticket-{username}-{count}"
    name = name.replace("{username}", re.sub(r"[^a-z0-9\-]", "", username.lower())[:20])
    name = name.replace("{count}", str(count))
    name = name.replace("{type}", re.sub(r"[^a-z0-9\-]", "", type_name.lower())[:20])
    name = re.sub(r"-{2,}", "-", name).strip("-")
    return name[:100] or f"ticket-{count}"


class TicketTypeSelect(discord.ui.Select):
    def __init__(self, ticket_types: list[dict]):
        options = [
            discord.SelectOption(
                label=t["name"],
                description=t.get("description", "")[:100],
                emoji=t.get("emoji", "🎫"),
                value=t["name"],
            )
            for t in ticket_types[:25]
        ]
        super().__init__(placeholder="Select a ticket type...", options=options, custom_id="ticket:type_select")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        ticket_types = cfg.get("ticket_types", [])
        chosen = next((t for t in ticket_types if t["name"] == self.values[0]), None)
        if not chosen:
            await interaction.followup.send(embed=error_embed("Not Found", "Ticket type not found."), ephemeral=True)
            return

        open_ticket = await Database.db.tickets.find_one({
            "guild_id": interaction.guild_id,
            "user_id": interaction.user.id,
            "status": "open",
        })
        if open_ticket:
            channel = interaction.guild.get_channel(open_ticket["channel_id"])
            if channel:
                await interaction.followup.send(
                    embed=error_embed("Existing Ticket", f"You already have an open ticket: {channel.mention}"),
                    ephemeral=True,
                )
                return

        category_id = chosen.get("category_id") or cfg.get("ticket_category_id")
        category = interaction.guild.get_channel(category_id) if category_id else None

        ticket_count = await Database.db.tickets.count_documents({"guild_id": interaction.guild_id}) + 1
        pattern = chosen.get("channel_name_pattern", "ticket-{username}-{count}")
        channel_name = _build_channel_name(pattern, interaction.user.name, ticket_count, chosen["name"])

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, attach_files=True, embed_links=True
            ),
            interaction.guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_channels=True
            ),
        }
        for role_id in cfg.get("ticket_staff_roles", []):
            role = interaction.guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, manage_messages=True
                )

        channel = await interaction.guild.create_text_channel(
            channel_name,
            category=category,
            overwrites=overwrites,
            topic=f"Ticket #{ticket_count} | {chosen['name']} | {interaction.user}",
        )

        doc = {
            "guild_id": interaction.guild_id,
            "channel_id": channel.id,
            "user_id": interaction.user.id,
            "ticket_id": ticket_count,
            "type": chosen["name"],
            "status": "open",
            "claimed_by": None,
            "created_at": datetime.datetime.utcnow(),
            "messages": [],
        }
        await Database.db.tickets.insert_one(doc)

        embed = primary_embed(
            f"🎫 {chosen['name']} Ticket #{ticket_count}",
            chosen.get("welcome_message", f"Welcome {interaction.user.mention}!\nSupport will be with you shortly."),
        )
        embed.add_field(name="Created by", value=interaction.user.mention)
        embed.add_field(name="Type", value=chosen["name"])

        view = TicketControlView()
        await channel.send(
            content=f"{interaction.user.mention}" + (
                f" {' '.join(f'<@&{r}>' for r in cfg.get('ticket_staff_roles', []))}"
                if cfg.get("ticket_staff_roles") else ""
            ),
            embed=embed,
            view=view,
        )
        await interaction.followup.send(
            embed=success_embed("Ticket Created", f"Your ticket has been created: {channel.mention}"),
            ephemeral=True,
        )

        log_channel_id = cfg.get("ticket_log_channel_id")
        if log_channel_id:
            log_ch = interaction.guild.get_channel(log_channel_id)
            if log_ch:
                log_embed = primary_embed(
                    "Ticket Opened",
                    f"**User:** {interaction.user.mention}\n**Type:** {chosen['name']}\n**Channel:** {channel.mention}",
                )
                log_embed.set_thumbnail(url=interaction.user.display_avatar.url)
                await log_ch.send(embed=log_embed)


class TicketPanelView(discord.ui.View):
    def __init__(self, ticket_types: list[dict]):
        super().__init__(timeout=None)
        self.add_item(TicketTypeSelect(ticket_types))

    @classmethod
    def from_config(cls, cfg: dict):
        types = cfg.get("ticket_types", [{"name": "Support", "emoji": "🎫", "description": "Open a support ticket"}])
        return cls(types)


class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="ticket:close")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = await Database.db.tickets.find_one({
            "guild_id": interaction.guild_id,
            "channel_id": interaction.channel_id,
            "status": "open",
        })
        if not ticket:
            await interaction.response.send_message(embed=error_embed("Not a Ticket", "This is not an open ticket channel."), ephemeral=True)
            return

        if interaction.user.id != ticket["user_id"] and not interaction.user.guild_permissions.manage_channels:
            cfg = await get_guild_config(interaction.guild_id)
            staff = cfg.get("ticket_staff_roles", [])
            if not any(r.id in staff for r in interaction.user.roles):
                await interaction.response.send_message(embed=error_embed("No Permission", "You cannot close this ticket."), ephemeral=True)
                return

        view = CloseConfirmView(ticket)
        await interaction.response.send_message(
            embed=primary_embed("Close Ticket", "Are you sure you want to close this ticket?"),
            view=view,
            ephemeral=True,
        )

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.success, emoji="🙋", custom_id="ticket:claim")
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await get_guild_config(interaction.guild_id)
        staff = cfg.get("ticket_staff_roles", [])
        if not interaction.user.guild_permissions.administrator and not any(r.id in staff for r in interaction.user.roles):
            await interaction.response.send_message(embed=error_embed("No Permission", "Only staff can claim tickets."), ephemeral=True)
            return

        ticket = await Database.db.tickets.find_one({"guild_id": interaction.guild_id, "channel_id": interaction.channel_id})
        if not ticket:
            await interaction.response.send_message(embed=error_embed("Not Found", "Ticket not found."), ephemeral=True)
            return

        if ticket.get("claimed_by"):
            claimed_user = interaction.guild.get_member(ticket["claimed_by"])
            await interaction.response.send_message(
                embed=error_embed("Already Claimed", f"This ticket is already claimed by {claimed_user.mention if claimed_user else 'someone'}."),
                ephemeral=True,
            )
            return

        await Database.db.tickets.update_one(
            {"channel_id": interaction.channel_id},
            {"$set": {"claimed_by": interaction.user.id}},
        )
        await interaction.response.send_message(
            embed=success_embed("Ticket Claimed", f"{interaction.user.mention} has claimed this ticket.")
        )

    @discord.ui.button(label="Transcript", style=discord.ButtonStyle.secondary, emoji="📄", custom_id="ticket:transcript")
    async def get_transcript(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        messages = []
        async for msg in interaction.channel.history(limit=500, oldest_first=True):
            ts = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
            messages.append(f"[{ts}] {msg.author} ({msg.author.id}): {msg.content}")
            for embed in msg.embeds:
                if embed.title:
                    messages.append(f"  [Embed] {embed.title}: {embed.description or ''}")

        content = "\n".join(messages)
        import io
        file = discord.File(
            io.BytesIO(content.encode()),
            filename=f"transcript-{interaction.channel.name}.txt",
        )
        await interaction.followup.send(embed=success_embed("Transcript Generated", "Here is your transcript:"), file=file, ephemeral=True)


class CloseConfirmView(discord.ui.View):
    def __init__(self, ticket: dict):
        super().__init__(timeout=30)
        self.ticket = ticket

    @discord.ui.button(label="Yes, Close", style=discord.ButtonStyle.danger)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=primary_embed("Closing...", "Closing the ticket..."),
            view=None,
        )

        await Database.db.tickets.update_one(
            {"channel_id": interaction.channel_id},
            {"$set": {"status": "closed", "closed_at": datetime.datetime.utcnow(), "closed_by": interaction.user.id}},
        )

        cfg = await get_guild_config(interaction.guild_id)
        for role_id in cfg.get("ticket_staff_roles", []):
            role = interaction.guild.get_role(role_id)
            if role:
                await interaction.channel.set_permissions(role, send_messages=False)

        owner = interaction.guild.get_member(self.ticket["user_id"])
        if owner:
            await interaction.channel.set_permissions(owner, send_messages=False)

        new_name = f"closed-{interaction.channel.name}"
        try:
            await interaction.channel.edit(name=new_name[:100])
        except discord.HTTPException:
            pass

        embed = primary_embed(
            "🔒 Ticket Closed",
            f"This ticket was closed by {interaction.user.mention}.\nUse the buttons below to delete or reopen it.",
        )

        view = ClosedTicketView()
        await interaction.channel.send(embed=embed, view=view)
        log_channel_id = cfg.get("ticket_log_channel_id")
        if log_channel_id:
            log_ch = interaction.guild.get_channel(log_channel_id)
            if log_ch:
                log_embed = primary_embed(
                    "Ticket Closed",
                    f"**Closed by:** {interaction.user.mention}\n**Channel:** {interaction.channel.mention}",
                )
                await log_ch.send(embed=log_embed)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=primary_embed("Cancelled", "The ticket was not closed."),
            view=None,
        )
        self.stop()


class ClosedTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger, emoji="🗑️", custom_id="ticket:delete")
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_channels:
            cfg = await get_guild_config(interaction.guild_id)
            if not any(r.id in cfg.get("ticket_staff_roles", []) for r in interaction.user.roles):
                await interaction.response.send_message(embed=error_embed("No Permission", "You cannot delete this ticket."), ephemeral=True)
                return

        await interaction.response.send_message(
            embed=primary_embed("🗑️ Deleting...", "This channel will be permanently deleted in **5 seconds**."),
            ephemeral=True,
        )
        import asyncio
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason=f"Ticket deleted by {interaction.user}")
        except discord.HTTPException as e:
            await interaction.followup.send(
                embed=error_embed("Delete Failed", f"Could not delete the channel: {e}"),
                ephemeral=True,
            )

    @discord.ui.button(label="Reopen", style=discord.ButtonStyle.success, emoji="🔓", custom_id="ticket:reopen")
    async def reopen(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = await Database.db.tickets.find_one({"channel_id": interaction.channel_id})
        if not ticket:
            await interaction.response.send_message(embed=error_embed("Not Found", "Ticket not found."), ephemeral=True)
            return

        cfg = await get_guild_config(interaction.guild_id)
        owner = interaction.guild.get_member(ticket["user_id"])
        if owner:
            await interaction.channel.set_permissions(owner, view_channel=True, send_messages=True)

        for role_id in cfg.get("ticket_staff_roles", []):
            role = interaction.guild.get_role(role_id)
            if role:
                await interaction.channel.set_permissions(role, view_channel=True, send_messages=True, manage_messages=True)

        new_name = interaction.channel.name
        if new_name.startswith("closed-"):
            new_name = new_name[len("closed-") :]
        try:
            await interaction.channel.edit(name=new_name[:100])
        except discord.HTTPException:
            pass

        await Database.db.tickets.update_one(
            {"channel_id": interaction.channel_id},
            {"$Set": {"status": "open", "claimed_by": None}},
        )
        await interaction.response.send_message(embed=success_embed("🔓 Reopened", "Ticket has been reopened."))

        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)
        self.stop()
