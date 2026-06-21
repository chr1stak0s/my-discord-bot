import discord
import datetime
from database import Database, get_guild_config, update_guild_config
from utils.helpers import success_embed, error_embed, primary_embed, warning_embed, info_embed


# ─── Modals ───────────────────────────────────────────────────────────────────

class ApplicationModal(discord.ui.Modal):
    def __init__(self, form: dict, questions: list[str]):
        super().__init__(title=form["name"][:45])
        self.form = form
        self.question_items = []
        for q in questions:
            item = discord.ui.TextInput(
                label=q[:45],
                style=discord.TextStyle.paragraph if len(q) > 50 else discord.TextStyle.short,
                placeholder="Type your answer here...",
                max_length=1000,
                required=True,
            )
            self.question_items.append(item)
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        answers = {q: item.value for q, item in zip(self.form.get("questions", []), self.question_items)}
        cfg = await get_guild_config(interaction.guild_id)

        # Check cooldown
        cooldown_minutes = self.form.get("cooldown_minutes", 0)
        if cooldown_minutes > 0:
            last_app = await Database.db.applications.find_one(
                {"guild_id": interaction.guild_id, "user_id": interaction.user.id, "form_name": self.form["name"]},
                sort=[("created_at", -1)],
            )
            if last_app:
                elapsed = (datetime.datetime.utcnow() - last_app["created_at"]).total_seconds()
                remaining = cooldown_minutes * 60 - elapsed
                if remaining > 0:
                    mins = int(remaining // 60)
                    secs = int(remaining % 60)
                    await interaction.response.send_message(
                        embed=warning_embed("Cooldown Active", f"You must wait **{mins}m {secs}s** before resubmitting this form."),
                        ephemeral=True,
                    )
                    return

        app_count = await Database.db.applications.count_documents({"guild_id": interaction.guild_id}) + 1
        doc = {
            "guild_id": interaction.guild_id,
            "user_id": interaction.user.id,
            "username": str(interaction.user),
            "form_name": self.form["name"],
            "answers": answers,
            "status": "pending",
            "app_id": app_count,
            "created_at": datetime.datetime.utcnow(),
            "reviewed_by": None,
            "review_reason": None,
            "message_id": None,
            "notes": [],
        }

        result = await Database.db.applications.insert_one(doc)

        review_channel_id = self.form.get("review_channel_id") or cfg.get("application_review_channel_id")
        if review_channel_id:
            channel = interaction.guild.get_channel(review_channel_id)
            if channel:
                embed = primary_embed(
                    f"📋 {self.form['name']} Application #{app_count}",
                    f"**Applicant:** {interaction.user.mention} (`{interaction.user.id}`)",
                )
                embed.set_thumbnail(url=interaction.user.display_avatar.url)
                for question, answer in answers.items():
                    embed.add_field(name=f"❓ {question}", value=answer[:1024] or "No answer", inline=False)
                embed.set_footer(text=f"Application ID: #{app_count} • Submitted")
                embed.timestamp = datetime.datetime.utcnow()

                view = ApplicationReviewView(str(result.inserted_id), interaction.user.id, app_count, self.form["name"])
                msg = await channel.send(embed=embed, view=view)
                await Database.db.applications.update_one(
                    {"_id": result.inserted_id},
                    {"$set": {"message_id": msg.id, "review_channel_id": channel.id}},
                )

        await interaction.response.send_message(
            embed=success_embed(
                "Application Submitted!",
                f"Your **{self.form['name']}** application (`#{app_count}`) has been submitted.\nYou will be notified when it's reviewed.",
            ),
            ephemeral=True,
        )

        log_channel_id = cfg.get("application_log_channel_id")
        if log_channel_id:
            log_ch = interaction.guild.get_channel(log_channel_id)
            if log_ch:
                await log_ch.send(embed=info_embed(
                    "Application Submitted",
                    f"**Applicant:** {interaction.user.mention}\n**Form:** {self.form['name']}\n**ID:** #{app_count}",
                ))


class ReviewModal(discord.ui.Modal):
    reason_input = discord.ui.TextInput(
        label="Reason (optional)",
        style=discord.TextStyle.paragraph,
        required=False,
        placeholder="Enter a reason...",
        max_length=500,
    )

    def __init__(self, action: str):
        super().__init__(title=f"{'Accept' if action == 'accept' else 'Deny' if action == 'deny' else 'Hold'} Application")
        self.reason = ""

    async def on_submit(self, interaction: discord.Interaction):
        self.reason = self.reason_input.value
        await interaction.response.defer()
        self.stop()


class RequestInfoModal(discord.ui.Modal, title="Request More Information"):
    message = discord.ui.TextInput(
        label="Message to Applicant",
        style=discord.TextStyle.paragraph,
        placeholder="What additional information do you need?",
        max_length=1000,
        required=True,
    )

    def __init__(self):
        super().__init__()
        self.result = None

    async def on_submit(self, interaction: discord.Interaction):
        self.result = self.message.value
        await interaction.response.defer()
        self.stop()


class NoteModal(discord.ui.Modal, title="Add Internal Note"):
    note = discord.ui.TextInput(
        label="Note",
        style=discord.TextStyle.paragraph,
        placeholder="Add an internal reviewer note (not shown to applicant)...",
        max_length=1000,
        required=True,
    )

    def __init__(self):
        super().__init__()
        self.result = None

    async def on_submit(self, interaction: discord.Interaction):
        self.result = self.note.value
        await interaction.response.defer()
        self.stop()


# ─── Panel Select / Buttons ───────────────────────────────────────────────────

class ApplicationSelect(discord.ui.Select):
    def __init__(self, forms: list[dict]):
        options = [
            discord.SelectOption(
                label=f["name"],
                description=f.get("description", "Click to apply")[:100],
                emoji=f.get("emoji", "📋"),
                value=f["name"],
            )
            for f in forms[:25]
        ]
        super().__init__(placeholder="Select an application to submit...", options=options, custom_id="app:dropdown_select")

    async def callback(self, interaction: discord.Interaction):
        cfg = await get_guild_config(interaction.guild_id)
        forms = cfg.get("application_forms", [])
        form = next((f for f in forms if f["name"] == self.values[0]), None)
        if not form:
            await interaction.response.send_message(embed=error_embed("Not Found", "Form not found."), ephemeral=True)
            return
        await _open_application(interaction, form)


class ApplicationFormButton(discord.ui.Button):
    def __init__(self, form: dict, row: int):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label=form["name"][:80],
            emoji=form.get("emoji", "📋"),
            custom_id=f"app:btn:{form['name'][:75]}",
            row=row,
        )
        self.form_name = form["name"]

    async def callback(self, interaction: discord.Interaction):
        cfg = await get_guild_config(interaction.guild_id)
        forms = cfg.get("application_forms", [])
        form = next((f for f in forms if f["name"] == self.form_name), None)
        if not form:
            await interaction.response.send_message(embed=error_embed("Not Found", "This form no longer exists."), ephemeral=True)
            return
        await _open_application(interaction, form)


