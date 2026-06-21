import discord
import datetime
from discord import app_commands
from discord.ext import commands
from database import Database, get_guild_config, update_guild_config
from utils import success_embed, error_embed, primary_embed, warning_embed, info_embed, is_admin, is_application_reviewer
from views.applications import ApplicationDropdownPanelView, ApplicationPanelView
from views.panel_customizer import AppPanelCustomizerView, build_panel_embed


class ApplicationSelect(discord.ui.Select):
    def __init__(self, forms: list[dict]):
        options = [
            discord.SelectOption(
                label=f["name"],
                description=f.get("description", "")[:100],
                emoji=f.get("emoji", "📋"),
                value=f["name"],
            )
            for f in forms[:25]
        ]
        super().__init__(placeholder="Select an application to submit...", options=options)

    async def callback(self, interaction: discord.Interaction):
        cfg = await get_guild_config(interaction.guild_id)
        forms = cfg.get("application_forms", [])
        form = next((f for f in forms if f["name"] == self.values[0]), None)
        if not form:
            await interaction.response.send_message(embed=error_embed("Not Found", "Form not found."), ephemeral=True)
            return

        existing = await Database.db.applications.find_one({
            "guild_id": interaction.guild_id,
            "user_id": interaction.user.id,
            "form_name": form["name"],
            "status": "pending",
        })
        if existing:
            await interaction.response.send_message(
                embed=warning_embed("Pending Application", f"You already have a pending **{form['name']}** application."),
                ephemeral=True,
            )
            return

        questions = form.get("questions", [])
        if not questions:
            await interaction.response.send_message(embed=error_embed("No Questions", "This form has no questions configured."), ephemeral=True)
            return

        modal = ApplicationModal(form, questions[:5])
        await interaction.response.send_modal(modal)


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

        app_count = await Database.db.applications.count_documents({"guild_id": interaction.guild_id}) + 1
        doc = {
            "guild_id": interaction.guild_id,
            "user_id": interaction.user.id,
            "form_name": self.form["name"],
            "answers": answers,
            "status": "pending",
            "app_id": app_count,
            "created_at": datetime.datetime.utcnow(),
            "reviewed_by": None,
            "message_id": None,
        }

        result = await Database.db.applications.insert_one(doc)

        review_channel_id = self.form.get("review_channel_id") or cfg.get("application_review_channel_id")
        if review_channel_id:
            channel = interaction.guild.get_channel(review_channel_id)
            if channel:
                embed = primary_embed(
                    f"📋 {self.form['name']} Application #{app_count}",
                    f"**Applicant:** {interaction.user.mention}\n**User ID:** {interaction.user.id}",
                )
                embed.set_thumbnail(url=interaction.user.display_avatar.url)
                for question, answer in answers.items():
                    embed.add_field(name=question, value=answer[:1024] or "No answer", inline=False)
                embed.set_footer(text=f"Application ID: {app_count}")
                embed.timestamp = datetime.datetime.utcnow()

                view = ApplicationReviewView(str(result.inserted_id), interaction.user.id)
                msg = await channel.send(embed=embed, view=view)
                await Database.db.applications.update_one(
                    {"_id": result.inserted_id},
                    {"$set": {"message_id": msg.id}},
                )

        await interaction.response.send_message(
            embed=success_embed("Application Submitted", f"Your **{self.form['name']}** application has been submitted successfully!"),
            ephemeral=True,
        )


