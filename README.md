<div align="center">

# ☁️ CF Control

**Manage all your Cloudflare accounts from inside Telegram.**
مدیریت کامل حساب‌های کلودفلر، بدون ورود به سایت.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![Ubuntu](https://img.shields.io/badge/Ubuntu-22.04-E95420?logo=ubuntu&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![Telegram](https://img.shields.io/badge/Bot%20API-latest-26A5E4?logo=telegram&logoColor=white)

Developed by **DenTeeR**

</div>

---

## ✨ Features

- 🔑 Multiple Cloudflare accounts (API tokens), switch instantly
- 📡 DNS: readable list with full names, **add / edit / delete**, proxy toggle, TTL
- 🔒 SSL mode · 🛡 Security level · ⚡ Quick toggles (Always HTTPS, IPv6, Brotli, HTTP/3)
- 🔥 One-tap **Under Attack** mode, dev mode, cache purge
- ⛔ Firewall: block / allow / challenge by IP, CIDR or country
- 👥 Multi-admin: the owner can add/remove admins from Settings
- 📶 Connection check for every saved Cloudflare account
- 🗑 Delete a domain (confirmed by typing its name)
- 📤 DNS export (backup file sent in chat)
- 🎨 **Design mode**: per-button and per-text **color** + **emoji** (premium or normal), all from inside the bot
- 🌍 Persian & English · persistent bottom menu · colored buttons (latest Bot API)
- 🔐 Admin-only access, token message auto-deleted, runs as an unprivileged service user

## 🚀 Install (Ubuntu / Debian)

```bash
curl -fsSL https://raw.githubusercontent.com/DenTeeR/CFManagement/main/install.sh | sudo bash
```

The installer asks for your **bot token** ([@BotFather](https://t.me/BotFather)) and **admin ID** ([@userinfobot](https://t.me/userinfobot)), then sets up everything (Python venv, systemd service, `cfbot` manager).

Non-interactive:

```bash
curl -fsSL https://raw.githubusercontent.com/DenTeeR/CFManagement/main/install.sh \
  | sudo BOT_TOKEN="123:ABC" ADMIN_IDS="111,222" bash
```

> Forked the repo? Run with `CFBOT_REPO="youruser/cf-control"` or edit `REPO=` at the top of `install.sh`.

## 🧰 Manager

After install, just run:

```bash
sudo cfbot            # interactive menu
sudo cfbot update     # update to latest version (data is kept)
sudo cfbot logs -f    # live logs
sudo cfbot config     # change token / admins
sudo cfbot uninstall
```

## ☁️ Cloudflare API token

Cloudflare → *My Profile → API Tokens → Create Custom Token* with:

| Permission | Level |
|---|---|
| Zone → Zone | Read + Edit (Edit is needed to delete a domain) |
| Zone → DNS | Edit |
| Zone → Zone Settings | Edit |
| Zone → Cache Purge | Purge |
| Zone → Firewall Services | Edit |

Zone Resources: *Include → All zones*. Then in the bot: **➕ Add account** and send the token.

## 🎨 Premium emoji & colors

1. Bot → **Settings → Design mode** → ON.
2. Under every screen tap **🎨 Customize this screen**, pick any button/text, choose a color and send any emoji.
3. Premium emoji on buttons/text require Telegram's condition: the bot **owner has Telegram Premium** *or* the bot owns an extra **Fragment username**. Otherwise normal emoji are shown.

---

## 🇮🇷 راهنمای فارسی

**نصب:** دستور بالا را روی سرور اجرا کنید؛ اسکریپت توکن ربات و آیدی عددی ادمین را می‌پرسد و همه‌چیز (سرویس، محیط پایتون، منوی مدیریت) را خودش راه می‌اندازد.

**مدیریت:** فقط بنویسید `sudo cfbot` تا منوی وضعیت، لاگ، ری‌استارت، آپدیت، تغییر توکن و حذف باز شود.

**توکن کلودفلر:** دسترسی‌های جدول بالا را بدهید و در ربات روی «افزودن حساب» بزنید.

**ایموجی پرمیوم و رنگ دکمه‌ها:** از *تنظیمات ← حالت طراحی* هر دکمه یا متن را جدا شخصی‌سازی کنید.

## 📁 Structure

```
CFManagement/
├── install.sh   # installer + manager (DenTeeR UI)
├── cfbot.py     # the bot (single file)
├── README.md
├── LICENSE
└── .gitignore
```

## 📜 License

MIT © DenTeeR
