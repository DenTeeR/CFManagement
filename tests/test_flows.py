"""End-to-end flows through the bot against the fakes: bugs that were fixed and safety rules that must hold."""
import asyncio, json, os, stat

import httpx

from conftest import ADMIN, GOOD, OWNER, arun


def last_json(cf, method, suffix):
    return next(b for m, p, b in reversed(cf.log) if m == method and p.endswith(suffix))


# ───────────── accounts & storage ─────────────
@arun
async def test_add_account_hides_token_and_stores_it_privately(bot):
    await bot.text("/start"); await bot.text("➕ افزودن حساب")
    text, buttons, _ = await bot.text(GOOD)
    assert ("deleteMessage", {"chat_id": OWNER, "message_id": 1000 + bot.n}) in bot.tg.calls
    acc = bot.b.db["accounts"][0]
    assert acc["name"] == "Acme" and acc["token"] == GOOD and len(acc["id"]) == 8
    assert stat.S_IMODE(os.stat(bot.b.DBF).st_mode) == 0o600
    assert any(b["text"].endswith("Acme") for b in buttons)
    # same token again is refused
    await bot.text("➕ افزودن حساب"); await bot.text(GOOD)
    assert len(bot.b.db["accounts"]) == 1 and "قبلاً" in bot.texts()


@arun
async def test_invalid_token_is_rejected(bot):
    await bot.text("➕ افزودن حساب"); await bot.text("bad_token_0123456789abcdefghij")
    assert not bot.b.db["accounts"] and "نامعتبر" in bot.texts()


@arun
async def test_removing_an_account_needs_confirmation(bot):
    await bot.login(); await bot.text("☁️ حساب‌ها")
    text, buttons, _ = await bot.tap("x")
    assert "Acme" in text and len(bot.b.db["accounts"]) == 1      # nothing removed yet
    await bot.tap("انصراف")
    assert len(bot.b.db["accounts"]) == 1
    await bot.tap("x"); await bot.tap("y")
    assert bot.b.db["accounts"] == []


@arun
async def test_selected_account_survives_removal_of_another(bot):
    """Accounts are addressed by id, so removing one can never make someone act on a different one."""
    b = bot.b
    b.db["accounts"] = [{"id": "aaaa1111", "name": "First", "token": "good_first_0123456789abcdef"},
                        {"id": "bbbb2222", "name": "Second", "token": "good_second_0123456789abcde"}]
    b.db["admins"] = [ADMIN]
    bot.as_user(ADMIN); await bot.text("☁️ حساب‌ها"); await bot.tap("Second")
    bot.as_user(OWNER); await bot.text("☁️ حساب‌ها"); await bot.tap("x:aaaa1111"); await bot.tap("y")
    bot.as_user(ADMIN)
    assert b.acc_of(ADMIN)["name"] == "Second"
    # and when the selected one itself is removed, the user is told instead of silently switched
    bot.as_user(OWNER); await bot.tap("x:bbbb2222"); await bot.tap("y")
    bot.as_user(ADMIN); text, _, _ = await bot.text("🌐 دامنه‌ها")
    assert "هنوز حسابی" in text


def test_tokens_are_encrypted_when_a_key_is_set(tmp_path, monkeypatch):
    import importlib, sys
    from cryptography.fernet import Fernet
    key = Fernet.generate_key().decode()
    (tmp_path / "data.json").write_text(json.dumps({"accounts": [{"name": "Old", "token": "plain_token_0123456789abcdefgh"}], "lang": {}}))
    os.chmod(tmp_path / "data.json", 0o644)
    monkeypatch.setenv("BOT_TOKEN", "1:T"); monkeypatch.setenv("ADMIN_IDS", "1"); monkeypatch.setenv("CFBOT_DIR", str(tmp_path))
    monkeypatch.setenv("DATA_KEY", key); sys.modules.pop("cfbot", None)
    mod = importlib.import_module("cfbot")
    stored = json.loads((tmp_path / "data.json").read_text())["accounts"][0]
    assert stored["token"].startswith("enc:") and "plain_token" not in (tmp_path / "data.json").read_text()
    assert stored["id"] and mod.dec(stored["token"]) == "plain_token_0123456789abcdefgh"
    assert stat.S_IMODE(os.stat(tmp_path / "data.json").st_mode) == 0o600      # old world-readable file is tightened
    # without the key the bot still starts and reports the problem instead of crashing
    monkeypatch.delenv("DATA_KEY"); sys.modules.pop("cfbot", None)
    mod = importlib.import_module("cfbot")
    try:
        mod.dec(mod.db["accounts"][0]["token"]); raise AssertionError("should not decrypt")
    except mod.Stop as ex:
        assert ex.args[0] == "nokey"
    sys.modules.pop("cfbot", None)


