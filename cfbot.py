#!/usr/bin/env python3
# CF Control — Cloudflare manager Telegram bot (single file, raw Bot API)
# Developed by DenTeeR  ·  MIT License
import os, re, sys, json, html, time, zlib, asyncio, secrets, ipaddress, traceback, contextvars
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from urllib.parse import quote
import httpx

VERSION = "3.0"
TOKEN = os.environ["BOT_TOKEN"]
ADMINS = {int(x) for x in os.environ["ADMIN_IDS"].split(",") if x.strip()}
TG = f"https://api.telegram.org/bot{TOKEN}/"
TGF = f"https://api.telegram.org/file/bot{TOKEN}/"
CF = "https://api.cloudflare.com/client/v4"
BASE = os.environ.get("CFBOT_DIR") or os.path.dirname(os.path.abspath(__file__))
DBF = os.path.join(BASE, "data.json")
AUDF = os.path.join(BASE, "audit.log")
MON_EVERY = int(os.environ.get("MONITOR_MINUTES") or 10) * 60  # 0 = no background checks
H = httpx.AsyncClient(timeout=70)   # Telegram (long polling needs a long timeout)
HC = httpx.AsyncClient(timeout=25)  # Cloudflare
S = {}      # runtime state per user
LOCKS = {}  # one lock per user: a slow request only blocks the user who made it

os.umask(0o077)  # data.json / audit.log hold secrets: never group/world readable
try:
    sys.stdout.reconfigure(line_buffering=True)  # logs reach journald immediately
except Exception:
    pass


def log(*a):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), " ".join(str(x) for x in a).replace(TOKEN, "***"), flush=True)


class Stop(Exception):
    """Abort the current action; the argument is a text key shown to the user."""


class Go(Exception):
    """Raised inside a view to show another view instead."""


# Premium emoji IDs (empty => normal emoji). Send a premium emoji to the bot to get its ID.
# New keys must be appended at the end: "Set emoji" maps a message's emoji to these keys in order.
EMO = {
    "cloud": ("", "☁️"), "plus": ("", "➕"), "globe": ("", "🌐"), "dns": ("", "📡"),
    "lock": ("", "🔒"), "fire": ("", "🔥"), "trash": ("", "🗑"), "back": ("", "◀️"),
    "gear": ("", "⚙️"), "lang": ("", "🌍"), "dev": ("", "🛠"), "ok": ("", "✅"),
    "edit": ("", "✏️"), "shield": ("", "🛡"), "export": ("", "📤"), "ban": ("", "⛔"),
    "bolt": ("", "⚡️"), "tag": ("", "🏷"), "green": ("", "🟢"), "yellow": ("", "🟡"), "red": ("", "🔴"),
    "target": ("", "🎯"), "time": ("", "⏱"), "warn": ("", "⚠️"), "puzzle": ("", "🧩"), "user": ("", "👤"), "crown": ("", "👑"),
    "bell": ("", "🔔"), "chart": ("", "📊"), "search": ("", "🔎"), "swap": ("", "🔁"), "import": ("", "📥"),
    "pause": ("", "⏸"), "play": ("", "▶️"), "eye": ("", "👁"), "log": ("", "📜"), "help": ("", "❓"),
    "link": ("", "🔗"), "box": ("", "📦"), "key": ("", "🔑"),
}

T = {
    "fa": dict(
        m_acc="حساب‌ها", m_zone="دامنه‌ها", m_add="افزودن حساب", m_set="تنظیمات",
        welcome="سلام! به <b>CF Control</b> خوش اومدی\nمدیریت کامل کلودفلر، بدون ورود به سایت.\nاز منوی پایین شروع کن 👇",
        back="بازگشت", lang="English", accs="حساب‌های کلودفلر", zones="دامنه‌های شما",
        empty="هنوز حسابی اضافه نشده.", none="موردی نیست", done="انجام شد ✅",
        bad="توکن نامعتبر است", saved="حساب ذخیره شد", dns="رکوردهای DNS", ssl="حالت SSL",
        sec="سطح امنیت", fw="فایروال", tog="تنظیمات سریع", purge="پاک‌سازی کش",
        export="خروجی DNS", ua="Under Attack", dev="حالت توسعه", new="رکورد جدید",
        e_content="ویرایش مقدار", e_name="ویرایش نام", e_ttl="ویرایش TTL", e_priority="ویرایش اولویت", proxy="پروکسی",
        delete="حذف", yes="بله، حذف کن", yes_do="بله، انجام بده",
        cancel="انصراف", lang_t="زبان / Language", emo="ایموجی پرمیوم", home="صفحه اصلی", prev="صفحه قبل", next="صفحه بعد", adm="ادمین‌ها", adm_add="افزودن ادمین",
        adm_ask="آیدی عددی تلگرام کاربر را بفرستید.\nکاربر می‌تواند آیدی خود را از @userinfobot بگیرد.", adm_ok="ادمین اضافه شد",
        adm_bad="آیدی نامعتبر است (فقط عدد).", owner="مالک", chk="بررسی اتصال", chk_title="وضعیت اتصال به کلودفلر",
        adm_note="فقط مالک می‌تواند ادمین اضافه یا حذف کند. برای هر ادمین می‌توانید نقش (کامل یا فقط‌خواندنی) و حساب‌های مجاز را تعیین کنید.",
        zdel="حذف دامنه", zdel_bad="❌ نام مطابقت نداشت. حذف لغو شد.",
        zdel_ask="⚠️ <b>حذف دامنه {}</b> از کلودفلر\nاین کار برگشت‌پذیر نیست و همهٔ رکوردها و تنظیمات پاک می‌شود.\nبرای تأیید، نام دقیق دامنه را تایپ و ارسال کنید:", design="حالت طراحی (شخصی‌سازی دکمه‌ها)", czm="دکمه‌های منوی پایین",
        cz_btn="شخصی‌سازی همین صفحه", cz_hint="روی هر دکمه یا متن بزنید تا رنگ و ایموجی همان یکی را جدا تغییر دهید. (📝 = ایموجی داخل متن)",
        c_style="رنگ", c_emoji="ایموجی", c_blue="آبی", c_green="سبز", c_red="قرمز", c_def="بدون رنگ",
        c_emo="تنظیم ایموجی", c_none="حذف ایموجی", c_reset="بازنشانی", c_ask="یک ایموجی بفرستید (پرمیوم یا معمولی، هر کدام دلخواه):", emo_set="ثبت ایموجی‌ها", emo_test="تست", emo_reset="بازنشانی",
        emo_ask="یک پیام بفرستید که <b>ایموجی‌های پرمیوم</b> را به‌ترتیب زیر داشته باشد (همه یا فقط چند تای اول):",
        emo_info="برای نمایش ایموجی پرمیوم، مالک ربات باید پریمیوم داشته باشد یا برای ربات یوزرنیم اضافه از Fragment خریده شده باشد.", block="مسدودسازی جدید",
        addtok="توکن API کلودفلر را بفرستید.\nدسترسی‌های پایه: Zone Read+Edit، DNS Edit، Zone Settings Edit، Cache Purge، Firewall Services Edit\nاختیاری برای بخش‌های جدید: Analytics Read، Zone WAF Edit، Dynamic Redirect Edit، Page Rules Edit، Workers Routes Edit، Workers Scripts Edit، Pages Edit، Cloudflare Tunnel Read، Account Settings Read",
        adddns="رکورد را بفرستید:\n<code>TYPE name content</code>\n\n<code>A sub 1.2.3.4 1</code>  ← عدد آخر: ۱ = پروکسی روشن\n<code>CNAME www example.com 0</code>\n<code>TXT @ v=spf1 include:_spf.google.com ~all</code>\n<code>MX @ 10 mail.example.com</code>\n<code>SRV _sip._tcp 10 5 5060 sip.example.com</code>\n<code>CAA @ 0 issue letsencrypt.org</code>\n\n<code>@</code> یعنی خودِ دامنه؛ نام کوتاه (مثل <code>sub</code>) خودکار کامل می‌شود.",
        ask_content="مقدار جدید را بفرستید (مثلاً IP):", ask_name="نام جدید را بفرستید (مثلاً sub.example.com):",
        ask_ttl="TTL را به ثانیه بفرستید یا <code>auto</code>:", ask_priority="اولویت جدید را بفرستید (مثلاً <code>10</code>):",
        ask_srv="مقدار جدید SRV را بفرستید:\n<code>priority weight port target</code>", ask_caa="مقدار جدید CAA را بفرستید:\n<code>flags tag value</code>",
        askfw="بفرستید:\n<code>1.2.3.4</code> یا <code>1.2.3.0/24</code> یا <code>2001:db8::1</code> یا <code>AS13335</code> یا کد کشور مثل <code>RU</code>\nپیش‌فرض: بلاک. برای اجازه: <code>allow 1.2.3.4</code>\nبرای چلنج: <code>challenge RU</code>\nبعد از مقدار می‌توانید یک یادداشت هم بنویسید.",
        stale="⚠️ این پیام قدیمی است؛ صفحهٔ فعلی نمایش داده شد.", denied="⛔ فقط مالک ربات اجازهٔ این کار را دارد.",
        ro="👁 دسترسی شما فقط‌خواندنی است.", nomg="⛔ شما اجازهٔ افزودن یا حذف حساب را ندارید.",
        expired="⌛ این تأیید منقضی شده؛ دوباره تلاش کنید.", cancelled="لغو شد.", oops="خطای داخلی: {}",
        gone="این حساب دیگر در دسترس نیست. از «حساب‌ها» دوباره انتخاب کنید.",
        nokey="توکن این حساب رمزنگاری شده ولی کلید DATA_KEY در دسترس نیست.",
        noaid="شناسهٔ حساب کلودفلر پیدا نشد (توکن به دسترسی Account Settings: Read نیاز دارد).",
        perm_hint="↳ احتمالاً توکن کلودفلر دسترسی این بخش را ندارد.", dup="این توکن قبلاً ذخیره شده است.",
        q_acc="حساب «{}» از ربات حذف شود؟\nخودِ حساب کلودفلر و دامنه‌هایش دست‌نخورده می‌مانند.",
        q_rec="رکورد <code>{}</code> برای همیشه حذف شود؟",
        q_purge="کل کش دامنهٔ <b>{}</b> پاک شود؟\nتا پر شدن دوبارهٔ کش، بار سرور اصلی بیشتر می‌شود.",
        q_fw="قانون <code>{}</code> حذف شود؟",
        q_ssl="SSL دامنهٔ <b>{}</b> خاموش شود؟\nبازدیدکننده‌ها دیگر اتصال امن نخواهند داشت.",
        q_pause="کلودفلر برای <b>{}</b> متوقف شود؟\nترافیک مستقیم به سرور اصلی می‌رود و IP آن آشکار می‌شود.",
        q_hsts="HSTS برای <b>{}</b> روشن شود؟\nاگر بعداً HTTPS سایت از کار بیفتد، مرورگرها تا پایان max-age سایت را باز نمی‌کنند.",
        q_dsec="DNSSEC برای <b>{}</b> خاموش شود؟\nاول رکورد DS را از ثبت‌کنندهٔ دامنه بردارید، وگرنه دامنه از دسترس خارج می‌شود.",
        q_adm="ادمین <code>{}</code> حذف شود؟", q_rule="این قانون حذف شود؟\n<code>{}</code>",
        q_wk="Worker «{}» برای همیشه حذف شود؟",
        q_bulk="<b>{}</b> رکورد در <b>{}</b> دامنه از <code>{}</code> به <code>{}</code> تغییر کند؟",
        search="جستجو", clear="حذف فیلتر", ftype="نوع رکورد", all="همه",
        ds_ask="بخشی از نام یا مقدار رکورد را بفرستید:", zq_ask="بخشی از نام دامنه را بفرستید:",
        bulk="تعویض گروهی IP", bulk_z="فقط همین دامنه", bulk_a="همهٔ دامنه‌های این حساب",
        bulk_ask="IP قدیمی و جدید را با یک فاصله بفرستید:\n<code>1.2.3.4 5.6.7.8</code>\nهمهٔ رکوردهایی که مقدارشان IP قدیمی است تغییر می‌کنند ({}).",
        bulk_none="رکوردی با این IP پیدا نشد.", bulk_bad="دو IP معتبر و متفاوت از یک نوع بفرستید (هر دو IPv4 یا هر دو IPv6).",
        bulk_res="🔁 {} از {} رکورد تغییر کرد.", bulk_more="… و {} مورد دیگر", bulk_cap="⚠️ فقط {} رکورد اول تغییر می‌کند.",
        x_fmt="فرمت نادرست است. نمونه‌های بالا را ببینید و دوباره بفرستید.", x_ip="IP با نوع رکورد جور نیست (A = IPv4، AAAA = IPv6).",
        x_mx="فرمت MX:\n<code>MX name priority server</code>", x_srv="فرمت SRV:\n<code>SRV name priority weight port target</code>",
        x_caa="فرمت CAA:\n<code>CAA name flags tag value</code>", x_ttl="TTL باید <code>auto</code> یا عددی بین ۶۰ تا ۸۶۴۰۰ باشد.",
        x_prio="اولویت باید عددی بین ۰ تا ۶۵۵۳۵ باشد.", x_rule="فرمت نادرست است. نمونهٔ بالا را ببینید.",
        fw_bad="مقدار معتبر نیست (IP، محدودهٔ CIDR، ASN یا کد دوحرفی کشور).",
        zadd="افزودن دامنه", zadd_ask="نام دامنه را بفرستید (مثلاً <code>example.com</code>):", zadd_bad="نام دامنه معتبر نیست.",
        zadd_ok="✅ دامنهٔ <b>{}</b> اضافه شد.\nاین نیم‌سرورها را در ثبت‌کنندهٔ دامنه تنظیم کنید:\n{}",
        aids="این توکن به چند حساب کلودفلر دسترسی دارد؛ یکی را انتخاب کنید:", aisw="تغییر حساب کلودفلر",
        paused="متوقف (فقط DNS)", pause="توقف کلودفلر", resume="ازسرگیری کلودفلر", zac="بررسی مجدد فعال‌سازی",
        pending_hint="برای فعال شدن، نیم‌سرورهای بالا را در ثبت‌کنندهٔ دامنه تنظیم کنید.",
        an="آمار", rl="قوانین", zs="تنظیمات بیشتر", imp="ورود DNS",
        imp_ask="فایل BIND (مثل خروجی همین ربات) را به‌صورت فایل بفرستید یا متنش را پیست کنید.\nرکوردها به رکوردهای فعلی <b>اضافه</b> می‌شوند.",
        imp_ok="✅ {} از {} رکورد اضافه شد.", imp_big="فایل بزرگ‌تر از ۲ مگابایت است.", imp_dl="دریافت فایل از تلگرام ناموفق بود.",
        pc_all="پاک‌سازی همه", pc_url="پاک‌سازی بر اساس URL",
        pc_ask="هر خط یک مورد (حداکثر ۳۰):\n<code>https://example.com/style.css</code> ← یک فایل\n<code>example.com/blog/</code> ← همهٔ آدرس‌های زیر این مسیر\n<code>www.example.com</code> ← کل یک هاست",
        pc_bad="هیچ مورد معتبری پیدا نشد.",
        tls="حداقل نسخهٔ TLS", cache="سطح کش", hsts="HSTS", dsec="DNSSEC", on="روشن", off="خاموش",
        enable="روشن کردن", disable="خاموش کردن", hs_6m="۶ ماه", hs_1y="۱ سال",
        ds_hint="این رکورد DS را در ثبت‌کنندهٔ دامنه وارد کنید:",
        an_req="درخواست‌ها", an_cached="کش‌شده", an_bw="پهنای باند", an_pv="بازدید صفحه", an_uniq="بازدیدکنندهٔ یکتا (بیشینه)",
        an_thr="تهدیدها", an_top="کشورهای پرترافیک", an_none="داده‌ای برای این بازه نیست.", an_24="۲۴ ساعت", an_7="۷ روز", an_30="۳۰ روز",
        rs_w="قوانین WAF", rs_r="محدودیت نرخ", rs_d="ریدایرکت‌ها", pr="Page Rules", wr="مسیرهای Worker",
        rule_new="قانون جدید", rule_toggle="روشن / خاموش",
        rn_w="قانون را بفرستید:\n<code>action expression</code>\naction یکی از: block، managed_challenge، js_challenge، challenge، log\n\nنمونه:\n<code>block (ip.src.country eq \"RU\" and http.request.uri.path contains \"/admin\")</code>",
        rn_r="بفرستید:\n<code>requests period timeout expression</code>\n\nنمونه (۵۰ درخواست در ۱۰ ثانیه ← ۱۰ ثانیه مسدود):\n<code>50 10 10 (http.request.uri.path contains \"/login\")</code>\nدر پلن رایگان period و timeout باید ۱۰ باشد.",
        rn_d="بفرستید:\n<code>from to [301|302]</code>\n\nنمونه:\n<code>old.example.com https://new.example.com 301</code>\n<code>example.com/blog https://blog.example.com</code>",
        prn_ask="بفرستید:\n<code>pattern target [301|302]</code>\n\nنمونه:\n<code>example.com/old/* https://example.com/new/$1 301</code>",
        wrn_ask="بفرستید:\n<code>pattern script</code>\n\nنمونه:\n<code>example.com/api/* my-worker</code>",
        svc="سرویس‌ها", wk="Workers", pgs="Pages", tn="Tunnels", pgr="تلاش مجدد آخرین استقرار", conns="اتصال‌ها",
        role="نقش", r_full="مدیر کامل", r_ro="فقط‌خواندنی", a_accs="حساب‌های مجاز", a_all="همهٔ حساب‌ها",
        mon="هشدارها", log="گزارش فعالیت", log_none="هنوز فعالیتی ثبت نشده.", log_x="دریافت فایل کامل",
        al_bad="🔴 اتصال حساب «{}» به کلودفلر قطع شد:\n{}", al_ok="🟢 اتصال حساب «{}» دوباره برقرار شد.",
        al_zone="🔔 وضعیت دامنهٔ <b>{}</b> تغییر کرد: {} ← {}",
        help="راهنما", c_start="منوی اصلی", c_help="راهنما", c_cancel="لغو عملیات جاری",
        help_t="<b>راهنمای CF Control</b>\n\n<b>حساب‌ها</b> — توکن API کلودفلر را اضافه کنید و اتصال را بررسی کنید.\n<b>دامنه‌ها</b> — جستجو، افزودن دامنه، تعویض گروهی IP و سرویس‌ها (Workers، Pages، Tunnel).\n<b>هر دامنه</b> — DNS (جستجو، فیلتر، ورود و خروجی فایل)، SSL، امنیت، فایروال، قوانین WAF، محدودیت نرخ، ریدایرکت، آمار، کش و تنظیمات بیشتر.\n\n<b>افزودن رکورد DNS</b>\n<code>A sub 1.2.3.4 1</code>\n<code>TXT @ v=spf1 include:_spf.google.com ~all</code>\n<code>MX @ 10 mail.example.com</code>\n\n<b>دستورها</b>\n/start منوی اصلی · /cancel لغو · /help راهنما\n\nکارهای خطرناک همیشه تأیید می‌خواهند و همهٔ تغییرها در «گزارش فعالیت» ثبت می‌شود.",
    ),
    "en": dict(
        m_acc="Accounts", m_zone="Zones", m_add="Add account", m_set="Settings",
        welcome="Welcome to <b>CF Control</b>\nFull Cloudflare management without leaving Telegram.\nUse the menu below 👇",
        back="Back", lang="فارسی", accs="Cloudflare accounts", zones="Your zones",
        empty="No accounts yet.", none="Nothing here", done="Done ✅",
        bad="Invalid token", saved="Account saved", dns="DNS records", ssl="SSL mode",
        sec="Security level", fw="Firewall", tog="Quick settings", purge="Purge cache",
        export="Export DNS", ua="Under Attack", dev="Dev mode", new="New record",
        e_content="Edit content", e_name="Edit name", e_ttl="Edit TTL", e_priority="Edit priority", proxy="Proxy",
        delete="Delete", yes="Yes, delete", yes_do="Yes, do it",
        cancel="Cancel", lang_t="Language / زبان", emo="Premium emoji", home="Main page", prev="Previous page", next="Next page", adm="Admins", adm_add="Add admin",
        adm_ask="Send the user's numeric Telegram ID.\nThey can get it from @userinfobot.", adm_ok="Admin added",
        adm_bad="Invalid ID (numbers only).", owner="Owner", chk="Check connection", chk_title="Cloudflare connection status",
        adm_note="Only the owner can add or remove admins. Each admin can be given a role (full or read-only) and a list of allowed accounts.",
        zdel="Delete domain", zdel_bad="❌ Name did not match. Deletion cancelled.",
        zdel_ask="⚠️ <b>Delete domain {}</b> from Cloudflare\nThis cannot be undone; all records and settings will be removed.\nTo confirm, type the exact domain name:", design="Design mode (customize buttons)", czm="Bottom menu buttons",
        cz_btn="Customize this screen", cz_hint="Tap any button or text to change its color and emoji individually. (📝 = emoji inside text)",
        c_style="Color", c_emoji="Emoji", c_blue="Blue", c_green="Green", c_red="Red", c_def="No color",
        c_emo="Set emoji", c_none="Remove emoji", c_reset="Reset", c_ask="Send any emoji (premium or normal):", emo_set="Set emoji", emo_test="Test", emo_reset="Reset",
        emo_ask="Send one message containing <b>premium emoji</b> in this order (all of them, or just the first few):",
        emo_info="Premium emoji need the bot owner to have Telegram Premium, or the bot to own an extra Fragment username.", block="New block rule",
        addtok="Send your Cloudflare API token.\nBase permissions: Zone Read+Edit, DNS Edit, Zone Settings Edit, Cache Purge, Firewall Services Edit\nOptional, for the newer sections: Analytics Read, Zone WAF Edit, Dynamic Redirect Edit, Page Rules Edit, Workers Routes Edit, Workers Scripts Edit, Pages Edit, Cloudflare Tunnel Read, Account Settings Read",
        adddns="Send the record:\n<code>TYPE name content</code>\n\n<code>A sub 1.2.3.4 1</code>  ← last number: 1 = proxied\n<code>CNAME www example.com 0</code>\n<code>TXT @ v=spf1 include:_spf.google.com ~all</code>\n<code>MX @ 10 mail.example.com</code>\n<code>SRV _sip._tcp 10 5 5060 sip.example.com</code>\n<code>CAA @ 0 issue letsencrypt.org</code>\n\n<code>@</code> is the domain itself; short names (like <code>sub</code>) are completed automatically.",
        ask_content="Send the new content (e.g. an IP):", ask_name="Send the new name (e.g. sub.example.com):",
        ask_ttl="Send TTL in seconds or <code>auto</code>:", ask_priority="Send the new priority (e.g. <code>10</code>):",
        ask_srv="Send the new SRV value:\n<code>priority weight port target</code>", ask_caa="Send the new CAA value:\n<code>flags tag value</code>",
        askfw="Send:\n<code>1.2.3.4</code> or <code>1.2.3.0/24</code> or <code>2001:db8::1</code> or <code>AS13335</code> or a country code like <code>RU</code>\nDefault: block. To allow: <code>allow 1.2.3.4</code>\nFor challenge: <code>challenge RU</code>\nYou can add a note after the value.",
        stale="⚠️ This message is outdated; showing the current screen.", denied="⛔ Only the bot owner can do this.",
        ro="👁 Your access is read-only.", nomg="⛔ You are not allowed to add or remove accounts.",
        expired="⌛ This confirmation has expired; try again.", cancelled="Cancelled.", oops="Internal error: {}",
        gone="This account is no longer available. Pick one again from “Accounts”.",
        nokey="This account's token is encrypted but the DATA_KEY is not available.",
        noaid="Could not find the Cloudflare account ID (the token needs Account Settings: Read).",
        perm_hint="↳ The Cloudflare token probably lacks permission for this section.", dup="This token is already saved.",
        q_acc="Remove account “{}” from the bot?\nThe Cloudflare account itself and its domains are not touched.",
        q_rec="Delete record <code>{}</code> permanently?",
        q_purge="Purge the whole cache of <b>{}</b>?\nUntil the cache refills, your origin server gets more load.",
        q_fw="Delete rule <code>{}</code>?",
        q_ssl="Turn SSL off for <b>{}</b>?\nVisitors will no longer have a secure connection.",
        q_pause="Pause Cloudflare for <b>{}</b>?\nTraffic goes straight to your origin and its IP is exposed.",
        q_hsts="Enable HSTS for <b>{}</b>?\nIf HTTPS breaks later, browsers refuse to open the site until max-age ends.",
        q_dsec="Disable DNSSEC for <b>{}</b>?\nRemove the DS record at your registrar first, or the domain stops resolving.",
        q_adm="Remove admin <code>{}</code>?", q_rule="Delete this rule?\n<code>{}</code>",
        q_wk="Delete Worker “{}” permanently?",
        q_bulk="Change <b>{}</b> record(s) in <b>{}</b> zone(s) from <code>{}</code> to <code>{}</code>?",
        search="Search", clear="Clear filter", ftype="Record type", all="All",
        ds_ask="Send part of a record name or content:", zq_ask="Send part of the domain name:",
        bulk="Bulk IP replace", bulk_z="this zone only", bulk_a="all zones of this account",
        bulk_ask="Send the old and the new IP separated by a space:\n<code>1.2.3.4 5.6.7.8</code>\nEvery record whose content is the old IP will be changed ({}).",
        bulk_none="No record with this IP was found.", bulk_bad="Send two valid, different IPs of the same kind (both IPv4 or both IPv6).",
        bulk_res="🔁 {} of {} record(s) changed.", bulk_more="… and {} more", bulk_cap="⚠️ Only the first {} records will be changed.",
        x_fmt="Wrong format. See the examples above and send it again.", x_ip="The IP does not match the record type (A = IPv4, AAAA = IPv6).",
        x_mx="MX format:\n<code>MX name priority server</code>", x_srv="SRV format:\n<code>SRV name priority weight port target</code>",
        x_caa="CAA format:\n<code>CAA name flags tag value</code>", x_ttl="TTL must be <code>auto</code> or a number between 60 and 86400.",
        x_prio="Priority must be a number between 0 and 65535.", x_rule="Wrong format. See the example above.",
        fw_bad="Not a valid value (IP, CIDR range, ASN or two-letter country code).",
        zadd="Add domain", zadd_ask="Send the domain name (e.g. <code>example.com</code>):", zadd_bad="Not a valid domain name.",
        zadd_ok="✅ Domain <b>{}</b> added.\nSet these nameservers at your registrar:\n{}",
        aids="This token can access several Cloudflare accounts; pick one:", aisw="Switch Cloudflare account",
        paused="Paused (DNS only)", pause="Pause Cloudflare", resume="Resume Cloudflare", zac="Re-check activation",
        pending_hint="To activate, set the nameservers above at your registrar.",
        an="Analytics", rl="Rules", zs="More settings", imp="Import DNS",
        imp_ask="Send a BIND file (like this bot's export) as a document, or paste its text.\nRecords are <b>added</b> to the existing ones.",
        imp_ok="✅ {} of {} record(s) added.", imp_big="The file is larger than 2 MB.", imp_dl="Could not download the file from Telegram.",
        pc_all="Purge everything", pc_url="Purge by URL",
        pc_ask="One item per line (max 30):\n<code>https://example.com/style.css</code> ← one file\n<code>example.com/blog/</code> ← everything under this path\n<code>www.example.com</code> ← a whole host",
        pc_bad="No valid item found.",
        tls="Minimum TLS version", cache="Cache level", hsts="HSTS", dsec="DNSSEC", on="On", off="Off",
        enable="Enable", disable="Disable", hs_6m="6 months", hs_1y="1 year",
        ds_hint="Add this DS record at your registrar:",
        an_req="Requests", an_cached="cached", an_bw="Bandwidth", an_pv="Page views", an_uniq="Unique visitors (peak)",
        an_thr="Threats", an_top="Top countries", an_none="No data for this period.", an_24="24 hours", an_7="7 days", an_30="30 days",
        rs_w="WAF rules", rs_r="Rate limiting", rs_d="Redirects", pr="Page Rules", wr="Worker routes",
        rule_new="New rule", rule_toggle="Enable / disable",
        rn_w="Send the rule:\n<code>action expression</code>\naction is one of: block, managed_challenge, js_challenge, challenge, log\n\nExample:\n<code>block (ip.src.country eq \"RU\" and http.request.uri.path contains \"/admin\")</code>",
        rn_r="Send:\n<code>requests period timeout expression</code>\n\nExample (50 requests in 10 s → blocked for 10 s):\n<code>50 10 10 (http.request.uri.path contains \"/login\")</code>\nOn the Free plan period and timeout must be 10.",
        rn_d="Send:\n<code>from to [301|302]</code>\n\nExamples:\n<code>old.example.com https://new.example.com 301</code>\n<code>example.com/blog https://blog.example.com</code>",
        prn_ask="Send:\n<code>pattern target [301|302]</code>\n\nExample:\n<code>example.com/old/* https://example.com/new/$1 301</code>",
        wrn_ask="Send:\n<code>pattern script</code>\n\nExample:\n<code>example.com/api/* my-worker</code>",
        svc="Services", wk="Workers", pgs="Pages", tn="Tunnels", pgr="Retry latest deployment", conns="Connections",
        role="Role", r_full="Full admin", r_ro="Read-only", a_accs="Allowed accounts", a_all="All accounts",
        mon="Alerts", log="Activity log", log_none="No activity recorded yet.", log_x="Download full file",
        al_bad="🔴 Account “{}” lost its connection to Cloudflare:\n{}", al_ok="🟢 Account “{}” is connected again.",
        al_zone="🔔 Zone <b>{}</b> changed status: {} → {}",
        help="Help", c_start="Main menu", c_help="Help", c_cancel="Cancel the current operation",
        help_t="<b>CF Control help</b>\n\n<b>Accounts</b> — add Cloudflare API tokens and check their connection.\n<b>Zones</b> — search, add a domain, bulk IP replace and services (Workers, Pages, Tunnel).\n<b>Each zone</b> — DNS (search, filter, file import and export), SSL, security, firewall, WAF rules, rate limiting, redirects, analytics, cache and more settings.\n\n<b>Adding a DNS record</b>\n<code>A sub 1.2.3.4 1</code>\n<code>TXT @ v=spf1 include:_spf.google.com ~all</code>\n<code>MX @ 10 mail.example.com</code>\n\n<b>Commands</b>\n/start main menu · /cancel cancel · /help help\n\nDangerous actions always ask for confirmation and every change is written to the activity log.",
    ),
}

