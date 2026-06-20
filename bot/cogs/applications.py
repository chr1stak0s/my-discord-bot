import discord
from discord import app_commands
from discord.ext import commands
import logging
from database import Database, get_guild_config, update_guild_config
from utils import success_embed, error_embed, info_embed, primary_embed, is_admin, is_application_reviewer
from views.applications import ApplicationPanelView, ApplicationReviewView

logger = logging.getLogger(__name__)


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
        modal = FormQuestionModal(name)
        await interaction.response.send_modal(modal)
        await modal.wait()
        questions = [q for q in modal.questions if q]
        if not questions:
            return
        forms.append({"name": name, "description": description, "questions": questions, "emoji": "📋"})
        await update_guild_config(interaction.guild_id, {"application_forms": forms})
        embed = success_embed("Form Created", f"Application form **{name}** created with {len(questions)} questions.")
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
        modal = FormQuestionModal(name)
        await interaction.response.send_modal(modal)
        await modal.wait()
        questions = [q for q in modal.questions if q]
        if not questions:
            return
        for f in forms:
            if f["name"].lower() == name.lower():
                f["questions"] = questions
                break
        await update_guild_config(interaction.guild_id, {"application_forms": forms})
        await interaction.followup.send(embed=success_embed("Form Updated", f"Form **{name}** updated with {len(questions)} questions."), ephemeral=True)

    @app_group.command(name="panel", description="Send an application panel to a channel")
    app_commands.describe(channel="Channel to send the panel to")
    @is_admin()
    async def panel(self, interaction:
        await interaction.response.defer(ephemeral=True)
        cfg = await get_guild_config(interaction.guild_id)
        forms = cfg.get("application_forms", [])
        if not forms:
            await interaction.followup.send(embed=error_embed("No Forms", "Create application forms first with `/applications create`."), ephemeral=True)
            return
        embed = primary_embed(title, "Select an application below to submit your application.")
        embed.set_footer(text=f"{interaction.guild.name} • Applications")
        view = ApplicationPanelView(forms)
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
        from utils.helpers import primary_embed as _primary
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
        embed = _primary("📋 Application Panel Customizer", "\n".join(lines))
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


class FormQuestionModal(discord.ui.Modal, title="Application Form Questions"):
    q1 = discord.ui.TextInput(label="Question 1", max_length=256, required=True)
    q2 = discord.ui.TextInput(label="Question 2", max_length=256, required=False)
    q3 = discord.ui.TextInput(label="Question 3", max_length=256, required=False)
    q4 = discord.ui.TextInput(label="Question 4", max_length=256, required=False)
    q5 = discord.ui.TextInput(label="Question 5", max_length=256, required=False)

    def __init__(self, form_name: str):
        super().__init__(title=f"Questions for '{form_name[:30]}'")
        self.questions = []

    async def on_submit(self, interaction: discord.Interaction):
        self.questions = [
            self.q1.value,
            self.q2.value,
            self.q3.value,
            self.q4.value,
            self.q5.value,
        ]
        await interaction.response.defer()
        self.stop()


async def setup(bot: commands.Bot):
    await bot.add_cog(Applications(bot))