def test_damaged_data_file_is_kept_aside(tmp_path, monkeypatch):
    import importlib, sys
    (tmp_path / "data.json").write_text('{"accounts": [{"name": "x", "tok')
    monkeypatch.setenv("BOT_TOKEN", "1:T"); monkeypatch.setenv("ADMIN_IDS", "1"); monkeypatch.setenv("CFBOT_DIR", str(tmp_path))
    monkeypatch.delenv("DATA_KEY", raising=False); sys.modules.pop("cfbot", None)
    mod = importlib.import_module("cfbot")
    assert mod.db["accounts"] == [] and [p for p in os.listdir(tmp_path) if ".corrupt-" in p]
    mod.save()
    assert json.loads((tmp_path / "data.json").read_text())["accounts"] == [] and not os.path.exists(tmp_path / "data.json.tmp")
    sys.modules.pop("cfbot", None)


# ───────────── DNS ─────────────
@arun
async def test_dns_records_with_spaces_priority_and_data(bot):
    await bot.login(); await bot.tap("dns"); await bot.tap("new")
    await bot.text("TXT @ v=spf1 include:_spf.google.com ~all")
    await bot.tap("new"); await bot.text("MX @ 10 mail.example.com")
    await bot.tap("new"); await bot.text("SRV _sip._tcp 10 5 5060 sip.example.com")
    recs = {r["type"]: r for r in bot.cf.recs("example.com") if r["type"] in ("TXT", "MX", "SRV")}
    assert recs["TXT"]["content"] == '"v=spf1 include:_spf.google.com ~all"'
    assert recs["MX"]["priority"] == 10 and recs["MX"]["content"] == "mail.example.com"
    assert recs["SRV"]["data"]["port"] == 5060 and recs["SRV"]["name"] == "_sip._tcp.example.com"


@arun
async def test_bad_dns_input_is_explained_and_can_be_retried(bot):
    await bot.login(); await bot.tap("dns"); await bot.tap("new")
    n = len(bot.cf.recs("example.com"))
    await bot.text("A sub")
    assert "فرمت نادرست" in bot.texts() and len(bot.cf.recs("example.com")) == n
    await bot.text("A sub 1.2.3.4")                      # still waiting: no need to press "new" again
    assert any(r["name"] == "sub.example.com" for r in bot.cf.recs("example.com"))


@arun
async def test_cloudflare_error_on_add_is_shown(bot):
    await bot.login(); await bot.tap("dns"); await bot.tap("new")
    bot.cf.fail_all = (400, json.dumps({"success": False, "errors": [{"code": 81057, "message": "The record already exists."}]}).encode())
    await bot.text("A sub 1.2.3.4")
    assert "The record already exists." in bot.texts()


@arun
async def test_dns_search_type_filter_and_paging(bot):
    z = bot.cf.zid("example.com")
    for i in range(10):
        bot.cf.add_rec(z, "A", f"n{i}.example.com", "9.9.9.9")
    await bot.login(); text, buttons, _ = await bot.tap("dns")
    assert "(1/2)" in text
    await bot.tap("ds"); text, _, _ = await bot.text("blog")
    assert "blog.example.com" in text and "www.example.com" not in text and "(1/1)" in text
    text, _, _ = await bot.tap("dc")
    assert "(1/2)" in text
    await bot.tap("dnst"); text, _, _ = await bot.tap("dty:CNAME")
    assert "blog.example.com" in text and "n1.example.com" not in text


@arun
async def test_edit_record_fields(bot):
    await bot.login(); await bot.tap("dns")
    rec = next(r for r in bot.cf.recs("example.com") if r["name"] == "www.example.com")
    await bot.tap(None, raw=bot.button("r:" + rec["id"])["callback_data"])
    await bot.tap("ed:ttl"); await bot.text("5")
    assert rec["ttl"] == 1 and "TTL" in bot.texts()          # refused: out of range
    await bot.text("300"); assert rec["ttl"] == 300
    await bot.tap("ed:content"); await bot.text("8.8.8.8"); assert rec["content"] == "8.8.8.8"
    await bot.tap("ed:name"); await bot.text("web"); assert rec["name"] == "web.example.com"
    await bot.tap("px"); assert rec["proxied"] is True


@arun
async def test_deleting_a_record_needs_confirmation(bot):
    await bot.login(); await bot.tap("dns")
    rec = next(r for r in bot.cf.recs("example.com") if r["name"] == "www.example.com")
    await bot.tap(None, raw=bot.button("r:" + rec["id"])["callback_data"])
    text, _, _ = await bot.tap("dq")
    assert "www.example.com" in text and len(bot.cf.recs("example.com")) == 3
    await bot.tap("y")
    assert [r["name"] for r in bot.cf.recs("example.com")] == ["example.com", "blog.example.com"]


