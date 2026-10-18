#!/usr/bin/env python3
# CF Control — Cloudflare manager Telegram bot (single file, raw Bot API)
# Developed by DenTeeR  ·  MIT License
import os, re, json, html, time, asyncio, httpx

TOKEN = os.environ["BOT_TOKEN"]
ADMINS = {int(x) for x in os.environ["ADMIN_IDS"].split(",")}
TG = f"https://api.telegram.org/bot{TOKEN}/"
CF = "https://api.cloudflare.com/client/v4"
DBF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")
H = httpx.AsyncClient(timeout=70)
S = {}  # runtime state per user

# Premium emoji IDs (empty => normal emoji). Send a premium emoji to the bot to get its ID.
EMO = {
    "cloud": ("", "☁️"), "plus": ("", "➕"), "globe": ("", "🌐"), "dns": ("", "📡"),
    "lock": ("", "🔒"), "fire": ("", "🔥"), "trash": ("", "🗑"), "back": ("", "◀️"),
    "gear": ("", "⚙️"), "lang": ("", "🌍"), "dev": ("", "🛠"), "ok": ("", "✅"),
    "edit": ("", "✏️"), "shield": ("", "🛡"), "export": ("", "📤"), "ban": ("", "⛔"),
    "bolt": ("", "⚡️"), "tag": ("", "🏷"), "green": ("", "🟢"), "yellow": ("", "🟡"), "red": ("", "🔴"),
    "target": ("", "🎯"), "time": ("", "⏱"), "warn": ("", "⚠️"), "puzzle": ("", "🧩"), "user": ("", "👤"), "crown": ("", "👑"),
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
        e_content="ویرایش مقدار", e_name="ویرایش نام", e_ttl="ویرایش TTL", proxy="پروکسی",
        delete="حذف", sure="مطمئنی؟ این رکورد برای همیشه حذف می‌شود.", yes="بله، حذف کن",
        cancel="انصراف", lang_t="زبان / Language", emo="ایموجی پرمیوم", home="صفحه اصلی", prev="صفحه قبل", next="صفحه بعد", adm="ادمین‌ها", adm_add="افزودن ادمین",
        adm_ask="آیدی عددی تلگرام کاربر را بفرستید.\nکاربر می‌تواند آیدی خود را از @userinfobot بگیرد.", adm_ok="ادمین اضافه شد",
        adm_bad="آیدی نامعتبر است (فقط عدد).", owner="مالک", chk="بررسی اتصال", chk_title="وضعیت اتصال به کلودفلر",
        adm_note="ادمین‌ها به همهٔ حساب‌های کلودفلر ذخیره‌شده دسترسی دارند. فقط مالک می‌تواند ادمین اضافه یا حذف کند.", zdel="حذف دامنه", zdel_bad="❌ نام مطابقت نداشت. حذف لغو شد.",
        zdel_ask="⚠️ <b>حذف دامنه {}</b> از کلودفلر\nاین کار برگشت‌پذیر نیست و همهٔ رکوردها و تنظیمات پاک می‌شود.\nبرای تأیید، نام دقیق دامنه را تایپ و ارسال کنید:", design="حالت طراحی (شخصی‌سازی دکمه‌ها)", czm="دکمه‌های منوی پایین",
        cz_btn="شخصی‌سازی همین صفحه", cz_hint="روی هر دکمه یا متن بزنید تا رنگ و ایموجی همان یکی را جدا تغییر دهید. (📝 = ایموجی داخل متن)",
        c_style="رنگ", c_emoji="ایموجی", c_blue="آبی", c_green="سبز", c_red="قرمز", c_def="بدون رنگ",
        c_emo="تنظیم ایموجی", c_none="حذف ایموجی", c_reset="بازنشانی", c_ask="یک ایموجی بفرستید (پرمیوم یا معمولی، هر کدام دلخواه):", emo_set="ثبت ایموجی‌ها", emo_test="تست", emo_reset="بازنشانی",
        emo_ask="یک پیام بفرستید که <b>ایموجی‌های پرمیوم</b> را به‌ترتیب زیر داشته باشد (همه یا فقط چند تای اول):",
        emo_info="برای نمایش ایموجی پرمیوم، مالک ربات باید پریمیوم داشته باشد یا برای ربات یوزرنیم اضافه از Fragment خریده شده باشد.", block="مسدودسازی جدید",
        addtok="توکن API کلودفلر را بفرستید.\nدسترسی‌ها: Zone Read+Edit، DNS Edit، Zone Settings Edit، Cache Purge، Firewall Services Edit",
        adddns="رکورد را بفرستید:\n<code>TYPE name content proxied</code>\nمثال:\n<code>A sub.example.com 1.2.3.4 1</code>",
        ask_content="مقدار جدید را بفرستید (مثلاً IP):", ask_name="نام جدید را بفرستید (مثلاً sub.example.com):",
        ask_ttl="TTL را به ثانیه بفرستید یا <code>auto</code>:",
        askfw="بفرستید:\n<code>1.2.3.4</code> یا <code>1.2.3.0/24</code> یا کد کشور مثل <code>RU</code>\nپیش‌فرض: بلاک. برای اجازه: <code>allow 1.2.3.4</code>\nبرای چلنج: <code>challenge RU</code>",
    ),
    "en": dict(
        m_acc="Accounts", m_zone="Zones", m_add="Add account", m_set="Settings",
        welcome="Welcome to <b>CF Control</b>\nFull Cloudflare management without leaving Telegram.\nUse the menu below 👇",
        back="Back", lang="فارسی", accs="Cloudflare accounts", zones="Your zones",
        empty="No accounts yet.", none="Nothing here", done="Done ✅",
        bad="Invalid token", saved="Account saved", dns="DNS records", ssl="SSL mode",
        sec="Security level", fw="Firewall", tog="Quick settings", purge="Purge cache",
        export="Export DNS", ua="Under Attack", dev="Dev mode", new="New record",
        e_content="Edit content", e_name="Edit name", e_ttl="Edit TTL", proxy="Proxy",
        delete="Delete", sure="Are you sure? This record will be deleted permanently.", yes="Yes, delete",
        cancel="Cancel", lang_t="Language / زبان", emo="Premium emoji", home="Main page", prev="Previous page", next="Next page", adm="Admins", adm_add="Add admin",
        adm_ask="Send the user's numeric Telegram ID.\nThey can get it from @userinfobot.", adm_ok="Admin added",
        adm_bad="Invalid ID (numbers only).", owner="Owner", chk="Check connection", chk_title="Cloudflare connection status",
        adm_note="Admins can access all saved Cloudflare accounts. Only the owner can add or remove admins.", zdel="Delete domain", zdel_bad="❌ Name did not match. Deletion cancelled.",
        zdel_ask="⚠️ <b>Delete domain {}</b> from Cloudflare\nThis cannot be undone; all records and settings will be removed.\nTo confirm, type the exact domain name:", design="Design mode (customize buttons)", czm="Bottom menu buttons",
        cz_btn="Customize this screen", cz_hint="Tap any button or text to change its color and emoji individually. (📝 = emoji inside text)",
        c_style="Color", c_emoji="Emoji", c_blue="Blue", c_green="Green", c_red="Red", c_def="No color",
        c_emo="Set emoji", c_none="Remove emoji", c_reset="Reset", c_ask="Send any emoji (premium or normal):", emo_set="Set emoji", emo_test="Test", emo_reset="Reset",
        emo_ask="Send one message containing <b>premium emoji</b> in this order (all of them, or just the first few):",
        emo_info="Premium emoji need the bot owner to have Telegram Premium, or the bot to own an extra Fragment username.", block="New block rule",
        addtok="Send your Cloudflare API token.\nPermissions: Zone Read+Edit, DNS Edit, Zone Settings Edit, Cache Purge, Firewall Services Edit",
        adddns="Send the record:\n<code>TYPE name content proxied</code>\nExample:\n<code>A sub.example.com 1.2.3.4 1</code>",
        ask_content="Send the new content (e.g. an IP):", ask_name="Send the new name (e.g. sub.example.com):",
        ask_ttl="Send TTL in seconds or <code>auto</code>:",
        askfw="Send:\n<code>1.2.3.4</code> or <code>1.2.3.0/24</code> or a country code like <code>RU</code>\nDefault: block. To allow: <code>allow 1.2.3.4</code>\nFor challenge: <code>challenge RU</code>",
    ),
}

