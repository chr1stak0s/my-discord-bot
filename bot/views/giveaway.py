import discord
import datetime
import random
from database import Database
from utils.helpers import success_embed, error_embed, primary_embed


class GiveawayView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Enter Giveaway", style=discord.ButtonStyle.success, emoji="🎉", custom_id="giveaway:enter")
    async def enter(self, interaction: discord.Interaction, button: discord.ui.Button):
        giveaway = await Database.db.giveaways.find_one({
            "guild_id": interaction.guild_id,
            "message_id": interaction.message.id,
            "ended": False,
        })
        if not giveaway:
            await interaction.response.send_message(embed=error_embed("Ended", "This giveaway has ended."), ephemeral=True)
            return

        if datetime.datetime.utcnow() > giveaway["ends_at"]:
            await interaction.response.send_message(embed=error_embed("Ended", "This giveaway has ended."), ephemeral=True)
            return

        participants = giveaway.get("participants", [])
        if interaction.user.id in participants:
            participants.remove(interaction.user.id)
            await Database.db.giveaways.update_one(
                {"message_id": interaction.message.id},
                {"$set": {"participants": participants}},
            )
            button.label = f"Enter Giveaway ({len(participants)})"
            await interaction.message.edit(view=self)
            await interaction.response.send_message(embed=primary_embed("Left Giveaway", "You have left the giveaway."), ephemeral=True)
        else:
            participants.append(interaction.user.id)
            await Database.db.giveaways.update_one(
                {"message_id": interaction.message.id},
                {"$set": {"participants": participants}},
            )
            button.label = f"Enter Giveaway ({len(participants)})"
            await interaction.message.edit(view=self)
            await interaction.response.send_message(embed=success_embed("Entered!", "You have entered the giveaway! Good luck! 🎉"), ephemeral=True)