@arun
async def test_bulk_ip_replace_one_zone_and_all_zones(bot):
    await bot.login(); await bot.tap("dns"); await bot.tap("bk:z")
    text, _, _ = await bot.text("1.1.1.1 5.5.5.5")
    assert "<b>2</b>" in text and "www.example.com" in text                       # preview first
    assert all(r["content"] != "5.5.5.5" for r in bot.cf.recs("example.com"))
    await bot.tap("y")
    assert [r["content"] for r in bot.cf.recs("example.com")] == ["5.5.5.5", "5.5.5.5", "example.com"]
    assert bot.cf.recs("example.org")[0]["content"] == "1.1.1.1"                 # other zone untouched
    assert "2 از 2" in bot.texts(4)
    # whole account
    await bot.text("🌐 دامنه‌ها"); await bot.tap("bk:a"); await bot.text("1.1.1.1 6.6.6.6"); await bot.tap("y")
    assert bot.cf.recs("example.org")[0]["content"] == "6.6.6.6"
    await bot.tap("bk:a"); await bot.text("7.7.7.7 8.8.8.8")
    assert "پیدا نشد" in bot.texts()


@arun
async def test_export_and_import(bot):
    await bot.login(); await bot.tap("ex")
    name, body = bot.tg.docs[-1]
    assert name == "example.com.dns.txt" and b"www.example.com. 1 IN A 1.1.1.1" in body
    await bot.tap("im"); bot.tg.files["F1"] = b"new.example.com. 300 IN A 1.2.3.4\n"
    await bot.doc("F1")
    assert b"new.example.com. 300 IN A 1.2.3.4" in bot.cf.imports[-1] and "2 از 3" in bot.texts()
    await bot.tap("zone"); await bot.tap("im"); await bot.doc("F1", size=5 << 20)
    assert "۲ مگابایت" in bot.texts() and len(bot.cf.imports) == 1


# ───────────── outdated buttons ─────────────
@arun
async def test_old_button_never_acts_on_another_zone(bot):
    await bot.login(); await bot.tap("ssl")
    old = bot.button("ss:strict")["callback_data"]
    await bot.text("🌐 دامنه‌ها"); await bot.tap("example.org")
    text, _, _ = await bot.tap(None, raw=old)                # tap from the example.com SSL message
    assert "قدیمی" in bot.alert()
    assert bot.cf.settings[bot.cf.zid("example.org")]["ssl"] == "full" and bot.cf.settings[bot.cf.zid("example.com")]["ssl"] == "full"
    assert "example.org" in text                              # shown where they really are


@arun
async def test_old_button_never_acts_on_another_record(bot):
    await bot.login(); await bot.tap("dns")
    a, c = [r for r in bot.cf.recs("example.com") if r["type"] == "A"]
    await bot.tap(None, raw=bot.button("r:" + a["id"])["callback_data"])
    old = bot.button("px")["callback_data"]
    await bot.tap("dns"); await bot.tap(None, raw=bot.button("r:" + c["id"])["callback_data"])
    await bot.tap(None, raw=old)
    assert "قدیمی" in bot.alert() and c["proxied"] is False and a["proxied"] is True


@arun
async def test_buttons_from_before_a_restart_do_nothing(bot):
    await bot.login(); await bot.tap("dns")
    rec = bot.cf.recs("example.com")[1]
    await bot.tap(None, raw=bot.button("r:" + rec["id"])["callback_data"]); await bot.tap("dq")
    yes = bot.button("y")["callback_data"]
    bot.b.S.clear()                                           # bot restarted: memory is gone
    await bot.tap(None, raw=yes)
    assert len(bot.cf.recs("example.com")) == 3
    for legacy in ("ss:off", "dd", "pc", "x:0", "fd:" + "0" * 32):   # buttons of the pre-3.0 bot carry no context
        await bot.tap(None, raw=legacy)
    assert bot.cf.settings[bot.cf.zid("example.com")]["ssl"] == "full" and not bot.cf.purges and len(bot.b.db["accounts"]) == 1


@arun
async def test_confirmation_is_single_use_and_cancelled_by_navigation(bot):
    await bot.login(); await bot.tap("pc"); await bot.tap("pca")
    yes = bot.button("y")["callback_data"]
    await bot.tap("انصراف")
    await bot.tap(None, raw=yes)
    assert not bot.cf.purges and "منقضی" in bot.alert()
    await bot.tap("pc"); await bot.tap("pca"); yes = bot.button("y")["callback_data"]
    await bot.tap(None, raw=yes); await bot.tap(None, raw=yes)
    assert bot.cf.purges == [{"purge_everything": True}]


