import discord
from discord import app_commands
from discord.ext import commands
from utils import primary_embed, info_embed


COMMANDS = {
    "⚙️ Admin": [
        ("/admin setup", "Run the initial bot setup wizard"),
        ("/admin config", "Set mod/admin roles"),
        ("/admin view", "View all server settings"),
        ("/admin reset", "Delete all bot data for this server"),
        ("/admin reload", "Reload a bot extension (owner only)"),
    ],
    "🔨 Moderation": [
        ("/moderation ban", "Ban a member"),
        ("/moderation unban", "Unban a user by ID"),
        ("/moderation kick", "Kick a member"),
        ("/moderation timeout", "Timeout a member (1m – 28d)"),
        ("/moderation mute", "Mute with role (auto-creates Muted role)"),
        ("/moderation unmute", "Unmute a member"),
        ("/moderation warn", "Warn a member"),
        ("/moderation warnings", "View a member's warning history"),
        ("/moderation clear", "Purge up to 100 messages"),
        ("/moderation slowmode", "Set channel slowmode (0–21600s)"),
        ("/moderation lock", "Lock a channel"),
        ("/moderation unlock", "Unlock a channel"),
        ("/moderation nickname", "Change a member's nickname"),
    ],
    "🎫 Tickets": [
        ("/tickets setup", "Configure ticket system"),
        ("/tickets panel", "Send ticket panel to a channel"),
        ("/tickets customize", "Customize the ticket panel appearance (color, title, image)"),
        ("/tickets addtype", "Add a ticket type with custom name, emoji & channel pattern"),
        ("/tickets removetype", "Remove a ticket type"),
        ("/tickets listtypes", "List all configured ticket types"),
        ("/tickets add", "Add a user to a ticket"),
        ("/tickets remove", "Remove a user from a ticket"),
        ("/tickets rename", "Rename the ticket channel"),
        ("/tickets claim", "Claim the current ticket"),
        ("/tickets unclaim", "Unclaim the current ticket"),
        ("/tickets close", "Close the current ticket"),
        ("/tickets delete", "Delete a closed ticket channel"),
        ("/tickets transcript", "Export a ticket transcript"),
        ("/tickets view", "View ticket statistics"),
        ("/tickets reset", "Reset the entire ticket system"),
    ],
    "📋 Applications": [
        ("/applications setup", "Configure review channel & roles"),
        ("/applications create", "Create a new application form"),
        ("/applications edit", "Edit a form's questions"),
        ("/applications delete", "Delete a form"),
        ("/applications panel", "Send application panel to a channel"),
        ("/applications customize", "Customize the application panel appearance"),
        ("/applications open", "Open applications for a form"),
        ("/applications close", "Close applications for a form"),
        ("/applications approve", "Approve a pending application"),
        ("/applications deny", "Deny a pending application"),
        ("/applications view", "View application statistics"),
        ("/applications reset", "Reset the entire application system"),
    ],
    "📝 Logs": [
        ("/logs setup", "Create log category + 9 channels"),
        ("/logs reset", "Remove all log channels"),
        ("/logs view", "View log channel configuration"),
        ("/logs test", "Send test messages to all log channels"),
    ],
    "🎨 Embeds": [
        ("/embeds create", "Open interactive embed builder"),
        ("/embeds edit", "Edit a saved embed template"),
        ("/embeds delete", "Delete an embed template"),
        ("/embeds preview", "Preview a saved template"),
        ("/embeds save", "Save an embed from a message"),
        ("/embeds template", "Send a template to a channel"),
    ],
    "👋 Welcome": [
        ("/welcome setup", "Set channel, auto-roles, leave channel"),
        ("/welcome preview", "Preview welcome/leave messages"),
        ("/welcome customize", "Customize the welcome embed appearance"),
        ("/welcome view", "View current configuration"),
        ("/welcome reset", "Reset welcome system"),
    ],
    "🛡️ AutoMod": [
        ("/automod setup", "Toggle anti-spam, anti-link, anti-scam rules"),
        ("/automod view", "View current automod configuration"),
        ("/automod reset", "Disable all automod rules"),
    ],
    "🛠️ Utility": [
        ("/utility avatar", "Get a user's avatar (PNG/JPG/GIF)"),
        ("/utility banner", "Get a user's banner"),
        ("/utility userinfo", "Detailed user information"),
        ("/utility serverinfo", "Detailed server information"),
        ("/utility roleinfo", "Role details & permissions"),
        ("/utility membercount", "Total, humans, bots, online"),
        ("/utility ping", "WebSocket & API latency"),
        ("/utility uptime", "How long the bot has been online"),
        ("/utility botinfo", "Bot stats, server count, invite"),
        ("/utility invite", "Bot invite & support server links"),
    ],
    "💰 Economy": [
        ("/economy balance", "View wallet, bank & total"),
        ("/economy daily", "Claim daily reward (streak bonus)"),
        ("/economy work", "Work for coins (1h cooldown)"),
        ("/economy deposit", "Deposit coins to bank"),
        ("/economy withdraw", "Withdraw coins from bank"),
        ("/economy pay", "Send coins to another member"),
        ("/economy leaderboard", "Top 10 richest members"),
    ],
    "🏆 Leveling": [
        ("/level rank", "View your or another member's rank"),
        ("/level leaderboard", "Top 10 members by XP"),
        ("/level setlevel", "Set a member's level (admin)"),
        ("/level toggle", "Enable or disable leveling"),
    ],
    "🎉 Giveaways": [
        ("/giveaway start", "Start a giveaway"),
        ("/giveaway end", "End a giveaway early"),
        ("/giveaway reroll", "Reroll a giveaway winner"),
    ],
    "📊 Polls": [
        ("/poll create", "Create a poll with 2–5 options"),
        ("/poll end", "End a poll & show final results"),
    ],
    "💡 Suggestions": [
        ("/suggestions setup", "Set the suggestion channel"),
        ("/suggestions submit", "Submit a suggestion"),
        ("/suggestions approve", "Approve a suggestion"),
        ("/suggestions deny", "Deny a suggestion"),
    ],
    "⭐ Starboard": [
        ("/starboard setup", "Set channel & star threshold"),
        ("/starboard view", "View starboard configuration"),
    ],
    "😴 AFK": [
        ("/afk set", "Set your AFK status with an optional reason"),
    ],
    "🎭 Reaction Roles": [
        ("/reactionroles add", "Add a reaction role to a message"),
        ("/reactionroles remove", "Remove a reaction role"),
        ("/reactionroles list", "List reaction roles for a message"),
    ],
    "✅ Verification": [
        ("/verification setup", "Send a verification panel to a channel"),
        ("/verification customize", "Customize the verification panel appearance"),
    ],
    "🔧 Custom Commands": [
        ("/customcmd add", "Add a custom slash command with a text response"),
        ("/customcmd remove", "Remove a custom command"),
        ("/customcmd list", "List all custom commands and their usage stats"),
    ],
    "🔊 Temp Voice Channels": [
        ("/vc setup", "Add/update a hub channel that creates temp VCs"),
        ("/vc removehub", "Remove a hub channel from the system"),
        ("/vc config", "View all configured hubs and their settings"),
        ("/vc reset", "Remove all hubs and disable the system"),
        ("/vc panel", "Post the VC control panel embed to a channel (admin)"),
        ("/vc forcedelete", "Force delete any temp VC (admin)"),
        ("/vc forcetransfer", "Force transfer ownership of any temp VC (admin)"),
        ("/vc rename", "Rename your temp voice channel"),
        ("/vc limit", "Set the user limit of your channel (0 = unlimited)"),
        ("/vc bitrate", "Set the bitrate of your channel (8–384 kbps)"),
        ("/vc lock", "Lock your channel — no new members can join"),
        ("/vc unlock", "Unlock your channel so anyone can join"),
        ("/vc hide", "Hide your channel from the server"),
        ("/vc show", "Make your channel visible to everyone"),
        ("/vc kick", "Kick a member from your channel"),
        ("/vc allow", "Allow a specific member to join your locked/hidden channel"),
        ("/vc deny", "Deny a specific member from joining your channel"),
        ("/vc transfer", "Transfer ownership to a member in your channel"),
        ("/vc claim", "Claim an abandoned channel whose owner left"),
        ("/vc info", "View info about the temp VC you are currently in"),
        ("/vc delete", "Delete your temp voice channel early"),
        ("/vc list", "List all active temporary voice channels"),
    ],
    "🏠 Private Rooms": [
        ("/room setup", "Add/update a hub channel that creates private rooms"),
        ("/room removehub", "Remove a private room hub channel"),
        ("/room config", "View all configured room hubs"),
        ("/room reset", "Remove all hubs and disable private rooms"),
        ("/room forcedelete", "Force delete any private room (admin)"),
        ("/room forcetransfer", "Force transfer room ownership (admin)"),
        ("/room list", "List all active private rooms (admin)"),
        ("/room name", "Rename your private room"),
        ("/room addrole", "Add a role that can see and join your room"),
        ("/room removerole", "Remove a role's access from your room"),
        ("/room addmember", "Add a specific member to your room"),
        ("/room removemember", "Revoke a member's access and kick them if inside"),
        ("/room info", "View your room's current roles and members"),
        ("/room transfer", "Transfer ownership to a member inside the room"),
        ("/room delete", "Delete your private room"),
    ],
    "📈 Server Stats": [
        ("/serverstats setup", "Create stat channels (members, bots, online, etc.)"),
        ("/serverstats refresh", "Force refresh all stat channel values"),
        ("/serverstats remove", "Remove all stat channels"),
        ("/serverstats settings", "View current stat channel configuration"),
    ],
    "📩 DM Commands": [
        ("/dm", "Send a DM to a specific server member (admin only)"),
        ("/dmall", "DM all members or a specific role — requires confirmation (admin only)"),
    ],
    "🤖 Bot Management": [
        ("/bot users", "Open the interactive role-permission manager — restrict any command to specific roles"),
        ("/bot permissions", "View all active role restrictions across every command"),
        ("/bot reset", "Remove ALL custom role restrictions and restore defaults"),
    ],
}