TOGGLES = [("always_use_https", "Always HTTPS"), ("automatic_https_rewrites", "HTTPS Rewrites"), ("tls_1_3", "TLS 1.3"),
           ("ipv6", "IPv6"), ("http3", "HTTP/3"), ("0rtt", "0-RTT"), ("websockets", "WebSockets"), ("brotli", "Brotli"),
           ("early_hints", "Early Hints"), ("always_online", "Always Online"), ("rocket_loader", "Rocket Loader"),
           ("opportunistic_encryption", "Opp. Encryption"), ("email_obfuscation", "Email Obfuscation"),
           ("hotlink_protection", "Hotlink Protection"), ("browser_check", "Browser Check")]
LEVELS = ["essentially_off", "low", "medium", "high", "under_attack"]
SSLM = ["off", "flexible", "full", "strict"]
TLSV = ["1.0", "1.1", "1.2", "1.3"]
CACHEL = ["basic", "simplified", "aggressive"]
DTYPES = ["A", "AAAA", "CNAME", "TXT", "MX", "NS", "SRV", "CAA"]
PH = {"w": "http_request_firewall_custom", "r": "http_ratelimit", "d": "http_request_dynamic_redirect"}
WAFACT = ("block", "managed_challenge", "js_challenge", "challenge", "log")
HEX = re.compile(r"[0-9a-f]{32}")
ison = lambda v: v in ("on", "zrt")

# ───────────────────────── storage ─────────────────────────
FER = None
if os.environ.get("DATA_KEY"):
    try:
        from cryptography.fernet import Fernet
        FER = Fernet(os.environ["DATA_KEY"].encode())
    except Exception as ex:  # missing library or malformed key: keep running, tokens stay as they are
        log("DATA_KEY is set but encryption is unavailable:", repr(ex))


def enc(s):
    return "enc:" + FER.encrypt(s.encode()).decode() if FER and not s.startswith("enc:") else s


def dec(s):
    if not s.startswith("enc:"):
        return s
    try:
        return FER.decrypt(s[4:].encode()).decode()
    except Exception:
        raise Stop("nokey")


def load():
    d = {}
    if os.path.exists(DBF):
        try:
            with open(DBF, encoding="utf-8") as f:
                d = json.load(f)
        except ValueError:  # never overwrite a damaged file: keep it aside and start clean
            bad = f"{DBF}.corrupt-{int(time.time())}"
            os.replace(DBF, bad)
            log("data.json was damaged; moved to", bad)
            d = {}
        else:
            try:
                os.chmod(DBF, 0o600)
            except OSError as ex:
                log("could not restrict data.json permissions:", repr(ex))
    if not isinstance(d, dict):
        d = {}
    d.setdefault("accounts", []); d.setdefault("lang", {})
    changed = False
    for a in d["accounts"]:
        if not a.get("id"):
            a["id"] = secrets.token_hex(4); changed = True
        if FER and not a["token"].startswith("enc:"):
            a["token"] = enc(a["token"]); changed = True
    return d, changed


def save():
    tmp = DBF + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=1)
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, DBF)  # atomic: a crash can never leave a half-written data.json


db, _changed = load()
if _changed:
    save()

lang = lambda uid: db["lang"].get(str(uid), "fa")
t = lambda uid, k: T[lang(uid)].get(k) or T["en"].get(k, k)
norm = lambda s: re.sub(r"^[^\w]+", "", s).strip()
MENU = {norm(T[l][k]): v for l in T for k, v in (("m_acc", "acc"), ("m_zone", "zones"), ("m_add", "addtok"), ("m_set", "set"))}
isowner = lambda uid: uid in ADMINS
isadmin = lambda uid: uid in ADMINS or uid in db.get("admins", [])
perm = lambda uid: (db.get("perm") or {}).get(str(uid), {})
readonly = lambda uid: not isowner(uid) and bool(perm(uid).get("ro"))
canmanage = lambda uid: isowner(uid) or (not perm(uid).get("ro") and perm(uid).get("accs") is None)
getacc = lambda aid: next((a for a in db["accounts"] if a["id"] == aid), None)


def canacc(uid, aid):
    accs = perm(uid).get("accs")
    return isowner(uid) or accs is None or aid in accs


myaccs = lambda uid: [a for a in db["accounts"] if canacc(uid, a["id"])]


def audit(uid, act, acc="", zone="", detail="", ok=True):
    """Append one line to the activity log: who did what, where, and whether it worked."""
    try:
        if os.path.exists(AUDF) and os.path.getsize(AUDF) > 1 << 20:  # keep the newest ~256 KB
            with open(AUDF, "rb") as f:
                f.seek(-(256 << 10), 2); keep = f.read().split(b"\n", 1)[-1]
            with open(AUDF + ".tmp", "wb") as f:
                f.write(keep)
            os.replace(AUDF + ".tmp", AUDF)
        with open(AUDF, "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": int(time.time()), "u": uid, "a": act, "acc": acc, "z": zone,
                                "d": str(detail)[:200], "ok": bool(ok)}, ensure_ascii=False) + "\n")
    except OSError as ex:
        log("audit write failed:", repr(ex))


def tail(path, n):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2); f.seek(max(0, f.tell() - (64 << 10)))
            return f.read().decode("utf-8", "replace").splitlines()[-n:]
    except OSError:
        return []