# ───────────── zone settings ─────────────
@arun
async def test_ssl_off_needs_confirmation_but_strict_does_not(bot):
    await bot.login(); z = bot.cf.zid("example.com")
    await bot.tap("ssl"); await bot.tap("ss:strict")
    assert bot.cf.settings[z]["ssl"] == "strict"
    await bot.tap("ss:off")
    assert bot.cf.settings[z]["ssl"] == "strict"
    await bot.tap("y")
    assert bot.cf.settings[z]["ssl"] == "off"


@arun
async def test_purge_by_url(bot):
    await bot.login(); await bot.tap("pc"); await bot.tap("pcu")
    await bot.text("https://example.com/a.css\nwww.example.com")
    assert bot.cf.purges == [{"files": ["https://example.com/a.css"]}, {"hosts": ["www.example.com"]}]


@arun
async def test_more_settings(bot):
    await bot.login(); z = bot.cf.zid("example.com"); s = bot.cf.settings[z]
    text, _, _ = await bot.tap("zs")
    assert "1.0" in text and "aggressive" in text
    await bot.tap("tls"); await bot.tap("tl:1.2"); assert s["min_tls_version"] == "1.2"
    await bot.tap("zs"); await bot.tap("cache"); await bot.tap("cl:basic"); assert s["cache_level"] == "basic"
    await bot.tap("zs"); await bot.tap("hsts"); await bot.tap("hs:en")
    assert s["security_header"]["strict_transport_security"]["enabled"] is False     # asks first
    await bot.tap("y")
    h = s["security_header"]["strict_transport_security"]
    assert h["enabled"] is True and h["max_age"] == 15552000
    await bot.tap("hs:sub"); await bot.tap("hs:a:31536000")
    h = s["security_header"]["strict_transport_security"]
    assert h["include_subdomains"] is True and h["max_age"] == 31536000 and h["enabled"] is True
    await bot.tap("zs"); await bot.tap("dsec"); text, _, _ = await bot.tap("dz:1")
    assert bot.cf.dnssec[z] == "pending" and "IN DS 2371" in text
    await bot.tap("dz:0"); assert bot.cf.dnssec[z] == "pending"
    await bot.tap("y"); assert bot.cf.dnssec[z] == "disabled"


@arun
async def test_quick_toggles_only_show_settings_the_zone_has(bot):
    await bot.login(); text, buttons, _ = await bot.tap("tog")
    labels = [b["text"] for b in buttons]
    assert any("TLS 1.3 ✅" in l for l in labels) and not any("Brotli" in l for l in labels)
    await bot.tap("tg:always_use_https")
    assert bot.cf.settings[bot.cf.zid("example.com")]["always_use_https"] == "on"


@arun
async def test_pause_add_search_and_delete_zone(bot):
    await bot.login(); z = bot.cf.zid("example.com")
    await bot.tap("zp"); assert bot.cf.zones[z]["paused"] is False
    await bot.tap("y"); assert bot.cf.zones[z]["paused"] is True
    await bot.tap("zp"); assert bot.cf.zones[z]["paused"] is False               # resuming is harmless: no question
    await bot.text("🌐 دامنه‌ها"); await bot.tap("zq"); text, buttons, _ = await bot.text("org")
    assert "example.org" in text and not any(b["text"].endswith("example.com") for b in buttons)
    await bot.tap("zqc"); await bot.tap("zadd"); await bot.text("not a domain")
    assert "معتبر نیست" in bot.texts()
    text, _, _ = await bot.text("New-Site.com")
    assert "new-site.com" in [v["name"] for v in bot.cf.zones.values()] and "ada.ns.cloudflare.com" in bot.texts()
    assert last_json(bot.cf, "POST", "/zones") == {"name": "new-site.com", "account": {"id": "a" * 32}, "type": "full"}
    await bot.tap("zdel"); await bot.text("wrong.com")
    assert "new-site.com" in [v["name"] for v in bot.cf.zones.values()]
    await bot.tap("zdel"); await bot.text("new-site.com")
    assert "new-site.com" not in [v["name"] for v in bot.cf.zones.values()]


@arun
async def test_analytics_screen(bot):
    await bot.login(); text, _, _ = await bot.tap("an")
    assert "3.0K" in text and "40%" in text and "6.0 MB" in text and "IR 67%" in text
    await bot.tap("anp:1")
    assert "httpRequests1hGroups" in last_json(bot.cf, "POST", "/graphql")["query"]


