"""
Flask Dashboard — Discord OAuth2 Login + Server Management
Run separately from the bot: python dashboard/app.py
"""
import os
import sys
import json
import datetime
import requests
from functools import wraps

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import (
    Flask, render_template, redirect, url_for,
    session, request, jsonify, abort, flash
)
from dotenv import load_dotenv

load_dotenv()

from config import config

app = Flask(__name__)
app.secret_key = config.FLASK_SECRET_KEY
app.config["SESSION_COOKIE_SECURE"] = False  # Set True in production with HTTPS
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = datetime.timedelta(hours=24)

DISCORD_API = "https://discord.com/api/v10"
DISCORD_OAUTH_URL = (
    f"https://discord.com/api/oauth2/authorize"
    f"?client_id={config.DISCORD_CLIENT_ID}"
    f"&redirect_uri={requests.utils.quote(config.DISCORD_REDIRECT_URI, safe='')}"
    f"&response_type=code"
    f"&scope=identify+guilds"
)


def get_discord_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def get_bot_headers() -> dict:
    return {"Authorization": f"Bot {config.TOKEN}", "Content-Type": "application/json"}


def fetch_user(token: str) -> dict | None:
    r = requests.get(f"{DISCORD_API}/users/@me", headers=get_discord_headers(token))
    return r.json() if r.ok else None


def fetch_user_guilds(token: str) -> list:
    r = requests.get(f"{DISCORD_API}/users/@me/guilds", headers=get_discord_headers(token))
    return r.json() if r.ok else []


def fetch_bot_guilds() -> list:
    r = requests.get(f"{DISCORD_API}/users/@me/guilds", headers=get_bot_headers())
    return r.json() if r.ok else []


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def get_manageable_guilds():
    user_guilds = fetch_user_guilds(session["access_token"])
    bot_guilds = fetch_bot_guilds()
    bot_guild_ids = {g["id"] for g in bot_guilds}
    MANAGE_GUILD = 0x20
    return [
        g for g in user_guilds
        if (int(g.get("permissions", 0)) & MANAGE_GUILD) and g["id"] in bot_guild_ids
    ]


# ─── Auth Routes ──────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if "user" in session:
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/login")
def login():
    return redirect(DISCORD_OAUTH_URL)


