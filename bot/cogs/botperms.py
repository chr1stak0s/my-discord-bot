"""
/bot users  — interactive role-permission manager for every bot command.
Admins pick a category → pick a command → assign/remove roles via Discord's
native Role Select component.  Stored in MongoDB under guild_doc["command_roles"].
A global CommandTree check (wired in main.py) enforces these rules on every
slash command automatically — no changes needed to individual cogs.
"""
import discord
from discord import app_commands
from discord.ext import commands
import logging
from database import get_guild_config, update_guild_config
from utils import success_embed, error_embed, info_embed, primary_embed, is_admin

logger = logging.getLogger(__name__)

# ─── Full command registry ─────────────────────────────────────────────────────
# "Category Label" → {"group": "slash_group_name", "commands": [(name, desc), ...]}
# Use group="_top" for commands that have no parent group (e.g. /dm, /dmall).

REGISTRY: dict[str, dict] = {
    "🛡️ Moderation": {
        "group": "moderation",
        "commands": [
            ("ban",      "Ban a member"),
            ("unban",    "Unban a member"),
            ("kick",     "Kick a member"),
            ("timeout",  "Timeout a member"),
            ("mute",     "Mute a member"),
            ("unmute",   "Unmute a member"),
            ("warn",     "Warn a member"),
            ("warnings", "View member warnings"),
            ("clear",    "Clear messages"),
            ("slowmode", "Set slowmode"),
            ("lock",     "Lock a channel"),
            ("unlock",   "Unlock a channel"),
            ("nickname", "Change a nickname"),
        ],
    },
    "🎫 Tickets": {
        "group": "tickets",
        "commands": [
            ("setup",      "Setup ticket system"),
            ("panel",      "Send ticket panel"),
            ("add",        "Add user to ticket"),
            ("remove",     "Remove user from ticket"),
            ("rename",     "Rename a ticket"),
            ("claim",      "Claim a ticket"),
            ("unclaim",    "Unclaim a ticket"),
            ("close",      "Close a ticket"),
            ("delete",     "Delete a ticket"),
            ("transcript", "Get a ticket transcript"),
            ("view",       "View ticket stats"),
            ("addtype",    "Add ticket type"),
            ("removetype", "Remove ticket type"),
            ("listtypes",  "List ticket types"),
            ("customize",  "Customize the panel"),
            ("reset",      "Reset ticket system"),
        ],
    },
    "📋 Applications": {
        "group": "applications",
        "commands": [
            ("setup",     "Setup application system"),
            ("create",    "Create an application form"),
            ("delete",    "Delete an application form"),
            ("edit",      "Edit form questions"),
            ("panel",     "Send application panel"),
            ("view",      "View statistics"),
            ("open",      "Open applications"),
            ("close",     "Close applications"),
            ("customize", "Customize the panel"),
            ("reset",     "Reset applications"),
        ],
    },
    "💰 Economy": {
        "group": "economy",
        "commands": [
            ("balance",     "Check balance"),
            ("daily",       "Claim daily reward"),
            ("work",        "Work for coins"),
            ("deposit",     "Deposit to bank"),
            ("withdraw",    "Withdraw from bank"),
            ("pay",         "Send coins to a member"),
            ("leaderboard", "Economy leaderboard"),
        ],
    },
    "📊 Levels": {
        "group": "level",
        "commands": [
            ("rank",        "View your rank"),
            ("leaderboard", "XP leaderboard"),
            ("setlevel",    "Set a member's level"),
            ("toggle",      "Enable / disable leveling"),
        ],
    },
    "🎉 Giveaways": {
        "group": "giveaway",
        "commands": [
            ("start",  "Start a giveaway"),
            ("end",    "End a giveaway early"),
            ("reroll", "Reroll giveaway winner"),
        ],
    },
    "📊 Polls": {
        "group": "poll",
        "commands": [
            ("create", "Create a poll"),
            ("end",    "End a poll"),
        ],
    },
    "💡 Suggestions": {
        "group": "suggestions",
        "commands": [
            ("setup",   "Configure suggestion channel"),
            ("submit",  "Submit a suggestion"),
            ("approve", "Approve a suggestion"),
            ("deny",    "Deny a suggestion"),
        ],
    },
    "⭐ Starboard": {
        "group": "starboard",
        "commands": [
            ("setup", "Configure starboard"),
            ("view",  "View starboard config"),
        ],
    },
    "😶 AFK": {
        "group": "afk",
        "commands": [
            ("set", "Set your AFK status"),
        ],
    },
    "🎭 Reaction Roles": {
        "group": "reactionroles",
        "commands": [
            ("add",    "Add a reaction role"),
            ("remove", "Remove a reaction role"),
            ("list",   "List reaction roles"),
        ],
    },
    "✅ Verification": {
        "group": "verification",
        "commands": [
            ("setup",     "Setup verification"),
            ("customize", "Customize the panel"),
        ],
    },
    "🔧 Custom Commands": {
        "group": "customcmd",
        "commands": [
            ("add",    "Add a custom command"),
            ("remove", "Remove a custom command"),
            ("list",   "List custom commands"),
        ],
    },
    "🔊 Voice Channels": {
        "group": "vc",
        "commands": [
            ("setup",         "Setup hub channel"),
            ("removehub",     "Remove hub channel"),
            ("config",        "View hub config"),
            ("reset",         "Reset VC system"),
            ("panel",         "Send VC panel"),
            ("forcedelete",   "Force-delete a VC"),
            ("forcetransfer", "Force-transfer a VC"),
            ("rename",        "Rename your VC"),
            ("limit",         "Set user limit"),
            ("bitrate",       "Set bitrate"),
            ("lock",          "Lock your VC"),
            ("unlock",        "Unlock your VC"),
            ("hide",          "Hide your VC"),
            ("show",          "Show your VC"),
            ("kick",          "Kick from your VC"),
            ("allow",         "Allow a member"),
            ("deny",          "Deny a member"),
            ("transfer",      "Transfer ownership"),
            ("claim",         "Claim a VC"),
            ("info",          "View VC info"),
            ("delete",        "Delete your VC"),
            ("list",          "List all VCs"),
        ],
    },
    "🏠 Private Rooms": {
        "group": "room",
        "commands": [
            ("setup",         "Setup hub channel"),
            ("removehub",     "Remove hub channel"),
            ("config",        "View hub config"),
            ("reset",         "Reset room system"),
            ("forcedelete",   "Force-delete a room"),
            ("forcetransfer", "Force-transfer a room"),
            ("list",          "List all rooms"),
            ("addmember",     "Add member to room"),
            ("name",          "Rename your room"),
            ("addrole",       "Grant role to room"),
            ("removerole",    "Revoke role from room"),
            ("removemember",  "Remove member from room"),
            ("info",          "View room info"),
            ("transfer",      "Transfer room"),
            ("delete",        "Delete your room"),
        ],
    },
    "🛠️ Utility": {
        "group": "utility",
        "commands": [
            ("avatar",      "Get a user's avatar"),
            ("banner",      "Get a user's banner"),
            ("userinfo",    "User information"),
            ("serverinfo",  "Server information"),
            ("roleinfo",    "Role information"),
            ("membercount", "Server member count"),
            ("ping",        "Bot latency"),
            ("uptime",      "Bot uptime"),
            ("botinfo",     "Bot information"),
            ("invite",      "Get bot invite link"),
        ],
    },
    "📝 Embeds": {
        "group": "embeds",
        "commands": [
            ("create",   "Build an embed"),
            ("edit",     "Edit a saved embed"),
            ("delete",   "Delete a saved embed"),
            ("preview",  "Preview an embed"),
            ("save",     "Save an embed from a message"),
            ("template", "Send an embed to a channel"),
        ],
    },
    "📈 Server Stats": {
        "group": "serverstats",
        "commands": [
            ("setup",    "Create stat channels"),
            ("refresh",  "Force refresh stats"),
            ("remove",   "Remove stat channels"),
            ("settings", "View stats settings"),
        ],
    },
    "👋 Welcome": {
        "group": "welcome",
        "commands": [
            ("setup",     "Configure welcome system"),
            ("preview",   "Preview welcome message"),
            ("view",      "View welcome config"),
            ("customize", "Customize embed"),
            ("reset",     "Reset welcome system"),
        ],
    },
    "📢 DM": {
        "group": "_top",
        "commands": [
            ("dm",    "DM a specific member"),
            ("dmall", "DM all members"),
        ],
    },
    "⚙️ Admin": {
        "group": "admin",
        "commands": [
            ("setup",  "Run the setup wizard"),
            ("config", "Update bot config"),
            ("view",   "View all settings"),
            ("reset",  "Reset all bot data"),
            ("reload", "Reload an extension"),
        ],
    },
    "📋 Logs": {
        "group": "logs",
        "commands": [
            ("setup", "Setup logging system"),
            ("reset", "Remove log channels"),
            ("view",  "View log config"),
            ("test",  "Send test log"),
        ],
    },
    "🤖 AutoMod": {
        "group": "automod",
        "commands": [
            ("setup", "Configure automod"),
            ("reset", "Reset automod"),
            ("view",  "View automod config"),
        ],
    },
}