# ───────────── firewall & rules ─────────────
@arun
async def test_firewall_rules(bot):
    await bot.login(); z = bot.cf.zid("example.com")
    await bot.tap("fw"); await bot.tap("fn"); await bot.text("nonsense!")
    assert not bot.cf.rules[z] and "معتبر نیست" in bot.texts()
    await bot.text("AS13335 bad bots")
    assert list(bot.cf.rules[z].values())[0]["configuration"] == {"target": "asn", "value": "AS13335"}
    for i in range(12):
        await bot.tap("fn"); await bot.text(f"10.0.0.{i}")
    text, buttons, _ = bot.screen()
    assert "(1/2)" in text                                    # more than ten rules are reachable now
    text, _, _ = await bot.tap("fgn"); assert "10.0.0.11" in text
    rid = next(k for k, v in bot.cf.rules[z].items() if v["configuration"]["value"] == "10.0.0.11")
    await bot.tap("fd:" + rid); assert rid in bot.cf.rules[z]
    await bot.tap("y"); assert rid not in bot.cf.rules[z]


@arun
async def test_waf_rate_limit_and_redirect_rules(bot):
    await bot.login(); z = bot.cf.zid("example.com")
    await bot.tap("rl"); text, _, _ = await bot.tap("rs:w")
    assert "موردی نیست" in text                                # 404 from Cloudflare = no rules yet, not an error
    await bot.tap("rn"); await bot.text("nope"); assert "فرمت نادرست" in bot.texts()
    await bot.text('block (ip.src.country eq "RU")')
    rs = bot.cf.rulesets[(z, "http_request_firewall_custom")]
    assert rs["rules"][0]["action"] == "block"
    await bot.tap("rn"); await bot.text('managed_challenge (http.request.uri.path contains "/admin")')
    assert len(rs["rules"]) == 2 and last_json(bot.cf, "POST", "/rules")["action"] == "managed_challenge"
    await bot.tap("ru:" + rs["rules"][0]["id"]); await bot.tap("rt")
    assert rs["rules"][0]["enabled"] is False
    await bot.tap("rd"); assert len(rs["rules"]) == 2
    await bot.tap("y"); assert len(rs["rules"]) == 1
    await bot.tap("rl"); await bot.tap("rs:d"); await bot.tap("rn"); await bot.text("old.example.com https://new.example.com")
    assert bot.cf.rulesets[(z, "http_request_dynamic_redirect")]["rules"][0]["action"] == "redirect"
    await bot.tap("rl"); await bot.tap("rs:r"); await bot.tap("rn"); await bot.text('50 10 10 (http.request.uri.path contains "/login")')
    assert bot.cf.rulesets[(z, "http_ratelimit")]["rules"][0]["ratelimit"]["requests_per_period"] == 50


@arun
async def test_page_rules_and_worker_routes(bot):
    await bot.login(); z = bot.cf.zid("example.com")
    await bot.tap("rl"); await bot.tap("pr"); await bot.tap("prn"); await bot.text("example.com/old/* https://example.com/new/$1 302")
    rid, rule = next(iter(bot.cf.pagerules[z].items()))
    assert rule["actions"][0]["value"]["status_code"] == 302 and rule["status"] == "active"
    await bot.tap("prt:" + rid); assert rule["status"] == "disabled"
    await bot.tap("prd:" + rid); await bot.tap("y"); assert not bot.cf.pagerules[z]
    await bot.tap("rl"); await bot.tap("wr"); await bot.tap("wrn"); await bot.text("example.com/api/* my-worker")
    rid = next(iter(bot.cf.routes[z]))
    assert bot.cf.routes[z][rid] == {"id": rid, "pattern": "example.com/api/*", "script": "my-worker"}
    await bot.tap("wrd:" + rid); await bot.tap("y"); assert not bot.cf.routes[z]


@arun
async def test_services(bot):
    await bot.login(); await bot.text("🌐 دامنه‌ها"); await bot.tap("svc")
    text, _, _ = await bot.tap("wk"); assert "my-worker" in text
    await bot.tap("wk1:0"); await bot.tap("wkx"); assert bot.cf.scripts
    await bot.tap("y"); assert not bot.cf.scripts
    await bot.tap("svc"); text, _, _ = await bot.tap("pgs"); assert "site.pages.dev" in text
    text, _, _ = await bot.tap("pg1:0"); assert "failure" in text
    await bot.tap("pgr"); assert bot.cf.retries == [("site", "dep1")]
    await bot.tap("pgs"); await bot.tap("svc"); text, _, _ = await bot.tap("tn"); assert "healthy" in text
    text, _, _ = await bot.tap("tn1:0"); assert "198.51.100.7" in text and "FRA" in text