PAGES = list(COMMANDS.items())


class HelpView(discord.ui.View):
    def __init__(self, user_id: int, page: int = 0):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.page = page
        self._update_buttons()

    def _update_buttons(self):
        self.prev_btn.disabled = self.page == 0
        self.next_btn.disabled = self.page >= len(PAGES) - 1
        self.page_btn.label = f"{self.page + 1} / {len(PAGES)}"

    def build_embed(self) -> discord.Embed:
        category, cmds = PAGES[self.page]
        embed = primary_embed(f"Help — {category}")
        embed.description = "\n".join(f"**`{name}`**\n{desc}" for name, desc in cmds)
        embed.set_footer(text=f"Page {self.page + 1}/{len(PAGES)} • {len(COMMANDS)} categories • {sum(len(v) for v in COMMANDS.values())} commands total")
        return embed

    async def _go(self, interaction: discord.Interaction, delta: int):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This help menu belongs to someone else.", ephemeral=True)
            return
        self.page += delta
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._go(interaction, -1)

    @discord.ui.button(label="1 / X", style=discord.ButtonStyle.primary, disabled=True)
    async def page_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._go(interaction, 1)

    @discord.ui.button(label="📋 All Categories", style=discord.ButtonStyle.success, row=1)
    async def overview_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This help menu belongs to someone else.", ephemeral=True)
            return
        embed = primary_embed("📚 All Command Categories")
        lines = []
        for i, (cat, cmds) in enumerate(PAGES):
            lines.append(f"`{i+1:02}.` {cat} — **{len(cmds)}** commands")
        embed.description = "\n".join(lines)
        embed.set_footer(text=f"{len(COMMANDS)} categories • {sum(len(v) for v in COMMANDS.values())} total commands")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🔍 Search", style=discord.ButtonStyle.secondary, row=1)
    async def search_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This help menu belongs to someone else.", ephemeral=True)
            return
        await interaction.response.send_modal(HelpSearchModal(self))

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