# ───────────────────────── rendering helpers ─────────────────────────
OK = {"text": True, "btn": True}  # flipped to False if Telegram rejects custom emoji
eid = lambda k: (db.get("emo") or {}).get(k) or EMO[k][0]


class Ctx:  # what is being rendered right now (per task, so users never mix)
    def __init__(self):
        self.cur = ""; self.buf = []; self.key = ""


_cx = contextvars.ContextVar("cx", default=None)


def cx():
    c = _cx.get()
    if c is None:
        c = Ctx(); _cx.set(c)
    return c


def e(k):
    """Emoji inside text. Each screen+emoji is its own customizable slot."""
    c = cx(); f = EMO[k][1]; slot = f"{c.cur}.t.{k}"; c.buf.append((slot, f, "txt"))
    ov = (db.get("btn") or {}).get(slot, {})
    if ov.get("uni"): return ov["uni"]
    if ov.get("emo") == "x": return ""
    i = ov.get("emo") or eid(k)
    return f'<tg-emoji emoji-id="{i}">{f}</tg-emoji>' if i and OK["text"] else f


def rb(text, style=None, emo=None, bid=None):
    """Button base. style: primary | success | danger. bid = unique id for per-button overrides."""
    x = {"text": text}
    ov = (db.get("btn") or {}).get(bid, {}) if bid else {}
    if "style" in ov: style = None if ov["style"] == "none" else ov["style"]
    ico = ov.get("emo")
    if ov.get("uni"):
        x["text"] = ov["uni"] + " " + text if text else ov["uni"]
    elif ico == "x":
        pass
    elif ico and OK["btn"]:
        x["icon_custom_emoji_id"] = ico
    elif emo:
        i, f = eid(emo), EMO[emo][1]
        if i and OK["btn"]: x["icon_custom_emoji_id"] = i
        else: x["text"] = f + " " + text if text else f
    if style: x["style"] = style
    if not x["text"].strip(): x["text"] = "•"
    if bid: cx().buf.append((bid, x["text"] or (EMO[emo][1] if emo else "•"), "btn"))
    return x


def b(text, data, style=None, emo=None):
    """Inline button. The screen's context key is appended so taps on outdated messages are detected."""
    c = cx()
    return {**rb(text, style, emo, f"{c.cur}.{data.partition(':')[0]}"), "callback_data": data + ("|" + c.key if c.key else "")}


kb = lambda rows: {"inline_keyboard": rows}
bk = lambda uid, d: [b(t(uid, "back"), d, emo="back")]
chunk = lambda l, n: [l[i:i + n] for i in range(0, len(l), n)]
esc = lambda s: html.escape(str(s))
zname = lambda st: (st.get("zones") or {}).get(st.get("zone"), "")
here = lambda st: "zone" if st.get("zone") else "zones" if st.get("acc") else "acc"
dshort = lambda s: str(s or "")[:16].replace("T", " ")


def menu(uid):  # persistent bottom keyboard (not glass/inline)
    L = lambda k, s, em: rb(t(uid, k), s, em, "menu." + k)
    return {"keyboard": [[L("m_acc", "primary", "cloud"), L("m_zone", "primary", "globe")],
                         [L("m_add", "success", "plus"), L("m_set", None, "gear")]],
            "resize_keyboard": True, "is_persistent": True, "input_field_placeholder": "CF Control"}


def hn(n):
    n = float(n or 0)
    for u in ("", "K", "M", "B"):
        if abs(n) < 1000 or u == "B":
            return f"{n:.0f}" if u == "" else f"{n:.1f}{u}"
        n /= 1000


def hb(n):
    n = float(n or 0)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024


def spark(v):
    m = max(v, default=0)
    return "".join("▁▂▃▄▅▆▇█"[min(7, int(x * 8 / m))] for x in v) if m > 0 else ""


# ───────────────────────── Telegram ─────────────────────────
async def tg(m, **p):
    r = {}
    for i in range(3):
        try:
            r = (await H.post(TG + m, json=p)).json()
        except Exception as ex:
            return {"ok": False, "description": type(ex).__name__}
        wait = (r.get("parameters") or {}).get("retry_after")
        if r.get("ok") or not wait or m == "getUpdates" or i == 2:
            break
        await asyncio.sleep(min(int(wait), 30) + 0.5)  # flood limit: wait as told, then retry
    return r


def plain(p):
    """Same payload without custom emoji (fallback when Telegram rejects them)."""
    p = dict(p)
    p["text"] = re.sub(r'<tg-emoji emoji-id="\d+">(.*?)</tg-emoji>', r"\1", p["text"])
    rm = p.get("reply_markup") or {}
    for key in ("inline_keyboard", "keyboard"):
        if key in rm:
            rm = {**rm, key: [[{k: v for k, v in bt.items() if k != "icon_custom_emoji_id"} for bt in row] for row in rm[key]]}
    p["reply_markup"] = rm
    return p


async def send_menu(cid, uid, text):
    p = dict(chat_id=cid, text=text, parse_mode="HTML", reply_markup=menu(uid))
    if not (await tg("sendMessage", **p)).get("ok"):
        await tg("sendMessage", **plain(p))


async def say(cid, text):
    """Plain notice. Text is HTML; if Telegram rejects the markup it is sent without it."""
    r = await tg("sendMessage", chat_id=cid, text=text[:4000], parse_mode="HTML", link_preview_options={"is_disabled": True})
    if not r.get("ok"):
        r = await tg("sendMessage", chat_id=cid, text=html.unescape(re.sub(r"<[^>]+>", "", text))[:4000])
    return r


async def show(cid, mid, text, markup):
    p = dict(chat_id=cid, text=text, parse_mode="HTML", reply_markup=markup,
             link_preview_options={"is_disabled": True})
    for q in (p, plain(p)):
        if mid:
            r = await tg("editMessageText", message_id=mid, **q)
            if r.get("ok") or "not modified" in str(r):
                return
        r = await tg("sendMessage", **q)
        if r.get("ok"):
            return
        log("send failed:", r.get("description"))
    await tg("sendMessage", chat_id=cid, text=html.unescape(re.sub(r"<[^>]+>", "", text))[:4000], reply_markup=plain(p)["reply_markup"])


async def senddoc(cid, name, content):
    try:
        return (await H.post(TG + "sendDocument", data={"chat_id": str(cid)}, files={"document": (name, content)})).json()
    except Exception as ex:
        return {"ok": False, "description": type(ex).__name__}


async def tgfile(file_id, limit=2 << 20):
    p = ((await tg("getFile", file_id=file_id)).get("result") or {}).get("file_path")
    if not p:
        return None
    try:
        r = await H.get(TGF + p)
    except httpx.HTTPError:
        return None
    return r.content if r.status_code == 200 and len(r.content) <= limit else None


# ───────────────────────── Cloudflare ─────────────────────────
def fail(msg, status=0):
    return {"success": False, "errors": [{"code": 0, "message": msg}], "result": None, "_status": status}


async def cfreq(token, method, path, **kw):
    """One Cloudflare API call. Never raises: network and non-JSON failures come back as an error body."""
    try:
        r = await HC.request(method, CF + path, headers={"Authorization": f"Bearer {token}"}, **kw)
    except httpx.TimeoutException:
        return fail("Cloudflare timeout")
    except httpx.HTTPError as ex:
        return fail(f"network error ({type(ex).__name__})")
    try:
        j = r.json()
    except ValueError:
        j = None
    if not isinstance(j, dict):
        return fail("rate limited, try again in a minute" if r.status_code == 429 else f"HTTP {r.status_code}", r.status_code)
    if "success" not in j:  # GraphQL answers have no envelope
        j["success"] = r.status_code < 400 and not j.get("errors")
    j["_status"] = r.status_code
    return j


def acc_of(uid):
    st = S.get(uid) or {}
    a = getacc(st.get("acc"))
    if not a or not canacc(uid, a["id"]):
        st.pop("acc", None); st.pop("zone", None)
        raise Stop("gone")
    return a


tok = lambda uid: dec(acc_of(uid)["token"])
C = lambda uid, method, path, **kw: cfreq(tok(uid), method, path, **kw)


def errtxt(j, uid=None):
    e0 = (j.get("errors") or [{}])[0]
    if not isinstance(e0, dict):
        e0 = {"message": str(e0)}
    msg = str(e0.get("message") or "error")
    for sub in (e0.get("error_chain") or [])[:1]:
        msg += ": " + str(sub.get("message"))
    if uid is not None and (e0.get("code") in (10000, 9109) or j.get("_status") == 403):
        msg += "\n" + t(uid, "perm_hint")
    return msg[:300]


async def allpages(token, path, params=None, per=50, cap=1000):
    """Follow pagination. Returns (items, error_body_or_None)."""
    out, p = [], 1
    while True:
        j = await cfreq(token, "GET", path, params={**(params or {}), "per_page": per, "page": p})
        if not j.get("success"):
            return out, j
        out += j.get("result") or []
        if p >= ((j.get("result_info") or {}).get("total_pages") or 1) or len(out) >= cap:
            return out[:cap], None
        p += 1


async def ping(a):
    t0 = time.monotonic()
    try:
        r = await cfreq(dec(a["token"]), "GET", "/zones", params={"per_page": 1})
    except Stop:
        return a["name"], False, "DATA_KEY", 0
    ms = int((time.monotonic() - t0) * 1000)
    if r.get("success"):
        return a["name"], True, f"{(r.get('result_info') or {}).get('total_count', 0)} zones", ms
    return a["name"], False, errtxt(r), ms


async def probe(cid):
    """Send test messages so the user sees whether Telegram accepts the custom emoji."""
    ids = [eid(k) for k in EMO if eid(k)]
    if not ids:
        return "—"
    r1 = await tg("sendMessage", chat_id=cid, parse_mode="HTML", text=f'<tg-emoji emoji-id="{ids[0]}">⭐</tg-emoji> text test')
    r2 = await tg("sendMessage", chat_id=cid, text="button test", reply_markup={"inline_keyboard": [[
        {"text": "test", "callback_data": "noop", "icon_custom_emoji_id": ids[0], "style": "primary"}]]})
    OK["text"], OK["btn"] = bool(r1.get("ok")), bool(r2.get("ok"))
    return (f"text: {'✅' if r1.get('ok') else '❌ ' + str(r1.get('description'))}\n"
            f"buttons: {'✅' if r2.get('ok') else '❌ ' + str(r2.get('description'))}")


# ───────────────────────── input parsers (pure functions) ─────────────────────────
YES, NO = ("1", "true", "yes", "on"), ("0", "false", "no", "off")


def idna(name):
    if name.isascii():
        return name
    try:
        return name.encode("idna").decode()
    except UnicodeError:
        return name


def fqdn(name, zone):
    """'@' -> zone, 'sub' -> sub.zone, full names stay as they are."""
    name = idna(name.strip().rstrip(".").lower()); zone = zone.lower()
    if not zone:
        return name
    if name in ("@", ""):
        return zone
    return name if name == zone or name.endswith("." + zone) else f"{name}.{zone}"


def txtq(s):
    """TXT content must be quoted strings of at most 255 characters each."""
    s = s.strip()
    if len(s) > 1 and s.startswith('"') and s.endswith('"'):
        return s
    q = lambda x: '"' + x.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return " ".join(q(s[i:i + 255]) for i in range(0, len(s), 255)) or '""'


def _ip(v, version):
    try:
        ip = ipaddress.ip_address(v)
    except ValueError:
        raise ValueError("ip")
    if ip.version != version:
        raise ValueError("ip")
    return str(ip)


def _srv(p):
    if len(p) != 4 or not all(x.isdigit() for x in p[:3]):
        raise ValueError("srv")
    return {"priority": int(p[0]), "weight": int(p[1]), "port": int(p[2]), "target": p[3].rstrip(".")}


def _caa(p):
    if len(p) < 3 or not p[0].isdigit():
        raise ValueError("caa")
    return {"flags": int(p[0]), "tag": p[1], "value": " ".join(p[2:]).strip('"')}


def parse_rec(txt, zone=""):
    """'TYPE name content…' -> Cloudflare DNS record body. Raises ValueError(<e_ text key suffix>)."""
    p = txt.split()
    if len(p) < 3 or not re.fullmatch(r"[A-Za-z0-9]{1,10}", p[0]):
        raise ValueError("fmt")
    typ, rest = p[0].upper(), p[2:]
    rec = {"type": typ, "name": fqdn(p[1], zone), "ttl": 1}
    if typ in ("A", "AAAA", "CNAME"):
        flag = rest[1].lower() if len(rest) > 1 else "0"
        if len(rest) > 2 or flag not in YES + NO:
            raise ValueError("fmt")
        rec["content"] = rest[0].rstrip(".") if typ == "CNAME" else _ip(rest[0], 4 if typ == "A" else 6)
        rec["proxied"] = flag in YES
    elif typ == "MX":
        num = [x for x in rest if x.isdigit()]
        if len(rest) != 2 or len(num) != 1 or not 0 <= int(num[0]) <= 65535:
            raise ValueError("mx")
        rec["content"] = next(x for x in rest if not x.isdigit()).rstrip("."); rec["priority"] = int(num[0])
    elif typ == "SRV":
        rec["data"] = _srv(rest)
    elif typ == "CAA":
        rec["data"] = _caa(rest)
    else:  # TXT, NS, PTR, …: everything after the name is the content, spaces included
        content = txt.split(None, 2)[2].strip()
        rec["content"] = txtq(content) if typ == "TXT" else content
    return rec


def parse_edit(typ, field, txt, zone=""):
    """New value for one field of an existing record -> PATCH body."""
    txt = txt.strip()
    if field == "ttl":
        v = 1 if txt.lower() in ("auto", "1") else int(txt) if txt.isdigit() else -1
        if v != 1 and not 60 <= v <= 86400:
            raise ValueError("ttl")
        return {"ttl": v}
    if field == "priority":
        if not txt.isdigit() or int(txt) > 65535:
            raise ValueError("prio")
        return {"priority": int(txt)}
    if field == "name":
        if not txt or " " in txt:
            raise ValueError("fmt")
        return {"name": fqdn(txt, zone)}
    if not txt:
        raise ValueError("fmt")
    if typ == "SRV": return {"data": _srv(txt.split())}
    if typ == "CAA": return {"data": _caa(txt.split())}
    if typ == "TXT": return {"content": txtq(txt)}
    if typ in ("A", "AAAA"): return {"content": _ip(txt, 4 if typ == "A" else 6)}
    return {"content": txt}


FWMODES = {"allow": "whitelist", "whitelist": "whitelist", "block": "block", "challenge": "challenge",
           "js": "js_challenge", "js_challenge": "js_challenge", "managed": "managed_challenge", "managed_challenge": "managed_challenge"}


def parse_fw(txt):
    """'[allow|block|challenge] <ip|cidr|ASN|country> [note]' -> IP Access Rule body."""
    p = txt.split(); mode = "block"
    if len(p) > 1 and p[0].lower() in FWMODES:
        mode = FWMODES[p[0].lower()]; p = p[1:]
    if not p:
        raise ValueError("fw_bad")
    val = p[0]
    try:
        if re.fullmatch(r"(?i)as\d{1,10}", val): tgt, val = "asn", val.upper()
        elif re.fullmatch(r"(?i)[a-z]{2}|t1", val): tgt, val = "country", val.upper()
        elif "/" in val: tgt, val = "ip_range", str(ipaddress.ip_network(val, strict=False))
        else:
            ip = ipaddress.ip_address(val); tgt, val = ("ip6" if ip.version == 6 else "ip"), str(ip)
    except ValueError:
        raise ValueError("fw_bad")
    return {"mode": mode, "configuration": {"target": tgt, "value": val}, "notes": " ".join(p[1:])[:200]}


def parse_bulk(txt):
    """'old new' -> (old, new, record type)."""
    p = txt.split()
    try:
        a, c = ipaddress.ip_address(p[0]), ipaddress.ip_address(p[1])
    except (ValueError, IndexError):
        raise ValueError("bulk_bad")
    if len(p) != 2 or a.version != c.version or a == c:
        raise ValueError("bulk_bad")
    return str(a), str(c), "A" if a.version == 4 else "AAAA"


def _code(p, allowed):
    code = int(p[2]) if len(p) == 3 and p[2].isdigit() else 301 if len(p) == 2 else 0
    if code not in allowed:
        raise ValueError("x_rule")
    return code


def parse_waf(txt):
    p = txt.split(None, 1)
    if len(p) != 2 or p[0].lower() not in WAFACT:
        raise ValueError("x_rule")
    return {"action": p[0].lower(), "expression": p[1].strip(), "description": p[1].strip()[:100], "enabled": True}


def parse_rl(txt):
    p = txt.split(None, 3)
    if len(p) != 4 or not all(x.isdigit() and int(x) > 0 for x in p[:3]):
        raise ValueError("x_rule")
    n, period, timeout = (int(x) for x in p[:3])
    return {"action": "block", "expression": p[3].strip(), "description": f"{n} req / {period}s", "enabled": True,
            "ratelimit": {"characteristics": ["ip.src", "cf.colo.id"], "period": period,
                          "requests_per_period": n, "mitigation_timeout": timeout}}


def parse_redirect(txt):
    p = txt.split()
    if len(p) not in (2, 3):
        raise ValueError("x_rule")
    code = _code(p, (301, 302, 303, 307, 308))
    src, dst = re.sub(r"(?i)^https?://", "", p[0]), p[1]
    host, _, path = src.partition("/")
    if (not re.match(r"(?i)https?://[^\s\"\\]+$", dst) or '"' in src or "\\" in src
            or not re.fullmatch(r"(?i)([a-z0-9_]([a-z0-9\-_]*[a-z0-9])?\.)+[a-z0-9\-]{2,}", host)):
        raise ValueError("x_rule")
    path = path.rstrip("/")
    expr = f'(http.host eq "{host.lower()}"' + (f' and http.request.uri.path eq "/{path}"' if path else "") + ")"
    return {"action": "redirect", "expression": expr, "description": f"{src} → {dst}"[:200], "enabled": True,
            "action_parameters": {"from_value": {"status_code": code, "target_url": {"value": dst}, "preserve_query_string": True}}}