TOGGLES = [("always_use_https", "Always HTTPS"), ("ipv6", "IPv6"), ("brotli", "Brotli"), ("http3", "HTTP/3")]
LEVELS = ["essentially_off", "low", "medium", "high", "under_attack"]

db = json.load(open(DBF)) if os.path.exists(DBF) else {"accounts": [], "lang": {}}
save = lambda: json.dump(db, open(DBF, "w"), ensure_ascii=False, indent=1)
lang = lambda uid: db["lang"].get(str(uid), "fa")
isadmin = lambda uid: uid in ADMINS or uid in db.get("admins", [])
t = lambda uid, k: T[lang(uid)][k]
norm = lambda s: re.sub(r"^[^\w]+", "", s).strip()
MENU = {norm(T[l][k]): v for l in T for k, v in (("m_acc", "acc"), ("m_zone", "zones"), ("m_add", "addtok"), ("m_set", "set"))}


OK = {"text": True, "btn": True}  # flipped to False if Telegram rejects custom emoji
eid = lambda k: (db.get("emo") or {}).get(k) or EMO[k][0]


CUR, BUF = "", []  # current screen name + elements rendered on it (for design mode)


def e(k):
    """Emoji inside text. Each screen+emoji is its own customizable slot."""
    f = EMO[k][1]; slot = f"{CUR}.t.{k}"; BUF.append((slot, f, "txt"))
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
    if bid: BUF.append((bid, x["text"] or (EMO[emo][1] if emo else "•"), "btn"))
    return x