class HelpSearchModal(discord.ui.Modal, title="Search Commands"):
    query = discord.ui.TextInput(label="Search term", placeholder="e.g. ban, ticket, daily ...", max_length=50)

    def __init__(self, parent_view: HelpView):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        q = self.query.value.lower()
        results = []
        for cat, cmds in COMMANDS.items():
            for name, desc in cmds:
                if q in name.lower() or q in desc.lower() or q in cat.lower():
                    results.append((cat, name, desc))

        if not results:
            embed = info_embed("No Results", f"No commands matched **{self.query.value}**.")
        else:
            embed = primary_embed(f"🔍 Search: \"{self.query.value}\"", f"Found **{len(results)}** result(s):")
            for cat, name, desc in results[:20]:
                embed.add_field(name=f"`{name}`", value=f"{desc}\n*{cat}*", inline=False)
            if len(results) > 20:
                embed.set_footer(text=f"Showing 20 of {len(results)} results. Refine your search.")

        await interaction.response.edit_message(embed=embed, view=self.parent_view)


class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Browse all bot commands with search and pagination")
    async def help(self, interaction: discord.Interaction):
        view = HelpView(interaction.user.id)
        await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)

    @app_commands.command(name="commands", description="Quick summary of all command categories")
    async def commands_overview(self, interaction: discord.Interaction):
        embed = primary_embed("📚 Command Categories", "Use `/help` for full details and search.")
        for cat, cmds in COMMANDS.items():
            embed.add_field(name=cat, value=f"{len(cmds)} commands", inline=True)
        embed.set_footer(text=f"{sum(len(v) for v in COMMANDS.values())} total commands across {len(COMMANDS)} categories")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