def parse_pagerule(txt):
    p = txt.split()
    if len(p) not in (2, 3) or not re.match(r"(?i)https?://\S+$", p[1]):
        raise ValueError("x_rule")
    return {"targets": [{"target": "url", "constraint": {"operator": "matches", "value": p[0]}}],
            "actions": [{"id": "forwarding_url", "value": {"url": p[1], "status_code": _code(p, (301, 302))}}], "status": "active"}


def parse_purge(txt):
    """Lines -> {'files': [...], 'prefixes': [...], 'hosts': [...]} (only the non-empty groups)."""
    out = {"files": [], "prefixes": [], "hosts": []}
    for line in txt.split()[:30]:
        if re.match(r"(?i)https?://\S+\.\S+", line): out["files"].append(line)
        elif re.fullmatch(r"(?i)([a-z0-9\-_]+\.)+[a-z0-9\-]{2,}", line): out["hosts"].append(line.lower())
        elif re.fullmatch(r"(?i)([a-z0-9\-_]+\.)+[a-z0-9\-]{2,}/\S*", line): out["prefixes"].append(line)
    out = {k: v for k, v in out.items() if v}
    if not out:
        raise ValueError("pc_bad")
    return out


# ───────────────────────── views ─────────────────────────
VIEWS, ACTS, WAITS = {}, {}, {}
LV1 = {"zones", "aids", "svc", "wk", "wk1", "pgs", "pg1", "tn", "tn1"}  # need a selected account
LV2 = {"zone", "dns", "dnst", "rec", "ssl", "sec", "tog", "fw", "zs", "tls", "cache", "hsts", "dsec", "an",
       "rl", "rs", "ru", "pr", "wr", "purge"}  # need a selected zone
ITEM = {"rec": "rec", "ru": "rule", "wk1": "wk", "pg1": "pg", "tn1": "tun", "adm1": "adm", "admc": "adm"}  # view -> state field
PARENT = {"rec": "dns", "ru": "rs", "wk1": "wk", "pg1": "pgs", "tn1": "tn", "adm1": "adm", "admc": "adm"}
OWNERV = {"adm", "adm1", "admc", "log"}


def nk(st, lvl, item=""):
    """Short fingerprint of (account, zone, item). Buttons carry it; a mismatch means the message is outdated."""
    s = f"{st.get('acc', '')}|{st.get('zone', '') if lvl > 1 else ''}|{item}"
    return format(zlib.crc32(s.encode()) & 0xffffff, "x")


def keyfor(st, v):
    if v == "ask": v = st.get("back")
    if v in ("cz", "cz1"): v = st.get("scr_v")
    if v == "cfm": v = (st.get("cfm") or {}).get("back")
    if v in LV1 or v in LV2:
        return nk(st, 2 if v in LV2 else 1, str(st.get(ITEM[v]) or "") if v in ITEM else "")
    return ""


def keys_now(st):
    items = [""] + [str(st.get(f) or "") for f in ("rec", "rule", "wk", "pg", "tun")]
    return {nk(st, lvl, i) for lvl in (1, 2) for i in items}


def V(*names):
    def deco(f):
        for n in names: VIEWS[n] = f
        return f
    return deco


def recline(i, r):
    px = (" " + e("cloud")) if r.get("proxied") else ""
    pr = f"{r['priority']} " if r.get("type") == "MX" and r.get("priority") is not None else ""
    return (f"<b>{i}.</b> <code>{r['type']}</code>  {esc(r['name'])}\n"
            f"      ↳ <code>{esc((pr + str(r.get('content', '')))[:60])}</code>{px}")


def pager(uid, p, tp, pre):
    row = []
    if p > 1: row.append(b(t(uid, "prev"), f"{pre}p:{p-1}"))
    if tp > 1: row.append(b(f"{p}/{tp}", "noop"))
    if p < tp: row.append(b(t(uid, "next"), f"{pre}n:{p+1}"))
    return row


def cferr(uid, j, title, back):
    """Screen shown when Cloudflare refused the request that fills a view."""
    return f"{title}\n\n❌ {esc(errtxt(j, uid))}", [bk(uid, back)]


@V("home")
async def v_home(uid, st):
    return t(uid, "welcome"), []


@V("help")
async def v_help(uid, st):
    return f"{e('help')} {t(uid, 'help_t')}\n\n<i>CF Control v{VERSION}</i>", [bk(uid, "set")]


@V("set")
async def v_set(uid, st):
    rows = [[b(t(uid, "adm"), "adm", "primary", "user")]] if isowner(uid) else []
    rows.append([b(t(uid, "lang"), "lang", "primary")])
    if not readonly(uid):
        rows += [[b(t(uid, "emo"), "emo", "primary", "bolt")],
                 [b(t(uid, "design") + (" ✅" if db.get("design") else ""), "design", "success" if db.get("design") else None, "edit")],
                 [b(t(uid, "czm"), "czm", "primary", "gear")]]
    if isowner(uid):
        on = (db.get("mon") or {}).get("on", True)
        rows.append([b(t(uid, "mon") + (" ✅" if on else " ▫️"), "mon", "success" if on else None, "bell"),
                     b(t(uid, "log"), "log", "primary", "log")])
    rows.append([b(t(uid, "help"), "help", None, "help")])
    return f"{e('gear')} <b>{t(uid, 'm_set')}</b>", rows


def roletxt(uid, i):
    p = perm(i); accs = p.get("accs")
    return (t(uid, "r_ro") if p.get("ro") else t(uid, "r_full")) + " · " + (t(uid, "a_all") if accs is None else f"{len(accs)}/{len(db['accounts'])}")


@V("adm")
async def v_adm(uid, st):
    extra = db.get("admins", [])
    txt = (f"{e('user')} <b>{t(uid, 'adm')}</b>\n\n"
           + "\n".join(f"{e('crown')} <code>{i}</code> · {t(uid, 'owner')}" for i in sorted(ADMINS))
           + ("\n" + "\n".join(f"{e('user')} <code>{i}</code> · {roletxt(uid, i)}" for i in extra) if extra else "")
           + f"\n\n<i>{t(uid, 'adm_note')}</i>")
    rows = [[b(str(i), f"am:{i}", "primary", "user")] for i in extra]
    rows.append([b(t(uid, "adm_add"), "ad", "success", "plus")])
    return txt, rows + [bk(uid, "set")]


@V("adm1")
async def v_adm1(uid, st):
    i = st["adm"]
    if i not in db.get("admins", []):
        raise Go("adm")
    ro = bool(perm(i).get("ro"))
    return (f"{e('user')} <code>{i}</code>\n{t(uid, 'role')}: <b>{roletxt(uid, i)}</b>",
            [[b(t(uid, "role") + ": " + (t(uid, "r_ro") if ro else t(uid, "r_full")), "amr", None if ro else "success", "eye" if ro else "key")],
             [b(t(uid, "a_accs"), "admc", "primary", "cloud")],
             [b(t(uid, "delete"), f"ax:{i}", "danger", "trash")], bk(uid, "adm")])


@V("admc")
async def v_admc(uid, st):
    i = st["adm"]; accs = perm(i).get("accs")
    rows = [[b(t(uid, "a_all") + (" ✅" if accs is None else " ▫️"), "amall", "success" if accs is None else None)]]
    rows += [[b(a["name"] + (" ✅" if accs is None or a["id"] in accs else " ▫️"), f"amt:{a['id']}",
                "success" if accs is not None and a["id"] in accs else None, "cloud")] for a in db["accounts"]]
    return f"{e('cloud')} <b>{t(uid, 'a_accs')}</b> · <code>{i}</code>", rows + [bk(uid, "adm1")]


@V("log")
async def v_log(uid, st):
    lines = []
    for raw in tail(AUDF, 15):
        try:
            r = json.loads(raw)
        except ValueError:
            continue
        where = " · ".join(x for x in (r.get("acc"), r.get("z")) if x)
        lines.append(f"{'✅' if r.get('ok') else '❌'} <code>{time.strftime('%m-%d %H:%M', time.localtime(r.get('t', 0)))}</code> "
                     f"<code>{r.get('u')}</code> <b>{esc(r.get('a'))}</b>"
                     + (f"\n      {esc(where)}" if where else "") + (f" — {esc(str(r.get('d'))[:80])}" if r.get("d") else ""))
    rows = [[b(t(uid, "log_x"), "logx", None, "export")]] if lines else []
    return f"{e('log')} <b>{t(uid, 'log')}</b>\n\n" + ("\n".join(lines) or t(uid, "log_none")), rows + [bk(uid, "set")]


@V("chk")
async def v_chk(uid, st):
    res = await asyncio.gather(*(ping(a) for a in myaccs(uid)))
    lines = [f"{e('green') if ok_ else e('red')} <b>{esc(n)}</b>\n      {esc(d)} · {ms}ms" for n, ok_, d, ms in res]
    return (f"{e('bolt')} <b>{t(uid, 'chk_title')}</b>\n\n" + ("\n".join(lines) or t(uid, "empty")),
            [[b(t(uid, "chk"), "chk", "primary", "bolt")], bk(uid, "acc")])


@V("cz")
async def v_cz(uid, st):
    rows = chunk([b(("📝 " if k == "txt" else "") + lbl, f"cz1:{n}", "primary" if k == "btn" else None)
                  for n, (bid, lbl, k) in enumerate(st["scr"])], 2)
    return f"🎨 <b>{t(uid, 'design')}</b>\n\n{t(uid, 'cz_hint')}", rows + [bk(uid, st.get("scr_v") or "set")]


@V("cz1")
async def v_cz1(uid, st):
    bid, lbl, k = st["scr"][st["sel"]]
    ov = (db.get("btn") or {}).get(bid, {})
    em = ov.get("uni") or ("—" if ov.get("emo") == "x" else ("premium …" + ov["emo"][-5:] if ov.get("emo") else "default"))
    txt = (f"🎨 <b>{esc(lbl)}</b>\n<code>{esc(bid)}</code>\n"
           + (f"{t(uid, 'c_style')}: {ov.get('style', 'default')}\n" if k == "btn" else "") + f"{t(uid, 'c_emoji')}: {esc(em)}")
    rows = []
    if k == "btn":
        rows.append([b(t(uid, "c_blue"), "cs:primary", "primary"), b(t(uid, "c_green"), "cs:success", "success"), b(t(uid, "c_red"), "cs:danger", "danger")])
        rows.append([b(t(uid, "c_def"), "cs:none")])
    rows.append([b(t(uid, "c_emo"), "ce", "primary", "edit"), b(t(uid, "c_none"), "cx", None, "trash")])
    rows.append([b(t(uid, "c_reset"), "cr", "danger")])
    return txt, rows + [bk(uid, "cz")]


@V("emo")
async def v_emo(uid, st):
    have = sum(1 for k in EMO if eid(k))
    return (f"{e('bolt')} <b>{t(uid, 'emo')}</b>  ({have}/{len(EMO)})\n\n{t(uid, 'emo_info')}\n\n"
            + "  ".join(f"{EMO[k][1]}{'✅' if eid(k) else '▫️'}" for k in EMO),
            [[b(t(uid, "emo_set"), "emoset", "success", "edit"), b(t(uid, "emo_test"), "emotest", "primary", "ok")],
             [b(t(uid, "emo_reset"), "emoreset", "danger", "trash")], bk(uid, "set")])


@V("ask")
async def v_ask(uid, st):
    return f"{e('edit')} {st.get('prompt', '')}", [bk(uid, st.get("back") or "acc")]


@V("cfm")
async def v_cfm(uid, st):
    f = st["cfm"]
    return f"{e('warn')} {f['text']}", [[b(t(uid, "yes_do"), f"y:{f['n']}", "danger", "ok"), b(t(uid, "cancel"), f["back"])]]


@V("addtok")
async def v_addtok(uid, st):
    return f"{e('plus')} {t(uid, 'addtok')}", [bk(uid, "acc")]


@V("acc")
async def v_acc(uid, st):
    accs, mg = myaccs(uid), canmanage(uid)
    rows = [[b(a["name"], f"a:{a['id']}", "primary", "cloud")] + ([b(t(uid, "delete"), f"x:{a['id']}", "danger", "trash")] if mg else [])
            for a in accs]
    if mg: rows.append([b(t(uid, "m_add"), "add", "success", "plus")])
    if accs: rows.append([b(t(uid, "chk"), "chk", "primary", "bolt")])
    return f"{e('cloud')} <b>{t(uid, 'accs')}</b>\n" + ("" if accs else t(uid, "empty")), rows


@V("zones")
async def v_zones(uid, st):
    p = st.setdefault("zpage", 1); q = st.get("zq")
    j = await C(uid, "GET", "/zones", params={"per_page": 10, "page": p, **({"name": "contains:" + q} if q else {})})
    zs = j.get("result") or []; info = j.get("result_info") or {}; tp = info.get("total_pages") or 1
    st.setdefault("zones", {}).update({x["id"]: x["name"] for x in zs})
    txt = (f"{e('globe')} <b>{t(uid, 'zones')}</b> ({info.get('total_count', len(zs))})"
           + (f"  {e('search')} <code>{esc(q)}</code>" if q else "") + "\n\n"
           + "\n".join(f"{e('pause') if x.get('paused') else e('green') if x.get('status') == 'active' else e('yellow')} <code>{esc(x['name'])}</code>" for x in zs))
    if not zs:
        txt += t(uid, "none") if j.get("success") else "❌ " + esc(errtxt(j, uid))
    rows = chunk([b(x["name"], f"z:{x['id']}", "primary", "globe") for x in zs], 2)
    pr = pager(uid, p, tp, "zg")
    if pr: rows.append(pr)
    rows.append([b(t(uid, "search"), "zq", None, "search")] + ([b(t(uid, "clear"), "zqc", None, "trash")] if q else []))
    rows.append([b(t(uid, "zadd"), "zadd", "success", "plus"), b(t(uid, "svc"), "svc", "primary", "puzzle")])
    rows.append([b(t(uid, "bulk"), "bk:a", None, "swap")])
    return txt, rows + [bk(uid, "home")]


@V("aids")
async def v_aids(uid, st):
    lst = st.get("aidl") or []
    if not lst:
        raise Go("zones")
    return f"{e('cloud')} {t(uid, 'aids')}", [[b(n or i, f"ai:{k}", "primary", "cloud")] for k, (i, n) in enumerate(lst)] + [bk(uid, "zones")]


@V("zone")
async def v_zone(uid, st):
    z = st["zone"]
    zj, sj = await asyncio.gather(C(uid, "GET", f"/zones/{z}"), C(uid, "GET", f"/zones/{z}/settings"))
    if not zj.get("success"):
        return cferr(uid, zj, f"{e('globe')} <b>{esc(zname(st))}</b>", "zones")
    zi = zj.get("result") or {}; st.setdefault("zones", {})[z] = zi.get("name") or zname(st)
    s = {x["id"]: x.get("value") for x in sj.get("result") or []}
    ua = s.get("security_level") == "under_attack"; dev = s.get("development_mode") == "on"
    paused, pending = bool(zi.get("paused")), zi.get("status") == "pending"
    txt = (f"{e('globe')} <b>{esc(zname(st))}</b>\n<blockquote>"
           f"{e('green') if zi.get('status') == 'active' else e('yellow')} {esc(zi.get('status', '?'))} · {esc((zi.get('plan') or {}).get('name', ''))}\n"
           + (f"{e('pause')} {t(uid, 'paused')}\n" if paused else "")
           + f"{e('lock')} SSL: <code>{esc(s.get('ssl', '?'))}</code>\n"
           f"{e('shield')} Security: <code>{esc(s.get('security_level', '?'))}</code>\n"
           f"{e('dev')} Dev mode: {'ON' if dev else 'OFF'}\n"
           f"{e('tag')} NS: <code>{esc(', '.join(zi.get('name_servers') or []))}</code></blockquote>"
           + (f"\n{e('warn')} {t(uid, 'pending_hint')}" if pending else ""))
    rows = [
        [b(t(uid, "dns"), "dns", "primary", "dns"), b(t(uid, "ssl"), "ssl", "primary", "lock")],
        [b(t(uid, "sec"), "sec", "primary", "shield"), b(t(uid, "tog"), "tog", "primary", "bolt")],
        [b(t(uid, "ua"), "ua", "danger" if ua else None, "fire"), b(t(uid, "dev"), "dev", "success" if dev else None, "dev")],
        [b(t(uid, "fw"), "fw", "primary", "ban"), b(t(uid, "rl"), "rl", "primary", "shield")],
        [b(t(uid, "an"), "an", "primary", "chart"), b(t(uid, "zs"), "zs", "primary", "gear")],
        [b(t(uid, "export"), "ex", None, "export"), b(t(uid, "imp"), "im", None, "import")],
        [b(t(uid, "purge"), "pc", "danger", "trash"),
         b(t(uid, "resume" if paused else "pause"), "zp", "success" if paused else None, "play" if paused else "pause")]]
    if pending: rows.append([b(t(uid, "zac"), "zac", "primary", "bolt")])
    rows.append([b(t(uid, "zdel"), "zdel", "danger", "ban")])
    return txt, rows + [bk(uid, "zones")]


