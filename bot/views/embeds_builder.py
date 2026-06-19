import discord
import json
import datetime
from utils.helpers import success_embed, error_embed, primary_embed


def build_embed_from_data(data: dict) -> discord.Embed:
    embed = discord.Embed(
        title=data.get("title", ""),
        description=data.get("description", ""),
        color=int(data.get("color", "0x5865F2"), 16) if isinstance(data.get("color"), str) else data.get("color", 0x5865F2),
        url=data.get("url"),
    )
    if data.get("author_name"):
        embed.set_author(
            name=data["author_name"],
            icon_url=data.get("author_icon"),
            url=data.get("author_url"),
        )
    if data.get("thumbnail"):
        embed.set_thumbnail(url=data["thumbnail"])
    if data.get("image"):
        embed.set_image(url=data["image"])
    for field in data.get("fields", []):
        embed.add_field(
            name=field.get("name", "\u200b"),
            value=field.get("value", "\u200b"),
            inline=field.get("inline", False),
        )
    if data.get("footer_text"):
        embed.set_footer(text=data["footer_text"], icon_url=data.get("footer_icon"))
    if data.get("timestamp"):
        embed.timestamp = datetime.datetime.utcnow()
    return embed


class EmbedBuilderModal(discord.ui.Modal, title="Embed Builder"):
    embed_title = discord.ui.TextInput(label="Title", max_length=256, required=False, placeholder="Embed title")
    embed_description = discord.ui.TextInput(
        label="Description", style=discord.TextStyle.paragraph, max_length=4000, required=False, placeholder="Embed description"
    )
    embed_color = discord.ui.TextInput(label="Color (hex)", max_length=7, required=False, placeholder="#5865F2", default="#5865F2")
    embed_thumbnail = discord.ui.TextInput(label="Thumbnail URL", required=False, placeholder="https://...")
    embed_image = discord.ui.TextInput(label="Image URL", required=False, placeholder="https://...")

    def __init__(self, existing: dict = None):
        super().__init__()
        if existing:
            self.embed_title.default = existing.get("title", "")
            self.embed_description.default = existing.get("description", "")
            color = existing.get("color", 0x5865F2)
            self.embed_color.default = f"#{color:06X}" if isinstance(color, int) else str(color)
            self.embed_thumbnail.default = existing.get("thumbnail", "")
            self.embed_image.default = existing.get("image", "")

    async def on_submit(self, interaction: discord.Interaction):
        color_str = self.embed_color.value.strip().lstrip("#")
        try:
            color = int(color_str, 16)
        except ValueError:
            color = 0x5865F2

        self.result = {
            "title": self.embed_title.value,
            "description": self.embed_description.value,
            "color": color,
            "thumbnail": self.embed_thumbnail.value or None,
            "image": self.embed_image.value or None,
            "fields": [],
        }
        await interaction.response.defer()
        self.stop()