b = lambda text, data, style=None, emo=None: {**rb(text, style, emo, f"{CUR}.{data.partition(':')[0]}"), "callback_data": data}
kb = lambda rows: {"inline_keyboard": rows}


def menu(uid):  # persistent bottom keyboard (not glass/inline)
    L = lambda k, s, em: rb(t(uid, k), s, em, "menu." + k)
    return {"keyboard": [[L("m_acc", "primary", "cloud"), L("m_zone", "primary", "globe")],
                         [L("m_add", "success", "plus"), L("m_set", None, "gear")]],
            "resize_keyboard": True, "is_persistent": True, "input_field_placeholder": "CF Control"}


async def tg(m, **p):
    return (await H.post(TG + m, json=p)).json()


def tok(uid):
    return db["accounts"][S[uid]["acc"]]["token"]


async def C(uid, method, path, **kw):
    r = await H.request(method, CF + path, headers={"Authorization": f"Bearer {tok(uid)}"}, **kw)
    return r.json()


errtxt = lambda j: (j.get("errors") or [{"message": "error"}])[0]["message"]
ttltxt = lambda r: "auto" if r.get("ttl") == 1 else str(r.get("ttl"))
chunk = lambda l, n: [l[i:i + n] for i in range(0, len(l), n)]


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
        print("send failed:", r.get("description"))


async def ping(a):
    t0 = time.monotonic()
    try:
        r = (await H.get(CF + "/zones?per_page=1", headers={"Authorization": f"Bearer {a['token']}"}, timeout=15)).json()
    except Exception as ex:
        return a["name"], False, type(ex).__name__, int((time.monotonic() - t0) * 1000)
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


def recline(i, r):
    px = (" " + e("cloud")) if r.get("proxied") else ""
    return (f"<b>{i}.</b> <code>{r['type']}</code>  {html.escape(r['name'])}\n"
            f"      ↳ <code>{html.escape(str(r['content'])[:60])}</code>{px}")


def pager(uid, p, tp, pre):
    row = []
    if p > 1: row.append(b(t(uid, "prev"), f"{pre}p:{p-1}"))
    if tp > 1: row.append(b(f"{p}/{tp}", "noop"))
    if p < tp: row.append(b(t(uid, "next"), f"{pre}n:{p+1}"))
    return row


