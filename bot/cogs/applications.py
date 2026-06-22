import discord
from discord import app_commands
from discord.ext import commands
from database import Database, get_guild_config, update_guild_config
from utils import success_embed, error_embed, info_embed, primary_embed, is_admin, is_application_reviewer
from views.applications import ApplicationPanelView, ApplicationDropdownPanelView


class Applications(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    app_group = app_commands.Group(name="applications", description="Application system commands")

    @app_group.command(name="setup", description="Configure the application system")
    @app_commands.describe(
        review_channel="Channel where applications are reviewed",
        log_channel="Channel for application logs",
        reviewer_role="Role that can review applications",
        accept_role="Role given when application is accepted",
    )
    @is_admin()
    async def setup(
        self,
        interaction: discord.Interaction,
        review_channel: discord.TextChannel = None,
        log_channel: discord.TextChannel = None,
        reviewer_role: discord.Role = None,
        accept_role: discord.Role = None,
    ):
        await interaction.response.defer(ephemeral=True)
        updates = {}
        if review_channel:
            updates["application_review_channel_id"] = review_channel.id
        if log_channel:
            updates["application_log_channel_id"] = log_channel.id
        if accept_role:
            updates["application_accept_role_id"] = accept_role.id
        if reviewer_role:
            cfg = await get_guild_config(interaction.guild_id)
            reviewer_roles = cfg.get("application_reviewer_roles", [])
            if reviewer_role.id not in reviewer_roles:
                reviewer_roles.append(reviewer_role.id)
            updates["application_reviewer_roles"] = reviewer_roles

        if not updates:
            cfg = await get_guild_config(interaction.guild_id)
            embed = info_embed("Application System", "Current configuration:")
            review_ch = interaction.guild.get_channel(cfg.get("application_review_channel_id"))
            log_ch = interaction.guild.get_channel(cfg.get("application_log_channel_id"))
            accept_r = interaction.guild.get_role(cfg.get("application_accept_role_id"))
            reviewer_rs = [interaction.guild.get_role(r) for r in cfg.get("application_reviewer_roles", [])]
            embed.add_field(name="Review Channel", value=review_ch.mention if review_ch else "Not set", inline=True)
            embed.add_field(name="Log Channel", value=log_ch.mention if log_ch else "Not set", inline=True)
            embed.add_field(name="Accept Role", value=accept_r.mention if accept_r else "None", inline=True)
            embed.add_field(name="Reviewer Roles", value=", ".join(r.mention for r in reviewer_rs if r) or "None", inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        await update_guild_config(interaction.guild_id, updates)
        await interaction.followup.send(embed=success_embed("Application System Configured", "Settings saved."), ephemeral=True)

    @app_group.command(name="create", description="Create a new application form")
    @app_commands.describe(name="Form name", description="Form description")
    @is_admin()
    async def create(self, interaction: discord.Interaction, name: str, description: str = ""):
        cfg = await get_guild_config(interaction.guild_id)
        forms = cfg.get("application_forms", [])
        if any(f["name"].lower() == name.lower() for f in forms):
            await interaction.response.send_message(embed=error_embed("Already Exists", f"A form named `{name}` already exists."), ephemeral=True)
            return
        modal = FormQPage1Modal(name)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if not modal.questions:
            return
        continue_view = FormQContinueView(interaction.user.id, name, modal.questions)
        preview = "\n".join(f"`{i+1}.` {q}" for i, q in enumerate(modal.questions))
        await interaction.followup.send(
            embed=info_embed(
                f"Questions 1–5 added  ({len(modal.questions)} filled)",
                f"{preview}\n\nClick **Add Q6–Q10** to add more, or **Done** to save the form now.",
            ),
            view=continue_view,
            ephemeral=True,
        )
        await continue_view.wait()
        questions = continue_view.final_questions or modal.questions
        forms.append({"name": name, "description": description, "questions": questions, "emoji": "📋", "open": True})
        await update_guild_config(interaction.guild_id, {"application_forms": forms})
        embed = success_embed("Form Created", f"Application form **{name}** created with **{len(questions)}** question(s).")
        embed.add_field(name="Questions", value="\n".join(f"`{i+1}.` {q}" for i, q in enumerate(questions)), inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_group.command(name="delete", description="Delete an application form")
    @app_commands.describe(name="Form name to delete")
    @is_admin()
    async def delete(self, interaction: discord.Interaction, name: str):
        cfg = await get_guild_config(interaction.guild_id)
        forms = cfg.get("application_forms", [])
        new_forms = [f for f in forms if f["name"].lower() != name.lower()]
        if len(new_forms) == len(forms):
            await interaction.response.send_message(embed=error_embed("Not Found", f"No form named `{name}` found."), ephemeral=True)
            return
        await update_guild_config(interaction.guild_id, {"application_forms": new_forms})
        await interaction.response.send_message(embed=success_embed("Form Deleted", f"Form **{name}** has been deleted."), ephemeral=True)

    @app_group.command(name="edit", description="Edit an application form's questions")
    @app_commands.describe(name="Form name to edit")
    @is_admin()
    async def edit(self, interaction: discord.Interaction, name: str):
        cfg = await get_guild_config(interaction.guild_id)
        forms = cfg.get("application_forms", [])
        form = next((f for f in forms if f["name"].lower() == name.lower()), None)
        if not form:
            await interaction.response.send_message(embed=error_embed("Not Found", f"No form named `{name}` found."), ephemeral=True)
            return
        modal = FormQPage1Modal(name, existing=form.get("questions", []))
        await interaction.response.send_modal(modal)
        await modal.wait()
        if not modal.questions:
            return
        continue_view = FormQContinueView(interaction.user.id, name, modal.questions)
        preview = "\n".join(f"`{i+1}.` {q}" for i, q in enumerate(modal.questions))
        await interaction.followup.send(
            embed=info_embed(
                f"Questions 1–5 set  ({len(modal.questions)} filled)",
                f"{preview}\n\nClick **Add Q6–Q10** to add more, or **Done** to save.",
            ),
            view=continue_view,
            ephemeral=True,
        )
        await continue_view.wait()
        questions = continue_view.final_questions or modal.questions
        for f in forms:
            if f["name"].lower() == name.lower():
                f["questions"] = questions
                break
        await update_guild_config(interaction.guild_id, {"application_forms": forms})
        await interaction.followup.send(embed=success_embed("Form Updated", f"Form **{name}** updated with **{len(questions)}** question(s)."), ephemeral=True)

    @app_group.command(name="panel", description="Send an application panel to a channel")
    @app_commands.describe(channel="Channel to send the panel to")
    @is_admin()
    async def panel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        forms = cfg.get("application_forms", [])
        if not forms:
            await interaction.followup.send(embed=error_embed("No Forms", "Create application forms first with `/applications create`."), ephemeral=True)
            return

        panel_cfg = cfg.get("application_panel", {})
        color_raw = panel_cfg.get("color", 0x5865F2)
        color = int(str(color_raw).lstrip("#"), 16) if isinstance(color_raw, str) else color_raw
        style = panel_cfg.get("panel_style", "buttons")

        if style == "buttons":
            visible_forms = forms[:25]   # Discord max: 5 rows × 5 buttons
            few = len(visible_forms) <= 5
            lines: list[str] = []
            if few:
                # ── Premium aligned layout (≤5 forms) ──
                # One form section per button row so each button visually
                # sits beside its matching embed row.
                div = "─" * 32
                for form in visible_forms:
                    emoji   = form.get("emoji", "📋")
                    name    = form["name"].upper()
                    desc    = form.get("description", "")
                    is_open = form.get("open", True)
                    lock    = "  🔒" if not is_open else ""
                    lines.append(f"{emoji}  **{name}**{lock}")
                    if desc:
                        lines.append(f"-# {desc}")
                    lines.append(div)
            else:
                # ── Compact grid layout (6-25 forms) ──
                # All forms listed vertically; buttons appear as a 5-wide grid.
                div = "─" * 28
                for form in visible_forms:
                    emoji   = form.get("emoji", "📋")
                    name    = form["name"].upper()
                    desc    = form.get("description", "")
                    is_open = form.get("open", True)
                    lock    = " 🔒" if not is_open else ""
                    line = f"{emoji}  **{name}**{lock}"
                    if desc:
                        line += f" — {desc}"
                    lines.append(line)
                lines.append(div)
            # Footer instruction (use panel config value or fall back)
            footer_text = (
                panel_cfg.get("footer_text")
                or "Πατήστε το αντίστοιχο κουμπί για να υποβάλετε αίτηση."
            )

            lines.append("")
            lines.append(f"-# {footer_text}")
            embed = discord.Embed(description="\n".join(lines), color=color)
            # Banner image (large, shown at bottom of embed)
            image_url = panel_cfg.get("image") or panel_cfg.get("image_url")
            if image_url:
                embed.set_image(url=image_url)
            # Thumbnail (small icon, top-right corner)
            thumbnail_url = panel_cfg.get("thumbnail")
            if thumbnail_url:
                embed.set_thumbnail(url=thumbnail_url)

            view = ApplicationPanelView(visible_forms)
        else:
            from views.panel_customizer import build_panel_embed
            embed = build_panel_embed(panel_cfg) if panel_cfg else primary_embed("📋 Applications", "Select an application below to submit.")
            view = ApplicationDropdownPanelView(forms)

        await channel.send(embed=embed, view=view)
        await interaction.followup.send(embed=success_embed("Panel Sent", f"Application panel sent to {channel.mention}."), ephemeral=True)

    @app_group.command(name="view", description="View application statistics")
    @is_admin()
    async def view(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        total = await Database.db.applications.count_documents({"guild_id": interaction.guild_id})
        pending = await Database.db.applications.count_documents({"guild_id": interaction.guild_id, "status": "pending"})
        accepted = await Database.db.applications.count_documents({"guild_id": interaction.guild_id, "status": "accepted"})
        denied = await Database.db.applications.count_documents({"guild_id": interaction.guild_id, "status": "denied"})
        embed = info_embed("📊 Application Statistics", f"**Server:** {interaction.guild.name}")
        embed.add_field(name="Total", value=str(total), inline=True)
        embed.add_field(name="Pending", value=str(pending), inline=True)
        embed.add_field(name="Accepted", value=str(accepted), inline=True)
        embed.add_field(name="Denied", value=str(denied), inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_group.command(name="open", description="Open applications for a form")
    @app_commands.describe(name="Form name")
    @is_admin()
    async def open(self, interaction: discord.Interaction, name: str):
        cfg = await get_guild_config(interaction.guild_id)
        forms = cfg.get("application_forms", [])
        form = next((f for f in forms if f["name"].lower() == name.lower()), None)
        if not form:
            await interaction.response.send_message(embed=error_embed("Not Found", f"Form `{name}` not found."), ephemeral=True)
            return
        for f in forms:
            if f["name"].lower() == name.lower():
                f["open"] = True
        await update_guild_config(interaction.guild_id, {"application_forms": forms})
        await interaction.response.send_message(embed=success_embed("Applications Opened", f"Applications for **{name}** are now open."), ephemeral=True)

    @app_group.command(name="close", description="Close applications for a form")
    @app_commands.describe(name="Form name")
    @is_admin()
    async def close_form(self, interaction: discord.Interaction, name: str):
        cfg = await get_guild_config(interaction.guild_id)
        forms = cfg.get("application_forms", [])
        form = next((f for f in forms if f["name"].lower() == name.lower()), None)
        if not form:
            await interaction.response.send_message(embed=error_embed("Not Found", f"Form `{name}` not found."), ephemeral=True)
            return
        for f in forms:
            if f["name"].lower() == name.lower():
                f["open"] = False
        await update_guild_config(interaction.guild_id, {"application_forms": forms})
        await interaction.response.send_message(embed=success_embed("Applications Closed", f"Applications for **{name}** are now closed."), ephemeral=True)

    @app_group.command(name="customize", description="Open the interactive application panel customizer")
    @is_admin()
    async def customize(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        data = dict(cfg.get("application_panel", {}))
        if "forms" not in data:
            data["forms"] = cfg.get("application_forms", [])
        from views.panel_customizer import AppPanelCustomizerView
        view = AppPanelCustomizerView(interaction.user.id, data)
        forms = data.get("forms", [])
        lines = [
            f"**Title:** {data.get('title') or '*Not set*'}",
            f"**Color:** #{data.get('color', 0x5865F2):06X}" if isinstance(data.get('color'), int) else f"**Color:** {data.get('color', '#5865F2')}",
            f"**Thumbnail:** {'✅' if data.get('thumbnail') else '❌'}",
            f"**Image:** {'✅' if data.get('image') else '❌'}",
            f"**Footer:** {data.get('footer_text') or '*Not set*'}",
            f"**Forms:** {', '.join(f['name'] for f in forms) if forms else '*None — add at least 1*'}",
        ]
        embed = primary_embed("📋 Application Panel Customizer", "\n".join(lines))
        embed.set_footer(text="Use the buttons below to customize • Preview shows a live preview")
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @app_group.command(name="reset", description="Reset all application data")
    @is_admin()
    async def reset(self, interaction: discord.Interaction):
        from views.confirm import ConfirmView
        view = ConfirmView(interaction.user.id)
        await interaction.response.send_message(embed=discord.Embed(title="⚠️ Reset Applications", description="This will delete all application data and forms.", color=0xE74C3C), view=view, ephemeral=True)
        await view.wait()
        if view.value:
            await Database.db.applications.delete_many({"guild_id": interaction.guild_id})
            await update_guild_config(interaction.guild_id, {"application_forms": [], "application_review_channel_id": None})
            await interaction.edit_original_response(embed=success_embed("Reset", "All application data deleted."), view=None)


class FormQPage1Modal(discord.ui.Modal):
    q1 = discord.ui.TextInput(label="Question 1  *required", max_length=45, required=True)
    q2 = discord.ui.TextInput(label="Question 2  (optional)", max_length=45, required=False)
    q3 = discord.ui.TextInput(label="Question 3  (optional)", max_length=45, required=False)
    q4 = discord.ui.TextInput(label="Question 4  (optional)", max_length=45, required=False)
    q5 = discord.ui.TextInput(label="Question 5  (optional)", max_length=45, required=False)
    def __init__(self, form_name: str, existing: list[str] | None = None):
        super().__init__(title=f"'{form_name[:25]}' — Q1–Q5")
        existing = existing or []
        fields = [self.q1, self.q2, self.q3, self.q4, self.q5]
        for i, f in enumerate(fields):
            f.default = existing[i] if i < len(existing) else ""
        self.questions: list[str] = []

    async def on_submit(self, interaction: discord.Interaction):
        self.questions = [q for q in [
            self.q1.value.strip(), self.q2.value.strip(),
            self.q3.value.strip(), self.q4.value.strip(), self.q5.value.strip(),
        ] if q]
        await interaction.response.defer()
        self.stop()

class FormQPage2Modal(discord.ui.Modal):
    q6  = discord.ui.TextInput(label="Question 6  (optional)", max_length=45, required=False)
    q7  = discord.ui.TextInput(label="Question 7  (optional)", max_length=45, required=False)
    q8  = discord.ui.TextInput(label="Question 8  (optional)", max_length=45, required=False)
    q9  = discord.ui.TextInput(label="Question 9  (optional)", max_length=45, required=False)
    q10 = discord.ui.TextInput(label="Question 10 (optional)", max_length=45, required=False)
    def __init__(self, form_name: str, existing: list[str] | None = None):
        super().__init__(title=f"'{form_name[:25]}' — Q6–Q10")
        existing = existing or []
        fields = [self.q6, self.q7, self.q8, self.q9, self.q10]
        for i, f in enumerate(fields):
            f.default = existing[i + 5] if i + 5 < len(existing) else ""
        self.questions: list[str] = []
    async def on_submit(self, interaction: discord.Interaction):
        self.questions = [q for q in [
            self.q6.value.strip(), self.q7.value.strip(),
            self.q8.value.strip(), self.q9.value.strip(), self.q10.value.strip(),
        ] if q]
        await interaction.response.defer()
        self.stop()
class FormQContinueView(discord.ui.View):
    """Appears after Q1-Q5, lets the user optionally add Q6-Q10 then signals done."""
    def __init__(self, user_id: int, form_name: str, page1_qs: list[str]):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.form_name = form_name
        self.page1_qs = page1_qs
        self.final_questions: list[str] | None = None
    def _disable_all(self):
        for child in self.children:
            child.disabled = True  # type: ignore[union-attr]
    @discord.ui.button(label="➕ Add Q6–Q10 (optional)", style=discord.ButtonStyle.primary)
    async def add_more(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Not yours.", ephemeral=True)
            return
        modal = FormQPage2Modal(self.form_name)
        await interaction.response.send_modal(modal)
        await modal.wait()
        self.final_questions = self.page1_qs + modal.questions
        self._disable_all()
        await interaction.message.edit(view=self)
        self.stop()
    @discord.ui.button(label="💾 Done  (Q1–Q5 only)", style=discord.ButtonStyle.success)
    async def done(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Not yours.", ephemeral=True)
            return
        self.final_questions = self.page1_qs
        self._disable_all()
        await interaction.response.edit_message(view=self)
        self.stop()
FormQuestionModal = FormQPage1Modal


async def setup(bot: commands.Bot):
    await bot.add_cog(Applications(bot))

