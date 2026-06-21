import discord
import datetime
from utils.helpers import success_embed, error_embed, primary_embed, info_embed


def build_panel_embed(data: dict) -> discord.Embed:
    color_raw = data.get("color", 0x5865F2)
    if isinstance(color_raw, str):
        try:
            color = int(color_raw.lstrip("#"), 16)
        except ValueError:
            color = 0x5865F2
    else:
        color = color_raw

    embed = discord.Embed(
        title=data.get("title", "📋 Panel"),
        description=data.get("description", ""),
        color=color,
    )
    if data.get("thumbnail"):
        embed.set_thumbnail(url=data["thumbnail"])
    if data.get("image"):
        embed.set_image(url=data["image"])
    if data.get("footer_text"):
        embed.set_footer(text=data["footer_text"], icon_url=data.get("footer_icon") or None)
    if data.get("timestamp"):
        embed.timestamp = datetime.datetime.utcnow()
    return embed


# ─── Modals ───────────────────────────────────────────────────────────────────

class TitleDescModal(discord.ui.Modal, title="Set Title & Description"):
    panel_title = discord.ui.TextInput(label="Title", max_length=256, required=False, placeholder="🎫 Support Tickets")
    panel_desc = discord.ui.TextInput(label="Description", style=discord.TextStyle.paragraph, max_length=2000, required=False, placeholder="Select a category below to open a ticket.")

    def __init__(self, existing: dict):
        super().__init__()
        self.panel_title.default = existing.get("title", "")
        self.panel_desc.default = existing.get("description", "")
        self.result = None

    async def on_submit(self, interaction: discord.Interaction):
        self.result = {"title": self.panel_title.value, "description": self.panel_desc.value}
        await interaction.response.defer()
        self.stop()


class ColorModal(discord.ui.Modal, title="Set Color"):
    color = discord.ui.TextInput(label="Hex Color", max_length=7, placeholder="#5865F2", default="#5865F2")

    def __init__(self, existing: dict):
        super().__init__()
        c = existing.get("color", 0x5865F2)
        self.color.default = f"#{c:06X}" if isinstance(c, int) else str(c)
        self.result = None

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.color.value.strip().lstrip("#")
        try:
            val = int(raw, 16)
            self.result = {"color": val}
            await interaction.response.defer()
        except ValueError:
            await interaction.response.send_message(embed=error_embed("Invalid Color", "Use a valid hex like `#FF0000`."), ephemeral=True)
        self.stop()


class MediaModal(discord.ui.Modal, title="Set Images"):
    thumbnail = discord.ui.TextInput(label="Thumbnail URL (top-right small image)", required=False, placeholder="https://...")
    image = discord.ui.TextInput(label="Large Image URL (bottom of embed)", required=False, placeholder="https://...")

    def __init__(self, existing: dict):
        super().__init__()
        self.thumbnail.default = existing.get("thumbnail", "")
        self.image.default = existing.get("image", "")
        self.result = None

    async def on_submit(self, interaction: discord.Interaction):
        self.result = {
            "thumbnail": self.thumbnail.value.strip() or None,
            "image": self.image.value.strip() or None,
        }
        await interaction.response.defer()
        self.stop()


class FooterModal(discord.ui.Modal, title="Set Footer"):
    footer_text = discord.ui.TextInput(label="Footer Text", max_length=2048, required=False, placeholder="Your Server Name • Ticket System")
    footer_icon = discord.ui.TextInput(label="Footer Icon URL", required=False, placeholder="https://... (server icon URL)")

    def __init__(self, existing: dict):
        super().__init__()
        self.footer_text.default = existing.get("footer_text", "")
        self.footer_icon.default = existing.get("footer_icon", "")
        self.result = None

    async def on_submit(self, interaction: discord.Interaction):
        self.result = {
            "footer_text": self.footer_text.value.strip() or None,
            "footer_icon": self.footer_icon.value.strip() or None,
        }
        await interaction.response.defer()
        self.stop()


