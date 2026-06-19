import discord
from discord import app_commands
from discord.ext import commands
import json
import logging
from database import Database, get_guild_config
from utils import success_embed, error_embed, info_embed, primary_embed, is_admin
from views.embeds_builder import EmbedBuilderView, build_embed_from_data

logger = logging.getLogger(__name__)


class Embeds(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    embeds_group = app_commands.Group(name="embeds", description="Embed builder and management commands")

    @embeds_group.command(name="create", description="Open the interactive embed builder")
    @is_admin()
    async def create(self, interaction: discord.Interaction):
        view = EmbedBuilderView(interaction.user.id)
        embed = primary_embed(
            "🎨 Embed Builder",
            "Use the buttons below to build your embed.\n\n"
            "**Edit Content** — Set title, description, color, images\n"
            "**Footer/Author** — Set footer and author fields\n"
            "**Add Field** — Add up to 25 fields\n"
            "**Preview** — Preview your embed\n"
            "**Save Template** — Save to reuse later\n"
            "**Send** — Send the embed to this channel\n"
            "**Export JSON** — Export as JSON file",
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @embeds_group.command(name="edit", description="Edit a saved embed template")
    @app_commands.describe(name="Template name to edit")
    @is_admin()
    async def edit(self, interaction: discord.Interaction, name: str):
        template = await Database.db.embeds.find_one({"guild_id": interaction.guild_id, "name": name})
        if not template:
            await interaction.response.send_message(embed=error_embed("Not Found", f"No template named `{name}` found."), ephemeral=True)
            return
        view = EmbedBuilderView(interaction.user.id, template.get("data", {}))
        status = primary_embed("🎨 Embed Builder", f"Editing template: **{name}**")
        await interaction.response.send_message(embed=status, view=view, ephemeral=True)

    @embeds_group.command(name="delete", description="Delete a saved embed template")
    @app_commands.describe(name="Template name to delete")
    @is_admin()
    async def delete(self, interaction: discord.Interaction, name: str):
        result = await Database.db.embeds.delete_one({"guild_id": interaction.guild_id, "name": name})
        if result.deleted_count == 0:
            await interaction.response.send_message(embed=error_embed("Not Found", f"No template named `{name}` found."), ephemeral=True)
            return
        await interaction.response.send_message(embed=success_embed("Deleted", f"Template `{name}` deleted."), ephemeral=True)

    @embeds_group.command(name="preview", description="Preview a saved embed template")
    @app_commands.describe(name="Template name to preview")
    async def preview(self, interaction: discord.Interaction, name: str):
        template = await Database.db.embeds.find_one({"guild_id": interaction.guild_id, "name": name})
        if not template:
            await interaction.response.send_message(embed=error_embed("Not Found", f"No template named `{name}` found."), ephemeral=True)
            return
        try:
            embed = build_embed_from_data(template["data"])
            await interaction.response.send_message(content=f"**Preview of `{name}`:**", embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(embed=error_embed("Error", str(e)), ephemeral=True)

    @embeds_group.command(name="save", description="Save an embed from a message (by message ID)")
    @app_commands.describe(message_id="ID of the message containing the embed", name="Name to save as")
    @is_admin()
    async def save(self, interaction: discord.Interaction, message_id: str, name: str):
        await interaction.response.defer(ephemeral=True)
        try:
            msg = await interaction.channel.fetch_message(int(message_id))
        except (discord.NotFound, ValueError):
            await interaction.followup.send(embed=error_embed("Not Found", "Message not found in this channel."), ephemeral=True)
            return

        if not msg.embeds:
            await interaction.followup.send(embed=error_embed("No Embed", "That message has no embeds."), ephemeral=True)
            return

        e = msg.embeds[0]
        data = {
            "title": e.title or "",
            "description": e.description or "",
            "color": e.color.value if e.color else 0x5865F2,
            "thumbnail": e.thumbnail.url if e.thumbnail else None,
            "image": e.image.url if e.image else None,
            "footer_text": e.footer.text if e.footer else None,
            "author_name": e.author.name if e.author else None,
            "fields": [{"name": f.name, "value": f.value, "inline": f.inline} for f in e.fields],
        }
        await Database.db.embeds.update_one(
            {"guild_id": interaction.guild_id, "name": name},
            {"$set": {"guild_id": interaction.guild_id, "name": name, "data": data}},
            upsert=True,
        )
        await interaction.followup.send(embed=success_embed("Saved", f"Embed saved as template `{name}`."), ephemeral=True)

    @embeds_group.command(name="template", description="Send a saved embed template to a channel")
    @app_commands.describe(name="Template name", channel="Channel to send to (defaults to current)")
    @is_admin()
    async def template(self, interaction: discord.Interaction, name: str, channel: discord.TextChannel = None):
        await interaction.response.defer(ephemeral=True)
        template = await Database.db.embeds.find_one({"guild_id": interaction.guild_id, "name": name})
        if not template:
            await interaction.followup.send(embed=error_embed("Not Found", f"No template named `{name}` found."), ephemeral=True)
            return
        target = channel or interaction.channel
        try:
            embed = build_embed_from_data(template["data"])
            await target.send(embed=embed)
            await interaction.followup.send(embed=success_embed("Sent", f"Template `{name}` sent to {target.mention}."), ephemeral=True)
        except Exception as e:
            await interaction.followup.send(embed=error_embed("Error", str(e)), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Embeds(bot))