def _cmd_key(group: str, cmd: str) -> str:
    """Build the MongoDB storage key for a command."""
    return f"_top.{cmd}" if group == "_top" else f"{group}.{cmd}"


def _cmd_display(group: str, cmd: str) -> str:
    """Human-readable slash command label."""
    return f"/{cmd}" if group == "_top" else f"/{group} {cmd}"


# ─── Embed builder ─────────────────────────────────────────────────────────────

async def _perm_embed(
    guild: discord.Guild,
    command_key: str,
    display: str,
) -> discord.Embed:
    cfg      = await get_guild_config(guild.id)
    role_ids: list[int] = cfg.get("command_roles", {}).get(command_key, [])

    embed = primary_embed(f"🔐 {display}", "")
    if not role_ids:
        embed.description = (
            "✅ **No role restriction set.**\n"
            "This command uses its built-in permission check.\n\n"
            "Use **➕ Add Role** to restrict it to specific roles."
        )
    else:
        mentions = []
        for rid in role_ids:
            role = guild.get_role(rid)
            mentions.append(role.mention if role else f"~~Deleted~~ (`{rid}`)")
        embed.description = "Only the following roles can use this command:"
        embed.add_field(
            name="✅ Allowed Roles",
            value="\n".join(f"• {m}" for m in mentions),
            inline=False,
        )
    embed.set_footer(text="Administrators always bypass role restrictions.")
    return embed


