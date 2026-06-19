"""
Private Rooms — locked, hidden voice channels with role/member-based access.
Useful for RP servers, private support sessions, staff channels, etc.

Command group: /room
Hub setup: admins designate hub voice channels. When a user joins a hub,
           the bot creates a private VC — hidden and locked for @everyone —
           and moves the owner in. Only the owner can control access.
"""
import discord
from discord import app_commands
from discord.ext import commands
import datetime
import logging
from database import Database, get_guild_config, update_guild_config
from utils import success_embed, error_embed, info_embed, primary_embed, is_admin

logger = logging.getLogger(__name__)


def _build_room_name(pattern: str, member: discord.Member, count: int) -> str:
    name = pattern or "🔒 {username}'s Room"
    name = name.replace("{username}", member.display_name[:20])
    name = name.replace("{count}", str(count))
    return name[:100] or f"🔒 {member.display_name}'s Room"


class PrivateRooms(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    room_group = app_commands.Group(name="room", description="Private voice room commands")

    # ── Internal helper ───────────────────────────────────────────────────────

    async def _get_owned_room(
        self, interaction: discord.Interaction
    ) -> tuple[dict | None, discord.VoiceChannel | None]:
        doc = await Database.db.private_rooms.find_one({
            "guild_id": interaction.guild_id,
            "owner_id": interaction.user.id,
        })
        if not doc:
            await interaction.response.send_message(
                embed=error_embed(
                    "No Room",
                    "You don't own a private room.\nJoin a hub channel to create one.",
                ),
                ephemeral=True,
            )
            return None, None
        channel = interaction.guild.get_channel(doc["channel_id"])
        if not channel:
            await Database.db.private_rooms.delete_one({"_id": doc["_id"]})
            await interaction.response.send_message(
                embed=error_embed("Not Found", "Your room no longer exists."),
                ephemeral=True,
            )
            return None, None
        return doc, channel

    # ── Admin: Hub management ─────────────────────────────────────────────────

    @room_group.command(name="setup", description="Add or update a hub voice channel that creates private rooms")
    @app_commands.describe(
        hub_channel="Voice channel users join to create a private room",
        category="Category where rooms are created (defaults to hub's category)",
        name_pattern="Room name pattern — variables: {username} {count}",
    )
    @is_admin()
    async def setup(
        self,
        interaction: discord.Interaction,
        hub_channel: discord.VoiceChannel,
        category: discord.CategoryChannel = None,
        name_pattern: str = "🔒 {username}'s Room",
    ):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        hubs: list = list(cfg.get("room_hubs", []))

        new_hub = {
            "hub_channel_id": hub_channel.id,
            "category_id": category.id if category else None,
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

        await update_guild_config(interaction.guild_id, {"room_hubs": hubs})
        action = "Updated" if updated else "Added"
        embed = success_embed(
            f"✅ Room Hub {action}",
            f"{hub_channel.mention} is now a private room hub.\n**Total hubs:** {len(hubs)}",
        )
        embed.add_field(name="Hub Channel", value=hub_channel.mention, inline=True)
        embed.add_field(name="Category", value=category.mention if category else "Hub's category", inline=True)
        embed.add_field(name="Name Pattern", value=f"`{name_pattern}`", inline=False)
        embed.add_field(name="Variables", value="`{username}` — display name\n`{count}` — room number", inline=False)
        embed.add_field(
            name="How it works",
            value=(
                "When a user joins this hub, the bot creates a voice channel that is:\n"
                "• **Hidden** from everyone\n"
                "• **Locked** — no one else can join\n"
                "• Only the owner can grant access via `/room addrole` and `/room addmember`"
            ),
            inline=False,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @room_group.command(name="removehub", description="Remove a private room hub channel")
    @app_commands.describe(hub_channel="The hub channel to remove")
    @is_admin()
    async def removehub(self, interaction: discord.Interaction, hub_channel: discord.VoiceChannel):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        original: list = cfg.get("room_hubs", [])
        new_hubs = [h for h in original if h.get("hub_channel_id") != hub_channel.id]
        if len(new_hubs) == len(original):
            await interaction.followup.send(
                embed=error_embed("Not a Hub", f"{hub_channel.mention} is not configured as a room hub."),
                ephemeral=True,
            )
            return
        await update_guild_config(interaction.guild_id, {"room_hubs": new_hubs})
        note = f"**Remaining hubs:** {len(new_hubs)}" if new_hubs else "No hubs remaining — private room system is now disabled."
        await interaction.followup.send(
            embed=success_embed("Hub Removed", f"{hub_channel.mention} removed.\n{note}"),
            ephemeral=True,
        )

    @room_group.command(name="config", description="View all configured private room hubs")
    @is_admin()
    async def config(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        hubs: list = cfg.get("room_hubs", [])
        active = await Database.db.private_rooms.count_documents({"guild_id": interaction.guild_id})

        if not hubs:
            embed = info_embed("🔒 Private Room Configuration", "No hubs configured yet.\nUse `/room setup` to add one.")
            embed.add_field(name="Active Rooms", value=str(active), inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        embed = info_embed(f"🔒 Private Rooms — {len(hubs)} Hub(s) Configured", "")
        default_pattern = "🔒 {username}'s Room"
        for i, h in enumerate(hubs, 1):
            ch = interaction.guild.get_channel(h.get("hub_channel_id"))
            cat = interaction.guild.get_channel(h.get("category_id"))
            cat_str = cat.mention if cat else "Hub's category"
            pattern_str = h.get("name_pattern", default_pattern)
            embed.add_field(
                name=f"Hub {i} — {ch.name if ch else 'Deleted Channel'}",
                value=(
                    f"**Channel:** {ch.mention if ch else '❌ Not found'}\n"
                    f"**Category:** {cat_str}\n"
                    f"**Pattern:** `{pattern_str}`"
                ),
                inline=False,
            )
        embed.add_field(name="Active Rooms", value=str(active), inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @room_group.command(name="reset", description="Remove ALL room hubs and disable the private room system")
    @is_admin()
    async def reset(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await update_guild_config(interaction.guild_id, {"room_hubs": []})
        await interaction.followup.send(
            embed=success_embed("Reset", "All room hubs removed. Private room system is now disabled."),
            ephemeral=True,
        )

    @room_group.command(name="forcedelete", description="Force delete any private room")
    @app_commands.describe(channel="The private room to delete")
    @is_admin()
    async def forcedelete(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        await interaction.response.defer(ephemeral=True)
        doc = await Database.db.private_rooms.find_one({
            "guild_id": interaction.guild_id,
            "channel_id": channel.id,
        })
        if not doc:
            await interaction.followup.send(
                embed=error_embed("Not a Room", "That channel is not a tracked private room."),
                ephemeral=True,
            )
            return
        await Database.db.private_rooms.delete_one({"_id": doc["_id"]})
        try:
            await channel.delete(reason=f"Force deleted by admin {interaction.user}")
        except discord.HTTPException:
            pass
        await interaction.followup.send(
            embed=success_embed("Deleted", f"**{channel.name}** has been force deleted."),
            ephemeral=True,
        )

    @room_group.command(name="forcetransfer", description="Force transfer ownership of any private room")
    @app_commands.describe(channel="The private room", member="New owner")
    @is_admin()
    async def forcetransfer(
        self,
        interaction: discord.Interaction,
        channel: discord.VoiceChannel,
        member: discord.Member,
    ):
        await interaction.response.defer(ephemeral=True)
        doc = await Database.db.private_rooms.find_one({
            "guild_id": interaction.guild_id,
            "channel_id": channel.id,
        })
        if not doc:
            await interaction.followup.send(
                embed=error_embed("Not a Room", "That is not a tracked private room."),
                ephemeral=True,
            )
            return
        await Database.db.private_rooms.update_one(
            {"_id": doc["_id"]}, {"$set": {"owner_id": member.id}}
        )
        await interaction.followup.send(
            embed=success_embed("Transferred", f"**{channel.name}** ownership transferred to {member.mention}."),
            ephemeral=True,
        )

    @room_group.command(name="list", description="List all active private rooms (admin only)")
    @is_admin()
    async def list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        docs = await Database.db.private_rooms.find(
            {"guild_id": interaction.guild_id}
        ).to_list(length=50)
        if not docs:
            await interaction.followup.send(
                embed=info_embed("No Active Rooms", "No private rooms are currently active."),
                ephemeral=True,
            )
            return
        embed = primary_embed(f"🔒 Active Private Rooms — {len(docs)}", "")
        for doc in docs:
            ch = interaction.guild.get_channel(doc["channel_id"])
            ow = interaction.guild.get_member(doc["owner_id"])
            if ch:
                roles_count = len(doc.get("support_roles", []))
                members_count = len(doc.get("allowed_members", []))
                embed.add_field(
                    name=ch.name,
                    value=(
                        f"👑 {ow.mention if ow else 'Unknown'} | "
                        f"👥 {len(ch.members)} in VC | "
                        f"🎭 {roles_count} role(s) | "
                        f"✅ {members_count} member(s)"
                    ),
                    inline=False,
                )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── Owner: Access management ──────────────────────────────────────────────

    @room_group.command(name="name", description="Rename your private room")
    @app_commands.describe(name="New room name")
    async def name(self, interaction: discord.Interaction, name: str):
        doc, channel = await self._get_owned_room(interaction)
        if not doc:
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await channel.edit(name=name[:100])
            await interaction.followup.send(
                embed=success_embed("✏️ Renamed", f"Your room has been renamed to **{name}**."),
                ephemeral=True,
            )
        except discord.HTTPException as e:
            await interaction.followup.send(embed=error_embed("Failed", str(e)), ephemeral=True)

    @room_group.command(name="addrole", description="Grant a role access to see and join your private room")
    @app_commands.describe(role="The role to grant access to")
    async def addrole(self, interaction: discord.Interaction, role: discord.Role):
        doc, channel = await self._get_owned_room(interaction)
        if not doc:
            return
        await interaction.response.defer(ephemeral=True)
        support_roles: list = list(doc.get("support_roles", []))
        if role.id in support_roles:
            await interaction.followup.send(
                embed=error_embed("Already Added", f"{role.mention} already has access to your room."),
                ephemeral=True,
            )
            return
        support_roles.append(role.id)
        await Database.db.private_rooms.update_one(
            {"_id": doc["_id"]}, {"$set": {"support_roles": support_roles}}
        )
        await channel.set_permissions(role, view_channel=True, connect=True)
        await interaction.followup.send(
            embed=success_embed("🎭 Role Added", f"{role.mention} can now see and join your private room."),
            ephemeral=True,
        )

    @room_group.command(name="removerole", description="Revoke a role's access to your private room")
    @app_commands.describe(role="The role to remove access from")
    async def removerole(self, interaction: discord.Interaction, role: discord.Role):
        doc, channel = await self._get_owned_room(interaction)
        if not doc:
            return
        await interaction.response.defer(ephemeral=True)
        support_roles: list = list(doc.get("support_roles", []))
        if role.id not in support_roles:
            await interaction.followup.send(
                embed=error_embed("Not Added", f"{role.mention} doesn't have special access to your room."),
                ephemeral=True,
            )
            return
        support_roles.remove(role.id)
        await Database.db.private_rooms.update_one(
            {"_id": doc["_id"]}, {"$set": {"support_roles": support_roles}}
        )
        await channel.set_permissions(role, overwrite=None)
        await interaction.followup.send(
            embed=success_embed("🎭 Role Removed", f"{role.mention}'s access has been revoked."),
            ephemeral=True,
        )

    @room_group.command(name="addmember", description="Add a specific member to your private room")
    @app_commands.describe(member="The member to grant access to")
    async def addmember(self, interaction: discord.Interaction, member: discord.Member):
        doc, channel = await self._get_owned_room(interaction)
        if not doc:
            return
        if member.id == interaction.user.id:
            await interaction.response.send_message(
                embed=error_embed("That's You", "You already own this room."),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        allowed: list = list(doc.get("allowed_members", []))
        if member.id in allowed:
            await interaction.followup.send(
                embed=error_embed("Already Added", f"{member.mention} already has access."),
                ephemeral=True,
            )
            return
        allowed.append(member.id)
        await Database.db.private_rooms.update_one(
            {"_id": doc["_id"]}, {"$set": {"allowed_members": allowed}}
        )
        await channel.set_permissions(member, view_channel=True, connect=True)
        await interaction.followup.send(
            embed=success_embed("✅ Member Added", f"{member.mention} can now see and join your private room."),
            ephemeral=True,
        )
        try:
            await member.send(embed=info_embed(
                "🔒 Private Room Access",
                f"You have been granted access to **{channel.name}** in **{interaction.guild.name}**.\n"
                f"Granted by: {interaction.user.display_name}",
            ))
        except discord.HTTPException:
            pass

    @room_group.command(name="removemember", description="Revoke a member's access to your private room")
    @app_commands.describe(member="The member to remove access from")
    async def removemember(self, interaction: discord.Interaction, member: discord.Member):
        doc, channel = await self._get_owned_room(interaction)
        if not doc:
            return
        if member.id == interaction.user.id:
            await interaction.response.send_message(
                embed=error_embed("Can't Remove Yourself", "You can't remove your own access."),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        allowed: list = list(doc.get("allowed_members", []))
        if member.id in allowed:
            allowed.remove(member.id)
            await Database.db.private_rooms.update_one(
                {"_id": doc["_id"]}, {"$set": {"allowed_members": allowed}}
            )
        if member.voice and member.voice.channel and member.voice.channel.id == channel.id:
            await member.move_to(None, reason=f"Removed from private room by owner {interaction.user}")
        await channel.set_permissions(member, overwrite=None)
        await interaction.followup.send(
            embed=success_embed("❌ Member Removed", f"{member.mention}'s access has been revoked."),
            ephemeral=True,
        )

    @room_group.command(name="info", description="View info about your private room")
    async def info(self, interaction: discord.Interaction):
        doc, channel = await self._get_owned_room(interaction)
        if not doc:
            return
        await interaction.response.defer(ephemeral=True)

        embed = primary_embed(f"🔒 {channel.name}", "")
        embed.add_field(name="Owner", value=interaction.user.mention, inline=True)
        embed.add_field(name="In Room", value=str(len(channel.members)), inline=True)
        created = doc.get("created_at")
        if created:
            embed.add_field(name="Created", value=discord.utils.format_dt(created, "R"), inline=True)

        support_roles = doc.get("support_roles", [])
        if support_roles:
            role_mentions = [
                interaction.guild.get_role(rid).mention
                for rid in support_roles
                if interaction.guild.get_role(rid)
            ]
            if role_mentions:
                embed.add_field(name="Support Roles", value="\n".join(role_mentions), inline=False)

        allowed_members = doc.get("allowed_members", [])
        if allowed_members:
            member_mentions = [
                interaction.guild.get_member(mid).mention
                for mid in allowed_members
                if interaction.guild.get_member(mid)
            ]
            if member_mentions:
                embed.add_field(
                    name=f"Allowed Members ({len(member_mentions)})",
                    value="\n".join(member_mentions[:10]),
                    inline=False,
                )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @room_group.command(name="transfer", description="Transfer ownership of your room to a member currently in it")
    @app_commands.describe(member="Member in the room to transfer ownership to")
    async def transfer(self, interaction: discord.Interaction, member: discord.Member):
        doc, channel = await self._get_owned_room(interaction)
        if not doc:
            return
        if member.id == interaction.user.id:
            await interaction.response.send_message(
                embed=error_embed("Already Owner", "You are already the owner."),
                ephemeral=True,
            )
            return
        if not (member.voice and member.voice.channel and member.voice.channel.id == channel.id):
            await interaction.response.send_message(
                embed=error_embed("Not in Room", f"{member.mention} must be inside the room to receive ownership."),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        await Database.db.private_rooms.update_one(
            {"_id": doc["_id"]}, {"$set": {"owner_id": member.id}}
        )
        await interaction.followup.send(
            embed=success_embed("🔄 Transferred", f"{member.mention} is now the owner of this room."),
            ephemeral=True,
        )
        try:
            await member.send(embed=info_embed(
                "🔒 Room Ownership",
                f"You are now the owner of **{channel.name}** in **{interaction.guild.name}**.\n"
                f"Use `/room` commands to manage your room.",
            ))
        except discord.HTTPException:
            pass

    @room_group.command(name="delete", description="Delete your private room")
    async def delete(self, interaction: discord.Interaction):
        doc, channel = await self._get_owned_room(interaction)
        if not doc:
            return
        await interaction.response.defer(ephemeral=True)
        await Database.db.private_rooms.delete_one({"_id": doc["_id"]})
        try:
            await channel.delete(reason=f"Private room deleted by owner {interaction.user}")
        except discord.HTTPException:
            pass
        await interaction.followup.send(
            embed=success_embed("🗑️ Deleted", "Your private room has been deleted."),
            ephemeral=True,
        )

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

        hubs: list = cfg.get("room_hubs", [])
        hub_map: dict = {h["hub_channel_id"]: h for h in hubs if "hub_channel_id" in h}
        hub_ids: set = set(hub_map.keys())

        # Joined a hub → create a private room and move the user in
        if after.channel and after.channel.id in hub_ids:
            hub_cfg = hub_map[after.channel.id]
            count = await Database.db.private_rooms.count_documents({"guild_id": guild.id}) + 1
            pattern = hub_cfg.get("name_pattern", "🔒 {username}'s Room")
            name = _build_room_name(pattern, member, count)
            category_id = hub_cfg.get("category_id")
            category = guild.get_channel(category_id) if category_id else after.channel.category

            # Everyone is denied; only the owner and bot can see/join
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False, connect=False),
                member: discord.PermissionOverwrite(view_channel=True, connect=True),
                guild.me: discord.PermissionOverwrite(view_channel=True, connect=True, manage_channels=True),
            }

            try:
                new_room = await guild.create_voice_channel(
                    name,
                    category=category,
                    overwrites=overwrites,
                    reason=f"Private room created for {member}",
                )
                await member.move_to(new_room, reason="Moved to private room")
                await Database.db.private_rooms.insert_one({
                    "guild_id": guild.id,
                    "channel_id": new_room.id,
                    "owner_id": member.id,
                    "created_at": datetime.datetime.utcnow(),
                    "support_roles": [],
                    "allowed_members": [],
                })
                logger.info(f"Created private room '{name}' for {member} in {guild.name}")
            except discord.HTTPException as e:
                logger.error(f"Failed to create private room for {member} in {guild.name}: {e}")

        # Left a channel → auto-delete if it's an empty private room (skip hubs)
        if before.channel and before.channel.id not in hub_ids:
            if len(before.channel.members) == 0:
                doc = await Database.db.private_rooms.find_one({
                    "guild_id": guild.id,
                    "channel_id": before.channel.id,
                })
                if doc:
                    await Database.db.private_rooms.delete_one({"_id": doc["_id"]})
                    try:
                        await before.channel.delete(reason="Private room auto-deleted: empty")
                        logger.info(f"Auto-deleted empty private room '{before.channel.name}' in {guild.name}")
                    except discord.HTTPException as e:
                        logger.error(f"Failed to auto-delete private room in {guild.name}: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(PrivateRooms(bot))
