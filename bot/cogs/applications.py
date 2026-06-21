import discord
import datetime
from discord import app_commands
from discord.ext import commands
from database import Database, get_guild_config, update_guild_config
from utils import success_embed, error_embed, primary_embed, warning_embed, info_embed, is_admin, is_application_reviewer
from views.applications import ApplicationDropdownPanelView, ApplicationPanelView, ApplicationReviewView
from views.panel_customizer import AppPanelCustomizerView, build_panel_embed


# ─── Autocomplete helpers ─────────────────────────────────────────────────────

async def form_name_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    cfg = await get_guild_config(interaction.guild_id)
    forms = cfg.get("application_forms", [])
    return [
        app_commands.Choice(name=f["name"], value=f["name"])
        for f in forms
        if current.lower() in f["name"].lower()
    ][:25]


def _bar(value: int, total: int, width: int = 12) -> str:
    fill = int((value / total) * width) if total else 0
    return "█" * fill + "░" * (width - fill)


# ─── Cog ──────────────────────────────────────────────────────────────────────

class Applications(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    applications_group = app_commands.Group(name="applications", description="Application form and panel commands")

    # ── Setup ──────────────────────────────────────────────────────────────────

    @applications_group.command(name="setup", description="Configure the application review channel, roles, and settings")
    @app_commands.describe(
        review_channel="Default channel where all applications are sent for review",
        reviewer_role="Role that can review applications",
        accept_role="Role automatically given when an application is accepted",
        log_channel="Channel for application activity logs",
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
        review_ch = interaction.guild.get_channel(cfg.get("application_review_channel_id"))
        log_ch = interaction.guild.get_channel(cfg.get("application_log_channel_id"))
        reviewer_roles = [interaction.guild.get_role(r) for r in cfg.get("application_reviewer_roles", [])]
        accept_r = interaction.guild.get_role(cfg.get("application_accept_role_id"))
        forms = cfg.get("application_forms", [])

        embed = info_embed("📋 Application Settings", f"**{interaction.guild.name}**")
        embed.add_field(name="Review Channel", value=review_ch.mention if review_ch else "Not set", inline=False)
        embed.add_field(name="Reviewer Roles", value=", ".join(r.mention for r in reviewer_roles if r) or "None", inline=False)
        embed.add_field(name="Accept Role", value=accept_r.mention if accept_r else "Not set", inline=False)
        embed.add_field(name="Log Channel", value=log_ch.mention if log_ch else "Not set", inline=False)
        embed.add_field(name="Application Forms", value=f"**{len(forms)}** form(s) configured", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── Create ─────────────────────────────────────────────────────────────────

    @applications_group.command(name="create", description="Create a new application form with up to 5 questions")
    @app_commands.describe(
        name="Application form name",
        description="Short description shown on the panel",
        emoji="Emoji shown next to the form name",
        review_channel="Specific review channel for this form (overrides default)",
        accept_role="Role given when this specific form is accepted",
        question1="First application question",
        question2="Second application question",
        question3="Third application question",
        question4="Fourth application question",
        question5="Fifth application question",
        is_open="Whether applications are open for this form right now",
        cooldown_minutes="Minutes users must wait before resubmitting (0 = no cooldown)",
    )
    @is_admin()
    async def create(
        self,
        interaction: discord.Interaction,
        name: str,
        question1: str,
        description: str = "",
        emoji: str = "📋",
        review_channel: discord.TextChannel = None,
        accept_role: discord.Role = None,
        question2: str = None,
        question3: str = None,
        question4: str = None,
        question5: str = None,
        is_open: bool = True,
        cooldown_minutes: int = 0,
    ):
        await interaction.response.defer(ephemeral=True)
        questions = [q.strip() for q in [question1, question2, question3, question4, question5] if q and q.strip()]

        cfg = await get_guild_config(interaction.guild_id)
        forms = cfg.get("application_forms", [])
        if any(f["name"].lower() == name.lower() for f in forms):
            await interaction.followup.send(
                embed=error_embed("Form Exists", f"An application form named **{name}** already exists."),
                ephemeral=True,
            )
            return
        if len(forms) >= 25:
            await interaction.followup.send(embed=error_embed("Limit Reached", "You can have at most 25 application forms."), ephemeral=True)
            return

        form = {
            "name": name,
            "description": description or "",
            "emoji": emoji or "📋",
            "questions": questions,
            "open": is_open,
            "review_channel_id": review_channel.id if review_channel else None,
            "accept_role_id": accept_role.id if accept_role else None,
            "cooldown_minutes": max(0, cooldown_minutes),
        }
        forms.append(form)
        await update_guild_config(interaction.guild_id, {"application_forms": forms})

        embed = success_embed("Application Form Created", f"Created application form **{name}**.")
        embed.add_field(name="Questions", value="\n".join(f"`{i+1}.` {q}" for i, q in enumerate(questions)), inline=False)
        embed.add_field(name="Status", value="🟢 Open" if is_open else "🔴 Closed", inline=True)
        if cooldown_minutes > 0:
            embed.add_field(name="Cooldown", value=f"{cooldown_minutes} minutes", inline=True)
        if review_channel:
            embed.add_field(name="Review Channel", value=review_channel.mention, inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── Edit ───────────────────────────────────────────────────────────────────

    @applications_group.command(name="edit", description="Edit an existing application form")
    @app_commands.describe(
        form_name="The form to edit",
        new_name="New form name",
        description="New description",
        emoji="New emoji",
        review_channel="New dedicated review channel",
        accept_role="New accept role for this form",
        question1="Replace question 1",
        question2="Replace question 2",
        question3="Replace question 3",
        question4="Replace question 4",
        question5="Replace question 5",
        is_open="Whether this form is open",
        cooldown_minutes="Submission cooldown in minutes (0 = none)",
    )
    @app_commands.autocomplete(form_name=form_name_autocomplete)
    @is_admin()
    async def edit(
        self,
        interaction: discord.Interaction,
        form_name: str,
        new_name: str = None,
        description: str = None,
        emoji: str = None,
        review_channel: discord.TextChannel = None,
        accept_role: discord.Role = None,
        question1: str = None,
        question2: str = None,
        question3: str = None,
        question4: str = None,
        question5: str = None,
        is_open: bool = None,
        cooldown_minutes: int = None,
    ):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        forms = cfg.get("application_forms", [])
        form = next((f for f in forms if f["name"].lower() == form_name.lower()), None)
        if not form:
            await interaction.followup.send(embed=error_embed("Not Found", f"No form named **{form_name}** exists."), ephemeral=True)
            return

        if new_name:
            if any(f["name"].lower() == new_name.lower() and f is not form for f in forms):
                await interaction.followup.send(embed=error_embed("Name Taken", f"Another form already uses **{new_name}**."), ephemeral=True)
                return
            form["name"] = new_name
        if description is not None:
            form["description"] = description
        if emoji is not None:
            form["emoji"] = emoji or "📋"
        if review_channel is not None:
            form["review_channel_id"] = review_channel.id
        if accept_role is not None:
            form["accept_role_id"] = accept_role.id
        if any(q is not None for q in [question1, question2, question3, question4, question5]):
            new_qs = [q.strip() for q in [question1, question2, question3, question4, question5] if q and q.strip()]
            if not new_qs:
                await interaction.followup.send(embed=error_embed("Missing Questions", "Provide at least one non-empty question."), ephemeral=True)
                return
            form["questions"] = new_qs
        if is_open is not None:
            form["open"] = is_open
        if cooldown_minutes is not None:
            form["cooldown_minutes"] = max(0, cooldown_minutes)

        await update_guild_config(interaction.guild_id, {"application_forms": forms})
        await interaction.followup.send(
            embed=success_embed("Form Updated", f"Application form **{form.get('name')}** has been updated."),
            ephemeral=True,
        )

    # ── Delete ─────────────────────────────────────────────────────────────────

    @applications_group.command(name="delete", description="Delete an application form")
    @app_commands.describe(form_name="The form to delete")
    @app_commands.autocomplete(form_name=form_name_autocomplete)
    @is_admin()
    async def delete(self, interaction: discord.Interaction, form_name: str):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        forms = cfg.get("application_forms", [])
        new_forms = [f for f in forms if f["name"].lower() != form_name.lower()]
        if len(new_forms) == len(forms):
            await interaction.followup.send(embed=error_embed("Not Found", f"No form named **{form_name}** exists."), ephemeral=True)
            return
        await update_guild_config(interaction.guild_id, {"application_forms": new_forms})
        await interaction.followup.send(embed=success_embed("Form Deleted", f"Deleted **{form_name}**."), ephemeral=True)

    # ── List ───────────────────────────────────────────────────────────────────

    @applications_group.command(name="list", description="View all configured application forms")
    @is_admin()
    async def list_forms(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        forms = cfg.get("application_forms", [])

        if not forms:
            await interaction.followup.send(embed=info_embed("No Forms", "No application forms configured. Use `/applications create` to get started."), ephemeral=True)
            return

        embed = primary_embed(
            f"📋 Application Forms — {interaction.guild.name}",
            f"**{len(forms)}** form(s) configured",
        )
        for form in forms:
            questions = form.get("questions", [])
            status = "🟢 Open" if form.get("open", True) else "🔴 Closed"
            cooldown = f"⏱ {form.get('cooldown_minutes', 0)}m cooldown" if form.get("cooldown_minutes", 0) > 0 else ""
            review_ch = interaction.guild.get_channel(form.get("review_channel_id"))
            val_parts = [
                f"{status}",
                f"**Questions:** {len(questions)}",
            ]
            if cooldown:
                val_parts.append(cooldown)
            if review_ch:
                val_parts.append(f"**Review:** {review_ch.mention}")
            if questions:
                val_parts.append("**Questions:**\n" + "\n".join(f"`{i+1}.` {q}" for i, q in enumerate(questions)))
            embed.add_field(
                name=f"{form.get('emoji','📋')} {form['name']}",
                value="\n".join(val_parts),
                inline=False,
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── Questions ──────────────────────────────────────────────────────────────

    @applications_group.command(name="questions", description="View and manage questions for a specific form")
    @app_commands.describe(form_name="The form to inspect")
    @app_commands.autocomplete(form_name=form_name_autocomplete)
    @is_admin()
    async def questions(self, interaction: discord.Interaction, form_name: str):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        forms = cfg.get("application_forms", [])
        form = next((f for f in forms if f["name"].lower() == form_name.lower()), None)
        if not form:
            await interaction.followup.send(embed=error_embed("Not Found", f"No form named **{form_name}**."), ephemeral=True)
            return

        qs = form.get("questions", [])
        embed = info_embed(
            f"📋 {form['name']} — Questions ({len(qs)}/5)",
            f"Status: {'🟢 Open' if form.get('open', True) else '🔴 Closed'}",
        )
        if qs:
            for i, q in enumerate(qs):
                embed.add_field(name=f"Question {i+1}", value=q, inline=False)
        else:
            embed.description += "\n\n*No questions set. Use `/applications edit` to add questions.*"
        embed.set_footer(text="Use /applications edit to modify questions • Max 5 questions per form")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── Open / Close ───────────────────────────────────────────────────────────

    @applications_group.command(name="open", description="Open applications for a form")
    @app_commands.describe(form_name="The form to open")
    @app_commands.autocomplete(form_name=form_name_autocomplete)
    @is_admin()
    async def open_form(self, interaction: discord.Interaction, form_name: str):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        forms = cfg.get("application_forms", [])
        form = next((f for f in forms if f["name"].lower() == form_name.lower()), None)
        if not form:
            await interaction.followup.send(embed=error_embed("Not Found", f"No form named **{form_name}**."), ephemeral=True)
            return
        form["open"] = True
        await update_guild_config(interaction.guild_id, {"application_forms": forms})
        await interaction.followup.send(embed=success_embed("Applications Opened", f"**{form['name']}** is now 🟢 open."), ephemeral=True)

    @applications_group.command(name="close", description="Close applications for a form")
    @app_commands.describe(form_name="The form to close")
    @app_commands.autocomplete(form_name=form_name_autocomplete)
    @is_admin()
    async def close_form(self, interaction: discord.Interaction, form_name: str):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        forms = cfg.get("application_forms", [])
        form = next((f for f in forms if f["name"].lower() == form_name.lower()), None)
        if not form:
            await interaction.followup.send(embed=error_embed("Not Found", f"No form named **{form_name}**."), ephemeral=True)
            return
        form["open"] = False
        await update_guild_config(interaction.guild_id, {"application_forms": forms})
        await interaction.followup.send(embed=success_embed("Applications Closed", f"**{form['name']}** is now 🔴 closed."), ephemeral=True)

    # ── Panel ──────────────────────────────────────────────────────────────────

    @applications_group.command(name="panel", description="Send an application panel to a channel")
    @app_commands.describe(channel="Channel to send the panel to (defaults to current channel)")
    @is_admin()
    async def panel(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        forms = cfg.get("application_forms", [])
        if not forms:
            await interaction.followup.send(embed=error_embed("No Forms", "Create at least one form with `/applications create` first."), ephemeral=True)
            return

        open_forms = [f for f in forms if f.get("open", True)]
        if not open_forms:
            await interaction.followup.send(embed=warning_embed("All Forms Closed", "All forms are currently closed. Open at least one with `/applications open`."), ephemeral=True)
            return

        panel_data = cfg.get("application_panel", {})
        embed = build_panel_embed(panel_data or {
            "title": "📋 Applications",
            "description": "Select an application below to submit your answers.",
            "color": 0x5865F2,
            "footer_text": f"{interaction.guild.name} • Applications",
        })
        style = panel_data.get("panel_style", "buttons")
        view = ApplicationDropdownPanelView(open_forms) if style == "dropdown" else ApplicationPanelView(open_forms)

        target = channel or interaction.channel
        await target.send(embed=embed, view=view)
        await interaction.followup.send(embed=success_embed("Panel Sent", f"Application panel sent to {target.mention}."), ephemeral=True)

    # ── Customize ──────────────────────────────────────────────────────────────

    @applications_group.command(name="customize", description="Open the interactive application panel customizer")
    @is_admin()
    async def customize(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        panel_data = dict(cfg.get("application_panel", {}))
        if "forms" not in panel_data:
            panel_data["forms"] = [
                {"name": f["name"], "emoji": f.get("emoji", "📋"), "description": f.get("description", ""), "questions": f.get("questions", []), "open": f.get("open", True)}
                for f in cfg.get("application_forms", [])
            ]

        view = AppPanelCustomizerView(interaction.user.id, panel_data)
        embed = primary_embed("📋 Application Panel Customizer", view._summary())
        embed.set_footer(text="🟢 Open  🔴 Closed • Use Preview to see the final result")
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    # ── Approve / Deny ─────────────────────────────────────────────────────────

    @applications_group.command(name="approve", description="Approve a pending application by ID")
    @app_commands.describe(application_id="Application ID number", reason="Reason for approval")
    @is_application_reviewer()
    async def approve(self, interaction: discord.Interaction, application_id: int, reason: str = None):
        await interaction.response.defer(ephemeral=True)
        app_doc = await Database.db.applications.find_one({"guild_id": interaction.guild_id, "app_id": application_id, "status": "pending"})
        if not app_doc:
            await interaction.followup.send(embed=error_embed("Not Found", f"No pending application `#{application_id}` found."), ephemeral=True)
            return

        await Database.db.applications.update_one(
            {"_id": app_doc["_id"]},
            {"$set": {"status": "accepted", "reviewed_by": interaction.user.id, "review_reason": reason, "reviewed_at": datetime.datetime.utcnow()}},
        )

        cfg = await get_guild_config(interaction.guild_id)
        applicant = interaction.guild.get_member(app_doc["user_id"])
        accept_role_id = cfg.get("application_accept_role_id")
        for f in cfg.get("application_forms", []):
            if f["name"] == app_doc.get("form_name") and f.get("accept_role_id"):
                accept_role_id = f["accept_role_id"]
                break

        if accept_role_id and applicant:
            role = interaction.guild.get_role(accept_role_id)
            if role:
                try:
                    await applicant.add_roles(role, reason="Application accepted")
                except discord.Forbidden:
                    pass

        if applicant:
            try:
                await applicant.send(embed=success_embed(
                    "Application Accepted! 🎉",
                    f"Your **{app_doc.get('form_name', 'application')}** application (`#{application_id}`) was **accepted**!\n**Reason:** {reason or 'No reason provided'}",
                ))
            except discord.Forbidden:
                pass

        log_channel_id = cfg.get("application_log_channel_id")
        if log_channel_id:
            log_ch = interaction.guild.get_channel(log_channel_id)
            if log_ch:
                await log_ch.send(embed=success_embed(
                    "Application Approved",
                    f"**Applicant:** <@{app_doc['user_id']}>\n**Form:** {app_doc.get('form_name')}\n**ID:** #{application_id}\n**By:** {interaction.user.mention}\n**Reason:** {reason or 'None'}",
                ))

        if app_doc.get("message_id") and app_doc.get("review_channel_id"):
            try:
                ch = interaction.guild.get_channel(app_doc["review_channel_id"])
                if ch:
                    msg = await ch.fetch_message(app_doc["message_id"])
                    embed = msg.embeds[0] if msg.embeds else discord.Embed()
                    embed.color = 0x2ECC71
                    embed.title = f"✅ ACCEPTED — {embed.title}"
                    await msg.edit(embed=embed, view=None)
            except Exception:
                pass

        await interaction.followup.send(embed=success_embed("Approved", f"Application `#{application_id}` has been approved."), ephemeral=True)

    @applications_group.command(name="deny", description="Deny a pending application by ID")
    @app_commands.describe(application_id="Application ID number", reason="Reason for denial")
    @is_application_reviewer()
    async def deny(self, interaction: discord.Interaction, application_id: int, reason: str = None):
        await interaction.response.defer(ephemeral=True)
        app_doc = await Database.db.applications.find_one({"guild_id": interaction.guild_id, "app_id": application_id, "status": "pending"})
        if not app_doc:
            await interaction.followup.send(embed=error_embed("Not Found", f"No pending application `#{application_id}` found."), ephemeral=True)
            return

        await Database.db.applications.update_one(
            {"_id": app_doc["_id"]},
            {"$set": {"status": "denied", "reviewed_by": interaction.user.id, "review_reason": reason, "reviewed_at": datetime.datetime.utcnow()}},
        )

        cfg = await get_guild_config(interaction.guild_id)
        applicant = interaction.guild.get_member(app_doc["user_id"])
        if applicant:
            try:
                await applicant.send(embed=error_embed(
                    "Application Denied",
                    f"Your **{app_doc.get('form_name', 'application')}** application (`#{application_id}`) was **denied**.\n**Reason:** {reason or 'No reason provided'}",
                ))
            except discord.Forbidden:
                pass

        log_channel_id = cfg.get("application_log_channel_id")
        if log_channel_id:
            log_ch = interaction.guild.get_channel(log_channel_id)
            if log_ch:
                await log_ch.send(embed=error_embed(
                    "Application Denied",
                    f"**Applicant:** <@{app_doc['user_id']}>\n**Form:** {app_doc.get('form_name')}\n**ID:** #{application_id}\n**By:** {interaction.user.mention}\n**Reason:** {reason or 'None'}",
                ))

        if app_doc.get("message_id") and app_doc.get("review_channel_id"):
            try:
                ch = interaction.guild.get_channel(app_doc["review_channel_id"])
                if ch:
                    msg = await ch.fetch_message(app_doc["message_id"])
                    embed = msg.embeds[0] if msg.embeds else discord.Embed()
                    embed.color = 0xE74C3C
                    embed.title = f"❌ DENIED — {embed.title}"
                    await msg.edit(embed=embed, view=None)
            except Exception:
                pass

        await interaction.followup.send(embed=success_embed("Denied", f"Application `#{application_id}` has been denied."), ephemeral=True)

    # ── View / Stats ───────────────────────────────────────────────────────────

    @applications_group.command(name="stats", description="View detailed application statistics for this server")
    @is_admin()
    async def stats(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        forms = cfg.get("application_forms", [])

        total = await Database.db.applications.count_documents({"guild_id": interaction.guild_id})
        pending = await Database.db.applications.count_documents({"guild_id": interaction.guild_id, "status": "pending"})
        accepted = await Database.db.applications.count_documents({"guild_id": interaction.guild_id, "status": "accepted"})
        denied = await Database.db.applications.count_documents({"guild_id": interaction.guild_id, "status": "denied"})
        on_hold = await Database.db.applications.count_documents({"guild_id": interaction.guild_id, "status": "on_hold"})

        embed = primary_embed(
            f"📊 Application Statistics — {interaction.guild.name}",
            f"**Total applications:** {total:,}",
        )

        if total > 0:
            embed.add_field(
                name="Overview",
                value=(
                    f"`{_bar(pending, total)}` ⏳ Pending — **{pending}** ({pending/total*100:.1f}%)\n"
                    f"`{_bar(accepted, total)}` ✅ Accepted — **{accepted}** ({accepted/total*100:.1f}%)\n"
                    f"`{_bar(denied, total)}` ❌ Denied — **{denied}** ({denied/total*100:.1f}%)\n"
                    f"`{_bar(on_hold, total)}` ⏸️ On Hold — **{on_hold}** ({on_hold/total*100:.1f}%)"
                ),
                inline=False,
            )

        if forms:
            per_form_lines = []
            for form in forms:
                form_total = await Database.db.applications.count_documents({"guild_id": interaction.guild_id, "form_name": form["name"]})
                form_pending = await Database.db.applications.count_documents({"guild_id": interaction.guild_id, "form_name": form["name"], "status": "pending"})
                status_icon = "🟢" if form.get("open", True) else "🔴"
                per_form_lines.append(f"{status_icon} {form.get('emoji','📋')} **{form['name']}** — {form_total} total ({form_pending} pending)")
            embed.add_field(name="Per Form", value="\n".join(per_form_lines) or "No data", inline=False)

        last_app = await Database.db.applications.find_one({"guild_id": interaction.guild_id}, sort=[("created_at", -1)])
        if last_app and last_app.get("created_at"):
            embed.add_field(
                name="Last Submission",
                value=f"**{last_app.get('form_name', '?')}** by <@{last_app['user_id']}> — {discord.utils.format_dt(last_app['created_at'], 'R')}",
                inline=False,
            )

        embed.set_footer(text=f"{len(forms)} form(s) configured")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── History ────────────────────────────────────────────────────────────────

    @applications_group.command(name="history", description="View application history for a member")
    @app_commands.describe(member="Member to check (defaults to yourself)", form_name="Filter by form name")
    @app_commands.autocomplete(form_name=form_name_autocomplete)
    async def history(self, interaction: discord.Interaction, member: discord.Member = None, form_name: str = None):
        await interaction.response.defer(ephemeral=True)
        target = member or interaction.user

        is_self = target.id == interaction.user.id
        if not is_self and not interaction.user.guild_permissions.administrator:
            cfg = await get_guild_config(interaction.guild_id)
            reviewer_roles = cfg.get("application_reviewer_roles", [])
            if not any(r.id in reviewer_roles for r in interaction.user.roles):
                await interaction.followup.send(embed=error_embed("No Permission", "You can only view your own application history."), ephemeral=True)
                return

        query = {"guild_id": interaction.guild_id, "user_id": target.id}
        if form_name:
            query["form_name"] = {"$regex": form_name, "$options": "i"}

        apps = await Database.db.applications.find(query).sort("created_at", -1).limit(15).to_list(15)
        total_count = await Database.db.applications.count_documents(query)

        status_icons = {"pending": "⏳", "accepted": "✅", "denied": "❌", "on_hold": "⏸️"}

        embed = primary_embed(
            f"📋 Application History — {target.display_name}",
            f"**{total_count}** application(s) total{f' for *{form_name}*' if form_name else ''}",
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        if not apps:
            embed.description = f"**{target.display_name}** has not submitted any applications yet."
        else:
            for app in apps:
                icon = status_icons.get(app.get("status", "pending"), "❓")
                ts = discord.utils.format_dt(app["created_at"], "R") if app.get("created_at") else "Unknown"
                reviewer_text = ""
                if app.get("reviewed_by"):
                    reviewer_text = f"\n👤 Reviewed by <@{app['reviewed_by']}>"
                    if app.get("review_reason"):
                        reviewer_text += f"\n💬 {app['review_reason'][:80]}"
                embed.add_field(
                    name=f"{icon} #{app.get('app_id','?')} — {app.get('form_name','?')}",
                    value=f"📅 {ts}{reviewer_text}",
                    inline=False,
                )

        if total_count > 15:
            embed.set_footer(text=f"Showing latest 15 of {total_count} applications")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── Search ─────────────────────────────────────────────────────────────────

    @applications_group.command(name="search", description="Search pending applications")
    @app_commands.describe(
        form_name="Filter by form",
        status="Filter by status",
        member="Filter by member",
    )
    @app_commands.autocomplete(form_name=form_name_autocomplete)
    @app_commands.choices(status=[
        app_commands.Choice(name="Pending", value="pending"),
        app_commands.Choice(name="Accepted", value="accepted"),
        app_commands.Choice(name="Denied", value="denied"),
        app_commands.Choice(name="On Hold", value="on_hold"),
    ])
    @is_application_reviewer()
    async def search(
        self,
        interaction: discord.Interaction,
        form_name: str = None,
        status: str = "pending",
        member: discord.Member = None,
    ):
        await interaction.response.defer(ephemeral=True)
        query = {"guild_id": interaction.guild_id, "status": status}
        if form_name:
            query["form_name"] = {"$regex": form_name, "$options": "i"}
        if member:
            query["user_id"] = member.id

        apps = await Database.db.applications.find(query).sort("created_at", -1).limit(10).to_list(10)
        total = await Database.db.applications.count_documents(query)

        status_labels = {"pending": "⏳ Pending", "accepted": "✅ Accepted", "denied": "❌ Denied", "on_hold": "⏸️ On Hold"}
        embed = primary_embed(
            f"🔍 Application Search — {status_labels.get(status, status)}",
            f"**{total}** result(s) found",
        )
        if not apps:
            embed.description = "No applications match your search criteria."
        else:
            for app in apps:
                ts = discord.utils.format_dt(app["created_at"], "R") if app.get("created_at") else "?"
                embed.add_field(
                    name=f"#{app.get('app_id','?')} — {app.get('form_name','?')}",
                    value=f"👤 <@{app['user_id']}>\n📅 {ts}",
                    inline=True,
                )
        if total > 10:
            embed.set_footer(text=f"Showing 10 of {total} results")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── Resend Review ──────────────────────────────────────────────────────────

    @applications_group.command(name="resend", description="Resend a specific application to the review channel")
    @app_commands.describe(application_id="Application ID to resend", channel="Channel to send it to (optional)")
    @is_application_reviewer()
    async def resend(self, interaction: discord.Interaction, application_id: int, channel: discord.TextChannel = None):
        await interaction.response.defer(ephemeral=True)
        app_doc = await Database.db.applications.find_one({"guild_id": interaction.guild_id, "app_id": application_id})
        if not app_doc:
            await interaction.followup.send(embed=error_embed("Not Found", f"Application `#{application_id}` not found."), ephemeral=True)
            return

        cfg = await get_guild_config(interaction.guild_id)
        target_ch = channel
        if not target_ch:
            form = next((f for f in cfg.get("application_forms", []) if f["name"] == app_doc.get("form_name")), {})
            ch_id = form.get("review_channel_id") or cfg.get("application_review_channel_id")
            target_ch = interaction.guild.get_channel(ch_id) if ch_id else interaction.channel

        applicant = interaction.guild.get_member(app_doc["user_id"])
        applicant_name = applicant.mention if applicant else f"<@{app_doc['user_id']}>"

        embed = primary_embed(
            f"📋 {app_doc.get('form_name')} Application #{application_id}",
            f"**Applicant:** {applicant_name} (`{app_doc['user_id']}`)",
        )
        if applicant:
            embed.set_thumbnail(url=applicant.display_avatar.url)
        for question, answer in app_doc.get("answers", {}).items():
            embed.add_field(name=f"❓ {question}", value=answer[:1024] or "No answer", inline=False)
        embed.add_field(name="Status", value=app_doc.get("status", "pending").title(), inline=True)
        if app_doc.get("created_at"):
            embed.add_field(name="Submitted", value=discord.utils.format_dt(app_doc["created_at"], "R"), inline=True)
        embed.set_footer(text=f"Application ID: #{application_id}")

        from bson import ObjectId
        view = ApplicationReviewView(str(app_doc["_id"]), app_doc["user_id"], application_id, app_doc.get("form_name", ""))
        msg = await target_ch.send(embed=embed, view=view)
        await Database.db.applications.update_one(
            {"_id": app_doc["_id"]},
            {"$set": {"message_id": msg.id, "review_channel_id": target_ch.id}},
        )
        await interaction.followup.send(embed=success_embed("Resent", f"Application `#{application_id}` resent to {target_ch.mention}."), ephemeral=True)

    # ── Reviewer Roles ─────────────────────────────────────────────────────────

    @applications_group.command(name="reviewers", description="Manage application reviewer roles")
    @app_commands.describe(
        action="Add or remove a reviewer role",
        role="The role to add or remove",
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Add", value="add"),
        app_commands.Choice(name="Remove", value="remove"),
        app_commands.Choice(name="List", value="list"),
    ])
    @is_admin()
    async def reviewers(self, interaction: discord.Interaction, action: str, role: discord.Role = None):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        reviewer_roles = cfg.get("application_reviewer_roles", [])

        if action == "list":
            roles = [interaction.guild.get_role(r) for r in reviewer_roles]
            embed = info_embed("👥 Application Reviewer Roles", ", ".join(r.mention for r in roles if r) or "None configured")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if not role:
            await interaction.followup.send(embed=error_embed("Missing Role", "Please provide a role."), ephemeral=True)
            return

        if action == "add":
            if role.id in reviewer_roles:
                await interaction.followup.send(embed=warning_embed("Already Added", f"{role.mention} is already a reviewer role."), ephemeral=True)
                return
            reviewer_roles.append(role.id)
            await update_guild_config(interaction.guild_id, {"application_reviewer_roles": reviewer_roles})
            await interaction.followup.send(embed=success_embed("Reviewer Added", f"{role.mention} can now review applications."), ephemeral=True)

        elif action == "remove":
            if role.id not in reviewer_roles:
                await interaction.followup.send(embed=error_embed("Not Found", f"{role.mention} is not a reviewer role."), ephemeral=True)
                return
            reviewer_roles.remove(role.id)
            await update_guild_config(interaction.guild_id, {"application_reviewer_roles": reviewer_roles})
            await interaction.followup.send(embed=success_embed("Reviewer Removed", f"{role.mention} removed from reviewers."), ephemeral=True)

    # ── Cooldown ───────────────────────────────────────────────────────────────

    @applications_group.command(name="cooldown", description="Set the submission cooldown for a form")
    @app_commands.describe(form_name="The form to configure", minutes="Cooldown in minutes (0 to disable)")
    @app_commands.autocomplete(form_name=form_name_autocomplete)
    @is_admin()
    async def cooldown(self, interaction: discord.Interaction, form_name: str, minutes: int):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        forms = cfg.get("application_forms", [])
        form = next((f for f in forms if f["name"].lower() == form_name.lower()), None)
        if not form:
            await interaction.followup.send(embed=error_embed("Not Found", f"No form named **{form_name}**."), ephemeral=True)
            return
        form["cooldown_minutes"] = max(0, minutes)
        await update_guild_config(interaction.guild_id, {"application_forms": forms})
        if minutes <= 0:
            await interaction.followup.send(embed=success_embed("Cooldown Disabled", f"No cooldown on **{form_name}**."), ephemeral=True)
        else:
            await interaction.followup.send(embed=success_embed("Cooldown Set", f"**{form_name}** now has a **{minutes}-minute** resubmission cooldown."), ephemeral=True)

    # ── Reset ──────────────────────────────────────────────────────────────────

    @applications_group.command(name="reset", description="Reset the entire application system configuration")
    @is_admin()
    async def reset(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await update_guild_config(interaction.guild_id, {
            "application_forms": [],
            "application_panel": {},
            "application_review_channel_id": None,
            "application_reviewer_roles": [],
            "application_accept_role_id": None,
            "application_log_channel_id": None,
        })
        await interaction.followup.send(
            embed=success_embed("Application System Reset", "All application forms, settings, and panel configuration have been cleared.\nSubmitted applications remain in the database."),
            ephemeral=True,
        )

    # ── Persistent view registration ───────────────────────────────────────────

    @commands.Cog.listener()
    async def on_ready(self):
        cfg_cursor = Database.db.guilds.find({})
        async for guild_cfg in cfg_cursor:
            forms = guild_cfg.get("application_forms", [])
            if forms:
                self.bot.add_view(ApplicationPanelView(forms))
                self.bot.add_view(ApplicationDropdownPanelView(forms))
        self.bot.add_view(ApplicationReviewView("000000000000000000000000", 0, 0, ""))


async def setup(bot: commands.Bot):
    await bot.add_cog(Applications(bot))