# ─── Views ─────────────────────────────────────────────────────────────────────

class CategorySelectView(discord.ui.View):
    """Step 1 — pick a command category."""

    def __init__(self, author_id: int):
        super().__init__(timeout=180)
        self.author_id = author_id

        options = [
            discord.SelectOption(label=cat, value=cat)
            for cat in list(REGISTRY.keys())[:25]
        ]
        sel = discord.ui.Select(
            placeholder="📂  Choose a command category…",
            options=options,
        )
        sel.callback = self._on_select
        self.add_item(sel)

    async def _on_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This panel isn't yours.", ephemeral=True)
            return
        category = interaction.data["values"][0]
        embed = primary_embed(
            f"🔐 Permissions — {category}",
            "Choose the specific command to configure.",
        )
        await interaction.response.edit_message(
            embed=embed,
            view=CommandSelectView(self.author_id, category),
        )


class CommandSelectView(discord.ui.View):
    """Step 2 — pick a specific command within the category."""

    def __init__(self, author_id: int, category: str):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.category  = category

        group = REGISTRY[category]["group"]
        options = [
            discord.SelectOption(
                label=_cmd_display(group, name),
                description=desc,
                value=_cmd_key(group, name),
            )
            for name, desc in REGISTRY[category]["commands"][:25]
        ]
        sel = discord.ui.Select(
            placeholder="⚡  Choose a command…",
            options=options,
        )
        sel.callback = self._on_select
        self.add_item(sel)

        back = discord.ui.Button(label="← Back", style=discord.ButtonStyle.secondary, row=1)
        back.callback = self._go_back
        self.add_item(back)

    async def _go_back(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            return
        embed = primary_embed(
            "🔐 Bot Permission Manager",
            "Select a category to configure role access.",
        )
        await interaction.response.edit_message(
            embed=embed, view=CategorySelectView(self.author_id)
        )

    async def _on_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This panel isn't yours.", ephemeral=True)
            return
        key     = interaction.data["values"][0]
        group   = REGISTRY[self.category]["group"]
        # reconstruct display from key
        parts   = key.split(".", 1)
        display = _cmd_display(parts[0], parts[1])

        embed = await _perm_embed(interaction.guild, key, display)
        view  = await PermissionPanelView.build(
            interaction.guild_id, self.author_id, self.category, key, display
        )
        await interaction.response.edit_message(embed=embed, view=view)


class PermissionPanelView(discord.ui.View):
    """Step 3 — Add / Remove / Clear roles for a command."""

    def __init__(
        self,
        author_id:   int,
        category:    str,
        command_key: str,
        display:     str,
        has_roles:   bool,
    ):
        super().__init__(timeout=180)
        self.author_id   = author_id
        self.category    = category
        self.command_key = command_key
        self.display     = display

        add = discord.ui.Button(
            label="➕ Add Role", style=discord.ButtonStyle.success, row=0
        )
        add.callback = self._add_role
        self.add_item(add)

        if has_roles:
            rem = discord.ui.Button(
                label="➖ Remove Role", style=discord.ButtonStyle.danger, row=0
            )
            rem.callback = self._remove_role
            self.add_item(rem)

            clr = discord.ui.Button(
                label="🗑️ Clear All", style=discord.ButtonStyle.danger, row=0
            )
            clr.callback = self._clear_all
            self.add_item(clr)

        back = discord.ui.Button(
            label="← Back", style=discord.ButtonStyle.secondary, row=1
        )
        back.callback = self._go_back
        self.add_item(back)

    @classmethod
    async def build(
        cls,
        guild_id:    int,
        author_id:   int,
        category:    str,
        command_key: str,
        display:     str,
    ) -> "PermissionPanelView":
        cfg       = await get_guild_config(guild_id)
        has_roles = bool(cfg.get("command_roles", {}).get(command_key))
        return cls(author_id, category, command_key, display, has_roles)

    async def _go_back(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            return
        embed = primary_embed(
            f"🔐 Permissions — {self.category}",
            "Choose the specific command to configure.",
        )
        await interaction.response.edit_message(
            embed=embed,
            view=CommandSelectView(self.author_id, self.category),
        )

    async def _add_role(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This panel isn't yours.", ephemeral=True)
            return
        embed = primary_embed(
            f"➕ Add Role — {self.display}",
            "Select one or more roles that should be allowed to use this command.",
        )
        await interaction.response.edit_message(
            embed=embed,
            view=RoleAddView(self.author_id, self.category, self.command_key, self.display),
        )

    async def _remove_role(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This panel isn't yours.", ephemeral=True)
            return
        view = await RoleRemoveView.build(
            interaction.guild_id,
            interaction.guild,
            self.author_id,
            self.category,
            self.command_key,
            self.display,
        )
        embed = primary_embed(
            f"➖ Remove Role — {self.display}",
            "Select the roles to remove from this command.",
        )
        await interaction.response.edit_message(embed=embed, view=view)

    async def _clear_all(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This panel isn't yours.", ephemeral=True)
            return
        cfg       = await get_guild_config(interaction.guild_id)
        roles_map = cfg.get("command_roles", {})
        roles_map.pop(self.command_key, None)
        await update_guild_config(interaction.guild_id, {"command_roles": roles_map})

        embed = await _perm_embed(interaction.guild, self.command_key, self.display)
        view  = await PermissionPanelView.build(
            interaction.guild_id, self.author_id, self.category, self.command_key, self.display
        )
        await interaction.response.edit_message(embed=embed, view=view)


class RoleAddView(discord.ui.View):
    """Role Select to add allowed roles to a command."""

    def __init__(self, author_id: int, category: str, command_key: str, display: str):
        super().__init__(timeout=180)
        self.author_id   = author_id
        self.category    = category
        self.command_key = command_key
        self.display     = display

    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="🎭  Select roles to allow…",
        min_values=1,
        max_values=10,
    )
    async def role_select(
        self, interaction: discord.Interaction, select: discord.ui.RoleSelect
    ):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This panel isn't yours.", ephemeral=True)
            return
        cfg       = await get_guild_config(interaction.guild_id)
        roles_map = cfg.get("command_roles", {})
        current   = set(roles_map.get(self.command_key, []))

        for role in select.values:
            current.add(role.id)

        roles_map[self.command_key] = list(current)
        await update_guild_config(interaction.guild_id, {"command_roles": roles_map})

        embed = await _perm_embed(interaction.guild, self.command_key, self.display)
        view  = await PermissionPanelView.build(
            interaction.guild_id, self.author_id, self.category, self.command_key, self.display
        )
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="← Cancel", style=discord.ButtonStyle.secondary, row=1)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return
        embed = await _perm_embed(interaction.guild, self.command_key, self.display)
        view  = await PermissionPanelView.build(
            interaction.guild_id, self.author_id, self.category, self.command_key, self.display
        )
        await interaction.response.edit_message(embed=embed, view=view)


class RoleRemoveView(discord.ui.View):
    """Dropdown to remove specific roles from a command."""

    def __init__(self, author_id: int, category: str, command_key: str, display: str):
        super().__init__(timeout=180)
        self.author_id   = author_id
        self.category    = category
        self.command_key = command_key
        self.display     = display

    @classmethod
    async def build(
        cls,
        guild_id:    int,
        guild:       discord.Guild,
        author_id:   int,
        category:    str,
        command_key: str,
        display:     str,
    ) -> "RoleRemoveView":
        self = cls(author_id, category, command_key, display)
        cfg      = await get_guild_config(guild_id)
        role_ids = cfg.get("command_roles", {}).get(command_key, [])

        options = []
        for rid in role_ids:
            role = guild.get_role(rid)
            options.append(
                discord.SelectOption(
                    label=role.name if role else f"Deleted Role",
                    value=str(rid),
                    description=f"ID: {rid}",
                )
            )

        if options:
            sel = discord.ui.Select(
                placeholder="🗑️  Pick roles to remove…",
                options=options[:25],
                min_values=1,
                max_values=len(options),
            )
            sel.callback = self._on_select
            self.add_item(sel)

        back = discord.ui.Button(label="← Cancel", style=discord.ButtonStyle.secondary, row=1)
        back.callback = self._cancel
        self.add_item(back)

        return self

    async def _cancel(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            return
        embed = await _perm_embed(interaction.guild, self.command_key, self.display)
        view  = await PermissionPanelView.build(
            interaction.guild_id, self.author_id, self.category, self.command_key, self.display
        )
        await interaction.response.edit_message(embed=embed, view=view)

    async def _on_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This panel isn't yours.", ephemeral=True)
            return
        to_remove = {int(v) for v in interaction.data["values"]}
        cfg       = await get_guild_config(interaction.guild_id)
        roles_map = cfg.get("command_roles", {})
        current   = set(roles_map.get(self.command_key, [])) - to_remove

        if current:
            roles_map[self.command_key] = list(current)
        else:
            roles_map.pop(self.command_key, None)

        await update_guild_config(interaction.guild_id, {"command_roles": roles_map})

        embed = await _perm_embed(interaction.guild, self.command_key, self.display)
        view  = await PermissionPanelView.build(
            interaction.guild_id, self.author_id, self.category, self.command_key, self.display
        )
        await interaction.response.edit_message(embed=embed, view=view)


# ─── Cog ───────────────────────────────────────────────────────────────────────

class BotPerms(commands.Cog, name="BotPerms"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    mgmt_group = app_commands.Group(
        name="bot",
        description="Bot management commands",
    )

    @mgmt_group.command(
        name="users",
        description="Configure which roles can use each bot command",
    )
    @is_admin()
    async def users(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        embed = primary_embed(
            "🔐 Bot Permission Manager",
            "Choose a command category below to configure role access.\n\n"
            "**How it works:**\n"
            "› By default every command uses its built-in permission check\n"
            "› Once you add roles to a command, **only those roles** can use it\n"
            "› Server administrators always bypass all restrictions\n\n"
            "Select a category to get started ↓",
        )
        await interaction.followup.send(
            embed=embed,
            view=CategorySelectView(interaction.user.id),
            ephemeral=True,
        )

    @mgmt_group.command(
        name="permissions",
        description="View all active role permission rules",
    )
    @is_admin()
    async def permissions(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg       = await get_guild_config(interaction.guild_id)
        roles_map = cfg.get("command_roles", {})

        if not roles_map:
            await interaction.followup.send(
                embed=info_embed(
                    "🔐 Permission Rules",
                    "No custom role restrictions have been set.\nUse `/bot users` to configure them.",
                ),
                ephemeral=True,
            )
            return

        embed = primary_embed(
            "🔐 Active Permission Rules",
            f"**{len(roles_map)}** command(s) have role restrictions:",
        )
        for key, role_ids in list(roles_map.items())[:20]:
            parts   = key.split(".", 1)
            display = f"/{parts[1]}" if parts[0] == "_top" else f"/{parts[0]} {parts[1]}"
            mentions = []
            for rid in role_ids:
                role = interaction.guild.get_role(rid)
                mentions.append(role.mention if role else f"~~`{rid}`~~")
            embed.add_field(
                name=display,
                value=", ".join(mentions) or "—",
                inline=False,
            )
        if len(roles_map) > 20:
            embed.set_footer(text=f"Showing 20 of {len(roles_map)} rules.")

        await interaction.followup.send(embed=embed, ephemeral=True)

    @mgmt_group.command(
        name="reset",
        description="Remove ALL custom role restrictions and restore defaults",
    )
    @is_admin()
    async def reset(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg       = await get_guild_config(interaction.guild_id)
        count     = len(cfg.get("command_roles", {}))
        await update_guild_config(interaction.guild_id, {"command_roles": {}})
        await interaction.followup.send(
            embed=success_embed(
                "Permissions Reset",
                f"Cleared **{count}** rule(s). All commands now use their default permission checks.",
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(BotPerms(bot))