@V("dns")
async def v_dns(uid, st):
    z, p, q, ty = st["zone"], st.setdefault("page", 1), st.get("dnsq"), st.get("dty")
    j = await C(uid, "GET", f"/zones/{z}/dns_records", params={
        "per_page": 8, "page": p, "order": "type", **({"search": q} if q else {}), **({"type": ty} if ty else {})})
    rs = j.get("result") or []; tp = (j.get("result_info") or {}).get("total_pages") or 1
    flt = " ".join(x for x in (f"<code>{esc(ty)}</code>" if ty else "", f"«{esc(q)}»" if q else "") if x)
    txt = (f"{e('dns')} <b>{t(uid, 'dns')}</b> · {esc(zname(st))}   ({p}/{tp})" + (f"\n{e('search')} {flt}" if flt else "") + "\n\n"
           + ("\n".join(recline(i, r) for i, r in enumerate(rs, 1)) or (t(uid, "none") if j.get("success") else "❌ " + esc(errtxt(j, uid)))))
    rows = chunk([b(str(i), f"r:{r['id']}", "primary") for i, r in enumerate(rs, 1)], 4)
    nav = pager(uid, p, tp, "dg")
    if nav: rows.append(nav)
    rows.append([b(t(uid, "search"), "ds", None, "search"), b(t(uid, "ftype"), "dnst", None, "tag")]
                + ([b(t(uid, "clear"), "dc", None, "trash")] if flt else []))
    rows.append([b(t(uid, "new"), "new", "success", "plus"), b(t(uid, "bulk"), "bk:z", None, "swap")])
    return txt, rows + [bk(uid, "zone")]


@V("dnst")
async def v_dnst(uid, st):
    cur = st.get("dty")
    rows = chunk([b(t(uid, "all"), "dty:", "success" if not cur else None)]
                 + [b(x, f"dty:{x}", "success" if x == cur else None) for x in DTYPES], 3)
    return f"{e('tag')} <b>{t(uid, 'ftype')}</b> · {esc(zname(st))}", rows + [bk(uid, "dns")]


@V("rec")
async def v_rec(uid, st):
    j = await C(uid, "GET", f"/zones/{st['zone']}/dns_records/{st['rec']}")
    r = j.get("result")
    if not r:
        return cferr(uid, j, f"{e('dns')} <b>{t(uid, 'dns')}</b>", "dns")
    st["rtype"] = r.get("type")
    txt = (f"{e('dns')} <b>{esc(r.get('type'))}</b>\n<blockquote>"
           f"{e('tag')} <code>{esc(r.get('name', ''))}</code>\n"
           f"{e('target')} <code>{esc(str(r.get('content', ''))[:700])}</code>\n"
           + (f"↕️ Priority: {r['priority']}\n" if r.get("priority") is not None and r.get("type") == "MX" else "")
           + f"{e('time')} TTL: {'auto' if r.get('ttl') == 1 else r.get('ttl')}\n{e('cloud')} Proxy: {'ON' if r.get('proxied') else 'OFF'}"
           + (f"\n💬 {esc(str(r['comment'])[:200])}" if r.get("comment") else "") + "</blockquote>")
    row2 = [b(t(uid, "e_ttl"), "ed:ttl", None, "edit")]
    if r.get("type") in ("A", "AAAA", "CNAME"):
        row2.append(b(t(uid, "proxy"), "px", "success" if r.get("proxied") else None, "cloud"))
    if r.get("type") == "MX":
        row2.append(b(t(uid, "e_priority"), "ed:priority", None, "edit"))
    return txt, [[b(t(uid, "e_content"), "ed:content", "primary", "edit"), b(t(uid, "e_name"), "ed:name", "primary", "edit")],
                 row2, [b(t(uid, "delete"), "dq", "danger", "trash")], bk(uid, "dns")]


async def choice(uid, st, setting, values, act, title, icon, back):
    """Generic 'pick one value' screen for a zone setting."""
    j = await C(uid, "GET", f"/zones/{st['zone']}/settings/{setting}")
    head = f"{e(icon)} <b>{title}</b> · {esc(zname(st))}"
    if not j.get("success"):
        return cferr(uid, j, head, back)
    cur = (j.get("result") or {}).get("value")
    danger = lambda m: m == "under_attack"
    rows = [[b(m, f"{act}:{m}", ("danger" if danger(m) else "success") if m == cur else None, "ok" if m == cur else icon)] for m in values]
    return head, rows + [bk(uid, back)]


@V("ssl")
async def v_ssl(uid, st):
    return await choice(uid, st, "ssl", SSLM, "ss", t(uid, "ssl"), "lock", "zone")


@V("sec")
async def v_sec(uid, st):
    return await choice(uid, st, "security_level", LEVELS, "sc", t(uid, "sec"), "shield", "zone")


@V("tls")
async def v_tls(uid, st):
    return await choice(uid, st, "min_tls_version", TLSV, "tl", t(uid, "tls"), "lock", "zs")


@V("cache")
async def v_cache(uid, st):
    return await choice(uid, st, "cache_level", CACHEL, "cl", t(uid, "cache"), "bolt", "zs")


@V("tog")
async def v_tog(uid, st):
    j = await C(uid, "GET", f"/zones/{st['zone']}/settings")
    head = f"{e('bolt')} <b>{t(uid, 'tog')}</b> · {esc(zname(st))}"
    if not j.get("success"):
        return cferr(uid, j, head, "zone")
    s = {x["id"]: x.get("value") for x in j.get("result") or []}
    rows = chunk([b(n + (" ✅" if ison(s[k]) else " ▫️"), f"tg:{k}", "success" if ison(s[k]) else None) for k, n in TOGGLES if k in s], 2)
    return head, rows + [bk(uid, "zone")]


@V("zs")
async def v_zs(uid, st):
    z = st["zone"]
    sj, dj = await asyncio.gather(C(uid, "GET", f"/zones/{z}/settings"), C(uid, "GET", f"/zones/{z}/dnssec"))
    s = {x["id"]: x.get("value") for x in sj.get("result") or []}
    hs = ((s.get("security_header") or {}).get("strict_transport_security") or {}).get("enabled")
    txt = (f"{e('gear')} <b>{t(uid, 'zs')}</b> · {esc(zname(st))}\n<blockquote>"
           f"{e('lock')} {t(uid, 'tls')}: <code>{esc(s.get('min_tls_version', '?'))}</code>\n"
           f"{e('bolt')} {t(uid, 'cache')}: <code>{esc(s.get('cache_level', '?'))}</code>\n"
           f"{e('shield')} HSTS: {t(uid, 'on') if hs else t(uid, 'off')}\n"
           f"{e('key')} DNSSEC: <code>{esc((dj.get('result') or {}).get('status', '?'))}</code></blockquote>")
    return txt, [[b(t(uid, "tls"), "tls", "primary", "lock"), b(t(uid, "cache"), "cache", "primary", "bolt")],
                 [b(t(uid, "hsts"), "hsts", "primary", "shield"), b(t(uid, "dsec"), "dsec", "primary", "key")], bk(uid, "zone")]


async def hsts_get(uid, z):
    j = await C(uid, "GET", f"/zones/{z}/settings/security_header")
    return j, dict(((j.get("result") or {}).get("value") or {}).get("strict_transport_security") or {})


@V("hsts")
async def v_hsts(uid, st):
    j, h = await hsts_get(uid, st["zone"])
    head = f"{e('shield')} <b>HSTS</b> · {esc(zname(st))}"
    if not j.get("success"):
        return cferr(uid, j, head, "zs")
    on, age = bool(h.get("enabled")), int(h.get("max_age") or 0)
    yn = lambda v: "✅" if v else "▫️"
    txt = (f"{head}\n<blockquote>{t(uid, 'on') if on else t(uid, 'off')}\nmax-age: <code>{age}</code>\n"
           f"includeSubDomains: {yn(h.get('include_subdomains'))}\npreload: {yn(h.get('preload'))}\nnosniff: {yn(h.get('nosniff'))}</blockquote>")
    return txt, [[b(t(uid, "disable" if on else "enable"), "hs:en", "danger" if on else "success")],
                 [b(t(uid, "hs_6m"), "hs:a:15552000", "success" if age == 15552000 else None),
                  b(t(uid, "hs_1y"), "hs:a:31536000", "success" if age == 31536000 else None)],
                 [b("includeSubDomains " + yn(h.get("include_subdomains")), "hs:sub"), b("preload " + yn(h.get("preload")), "hs:pre")],
                 [b("nosniff " + yn(h.get("nosniff")), "hs:ns")], bk(uid, "zs")]


@V("dsec")
async def v_dsec(uid, st):
    j = await C(uid, "GET", f"/zones/{st['zone']}/dnssec")
    head = f"{e('key')} <b>DNSSEC</b> · {esc(zname(st))}"
    if not j.get("success"):
        return cferr(uid, j, head, "zs")
    d = j.get("result") or {}; status = d.get("status") or "disabled"
    txt = f"{head}\n<blockquote>{e('green') if status == 'active' else e('yellow') if status == 'pending' else e('red')} <code>{esc(status)}</code></blockquote>"
    if status in ("pending", "active") and d.get("ds"):
        txt += (f"\n{t(uid, 'ds_hint')}\n<code>{esc(d['ds'])}</code>\n\nKey tag: <code>{esc(d.get('key_tag'))}</code> · "
                f"Algorithm: <code>{esc(d.get('algorithm'))}</code> · Digest type: <code>{esc(d.get('digest_type'))}</code>\n"
                f"Digest: <code>{esc(d.get('digest'))}</code>")
    off = status in ("disabled", "pending-disabled", "error")
    return txt, [[b(t(uid, "enable" if off else "disable"), "dz:1" if off else "dz:0", "success" if off else "danger")], bk(uid, "zs")]


@V("fw")
async def v_fw(uid, st):
    p = st.setdefault("fpage", 1)
    j = await C(uid, "GET", f"/zones/{st['zone']}/firewall/access_rules/rules", params={"per_page": 10, "page": p})
    rs = j.get("result") or []; tp = (j.get("result_info") or {}).get("total_pages") or 1
    st["fwl"] = {r["id"]: r["configuration"]["value"] for r in rs}
    icon = lambda m: e("ban") if m == "block" else e("ok") if m == "whitelist" else e("puzzle")
    txt = f"{e('ban')} <b>{t(uid, 'fw')}</b> · {esc(zname(st))}" + (f"   ({p}/{tp})" if tp > 1 else "") + "\n\n" + ("\n".join(
        f"<b>{i}.</b> {icon(r['mode'])} <code>{esc(r['configuration']['value'])}</code> <i>{esc(r.get('notes') or '')}</i>"
        for i, r in enumerate(rs, 1)) or (t(uid, "none") if j.get("success") else "❌ " + esc(errtxt(j, uid))))
    rows = chunk([b(f"🗑 {i}", f"fd:{r['id']}", "danger") for i, r in enumerate(rs, 1)], 5)
    nav = pager(uid, p, tp, "fg")
    if nav: rows.append(nav)
    rows.append([b(t(uid, "block"), "fn", "success", "plus")])
    return txt, rows + [bk(uid, "zone")]


GQL = ("query($z: string) { viewer { zones(filter: {zoneTag: $z}) { g: %s(limit: %d, orderBy: [%s_ASC], filter: {%s}) { "
       "dimensions { t: %s } sum { requests cachedRequests bytes cachedBytes threats pageViews countryMap { clientCountryName requests } } "
       "uniq { uniques } } } } }")


@V("an")
async def v_an(uid, st):
    days = st.get("anp", 7); now = datetime.now(timezone.utc)
    if days == 1:
        a0, a1 = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H:00:00Z"), now.strftime("%Y-%m-%dT%H:%M:%SZ")
        q = GQL % ("httpRequests1hGroups", 30, "datetime", f'datetime_geq: "{a0}", datetime_lt: "{a1}"', "datetime")
    else:
        a0, a1 = (now - timedelta(days=days - 1)).strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d")
        q = GQL % ("httpRequests1dGroups", 40, "date", f'date_geq: "{a0}", date_leq: "{a1}"', "date")
    j = await C(uid, "POST", "/graphql", json={"query": q, "variables": {"z": st["zone"]}})
    label = {1: "an_24", 7: "an_7", 30: "an_30"}[days]
    head = f"{e('chart')} <b>{t(uid, 'an')}</b> · {esc(zname(st))} · {t(uid, label)}"
    rows = [[b(t(uid, k), f"anp:{d}", "success" if d == days else None) for d, k in ((1, "an_24"), (7, "an_7"), (30, "an_30"))], bk(uid, "zone")]
    if not j.get("success"):
        return f"{head}\n\n❌ {esc(errtxt(j, uid))}", rows
    zl = ((j.get("data") or {}).get("viewer") or {}).get("zones") or [{}]
    g = zl[0].get("g") or []
    if not g:
        return f"{head}\n\n{t(uid, 'an_none')}", rows
    tot = lambda k: sum((x.get("sum") or {}).get(k) or 0 for x in g)
    req, creq, by, cby = tot("requests"), tot("cachedRequests"), tot("bytes"), tot("cachedBytes")
    pct = lambda a, c: f"{100 * a / c:.0f}%" if c else "0%"
    cc = {}
    for x in g:
        for m in (x.get("sum") or {}).get("countryMap") or []:
            cc[m.get("clientCountryName")] = cc.get(m.get("clientCountryName"), 0) + (m.get("requests") or 0)
    top = sorted(cc.items(), key=lambda kv: -kv[1])[:5]
    txt = (f"{head}\n<blockquote>{t(uid, 'an_req')}: <b>{hn(req)}</b> ({t(uid, 'an_cached')} {pct(creq, req)})\n"
           f"{t(uid, 'an_bw')}: <b>{hb(by)}</b> ({t(uid, 'an_cached')} {pct(cby, by)})\n"
           f"{t(uid, 'an_pv')}: <b>{hn(tot('pageViews'))}</b>\n"
           f"{t(uid, 'an_uniq')}: <b>{hn(max((x.get('uniq') or {}).get('uniques') or 0 for x in g))}</b>\n"
           f"{t(uid, 'an_thr')}: <b>{hn(tot('threats'))}</b></blockquote>\n"
           f"<code>{spark([(x.get('sum') or {}).get('requests') or 0 for x in g])}</code>"
           + (f"\n\n{t(uid, 'an_top')}: " + " · ".join(f"{esc(k)} {pct(v, req)}" for k, v in top) if top else ""))
    return txt, rows


@V("purge")
async def v_purge(uid, st):
    return (f"{e('trash')} <b>{t(uid, 'purge')}</b> · {esc(zname(st))}",
            [[b(t(uid, "pc_url"), "pcu", "primary", "link")], [b(t(uid, "pc_all"), "pca", "danger", "trash")], bk(uid, "zone")])


@V("rl")
async def v_rl(uid, st):
    return (f"{e('shield')} <b>{t(uid, 'rl')}</b> · {esc(zname(st))}",
            [[b(t(uid, "rs_w"), "rs:w", "primary", "shield"), b(t(uid, "rs_r"), "rs:r", "primary", "time")],
             [b(t(uid, "rs_d"), "rs:d", "primary", "link"), b(t(uid, "pr"), "pr", "primary", "tag")],
             [b(t(uid, "wr"), "wr", "primary", "box")], bk(uid, "zone")])


def setrules(st, ruleset):
    st["rsid"] = (ruleset or {}).get("id")
    st["rules"] = {r["id"]: r for r in (ruleset or {}).get("rules") or [] if r.get("id")}


@V("rs")
async def v_rs(uid, st):
    ph = st.get("ph") if st.get("ph") in PH else "w"
    j = await C(uid, "GET", f"/zones/{st['zone']}/rulesets/phases/{PH[ph]}/entrypoint")
    head = f"{e('shield')} <b>{t(uid, 'rs_' + ph)}</b> · {esc(zname(st))}"
    if j.get("_status") == 404:  # no rule was ever created in this phase
        setrules(st, None)
    elif not j.get("success"):
        return cferr(uid, j, head, "rl")
    else:
        setrules(st, j.get("result"))
    rules = list(st["rules"].values())[:20]
    txt = head + "\n\n" + ("\n".join(
        f"<b>{i}.</b> {e('green') if r.get('enabled', True) else e('red')} <code>{esc(r.get('action'))}</code> {esc((r.get('description') or r.get('expression') or '')[:70])}"
        for i, r in enumerate(rules, 1)) or t(uid, "none"))
    rows = chunk([b(str(i), f"ru:{r['id']}", "primary") for i, r in enumerate(rules, 1)], 5)
    rows.append([b(t(uid, "rule_new"), "rn", "success", "plus")])
    return txt, rows + [bk(uid, "rl")]


@V("ru")
async def v_ru(uid, st):
    r = (st.get("rules") or {}).get(st["rule"])
    if not r:
        raise Go("rs")
    on = r.get("enabled", True); rl = r.get("ratelimit") or {}
    to = ((((r.get("action_parameters") or {}).get("from_value") or {}).get("target_url")) or {})
    txt = (f"{e('shield')} <b>{esc(r.get('description') or r['id'])}</b>\n<blockquote>"
           f"{e('green') if on else e('red')} {t(uid, 'on') if on else t(uid, 'off')} · <code>{esc(r.get('action'))}</code>\n"
           + (f"{e('time')} {rl.get('requests_per_period')} req / {rl.get('period')}s → {rl.get('mitigation_timeout')}s\n" if rl else "")
           + (f"{e('link')} <code>{esc(to.get('value') or to.get('expression'))}</code>\n" if to else "")
           + f"</blockquote>\n<code>{esc(str(r.get('expression', ''))[:800])}</code>")
    return txt, [[b(t(uid, "rule_toggle"), "rt", None if on else "success", "bolt")], [b(t(uid, "delete"), "rd", "danger", "trash")], bk(uid, "rs")]


