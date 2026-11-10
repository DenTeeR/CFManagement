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

**Accounts & zones**
- 🔑 Multiple Cloudflare accounts (API tokens), switch instantly, connection check
- 🌐 Zone list with search · **add a domain** · pause / resume Cloudflare · re-check activation · delete (confirmed by typing the name)

**DNS**
- 📡 Readable list with **search** and **type filter**, add / edit / delete, proxy toggle, TTL
- All record types: `A`, `AAAA`, `CNAME`, `TXT` (spaces kept, long values split), `MX` (priority), `SRV`, `CAA`, …
- 🔁 **Bulk IP replace** in one zone or across every zone of an account, with a preview before anything changes
- 📤 Export and 📥 **import** (BIND file)

**Security & performance**
- 🔒 SSL mode · minimum TLS version · HSTS · DNSSEC (shows the DS record for your registrar)
- 🛡 Security level · one-tap **Under Attack** · dev mode · 15 quick toggles (only those the zone actually offers)
- ⛔ Firewall (IP Access Rules): IP, IPv6, CIDR, **ASN** or country, with paging
- 📐 **WAF custom rules**, **rate limiting**, **redirect rules**, Page Rules, Worker routes
- 🗑 Cache: purge everything or **by URL / prefix / host** · cache level
- 📊 **Analytics**: requests, cached share, bandwidth, visitors, threats, top countries (24 h / 7 d / 30 d)

**Services**
- 👷 Workers (list, delete) · 📄 Pages (projects, deployments, retry) · 🚇 Tunnels (status, connections)

**Team & safety**
- 👥 Roles: owner, full admin, **read-only** admin, and per-admin **allowed accounts**
- 📜 **Activity log**: who changed what, where, and whether it worked
- ⚠️ Destructive actions always ask first; a button on an old message never acts on a different zone or record
- 🔔 **Alerts** when an account stops answering or a zone changes status
- 🔐 Tokens **encrypted on disk**, data readable by the service user only, token message auto-deleted

**Interface**
- 🎨 **Design mode**: per-button and per-text **color** + **emoji** (premium or normal), all from inside the bot
- 🌍 Persian & English · persistent bottom menu · colored buttons (latest Bot API) · `/help`, `/cancel`

## 🚀 Install (Ubuntu / Debian)

```bash
curl -fsSL https://raw.githubusercontent.com/DenTeeR/CFManagement/main/install.sh | sudo bash
```

