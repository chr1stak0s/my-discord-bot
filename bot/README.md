# ⚡ Professional Discord Bot

A production-ready, feature-rich Discord bot built with **discord.py 2.x**, **MongoDB**, and a **Flask dashboard**.

---

## 🚀 Quick Start

### 1. Prerequisites

- Python 3.11+
- MongoDB (local or [MongoDB Atlas](https://www.mongodb.com/atlas))
- A Discord Bot Token ([Discord Developer Portal](https://discord.com/developers/applications))

### 2. Install Dependencies

```bash
cd bot
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your values:

```env
DISCORD_TOKEN=your_bot_token_here
MONGODB_URI=mongodb://localhost:27017
DATABASE_NAME=discord_bot
```

### 4. Run the Bot

```bash
python main.py
```

### 5. Run the Dashboard (optional, separate process)

```bash
python dashboard/app.py
```

Dashboard will be available at `http://localhost:5000`

---

## 📁 Project Structure

```
bot/
├── cogs/                   # Bot cog extensions
│   ├── admin.py            # /admin commands
│   ├── applications.py     # /applications system
│   ├── automod.py          # /automod — anti-spam, anti-link, etc.
│   ├── economy.py          # /economy — balance, daily, work, etc.
│   ├── embeds.py           # /embeds — interactive embed builder
│   ├── extra.py            # Leveling, giveaways, polls, starboard, AFK,
│   │                       # reaction roles, verification, custom commands
│   ├── logs.py             # /logs — automatic log channel setup
│   ├── moderation.py       # /moderation — ban, kick, warn, etc.
│   ├── tickets.py          # /tickets — full ticket system
│   ├── utility.py          # /utility — userinfo, serverinfo, etc.
│   └── welcome.py          # /welcome — welcome/leave messages
├── views/                  # discord.py UI components
│   ├── applications.py     # Application modals and review buttons
│   ├── confirm.py          # Confirmation dialogs
│   ├── embeds_builder.py   # Interactive embed builder UI
│   ├── giveaway.py         # Giveaway entry button
│   ├── polls.py            # Poll vote buttons
│   └── tickets.py          # Ticket panel, control, and close buttons
├── utils/                  # Utility modules
│   ├── checks.py           # Permission check decorators
│   ├── helpers.py          # Embed helpers, XP math, pagination
│   └── logger.py           # Colored rotating log setup
├── database/
│   ├── __init__.py
│   └── db.py               # MongoDB connection + index setup
├── dashboard/              # Flask web dashboard
│   ├── app.py              # Flask app + OAuth2 + routes
│   ├── templates/          # Jinja2 HTML templates
│   └── static/             # CSS + JS assets
├── main.py                 # Bot entry point
├── config.py               # All configuration from .env
├── requirements.txt        # Python dependencies
└── .env.example            # Environment variable template
```

---

## 🛠️ Commands Reference

### `/admin`
| Command | Description |
|---------|-------------|
| `/admin setup` | Run initial setup wizard |
| `/admin config` | Configure mod/admin roles |
| `/admin view` | View all bot settings |
| `/admin reset` | Reset all server data |
| `/admin reload` | Reload a cog extension (owner only) |

### `/moderation`
| Command | Description |
|---------|-------------|
| `/moderation ban` | Ban a member |
| `/moderation unban` | Unban a user by ID |
| `/moderation kick` | Kick a member |
| `/moderation timeout` | Timeout a member (1min – 28 days) |
| `/moderation mute` | Mute with role (auto-creates Muted role) |
| `/moderation unmute` | Unmute a member |
| `/moderation warn` | Warn a member |
| `/moderation warnings` | View a member's warnings |
| `/moderation clear` | Purge up to 100 messages |
| `/moderation slowmode` | Set channel slowmode |
| `/moderation lock` | Lock a channel |
| `/moderation unlock` | Unlock a channel |
| `/moderation nickname` | Change a member's nickname |

### `/tickets`
| Command | Description |
|---------|-------------|
| `/tickets setup` | Configure ticket system |
| `/tickets panel` | Send ticket panel to a channel |
| `/tickets add` | Add user to ticket |
| `/tickets remove` | Remove user from ticket |
| `/tickets rename` | Rename ticket channel |
| `/tickets claim` | Claim a ticket |
| `/tickets unclaim` | Unclaim a ticket |
| `/tickets close` | Close the current ticket |
| `/tickets delete` | Delete a closed ticket |
| `/tickets transcript` | Export ticket transcript |
| `/tickets view` | View ticket statistics |
| `/tickets reset` | Reset ticket configuration |

**Ticket Features:** Dropdown panel with custom types, claim system, automatic category creation, staff permissions, transcripts, logs.

### `/applications`
| Command | Description |
|---------|-------------|
| `/applications setup` | Configure review channel and roles |
| `/applications create` | Create a new form with questions |
| `/applications edit` | Edit form questions |
| `/applications delete` | Delete a form |
| `/applications panel` | Send application panel |
| `/applications open` | Open applications |
| `/applications close` | Close applications |
| `/applications view` | View statistics |
| `/applications reset` | Reset all application data |

**Application Features:** Up to 5 questions per form, modal submission, reviewer accept/deny with reasons, DM notifications, role on accept, logs.

### `/logs`
| Command | Description |
|---------|-------------|
| `/logs setup` | Create log category + 9 channels |
| `/logs reset` | Remove all log channels |
| `/logs view` | View channel configuration |
| `/logs test` | Send test messages to all log channels |

**Auto-tracked:** joins, leaves, message delete/edit, role changes, nickname changes, bans, unbans, channel create/delete/update, voice activity.

### `/embeds`
| Command | Description |
|---------|-------------|
| `/embeds create` | Open interactive embed builder |
| `/embeds edit` | Edit a saved template |
| `/embeds delete` | Delete a template |
| `/embeds preview` | Preview a template |
| `/embeds save` | Save embed from a message |
| `/embeds template` | Send a template to a channel |

**Features:** Live builder, title/description/color/thumbnail/image/fields/footer/author, JSON export, template save.

### `/welcome`
| Command | Description |
|---------|-------------|
| `/welcome setup` | Configure welcome channel, leave channel, auto-roles |
| `/welcome preview` | Preview welcome/leave message |
| `/welcome view` | View configuration |
| `/welcome reset` | Reset configuration |

### `/automod`
| Command | Description |
|---------|-------------|
| `/automod setup` | Configure all automod rules |
| `/automod view` | View current rules |
| `/automod reset` | Disable all automod |

**Rules:** Anti-spam (5 msgs/5s → timeout), anti-links, anti-invite, anti-mention spam, anti-caps, anti-scam.

### `/utility`
| Command | Description |
|---------|-------------|
| `/utility avatar` | Get user avatar (PNG/JPG/WEBP/GIF) |
| `/utility banner` | Get user banner |
| `/utility userinfo` | Full user information |
| `/utility serverinfo` | Full server information |
| `/utility roleinfo` | Role details + key permissions |
| `/utility membercount` | Total, humans, bots, online |
| `/utility ping` | WebSocket + API latency |
| `/utility uptime` | Bot uptime |
| `/utility botinfo` | Bot stats, servers, users |
| `/utility invite` | Bot invite + support server links |

### `/economy`
| Command | Description |
|---------|-------------|
| `/economy balance` | View wallet + bank + total |
| `/economy daily` | Claim daily reward (streak bonus) |
| `/economy work` | Work for coins (1hr cooldown) |
| `/economy deposit` | Deposit to bank |
| `/economy withdraw` | Withdraw from bank |
| `/economy pay` | Pay another member |
| `/economy leaderboard` | Top 10 richest members |

### Extra Features (Slash Commands)

| Command Group | Commands |
|---------------|----------|
| `/level` | `rank`, `leaderboard`, `setlevel` |
| `/giveaway` | `start`, `end`, `reroll` |
| `/poll` | `create`, `end` |
| `/suggestions` | `setup`, `submit`, `approve`, `deny` |
| `/starboard` | `setup` |
| `/afk` | `set` |
| `/reactionroles` | `add`, `remove` |
| `/verification` | `setup` |
| `/customcmd` | `add`, `remove`, `list` |

---

## 🗄️ Database Collections

| Collection | Purpose |
|-----------|---------|
| `guilds` | Per-server configuration |
| `tickets` | All ticket records |
| `applications` | Application submissions |
| `warnings` | Moderation warnings |
| `moderation` | Ban/kick/mute history |
| `economy` | Wallet, bank, daily/work cooldowns |
| `levels` | XP and level data |
| `embeds` | Saved embed templates |
| `giveaways` | Giveaway data + participants |
| `polls` | Poll questions + votes |
| `suggestions` | Server suggestions |
| `starboard` | Starred messages |
| `afk` | AFK status records |
| `reaction_roles` | Reaction → role mappings |
| `custom_commands` | Custom text commands |

---

## 🖥️ Flask Dashboard

| Page | URL |
|------|-----|
| Landing | `/` |
| Login (Discord OAuth2) | `/login` |
| Server Select | `/dashboard` |
| Server Overview | `/dashboard/<guild_id>` |
| Tickets | `/dashboard/<guild_id>/tickets` |
| Moderation | `/dashboard/<guild_id>/moderation` |
| Applications | `/dashboard/<guild_id>/applications` |
| Logs | `/dashboard/<guild_id>/logs` |
| Embed Builder | `/dashboard/<guild_id>/embeds` |
| Welcome | `/dashboard/<guild_id>/welcome` |
| AutoMod | `/dashboard/<guild_id>/automod` |

**Dashboard API:**
- `GET /api/<guild_id>/stats` — ticket, application, warning counts
- `GET /api/<guild_id>/tickets` — last 50 tickets
- `GET /api/<guild_id>/leaderboard` — top 20 by XP
- `GET/POST /api/<guild_id>/config` — read/write guild settings

---

## ⚙️ Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DISCORD_TOKEN` | ✅ | Bot token from Discord Developer Portal |
| `MONGODB_URI` | ✅ | MongoDB connection string |
| `DATABASE_NAME` | ✅ | Database name (default: `discord_bot`) |
| `FLASK_SECRET_KEY` | Dashboard | Secret key for Flask sessions |
| `DISCORD_CLIENT_ID` | Dashboard | OAuth2 client ID |
| `DISCORD_CLIENT_SECRET` | Dashboard | OAuth2 client secret |
| `DISCORD_REDIRECT_URI` | Dashboard | OAuth2 redirect URI |
| `OWNER_IDS` | Optional | Comma-separated owner user IDs |
| `LOG_LEVEL` | Optional | Logging level (default: `INFO`) |
| `SUPPORT_SERVER` | Optional | Support server invite link |
| `BOT_INVITE` | Optional | Bot invite link |

---

## 🔒 Required Bot Permissions

Enable the following in the Discord Developer Portal:

**Privileged Intents:**
- ✅ Server Members Intent
- ✅ Message Content Intent
- ✅ Presence Intent

**Bot Permissions (use permission integer `8` for Administrator or configure granularly):**
- Manage Roles, Manage Channels, Manage Messages
- Ban Members, Kick Members, Moderate Members
- Send Messages, Embed Links, Attach Files
- Read Message History, Add Reactions
- View Audit Log

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/new-feature`
3. Commit changes: `git commit -m "Add new feature"`
4. Push and open a Pull Request

---

## 📄 License

MIT License — free to use and modify.