@V("pr")
async def v_pr(uid, st):
    j = await C(uid, "GET", f"/zones/{st['zone']}/pagerules")
    head = f"{e('tag')} <b>{t(uid, 'pr')}</b> · {esc(zname(st))}"
    if not j.get("success"):
        return cferr(uid, j, head, "rl")
    rs = (j.get("result") or [])[:12]; st["prl"] = {r["id"]: r for r in rs}

    def line(i, r):
        url = ((r.get("targets") or [{}])[0].get("constraint") or {}).get("value", "")
        acts = []
        for a in r.get("actions") or []:
            v = a.get("value")
            acts.append(f"→ {v.get('url')} ({v.get('status_code')})" if a.get("id") == "forwarding_url" and isinstance(v, dict) else str(a.get("id")))
        return f"<b>{i}.</b> {e('green') if r.get('status') == 'active' else e('red')} <code>{esc(url)}</code>\n      {esc(', '.join(acts)[:120])}"

    txt = head + "\n\n" + ("\n".join(line(i, r) for i, r in enumerate(rs, 1)) or t(uid, "none"))
    rows = chunk([x for i, r in enumerate(rs, 1) for x in (b(f"⏯ {i}", f"prt:{r['id']}"), b(f"🗑 {i}", f"prd:{r['id']}", "danger"))], 4)
    rows.append([b(t(uid, "rule_new"), "prn", "success", "plus")])
    return txt, rows + [bk(uid, "rl")]


@V("wr")
async def v_wr(uid, st):
    j = await C(uid, "GET", f"/zones/{st['zone']}/workers/routes")
    head = f"{e('box')} <b>{t(uid, 'wr')}</b> · {esc(zname(st))}"
    if not j.get("success"):
        return cferr(uid, j, head, "rl")
    rs = (j.get("result") or [])[:25]; st["wrl"] = {r["id"]: r.get("pattern", "") for r in rs}
    txt = head + "\n\n" + ("\n".join(f"<b>{i}.</b> <code>{esc(r.get('pattern'))}</code> → {esc(r.get('script') or '—')}" for i, r in enumerate(rs, 1)) or t(uid, "none"))
    rows = chunk([b(f"🗑 {i}", f"wrd:{r['id']}", "danger") for i, r in enumerate(rs, 1)], 5)
    rows.append([b(t(uid, "rule_new"), "wrn", "success", "plus")])
    return txt, rows + [bk(uid, "rl")]


def aid_of(st):
    if not st.get("aid"):
        raise Go("zones")
    return st["aid"]


@V("svc")
async def v_svc(uid, st):
    aid_of(st)
    rows = [[b(t(uid, "wk"), "wk", "primary", "box"), b(t(uid, "pgs"), "pgs", "primary", "globe")], [b(t(uid, "tn"), "tn", "primary", "link")]]
    if len(st.get("aidl") or []) > 1: rows.append([b(t(uid, "aisw"), "aisw", None, "swap")])
    return f"{e('puzzle')} <b>{t(uid, 'svc')}</b>", rows + [bk(uid, "zones")]


@V("wk")
async def v_wk(uid, st):
    j = await C(uid, "GET", f"/accounts/{aid_of(st)}/workers/scripts")
    head = f"{e('box')} <b>{t(uid, 'wk')}</b>"
    if not j.get("success"):
        return cferr(uid, j, head, "svc")
    ws = (j.get("result") or [])[:30]; st["wkl"] = ws
    txt = head + f" ({len(ws)})\n\n" + ("\n".join(f"<b>{i}.</b> <code>{esc(w.get('id'))}</code> · {dshort(w.get('modified_on'))}" for i, w in enumerate(ws, 1)) or t(uid, "none"))
    return txt, chunk([b(str(i), f"wk1:{i - 1}", "primary") for i in range(1, len(ws) + 1)], 5) + [bk(uid, "svc")]


@V("wk1")
async def v_wk1(uid, st):
    w = next((x for x in st.get("wkl") or [] if x.get("id") == st["wk"]), None)
    if not w:
        raise Go("wk")
    routes = [str(r.get("pattern")) for r in w.get("routes") or [] if isinstance(r, dict)]
    txt = (f"{e('box')} <b>{esc(w.get('id'))}</b>\n<blockquote>Created: {dshort(w.get('created_on'))}\nModified: {dshort(w.get('modified_on'))}\n"
           f"Handlers: {esc(', '.join(w.get('handlers') or []) or '—')}\nUsage model: {esc(w.get('usage_model') or '—')}"
           + ("\nRoutes: " + esc(", ".join(routes)[:300]) if routes else "") + "</blockquote>")
    return txt, [[b(t(uid, "delete"), "wkx", "danger", "trash")], bk(uid, "wk")]


stage = lambda d: ((d or {}).get("latest_stage") or {})
sticon = lambda s: e("green") if s == "success" else e("red") if s in ("failure", "canceled") else e("yellow")


@V("pgs")
async def v_pgs(uid, st):
    j = await C(uid, "GET", f"/accounts/{aid_of(st)}/pages/projects")
    head = f"{e('globe')} <b>{t(uid, 'pgs')}</b>"
    if not j.get("success"):
        return cferr(uid, j, head, "svc")
    ps = (j.get("result") or [])[:30]; st["pgl"] = ps
    txt = head + f" ({len(ps)})\n\n" + ("\n".join(
        f"<b>{i}.</b> {sticon(stage(p.get('latest_deployment')).get('status'))} <code>{esc(p.get('name'))}</code> · {esc(p.get('subdomain') or '')}"
        for i, p in enumerate(ps, 1)) or t(uid, "none"))
    return txt, chunk([b(str(i), f"pg1:{i - 1}", "primary") for i in range(1, len(ps) + 1)], 5) + [bk(uid, "svc")]


@V("pg1")
async def v_pg1(uid, st):
    p = next((x for x in st.get("pgl") or [] if x.get("name") == st["pg"]), None)
    if not p:
        raise Go("pgs")
    j = await C(uid, "GET", f"/accounts/{aid_of(st)}/pages/projects/{quote(p['name'], safe='')}/deployments", params={"per_page": 5})
    ds = (j.get("result") or [])[:5]; st["pgd"] = ds[0]["id"] if ds else None
    txt = (f"{e('globe')} <b>{esc(p.get('name'))}</b>\n<blockquote>{esc(p.get('subdomain') or '')}\n"
           f"Domains: {esc(', '.join(p.get('domains') or []) or '—')}\nBranch: <code>{esc(p.get('production_branch') or '—')}</code></blockquote>\n"
           + ("\n".join(f"{sticon(stage(d).get('status'))} {dshort(d.get('created_on'))} · {esc(d.get('environment'))} · {esc(stage(d).get('name'))}: {esc(stage(d).get('status'))}"
                        for d in ds) or (t(uid, "none") if j.get("success") else "❌ " + esc(errtxt(j, uid)))))
    return txt, ([[b(t(uid, "pgr"), "pgr", "primary", "swap")]] if ds else []) + [bk(uid, "pgs")]


tnicon = lambda s: e("green") if s == "healthy" else e("yellow") if s == "degraded" else e("red")


@V("tn")
async def v_tn(uid, st):
    j = await C(uid, "GET", f"/accounts/{aid_of(st)}/cfd_tunnel", params={"is_deleted": "false", "per_page": 30})
    head = f"{e('link')} <b>{t(uid, 'tn')}</b>"
    if not j.get("success"):
        return cferr(uid, j, head, "svc")
    ts = (j.get("result") or [])[:30]; st["tnl"] = ts
    txt = head + f" ({len(ts)})\n\n" + ("\n".join(
        f"<b>{i}.</b> {tnicon(x.get('status'))} <code>{esc(x.get('name'))}</code> · {esc(x.get('status'))} · {len(x.get('connections') or [])} {t(uid, 'conns')}"
        for i, x in enumerate(ts, 1)) or t(uid, "none"))
    return txt, chunk([b(str(i), f"tn1:{i - 1}", "primary") for i in range(1, len(ts) + 1)], 5) + [bk(uid, "svc")]


@V("tn1")
async def v_tn1(uid, st):
    x = next((y for y in st.get("tnl") or [] if y.get("id") == st["tun"]), None)
    if not x:
        raise Go("tn")
    conns = x.get("connections") or []
    txt = (f"{e('link')} <b>{esc(x.get('name'))}</b>\n<blockquote>{tnicon(x.get('status'))} {esc(x.get('status'))}\nID: <code>{esc(x.get('id'))}</code>\n"
           f"Created: {dshort(x.get('created_at'))}</blockquote>\n<b>{t(uid, 'conns')}</b> ({len(conns)})\n"
           + ("\n".join(f"• {esc(c.get('colo_name'))} · <code>{esc(c.get('origin_ip'))}</code> · {esc(c.get('client_version'))}" for c in conns[:8]) or t(uid, "none")))
    return txt, [bk(uid, "tn")]


async def view(uid, v):
    """Pick the right screen for the user's state and build it."""
    st = S.setdefault(uid, {}); c = cx()
    for _ in range(4):
        if v in LV1 | LV2 and (not getacc(st.get("acc")) or not canacc(uid, st["acc"])):
            st.pop("acc", None); st.pop("zone", None); v = "acc"
        if v in LV2 and not st.get("zone"): v = "zones"
        if v in ("cz", "cz1") and not st.get("scr"): v = "set"
        if v == "cz1" and (st.get("sel") is None or st["sel"] >= len(st["scr"])): v = "cz"
        if v in OWNERV and not isowner(uid): v = "set"
        if v in ITEM and not st.get(ITEM[v]): v = PARENT[v]
        if v == "cfm" and not st.get("cfm"): v = here(st)
        if v not in VIEWS: v = "acc"
        c.cur = v; c.buf.clear(); c.key = keyfor(st, v)
        try:
            text, rows = await VIEWS[v](uid, st)
            return text, kb(rows)
        except Go as g:
            v = g.args[0]
    raise Stop("gone")


def uniq(buf):
    seen, out = set(), []
    for bid, lbl, k in buf:
        if bid not in seen:
            seen.add(bid); out.append((bid, lbl, k))
    return out


async def render(uid, cid, mid, v):
    text, markup = await view(uid, v); c = cx(); st = S[uid]
    if c.cur != "home" and not any(bt.get("callback_data", "").partition("|")[0] == "home" for row in markup["inline_keyboard"] for bt in row):
        markup["inline_keyboard"].append([b(t(uid, "home"), "home", "primary", "cloud")])
    if db.get("design") and not readonly(uid) and c.cur not in ("cz", "cz1", "ask", "cfm"):
        st["scr"] = uniq(c.buf); st["scr_v"] = c.cur; st["sel"] = None
        markup["inline_keyboard"].append([{"text": "🎨 " + t(uid, "cz_btn"), "callback_data": "cz", "style": "primary"}])
    await show(cid, mid, text, markup)


async def remenu(cid, uid):
    await send_menu(cid, uid, "🎨 ✅")


# ───────────────────────── actions (button taps) ─────────────────────────
def A(*names, w=False, own=False, mg=False, lv=0):
    """Register a callback action. w: changes something (blocked for read-only admins) · own: owner only ·
    mg: needs account-management rights · lv: 1 needs a selected account, 2 a selected zone."""
    def deco(f):
        for n in names: ACTS[n] = (f, w, own, mg, lv)
        return f
    return deco


def W(name, w=True, own=False, mg=False):
    """Register a handler for a text the bot is waiting for."""
    def deco(f):
        WAITS[name] = (f, w, own, mg)
        return f
    return deco


def ask(c, wait, prompt, back, **kw):
    c.st.update(wait=wait, prompt=prompt, back=back, **kw)
    return "ask"


def confirm(c, text, run, back):
    """Show a yes/no screen; `run` only executes when this exact confirmation is accepted."""
    c.st["cfm"] = {"n": secrets.token_hex(3), "text": text, "run": run, "back": back, "t": time.time()}
    return "cfm"


def done(c, j, act, detail="", zone=True):
    """Record the result of a change and return the short notice for the user."""
    ok = bool(j.get("success"))
    audit(c.uid, act, (getacc(c.st.get("acc")) or {}).get("name", ""), zname(c.st) if zone else "", detail, ok)
    return t(c.uid, "done") if ok else "❌ " + errtxt(j, c.uid)


def retry(c, key, *a):
    """Reject the text but keep waiting, so the user can simply send it again."""
    c.st["wait"] = c.w
    return "❌ " + t(c.uid, key).format(*a), None


setz = lambda c, k, val: C(c.uid, "PATCH", f"/zones/{c.z}/settings/{k}", json={"value": val})
getz = lambda c, k: C(c.uid, "GET", f"/zones/{c.z}/settings/{k}")


@A("home", "set", "acc", "emo", "cz", "help", "chk")
@A("adm", "log", "adm1", "admc", own=True)
@A("zones", lv=1)
@A("zone", "ssl", "sec", "tog", "fw", "rec", "zs", "tls", "cache", "hsts", "dsec", "an", "rl", "pr", "wr", "purge", "dnst", lv=2)
@A("wk", "pgs", "tn", lv=1)
async def a_nav(c):
    return c.a


@A("pc", lv=2)
async def a_pc(c):
    return "purge"


@A("y")
async def a_y(c):
    f = c.st.pop("cfm", None)
    if not f or f["n"] != c.x or time.time() - f["t"] > 300:
        return t(c.uid, "expired"), here(c.st)
    return await f["run"]()


# ── settings, design, admins
@A("lang")
async def a_lang(c):
    db["lang"][str(c.uid)] = "en" if lang(c.uid) == "fa" else "fa"; save()
    await send_menu(c.cid, c.uid, t(c.uid, "welcome"))
    return "set"


@A("emoset", w=True)
async def a_emoset(c):
    return ask(c, "emo", t(c.uid, "emo_ask") + "\n\n" + " ".join(EMO[k][1] for k in EMO), "emo")


@A("emotest", w=True)
async def a_emotest(c):
    await tg("sendMessage", chat_id=c.cid, text=await probe(c.cid))
    return "emo"


@A("emoreset", w=True)
async def a_emoreset(c):
    db["emo"] = {}; save(); OK.update(text=True, btn=True)
    return "emo"


@A("design", w=True)
async def a_design(c):
    db["design"] = not db.get("design"); save()
    return "set"


@A("czm", w=True)
async def a_czm(c):
    c.st["scr"] = [(f"menu.{k}", t(c.uid, k), "btn") for k in ("m_acc", "m_zone", "m_add", "m_set")]; c.st["scr_v"] = "set"
    return "cz"


@A("cz1", w=True)
async def a_cz1(c):
    c.st["sel"] = int(c.x)
    return "cz1"


@A("cs", "cx", "cr", w=True)
async def a_cstyle(c):
    bid = c.st["scr"][c.st["sel"]][0]
    if c.a == "cr":
        (db.get("btn") or {}).pop(bid, None)
    else:
        o = db.setdefault("btn", {}).setdefault(bid, {})
        if c.a == "cs" and c.x in ("primary", "success", "danger", "none"): o["style"] = c.x
        elif c.a == "cx": o.pop("uni", None); o["emo"] = "x"
    save()
    if bid.startswith("menu."): await remenu(c.cid, c.uid)
    return "cz1"


@A("ce", w=True)
async def a_ce(c):
    return ask(c, "czemo", t(c.uid, "c_ask"), "cz1")


@A("mon", own=True)
async def a_mon(c):
    m = db.setdefault("mon", {}); m["on"] = not m.get("on", True); save()
    audit(c.uid, "alerts." + ("on" if m["on"] else "off"))
    return "set"


@A("logx", own=True)
async def a_logx(c):
    try:
        with open(AUDF, "rb") as f:
            await senddoc(c.cid, "cfbot-activity.log", f.read())
    except OSError:
        return t(c.uid, "log_none"), "log"
    return "log"


@A("ad", own=True)
async def a_ad(c):
    return ask(c, "adm", t(c.uid, "adm_ask"), "adm")


@A("am", own=True)
async def a_am(c):
    c.st["adm"] = int(c.x)
    return "adm1"


@A("amr", own=True)
async def a_amr(c):
    i = c.st["adm"]; p = db.setdefault("perm", {}).setdefault(str(i), {})
    p["ro"] = not p.get("ro"); save(); audit(c.uid, "admin.role", detail=f"{i} → {'read-only' if p['ro'] else 'full'}")
    return "adm1"


@A("amall", "amt", own=True)
async def a_amacc(c):
    i = c.st["adm"]; p = db.setdefault("perm", {}).setdefault(str(i), {})
    if c.a == "amall":
        if p.get("accs") is None: p["accs"] = []
        else: p.pop("accs", None)
    elif getacc(c.x):
        cur = [a["id"] for a in db["accounts"]] if p.get("accs") is None else list(p["accs"])
        cur.remove(c.x) if c.x in cur else cur.append(c.x)
        p["accs"] = cur
    save(); audit(c.uid, "admin.accounts", detail=f"{i} → {'all' if p.get('accs') is None else len(p['accs'])}")
    return "admc"


@A("ax", own=True)
async def a_ax(c):
    i = int(c.x)

    async def run():
        if i in db.get("admins", []): db["admins"].remove(i)
        (db.get("perm") or {}).pop(str(i), None); save(); S.pop(i, None)
        audit(c.uid, "admin.remove", detail=i)
        return "adm"
    return confirm(c, t(c.uid, "q_adm").format(i), run, "adm1")


# ── accounts
@A("add", mg=True)
async def a_add(c):
    c.st["wait"] = "token"
    return "addtok"


@A("a")
async def a_a(c):
    if not getacc(c.x) or not canacc(c.uid, c.x):
        return "acc"
    for k in ("zone", "zq", "aid", "aidl", "rec", "rule", "dnsq", "dty", "bulk"): c.st.pop(k, None)
    c.st.update(acc=c.x, zones={}, zpage=1)
    return "zones"


@A("x", mg=True)
async def a_x(c):
    a = getacc(c.x)
    if not a:
        return "acc"

    async def run():
        if getacc(a["id"]):
            db["accounts"].remove(a)
            for p in (db.get("perm") or {}).values():
                if a["id"] in (p.get("accs") or []): p["accs"].remove(a["id"])
            ((db.get("mon") or {}).get("a") or {}).pop(a["id"], None)
            save(); audit(c.uid, "account.remove", a["name"])
        return "acc"
    return confirm(c, t(c.uid, "q_acc").format(esc(a["name"])), run, "acc")


# ── zones list
@A("z", lv=1)
async def a_z(c):
    if not HEX.fullmatch(c.x):
        return "zones"
    for k in ("rec", "rule", "dnsq", "dty"): c.st.pop(k, None)
    c.st.update(zone=c.x, page=1, fpage=1)
    return "zone"