@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        flash("Authentication failed — no code received.", "error")
        return redirect(url_for("index"))

    data = {
        "client_id": config.DISCORD_CLIENT_ID,
        "client_secret": config.DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": config.DISCORD_REDIRECT_URI,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    r = requests.post(f"{DISCORD_API}/oauth2/token", data=data, headers=headers)

    if not r.ok:
        flash("Failed to exchange code for token.", "error")
        return redirect(url_for("index"))

    token_data = r.json()
    access_token = token_data.get("access_token")
    user = fetch_user(access_token)

    if not user:
        flash("Failed to fetch user data.", "error")
        return redirect(url_for("index"))

    session.permanent = True
    session["access_token"] = access_token
    session["user"] = user
    return redirect(url_for("dashboard"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# ─── Dashboard ────────────────────────────────────────────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
    guilds = get_manageable_guilds()
    return render_template("dashboard.html", user=session["user"], guilds=guilds)


@app.route("/dashboard/<guild_id>")
@login_required
def guild_dashboard(guild_id: str):
    guilds = get_manageable_guilds()
    guild = next((g for g in guilds if g["id"] == guild_id), None)
    if not guild:
        abort(403)

    # Fetch full guild info from bot
    r = requests.get(f"{DISCORD_API}/guilds/{guild_id}?with_counts=true", headers=get_bot_headers())
    guild_info = r.json() if r.ok else {}

    return render_template("guild.html", user=session["user"], guild=guild, guild_info=guild_info)


@app.route("/dashboard/<guild_id>/tickets")
@login_required
def tickets_page(guild_id: str):
    guilds = get_manageable_guilds()
    guild = next((g for g in guilds if g["id"] == guild_id), None)
    if not guild:
        abort(403)
    return render_template("tickets.html", user=session["user"], guild=guild)


@app.route("/dashboard/<guild_id>/moderation")
@login_required
def moderation_page(guild_id: str):
    guilds = get_manageable_guilds()
    guild = next((g for g in guilds if g["id"] == guild_id), None)
    if not guild:
        abort(403)
    return render_template("moderation.html", user=session["user"], guild=guild)


@app.route("/dashboard/<guild_id>/welcome")
@login_required
def welcome_page(guild_id: str):
    guilds = get_manageable_guilds()
    guild = next((g for g in guilds if g["id"] == guild_id), None)
    if not guild:
        abort(403)
    return render_template("welcome.html", user=session["user"], guild=guild)


@app.route("/dashboard/<guild_id>/automod")
@login_required
def automod_page(guild_id: str):
    guilds = get_manageable_guilds()
    guild = next((g for g in guilds if g["id"] == guild_id), None)
    if not guild:
        abort(403)
    return render_template("automod.html", user=session["user"], guild=guild)


@app.route("/dashboard/<guild_id>/logs")
@login_required
def logs_page(guild_id: str):
    guilds = get_manageable_guilds()
    guild = next((g for g in guilds if g["id"] == guild_id), None)
    if not guild:
        abort(403)
    return render_template("logs.html", user=session["user"], guild=guild)


@app.route("/dashboard/<guild_id>/embeds")
@login_required
def embeds_page(guild_id: str):
    guilds = get_manageable_guilds()
    guild = next((g for g in guilds if g["id"] == guild_id), None)
    if not guild:
        abort(403)
    return render_template("embeds.html", user=session["user"], guild=guild)


@app.route("/dashboard/<guild_id>/applications")
@login_required
def applications_page(guild_id: str):
    guilds = get_manageable_guilds()
    guild = next((g for g in guilds if g["id"] == guild_id), None)
    if not guild:
        abort(403)
    return render_template("applications.html", user=session["user"], guild=guild)


# ─── API Endpoints (async DB access via motor is not available in sync Flask) ─
# These endpoints proxy data from the MongoDB using pymongo (sync) for dashboard use.

@app.route("/api/<guild_id>/stats")
@login_required
def api_stats(guild_id: str):
    guilds = get_manageable_guilds()
    if not any(g["id"] == guild_id for g in guilds):
        return jsonify({"error": "Forbidden"}), 403

    from pymongo import MongoClient
    client = MongoClient(config.MONGODB_URI)
    db = client[config.DATABASE_NAME]

    gid = int(guild_id)
    stats = {
        "tickets": {"total": db.tickets.count_documents({"guild_id": gid}),
                    "open": db.tickets.count_documents({"guild_id": gid, "status": "open"}),
                    "closed": db.tickets.count_documents({"guild_id": gid, "status": "closed"})},
        "applications": {"total": db.applications.count_documents({"guild_id": gid}),
                         "pending": db.applications.count_documents({"guild_id": gid, "status": "pending"}),
                         "accepted": db.applications.count_documents({"guild_id": gid, "status": "accepted"}),
                         "denied": db.applications.count_documents({"guild_id": gid, "status": "denied"})},
        "warnings": db.warnings.count_documents({"guild_id": gid}),
        "economy_users": db.economy.count_documents({"guild_id": gid}),
        "leveling_users": db.levels.count_documents({"guild_id": gid}),
    }
    client.close()
    return jsonify(stats)


@app.route("/api/<guild_id>/tickets")
@login_required
def api_tickets(guild_id: str):
    guilds = get_manageable_guilds()
    if not any(g["id"] == guild_id for g in guilds):
        return jsonify({"error": "Forbidden"}), 403

    from pymongo import MongoClient
    import bson
    client = MongoClient(config.MONGODB_URI)
    db = client[config.DATABASE_NAME]
    gid = int(guild_id)
    tickets = list(db.tickets.find({"guild_id": gid}, {"_id": 0}).sort("created_at", -1).limit(50))
    for t in tickets:
        if "created_at" in t:
            t["created_at"] = t["created_at"].isoformat()
        if "closed_at" in t and t["closed_at"]:
            t["closed_at"] = t["closed_at"].isoformat()
    client.close()
    return jsonify(tickets)


@app.route("/api/<guild_id>/leaderboard")
@login_required
def api_leaderboard(guild_id: str):
    guilds = get_manageable_guilds()
    if not any(g["id"] == guild_id for g in guilds):
        return jsonify({"error": "Forbidden"}), 403

    from pymongo import MongoClient
    client = MongoClient(config.MONGODB_URI)
    db = client[config.DATABASE_NAME]
    gid = int(guild_id)
    levels = list(db.levels.find({"guild_id": gid}, {"_id": 0}).sort("xp", -1).limit(20))
    client.close()
    return jsonify(levels)


@app.route("/api/<guild_id>/config", methods=["GET", "POST"])
@login_required
def api_config(guild_id: str):
    guilds = get_manageable_guilds()
    if not any(g["id"] == guild_id for g in guilds):
        return jsonify({"error": "Forbidden"}), 403

    from pymongo import MongoClient
    client = MongoClient(config.MONGODB_URI)
    db = client[config.DATABASE_NAME]
    gid = int(guild_id)

    if request.method == "GET":
        cfg = db.guilds.find_one({"guild_id": gid}, {"_id": 0})
        client.close()
        return jsonify(cfg or {})

    if request.method == "POST":
        data = request.get_json()
        allowed_keys = [
            "welcome_message", "leave_message", "dm_welcome",
            "automod_enabled", "automod_anti_spam", "automod_anti_links",
            "automod_anti_invite", "automod_anti_mention_spam", "automod_anti_caps",
            "automod_anti_scam",
        ]
        update = {k: v for k, v in data.items() if k in allowed_keys}
        if update:
            db.guilds.update_one({"guild_id": gid}, {"$set": update}, upsert=True)
        client.close()
        return jsonify({"success": True})


if __name__ == "__main__":
    app.run(
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true",
    )