class AddTypeModal(discord.ui.Modal, title="Add Ticket Type"):
    name = discord.ui.TextInput(label="Type Name", max_length=100, placeholder="Support")
    description = discord.ui.TextInput(label="Description", max_length=100, required=False, placeholder="Get help from our team")
    emoji = discord.ui.TextInput(label="Emoji", max_length=10, required=False, placeholder="🎫", default="🎫")
    channel_name_pattern = discord.ui.TextInput(
        label="Channel Name Pattern",
        max_length=80,
        required=False,
        placeholder="ticket-{username}-{count}",
        default="ticket-{username}-{count}",
    )

    def __init__(self):
        super().__init__()
        self.result = None

    async def on_submit(self, interaction: discord.Interaction):
        self.result = {
            "name": self.name.value.strip(),
            "description": self.description.value.strip()[:100],
            "emoji": self.emoji.value.strip() or "🎫",
            "channel_name_pattern": self.channel_name_pattern.value.strip() or "ticket-{username}-{count}",
        }
        await interaction.response.defer()
        self.stop()


class RemoveTypeModal(discord.ui.Modal, title="Remove Ticket Type"):
    name = discord.ui.TextInput(label="Type Name to Remove", max_length=100, placeholder="Support")

    def __init__(self):
        super().__init__()
        self.result = None

    async def on_submit(self, interaction: discord.Interaction):
        self.result = self.name.value.strip()
        await interaction.response.defer()
        self.stop()


class SendChannelModal(discord.ui.Modal, title="Send Panel to Channel"):
    channel_id = discord.ui.TextInput(label="Channel ID or #name", max_length=30, placeholder="Paste the channel ID")

    def __init__(self):
        super().__init__()
        self.result = None

    async def on_submit(self, interaction: discord.Interaction):
        self.result = self.channel_id.value.strip().lstrip("#").strip()
        await interaction.response.defer()
        self.stop()


# ─── Add Form Modal (Applications) ────────────────────────────────────────────

class AddFormModal(discord.ui.Modal, title="Add Application Form"):
    name = discord.ui.TextInput(label="Form Name", max_length=100, placeholder="Staff Application")
    description = discord.ui.TextInput(label="Description", max_length=150, required=False, placeholder="Apply to become a staff member")
    q1 = discord.ui.TextInput(label="Question 1", max_length=45, placeholder="How old are you?")
    q2 = discord.ui.TextInput(label="Question 2", max_length=45, required=False, placeholder="Tell us about yourself")
    q3 = discord.ui.TextInput(label="Question 3", max_length=45, required=False, placeholder="Why do you want to join?")

    def __init__(self):
        super().__init__()
        self.result = None

    async def on_submit(self, interaction: discord.Interaction):
        questions = [q for q in [self.q1.value, self.q2.value, self.q3.value] if q.strip()]
        self.result = {
            "name": self.name.value.strip(),
            "description": self.description.value.strip(),
            "questions": questions,
            "open": True,
        }
        await interaction.response.defer()
        self.stop()


# ─── Ticket Panel Customizer View ─────────────────────────────────────────────