async def view(uid, v):
    global CUR
    st = S[uid]; z = st.get("zone")
    zn = html.escape(st.get("zones", {}).get(z, ""))
    bk = lambda d: [b(t(uid, "back"), d, emo="back")]
    if v in ("zones", "zone", "dns", "rec", "dq", "ssl", "sec", "tog", "fw") and "acc" not in st:
        v = "acc"
    if v in ("zone", "dns", "rec", "dq", "ssl", "sec", "tog", "fw") and not z:
        v = "zones"

    if v in ("cz", "cz1") and not st.get("scr"):
        v = "set"
    if v == "cz1" and st.get("sel") is None:
        v = "cz"
    if v == "adm" and uid not in ADMINS:
        v = "set"
    CUR = v; BUF.clear()

    if v == "home":
        return t(uid, "welcome"), kb([])
    if v == "adm":
        extra = db.get("admins", [])
        txt = (f"{e('user')} <b>{t(uid,'adm')}</b>\n\n"
               + "\n".join(f"{e('crown')} <code>{i}</code> · {t(uid,'owner')}" for i in sorted(ADMINS))
               + ("\n" + "\n".join(f"{e('user')} <code>{i}</code>" for i in extra) if extra else "")
               + f"\n\n<i>{t(uid,'adm_note')}</i>")
        rows = [[b(f"{t(uid,'delete')} {i}", f"ax:{i}", "danger", "trash")] for i in extra]
        rows.append([b(t(uid, "adm_add"), "ad", "success", "plus")])
        return txt, kb(rows + [bk("set")])
    if v == "chk":
        res = await asyncio.gather(*(ping(a) for a in db["accounts"]))
        lines = [f"{e('green') if ok_ else e('red')} <b>{html.escape(n)}</b>\n      {html.escape(d)} · {ms}ms" for n, ok_, d, ms in res]
        return (f"{e('bolt')} <b>{t(uid,'chk_title')}</b>\n\n" + ("\n".join(lines) or t(uid, "empty")),
                kb([[b(t(uid, "chk"), "chk", "primary", "bolt")], bk("acc")]))

    if v == "cz":
        rows = chunk([b(("📝 " if k == "txt" else "") + lbl, f"cz1:{n}", "primary" if k == "btn" else None)
                      for n, (bid, lbl, k) in enumerate(st["scr"])], 2)
        return f"🎨 <b>{t(uid,'design')}</b>\n\n{t(uid,'cz_hint')}", kb(rows + [bk(st["scr_v"])])
    if v == "cz1":
        bid, lbl, k = st["scr"][st["sel"]]
        ov = (db.get("btn") or {}).get(bid, {})
        em = ov.get("uni") or ("—" if ov.get("emo") == "x" else ("premium …" + ov["emo"][-5:] if ov.get("emo") else "default"))
        txt = (f"🎨 <b>{html.escape(lbl)}</b>\n<code>{bid}</code>\n"
               + (f"{t(uid,'c_style')}: {ov.get('style','default')}\n" if k == "btn" else "") + f"{t(uid,'c_emoji')}: {em}")
        rows = []
        if k == "btn":
            rows.append([b(t(uid, "c_blue"), "cs:primary", "primary"), b(t(uid, "c_green"), "cs:success", "success"), b(t(uid, "c_red"), "cs:danger", "danger")])
            rows.append([b(t(uid, "c_def"), "cs:none")])
        rows.append([b(t(uid, "c_emo"), "ce", "primary", "edit"), b(t(uid, "c_none"), "cx", None, "trash")])
        rows.append([b(t(uid, "c_reset"), "cr", "danger")])
        return txt, kb(rows + [bk("cz")])

    if v == "set":
        return f"{e('gear')} <b>{t(uid,'m_set')}</b>", kb(([[b(t(uid, "adm"), "adm", "primary", "user")]] if uid in ADMINS else []) + [[b(t(uid, "lang"), "lang", "primary")],
                                                          [b(t(uid, "emo"), "emo", "primary", "bolt")],
                                                          [b(t(uid, "design") + (" ✅" if db.get("design") else ""), "design", "success" if db.get("design") else None, "edit")],
                                                          [b(t(uid, "czm"), "czm", "primary", "gear")]])
    if v == "emo":
        have = sum(1 for k in EMO if eid(k))
        return (f"{e('bolt')} <b>{t(uid,'emo')}</b>  ({have}/{len(EMO)})\n\n{t(uid,'emo_info')}\n\n"
                + "  ".join(f"{EMO[k][1]}{'✅' if eid(k) else '▫️'}" for k in EMO),
                kb([[b(t(uid, "emo_set"), "emoset", "success", "edit"), b(t(uid, "emo_test"), "emotest", "primary", "ok")],
                    [b(t(uid, "emo_reset"), "emoreset", "danger", "trash")], bk("set")]))
    if v == "ask":
        return f"{e('edit')} {st['prompt']}", kb([bk(st["back"])])
    if v == "addtok":
        return f"{e('plus')} {t(uid,'addtok')}", kb([bk("acc")])

    if v == "acc":
        rows = [[b(a["name"], f"a:{i}", "primary", "cloud"), b(t(uid, "delete"), f"x:{i}", "danger", "trash")]
                for i, a in enumerate(db["accounts"])]
        rows.append([b(t(uid, "m_add"), "add", "success", "plus")])
        if db["accounts"]: rows.append([b(t(uid, "chk"), "chk", "primary", "bolt")])
        return f"{e('cloud')} <b>{t(uid,'accs')}</b>\n" + ("" if db["accounts"] else t(uid, "empty")), kb(rows)

    if v == "zones":
        p = st.setdefault("zpage", 1)
        j = await C(uid, "GET", f"/zones?per_page=10&page={p}")
        zs = j.get("result") or []; info = j.get("result_info") or {}; tp = info.get("total_pages") or 1
        st.setdefault("zones", {}).update({x["id"]: x["name"] for x in zs})
        txt = f"{e('globe')} <b>{t(uid,'zones')}</b> ({info.get('total_count', len(zs))})\n\n" + "\n".join(
            f"{e('green') if x['status']=='active' else e('yellow')} <code>{html.escape(x['name'])}</code>" for x in zs)
        if not zs:
            txt += t(uid, "none") if j.get("success") else errtxt(j)
        rows = chunk([b(x["name"], f"z:{x['id']}", "primary", "globe") for x in zs], 2)
        pr = pager(uid, p, tp, "zg")
        if pr: rows.append(pr)
        rows.append(bk("home"))
        return txt, kb(rows)

    if v == "zone":
        zi = (await C(uid, "GET", f"/zones/{z}")).get("result") or {}
        s = {x["id"]: x["value"] for x in (await C(uid, "GET", f"/zones/{z}/settings")).get("result") or []}
        ua = s.get("security_level") == "under_attack"; dev = s.get("development_mode") == "on"
        txt = (f"{e('globe')} <b>{zn}</b>\n<blockquote>"
               f"{e('green') if zi.get('status')=='active' else e('yellow')} {zi.get('status','?')} · {zi.get('plan',{}).get('name','')}\n"
               f"{e('lock')} SSL: <code>{s.get('ssl','?')}</code>\n"
               f"{e('shield')} Security: <code>{s.get('security_level','?')}</code>\n"
               f"{e('dev')} Dev mode: {'ON' if dev else 'OFF'}\n"
               f"{e('tag')} NS: <code>{html.escape(', '.join(zi.get('name_servers') or []))}</code></blockquote>")
        return txt, kb([
            [b(t(uid, "dns"), "dns", "primary", "dns"), b(t(uid, "ssl"), "ssl", "primary", "lock")],
            [b(t(uid, "sec"), "sec", "primary", "shield"), b(t(uid, "tog"), "tog", "primary", "bolt")],
            [b(t(uid, "ua"), "ua", "danger" if ua else None, "fire"), b(t(uid, "dev"), "dev", "success" if dev else None, "dev")],
            [b(t(uid, "fw"), "fw", "primary", "ban"), b(t(uid, "export"), "ex", None, "export")],
            [b(t(uid, "purge"), "pc", "danger", "trash"), b(t(uid, "zdel"), "zdel", "danger", "ban")],
            bk("zones")])

    if v == "dns":
        p = st.setdefault("page", 1)
        j = await C(uid, "GET", f"/zones/{z}/dns_records?per_page=8&page={p}&order=type")
        rs = j.get("result") or []; tp = (j.get("result_info") or {}).get("total_pages") or 1
        txt = f"{e('dns')} <b>{t(uid,'dns')}</b> · {zn}   ({p}/{tp})\n\n" + ("\n".join(recline(i, r) for i, r in enumerate(rs, 1)) or t(uid, "none"))
        rows = chunk([b(str(i), f"r:{r['id']}", "primary") for i, r in enumerate(rs, 1)], 4)
        nav = pager(uid, p, tp, "dg")
        if nav: rows.append(nav)
        rows.append([b(t(uid, "new"), "new", "success", "plus")])
        rows.append(bk("zone"))
        return txt, kb(rows)

    if v in ("rec", "dq"):
        r = (await C(uid, "GET", f"/zones/{z}/dns_records/{st['rec']}")).get("result") or {}
        txt = (f"{e('dns')} <b>{r.get('type')}</b>\n<blockquote>"
               f"{e('tag')} <code>{html.escape(r.get('name',''))}</code>\n"
               f"{e('target')} <code>{html.escape(str(r.get('content','')))}</code>\n"
               f"{e('time')} TTL: {ttltxt(r)}\n{e('cloud')} Proxy: {'ON' if r.get('proxied') else 'OFF'}</blockquote>")
        if v == "dq":
            return txt + f"\n{e('warn')} {t(uid,'sure')}", kb([[b(t(uid, "yes"), "dd", "danger", "trash"), b(t(uid, "cancel"), "rec")]])
        row2 = [b(t(uid, "e_ttl"), "ed:ttl", None, "edit")]
        if r.get("type") in ("A", "AAAA", "CNAME"):
            row2.append(b(t(uid, "proxy"), "px", "success" if r.get("proxied") else None, "cloud"))
        return txt, kb([[b(t(uid, "e_content"), "ed:content", "primary", "edit"), b(t(uid, "e_name"), "ed:name", "primary", "edit")],
                        row2, [b(t(uid, "delete"), "dq", "danger", "trash")], bk("dns")])

    if v == "ssl":
        cur = ((await C(uid, "GET", f"/zones/{z}/settings/ssl")).get("result") or {}).get("value")
        rows = [[b(m, f"ss:{m}", "success" if m == cur else None, "ok" if m == cur else "lock")] for m in ("off", "flexible", "full", "strict")]
        return f"{e('lock')} <b>{t(uid,'ssl')}</b> · {zn}", kb(rows + [bk("zone")])

    if v == "sec":
        cur = ((await C(uid, "GET", f"/zones/{z}/settings/security_level")).get("result") or {}).get("value")
        rows = [[b(m, f"sc:{m}", ("danger" if m == "under_attack" else "success") if m == cur else None, "ok" if m == cur else "shield")] for m in LEVELS]
        return f"{e('shield')} <b>{t(uid,'sec')}</b> · {zn}", kb(rows + [bk("zone")])

    if v == "tog":
        s = {x["id"]: x["value"] for x in (await C(uid, "GET", f"/zones/{z}/settings")).get("result") or []}
        rows = chunk([b(n + (" ✅" if s.get(k) == "on" else " ▫️"), f"tg:{k}", "success" if s.get(k) == "on" else None) for k, n in TOGGLES], 2)
        return f"{e('bolt')} <b>{t(uid,'tog')}</b> · {zn}", kb(rows + [bk("zone")])

    if v == "fw":
        j = await C(uid, "GET", f"/zones/{z}/firewall/access_rules/rules?per_page=10")
        rs = j.get("result") or []
        icon = lambda m: e("ban") if m == "block" else e("ok") if m == "whitelist" else e("puzzle")
        txt = f"{e('ban')} <b>{t(uid,'fw')}</b> · {zn}\n\n" + ("\n".join(
            f"<b>{i}.</b> {icon(r['mode'])} <code>{html.escape(r['configuration']['value'])}</code> <i>{html.escape(r.get('notes') or '')}</i>"
            for i, r in enumerate(rs, 1)) or (t(uid, "none") if j.get("success") else errtxt(j)))
        rows = chunk([b(f"🗑 {i}", f"fd:{r['id']}", "danger") for i, r in enumerate(rs, 1)], 5)
        rows.append([b(t(uid, "block"), "fn", "success", "plus")])
        return txt, kb(rows + [bk("zone")])
    return await view(uid, "acc")