@A("zgp", "zgn", lv=1)
async def a_zpage(c):
    c.st["zpage"] = max(1, int(c.x))
    return "zones"


@A("zq", lv=1)
async def a_zq(c):
    return ask(c, "zq", t(c.uid, "zq_ask"), "zones")


@A("zqc", lv=1)
async def a_zqc(c):
    c.st.pop("zq", None); c.st["zpage"] = 1
    return "zones"


async def need_aid(c, nxt):
    """Make sure the Cloudflare account ID is known; False means the user must pick one first."""
    st = c.st
    if st.get("aid"):
        return True
    j = await C(c.uid, "GET", "/accounts", params={"per_page": 50})
    lst = [(a["id"], a.get("name", "")) for a in j.get("result") or [] if a.get("id")]
    if not lst:  # token cannot list accounts: take the account of any zone it can see
        zs = (await C(c.uid, "GET", "/zones", params={"per_page": 1})).get("result") or []
        if zs and (zs[0].get("account") or {}).get("id"):
            lst = [(zs[0]["account"]["id"], zs[0]["account"].get("name", ""))]
    if not lst:
        raise Stop("noaid")
    st["aidl"] = lst
    if len(lst) == 1:
        st["aid"] = lst[0][0]
        return True
    st["aidnext"] = nxt
    return False


@A("svc", lv=1)
async def a_svc(c):
    return "svc" if await need_aid(c, "svc") else "aids"


@A("aisw", lv=1)
async def a_aisw(c):
    c.st.pop("aid", None); c.st["aidnext"] = "svc"
    return "aids"


@A("zadd", w=True, lv=1)
async def a_zadd(c):
    if not await need_aid(c, "zadd"):
        return "aids"
    return ask(c, "zadd", t(c.uid, "zadd_ask"), "zones")


@A("ai", lv=1)
async def a_ai(c):
    c.st["aid"] = c.st["aidl"][int(c.x)][0]
    if c.st.pop("aidnext", "") == "zadd" and not readonly(c.uid):
        return ask(c, "zadd", t(c.uid, "zadd_ask"), "zones")
    return "svc"


@A("bk", w=True, lv=1)
async def a_bk(c):
    scope = "z" if c.x == "z" and c.z else "a"
    c.st["bulk"] = {"scope": scope}
    return ask(c, "bulk", t(c.uid, "bulk_ask").format(t(c.uid, "bulk_" + scope)), "dns" if scope == "z" else "zones")


# ── one zone
@A("ua", w=True, lv=2)
async def a_ua(c):
    j = await getz(c, "security_level")
    if not j.get("success"):  # never flip a switch whose current position is unknown
        return "❌ " + errtxt(j, c.uid), "zone"
    new = "medium" if (j.get("result") or {}).get("value") == "under_attack" else "under_attack"
    return done(c, await setz(c, "security_level", new), "security_level", new), "zone"


@A("dev", w=True, lv=2)
async def a_dev(c):
    j = await getz(c, "development_mode")
    if not j.get("success"):
        return "❌ " + errtxt(j, c.uid), "zone"
    new = "off" if (j.get("result") or {}).get("value") == "on" else "on"
    return done(c, await setz(c, "development_mode", new), "development_mode", new), "zone"


@A("zp", w=True, lv=2)
async def a_zp(c):
    j = await C(c.uid, "GET", f"/zones/{c.z}")
    if not j.get("result"):
        return "❌ " + errtxt(j, c.uid), "zone"
    new = not j["result"].get("paused")

    async def run():
        return done(c, await C(c.uid, "PATCH", f"/zones/{c.z}", json={"paused": new}), "zone.pause" if new else "zone.resume"), "zone"
    return confirm(c, t(c.uid, "q_pause").format(esc(zname(c.st))), run, "zone") if new else await run()


@A("zac", w=True, lv=2)
async def a_zac(c):
    return done(c, await C(c.uid, "PUT", f"/zones/{c.z}/activation_check"), "zone.activation_check"), "zone"


@A("zdel", w=True, lv=2)
async def a_zdel(c):
    return ask(c, "zdel", t(c.uid, "zdel_ask").format(esc(zname(c.st))), "zone")


@A("ex", lv=2)
async def a_ex(c):
    try:
        r = await HC.get(CF + f"/zones/{c.z}/dns_records/export", headers={"Authorization": f"Bearer {tok(c.uid)}"})
    except httpx.HTTPError as ex:
        return f"❌ network error ({type(ex).__name__})", "zone"
    if r.status_code != 200 or r.text.lstrip().startswith("{"):
        try:
            j = {**r.json(), "_status": r.status_code}
        except ValueError:
            j = fail(f"HTTP {r.status_code}", r.status_code)
        return "❌ " + errtxt(j, c.uid), "zone"
    d = await senddoc(c.cid, (zname(c.st) or "zone") + ".dns.txt", r.content)
    return (t(c.uid, "done") if d.get("ok") else "❌ " + str(d.get("description"))), "zone"


@A("im", w=True, lv=2)
async def a_im(c):
    return ask(c, "imp", t(c.uid, "imp_ask"), "zone")


@A("pca", w=True, lv=2)
async def a_pca(c):
    async def run():
        return done(c, await C(c.uid, "POST", f"/zones/{c.z}/purge_cache", json={"purge_everything": True}), "cache.purge", "everything"), "zone"
    return confirm(c, t(c.uid, "q_purge").format(esc(zname(c.st))), run, "purge")


@A("pcu", w=True, lv=2)
async def a_pcu(c):
    return ask(c, "pcu", t(c.uid, "pc_ask"), "purge")


@A("ss", w=True, lv=2)
async def a_ss(c):
    if c.x not in SSLM:
        return "ssl"

    async def run():
        return done(c, await setz(c, "ssl", c.x), "ssl", c.x), "ssl"
    return confirm(c, t(c.uid, "q_ssl").format(esc(zname(c.st))), run, "ssl") if c.x == "off" else await run()


@A("sc", w=True, lv=2)
async def a_sc(c):
    if c.x not in LEVELS:
        return "sec"
    return done(c, await setz(c, "security_level", c.x), "security_level", c.x), "sec"


@A("tl", w=True, lv=2)
async def a_tl(c):
    if c.x not in TLSV:
        return "tls"
    return done(c, await setz(c, "min_tls_version", c.x), "min_tls_version", c.x), "tls"


@A("cl", w=True, lv=2)
async def a_cl(c):
    if c.x not in CACHEL:
        return "cache"
    return done(c, await setz(c, "cache_level", c.x), "cache_level", c.x), "cache"


@A("tg", w=True, lv=2)
async def a_tg(c):
    if c.x not in dict(TOGGLES):
        return "tog"
    j = await getz(c, c.x)
    if not j.get("success"):
        return "❌ " + errtxt(j, c.uid), "tog"
    new = "off" if ison((j.get("result") or {}).get("value")) else "on"
    return done(c, await setz(c, c.x, new), c.x, new), "tog"


@A("hs", w=True, lv=2)
async def a_hs(c):
    op, _, arg = c.x.partition(":")
    j, h = await hsts_get(c.uid, c.z)
    if not j.get("success"):
        return "❌ " + errtxt(j, c.uid), "hsts"
    if op == "en": h["enabled"] = not h.get("enabled")
    elif op == "a" and arg.isdigit(): h["max_age"] = int(arg)
    elif op in ("sub", "pre", "ns"):
        k = {"sub": "include_subdomains", "pre": "preload", "ns": "nosniff"}[op]; h[k] = not h.get(k)
    else:
        return "hsts"
    if h.get("enabled") and not h.get("max_age"): h["max_age"] = 15552000

    async def run():
        return done(c, await setz(c, "security_header", {"strict_transport_security": h}), "hsts", f"{op} {arg}".strip()), "hsts"
    return confirm(c, t(c.uid, "q_hsts").format(esc(zname(c.st))), run, "hsts") if op == "en" and h["enabled"] else await run()


@A("dz", w=True, lv=2)
async def a_dz(c):
    on = c.x == "1"

    async def run():
        return done(c, await C(c.uid, "PATCH", f"/zones/{c.z}/dnssec", json={"status": "active" if on else "disabled"}), "dnssec", "on" if on else "off"), "dsec"
    return await run() if on else confirm(c, t(c.uid, "q_dsec").format(esc(zname(c.st))), run, "dsec")


@A("anp", lv=2)
async def a_anp(c):
    c.st["anp"] = int(c.x) if c.x in ("1", "7", "30") else 7
    return "an"


# ── DNS
@A("dns", lv=2)
async def a_dns(c):
    c.st["page"] = 1
    return "dns"


@A("r", lv=2)
async def a_r(c):
    if not HEX.fullmatch(c.x):
        return "dns"
    c.st["rec"] = c.x
    return "rec"


@A("dgp", "dgn", lv=2)
async def a_dpage(c):
    c.st["page"] = max(1, int(c.x))
    return "dns"


@A("ds", lv=2)
async def a_ds(c):
    return ask(c, "dsq", t(c.uid, "ds_ask"), "dns")


@A("dty", lv=2)
async def a_dty(c):
    c.st["dty"] = c.x if c.x in DTYPES else None; c.st["page"] = 1
    return "dns"


@A("dc", lv=2)
async def a_dc(c):
    c.st.pop("dnsq", None); c.st.pop("dty", None); c.st["page"] = 1
    return "dns"


@A("new", w=True, lv=2)
async def a_new(c):
    return ask(c, "dns", t(c.uid, "adddns"), "dns")


@A("ed", w=True, lv=2)
async def a_ed(c):
    if c.x not in ("content", "name", "ttl", "priority") or not c.st.get("rec"):
        return "rec"
    key = {"SRV": "ask_srv", "CAA": "ask_caa"}.get(c.st.get("rtype"), "ask_content") if c.x == "content" else "ask_" + c.x
    return ask(c, "edit", t(c.uid, key), "rec", field=c.x)


@A("px", w=True, lv=2)
async def a_px(c):
    path = f"/zones/{c.z}/dns_records/{c.st.get('rec')}"
    j = await C(c.uid, "GET", path); r = j.get("result")
    if not r:
        return "❌ " + errtxt(j, c.uid), "dns"
    new = not r.get("proxied")
    return done(c, await C(c.uid, "PATCH", path, json={"proxied": new}), "dns.proxy", f"{r.get('name')} → {'on' if new else 'off'}"), "rec"


@A("dq", w=True, lv=2)
async def a_dq(c):
    path = f"/zones/{c.z}/dns_records/{c.st.get('rec')}"
    j = await C(c.uid, "GET", path); r = j.get("result")
    if not r:
        return "❌ " + errtxt(j, c.uid), "dns"
    label = f"{r.get('type')} {r.get('name')}"

    async def run():
        return done(c, await C(c.uid, "DELETE", path), "dns.delete", label), "dns"
    return confirm(c, t(c.uid, "q_rec").format(esc(label)), run, "rec")


# ── firewall (IP Access Rules)
@A("fgp", "fgn", lv=2)
async def a_fpage(c):
    c.st["fpage"] = max(1, int(c.x))
    return "fw"


@A("fn", w=True, lv=2)
async def a_fn(c):
    return ask(c, "fw", t(c.uid, "askfw"), "fw")


@A("fd", w=True, lv=2)
async def a_fd(c):
    if not HEX.fullmatch(c.x):
        return "fw"
    label = (c.st.get("fwl") or {}).get(c.x, c.x)

    async def run():
        return done(c, await C(c.uid, "DELETE", f"/zones/{c.z}/firewall/access_rules/rules/{c.x}"), "firewall.delete", label), "fw"
    return confirm(c, t(c.uid, "q_fw").format(esc(label)), run, "fw")


# ── rulesets (WAF custom rules, rate limiting, redirects)
@A("rs", lv=2)
async def a_rs(c):
    if c.x in PH: c.st["ph"] = c.x
    c.st.pop("rule", None)
    return "rs"


@A("ru", lv=2)
async def a_ru(c):
    if c.x not in (c.st.get("rules") or {}):
        return "rs"
    c.st["rule"] = c.x
    return "ru"


@A("rn", w=True, lv=2)
async def a_rn(c):
    ph = c.st.get("ph") if c.st.get("ph") in PH else "w"
    return ask(c, "rn", t(c.uid, "rn_" + ph), "rs")


def rule_of(c):
    r = (c.st.get("rules") or {}).get(c.st.get("rule"))
    return r if r and c.st.get("rsid") else None


@A("rt", w=True, lv=2)
async def a_rt(c):
    r = rule_of(c)
    if not r:
        return "rs"
    body = {k: r[k] for k in ("action", "expression", "description", "action_parameters", "ratelimit", "logging") if k in r}
    body["enabled"] = not r.get("enabled", True)
    j = await C(c.uid, "PATCH", f"/zones/{c.z}/rulesets/{c.st['rsid']}/rules/{r['id']}", json=body)
    if j.get("success"):
        setrules(c.st, j.get("result")) if (j.get("result") or {}).get("rules") else r.update(enabled=body["enabled"])
    return done(c, j, "rule.toggle", f"{r.get('description') or r['id']} → {'on' if body['enabled'] else 'off'}"), "ru"


@A("rd", w=True, lv=2)
async def a_rd(c):
    r = rule_of(c)
    if not r:
        return "rs"
    rsid, label = c.st["rsid"], r.get("description") or r.get("expression") or r["id"]

    async def run():
        return done(c, await C(c.uid, "DELETE", f"/zones/{c.z}/rulesets/{rsid}/rules/{r['id']}"), "rule.delete", label), "rs"
    return confirm(c, t(c.uid, "q_rule").format(esc(str(label)[:200])), run, "ru")


# ── page rules, worker routes
@A("prt", w=True, lv=2)
async def a_prt(c):
    r = (c.st.get("prl") or {}).get(c.x)
    if not r:
        return "pr"
    new = "disabled" if r.get("status") == "active" else "active"
    return done(c, await C(c.uid, "PATCH", f"/zones/{c.z}/pagerules/{c.x}", json={"status": new}), "pagerule.toggle", new), "pr"


@A("prd", w=True, lv=2)
async def a_prd(c):
    r = (c.st.get("prl") or {}).get(c.x)
    if not r:
        return "pr"
    label = ((r.get("targets") or [{}])[0].get("constraint") or {}).get("value", c.x)

    async def run():
        return done(c, await C(c.uid, "DELETE", f"/zones/{c.z}/pagerules/{c.x}"), "pagerule.delete", label), "pr"
    return confirm(c, t(c.uid, "q_rule").format(esc(label)), run, "pr")


@A("prn", w=True, lv=2)
async def a_prn(c):
    return ask(c, "prn", t(c.uid, "prn_ask"), "pr")


@A("wrd", w=True, lv=2)
async def a_wrd(c):
    if c.x not in (c.st.get("wrl") or {}):
        return "wr"
    label = c.st["wrl"][c.x]

    async def run():
        return done(c, await C(c.uid, "DELETE", f"/zones/{c.z}/workers/routes/{c.x}"), "worker_route.delete", label), "wr"
    return confirm(c, t(c.uid, "q_rule").format(esc(label)), run, "wr")


@A("wrn", w=True, lv=2)
async def a_wrn(c):
    return ask(c, "wrn", t(c.uid, "wrn_ask"), "wr")


# ── account-level services
@A("wk1", lv=1)
async def a_wk1(c):
    c.st["wk"] = c.st["wkl"][int(c.x)]["id"]
    return "wk1"


@A("wkx", w=True, lv=1)
async def a_wkx(c):
    name, aid = c.st.get("wk"), c.st.get("aid")
    if not name or not aid:
        return "wk"

    async def run():
        return done(c, await C(c.uid, "DELETE", f"/accounts/{aid}/workers/scripts/{quote(name, safe='')}"), "worker.delete", name, zone=False), "wk"
    return confirm(c, t(c.uid, "q_wk").format(esc(name)), run, "wk1")


@A("pg1", lv=1)
async def a_pg1(c):
    c.st["pg"] = c.st["pgl"][int(c.x)]["name"]
    return "pg1"


@A("pgr", w=True, lv=1)
async def a_pgr(c):
    name, dep, aid = c.st.get("pg"), c.st.get("pgd"), c.st.get("aid")
    if not name or not dep or not aid:
        return "pg1"
    j = await C(c.uid, "POST", f"/accounts/{aid}/pages/projects/{quote(name, safe='')}/deployments/{quote(dep, safe='')}/retry")
    return done(c, j, "pages.retry", name, zone=False), "pg1"


@A("tn1", lv=1)
async def a_tn1(c):
    c.st["tun"] = c.st["tnl"][int(c.x)]["id"]
    return "tn1"


async def cb(q):
    uid = q["from"]["id"]; m = q.get("message") or {}
    cid = (m.get("chat") or {}).get("id", uid); mid = m.get("message_id")
    st = S.setdefault(uid, {}); st["wait"] = None
    data, _, key = (q.get("data") or "").partition("|"); a, _, x = data.partition(":")

    async def ans(text=None, alert=False):
        await tg("answerCallbackQuery", callback_query_id=q["id"], **({"text": text[:190], "show_alert": alert} if text else {}))

    if a == "noop":
        return await ans()
    if a != "y":
        st.pop("cfm", None)  # leaving a confirmation screen cancels it
    h = ACTS.get(a)
    lv = h[4] if h else 0
    if not h or (key and key not in keys_now(st)) or (lv and (not key or not st.get("acc"))) or (lv == 2 and not st.get("zone")):
        await ans(t(uid, "stale"), True)  # button from an old message: never act on another account/zone/record
        return await render(uid, cid, mid, here(st))
    f, w, own, mg, _ = h
    deny = "denied" if own and not isowner(uid) else "ro" if w and readonly(uid) else "nomg" if mg and not canmanage(uid) else None
    if deny:
        return await ans(t(uid, deny), True)
    c = NS(uid=uid, cid=cid, mid=mid, st=st, a=a, x=x, z=st.get("zone"), q=q)
    try:
        r = await f(c)
    except (IndexError, KeyError, ValueError) as ex:  # the list this button pointed into has changed
        log("stale callback:", a, repr(ex))
        await ans(t(uid, "stale"), True)
        return await render(uid, cid, mid, here(st))
    note, v = r if isinstance(r, tuple) else (None, r)
    await ans(note, bool(note) and note.startswith("❌"))
    if v:
        await render(uid, cid, mid, v)