# ───────────── roles ─────────────
@arun
async def test_read_only_admin_can_look_but_not_change(bot):
    await bot.login(); b = bot.b
    await bot.text("⚙️ تنظیمات"); await bot.tap("adm"); await bot.tap("ad"); await bot.text(str(ADMIN))
    await bot.tap("am:" + str(ADMIN)); await bot.tap("amr")
    assert b.readonly(ADMIN) and not b.readonly(OWNER)
    bot.as_user(ADMIN); await bot.text("🌐 دامنه‌ها"); text, _, _ = await bot.tap("example.com")
    assert "SSL" in text
    text, _, _ = await bot.tap("dns"); assert "www.example.com" in text
    await bot.tap("new"); assert "فقط‌خواندنی" in bot.alert()
    await bot.tap("zone"); await bot.tap("ua"); assert "فقط‌خواندنی" in bot.alert()
    assert bot.cf.settings[bot.cf.zid("example.com")]["security_level"] == "medium"
    await bot.tap("ex"); assert bot.tg.docs                                   # reading (export) is allowed
    await bot.text("➕ افزودن حساب"); assert "اجازهٔ افزودن" in bot.texts()
    await bot.text("⚙️ تنظیمات"); _, buttons, _ = bot.screen()
    assert not any(x.get("callback_data", "").startswith(("adm", "design", "mon", "log")) for x in buttons)
    await bot.tap(None, raw="adm"); text, _, _ = bot.screen(); assert "ادمین‌ها" not in text
    await bot.tap(None, raw="ad"); assert "فقط مالک" in bot.alert()


@arun
async def test_admin_limited_to_some_accounts(bot):
    b = bot.b
    b.db["accounts"] = [{"id": "aaaa1111", "name": "First", "token": "good_first_0123456789abcdef"},
                        {"id": "bbbb2222", "name": "Second", "token": "good_second_0123456789abcde"}]
    b.db["admins"] = [ADMIN]
    await bot.text("⚙️ تنظیمات"); await bot.tap("adm"); await bot.tap("am:" + str(ADMIN)); await bot.tap("admc")
    await bot.tap("amt:aaaa1111")                              # un-tick First
    assert b.perm(ADMIN)["accs"] == ["bbbb2222"]
    bot.as_user(ADMIN); text, buttons, _ = await bot.text("☁️ حساب‌ها")
    assert [x["text"] for x in buttons if x["callback_data"].startswith("a:")] == ["☁️ Second"]
    assert not any(x["callback_data"].startswith(("x:", "add")) for x in buttons)   # cannot add/remove accounts
    await bot.tap(None, raw="a:aaaa1111"); assert "acc" not in b.S[ADMIN]
    bot.as_user(OWNER); await bot.tap("amall"); assert "accs" not in b.perm(ADMIN)
    await bot.tap("adm1"); await bot.tap("ax"); await bot.tap("y")
    assert ADMIN not in b.db["admins"] and str(ADMIN) not in b.db.get("perm", {})
    bot.as_user(ADMIN); n = len(bot.tg.calls); await bot.text("/start"); assert len(bot.tg.calls) == n   # ignored


# ───────────── errors, logging, background ─────────────
@arun
async def test_non_json_and_timeouts_become_readable_errors(bot):
    await bot.login(); ua, dns = bot.button("ua")["callback_data"], bot.button("dns")["callback_data"]
    bot.cf.fail_all = (502, b"<html>Bad gateway</html>")
    text, _, _ = await bot.tap(None, raw=dns); assert "HTTP 502" in text
    await bot.tap(None, raw=ua); assert "HTTP 502" in bot.alert()
    assert not any(m == "PATCH" for m, _, _ in bot.cf.log)       # a failed read never leads to a blind write

    def boom(req):
        raise httpx.ReadTimeout("slow", request=req)
    bot.b.HC = httpx.AsyncClient(transport=httpx.MockTransport(boom))
    text, _, _ = await bot.tap(None, raw=dns); assert "Cloudflare timeout" in text


@arun
async def test_unexpected_exception_is_reported_to_the_user(bot):
    await bot.login()

    async def broken(uid, st):
        raise RuntimeError("kaboom")
    bot.b.VIEWS["dns"] = broken
    await bot.tap("dns")
    assert "RuntimeError" in bot.alert()
    bot.b.VIEWS["help"] = broken
    await bot.text("/help")
    assert "RuntimeError" in bot.texts(1)


@arun
async def test_permission_error_gets_a_hint(bot):
    await bot.login()
    bot.cf.fail_all = (403, json.dumps({"success": False, "errors": [{"code": 10000, "message": "Authentication error"}]}).encode())
    text, _, _ = await bot.tap("an")
    assert "Authentication error" in text and "دسترسی این بخش" in text


@arun
async def test_polling_backs_off_on_errors(bot):
    b = bot.b
    bot.tg.updates = [{"ok": False, "error_code": 409, "description": "Conflict"},
                      {"ok": False, "error_code": 401, "description": "Unauthorized"},
                      {"ok": False, "error_code": 429, "description": "Too Many Requests", "parameters": {"retry_after": 17}},
                      {"ok": True, "result": [{"update_id": 41, "message": {}}]}]
    assert await b.poll(7) == (7, [], 5)
    assert await b.poll(7) == (7, [], 30)
    assert await b.poll(7) == (7, [], 17)
    off, ups, wait = await b.poll(7)
    assert (off, len(ups), wait) == (42, 1, 0)

    def down(req):
        raise httpx.ConnectError("no network", request=req)
    b.H = httpx.AsyncClient(transport=httpx.MockTransport(down))
    assert await b.poll(42) == (42, [], 5)


