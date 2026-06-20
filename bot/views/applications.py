import discord
import datetime
from database import Database, get_guild_config
from utils.helpers import success_embed, error_embed, primary_embed, warning_embed


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
        if not form.get("is_open", True):
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