class TicketPanelCustomizerView(discord.ui.View):
    def __init__(self, user_id: int, data: dict):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.data = data

    async def _check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This customizer belongs to someone else.", ephemeral=True)
            return False
        return True

    def _summary(self) -> str:
        types = self.data.get("ticket_types", [])
        lines = [
            f"**Title:** {self.data.get('title') or '*Not set*'}",
            f"**Color:** #{self.data.get('color', 0x5865F2):06X}" if isinstance(self.data.get('color'), int) else f"**Color:** {self.data.get('color', '#5865F2')}",
            f"**Thumbnail:** {'✅' if self.data.get('thumbnail') else '❌'}",
            f"**Image:** {'✅' if self.data.get('image') else '❌'}",
            f"**Footer:** {self.data.get('footer_text') or '*Not set*'}",
            f"**Types:** {', '.join(t['emoji']+' '+t['name'] for t in types) if types else '*None — add at least 1*'}",
        ]
        return "\n".join(lines)

    async def _refresh(self, interaction: discord.Interaction):
        embed = primary_embed("🎫 Ticket Panel Customizer", self._summary())
        embed.set_footer(text="Use the buttons below to customize • Preview shows a live preview")
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="✏️ Title & Description", style=discord.ButtonStyle.primary, row=0)
    async def set_title(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        modal = TitleDescModal(self.data)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.result:
            self.data.update(modal.result)
            await self._refresh(interaction)

    @discord.ui.button(label="🎨 Color", style=discord.ButtonStyle.primary, row=0)
    async def set_color(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        modal = ColorModal(self.data)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.result:
            self.data.update(modal.result)
            await self._refresh(interaction)

    @discord.ui.button(label="🖼️ Images", style=discord.ButtonStyle.primary, row=0)
    async def set_images(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        modal = MediaModal(self.data)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.result:
            self.data.update(modal.result)
            await self._refresh(interaction)

    @discord.ui.button(label="📝 Footer", style=discord.ButtonStyle.primary, row=0)
    async def set_footer(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        modal = FooterModal(self.data)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.result:
            self.data.update(modal.result)
            await self._refresh(interaction)

    @discord.ui.button(label="➕ Add Type", style=discord.ButtonStyle.success, row=1)
    async def add_type(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        modal = AddTypeModal()
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.result:
            types = self.data.get("ticket_types", [])
            if any(t["name"].lower() == modal.result["name"].lower() for t in types):
                await interaction.followup.send(embed=error_embed("Already Exists", f"**{modal.result['name']}** already exists."), ephemeral=True)
                return
            types.append(modal.result)
            self.data["ticket_types"] = types
            await self._refresh(interaction)

    @discord.ui.button(label="❌ Remove Type", style=discord.ButtonStyle.danger, row=1)
    async def remove_type(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        modal = RemoveTypeModal()
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.result:
            types = self.data.get("ticket_types", [])
            new = [t for t in types if t["name"].lower() != modal.result.lower()]
            if len(new) == len(types):
                await interaction.followup.send(embed=error_embed("Not Found", f"No type named **{modal.result}**."), ephemeral=True)
                return
            self.data["ticket_types"] = new
            await self._refresh(interaction)

    @discord.ui.button(label="👁️ Preview", style=discord.ButtonStyle.secondary, row=1)
    async def preview(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        embed = build_panel_embed(self.data)
        types = self.data.get("ticket_types", [])
        if types:
            embed.add_field(name="Ticket Types", value="\n".join(f"{t.get('emoji','🎫')} **{t['name']}** — {t.get('description','')}" for t in types), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="💾 Save & Send", style=discord.ButtonStyle.success, row=2)
    async def save_send(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        types = self.data.get("ticket_types", [])
        if not types:
            await interaction.response.send_message(embed=error_embed("No Types", "Add at least one ticket type before sending."), ephemeral=True)
            return
        modal = SendChannelModal()
        await interaction.response.send_modal(modal)
        await modal.wait()
        if not modal.result:
            return
        raw = modal.result
        channel = interaction.guild.get_channel(int(raw)) if raw.isdigit() else discord.utils.get(interaction.guild.text_channels, name=raw.lower())
        if not channel:
            await interaction.followup.send(embed=error_embed("Channel Not Found", f"Could not find channel `{raw}`. Use the channel ID."), ephemeral=True)
            return
        self.data["_customized"] = True
        from database import update_guild_config
        await update_guild_config(interaction.guild_id, {"ticket_panel": self.data, "ticket_types": types})
        from views.tickets import TicketPanelView
        embed = build_panel_embed(self.data)
        view = TicketPanelView(types)
        await channel.send(embed=embed, view=view)
        await interaction.followup.send(embed=success_embed("Panel Sent!", f"Your custom ticket panel has been sent to {channel.mention}."), ephemeral=True)

    @discord.ui.button(label="💾 Save Only", style=discord.ButtonStyle.secondary, row=2)
    async def save_only(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        from database import update_guild_config
        types = self.data.get("ticket_types", [])
        await update_guild_config(interaction.guild_id, {"ticket_panel": self.data, "ticket_types": types})
        await interaction.response.send_message(embed=success_embed("Saved!", "Panel design saved. Use **Save & Send** to post it to a channel."), ephemeral=True)


# ─── Application Panel Customizer View ────────────────────────────────────────

class AppPanelCustomizerView(discord.ui.View):
    def __init__(self, user_id: int, data: dict):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.data = data

    async def _check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This customizer belongs to someone else.", ephemeral=True)
            return False
        return True

    def _style(self) -> str:
        return self.data.get("panel_style", "buttons")

    def _summary(self) -> str:
        forms = self.data.get("forms", [])
        style = self._style()
        lines = [
            f"**Title:** {self.data.get('title') or '*Not set*'}",
            f"**Color:** #{self.data.get('color', 0x5865F2):06X}" if isinstance(self.data.get('color'), int) else f"**Color:** {self.data.get('color', '#5865F2')}",
            f"**Thumbnail:** {'✅' if self.data.get('thumbnail') else '❌'}",
            f"**Image:** {'✅' if self.data.get('image') else '❌'}",
            f"**Footer:** {self.data.get('footer_text') or '*Not set*'}",
            f"**Panel Style:** {'🔘 Buttons' if style == 'buttons' else '📋 Dropdown'}",
            f"**Forms:** {', '.join(f['name'] for f in forms) if forms else '*None — add at least 1*'}",
        ]
        return "\n".join(lines)

    async def _refresh(self, interaction: discord.Interaction):
        embed = primary_embed("📋 Application Panel Customizer", self._summary())
        embed.set_footer(text="Use the buttons below to customize • Preview shows a live preview")
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="✏️ Title & Description", style=discord.ButtonStyle.primary, row=0)
    async def set_title(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        modal = TitleDescModal(self.data)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.result:
            self.data.update(modal.result)
            await self._refresh(interaction)

    @discord.ui.button(label="🎨 Color", style=discord.ButtonStyle.primary, row=0)
    async def set_color(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        modal = ColorModal(self.data)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.result:
            self.data.update(modal.result)
            await self._refresh(interaction)

    @discord.ui.button(label="🖼️ Images", style=discord.ButtonStyle.primary, row=0)
    async def set_images(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        modal = MediaModal(self.data)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.result:
            self.data.update(modal.result)
            await self._refresh(interaction)

    @discord.ui.button(label="📝 Footer", style=discord.ButtonStyle.primary, row=0)
    async def set_footer(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        modal = FooterModal(self.data)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.result:
            self.data.update(modal.result)
            await self._refresh(interaction)

    @discord.ui.button(label="🔘 Style: Buttons", style=discord.ButtonStyle.secondary, row=1)
    async def toggle_style(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        current = self._style()
        new_style = "dropdown" if current == "buttons" else "buttons"
        self.data["panel_style"] = new_style
        button.label = "📋 Style: Dropdown" if new_style == "dropdown" else "🔘 Style: Buttons"
        await self._refresh(interaction)

    @discord.ui.button(label="👁️ Preview", style=discord.ButtonStyle.secondary, row=1)
    async def preview(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        embed = build_panel_embed(self.data)
        forms = self.data.get("forms", [])
        style = self._style()
        if forms:
            if style == "buttons":
                embed.add_field(
                    name="Panel Buttons",
                    value="\n".join(f"{f.get('emoji', '📋')} **{f['name']}**" for f in forms),
                    inline=False,
                )
            else:
                embed.add_field(
                    name="Panel Dropdown",
                    value="*A dropdown menu will appear with the forms listed below*\n" + "\n".join(f"{f.get('emoji', '📋')} {f['name']}" for f in forms),
                    inline=False,
                )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="💾 Save & Send", style=discord.ButtonStyle.success, row=2)
    async def save_send(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        forms = self.data.get("forms", [])
        if not forms:
            await interaction.response.send_message(embed=error_embed("No Forms", "Add at least one application form before sending."), ephemeral=True)
            return
        modal = SendChannelModal()
        await interaction.response.send_modal(modal)
        await modal.wait()
        if not modal.result:
            return
        raw = modal.result
        channel = interaction.guild.get_channel(int(raw)) if raw.isdigit() else discord.utils.get(interaction.guild.text_channels, name=raw.lower())
        if not channel:
            await interaction.followup.send(embed=error_embed("Channel Not Found", f"Could not find channel `{raw}`. Use the channel ID."), ephemeral=True)
            return
        from database import update_guild_config
        await update_guild_config(interaction.guild_id, {"application_panel": self.data})
        style = self._style()
        embed = build_panel_embed(self.data)
        if style == "buttons":
            from views.applications import ApplicationPanelView
            view = ApplicationPanelView(forms)
        else:
            from views.applications import ApplicationDropdownPanelView
            view = ApplicationDropdownPanelView(forms)
        await channel.send(embed=embed, view=view)
        await interaction.followup.send(embed=success_embed("Panel Sent!", f"Your custom application panel has been sent to {channel.mention}."), ephemeral=True)

    @discord.ui.button(label="💾 Save Only", style=discord.ButtonStyle.secondary, row=2)
    async def save_only(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        from database import update_guild_config
        await update_guild_config(interaction.guild_id, {"application_panel": self.data})
        await interaction.response.send_message(embed=success_embed("Saved!", "Application panel design saved. Use **Save & Send** to post it to a channel."), ephemeral=True)


# ─── Verification Panel Customizer ────────────────────────────────────────────

class VerifyPanelCustomizerView(discord.ui.View):
    def __init__(self, user_id: int, data: dict):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.data = data

    async def _check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This customizer belongs to someone else.", ephemeral=True)
            return False
        return True

    def _summary(self) -> str:
        lines = [
            f"**Title:** {self.data.get('title') or '✅ Verification'}",
            f"**Description:** {(self.data.get('description') or '')[:80] or 'Click the button below to verify.'}",
            f"**Color:** #{self.data.get('color', 0x5865F2):06X}" if isinstance(self.data.get('color'), int) else f"**Color:** {self.data.get('color','#5865F2')}",
            f"**Thumbnail:** {'✅' if self.data.get('thumbnail') else '❌'}",
            f"**Image:** {'✅' if self.data.get('image') else '❌'}",
            f"**Footer:** {self.data.get('footer_text') or '❌ None'}",
            f"**Button Label:** {self.data.get('button_label') or 'Verify'}",
        ]
        return "\n".join(lines)

    async def _refresh(self, interaction: discord.Interaction):
        embed = primary_embed("✅ Verification Panel Customizer", self._summary())
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="✏️ Title & Description", style=discord.ButtonStyle.primary, row=0)
    async def set_title(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        modal = TitleDescModal(self.data)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.result:
            self.data.update(modal.result)
            await self._refresh(interaction)

    @discord.ui.button(label="🎨 Color", style=discord.ButtonStyle.primary, row=0)
    async def set_color(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        modal = ColorModal(self.data)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.result:
            self.data.update(modal.result)
            await self._refresh(interaction)

    @discord.ui.button(label="🖼️ Images", style=discord.ButtonStyle.primary, row=0)
    async def set_images(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        modal = MediaModal(self.data)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.result:
            self.data.update(modal.result)
            await self._refresh(interaction)

    @discord.ui.button(label="📝 Footer", style=discord.ButtonStyle.primary, row=0)
    async def set_footer(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        modal = FooterModal(self.data)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.result:
            self.data.update(modal.result)
            await self._refresh(interaction)

    @discord.ui.button(label="🔘 Button Label", style=discord.ButtonStyle.secondary, row=1)
    async def set_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return

        class ButtonLabelModal(discord.ui.Modal, title="Set Button Label"):
            label_input = discord.ui.TextInput(label="Button Label", max_length=80, placeholder="Verify ✅")
            def __init__(s, existing):
                super().__init__()
                s.label_input.default = existing.get("button_label", "Verify")
                s.result = None
            async def on_submit(s, inter):
                s.result = s.label_input.value.strip()
                await inter.response.defer()
                s.stop()

        m = ButtonLabelModal(self.data)
        await interaction.response.send_modal(m)
        await m.wait()
        if m.result:
            self.data["button_label"] = m.result
            await self._refresh(interaction)

    @discord.ui.button(label="👁️ Preview", style=discord.ButtonStyle.secondary, row=1)
    async def preview(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        embed = build_panel_embed(self.data)
        if not embed.title:
            embed.title = "✅ Verification"
        if not embed.description:
            embed.description = "Click the button below to verify and gain access to the server."
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="💾 Save & Send", style=discord.ButtonStyle.success, row=2)
    async def save_send(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        modal = SendChannelModal()
        await interaction.response.send_modal(modal)
        await modal.wait()
        if not modal.result:
            return
        raw = modal.result
        channel = interaction.guild.get_channel(int(raw)) if raw.isdigit() else discord.utils.get(interaction.guild.text_channels, name=raw.lower())
        if not channel:
            await interaction.followup.send(embed=error_embed("Channel Not Found", f"Could not find `{raw}`. Use the channel ID."), ephemeral=True)
            return
        from database import update_guild_config, get_guild_config
        cfg = await get_guild_config(interaction.guild_id)
        role_id = cfg.get("verification_role_id")
        await update_guild_config(interaction.guild_id, {"verify_panel": self.data, "verification_channel_id": channel.id})
        embed = build_panel_embed(self.data)
        if not embed.title:
            embed.title = "✅ Verification"
        if not embed.description:
            embed.description = "Click the button below to verify and gain access to the server."
        from cogs.extra import VerifyView
        real_view = VerifyView(role_id)
        await channel.send(embed=embed, view=real_view)
        await interaction.followup.send(embed=success_embed("Sent!", f"Verification panel sent to {channel.mention}."), ephemeral=True)

    @discord.ui.button(label="💾 Save Only", style=discord.ButtonStyle.secondary, row=2)
    async def save_only(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        from database import update_guild_config
        await update_guild_config(interaction.guild_id, {"verify_panel": self.data})
        await interaction.response.send_message(embed=success_embed("Saved!", "Verification panel design saved."), ephemeral=True)

# ─── Welcome / Leave Embed Customizer ─────────────────────────────────────────
class WelcomeCustomizerView(discord.ui.View):
    def __init__(self, user_id: int, kind: str, data: dict):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.kind = kind  # "welcome" or "leave"
        self.data = data
    async def _check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This customizer belongs to someone else.", ephemeral=True)
            return False
        return True
    def _label(self) -> str:
        return "👋 Join Embed" if self.kind == "welcome" else "👋 Leave Embed"
    def _summary(self) -> str:
        lines = [
            f"**Title:** {self.data.get('title') or ('*👋 Welcome, {user}!*' if self.kind == 'welcome' else '*👋 Member Left*')}",
            f"**Description:** {(self.data.get('description') or '')[:80] or '*Default message*'}",
            f"**Color:** #{self.data.get('color', 0x5865F2):06X}" if isinstance(self.data.get('color'), int) else f"**Color:** {self.data.get('color', '#5865F2')}",
            f"**Thumbnail:** {'✅' if self.data.get('thumbnail') else '❌ (uses member avatar)'}",
            f"**Image:** {'✅' if self.data.get('image') else '❌'}",
            f"**Footer:** {self.data.get('footer_text') or '*Not set*'}",
        ]
        return "\n".join(lines)
    async def _refresh(self, interaction: discord.Interaction):
        embed = primary_embed(self._label() + " Customizer", self._summary())
        embed.set_footer(text="Variables: {user} {server} {count} • Use Preview to test")
        await interaction.edit_original_response(embed=embed, view=self)
    @discord.ui.button(label="✏️ Title & Description", style=discord.ButtonStyle.primary, row=0)
    async def set_title(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        modal = TitleDescModal(self.data)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.result:
            self.data.update(modal.result)
            await self._refresh(interaction)
    @discord.ui.button(label="🎨 Color", style=discord.ButtonStyle.primary, row=0)
    async def set_color(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        modal = ColorModal(self.data)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.result:
            self.data.update(modal.result)
            await self._refresh(interaction)
    @discord.ui.button(label="🖼️ Images", style=discord.ButtonStyle.primary, row=0)
    async def set_images(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        modal = MediaModal(self.data)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.result:
            self.data.update(modal.result)
            await self._refresh(interaction)
    @discord.ui.button(label="📝 Footer", style=discord.ButtonStyle.primary, row=0)
    async def set_footer(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        modal = FooterModal(self.data)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.result:
            self.data.update(modal.result)
            await self._refresh(interaction)
    @discord.ui.button(label="👁️ Preview", style=discord.ButtonStyle.secondary, row=1)
    async def preview(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        member = interaction.user
        data = dict(self.data)
        default_title = "👋 Welcome, {user}!" if self.kind == "welcome" else "👋 Member Left"
        title = (data.get("title") or default_title).replace("{user}", member.display_name).replace("{server}", interaction.guild.name).replace("{count}", str(interaction.guild.member_count))
        desc = (data.get("description") or "").replace("{user}", member.mention).replace("{server}", interaction.guild.name).replace("{count}", str(interaction.guild.member_count))
        data["title"] = title
        data["description"] = desc
        embed = build_panel_embed(data)
        if not data.get("thumbnail"):
            embed.set_thumbnail(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    @discord.ui.button(label="💾 Save", style=discord.ButtonStyle.success, row=1)
    async def save(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        from database import update_guild_config
        key = f"{self.kind}_embed"
        await update_guild_config(interaction.guild_id, {key: self.data})
        await interaction.response.send_message(
            embed=success_embed("Saved!", f"{'Join' if self.kind == 'welcome' else 'Leave'} embed saved. It will be used for all future messages."),
            ephemeral=True,
        )
    @discord.ui.button(label="🔄 Reset to Default", style=discord.ButtonStyle.danger, row=1)
    async def reset(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        from database import update_guild_config
        key = f"{self.kind}_embed"
        self.data = {}
        await update_guild_config(interaction.guild_id, {key: {}})
        await self._refresh(interaction)