@arun
async def test_slow_request_of_one_user_does_not_block_another(bot):
    b = bot.b; b.db["admins"] = [ADMIN]
    await bot.login()
    order = []

    async def slow(req):
        await asyncio.sleep(0.3)
        return bot.cf.handler(req)
    b.HC = httpx.AsyncClient(transport=httpx.MockTransport(slow))
    slow_tap = bot.button("dns")["callback_data"]; _, _, mid = bot.screen()

    async def owner():
        await b.handle({"update_id": 900, "callback_query": {"id": "900", "from": {"id": OWNER}, "data": slow_tap, "message": {"message_id": mid, "chat": {"id": OWNER}}}})
        order.append("owner")

    async def other():
        await asyncio.sleep(0.05)
        await b.handle({"update_id": 901, "message": {"message_id": 5, "from": {"id": ADMIN}, "chat": {"id": ADMIN}, "text": "/start"}})
        order.append("admin")
    await asyncio.gather(owner(), other())
    assert order == ["admin", "owner"]


@arun
async def test_activity_log_records_changes(bot):
    await bot.login(); await bot.tap("ssl"); await bot.tap("ss:strict")
    bot.cf.fail_all = (400, json.dumps({"success": False, "errors": [{"code": 1, "message": "nope"}]}).encode())
    await bot.tap("ss:flexible"); bot.cf.fail_all = None
    rows = [json.loads(l) for l in open(bot.b.AUDF, encoding="utf-8")]
    assert [(r["a"], r["ok"]) for r in rows] == [("account.add", True), ("ssl", True), ("ssl", False)]
    assert rows[1]["u"] == OWNER and rows[1]["acc"] == "Acme" and rows[1]["z"] == "example.com" and rows[1]["d"] == "strict"
    assert GOOD not in open(bot.b.AUDF).read()
    assert stat.S_IMODE(os.stat(bot.b.AUDF).st_mode) == 0o600
    await bot.text("⚙️ تنظیمات"); text, _, _ = await bot.tap("log")
    assert "ssl" in text and "example.com" in text
    await bot.tap("logx"); assert bot.tg.docs[-1][0] == "cfbot-activity.log"


@arun
async def test_alerts_for_zone_status_and_lost_connection(bot):
    await bot.login(); b = bot.b
    n = len(bot.tg.shown())
    await b.mon_tick(); await b.mon_tick()
    assert len(bot.tg.shown()) == n                           # first look and "nothing changed" stay silent
    bot.cf.zones[bot.cf.zid("example.org")]["status"] = "active"
    await b.mon_tick()
    assert "example.org" in bot.texts(1) and "pending ← active" in bot.texts(1)
    bot.cf.fail_all = (401, json.dumps({"success": False, "errors": [{"code": 10000, "message": "Authentication error"}]}).encode())
    n = len(bot.tg.shown()); await b.mon_tick()
    assert len(bot.tg.shown()) == n                           # one miss is not reported
    await b.mon_tick(); assert "قطع شد" in bot.texts(1)
    n = len(bot.tg.shown()); await b.mon_tick(); assert len(bot.tg.shown()) == n   # and not repeated
    bot.cf.fail_all = None; await b.mon_tick()
    assert "دوباره برقرار شد" in bot.texts(1)
    await bot.text("⚙️ تنظیمات"); await bot.tap("mon")
    assert b.db["mon"]["on"] is False


@arun
async def test_commands_and_help(bot):
    await bot.b.startup()
    sets = [p for m, p in bot.tg.calls if m == "setMyCommands"]
    assert len(sets) == 2 and [c["command"] for c in sets[0]["commands"]] == ["start", "help", "cancel"]
    text, _, _ = await bot.text("/help"); assert "CF Control" in text
    await bot.login(); await bot.tap("dns"); await bot.tap("new"); await bot.text("/cancel")
    assert "لغو شد" in bot.texts(1)
    n = len(bot.cf.recs("example.com")); await bot.text("A sub 1.2.3.4")
    assert len(bot.cf.recs("example.com")) == n               # no longer waiting for a record


