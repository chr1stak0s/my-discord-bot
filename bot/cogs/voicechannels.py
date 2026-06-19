import discord
from discord import app_commands
from discord.ext import commands
import datetime
import logging
from database import Database, get_guild_config, update_guild_config
from utils import success_embed, error_embed, info_embed, primary_embed, is_admin
from views.vc_panel import VCPanelView, build_panel_embed

logger = logging.getLogger(__name__)


def _build_vc_name(pattern: str, member: discord.Member, count: int) -> str:
    name = pattern or "🔊 {username}'s Channel"
    name = name.replace("{username}", member.display_name[:20])
    name = name.replace("{count}", str(count))
    game = next((a.name for a in member.activities if isinstance(a, discord.Game)), None)
    name = name.replace("{game}", game[:20] if game else "Channel")
    return name[:100] or f"{member.display_name}'s Channel"


class VoiceChannels(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    vc_group = app_commands.Group(name="vc", description="Temporary voice channel commands")

    async def _get_owned_vc(self, interaction: discord.Interaction) -> tuple[dict | None, discord.VoiceChannel | None]:
        doc = await Database.db.temp_vcs.find_one({
            "guild_id": interaction.guild_id,
            "owner_id": interaction.user.id,
        })
        if not doc:
            await interaction.response.send_message(
                embed=error_embed("No Channel", "You don't own a temporary voice channel. Join the hub channel to create one."),
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

    # ── Admin: Setup ──────────────────────────────────────────────────────────

    @vc_group.command(name="setup", description="Add or update a hub voice channel that creates temp VCs")
    @app_commands.describe(
        hub_channel="Voice channel users join to get their own temp VC",
        category="Category where temp VCs are created (defaults to hub's category)",
        default_limit="Default user limit per VC (0 = unlimited)",
        name_pattern="Channel name pattern — variables: {username} {count} {game}",
    )
    @is_admin()
    async def setup(
        self,
        interaction: discord.Interaction,
        hub_channel: discord.VoiceChannel,
        category: discord.CategoryChannel = None,
        default_limit: int = 0,
        name_pattern: str = "🔊 {username}'s Channel",
    ):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        hubs: list = list(cfg.get("vc_hubs", []))
        new_hub = {
            "hub_channel_id": hub_channel.id,
            "category_id": category.id if category else None,
            "default_limit": max(0, min(99, default_limit)),
            "name_pattern": name_pattern,
        }
        updated = False
        for i, h in enumerate(hubs):
            if h.get("hub_channel_id") == hub_channel.id:
                hubs[i] = new_hub
                updated = True
                break
        if not updated:
            hubs.append(new_hub)
        await update_guild_config(interaction.guild_id, {"vc_hubs": hubs})
        action = "Updated" if updated else "Added"
        embed = success_embed(
            f"✅ Hub {action}",
            f"{hub_channel.mention} is now a hub channel. Users who join it will get their own temp VC.\n"
            f"**Total hub channels:** {len(hubs)}",
        )
        embed = success_embed("✅ Temp VC System Ready", "Configuration saved! Users can now join the hub channel to get their own voice channel.")
        embed.add_field(name="Hub Channel", value=hub_channel.mention, inline=True)
        embed.add_field(name="Category", value=category.mention if category else "Hub's category", inline=True)
        embed.add_field(name="Default Limit", value=str(default_limit) if default_limit else "Unlimited", inline=True)
        default_pattern = "🔊 {username}'s Channel"
        embed.add_field(name="Name Pattern", value=f"`{name_pattern or default_pattern}`", inline=True)
        embed.add_field(name="Variables", value="`{username}` — display name\n`{count}` — VC number\n`{game}` — current game", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @vc_group.command(name="removehub", description="Remove a hub voice channel from the temp VC system")
    @app_commands.describe(hub_channel="The hub voice channel to remove")
    @is_admin()
    async def removehub(self, interaction: discord.Interaction, hub_channel: discord.VoiceChannel):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        hubs: list = list(cfg.get("vc_hubs", []))
        new_hubs = [h for h in hubs if h.get("hub_channel_id") != hub_channel.id]
        if len(new_hubs) == len(hubs):
            await interaction.followup.send(
                embed=error_embed("Not a Hub", f"{hub_channel.mention} is not configured as a hub channel."),
                ephemeral=True,
            )
            return
        await update_guild_config(interaction.guild_id, {"vc_hubs": new_hubs})
        remaining = f"**Remaining hubs:** {len(new_hubs)}" if new_hubs else "No hub channels remaining — temp VC system is now disabled."
        await interaction.followup.send(
            embed=success_embed("Hub Removed", f"{hub_channel.mention} has been removed.\n{remaining}"),
            ephemeral=True,
        )

    @vc_group.command(name="config", description="View all configured hub channels and their settings")
    @is_admin()
    async def config(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        hubs: list = cfg.get("vc_hubs", [])
        active = await Database.db.temp_vcs.count_documents({"guild_id": interaction.guild_id})
        if not hubs:
            embed = info_embed("🔊 Temp VC Configuration", "No hub channels configured yet.\nUse `/vc setup` to add one.")
            embed.add_field(name="Active Temp VCs", value=str(active), inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        embed = info_embed(f"🔊 Temp VC — {len(hubs)} Hub(s) Configured", "")
        default_pattern = "🔊 {username}'s Channel"
        for i, h in enumerate(hubs, 1):
            ch = interaction.guild.get_channel(h.get("hub_channel_id"))
            cat = interaction.guild.get_channel(h.get("category_id"))
            limit = h.get("default_limit", 0)
            cat_str = cat.mention if cat else "Hub's category"
            pattern_str = h.get("name_pattern", default_pattern)
            limit_str = str(limit) if limit else "Unlimited"
            embed.add_field(
                name=f"Hub {i} — {ch.name if ch else 'Deleted Channel'}",
                value=(
                    f"**Channel:** {ch.mention if ch else '❌ Not found'}\n"
                    f"**Category:** {cat_str}\n"
                    f"**Limit:** {limit_str}\n"
                    f"**Pattern:** `{pattern_str}`"
                ),
                inline=False,
            )
        embed.add_field(name="Active Temp VCs", value=str(active), inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @vc_group.command(name="reset", description="Remove ALL hub channels and disable the temp VC system")
    @is_admin()
    async def reset(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await update_guild_config(interaction.guild_id, {"vc_hubs": []})
        await interaction.followup.send(
            embed=success_embed("Reset", "All hub channels have been removed. The temp VC system is now disabled."),
            ephemeral=True,
        )

    @vc_group.command(name="panel", description="Send the VC control panel embed to a channel")
    @app_commands.describe(channel="The text channel where the panel will be posted")
    @is_admin()
    async def panel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await interaction.response.defer(ephemeral=True)
        try:
            await channel.send(embed=build_panel_embed(), view=VCPanelView())
            await interaction.followup.send(
                embed=success_embed("✅ Panel Sent", f"The voice channel control panel has been posted in {channel.mention}."),
                ephemeral=True,
            )
            logger.info(f"VC panel posted in #{channel.name} by {interaction.user} in {interaction.guild.name}")
        except discord.Forbidden:
            await interaction.followup.send(
                embed=error_embed("No Permission", f"I don't have permission to send messages in {channel.mention}."),
                ephemeral=True,
            )
        except discord.HTTPException as e:
            await interaction.followup.send(embed=error_embed("Failed", str(e)), ephemeral=True)


    @vc_group.command(name="forcedelete", description="Force delete any temporary voice channel")
    @app_commands.describe(channel="The temp VC to delete")
    @is_admin()
    async def forcedelete(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        await interaction.response.defer(ephemeral=True)
        doc = await Database.db.temp_vcs.find_one({"guild_id": interaction.guild_id, "channel_id": channel.id})
        if not doc:
            await interaction.followup.send(embed=error_embed("Not a Temp VC", "That channel is not tracked as a temporary VC."), ephemeral=True)
            return
        await Database.db.temp_vcs.delete_one({"_id": doc["_id"]})
        try:
            await channel.delete(reason=f"Force deleted by admin {interaction.user}")
        except discord.HTTPException:
            pass
        await interaction.followup.send(embed=success_embed("Deleted", f"**{channel.name}** has been force deleted."), ephemeral=True)

    @vc_group.command(name="forcetransfer", description="Force transfer ownership of any temp VC")
    @app_commands.describe(channel="The temp VC", member="New owner")
    @is_admin()
    async def forcetransfer(self, interaction: discord.Interaction, channel: discord.VoiceChannel, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        doc = await Database.db.temp_vcs.find_one({"guild_id": interaction.guild_id, "channel_id": channel.id})
        if not doc:
            await interaction.followup.send(embed=error_embed("Not a Temp VC", "That is not a tracked temporary VC."), ephemeral=True)
            return
        await Database.db.temp_vcs.update_one({"_id": doc["_id"]}, {"$set": {"owner_id": member.id}})
        await interaction.followup.send(
            embed=success_embed("Transferred", f"**{channel.name}** ownership transferred to {member.mention}."),
            ephemeral=True,
        )

    # ── Owner commands ────────────────────────────────────────────────────────

    @vc_group.command(name="rename", description="Rename your temporary voice channel")
    @app_commands.describe(name="New channel name")
    async def rename(self, interaction: discord.Interaction, name: str):
        doc, channel = await self._get_owned_vc(interaction)
        if not doc:
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await channel.edit(name=name[:100])
            await interaction.followup.send(embed=success_embed("Renamed", f"Your channel has been renamed to **{name}**."), ephemeral=True)
        except discord.HTTPException as e:
            await interaction.followup.send(embed=error_embed("Failed", f"Could not rename: {e}"), ephemeral=True)

    @vc_group.command(name="limit", description="Set the user limit for your voice channel")
    @app_commands.describe(limit="User limit (0 = unlimited, max 99)")
    async def limit(self, interaction: discord.Interaction, limit: int):
        doc, channel = await self._get_owned_vc(interaction)
        if not doc:
            return
        limit = max(0, min(99, limit))
        await interaction.response.defer(ephemeral=True)
        await channel.edit(user_limit=limit)
        label = str(limit) if limit else "Unlimited"
        await interaction.followup.send(embed=success_embed("Limit Set", f"User limit set to **{label}**."), ephemeral=True)

    @vc_group.command(name="bitrate", description="Set the bitrate of your voice channel")
    @app_commands.describe(kbps="Bitrate in kbps (8–384)")
    async def bitrate(self, interaction: discord.Interaction, kbps: int):
        doc, channel = await self._get_owned_vc(interaction)
        if not doc:
            return
        kbps = max(8, min(384, kbps))
        await interaction.response.defer(ephemeral=True)
        try:
            await channel.edit(bitrate=kbps * 1000)
            await interaction.followup.send(embed=success_embed("Bitrate Set", f"Bitrate set to **{kbps} kbps**."), ephemeral=True)
        except discord.HTTPException as e:
            await interaction.followup.send(embed=error_embed("Failed", f"Could not set bitrate: {e}"), ephemeral=True)

    @vc_group.command(name="lock", description="Lock your voice channel — no new members can join")
    async def lock(self, interaction: discord.Interaction):
        doc, channel = await self._get_owned_vc(interaction)
        if not doc:
            return
        await interaction.response.defer(ephemeral=True)
        await channel.set_permissions(interaction.guild.default_role, connect=False)
        await Database.db.temp_vcs.update_one({"_id": doc["_id"]}, {"$set": {"locked": True}})
        await interaction.followup.send(embed=success_embed("🔒 Locked", "Your channel is locked. No new members can join."), ephemeral=True)

    @vc_group.command(name="unlock", description="Unlock your voice channel so anyone can join")
    async def unlock(self, interaction: discord.Interaction):
        doc, channel = await self._get_owned_vc(interaction)
        if not doc:
            return
        await interaction.response.defer(ephemeral=True)
        await channel.set_permissions(interaction.guild.default_role, connect=None)
        await Database.db.temp_vcs.update_one({"_id": doc["_id"]}, {"$set": {"locked": False}})
        await interaction.followup.send(embed=success_embed("🔓 Unlocked", "Your channel is now open to everyone."), ephemeral=True)

    @vc_group.command(name="hide", description="Hide your voice channel from the server")
    async def hide(self, interaction: discord.Interaction):
        doc, channel = await self._get_owned_vc(interaction)
        if not doc:
            return
        await interaction.response.defer(ephemeral=True)
        await channel.set_permissions(interaction.guild.default_role, view_channel=False)
        await Database.db.temp_vcs.update_one({"_id": doc["_id"]}, {"$set": {"hidden": True}})
        await interaction.followup.send(embed=success_embed("👻 Hidden", "Your channel is now hidden from the server."), ephemeral=True)

    @vc_group.command(name="show", description="Make your voice channel visible to everyone")
    async def show(self, interaction: discord.Interaction):
        doc, channel = await self._get_owned_vc(interaction)
        if not doc:
            return
        await interaction.response.defer(ephemeral=True)
        await channel.set_permissions(interaction.guild.default_role, view_channel=None)
        await Database.db.temp_vcs.update_one({"_id": doc["_id"]}, {"$set": {"hidden": False}})
        await interaction.followup.send(embed=success_embed("👁️ Visible", "Your channel is now visible to everyone."), ephemeral=True)

    @vc_group.command(name="kick", description="Kick a member from your voice channel")
    @app_commands.describe(member="Member to kick")
    async def kick(self, interaction: discord.Interaction, member: discord.Member):
        doc, channel = await self._get_owned_vc(interaction)
        if not doc:
            return
        if member.id == interaction.user.id:
            await interaction.response.send_message(embed=error_embed("Can't Kick Yourself", "You cannot kick yourself from your own channel."), ephemeral=True)
            return
        if not (member.voice and member.voice.channel and member.voice.channel.id == channel.id):
            await interaction.response.send_message(embed=error_embed("Not in Channel", f"{member.mention} is not in your voice channel."), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await member.move_to(None, reason=f"Kicked from temp VC by owner {interaction.user}")
        await interaction.followup.send(embed=success_embed("Kicked", f"{member.mention} has been kicked from your channel."), ephemeral=True)

    @vc_group.command(name="allow", description="Allow a specific member to join your channel (bypasses lock/hide)")
    @app_commands.describe(member="Member to allow")
    async def allow(self, interaction: discord.Interaction, member: discord.Member):
        doc, channel = await self._get_owned_vc(interaction)
        if not doc:
            return
        await interaction.response.defer(ephemeral=True)
        await channel.set_permissions(member, connect=True, view_channel=True)
        await interaction.followup.send(embed=success_embed("Allowed", f"{member.mention} can now see and join your channel."), ephemeral=True)

    @vc_group.command(name="deny", description="Deny a member from joining your channel")
    @app_commands.describe(member="Member to deny")
    async def deny(self, interaction: discord.Interaction, member: discord.Member):
        doc, channel = await self._get_owned_vc(interaction)
        if not doc:
            return
        await interaction.response.defer(ephemeral=True)
        if member.voice and member.voice.channel and member.voice.channel.id == channel.id:
            await member.move_to(None, reason=f"Denied from temp VC by owner {interaction.user}")
        await channel.set_permissions(member, connect=False, view_channel=False)
        await interaction.followup.send(embed=success_embed("Denied", f"{member.mention} cannot see or join your channel."), ephemeral=True)

    @vc_group.command(name="transfer", description="Transfer ownership of your channel to another member in it")
    @app_commands.describe(member="Member to transfer ownership to (must be in the channel)")
    async def transfer(self, interaction: discord.Interaction, member: discord.Member):
        doc, channel = await self._get_owned_vc(interaction)
        if not doc:
            return
        if member.id == interaction.user.id:
            await interaction.response.send_message(embed=error_embed("Already Owner", "You are already the owner."), ephemeral=True)
            return
        if not (member.voice and member.voice.channel and member.voice.channel.id == channel.id):
            await interaction.response.send_message(
                embed=error_embed("Not in Channel", f"{member.mention} must be in your voice channel to receive ownership."),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        await Database.db.temp_vcs.update_one({"_id": doc["_id"]}, {"$set": {"owner_id": member.id}})
        await interaction.followup.send(
            embed=success_embed("Ownership Transferred", f"**{member.display_name}** is now the owner of {channel.mention}."),
            ephemeral=True,
        )
        try:
            await member.send(embed=info_embed(
                "🔊 VC Ownership",
                f"You are now the owner of **{channel.name}** in **{interaction.guild.name}**.\nUse `/vc` commands to manage it.",
            ))
        except discord.HTTPException:
            pass

    @vc_group.command(name="claim", description="Claim an ownerless temporary voice channel you are in")
    async def claim(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send(embed=error_embed("Not in a VC", "You must be in a voice channel to claim it."), ephemeral=True)
            return
        vc = interaction.user.voice.channel
        doc = await Database.db.temp_vcs.find_one({"guild_id": interaction.guild_id, "channel_id": vc.id})
        if not doc:
            await interaction.followup.send(embed=error_embed("Not a Temp VC", "This is not a temporary voice channel."), ephemeral=True)
            return
        owner = interaction.guild.get_member(doc["owner_id"])
        if owner and owner.voice and owner.voice.channel and owner.voice.channel.id == vc.id:
            await interaction.followup.send(
                embed=error_embed("Owner Still Present", f"The owner {owner.mention} is still in the channel."),
                ephemeral=True,
            )
            return
        await Database.db.temp_vcs.update_one({"_id": doc["_id"]}, {"$set": {"owner_id": interaction.user.id}})
        await interaction.followup.send(embed=success_embed("Channel Claimed", f"You are now the owner of **{vc.name}**."), ephemeral=True)

    @vc_group.command(name="info", description="View info about the temporary voice channel you are in")
    async def info(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send(embed=error_embed("Not in a VC", "You must be in a voice channel."), ephemeral=True)
            return
        vc = interaction.user.voice.channel
        doc = await Database.db.temp_vcs.find_one({"guild_id": interaction.guild_id, "channel_id": vc.id})
        if not doc:
            await interaction.followup.send(embed=error_embed("Not a Temp VC", "This is not a temporary voice channel."), ephemeral=True)
            return
        owner = interaction.guild.get_member(doc["owner_id"])
        embed = primary_embed(f"🔊 {vc.name}", "")
        embed.add_field(name="Owner", value=owner.mention if owner else "Unknown", inline=True)
        embed.add_field(name="Members", value=f"{len(vc.members)}/{vc.user_limit if vc.user_limit else '∞'}", inline=True)
        embed.add_field(name="Bitrate", value=f"{vc.bitrate // 1000} kbps", inline=True)
        embed.add_field(name="Locked", value="🔒 Yes" if doc.get("locked") else "🔓 No", inline=True)
        embed.add_field(name="Hidden", value="👻 Yes" if doc.get("hidden") else "👁️ No", inline=True)
        created = doc.get("created_at")
        if created:
            embed.add_field(name="Created", value=discord.utils.format_dt(created, "R"), inline=True)
        if vc.members:
            embed.add_field(name="Current Members", value="\n".join(m.mention for m in vc.members[:10]), inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @vc_group.command(name="delete", description="Delete your temporary voice channel early")
    async def delete(self, interaction: discord.Interaction):
        doc, channel = await self._get_owned_vc(interaction)
        if not doc:
            return
        await interaction.response.defer(ephemeral=True)
        await Database.db.temp_vcs.delete_one({"_id": doc["_id"]})
        try:
            await channel.delete(reason=f"Temp VC manually deleted by owner {interaction.user}")
        except discord.HTTPException:
            pass
        await interaction.followup.send(embed=success_embed("Deleted", "Your temporary voice channel has been deleted."), ephemeral=True)

    @vc_group.command(name="list", description="List all active temporary voice channels in the server")
    async def list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        docs = await Database.db.temp_vcs.find({"guild_id": interaction.guild_id}).to_list(length=50)
        if not docs:
            await interaction.followup.send(embed=info_embed("No Active Channels", "There are no active temporary voice channels right now."), ephemeral=True)
            return
        embed = primary_embed(f"🔊 Active Temp VCs — {len(docs)}", "")
        for doc in docs:
            channel = interaction.guild.get_channel(doc["channel_id"])
            owner = interaction.guild.get_member(doc["owner_id"])
            if channel:
                limit = channel.user_limit if channel.user_limit else "∞"
                flags = ("🔒" if doc.get("locked") else "") + ("👻" if doc.get("hidden") else "")
                name_display = f"{flags} {channel.name}" if flags else channel.name
                embed.add_field(
                    name=name_display,
                    value=f"👑 {owner.mention if owner else 'Unknown'} | 👥 {len(channel.members)}/{limit}",
                    inline=False,
                )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── Voice state listener ──────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        guild = member.guild
        cfg = await get_guild_config(guild.id)
         # Build hub lookup: {hub_channel_id: hub_config_dict}
        hubs: list = cfg.get("vc_hubs", [])
        hub_map: dict = {h["hub_channel_id"]: h for h in hubs if "hub_channel_id" in h}
        hub_ids: set = set(hub_map.keys())
        # Joined a hub → create temp VC and move user in
        if after.channel and after.channel.id in hub_ids:
            hub_cfg = hub_map[after.channel.id]
            count = await Database.db.temp_vcs.count_documents({"guild_id": guild.id}) + 1
            pattern = hub_cfg.get("name_pattern", "🔊 {username}'s Channel")
            name = _build_vc_name(pattern, member, count)
            limit = hub_cfg.get("default_limit", 0)
            category_id = hub_cfg.get("category_id")
            category = guild.get_channel(category_id) if category_id else after.channel.category

            try:
                new_vc = await guild.create_voice_channel(
                    name,
                    category=category,
                    user_limit=limit,
                    reason=f"Temp VC created for {member}",
                )
                await member.move_to(new_vc, reason="Moved to personal temp VC")
                await Database.db.temp_vcs.insert_one({
                    "guild_id": guild.id,
                    "channel_id": new_vc.id,
                    "owner_id": member.id,
                    "created_at": datetime.datetime.utcnow(),
                    "locked": False,
                    "hidden": False,
                })
                logger.info(f"Created temp VC '{name}' for {member} in {guild.name}")
            except discord.HTTPException as e:
                logger.error(f"Failed to create temp VC for {member} in {guild.name}: {e}")

        # Left a channel → auto-delete if it's an empty temp VC (skip hub channels)
        if before.channel and before.channel.id not in hub_ids:
            if len(before.channel.members) == 0:
                doc = await Database.db.temp_vcs.find_one({
                    "guild_id": guild.id,
                    "channel_id": before.channel.id,
                })
                if doc:
                    await Database.db.temp_vcs.delete_one({"_id": doc["_id"]})
                    try:
                        await before.channel.delete(reason="Temp VC auto-deleted: empty")
                        logger.info(f"Auto-deleted empty temp VC '{before.channel.name}' in {guild.name}")
                    except discord.HTTPException as e:
                        logger.error(f"Failed to auto-delete temp VC in {guild.name}: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceChannels(bot))