async def _open_application(interaction: discord.Interaction, form: dict):
    """Shared logic for opening an application modal from any trigger."""
    if not form.get("open", True):
        await interaction.response.send_message(
            embed=error_embed("Applications Closed", f"Applications for **{form['name']}** are currently closed."),
            ephemeral=True,
        )
        return

    existing = await Database.db.applications.find_one({
        "guild_id": interaction.guild_id,
        "user_id": interaction.user.id,
        "form_name": form["name"],
        "status": "pending",
    })
    if existing:
        await interaction.response.send_message(
            embed=warning_embed(
                "Pending Application",
                f"You already have a pending **{form['name']}** application (`#{existing.get('app_id', '?')}`).\nWait for it to be reviewed before submitting again.",
            ),
            ephemeral=True,
        )
        return

    questions = form.get("questions", [])
    if not questions:
        await interaction.response.send_message(embed=error_embed("No Questions", "This form has no questions configured."), ephemeral=True)
        return

    modal = ApplicationModal(form, questions[:5])
    await interaction.response.send_modal(modal)


# ─── Panel Views ──────────────────────────────────────────────────────────────

class ApplicationPanelView(discord.ui.View):
    """Buttons style — one button per form."""
    def __init__(self, forms: list[dict]):
        super().__init__(timeout=None)
        for i, form in enumerate(forms[:25]):
            self.add_item(ApplicationFormButton(form, row=min(i // 5, 4)))


class ApplicationDropdownPanelView(discord.ui.View):
    """Dropdown style — single select menu."""
    def __init__(self, forms: list[dict]):
        super().__init__(timeout=None)
        self.add_item(ApplicationSelect(forms))


# ─── Review View ──────────────────────────────────────────────────────────────

class ApplicationReviewView(discord.ui.View):
    def __init__(self, app_object_id: str, applicant_id: int, app_id: int = 0, form_name: str = ""):
        super().__init__(timeout=None)
        self.app_object_id = app_object_id
        self.applicant_id = applicant_id
        self.app_id = app_id
        self.form_name = form_name

    async def _check_reviewer(self, interaction: discord.Interaction) -> bool:
        cfg = await get_guild_config(interaction.guild_id)
        reviewer_roles = cfg.get("application_reviewer_roles", [])
        if interaction.user.guild_permissions.administrator or any(r.id in reviewer_roles for r in interaction.user.roles):
            return True
        await interaction.response.send_message(embed=error_embed("No Permission", "You are not a reviewer."), ephemeral=True)
        return False

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, emoji="✅", custom_id="app:review:accept", row=0)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_reviewer(interaction):
            return

        modal = ReviewModal("accept")
        await interaction.response.send_modal(modal)
        await modal.wait()

        from bson import ObjectId
        app = await Database.db.applications.find_one_and_update(
            {"_id": ObjectId(self.app_object_id)},
            {"$set": {"status": "accepted", "reviewed_by": interaction.user.id, "review_reason": modal.reason, "reviewed_at": datetime.datetime.utcnow()}},
        )
        if not app:
            return

        cfg = await get_guild_config(interaction.guild_id)
        applicant = interaction.guild.get_member(self.applicant_id)

        accept_role_id = cfg.get("application_accept_role_id")
        form_accept_role = None
        for f in cfg.get("application_forms", []):
            if f["name"] == app.get("form_name"):
                form_accept_role = f.get("accept_role_id")
                break

        for role_id in [r for r in [accept_role_id, form_accept_role] if r]:
            role = interaction.guild.get_role(role_id)
            if role and applicant:
                try:
                    await applicant.add_roles(role, reason="Application accepted")
                except discord.Forbidden:
                    pass

        embed = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed()
        embed.color = 0x2ECC71
        embed.title = f"✅ ACCEPTED — {embed.title}"
        embed.add_field(name="Reviewed By", value=interaction.user.mention, inline=True)
        embed.add_field(name="Reason", value=modal.reason or "No reason provided", inline=True)
        embed.add_field(name="Reviewed At", value=discord.utils.format_dt(datetime.datetime.utcnow(), "R"), inline=True)
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(embed=embed, view=self)

        if applicant:
            try:
                dm_embed = success_embed(
                    "Application Accepted! 🎉",
                    f"Your **{app.get('form_name', 'application')}** application (`#{self.app_id}`) has been **accepted**!\n**Reason:** {modal.reason or 'No reason provided'}",
                )
                dm_embed.set_footer(text=interaction.guild.name, icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
                await applicant.send(embed=dm_embed)
            except discord.Forbidden:
                pass

        log_channel_id = cfg.get("application_log_channel_id")
        if log_channel_id:
            log_ch = interaction.guild.get_channel(log_channel_id)
            if log_ch:
                await log_ch.send(embed=success_embed(
                    "Application Accepted",
                    f"**Applicant:** {applicant.mention if applicant else f'<@{self.applicant_id}>'}\n**Form:** {app.get('form_name')}\n**ID:** #{self.app_id}\n**Reviewed by:** {interaction.user.mention}\n**Reason:** {modal.reason or 'None'}",
                ))

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger, emoji="❌", custom_id="app:review:deny", row=0)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_reviewer(interaction):
            return

        modal = ReviewModal("deny")
        await interaction.response.send_modal(modal)
        await modal.wait()

        from bson import ObjectId
        app = await Database.db.applications.find_one_and_update(
            {"_id": ObjectId(self.app_object_id)},
            {"$set": {"status": "denied", "reviewed_by": interaction.user.id, "review_reason": modal.reason, "reviewed_at": datetime.datetime.utcnow()}},
        )
        if not app:
            return

        embed = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed()
        embed.color = 0xE74C3C
        embed.title = f"❌ DENIED — {embed.title}"
        embed.add_field(name="Reviewed By", value=interaction.user.mention, inline=True)
        embed.add_field(name="Reason", value=modal.reason or "No reason provided", inline=True)
        embed.add_field(name="Reviewed At", value=discord.utils.format_dt(datetime.datetime.utcnow(), "R"), inline=True)
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(embed=embed, view=self)

        cfg = await get_guild_config(interaction.guild_id)
        applicant = interaction.guild.get_member(self.applicant_id)
        if applicant:
            try:
                dm_embed = error_embed(
                    "Application Denied",
                    f"Your **{app.get('form_name', 'application')}** application (`#{self.app_id}`) has been **denied**.\n**Reason:** {modal.reason or 'No reason provided'}",
                )
                dm_embed.set_footer(text=interaction.guild.name, icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
                await applicant.send(embed=dm_embed)
            except discord.Forbidden:
                pass

        log_channel_id = cfg.get("application_log_channel_id")
        if log_channel_id:
            log_ch = interaction.guild.get_channel(log_channel_id)
            if log_ch:
                await log_ch.send(embed=error_embed(
                    "Application Denied",
                    f"**Applicant:** {applicant.mention if applicant else f'<@{self.applicant_id}>'}\n**Form:** {app.get('form_name')}\n**ID:** #{self.app_id}\n**Reviewed by:** {interaction.user.mention}\n**Reason:** {modal.reason or 'None'}",
                ))

    @discord.ui.button(label="Hold", style=discord.ButtonStyle.secondary, emoji="⏸️", custom_id="app:review:hold", row=0)
    async def hold(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_reviewer(interaction):
            return

        modal = ReviewModal("hold")
        await interaction.response.send_modal(modal)
        await modal.wait()

        from bson import ObjectId
        app = await Database.db.applications.find_one_and_update(
            {"_id": ObjectId(self.app_object_id)},
            {"$set": {"status": "on_hold", "held_by": interaction.user.id, "hold_reason": modal.reason}},
        )
        if not app:
            return

        embed = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed()
        embed.color = 0xF39C12
        embed.title = f"⏸️ ON HOLD — {embed.title}"
        embed.add_field(name="Held By", value=interaction.user.mention, inline=True)
        embed.add_field(name="Reason", value=modal.reason or "No reason provided", inline=True)
        await interaction.message.edit(embed=embed, view=self)

        applicant = interaction.guild.get_member(self.applicant_id)
        if applicant:
            try:
                dm_embed = warning_embed(
                    "Application On Hold",
                    f"Your **{app.get('form_name', 'application')}** application (`#{self.app_id}`) has been placed **on hold** pending further review.\n**Note:** {modal.reason or 'No note provided'}",
                )
                dm_embed.set_footer(text=interaction.guild.name, icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
                await applicant.send(embed=dm_embed)
            except discord.Forbidden:
                pass

        await interaction.followup.send(embed=success_embed("Application On Hold", f"Application #{self.app_id} placed on hold."), ephemeral=True)

    @discord.ui.button(label="Request Info", style=discord.ButtonStyle.primary, emoji="💬", custom_id="app:review:request_info", row=1)
    async def request_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_reviewer(interaction):
            return

        modal = RequestInfoModal()
        await interaction.response.send_modal(modal)
        await modal.wait()

        if not modal.result:
            return

        applicant = interaction.guild.get_member(self.applicant_id)
        if not applicant:
            await interaction.followup.send(embed=error_embed("Not Found", "Could not find the applicant in the server."), ephemeral=True)
            return

        try:
            dm_embed = info_embed(
                "Additional Information Requested",
                f"A reviewer for your **{self.form_name}** application (`#{self.app_id}`) has requested more information:\n\n>>> {modal.result}",
            )
            dm_embed.set_footer(text=f"Requested by {interaction.user.display_name} • {interaction.guild.name}")
            await applicant.send(embed=dm_embed)
            await interaction.followup.send(embed=success_embed("Message Sent", f"Information request sent to {applicant.mention}."), ephemeral=True)

            embed = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed()
            embed.add_field(name=f"💬 Info Requested by {interaction.user.display_name}", value=modal.result[:512], inline=False)
            await interaction.message.edit(embed=embed)
        except discord.Forbidden:
            await interaction.followup.send(embed=error_embed("DM Failed", "Could not send a DM to the applicant (DMs disabled)."), ephemeral=True)

    @discord.ui.button(label="Add Note", style=discord.ButtonStyle.secondary, emoji="📝", custom_id="app:review:note", row=1)
    async def add_note(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_reviewer(interaction):
            return

        modal = NoteModal()
        await interaction.response.send_modal(modal)
        await modal.wait()

        if not modal.result:
            return

        from bson import ObjectId
        await Database.db.applications.update_one(
            {"_id": ObjectId(self.app_object_id)},
            {"$push": {"notes": {"by": interaction.user.id, "note": modal.result, "at": datetime.datetime.utcnow()}}},
        )

        embed = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed()
        embed.add_field(name=f"📝 Note — {interaction.user.display_name}", value=modal.result[:512], inline=False)
        await interaction.message.edit(embed=embed)
        await interaction.followup.send(embed=success_embed("Note Added", "Internal note added to the application."), ephemeral=True)