@arun
async def test_design_mode_and_language_still_work(bot):
    await bot.login(); await bot.text("⚙️ تنظیمات"); await bot.tap("design")
    await bot.text("🌐 دامنه‌ها"); _, buttons, _ = bot.screen()
    assert buttons[-1]["callback_data"] == "cz"
    await bot.tap("cz")
    i = next(n for n, (_, _, kind) in enumerate(bot.b.S[OWNER]["scr"]) if kind == "btn")
    await bot.tap(f"cz1:{i}"); await bot.tap("cs:danger")
    bid = bot.b.S[OWNER]["scr"][bot.b.S[OWNER]["sel"]][0]
    assert bot.b.db["btn"][bid] == {"style": "danger"}
    await bot.text("⚙️ تنظیمات"); await bot.tap("lang"); text, _, _ = bot.screen()
    assert "Settings" in text


@arun
async def test_design_mode_back_button_returns_to_the_customized_screen(bot):
    await bot.login(); await bot.text("⚙️ تنظیمات"); await bot.tap("design")
    await bot.text("🌐 دامنه‌ها"); await bot.tap("example.com"); await bot.tap("dns")
    await bot.tap("cz"); text, _, _ = await bot.tap("dns")    # the back button of the design screen
    assert "رکوردهای DNS" in text and "قدیمی" not in bot.alert()


@arun
async def test_main_loop_dispatches_updates_and_survives_errors(bot):
    b = bot.b
    bot.tg.updates = [{"ok": False, "error_code": 502, "description": "Bad Gateway"},
                      {"ok": True, "result": [{"update_id": 5, "message": {"message_id": 1, "from": {"id": OWNER}, "chat": {"id": OWNER}, "text": "/start"}},
                                              {"update_id": 6, "message": {"message_id": 2, "from": {"id": 999}, "chat": {"id": 999}, "text": "/start"}}]}]

    async def telegram(req):                                  # like the real thing: an empty long poll just waits
        if req.url.path.endswith("getUpdates") and not bot.tg.updates:
            bot.tg.calls.append(("getUpdates", json.loads(req.content)))
            await asyncio.sleep(3600)
        return bot.tg.handler(req)
    b.H = httpx.AsyncClient(transport=httpx.MockTransport(telegram))
    real_poll, waits = b.poll, []

    async def quick_poll(off):                                # keep the back-off decision, skip the real waiting
        off, ups, wait = await real_poll(off)
        waits.append(wait)
        return off, ups, 0.01 if wait else 0
    b.poll = quick_poll
    task = asyncio.ensure_future(b.main())
    for _ in range(300):
        await asyncio.sleep(0.01)
        if any(m == "sendMessage" for m, _ in bot.tg.calls) and len(waits) >= 2:
            break
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    sent = [p for m, p in bot.tg.calls if m == "sendMessage"]
    assert [p["chat_id"] for p in sent] == [OWNER]            # the stranger (999) gets no answer
    assert waits[:2] == [5, 0]                                # backed off after the failed poll instead of spinning
    assert [p["offset"] for m, p in bot.tg.calls if m == "getUpdates"][:3] == [0, 0, 7]


@arun
async def test_connection_check_and_account_picker(bot):
    await bot.login(); await bot.text("☁️ حساب‌ها"); text, _, _ = await bot.tap("chk")
    assert "Acme" in text and "2 zones" in text
    # a token that sees several Cloudflare accounts must ask which one to use
    second = {"id": "b" * 32, "name": "Other Org"}
    real = bot.cf.handler

    def two_accounts(req):
        if req.url.path.endswith("/client/v4/accounts"):
            return bot.cf.page([bot.cf.account, second], dict(req.url.params))
        return real(req)
    bot.b.HC = httpx.AsyncClient(transport=httpx.MockTransport(two_accounts))
    await bot.text("🌐 دامنه‌ها"); text, buttons, _ = await bot.tap("svc")
    assert "چند حساب" in text and [x["text"] for x in buttons[:2]] == ["☁️ Acme", "☁️ Other Org"]
    await bot.tap("ai:1"); assert bot.b.S[OWNER]["aid"] == "b" * 32
    _, buttons, _ = bot.screen(); assert any(x["callback_data"].startswith("aisw") for x in buttons)


@arun
async def test_button_pointing_into_a_changed_list_is_treated_as_outdated(bot):
    await bot.login(); await bot.text("🌐 دامنه‌ها"); await bot.tap("svc"); await bot.tap("wk")
    tap = bot.button("wk1:0")["callback_data"]
    bot.b.S[OWNER]["wkl"] = []                                # the list was refreshed and is now shorter
    await bot.tap(None, raw=tap)
    assert "قدیمی" in bot.alert()


@arun
async def test_premium_emoji_id_helper_still_works(bot):
    await bot.text("/start")
    await bot.text("⭐", entities=[{"type": "custom_emoji", "offset": 0, "length": 1, "custom_emoji_id": "5368324170671202286"}])
    assert "5368324170671202286" in bot.texts(1)