def uniq(buf):
    seen, out = set(), []
    for bid, lbl, k in buf:
        if bid not in seen:
            seen.add(bid); out.append((bid, lbl, k))
    return out


async def render(uid, cid, mid, v):
    text, markup = await view(uid, v)
    if CUR != "home" and not any(bt.get("callback_data") == "home" for row in markup["inline_keyboard"] for bt in row):
        markup["inline_keyboard"].append([b(t(uid, "home"), "home", "primary", "cloud")])
    if db.get("design") and CUR not in ("cz", "cz1", "ask"):
        st = S[uid]; st["scr"] = uniq(BUF); st["scr_v"] = CUR; st["sel"] = None
        markup["inline_keyboard"].append([{"text": "🎨 " + t(uid, "cz_btn"), "callback_data": "cz", "style": "primary"}])
    await show(cid, mid, text, markup)


async def remenu(cid, uid):
    await send_menu(cid, uid, "🎨 ✅")


async def cb(q):
    uid = q["from"]["id"]
    if not isadmin(uid):
        return
    m = q["message"]; cid = m["chat"]["id"]; st = S.setdefault(uid, {}); st["wait"] = None
    a, _, x = q["data"].partition(":"); z = st.get("zone"); note = None; v = "acc"
    ok = lambda j: t(uid, "done") if j.get("success") else errtxt(j)
    P = lambda k, val: C(uid, "PATCH", f"/zones/{z}/settings/{k}", json={"value": val})
    G = lambda k: C(uid, "GET", f"/zones/{z}/settings/{k}")
    R = f"/zones/{z}/dns_records/"
    rec = st.get("rec", "")

    if a == "noop":
        await tg("answerCallbackQuery", callback_query_id=q["id"]); return
    if a == "lang":
        db["lang"][str(uid)] = "en" if lang(uid) == "fa" else "fa"; save()
        await send_menu(cid, uid, t(uid, "welcome"))
        v = "set"
    elif a == "emoset":
        st.update(wait="emo", back="emo", prompt=t(uid, "emo_ask") + "\n\n" + " ".join(EMO[k][1] for k in EMO)); v = "ask"
    elif a == "emotest":
        note = None
        await tg("sendMessage", chat_id=cid, text=await probe(cid)); v = "emo"
    elif a == "emoreset":
        db["emo"] = {}; save(); OK.update(text=True, btn=True); v = "emo"
    elif a == "design":
        db["design"] = not db.get("design"); save(); v = "set"
    elif a == "czm":
        st["scr"] = [(f"menu.{k}", t(uid, k), "btn") for k in ("m_acc", "m_zone", "m_add", "m_set")]; st["scr_v"] = "set"; v = "cz"
    elif a == "cz1":
        st["sel"] = int(x); v = "cz1"
    elif a in ("cs", "cx", "cr"):
        bid = st["scr"][st["sel"]][0]
        if a == "cr":
            (db.get("btn") or {}).pop(bid, None)
        else:
            o = db.setdefault("btn", {}).setdefault(bid, {})
            if a == "cs": o["style"] = x
            else: o.pop("uni", None); o["emo"] = "x"
        save()
        if bid.startswith("menu."): await remenu(cid, uid)
        v = "cz1"
    elif a == "ce":
        st.update(wait="czemo", prompt=t(uid, "c_ask"), back="cz1"); v = "ask"
    elif a in ("home", "adm", "chk", "cz", "ask", "emo", "set", "acc", "zones", "ssl", "sec", "tog", "fw", "zone", "rec", "dq"):
        v = a
    elif a == "dns":
        st["page"] = 1; v = "dns"
    elif a == "add":
        st["wait"] = "token"; v = "addtok"
    elif a == "a":
        st["acc"] = int(x); st.pop("zone", None); st["zones"] = {}; st["zpage"] = 1; v = "zones"
    elif a == "x":
        del db["accounts"][int(x)]; save(); st.pop("acc", None); st.pop("zone", None); v = "acc"
    elif a == "z":
        st["zone"] = x; v = "zone"
    elif a == "r":
        st["rec"] = x; v = "rec"
    elif a in ("dgp", "dgn"):
        st["page"] = int(x); v = "dns"
    elif a in ("zgp", "zgn"):
        st["zpage"] = int(x); v = "zones"
    elif a == "ad" and uid in ADMINS:
        st.update(wait="adm", prompt=t(uid, "adm_ask"), back="adm"); v = "ask"
    elif a == "ax" and uid in ADMINS:
        if int(x) in db.get("admins", []): db["admins"].remove(int(x)); save()
        v = "adm"
    elif a == "px":
        r = (await C(uid, "GET", R + rec))["result"]
        note = ok(await C(uid, "PATCH", R + rec, json={"proxied": not r["proxied"]})); v = "rec"
    elif a == "dd":
        note = ok(await C(uid, "DELETE", R + rec)); v = "dns"
    elif a == "ed":
        st.update(wait="edit", field=x, prompt=t(uid, "ask_" + x), back="rec"); v = "ask"
    elif a == "new":
        st.update(wait="dns", prompt=t(uid, "adddns"), back="dns"); v = "ask"
    elif a == "zdel":
        st.update(wait="zdel", prompt=t(uid, "zdel_ask").format(html.escape(st["zones"].get(z, ""))), back="zone"); v = "ask"
    elif a == "fn":
        st.update(wait="fw", prompt=t(uid, "askfw"), back="fw"); v = "ask"
    elif a == "fd":
        note = ok(await C(uid, "DELETE", f"/zones/{z}/firewall/access_rules/rules/{x}")); v = "fw"
    elif a == "ss":
        note = ok(await P("ssl", x)); v = "ssl"
    elif a == "sc":
        note = ok(await P("security_level", x)); v = "sec"
    elif a == "tg":
        cur = (await G(x))["result"]["value"]; note = ok(await P(x, "off" if cur == "on" else "on")); v = "tog"
    elif a == "ua":
        cur = (await G("security_level"))["result"]["value"]
        note = ok(await P("security_level", "medium" if cur == "under_attack" else "under_attack")); v = "zone"
    elif a == "dev":
        cur = (await G("development_mode"))["result"]["value"]
        note = ok(await P("development_mode", "off" if cur == "on" else "on")); v = "zone"
    elif a == "pc":
        note = ok(await C(uid, "POST", f"/zones/{z}/purge_cache", json={"purge_everything": True})); v = "zone"
    elif a == "ex":
        r = await H.get(CF + f"/zones/{z}/dns_records/export", headers={"Authorization": f"Bearer {tok(uid)}"})
        await H.post(TG + "sendDocument", data={"chat_id": cid}, files={"document": (st["zones"][z] + ".dns.txt", r.content)})
        note = t(uid, "done"); v = "zone"
    await tg("answerCallbackQuery", callback_query_id=q["id"], **({"text": note} if note else {}))
    await render(uid, cid, m["message_id"], v)


