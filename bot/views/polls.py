import discord
from database import Database
from utils.helpers import primary_embed, error_embed


class PollView(discord.ui.View):
    def __init__(self, options: list[str]):
        super().__init__(timeout=None)
        for i, option in enumerate(options[:5]):
            self.add_item(PollButton(option, i))


class PollButton(discord.ui.Button):
    def __init__(self, label: str, index: int):
        styles = [
            discord.ButtonStyle.primary,
            discord.ButtonStyle.success,
            discord.ButtonStyle.danger,
            discord.ButtonStyle.secondary,
            discord.ButtonStyle.primary,
        ]
        super().__init__(label=label, style=styles[index % len(styles)], custom_id=f"poll:vote:{index}")
        self.option_index = index

    async def callback(self, interaction: discord.Interaction):
        poll = await Database.db.polls.find_one({
            "guild_id": interaction.guild_id,
            "message_id": interaction.message.id,
        })
        if not poll:
            await interaction.response.send_message(embed=error_embed("Not Found", "Poll not found."), ephemeral=True)
            return

        votes = poll.get("votes", {})
        user_id = str(interaction.user.id)

        if votes.get(user_id) == self.option_index:
            del votes[user_id]
            await interaction.response.send_message(primary_embed("Vote Removed", "Your vote has been removed."), ephemeral=True)
        else:
            votes[user_id] = self.option_index
            await interaction.response.send_message(
                embed=primary_embed("Voted!", f"You voted for **{self.label}**!"), ephemeral=True
            )

        await Database.db.polls.update_one(
            {"message_id": interaction.message.id},
            {"$set": {"votes": votes}},
        )

        options = poll.get("options", [])
        counts = [sum(1 for v in votes.values() if v == i) for i in range(len(options))]
        total = sum(counts)

        embed = interaction.message.embeds[0].copy() if interaction.message.embeds else discord.Embed(title="Poll")
        embed.clear_fields()
        for i, (option, count) in enumerate(zip(options, counts)):
            pct = (count / total * 100) if total > 0 else 0
            bar_filled = int(pct / 10)
            bar = "█" * bar_filled + "░" * (10 - bar_filled)
            embed.add_field(name=option, value=f"`{bar}` {pct:.1f}% ({count} votes)", inline=False)
        embed.set_footer(text=f"Total votes: {total}")
        await interaction.message.edit(embed=embed)