class ApplicationFormButton(discord.ui.Button):
    def __init__(self, form: dict, row: int):
        emoji_str = form.get("emoji", "📋")
        super().__init__(
            style=discord.ButtonStyle.secondary,
            emoji=emoji_str,
            custom_id=f"app:btn:{form['name'][:80]}",
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
        if not form.get("open", True):
            await interaction.response.send_message(embed=error_embed("Closed", f"Applications for **{form['name']}** are currently closed."), ephemeral=True)
            return
        existing = await Database.db.applications.find_one({
            "guild_id": interaction.guild_id,
            "user_id": interaction.user.id,
            "form_name": form["name"],
            "status": "pending",
        })
        if existing:
            await interaction.response.send_message(
                embed=warning_embed("Pending Application", f"You already have a pending **{form['name']}** application."),
                ephemeral=True,
            )
            return
        questions = form.get("questions", [])
        if not questions:
            await interaction.response.send_message(embed=error_embed("No Questions", "This form has no questions configured."), ephemeral=True)
            return
        modal = ApplicationModal(form, questions[:5])
        await interaction.response.send_modal(modal)


class ApplicationPanelView(discord.ui.View):
    """Buttons style — one emoji button per form."""
    def __init__(self, forms: list[dict]):
        super().__init__(timeout=None)
        for i, form in enumerate(forms[:25]):
            self.add_item(ApplicationFormButton(form, row=i // 5))


class ApplicationDropdownPanelView(discord.ui.View):
    """Dropdown style — single select menu."""
    def __init__(self, forms: list[dict]):
        super().__init__(timeout=None)
        self.add_item(ApplicationSelect(forms))


class ApplicationReviewView(discord.ui.View):
    def __init__(self, app_object_id: str, applicant_id: int):
        super().__init__(timeout=None)
        self.app_object_id = app_object_id
        self.applicant_id = applicant_id

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, emoji="✅", custom_id="app:accept")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await get_guild_config(interaction.guild_id)
        reviewer_roles = cfg.get("application_reviewer_roles", [])
        if not interaction.user.guild_permissions.administrator and not any(r.id in reviewer_roles for r in interaction.user.roles):
            await interaction.response.send_message(embed=error_embed("No Permission", "You are not a reviewer."), ephemeral=True)
            return

        modal = ReviewModal("accept")
        await interaction.response.send_modal(modal)
        await modal.wait()

        from bson import ObjectId
        app = await Database.db.applications.find_one_and_update(
            {"_id": ObjectId(self.app_object_id)},
            {"$set": {"status": "accepted", "reviewed_by": interaction.user.id, "review_reason": modal.reason}},
        )
        if not app:
            return

        applicant = interaction.guild.get_member(self.applicant_id)
        accept_role_id = cfg.get("application_accept_role_id")
        if accept_role_id and applicant:
            role = interaction.guild.get_role(accept_role_id)
            if role:
                try:
                    await applicant.add_roles(role, reason="Application accepted")
                except discord.Forbidden:
                    pass

        embed = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed()
        embed.color = 0x2ECC71
        embed.title = f"✅ ACCEPTED — {embed.title}"
        embed.add_field(name="Reviewed By", value=interaction.user.mention, inline=True)
        embed.add_field(name="Reason", value=modal.reason or "No reason provided", inline=True)
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(embed=embed, view=self)

        if applicant:
            try:
                dm_embed = success_embed(
                    "Application Accepted",
                    f"Your **{app['form_name']}** application has been **accepted**!\n**Reason:** {modal.reason or 'No reason provided'}",
                )
                await applicant.send(embed=dm_embed)
            except discord.Forbidden:
                pass

        log_channel_id = cfg.get("application_log_channel_id")
        if log_channel_id:
            log_ch = interaction.guild.get_channel(log_channel_id)
            if log_ch:
                log_embed = success_embed(
                    "Application Accepted",
                    f"**Applicant:** {applicant.mention if applicant else self.applicant_id}\n**Form:** {app['form_name']}\n**Reviewed by:** {interaction.user.mention}",
                )
                await log_ch.send(embed=log_embed)

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger, emoji="❌", custom_id="app:deny")
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await get_guild_config(interaction.guild_id)
        reviewer_roles = cfg.get("application_reviewer_roles", [])
        if not interaction.user.guild_permissions.administrator and not any(r.id in reviewer_roles for r in interaction.user.roles):
            await interaction.response.send_message(embed=error_embed("No Permission", "You are not a reviewer."), ephemeral=True)
            return

        modal = ReviewModal("deny")
        await interaction.response.send_modal(modal)
        await modal.wait()

        from bson import ObjectId
        app = await Database.db.applications.find_one_and_update(
            {"_id": ObjectId(self.app_object_id)},
            {"$set": {"status": "denied", "reviewed_by": interaction.user.id, "review_reason": modal.reason}},
        )
        if not app:
            return

        embed = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed()
        embed.color = 0xE74C3C
        embed.title = f"❌ DENIED — {embed.title}"
        embed.add_field(name="Reviewed By", value=interaction.user.mention, inline=True)
        embed.add_field(name="Reason", value=modal.reason or "No reason provided", inline=True)
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(embed=embed, view=self)

        applicant = interaction.guild.get_member(self.applicant_id)
        if applicant:
            try:
                dm_embed = error_embed(
                    "Application Denied",
                    f"Your **{app['form_name']}** application has been **denied**.\n**Reason:** {modal.reason or 'No reason provided'}",
                )
                await applicant.send(embed=dm_embed)
            except discord.Forbidden:
                pass


class ReviewModal(discord.ui.Modal, title="Review Reason"):
    reason_input = discord.ui.TextInput(
        label="Reason (optional)",
        style=discord.TextStyle.paragraph,
        required=False,
        placeholder="Enter reason...",
        max_length=500,
    )

    def __init__(self, action: str):
        super().__init__(title=f"{'Accept' if action == 'accept' else 'Deny'} Application")
        self.reason = ""

    async def on_submit(self, interaction: discord.Interaction):
        self.reason = self.reason_input.value
        await interaction.response.defer()
        self.stop()


class Applications(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    applications_group = app_commands.Group(name="applications", description="Application form and panel commands")

    @applications_group.command(name="setup", description="Configure review channel and roles")
    @app_commands.describe(
        review_channel="Channel where applications are reviewed",
        reviewer_role="Role that can review applications",
        accept_role="Role given when applications are accepted",
        log_channel="Channel for application logs",
    )
    @is_admin()
    async def setup(
        self,
        interaction: discord.Interaction,
        review_channel: discord.TextChannel = None,
        reviewer_role: discord.Role = None,
        accept_role: discord.Role = None,
        log_channel: discord.TextChannel = None,
    ):
        await interaction.response.defer(ephemeral=True)
        updates = {}
        if review_channel:
            updates["application_review_channel_id"] = review_channel.id
        if reviewer_role:
            cfg = await get_guild_config(interaction.guild_id)
            roles = cfg.get("application_reviewer_roles", [])
            if reviewer_role.id not in roles:
                roles.append(reviewer_role.id)
            updates["application_reviewer_roles"] = roles
        if accept_role:
            updates["application_accept_role_id"] = accept_role.id
        if log_channel:
            updates["application_log_channel_id"] = log_channel.id

        if updates:
            await update_guild_config(interaction.guild_id, updates)
            await interaction.followup.send(
                embed=success_embed("Applications Setup Updated", "Application review settings have been saved."),
                ephemeral=True,
            )
            return

        cfg = await get_guild_config(interaction.guild_id)
        review_channel_id = cfg.get("application_review_channel_id")
        reviewer_roles = cfg.get("application_reviewer_roles", [])
        accept_role_id = cfg.get("application_accept_role_id")
        log_channel_id = cfg.get("application_log_channel_id")
        forms = cfg.get("application_forms", [])

        embed = info_embed("📋 Application Settings", f"**{interaction.guild.name}**")
        embed.add_field(
            name="Review Channel",
            value=(interaction.guild.get_channel(review_channel_id).mention if review_channel_id and interaction.guild.get_channel(review_channel_id) else "Not set"),
            inline=False,
        )
        embed.add_field(
            name="Reviewer Roles",
            value=(", ".join(interaction.guild.get_role(r).mention for r in reviewer_roles if interaction.guild.get_role(r)) or "None"),
            inline=False,
        )
        embed.add_field(
            name="Accept Role",
            value=(interaction.guild.get_role(accept_role_id).mention if accept_role_id and interaction.guild.get_role(accept_role_id) else "Not set"),
            inline=False,
        )
        embed.add_field(
            name="Log Channel",
            value=(interaction.guild.get_channel(log_channel_id).mention if log_channel_id and interaction.guild.get_channel(log_channel_id) else "Not set"),
            inline=False,
        )
        embed.add_field(name="Application Forms", value=str(len(forms)), inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @applications_group.command(name="create", description="Create a new application form")
    @app_commands.describe(
        name="Application form name",
        description="Short description shown on the panel",
        emoji="Emoji shown next to the form name",
        review_channel="Channel where this form is reviewed",
        question1="First application question",
        question2="Second application question",
        question3="Third application question",
        is_open="Whether applications are open for this form",
    )
    @is_admin()
    async def create(
        self,
        interaction: discord.Interaction,
        name: str,
        description: str = "",
        emoji: str = "📋",
        review_channel: discord.TextChannel = None,
        question1: str = None,
        question2: str = None,
        question3: str = None,
        is_open: bool = True,
    ):
        await interaction.response.defer(ephemeral=True)
        questions = [q.strip() for q in (question1, question2, question3) if q and q.strip()]
        if not questions:
            await interaction.followup.send(
                embed=error_embed("Missing Questions", "You must provide at least one question for the form."),
                ephemeral=True,
            )
            return

        cfg = await get_guild_config(interaction.guild_id)
        forms = cfg.get("application_forms", [])
        if any(f["name"].lower() == name.lower() for f in forms):
            await interaction.followup.send(
                embed=error_embed("Form Exists", f"An application form named **{name}** already exists."),
                ephemeral=True,
            )
            return

        form = {
            "name": name,
            "description": description or "",
            "emoji": emoji or "📋",
            "questions": questions,
            "open": is_open,
            "review_channel_id": review_channel.id if review_channel else None,
        }
        forms.append(form)
        await update_guild_config(interaction.guild_id, {"application_forms": forms})
        await interaction.followup.send(
            embed=success_embed("Application Form Created", f"Created application form **{name}**."),
            ephemeral=True,
        )

    @applications_group.command(name="edit", description="Edit an existing application form")
    @app_commands.describe(
        form_name="The name of the form to edit",
        new_name="New form name",
        description="New description for the form",
        emoji="New emoji for the form",
        review_channel="New review channel for this form",
        question1="Question 1",
        question2="Question 2",
        question3="Question 3",
        is_open="Whether this form is open",
    )
    @is_admin()
    async def edit(
        self,
        interaction: discord.Interaction,
        form_name: str,
        new_name: str = None,
        description: str = None,
        emoji: str = None,
        review_channel: discord.TextChannel = None,
        question1: str = None,
        question2: str = None,
        question3: str = None,
        is_open: bool = None,
    ):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        forms = cfg.get("application_forms", [])
        form = next((f for f in forms if f["name"].lower() == form_name.lower()), None)
        if not form:
            await interaction.followup.send(
                embed=error_embed("Not Found", f"No application form named **{form_name}** exists."),
                ephemeral=True,
            )
            return

        if new_name:
            if any(f["name"].lower() == new_name.lower() and f is not form for f in forms):
                await interaction.followup.send(
                    embed=error_embed("Name Taken", f"Another form already uses the name **{new_name}**."),
                    ephemeral=True,
                )
                return
            form["name"] = new_name
        if description is not None:
            form["description"] = description
        if emoji is not None:
            form["emoji"] = emoji or "📋"
        if review_channel is not None:
            form["review_channel_id"] = review_channel.id
        if any(q is not None for q in (question1, question2, question3)):
            questions = [q.strip() for q in (question1, question2, question3) if q and q.strip()]
            if not questions:
                await interaction.followup.send(
                    embed=error_embed("Missing Questions", "If you update questions, include at least one non-empty question."),
                    ephemeral=True,
                )
                return
            form["questions"] = questions
        if is_open is not None:
            form["open"] = is_open

        await update_guild_config(interaction.guild_id, {"application_forms": forms})
        await interaction.followup.send(
            embed=success_embed("Application Form Updated", f"Updated application form **{form.get('name')}**."),
            ephemeral=True,
        )

    @applications_group.command(name="delete", description="Delete an application form")
    @app_commands.describe(form_name="The name of the form to delete")
    @is_admin()
    async def delete(self, interaction: discord.Interaction, form_name: str):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        forms = cfg.get("application_forms", [])
        new_forms = [f for f in forms if f["name"].lower() != form_name.lower()]
        if len(new_forms) == len(forms):
            await interaction.followup.send(
                embed=error_embed("Not Found", f"No application form named **{form_name}** exists."),
                ephemeral=True,
            )
            return
        await update_guild_config(interaction.guild_id, {"application_forms": new_forms})
        await interaction.followup.send(
            embed=success_embed("Form Deleted", f"Deleted application form **{form_name}**."),
            ephemeral=True,
        )

    @applications_group.command(name="panel", description="Send an application panel to a channel")
    @app_commands.describe(channel="Channel to send the panel to")
    @is_admin()
    async def panel(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        forms = cfg.get("application_forms", [])
        if not forms:
            await interaction.followup.send(
                embed=error_embed("No Forms", "Create at least one application form before sending a panel."),
                ephemeral=True,
            )
            return

        panel_data = cfg.get("application_panel", {})
        embed = build_panel_embed(
            panel_data or {
                "title": "📋 Applications",
                "description": "Select an application below to submit your answers.",
                "color": 0x5865F2,
                "footer_text": f"{interaction.guild.name} • Applications",
            }
        )
        style = panel_data.get("panel_style", "buttons")
        if style == "dropdown":
            view = ApplicationDropdownPanelView(forms)
        else:
            view = ApplicationPanelView(forms)

        target_channel = channel or interaction.channel
        await target_channel.send(embed=embed, view=view)
        await interaction.followup.send(
            embed=success_embed("Panel Sent", f"Application panel sent to {target_channel.mention}."),
            ephemeral=True,
        )

    @applications_group.command(name="customize", description="Customize the application panel appearance")
    @is_admin()
    async def customize(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        panel_data = cfg.get("application_panel", {})
        view = AppPanelCustomizerView(interaction.user.id, panel_data)
        embed = build_panel_embed(panel_data or {
            "title": "📋 Applications",
            "description": "Select an application below to submit your answers.",
            "color": 0x5865F2,
            "footer_text": f"{interaction.guild.name} • Applications",
        })
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @applications_group.command(name="open", description="Open applications for a form")
    @app_commands.describe(form_name="The name of the form to open")
    @is_admin()
    async def open_form(self, interaction: discord.Interaction, form_name: str):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        forms = cfg.get("application_forms", [])
        form = next((f for f in forms if f["name"].lower() == form_name.lower()), None)
        if not form:
            await interaction.followup.send(
                embed=error_embed("Not Found", f"No application form named **{form_name}** exists."),
                ephemeral=True,
            )
            return
        form["open"] = True
        await update_guild_config(interaction.guild_id, {"application_forms": forms})
        await interaction.followup.send(
            embed=success_embed("Application Opened", f"**{form['name']}** is now open."),
            ephemeral=True,
        )

    @applications_group.command(name="close", description="Close applications for a form")
    @app_commands.describe(form_name="The name of the form to close")
    @is_admin()
    async def close_form(self, interaction: discord.Interaction, form_name: str):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        forms = cfg.get("application_forms", [])
        form = next((f for f in forms if f["name"].lower() == form_name.lower()), None)
        if not form:
            await interaction.followup.send(
                embed=error_embed("Not Found", f"No application form named **{form_name}** exists."),
                ephemeral=True,
            )
            return
        form["open"] = False
        await update_guild_config(interaction.guild_id, {"application_forms": forms})
        await interaction.followup.send(
            embed=success_embed("Application Closed", f"**{form['name']}** is now closed."),
            ephemeral=True,
        )

    @applications_group.command(name="approve", description="Approve a pending application")
    @app_commands.describe(application_id="Application ID to approve", reason="Optional reason for approval")
    @is_application_reviewer()
    async def approve(self, interaction: discord.Interaction, application_id: int, reason: str = None):
        await interaction.response.defer(ephemeral=True)
        app_doc = await Database.db.applications.find_one(
            {"guild_id": interaction.guild_id, "app_id": application_id, "status": "pending"}
        )
        if not app_doc:
            await interaction.followup.send(
                embed=error_embed("Not Found", f"Pending application #{application_id} not found."),
                ephemeral=True,
            )
            return

        await Database.db.applications.update_one(
            {"_id": app_doc["_id"]},
            {"$set": {"status": "accepted", "reviewed_by": interaction.user.id, "review_reason": reason}},
        )

        cfg = await get_guild_config(interaction.guild_id)
        applicant = interaction.guild.get_member(app_doc["user_id"])
        accept_role_id = cfg.get("application_accept_role_id")
        if accept_role_id and applicant:
            role = interaction.guild.get_role(accept_role_id)
            if role:
                try:
                    await applicant.add_roles(role, reason="Application accepted")
                except discord.Forbidden:
                    pass

        if applicant:
            try:
                await applicant.send(
                    embed=success_embed(
                        "Application Accepted",
                        f"Your application **#{application_id}** has been accepted!\nReason: {reason or 'No reason provided'}",
                    )
                )
            except discord.Forbidden:
                pass

        log_channel_id = cfg.get("application_log_channel_id")
        if log_channel_id:
            log_channel = interaction.guild.get_channel(log_channel_id)
            if log_channel:
                await log_channel.send(
                    embed=success_embed(
                        "Application Approved",
                        f"**Applicant:** <@{app_doc['user_id']}>\n**Application #:** {application_id}\n**Reason:** {reason or 'No reason provided'}",
                    )
                )

        await interaction.followup.send(
            embed=success_embed("Application Approved", f"Application #{application_id} has been approved."),
            ephemeral=True,
        )

    @applications_group.command(name="deny", description="Deny a pending application")
    @app_commands.describe(application_id="Application ID to deny", reason="Optional reason for denial")
    @is_application_reviewer()
    async def deny(self, interaction: discord.Interaction, application_id: int, reason: str = None):
        await interaction.response.defer(ephemeral=True)
        app_doc = await Database.db.applications.find_one(
            {"guild_id": interaction.guild_id, "app_id": application_id, "status": "pending"}
        )
        if not app_doc:
            await interaction.followup.send(
                embed=error_embed("Not Found", f"Pending application #{application_id} not found."),
                ephemeral=True,
            )
            return

        await Database.db.applications.update_one(
            {"_id": app_doc["_id"]},
            {"$set": {"status": "denied", "reviewed_by": interaction.user.id, "review_reason": reason}},
        )

        applicant = interaction.guild.get_member(app_doc["user_id"])
        if applicant:
            try:
                await applicant.send(
                    embed=error_embed(
                        "Application Denied",
                        f"Your application **#{application_id}** has been denied.\nReason: {reason or 'No reason provided'}",
                    )
                )
            except discord.Forbidden:
                pass

        cfg = await get_guild_config(interaction.guild_id)
        log_channel_id = cfg.get("application_log_channel_id")
        if log_channel_id:
            log_channel = interaction.guild.get_channel(log_channel_id)
            if log_channel:
                await log_channel.send(
                    embed=error_embed(
                        "Application Denied",
                        f"**Applicant:** <@{app_doc['user_id']}>\n**Application #:** {application_id}\n**Reason:** {reason or 'No reason provided'}",
                    )
                )

        await interaction.followup.send(
            embed=success_embed("Application Denied", f"Application #{application_id} has been denied."),
            ephemeral=True,
        )

    @applications_group.command(name="view", description="View application statistics")
    @is_admin()
    async def view(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        forms = cfg.get("application_forms", [])
        pending = await Database.db.applications.count_documents({"guild_id": interaction.guild_id, "status": "pending"})
        accepted = await Database.db.applications.count_documents({"guild_id": interaction.guild_id, "status": "accepted"})
        denied = await Database.db.applications.count_documents({"guild_id": interaction.guild_id, "status": "denied"})

        embed = info_embed("📊 Application Statistics", f"**{interaction.guild.name}**")
        embed.add_field(name="Application Forms", value=str(len(forms)), inline=True)
        embed.add_field(name="Pending", value=str(pending), inline=True)
        embed.add_field(name="Accepted", value=str(accepted), inline=True)
        embed.add_field(name="Denied", value=str(denied), inline=True)
        if forms:
            embed.add_field(
                name="Forms",
                value="\n".join(
                    f"{f.get('emoji','📋')} **{f['name']}** — {'Open' if f.get('open', True) else 'Closed'}"
                    for f in forms[:10]
                ) + ("\n..." if len(forms) > 10 else ""),
                inline=False,
            )
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Applications(bot))