class EmbedFooterModal(discord.ui.Modal, title="Embed Footer & Author"):
    footer_text = discord.ui.TextInput(label="Footer Text", max_length=2048, required=False)
    footer_icon = discord.ui.TextInput(label="Footer Icon URL", required=False)
    author_name = discord.ui.TextInput(label="Author Name", max_length=256, required=False)
    author_icon = discord.ui.TextInput(label="Author Icon URL", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        self.result = {
            "footer_text": self.footer_text.value,
            "footer_icon": self.footer_icon.value or None,
            "author_name": self.author_name.value,
            "author_icon": self.author_icon.value or None,
        }
        await interaction.response.defer()
        self.stop()


class AddFieldModal(discord.ui.Modal, title="Add Field"):
    field_name = discord.ui.TextInput(label="Field Name", max_length=256)
    field_value = discord.ui.TextInput(label="Field Value", style=discord.TextStyle.paragraph, max_length=1024)
    field_inline = discord.ui.TextInput(label="Inline? (yes/no)", max_length=3, default="no")

    async def on_submit(self, interaction: discord.Interaction):
        self.result = {
            "name": self.field_name.value,
            "value": self.field_value.value,
            "inline": self.field_inline.value.lower().startswith("y"),
        }
        await interaction.response.defer()
        self.stop()


class SaveEmbedModal(discord.ui.Modal, title="Save Embed Template"):
    name = discord.ui.TextInput(label="Template Name", max_length=64, placeholder="e.g. welcome-embed")

    async def on_submit(self, interaction: discord.Interaction):
        self.template_name = self.name.value
        await interaction.response.defer()
        self.stop()


class EmbedBuilderView(discord.ui.View):
    def __init__(self, author_id: int, data: dict = None):
        super().__init__(timeout=300)
        self.author_id = author_id
        self.data = data or {}

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This builder is not for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Edit Content", style=discord.ButtonStyle.primary, emoji="✏️", row=0)
    async def edit_content(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = EmbedBuilderModal(self.data)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if hasattr(modal, "result"):
            self.data.update(modal.result)
            await self._refresh(interaction)

    @discord.ui.button(label="Footer/Author", style=discord.ButtonStyle.secondary, emoji="📝", row=0)
    async def edit_footer(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = EmbedFooterModal()
        await interaction.response.send_modal(modal)
        await modal.wait()
        if hasattr(modal, "result"):
            self.data.update(modal.result)
            await self._refresh(interaction)

    @discord.ui.button(label="Add Field", style=discord.ButtonStyle.secondary, emoji="➕", row=0)
    async def add_field(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = AddFieldModal()
        await interaction.response.send_modal(modal)
        await modal.wait()
        if hasattr(modal, "result"):
            if "fields" not in self.data:
                self.data["fields"] = []
            if len(self.data["fields"]) < 25:
                self.data["fields"].append(modal.result)
            await self._refresh(interaction)

    @discord.ui.button(label="Clear Fields", style=discord.ButtonStyle.secondary, emoji="🗑️", row=1)
    async def clear_fields(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.data["fields"] = []
        await self._refresh(interaction)

    @discord.ui.button(label="Preview", style=discord.ButtonStyle.success, emoji="👁️", row=1)
    async def preview(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.data:
            await interaction.response.send_message(embed=error_embed("Empty", "Build your embed first."), ephemeral=True)
            return
        try:
            embed = build_embed_from_data(self.data)
            await interaction.response.send_message(content="**Preview:**", embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(embed=error_embed("Error", str(e)), ephemeral=True)

    @discord.ui.button(label="Save Template", style=discord.ButtonStyle.success, emoji="💾", row=1)
    async def save_template(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = SaveEmbedModal()
        await interaction.response.send_modal(modal)
        await modal.wait()
        if hasattr(modal, "template_name"):
            from database import Database
            await Database.db.embeds.update_one(
                {"guild_id": interaction.guild_id, "name": modal.template_name},
                {"$set": {"guild_id": interaction.guild_id, "name": modal.template_name, "data": self.data}},
                upsert=True,
            )
            await interaction.followup.send(
                embed=success_embed("Saved", f"Template `{modal.template_name}` saved!"), ephemeral=True
            )

    @discord.ui.button(label="Send", style=discord.ButtonStyle.danger, emoji="📨", row=2)
    async def send_embed(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.data:
            await interaction.response.send_message(embed=error_embed("Empty", "Build your embed first."), ephemeral=True)
            return
        try:
            embed = build_embed_from_data(self.data)
            await interaction.channel.send(embed=embed)
            await interaction.response.send_message(embed=success_embed("Sent", "Embed sent!"), ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(embed=error_embed("Error", str(e)), ephemeral=True)

    @discord.ui.button(label="Export JSON", style=discord.ButtonStyle.secondary, emoji="📤", row=2)
    async def export_json(self, interaction: discord.Interaction, button: discord.ui.Button):
        json_str = json.dumps(self.data, indent=2)
        import io
        file = discord.File(
            io.BytesIO(json_str.encode()),
            filename="embed.json",
        )
        await interaction.response.send_message(file=file, ephemeral=True)

    async def _refresh(self, interaction: discord.Interaction):
        status = primary_embed(
            "Embed Builder",
            f"**Title:** {self.data.get('title') or 'None'}\n"
            f"**Description:** {'Set ✅' if self.data.get('description') else 'None'}\n"
            f"**Fields:** {len(self.data.get('fields', []))}\n"
            f"**Image:** {'Set ✅' if self.data.get('image') else 'None'}\n"
            f"**Thumbnail:** {'Set ✅' if self.data.get('thumbnail') else 'None'}",
        )
        try:
            await interaction.message.edit(embed=status, view=self)
        except Exception:
            pass