async def msg(m):
    uid = m["from"]["id"]
    if not isadmin(uid):
        return
    cid = m["chat"]["id"]; st = S.setdefault(uid, {}); txt = (m.get("text") or "").strip()
    ids = [en for en in m.get("entities", []) if en["type"] == "custom_emoji"]
    if st.get("wait") == "czemo" and (ids or txt):
        st["wait"] = None
        bid = st["scr"][st["sel"]][0]
        o = db.setdefault("btn", {}).setdefault(bid, {}); o.pop("emo", None); o.pop("uni", None)
        if ids: o["emo"] = sorted(ids, key=lambda en: en["offset"])[0]["custom_emoji_id"]
        else: o["uni"] = txt[:8]
        save()
        if bid.startswith("menu."): await remenu(cid, uid)
        await render(uid, cid, None, "cz1"); return
    if ids and st.get("wait") == "emo":
        st["wait"] = None
        found = [en["custom_emoji_id"] for en in sorted(ids, key=lambda en: en["offset"])]
        db.setdefault("emo", {}).update(dict(zip(EMO, found))); save(); OK.update(text=True, btn=True)
        await tg("sendMessage", chat_id=cid, text=f"✅ {len(found)}/{len(EMO)}\n" + await probe(cid))
        await render(uid, cid, None, "emo"); return
    if ids:  # helper: reveal premium emoji IDs
        await tg("sendMessage", chat_id=cid, parse_mode="HTML", text="\n".join(f"<code>{en['custom_emoji_id']}</code>" for en in ids))
        return
    w = st.get("wait"); st["wait"] = None; z = st.get("zone"); n = norm(txt)
    send = lambda v: view(uid, v)
    err = lambda j: tg("sendMessage", chat_id=cid, text="❌ " + errtxt(j))

    if txt.startswith("/start"):
        await send_menu(cid, uid, t(uid, "welcome")); return
    if n in MENU:
        v = MENU[n]
        if v == "zones" and "acc" not in st:
            if len(db["accounts"]) == 1: st["acc"] = 0
            else: v = "acc"
        if v == "addtok": st["wait"] = "token"
        await render(uid, cid, None, v); return

    if w == "token":
        await tg("deleteMessage", chat_id=cid, message_id=m["message_id"])  # hide the token
        r = (await H.get(CF + "/zones?per_page=1", headers={"Authorization": f"Bearer {txt}"})).json()
        if r.get("success"):
            name = r["result"][0]["account"]["name"] if r.get("result") else f"Account {len(db['accounts'])+1}"
            db["accounts"].append({"name": name, "token": txt}); save()
            await tg("sendMessage", chat_id=cid, text="✅ " + t(uid, "saved")); v = "acc"
        else:
            await tg("sendMessage", chat_id=cid, text="❌ " + t(uid, "bad")); return
    elif w == "dns":
        p = txt.split()
        try:
            j = await C(uid, "POST", f"/zones/{z}/dns_records", json={
                "type": p[0].upper(), "name": p[1], "content": p[2], "ttl": 1,
                "proxied": len(p) > 3 and p[3].lower() in ("1", "true", "yes")})
            if not j.get("success"): await err(j)
        except IndexError:
            pass
        v = "dns"
    elif w == "edit":
        f = st["field"]
        try:
            val = (1 if txt.lower() in ("auto", "1") else int(txt)) if f == "ttl" else txt
            j = await C(uid, "PATCH", f"/zones/{z}/dns_records/{st['rec']}", json={f: val})
            if not j.get("success"): await err(j)
        except ValueError:
            pass
        v = "rec"
    elif w == "zdel":
        name = st.get("zones", {}).get(z, "")
        if txt.lower() != name.lower():
            await tg("sendMessage", chat_id=cid, text=t(uid, "zdel_bad")); v = "zone"
        else:
            j = await C(uid, "DELETE", f"/zones/{z}")
            if j.get("success"):
                await tg("sendMessage", chat_id=cid, text="✅ " + name + " — " + t(uid, "done")); st.pop("zone", None); v = "zones"
            else:
                await err(j); v = "zone"
    elif w == "adm":
        if uid in ADMINS and txt.isdigit():
            n = int(txt)
            if n not in ADMINS and n not in db.setdefault("admins", []): db["admins"].append(n); save()
            await tg("sendMessage", chat_id=cid, text="✅ " + t(uid, "adm_ok"))
            await send_menu(n, n, T["fa"]["welcome"])  # silently ignored if they never started the bot
        else:
            await tg("sendMessage", chat_id=cid, text="❌ " + t(uid, "adm_bad"))
        v = "adm"
    elif w == "fw":
        p = txt.split(); mode = "block"
        if len(p) > 1 and p[0].lower() in ("allow", "block", "challenge"):
            mode = {"allow": "whitelist"}.get(p[0].lower(), p[0].lower()); p = p[1:]
        val = p[0] if p else ""
        tgt = "ip_range" if "/" in val else "country" if re.fullmatch(r"[A-Za-z]{2}", val) else "ip"
        j = await C(uid, "POST", f"/zones/{z}/firewall/access_rules/rules", json={
            "mode": mode, "configuration": {"target": tgt, "value": val.upper() if tgt == "country" else val},
            "notes": " ".join(p[1:])})
        if not j.get("success"): await err(j)
        v = "fw"
    else:
        await send_menu(cid, uid, t(uid, "welcome")); return
    await render(uid, cid, None, v)


async def main():
    off = 0
    while True:
        try:
            r = await tg("getUpdates", offset=off, timeout=50, allowed_updates=["message", "callback_query"])
            for u in r.get("result", []):
                off = u["update_id"] + 1
                try:
                    if "callback_query" in u: await cb(u["callback_query"])
                    elif "message" in u: await msg(u["message"])
                except Exception as ex:
                    print("handler error:", repr(ex))
        except Exception as ex:
            print("poll error:", repr(ex)); await asyncio.sleep(3)


asyncio.run(main())