The installer asks for your **bot token** ([@BotFather](https://t.me/BotFather)) and **admin ID** ([@userinfobot](https://t.me/userinfobot)), then sets up everything (Python venv with pinned dependencies, encryption key, systemd service, `cfbot` manager).

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

`cfbot update` keeps the running version and its data aside; if the new version does not start, both are put back automatically.

### Upgrading from 2.x

Run `sudo cfbot update` **twice**. The first run is done by the old updater and only replaces the bot; the second one (now the new updater) installs the pinned dependencies, tightens the service and creates the encryption key. Buttons on messages sent before the upgrade answer “outdated” — open the screen again from the menu.

## ☁️ Cloudflare API token

Cloudflare → *My Profile → API Tokens → Create Custom Token*. The first five are enough for the core features; add the others for the sections you want to use. A section whose permission is missing simply shows Cloudflare's error.

| Permission | Level | Used for |
|---|---|---|
| Zone → Zone | Read + Edit | zone list, add / pause / delete a domain |
| Zone → DNS | Edit | DNS records, import / export, DNSSEC |
| Zone → Zone Settings | Edit | SSL, security level, toggles, TLS, HSTS, cache level |
| Zone → Cache Purge | Purge | cache purge |
| Zone → Firewall Services | Edit | IP Access Rules |
| Zone → Analytics | Read | analytics |
| Zone → Zone WAF | Edit | WAF custom rules, rate limiting |
| Zone → Dynamic Redirect | Edit | redirect rules |
| Zone → Page Rules | Edit | Page Rules |
| Zone → Workers Routes | Edit | Worker routes |
| Account → Account Settings | Read | add a domain, services |
| Account → Workers Scripts | Edit | Workers |
| Account → Cloudflare Pages | Edit | Pages |
| Account → Cloudflare Tunnel | Read | Tunnels |

Zone Resources: *Include → All zones*. Then in the bot: **➕ Add account** and send the token.

## ✍️ Text formats

| Where | Send | Example |
|---|---|---|
| New DNS record | `TYPE name content` | `A sub 1.2.3.4 1` · `TXT @ v=spf1 include:_spf.google.com ~all` · `MX @ 10 mail.example.com` · `SRV _sip._tcp 10 5 5060 sip.example.com` · `CAA @ 0 issue letsencrypt.org` |
| Bulk IP replace | `old new` | `1.2.3.4 5.6.7.8` |
| Firewall | `[allow\|block\|challenge] target [note]` | `1.2.3.0/24` · `allow 2001:db8::1` · `challenge RU` · `AS13335 bad bots` |
| WAF rule | `action expression` | `block (ip.src.country eq "RU")` |
| Rate limit | `requests period timeout expression` | `50 10 10 (http.request.uri.path contains "/login")` |
| Redirect | `from to [code]` | `old.example.com https://new.example.com 301` |
| Page Rule | `pattern target [code]` | `example.com/old/* https://example.com/new/$1` |
| Purge by URL | one item per line | `https://example.com/a.css` · `example.com/blog/` · `www.example.com` |

`@` is the domain itself and short names (`sub`) are completed automatically. For A / AAAA / CNAME the last `1` turns the proxy on.

## 🔐 Security

- **Tokens are encrypted** in `data.json` with a key kept in `/etc/cfbot.env` (`DATA_KEY`, root-only). Back up both together: the data file is useless without the key. If the `cryptography` package cannot be installed on your system, the bot still runs and stores tokens unencrypted.
- `/opt/cfbot` is `700` and `data.json` / `audit.log` are `600`, owned by the unprivileged `cfbot` user.
- **Roles** (Settings → Admins): the owner (from `ADMIN_IDS`) decides for each admin whether they are *full* or *read-only* and which accounts they can see. Only full admins with access to all accounts can add or remove accounts.
- **Activity log** (Settings → Activity log): every change is appended to `/opt/cfbot/audit.log`; tokens are never written there.
- **Alerts** run every 10 minutes. Set `MONITOR_MINUTES=30` (or `0` to turn the checks off) in `/etc/cfbot.env`, then `sudo cfbot restart`.

Restoring a backup made by `cfbot uninstall`: reinstall, copy `/root/cfbot-data-backup.json` to `/opt/cfbot/data.json` (`chown cfbot:cfbot`, `chmod 600`), replace the `DATA_KEY=` line in `/etc/cfbot.env` with the one from `/root/cfbot-env-backup`, then `sudo cfbot restart`.

## 🎨 Premium emoji & colors

1. Bot → **Settings → Design mode** → ON.
2. Under every screen tap **🎨 Customize this screen**, pick any button/text, choose a color and send any emoji.
3. Premium emoji on buttons/text require Telegram's condition: the bot **owner has Telegram Premium** *or* the bot owns an extra **Fragment username**. Otherwise normal emoji are shown.

## 🧪 Development

```bash
pip install -r requirements.txt pytest
python -m pytest -q
```

The tests drive the whole bot against in-memory fakes of Telegram and the Cloudflare API (`tests/conftest.py`); no token or network is needed.

---

## 🇮🇷 راهنمای فارسی

**نصب:** دستور بالا را روی سرور اجرا کنید؛ اسکریپت توکن ربات و آیدی عددی ادمین را می‌پرسد و همه‌چیز (سرویس، محیط پایتون، کلید رمزنگاری، منوی مدیریت) را خودش راه می‌اندازد.

**مدیریت:** فقط بنویسید `sudo cfbot` تا منوی وضعیت، لاگ، ری‌استارت، آپدیت، تغییر توکن و حذف باز شود. اگر نسخهٔ جدید بعد از آپدیت بالا نیاید، نسخه و دادهٔ قبلی خودکار برمی‌گردد.

**ارتقا از نسخهٔ ۲:** دستور `sudo cfbot update` را **دو بار** اجرا کنید (بار دوم کلید رمزنگاری و تنظیمات امنیتی سرویس اعمال می‌شود).

**توکن کلودفلر:** پنج دسترسی اول جدول بالا برای کارهای اصلی کافی است؛ برای آمار، قوانین WAF، ریدایرکت، Workers، Pages و Tunnel دسترسی‌های بعدی را هم بدهید. سپس در ربات روی «افزودن حساب» بزنید.

**رکورد DNS:** مثل `A sub 1.2.3.4 1` یا `TXT @ v=spf1 include:_spf.google.com ~all` یا `MX @ 10 mail.example.com` بفرستید. `@` یعنی خودِ دامنه.

**تعویض گروهی IP:** در صفحهٔ DNS (یک دامنه) یا صفحهٔ دامنه‌ها (کل حساب) روی «تعویض گروهی IP» بزنید و `IP قدیم IP جدید` را بفرستید؛ قبل از هر تغییری فهرست رکوردها نمایش داده می‌شود.

**ادمین‌ها:** از *تنظیمات ← ادمین‌ها* برای هر ادمین نقش «کامل» یا «فقط‌خواندنی» و حساب‌های مجاز را تعیین کنید. همهٔ تغییرها در *گزارش فعالیت* ثبت می‌شود.

**امنیت:** توکن‌ها رمزنگاری‌شده ذخیره می‌شوند و کلید در `/etc/cfbot.env` است؛ از هر دو با هم بکاپ بگیرید.

**ایموجی پرمیوم و رنگ دکمه‌ها:** از *تنظیمات ← حالت طراحی* هر دکمه یا متن را جدا شخصی‌سازی کنید.

## 📁 Structure

```
CFManagement/
├── install.sh         # installer + manager (DenTeeR UI)
├── cfbot.py           # the bot (single file)
├── requirements.txt   # pinned dependencies
├── tests/             # pytest suite (fake Telegram + fake Cloudflare)
├── .github/workflows/ # CI
├── README.md
├── LICENSE
└── .gitignore
```

## 📜 License

MIT © DenTeeR
