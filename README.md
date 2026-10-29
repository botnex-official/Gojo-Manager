<h1 align="center">Gojo Manager Bot</h1>

<p align="center"><img src="./extras/gojo_art.jpg" width="600" /></p>

<p align="center">
  A powerful Telegram <b>group management bot</b> built with <b>Pyrogram</b> &amp; <b>Python</b> — modern, fast and packed with plugins.<br/>
  Developed &amp; maintained by <b>BotNex</b>.
</p>

<p align="center">
  <a href="https://t.me/Gojo_Manager_Bot"><b>🤖 Try the live bot — @Gojo_Manager_Bot</b></a>
</p>

<p align="center"><img src="./extras/original.gif" /></p>

---

## 📣 Official Links

| | |
|---|---|
| 🤖 Bot | [@Gojo_Manager_Bot](https://t.me/Gojo_Manager_Bot) |
| 👤 Owner | [@Sohan_Rajpurohit_1](https://t.me/Sohan_Rajpurohit_1) |
| 🛠 Support Group | [@Purohit_Bots_Support](https://t.me/Purohit_Bots_Support) |
| 📢 Updates Channel | [@Purohit_Bots](https://t.me/Purohit_Bots) |
| 🌐 BotNex Channel | [@botnex_Official](https://t.me/botnex_Official) |
| 💻 GitHub Org | [botnex-official](https://github.com/botnex-official) |

Facing a bug or a problem? Join the [Support Group](https://t.me/Purohit_Bots_Support) and ask — help is quickest there.

---

## ✨ Features

- **Admin tools** — ban / mute / warn system with reasons, kick, pin, purge, promote/demote helpers
- **Federation** — link multiple groups and share bans across them
- **Protection** — anti-spam, anti-raid, anti-flood, captcha for new members, chat blacklist, content locks
- **Greetings** — custom welcome/goodbye messages with buttons and media
- **Filters, Notes & Rules** — auto-replies on keywords, saveable notes, group rules
- **Approvals & Reports** — approve trusted users, member reporting to admins
- **Fun & Utility** — games, AFK, stickers tools, info cards, birthdays
- **Automation** — scheduled messages, watchers, audit logging
- **Import / Export** — export your group settings, and import settings from Rose-format exports
- **Bot staff system** — dev / sudo / whitelist user levels, broadcast-ready PM management

---

## 🚀 Deploy Your Own

You run **your own copy** of the bot with **your own** credentials. You need:

1. A bot token from [@BotFather](https://t.me/BotFather)
2. `API_ID` + `API_HASH` from [my.telegram.org](https://my.telegram.org)
3. A free MongoDB database — [MongoDB Atlas](https://www.mongodb.com/atlas) works great
4. Your Telegram user ID (send `/id` style command to any ID bot, or check with the live bot)

### Option 1 — Heroku (easiest, one click)

[![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/botnex-official/Gojo-Manager)

Heroku will ask you for the values listed in the [Environment Variables](#-environment-variables) table below — fill them with **your own** values, then deploy. After the build finishes, open your app → **Resources** tab → turn the **worker** dyno ON.

### Option 2 — Docker

```bash
git clone https://github.com/botnex-official/Gojo-Manager.git
cd gojo-manager
cp sample_config.env .env   # fill in your own values
docker compose up -d --build
```

### Option 3 — VPS / Local (traditional)

```bash
git clone https://github.com/botnex-official/Gojo-Manager.git
cd gojo-manager
pip3 install -r requirements.txt
```

Create a `.env` file in the project root with your values (see the table below), **or** fill the `Development` class in `Powers/vars.py` directly. Then start the bot:

```bash
python3 -m Powers
```

> Setting the `ENV` variable to anything makes the bot read all values from environment variables / the `.env` file.

---

## 🔑 Environment Variables

| Variable | Required | Description |
|---|---|---|
| `BOT_TOKEN` | ✅ | Your bot token from @BotFather |
| `API_ID` | ✅ | API ID from my.telegram.org |
| `API_HASH` | ✅ | API HASH from my.telegram.org |
| `DB_URI` | ✅ | MongoDB connection string |
| `OWNER_ID` | ✅ | Your Telegram user ID |
| `ENV` | ✅ (Heroku) | Set to anything to enable env-based config |
| `DB_NAME` | — | Database name (default: `gojo_manager`) |
| `BDB_URI` | — | Second MongoDB URI (backup DB) |
| `MESSAGE_DUMP` | — | Chat ID of your log group/channel |
| `SUPPORT_GROUP` | — | Support group username (without @) |
| `SUPPORT_CHANNEL` | — | Updates channel username (without @) |
| `DEV_USERS` / `SUDO_USERS` / `WHITELIST_USERS` | — | Space-separated user IDs |
| `PREFIX_HANDLER` | — | Command prefixes (default: `/`) |
| `GENIUS_API` | — | Genius API token (lyrics) |
| `RMBG_API` | — | remove.bg API key (background remover) |
| `TIME_ZONE` | — | Your time zone (default: `Asia/Kolkata`) |
| `WORKERS` | — | Pyrogram workers (default: 16) |

---

## 🆘 Support

- Support Group: [@Purohit_Bots_Support](https://t.me/Purohit_Bots_Support)
- Updates: [@Purohit_Bots](https://t.me/Purohit_Bots) • [@botnex_Official](https://t.me/botnex_Official)
- Owner: [@Sohan_Rajpurohit_1](https://t.me/Sohan_Rajpurohit_1)
- Issues: [GitHub Issues](https://github.com/botnex-official/Gojo-Manager/issues)

## 📜 License

Licensed under the GNU General Public License v3.0 — see [LICENSE](LICENSE).

---

<p align="center"><b>Powered by <a href="https://github.com/botnex-official">BotNex</a></b> • Bot: <a href="https://t.me/Gojo_Manager_Bot">@Gojo_Manager_Bot</a> • Owner: <a href="https://t.me/Sohan_Rajpurohit_1">@Sohan_Rajpurohit_1</a></p>
