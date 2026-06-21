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


# ─── Shared Modals ────────────────────────────────────────────────────────────

class TitleDescModal(discord.ui.Modal, title="Set Title & Description"):
    panel_title = discord.ui.TextInput(label="Title", max_length=256, required=False, placeholder="📋 Applications")
    panel_desc = discord.ui.TextInput(label="Description", style=discord.TextStyle.paragraph, max_length=2000, required=False, placeholder="Select an application below to submit.")

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
    footer_text = discord.ui.TextInput(label="Footer Text", max_length=2048, required=False, placeholder="Your Server • Application System")
    footer_icon = discord.ui.TextInput(label="Footer Icon URL", required=False, placeholder="https://...")

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


class SendChannelModal(discord.ui.Modal, title="Send Panel to Channel"):
    channel_id = discord.ui.TextInput(label="Channel ID", max_length=30, placeholder="Paste the channel ID here")

    def __init__(self):
        super().__init__()
        self.result = None

    async def on_submit(self, interaction: discord.Interaction):
        self.result = self.channel_id.value.strip().lstrip("#").strip()
        await interaction.response.defer()
        self.stop()


# ─── Ticket-specific Modals ───────────────────────────────────────────────────

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


# ─── Application-specific Modals ──────────────────────────────────────────────

class AddFormModal(discord.ui.Modal, title="Add Application Form"):
    name = discord.ui.TextInput(label="Form Name", max_length=100, placeholder="Staff Application")
    description = discord.ui.TextInput(label="Short Description", max_length=150, required=False, placeholder="Apply to become a staff member")
    emoji = discord.ui.TextInput(label="Emoji", max_length=10, required=False, placeholder="📋", default="📋")
    q1 = discord.ui.TextInput(label="Question 1", max_length=45, placeholder="How old are you?")
    q2 = discord.ui.TextInput(label="Question 2 (optional)", max_length=45, required=False, placeholder="Tell us about yourself")

    def __init__(self):
        super().__init__()
        self.result = None

    async def on_submit(self, interaction: discord.Interaction):
        questions = [q for q in [self.q1.value.strip(), self.q2.value.strip()] if q]
        self.result = {
            "name": self.name.value.strip(),
            "description": self.description.value.strip(),
            "emoji": self.emoji.value.strip() or "📋",
            "questions": questions,
            "open": True,
        }
        await interaction.response.defer()
        self.stop()


class RemoveFormModal(discord.ui.Modal, title="Remove Application Form"):
    name = discord.ui.TextInput(label="Form Name to Remove", max_length=100, placeholder="Staff Application")

    def __init__(self):
        super().__init__()
        self.result = None

    async def on_submit(self, interaction: discord.Interaction):
        self.result = self.name.value.strip()
        await interaction.response.defer()
        self.stop()