# ───────────────────────── text input ─────────────────────────
def mdone(c, j, act, detail="", zone=True):
    """Like done(), for answers sent as a chat message (HTML)."""
    r = done(c, j, act, detail, zone)
    return None if j.get("success") else esc(r)


@W("token", mg=True)
async def w_token(c, txt):
    await tg("deleteMessage", chat_id=c.cid, message_id=c.m["message_id"])  # hide the token
    if not re.fullmatch(r"[A-Za-z0-9_\-.]{20,200}", txt):
        return "❌ " + t(c.uid, "bad"), None
    for a in db["accounts"]:
        try:
            if dec(a["token"]) == txt:
                return "❌ " + t(c.uid, "dup"), "acc"
        except Stop:
            pass
    r = await cfreq(txt, "GET", "/zones", params={"per_page": 1})
    if not r.get("success"):
        return "❌ " + t(c.uid, "bad") + f"\n<i>{esc(errtxt(r))}</i>", None
    name = ((r["result"][0].get("account") or {}).get("name") if r.get("result") else None) or f"Account {len(db['accounts']) + 1}"
    base, n = name, 2
    while any(a["name"] == name for a in db["accounts"]):
        name = f"{base} ({n})"; n += 1
    db["accounts"].append({"id": secrets.token_hex(4), "name": name, "token": enc(txt)}); save()
    audit(c.uid, "account.add", name)
    return "✅ " + t(c.uid, "saved"), "acc"


@W("dns")
async def w_dns(c, txt):
    try:
        rec = parse_rec(txt, zname(c.st))
    except ValueError as ex:
        return retry(c, "x_" + str(ex))
    j = await C(c.uid, "POST", f"/zones/{c.z}/dns_records", json=rec)
    note = mdone(c, j, "dns.add", f"{rec['type']} {rec['name']}")
    if note:
        c.st["wait"] = c.w  # let the user fix it and send again
        return note, None
    return "dns"


@W("edit")
async def w_edit(c, txt):
    f = c.st.get("field"); rec = c.st.get("rec")
    if not rec or f not in ("content", "name", "ttl", "priority"):
        return "dns"
    try:
        body = parse_edit(c.st.get("rtype"), f, txt, zname(c.st))
    except ValueError as ex:
        return retry(c, "x_" + str(ex))
    j = await C(c.uid, "PATCH", f"/zones/{c.z}/dns_records/{rec}", json=body)
    return mdone(c, j, "dns.edit", f"{f} → {txt[:80]}"), "rec"


@W("dsq", w=False)
async def w_dsq(c, txt):
    c.st["dnsq"] = txt[:60]; c.st["page"] = 1
    return "dns"


@W("zq", w=False)
async def w_zq(c, txt):
    c.st["zq"] = txt[:60].lower(); c.st["zpage"] = 1
    return "zones"


@W("bulk")
async def w_bulk(c, txt):
    uid, st = c.uid, c.st
    scope = (st.get("bulk") or {}).get("scope", "a"); back = "dns" if scope == "z" and c.z else "zones"
    try:
        old, new, typ = parse_bulk(txt)
    except ValueError as ex:
        return retry(c, str(ex))
    token = tok(uid)
    if back == "dns":
        zones = [(c.z, zname(st))]
    else:
        zl, errj = await allpages(token, "/zones")
        if errj:
            return "❌ " + esc(errtxt(errj, uid)), back
        zones = [(z["id"], z["name"]) for z in zl]
    sem = asyncio.Semaphore(5)

    async def scan(zid, zn):
        async with sem:
            rs, _ = await allpages(token, f"/zones/{zid}/dns_records", {"type": typ, "content": old}, per=100, cap=500)
        return [(zid, zn, r["id"], r["name"]) for r in rs]
    items = [x for part in await asyncio.gather(*(scan(*z) for z in zones)) for x in part]
    if not items:
        return "❌ " + t(uid, "bulk_none"), back
    capped = len(items) > 500; items = items[:500]

    async def run():
        async def one(it):
            async with sem:
                return (await cfreq(token, "PATCH", f"/zones/{it[0]}/dns_records/{it[2]}", json={"content": new})).get("success")
        okn = sum(1 for r in await asyncio.gather(*(one(it) for it in items)) if r)
        audit(uid, "dns.bulk_replace", (getacc(st.get("acc")) or {}).get("name", ""), zname(st) if back == "dns" else "",
              f"{old} → {new}: {okn}/{len(items)}", okn == len(items))
        await say(c.cid, t(uid, "bulk_res").format(okn, len(items)))
        return back
    lines = "\n".join(f"• <code>{esc(n)}</code>" for _, _, _, n in items[:12])
    more = f"\n{t(uid, 'bulk_more').format(len(items) - 12)}" if len(items) > 12 else ""
    text = (t(uid, "q_bulk").format(len(items), len({i[0] for i in items}), esc(old), esc(new)) + f"\n\n{lines}{more}"
            + (f"\n{t(uid, 'bulk_cap').format(500)}" if capped else ""))
    return confirm(c, text, run, back)


@W("zadd")
async def w_zadd(c, txt):
    name = idna(txt.strip().rstrip(".").lower())
    if not re.fullmatch(r"([a-z0-9][\-a-z0-9]*\.)+[\-a-z0-9]{2,20}", name):
        return retry(c, "zadd_bad")
    j = await C(c.uid, "POST", "/zones", json={"name": name, "account": {"id": c.st.get("aid")}, "type": "full"})
    note = mdone(c, j, "zone.add", name, zone=False)
    if note:
        return note, "zones"
    zi = j.get("result") or {}
    c.st["zone"] = zi.get("id"); c.st.setdefault("zones", {})[zi.get("id")] = zi.get("name", name); c.st["page"] = 1
    ns = "\n".join(f"<code>{esc(n)}</code>" for n in zi.get("name_servers") or [])
    return t(c.uid, "zadd_ok").format(esc(name), ns), "zone"


@W("zdel")
async def w_zdel(c, txt):
    name = zname(c.st)
    if not name or txt.lower() != name.lower():
        return t(c.uid, "zdel_bad"), "zone"
    j = await C(c.uid, "DELETE", f"/zones/{c.z}")
    note = mdone(c, j, "zone.delete", name)
    if note:
        return note, "zone"
    c.st.pop("zone", None)
    return "✅ " + esc(name) + " — " + t(c.uid, "done"), "zones"


@W("adm", own=True)
async def w_adm(c, txt):
    if not txt.isdigit() or len(txt) > 15:
        return "❌ " + t(c.uid, "adm_bad"), "adm"
    n = int(txt)
    if n not in ADMINS and n not in db.setdefault("admins", []):
        db["admins"].append(n); save(); audit(c.uid, "admin.add", detail=n)
    await send_menu(n, n, T[lang(n)]["welcome"])  # silently ignored if they never started the bot
    return "✅ " + t(c.uid, "adm_ok"), "adm"


@W("fw")
async def w_fw(c, txt):
    try:
        body = parse_fw(txt)
    except ValueError as ex:
        return retry(c, str(ex))
    j = await C(c.uid, "POST", f"/zones/{c.z}/firewall/access_rules/rules", json=body)
    return mdone(c, j, "firewall.add", f"{body['mode']} {body['configuration']['value']}"), "fw"


@W("rn")
async def w_rn(c, txt):
    ph = c.st.get("ph") if c.st.get("ph") in PH else "w"
    try:
        rule = {"w": parse_waf, "r": parse_rl, "d": parse_redirect}[ph](txt)
    except ValueError:
        return retry(c, "x_rule")
    if c.st.get("rsid"):
        j = await C(c.uid, "POST", f"/zones/{c.z}/rulesets/{c.st['rsid']}/rules", json=rule)
    else:  # first rule of this phase: create its ruleset
        j = await C(c.uid, "PUT", f"/zones/{c.z}/rulesets/phases/{PH[ph]}/entrypoint", json={"rules": [rule]})
    note = mdone(c, j, "rule.add", f"{PH[ph]}: {rule['description']}")
    if note:
        c.st["wait"] = c.w
        return note, None
    return "rs"


@W("prn")
async def w_prn(c, txt):
    try:
        body = parse_pagerule(txt)
    except ValueError:
        return retry(c, "x_rule")
    return mdone(c, await C(c.uid, "POST", f"/zones/{c.z}/pagerules", json=body), "pagerule.add", txt[:120]), "pr"


@W("wrn")
async def w_wrn(c, txt):
    p = txt.split()
    if len(p) != 2:
        return retry(c, "x_rule")
    return mdone(c, await C(c.uid, "POST", f"/zones/{c.z}/workers/routes", json={"pattern": p[0], "script": p[1]}), "worker_route.add", txt[:120]), "wr"


@W("pcu")
async def w_pcu(c, txt):
    try:
        groups = parse_purge(txt)
    except ValueError as ex:
        return retry(c, str(ex))
    bad = None
    for k, items in groups.items():  # Cloudflare takes one kind of target per request
        note = mdone(c, await C(c.uid, "POST", f"/zones/{c.z}/purge_cache", json={k: items}), "cache.purge", f"{k}: {len(items)}")
        bad = bad or note
    return bad or "✅ " + t(c.uid, "done").replace(" ✅", ""), "purge"


@W("imp")
async def w_imp(c, txt):
    doc = c.m.get("document")
    if doc:
        if (doc.get("file_size") or 0) > 2 << 20:
            return retry(c, "imp_big")
        data = await tgfile(doc["file_id"])
        if data is None:
            return retry(c, "imp_dl")
    else:
        data = (c.m.get("text") or "").encode()
    j = await C(c.uid, "POST", f"/zones/{c.z}/dns_records/import", files={"file": ("zone.txt", data, "text/plain")}, data={"proxied": "false"})
    res = j.get("result") or {}
    note = mdone(c, j, "dns.import", f"{res.get('recs_added', 0)}/{res.get('total_records_parsed', 0)}")
    return note or t(c.uid, "imp_ok").format(res.get("recs_added", 0), res.get("total_records_parsed", 0)), "dns"


async def msg(m):
    uid = m["from"]["id"]; cid = m["chat"]["id"]; st = S.setdefault(uid, {}); txt = (m.get("text") or "").strip()
    ids = [en for en in m.get("entities", []) if en["type"] == "custom_emoji"]
    rw = not readonly(uid)
    if rw and st.get("wait") == "czemo" and (ids or txt) and st.get("scr") and st.get("sel") is not None:
        st["wait"] = None
        bid = st["scr"][st["sel"]][0]
        o = db.setdefault("btn", {}).setdefault(bid, {}); o.pop("emo", None); o.pop("uni", None)
        if ids: o["emo"] = sorted(ids, key=lambda en: en["offset"])[0]["custom_emoji_id"]
        else: o["uni"] = txt[:8]
        save()
        if bid.startswith("menu."): await remenu(cid, uid)
        await render(uid, cid, None, "cz1"); return
    if rw and ids and st.get("wait") == "emo":
        st["wait"] = None
        found = [en["custom_emoji_id"] for en in sorted(ids, key=lambda en: en["offset"])]
        db.setdefault("emo", {}).update(dict(zip(EMO, found))); save(); OK.update(text=True, btn=True)
        await tg("sendMessage", chat_id=cid, text=f"✅ {len(found)}/{len(EMO)}\n" + await probe(cid))
        await render(uid, cid, None, "emo"); return
    if ids:  # helper: reveal premium emoji IDs
        await tg("sendMessage", chat_id=cid, parse_mode="HTML", text="\n".join(f"<code>{en['custom_emoji_id']}</code>" for en in ids))
        return
    w = st.get("wait"); st["wait"] = None; st.pop("cfm", None); n = norm(txt)
    cmd = txt.split()[0].split("@")[0].lower() if txt.startswith("/") else ""

    if cmd == "/start":
        return await send_menu(cid, uid, t(uid, "welcome"))
    if cmd == "/cancel":
        return await send_menu(cid, uid, t(uid, "cancelled"))
    if cmd == "/help":
        return await render(uid, cid, None, "help")
    if n in MENU:
        v = MENU[n]
        if v == "zones" and not getacc(st.get("acc")):
            accs = myaccs(uid)
            if len(accs) == 1: st.update(acc=accs[0]["id"], zones={}, zpage=1)
            else: v = "acc"
        if v == "addtok":
            if not canmanage(uid):
                return await say(cid, t(uid, "nomg"))
            st["wait"] = "token"
        return await render(uid, cid, None, v)

    h = WAITS.get(w)
    if not h or not (txt or (w == "imp" and m.get("document"))):
        return await send_menu(cid, uid, t(uid, "welcome"))
    f, wr, own, mg = h
    deny = "denied" if own and not isowner(uid) else "ro" if wr and readonly(uid) else "nomg" if mg and not canmanage(uid) else None
    if deny:
        return await say(cid, t(uid, deny))
    r = await f(NS(uid=uid, cid=cid, st=st, z=st.get("zone"), m=m, w=w), txt)
    note, v = r if isinstance(r, tuple) else (None, r)
    if note:
        await say(cid, note)
    if v:
        await render(uid, cid, None, v)


async def handle(u):
    """One update, start to finish. Errors are reported to the user instead of vanishing into the log."""
    _cx.set(Ctx())
    q, m = u.get("callback_query"), u.get("message")
    uid = ((q or m or {}).get("from") or {}).get("id")
    if not uid or not isadmin(uid):
        return
    async with LOCKS.setdefault(uid, asyncio.Lock()):
        try:
            await (cb(q) if q else msg(m))
        except Exception as ex:
            if isinstance(ex, Stop):
                text = t(uid, ex.args[0])
            else:
                log("handler error:", traceback.format_exc())
                text = t(uid, "oops").format(type(ex).__name__)
            if q:
                await tg("answerCallbackQuery", callback_query_id=q["id"], text=("❌ " + text)[:190], show_alert=True)
                if isinstance(ex, Stop):
                    try:
                        await render(uid, ((q.get("message") or {}).get("chat") or {}).get("id", uid), (q.get("message") or {}).get("message_id"), "acc")
                    except Exception:
                        pass
            else:
                await say(m["chat"]["id"], "❌ " + esc(text))


# ───────────────────────── background alerts ─────────────────────────
async def alert(aid, key, *args):
    for u in set(ADMINS) | set(db.get("admins", [])):
        if canacc(u, aid):
            await say(u, T[lang(u)][key].format(*(esc(a) for a in args)))


async def mon_tick():
    """Tell the admins when an account stops answering or a zone changes status."""
    stt = db.setdefault("mon", {}).setdefault("a", {}); changed = False
    for a in list(db["accounts"]):
        s = stt.setdefault(a["id"], {})
        try:
            zones, errj = await allpages(dec(a["token"]), "/zones", cap=5000)
        except Stop:
            continue
        if errj:
            s["fails"] = s.get("fails", 0) + 1
            if s["fails"] == 2 and not s.get("bad"):  # two misses in a row: not a blip
                s["bad"] = True; changed = True
                await alert(a["id"], "al_bad", a["name"], errtxt(errj))
            continue
        if s.get("bad"):
            await alert(a["id"], "al_ok", a["name"])
        if s.get("bad") or s.get("fails"):
            s["bad"] = False; s["fails"] = 0; changed = True
        old, new = s.get("z") or {}, {z["id"]: z.get("status", "") for z in zones}
        if s.get("init"):
            for z in zones:
                if old.get(z["id"]) and old[z["id"]] != z.get("status"):
                    await alert(a["id"], "al_zone", z["name"], old[z["id"]], z.get("status"))
        if new != old or not s.get("init"):
            s["z"] = new; s["init"] = True; changed = True
    for k in [k for k in stt if not getacc(k)]:
        del stt[k]; changed = True
    if changed:
        save()


async def monitor():
    await asyncio.sleep(30)
    while True:
        try:
            if (db.get("mon") or {}).get("on", True):
                await mon_tick()
        except Exception:
            log("monitor error:", traceback.format_exc())
        await asyncio.sleep(MON_EVERY)


# ───────────────────────── main loop ─────────────────────────
async def startup():
    for code, l in ((None, "fa"), ("en", "en")):
        cmds = [{"command": k, "description": T[l]["c_" + k]} for k in ("start", "help", "cancel")]
        await tg("setMyCommands", commands=cmds, **({"language_code": code} if code else {}))


async def poll(off):
    """One getUpdates round. Returns (new offset, updates, seconds to wait before the next round)."""
    r = await tg("getUpdates", offset=off, timeout=50, allowed_updates=["message", "callback_query"])
    if not r.get("ok"):  # never hammer Telegram: back off, longer when the token itself is rejected
        wait = (r.get("parameters") or {}).get("retry_after") or (30 if r.get("error_code") in (401, 404) else 5)
        log("poll error:", r.get("error_code") or "", r.get("description"))
        return off, [], min(int(wait), 300)
    ups = r.get("result") or []
    return (ups[-1]["update_id"] + 1 if ups else off), ups, 0


async def main():
    log(f"CF Control v{VERSION} started · accounts: {len(db['accounts'])} · token encryption: {'on' if FER else 'off'}")
    await startup()
    tasks = set()

    def finished(task):
        tasks.discard(task)
        if not task.cancelled() and task.exception():
            log("task error:", repr(task.exception()))
    if MON_EVERY > 0:
        tasks.add(asyncio.create_task(monitor()))
    off = 0
    while True:
        off, ups, wait = await poll(off)
        for u in ups:  # each update runs on its own; handle() serialises per user
            task = asyncio.create_task(handle(u)); tasks.add(task); task.add_done_callback(finished)
        if wait:
            await asyncio.sleep(wait)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
