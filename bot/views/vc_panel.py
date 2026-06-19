import discord
from database import Database
from utils import success_embed, error_embed, info_embed, primary_embed


# ── Helper ────────────────────────────────────────────────────────────────────

async def _get_owned(
    interaction: discord.Interaction,
) -> tuple[dict | None, discord.VoiceChannel | None]:
    """Return (doc, channel) for the VC owned by the interacting user, or respond with an error."""
    doc = await Database.db.temp_vcs.find_one({
        "guild_id": interaction.guild_id,
        "owner_id": interaction.user.id,
    })
    if not doc:
        await interaction.response.send_message(
            embed=error_embed(
                "No Channel",
                "You don't own a temporary voice channel.\nJoin the hub channel to create one!",
            ),
            ephemeral=True,
        )
        return None, None
    channel = interaction.guild.get_channel(doc["channel_id"])
    if not channel:
        await Database.db.temp_vcs.delete_one({"_id": doc["_id"]})
        await interaction.response.send_message(
            embed=error_embed("Not Found", "Your channel no longer exists."),
            ephemeral=True,
        )
        return None, None
    return doc, channel


# ── Modals ────────────────────────────────────────────────────────────────────

class RenameModal(discord.ui.Modal, title="✏️ Rename Your Channel"):
    name = discord.ui.TextInput(
        label="New Channel Name",
        max_length=100,
        placeholder="e.g. Study Room 📚",
    )

    async def on_submit(self, interaction: discord.Interaction):
        doc, channel = await _get_owned(interaction)
        if not doc:
            return
        try:
            await channel.edit(name=str(self.name)[:100])
            await interaction.response.send_message(
                embed=success_embed("✏️ Renamed", f"Channel renamed to **{self.name}**."),
                ephemeral=True,
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(embed=error_embed("Failed", str(e)), ephemeral=True)


class LimitModal(discord.ui.Modal, title="👥 Set User Limit"):
    limit = discord.ui.TextInput(
        label="User Limit (0 = unlimited, max 99)",
        placeholder="e.g. 5",
        max_length=2,
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            value = max(0, min(99, int(str(self.limit))))
        except ValueError:
            await interaction.response.send_message(
                embed=error_embed("Invalid Input", "Enter a number between **0** and **99**."),
                ephemeral=True,
            )
            return
        doc, channel = await _get_owned(interaction)
        if not doc:
            return
        await channel.edit(user_limit=value)
        label = str(value) if value else "Unlimited"
        await interaction.response.send_message(
            embed=success_embed("👥 Limit Set", f"User limit set to **{label}**."),
            ephemeral=True,
        )


class BitrateModal(discord.ui.Modal, title="📻 Set Bitrate"):
    kbps = discord.ui.TextInput(
        label="Bitrate in kbps (8–384)",
        placeholder="e.g. 64",
        max_length=3,
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            value = max(8, min(384, int(str(self.kbps))))
        except ValueError:
            await interaction.response.send_message(
                embed=error_embed("Invalid Input", "Enter a number between **8** and **384**."),
                ephemeral=True,
            )
            return
        doc, channel = await _get_owned(interaction)
        if not doc:
            return
        try:
            await channel.edit(bitrate=value * 1000)
            await interaction.response.send_message(
                embed=success_embed("📻 Bitrate Set", f"Bitrate set to **{value} kbps**."),
                ephemeral=True,
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(embed=error_embed("Failed", str(e)), ephemeral=True)


class MemberActionModal(discord.ui.Modal):
    member_input = discord.ui.TextInput(
        label="User ID or @mention",
        placeholder="e.g. 123456789012345678",
        max_length=100,
    )

    _TITLES = {
        "kick": "👢 Kick Member",
        "allow": "✅ Allow Member",
        "deny": "❌ Deny Member",
        "transfer": "🔄 Transfer Ownership",
    }

    def __init__(self, action: str):
        self.action = action
        super().__init__(title=self._TITLES.get(action, "Member Action"))

    async def on_submit(self, interaction: discord.Interaction):
        raw = str(self.member_input).strip().lstrip("<@!").rstrip(">")
        try:
            member_id = int(raw)
        except ValueError:
            await interaction.response.send_message(
                embed=error_embed("Invalid Input", "Enter a valid **User ID** (right-click → Copy ID)."),
                ephemeral=True,
            )
            return

        member = interaction.guild.get_member(member_id)
        if not member:
            await interaction.response.send_message(
                embed=error_embed("Not Found", "That member was not found in this server."),
                ephemeral=True,
            )
            return

        doc, channel = await _get_owned(interaction)
        if not doc:
            return

        if self.action == "kick":
            if member.voice and member.voice.channel and member.voice.channel.id == channel.id:
                await member.move_to(None, reason=f"Kicked from temp VC by owner {interaction.user}")
                await interaction.response.send_message(
                    embed=success_embed("👢 Kicked", f"{member.mention} has been removed from your channel."),
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    embed=error_embed("Not in Channel", f"{member.mention} is not in your voice channel."),
                    ephemeral=True,
                )

        elif self.action == "allow":
            await channel.set_permissions(member, connect=True, view_channel=True)
            await interaction.response.send_message(
                embed=success_embed("✅ Allowed", f"{member.mention} can now see and join your channel."),
                ephemeral=True,
            )

        elif self.action == "deny":
            if member.voice and member.voice.channel and member.voice.channel.id == channel.id:
                await member.move_to(None, reason=f"Denied from temp VC by owner {interaction.user}")
            await channel.set_permissions(member, connect=False, view_channel=False)
            await interaction.response.send_message(
                embed=success_embed("❌ Denied", f"{member.mention} cannot see or join your channel."),
                ephemeral=True,
            )

        elif self.action == "transfer":
            if member.id == interaction.user.id:
                await interaction.response.send_message(
                    embed=error_embed("Already Owner", "You are already the owner."),
                    ephemeral=True,
                )
                return
            if not (member.voice and member.voice.channel and member.voice.channel.id == channel.id):
                await interaction.response.send_message(
                    embed=error_embed("Not in Channel", f"{member.mention} must be in your VC to receive ownership."),
                    ephemeral=True,
                )
                return
            await Database.db.temp_vcs.update_one({"_id": doc["_id"]}, {"$set": {"owner_id": member.id}})
            await interaction.response.send_message(
                embed=success_embed("🔄 Transferred", f"{member.mention} is now the owner of your channel."),
                ephemeral=True,
            )
            try:
                await member.send(embed=info_embed(
                    "🔊 VC Ownership",
                    f"You are now the owner of **{channel.name}** in **{interaction.guild.name}**.\nUse the VC panel or `/vc` commands to manage it.",
                ))
            except discord.HTTPException:
                pass


# ── Panel View ────────────────────────────────────────────────────────────────

class VCPanelView(discord.ui.View):
    """Persistent view — must be registered via bot.add_view() on startup."""

    def __init__(self):
        super().__init__(timeout=None)

    # ── Row 0: Channel visibility / access ────────────────────────────────────

    @discord.ui.button(label="Lock", emoji="🔒", style=discord.ButtonStyle.danger,
                       custom_id="vc_panel:lock", row=0)
    async def lock(self, interaction: discord.Interaction, button: discord.ui.Button):
        doc, channel = await _get_owned(interaction)
        if not doc:
            return
        await channel.set_permissions(interaction.guild.default_role, connect=False)
        await Database.db.temp_vcs.update_one({"_id": doc["_id"]}, {"$set": {"locked": True}})
        await interaction.response.send_message(
            embed=success_embed("🔒 Locked", "Your channel is locked. No new members can join."),
            ephemeral=True,
        )

    @discord.ui.button(label="Unlock", emoji="🔓", style=discord.ButtonStyle.success,
                       custom_id="vc_panel:unlock", row=0)
    async def unlock(self, interaction: discord.Interaction, button: discord.ui.Button):
        doc, channel = await _get_owned(interaction)
        if not doc:
            return
        await channel.set_permissions(interaction.guild.default_role, connect=None)
        await Database.db.temp_vcs.update_one({"_id": doc["_id"]}, {"$set": {"locked": False}})
        await interaction.response.send_message(
            embed=success_embed("🔓 Unlocked", "Your channel is now open to everyone."),
            ephemeral=True,
        )

    @discord.ui.button(label="Hide", emoji="👻", style=discord.ButtonStyle.secondary,
                       custom_id="vc_panel:hide", row=0)
    async def hide(self, interaction: discord.Interaction, button: discord.ui.Button):
        doc, channel = await _get_owned(interaction)
        if not doc:
            return
        await channel.set_permissions(interaction.guild.default_role, view_channel=False)
        await Database.db.temp_vcs.update_one({"_id": doc["_id"]}, {"$set": {"hidden": True}})
        await interaction.response.send_message(
            embed=success_embed("👻 Hidden", "Your channel is now hidden from the server."),
            ephemeral=True,
        )

    @discord.ui.button(label="Show", emoji="👁️", style=discord.ButtonStyle.secondary,
                       custom_id="vc_panel:show", row=0)
    async def show(self, interaction: discord.Interaction, button: discord.ui.Button):
        doc, channel = await _get_owned(interaction)
        if not doc:
            return
        await channel.set_permissions(interaction.guild.default_role, view_channel=None)
        await Database.db.temp_vcs.update_one({"_id": doc["_id"]}, {"$set": {"hidden": False}})
        await interaction.response.send_message(
            embed=success_embed("👁️ Visible", "Your channel is now visible to everyone."),
            ephemeral=True,
        )

    @discord.ui.button(label="Rename", emoji="✏️", style=discord.ButtonStyle.primary,
                       custom_id="vc_panel:rename", row=0)
    async def rename(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RenameModal())

    # ── Row 1: Channel settings ───────────────────────────────────────────────

    @discord.ui.button(label="Limit", emoji="👥", style=discord.ButtonStyle.secondary,
                       custom_id="vc_panel:limit", row=1)
    async def limit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(LimitModal())

    @discord.ui.button(label="Bitrate", emoji="📻", style=discord.ButtonStyle.secondary,
                       custom_id="vc_panel:bitrate", row=1)
    async def bitrate(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BitrateModal())

    @discord.ui.button(label="Kick", emoji="👢", style=discord.ButtonStyle.danger,
                       custom_id="vc_panel:kick", row=1)
    async def kick(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MemberActionModal("kick"))

    @discord.ui.button(label="Allow", emoji="✅", style=discord.ButtonStyle.success,
                       custom_id="vc_panel:allow", row=1)
    async def allow(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MemberActionModal("allow"))

    @discord.ui.button(label="Deny", emoji="❌", style=discord.ButtonStyle.danger,
                       custom_id="vc_panel:deny", row=1)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MemberActionModal("deny"))

    # ── Row 2: Ownership / info / utility ─────────────────────────────────────

    @discord.ui.button(label="Transfer", emoji="🔄", style=discord.ButtonStyle.primary,
                       custom_id="vc_panel:transfer", row=2)
    async def transfer(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MemberActionModal("transfer"))

    @discord.ui.button(label="Claim", emoji="🏴", style=discord.ButtonStyle.success,
                       custom_id="vc_panel:claim", row=2)
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send(
                embed=error_embed("Not in a VC", "You must be in a voice channel to claim it."),
                ephemeral=True,
            )
            return
        vc = interaction.user.voice.channel
        doc = await Database.db.temp_vcs.find_one({"guild_id": interaction.guild_id, "channel_id": vc.id})
        if not doc:
            await interaction.followup.send(
                embed=error_embed("Not a Temp VC", "This is not a temporary voice channel."),
                ephemeral=True,
            )
            return
        owner = interaction.guild.get_member(doc["owner_id"])
        if owner and owner.voice and owner.voice.channel and owner.voice.channel.id == vc.id:
            await interaction.followup.send(
                embed=error_embed("Owner Still Present", f"The owner {owner.mention} is still in the channel."),
                ephemeral=True,
            )
            return
        await Database.db.temp_vcs.update_one({"_id": doc["_id"]}, {"$set": {"owner_id": interaction.user.id}})
        await interaction.followup.send(
            embed=success_embed("🏴 Claimed", f"You are now the owner of **{vc.name}**."),
            ephemeral=True,
        )

    @discord.ui.button(label="Info", emoji="ℹ️", style=discord.ButtonStyle.secondary,
                       custom_id="vc_panel:info", row=2)
    async def info(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send(
                embed=error_embed("Not in a VC", "You must be in a voice channel to view its info."),
                ephemeral=True,
            )
            return
        vc = interaction.user.voice.channel
        doc = await Database.db.temp_vcs.find_one({"guild_id": interaction.guild_id, "channel_id": vc.id})
        if not doc:
            await interaction.followup.send(
                embed=error_embed("Not a Temp VC", "This is not a temporary voice channel."),
                ephemeral=True,
            )
            return
        owner = interaction.guild.get_member(doc["owner_id"])
        embed = primary_embed(f"🔊 {vc.name}", "")
        embed.add_field(name="Owner", value=owner.mention if owner else "Unknown", inline=True)
        embed.add_field(
            name="Members",
            value=f"{len(vc.members)}/{vc.user_limit if vc.user_limit else '∞'}",
            inline=True,
        )
        embed.add_field(name="Bitrate", value=f"{vc.bitrate // 1000} kbps", inline=True)
        embed.add_field(name="Locked", value="🔒 Yes" if doc.get("locked") else "🔓 No", inline=True)
        embed.add_field(name="Hidden", value="👻 Yes" if doc.get("hidden") else "👁️ No", inline=True)
        created = doc.get("created_at")
        if created:
            embed.add_field(name="Created", value=discord.utils.format_dt(created, "R"), inline=True)
        if vc.members:
            embed.add_field(
                name="Current Members",
                value="\n".join(m.mention for m in vc.members[:10]),
                inline=False,
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="Delete", emoji="🗑️", style=discord.ButtonStyle.danger,
                       custom_id="vc_panel:delete", row=2)
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        doc, channel = await _get_owned(interaction)
        if not doc:
            return
        await interaction.response.defer(ephemeral=True)
        await Database.db.temp_vcs.delete_one({"_id": doc["_id"]})
        try:
            await channel.delete(reason=f"Temp VC deleted via panel by owner {interaction.user}")
        except discord.HTTPException:
            pass
        await interaction.followup.send(
            embed=success_embed("🗑️ Deleted", "Your temporary voice channel has been deleted."),
            ephemeral=True,
        )

    @discord.ui.button(label="List", emoji="📋", style=discord.ButtonStyle.secondary,
                       custom_id="vc_panel:list", row=2)
    async def list_vcs(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        docs = await Database.db.temp_vcs.find({"guild_id": interaction.guild_id}).to_list(length=50)
        if not docs:
            await interaction.followup.send(
                embed=info_embed("No Active Channels", "There are no active temporary voice channels right now."),
                ephemeral=True,
            )
            return
        embed = primary_embed(f"🔊 Active Temp VCs — {len(docs)}", "")
        for doc in docs:
            ch = interaction.guild.get_channel(doc["channel_id"])
            ow = interaction.guild.get_member(doc["owner_id"])
            if ch:
                limit = ch.user_limit if ch.user_limit else "∞"
                flags = ("🔒" if doc.get("locked") else "") + ("👻" if doc.get("hidden") else "")
                embed.add_field(
                    name=f"{flags} {ch.name}".strip(),
                    value=f"👑 {ow.mention if ow else 'Unknown'} | 👥 {len(ch.members)}/{limit}",
                    inline=False,
                )
        await interaction.followup.send(embed=embed, ephemeral=True)


# ── Panel embed builder ───────────────────────────────────────────────────────

def build_panel_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🔊 Voice Channel Control Panel",
        description=(
            "Use the buttons below to manage your **temporary voice channel**.\n"
            "First, join the **hub voice channel** to create your own channel.\n"
            "All responses are private — only you can see them."
        ),
        color=0x5865F2,
    )
    embed.add_field(
        name="🔒 Lock / 🔓 Unlock",
        value="Toggle whether new members can join your channel.",
        inline=False,
    )
    embed.add_field(
        name="👻 Hide / 👁️ Show",
        value="Toggle whether your channel is visible in the channel list.",
        inline=False,
    )
    embed.add_field(
        name="✏️ Rename",
        value="Give your channel a custom name.",
        inline=False,
    )
    embed.add_field(
        name="👥 Limit / 📻 Bitrate",
        value="Set the user limit (0 = unlimited) or audio bitrate.",
        inline=False,
    )
    embed.add_field(
        name="👢 Kick / ✅ Allow / ❌ Deny",
        value="Control who can or can't be in your channel by User ID.",
        inline=False,
    )
    embed.add_field(
        name="🔄 Transfer / 🏴 Claim",
        value="Hand off ownership to someone in your VC, or claim an abandoned one.",
        inline=False,
    )
    embed.add_field(
        name="ℹ️ Info / 📋 List / 🗑️ Delete",
        value="View details about your VC, list all active VCs, or delete yours.",
        inline=False,
    )
    embed.set_footer(text="Only the channel owner can use management commands.")
    return embed