class EditFormQuestionsModal(discord.ui.Modal, title="Edit Form Questions"):
    q1 = discord.ui.TextInput(label="Question 1", max_length=45, required=True)
    q2 = discord.ui.TextInput(label="Question 2 (optional)", max_length=45, required=False)
    q3 = discord.ui.TextInput(label="Question 3 (optional)", max_length=45, required=False)
    q4 = discord.ui.TextInput(label="Question 4 (optional)", max_length=45, required=False)
    q5 = discord.ui.TextInput(label="Question 5 (optional)", max_length=45, required=False)

    def __init__(self, existing_questions: list[str]):
        super().__init__()
        fields = [self.q1, self.q2, self.q3, self.q4, self.q5]
        for i, field in enumerate(fields):
            field.default = existing_questions[i] if i < len(existing_questions) else ""
        self.result = None

    async def on_submit(self, interaction: discord.Interaction):
        questions = [q for q in [
            self.q1.value.strip(),
            self.q2.value.strip(),
            self.q3.value.strip(),
            self.q4.value.strip(),
            self.q5.value.strip(),
        ] if q]
        self.result = questions
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
        color = self.data.get("color", 0x5865F2)
        color_str = f"#{color:06X}" if isinstance(color, int) else str(color)
        lines = [
            f"**Title:** {self.data.get('title') or '*Not set*'}",
            f"**Color:** {color_str}",
            f"**Thumbnail:** {'✅' if self.data.get('thumbnail') else '❌'}",
            f"**Image:** {'✅' if self.data.get('image') else '❌'}",
            f"**Footer:** {self.data.get('footer_text') or '*Not set*'}",
            f"**Style:** {'🔘 Buttons' if style == 'buttons' else '📋 Dropdown'}",
            "",
            f"**Forms ({len(forms)}):**",
        ]
        if forms:
            for f in forms:
                status = "🟢" if f.get("open", True) else "🔴"
                lines.append(f"  {status} {f.get('emoji','📋')} **{f['name']}** — {len(f.get('questions', []))} question(s)")
        else:
            lines.append("  *None — add at least 1 form*")
        return "\n".join(lines)

    async def _refresh(self, interaction: discord.Interaction):
        embed = primary_embed("📋 Application Panel Customizer", self._summary())
        embed.set_footer(text="🟢 Open  🔴 Closed • Use Preview to see the final result")
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

    @discord.ui.button(label="➕ Add Form", style=discord.ButtonStyle.success, row=1)
    async def add_form(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        modal = AddFormModal()
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.result:
            forms = self.data.get("forms", [])
            if any(f["name"].lower() == modal.result["name"].lower() for f in forms):
                await interaction.followup.send(embed=error_embed("Already Exists", f"A form named **{modal.result['name']}** already exists."), ephemeral=True)
                return
            forms.append(modal.result)
            self.data["forms"] = forms
            from database import update_guild_config, get_guild_config
            cfg = await get_guild_config(interaction.guild_id)
            all_forms = cfg.get("application_forms", [])
            if not any(f["name"].lower() == modal.result["name"].lower() for f in all_forms):
                all_forms.append(modal.result)
                await update_guild_config(interaction.guild_id, {"application_forms": all_forms})
            await self._refresh(interaction)

    @discord.ui.button(label="❌ Remove Form", style=discord.ButtonStyle.danger, row=1)
    async def remove_form(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        modal = RemoveFormModal()
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.result:
            forms = self.data.get("forms", [])
            new = [f for f in forms if f["name"].lower() != modal.result.lower()]
            if len(new) == len(forms):
                await interaction.followup.send(embed=error_embed("Not Found", f"No form named **{modal.result}** in this panel."), ephemeral=True)
                return
            self.data["forms"] = new
            await self._refresh(interaction)

    @discord.ui.button(label="✏️ Edit Questions", style=discord.ButtonStyle.secondary, row=1)
    async def edit_questions(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        forms = self.data.get("forms", [])
        if not forms:
            await interaction.response.send_message(embed=error_embed("No Forms", "Add a form first."), ephemeral=True)
            return
        view = FormSelectForEditView(self.user_id, self.data, forms)
        await interaction.response.send_message(embed=primary_embed("Select a Form", "Choose which form's questions to edit:"), view=view, ephemeral=True)

    @discord.ui.button(label="🔘 Style: Buttons", style=discord.ButtonStyle.secondary, row=2)
    async def toggle_style(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        current = self._style()
        new_style = "dropdown" if current == "buttons" else "buttons"
        self.data["panel_style"] = new_style
        button.label = "📋 Style: Dropdown" if new_style == "dropdown" else "🔘 Style: Buttons"
        await self._refresh(interaction)

    @discord.ui.button(label="👁️ Preview", style=discord.ButtonStyle.secondary, row=2)
    async def preview(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        embed = build_panel_embed(self.data)
        forms = self.data.get("forms", [])
        style = self._style()
        if forms:
            if style == "buttons":
                embed.add_field(
                    name="Panel Buttons",
                    value="\n".join(f"{f.get('emoji', '📋')} **{f['name']}**" + (" 🔴" if not f.get("open", True) else "") for f in forms),
                    inline=False,
                )
            else:
                embed.add_field(
                    name="Panel Dropdown",
                    value="*A dropdown will appear with the forms listed below*\n" + "\n".join(f"{f.get('emoji', '📋')} {f['name']}" for f in forms),
                    inline=False,
                )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="💾 Save & Send", style=discord.ButtonStyle.success, row=3)
    async def save_send(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        forms = self.data.get("forms", [])
        if not forms:
            await interaction.response.send_message(embed=error_embed("No Forms", "Add at least one form before sending."), ephemeral=True)
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
        from views.applications import ApplicationPanelView, ApplicationDropdownPanelView
        view = ApplicationDropdownPanelView(forms) if style == "dropdown" else ApplicationPanelView(forms)
        await channel.send(embed=embed, view=view)
        await interaction.followup.send(embed=success_embed("Panel Sent!", f"Your application panel has been sent to {channel.mention}."), ephemeral=True)

    @discord.ui.button(label="💾 Save Only", style=discord.ButtonStyle.secondary, row=3)
    async def save_only(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        from database import update_guild_config
        await update_guild_config(interaction.guild_id, {"application_panel": self.data})
        await interaction.response.send_message(embed=success_embed("Saved!", "Panel saved. Use **Save & Send** to post it to a channel."), ephemeral=True)


class FormSelectForEditView(discord.ui.View):
    """Lets the user pick which form to edit questions for."""
    def __init__(self, user_id: int, panel_data: dict, forms: list[dict]):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.panel_data = panel_data
        options = [
            discord.SelectOption(label=f["name"], emoji=f.get("emoji", "📋"), value=f["name"])
            for f in forms[:25]
        ]
        select = discord.ui.Select(placeholder="Choose a form...", options=options)
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not yours.", ephemeral=True)
            return
        form_name = interaction.data["values"][0]
        forms = self.panel_data.get("forms", [])
        form = next((f for f in forms if f["name"] == form_name), None)
        if not form:
            await interaction.response.send_message(embed=error_embed("Not Found", "Form not found."), ephemeral=True)
            return
        modal = EditFormQuestionsModal(form.get("questions", []))
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.result:
            form["questions"] = modal.result
            self.panel_data["forms"] = forms
            await interaction.followup.send(
                embed=success_embed("Questions Updated", f"Questions for **{form_name}** have been updated to {len(modal.result)} question(s)."),
                ephemeral=True,
            )


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
            f"**Color:** #{self.data.get('color', 0x5865F2):06X}" if isinstance(self.data.get('color'), int) else f"**Color:** {self.data.get('color', '#5865F2')}",
            f"**Button Label:** {self.data.get('button_label') or 'Verify'}",
            f"**Verify Role:** {'Set ✅' if self.data.get('verify_role_id') else 'Not set'}",
            f"**Thumbnail:** {'✅' if self.data.get('thumbnail') else '❌'}",
            f"**Image:** {'✅' if self.data.get('image') else '❌'}",
            f"**Footer:** {self.data.get('footer_text') or '*Not set*'}",
        ]
        return "\n".join(lines)

    async def _refresh(self, interaction: discord.Interaction):
        embed = primary_embed("✅ Verification Panel Customizer", self._summary())
        embed.set_footer(text="Use the buttons below to customize")
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
        embed = build_panel_embed(self.data)
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
            await interaction.followup.send(embed=error_embed("Channel Not Found", f"Could not find channel `{raw}`."), ephemeral=True)
            return
        from database import update_guild_config
        await update_guild_config(interaction.guild_id, {"verify_panel": self.data})
        from views.confirm import VerifyView
        embed = build_panel_embed(self.data)
        view = VerifyView(self.data)
        await channel.send(embed=embed, view=view)
        await interaction.followup.send(embed=success_embed("Panel Sent!", f"Verification panel sent to {channel.mention}."), ephemeral=True)

    @discord.ui.button(label="💾 Save Only", style=discord.ButtonStyle.secondary, row=2)
    async def save_only(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        from database import update_guild_config
        await update_guild_config(interaction.guild_id, {"verify_panel": self.data})
        await interaction.response.send_message(embed=success_embed("Saved!", "Verification panel saved."), ephemeral=True)


# ─── Welcome/Leave Embed Customizer View ─────────────────────────────────────

class WelcomeCustomizerView(discord.ui.View):
    def __init__(self, user_id: int, embed_type: str, data: dict):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.embed_type = embed_type
        self.data = data

    def _label(self) -> str:
        return "👋 Join Message" if self.embed_type == "welcome" else "👋 Leave Message"

    async def _check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This customizer belongs to someone else.", ephemeral=True)
            return False
        return True

    def _summary(self) -> str:
        lines = [
            f"**Title:** {self.data.get('title') or '*Not set*'}",
            f"**Color:** #{self.data.get('color', 0x5865F2):06X}" if isinstance(self.data.get('color'), int) else f"**Color:** {self.data.get('color', '#5865F2')}",
            f"**Thumbnail:** {'✅' if self.data.get('thumbnail') else '❌'}",
            f"**Image:** {'✅' if self.data.get('image') else '❌'}",
            f"**Footer:** {self.data.get('footer_text') or '*Not set*'}",
            "",
            "*Variables: `{user}` `{server}` `{count}`*",
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
        data_copy = dict(self.data)
        if data_copy.get("title"):
            data_copy["title"] = data_copy["title"].replace("{user}", interaction.user.display_name).replace("{server}", interaction.guild.name).replace("{count}", str(interaction.guild.member_count))
        if data_copy.get("description"):
            data_copy["description"] = data_copy["description"].replace("{user}", interaction.user.mention).replace("{server}", interaction.guild.name).replace("{count}", str(interaction.guild.member_count))
        embed = build_panel_embed(data_copy)
        await interaction.response.send_message(content="**Preview:**", embed=embed, ephemeral=True)

    @discord.ui.button(label="💾 Save", style=discord.ButtonStyle.success, row=1)
    async def save(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction): return
        from database import update_guild_config
        await update_guild_config(interaction.guild_id, {f"{self.embed_type}_embed": self.data})
        await interaction.response.send_message(embed=success_embed("Saved!", f"{self._label()} saved successfully."), ephemeral=True)
