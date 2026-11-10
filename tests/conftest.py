"""Test harness: the bot talks to an in-memory fake of Telegram and of the Cloudflare API."""
import asyncio, functools, importlib, json, os, re, sys, uuid

import httpx
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOOD = "good_token_0123456789abcdefghij"  # the fake Cloudflare accepts tokens starting with "good"
OWNER, ADMIN = 1, 2


def arun(f):
    """Run an async test function to completion."""
    @functools.wraps(f)
    def wrapper(*a, **kw):
        return asyncio.run(f(*a, **kw))
    return wrapper


def hexid():
    return uuid.uuid4().hex


class FakeTelegram:
    def __init__(self):
        self.calls = []       # (method, payload)
        self.files = {}       # file_id -> bytes
        self.docs = []        # (filename, bytes) sent by the bot
        self.updates = []     # queue of getUpdates answers (dicts)
        self.mid = 100

    def handler(self, req: httpx.Request):
        path = req.url.path
        if "/file/bot" in path:
            return httpx.Response(200, content=self.files.get(path.rsplit("/", 1)[-1], b""))
        method = path.rsplit("/", 1)[-1]
        if method == "sendDocument":
            body = req.content
            name = re.search(rb'filename="([^"]+)"', body).group(1).decode()
            self.docs.append((name, body))
            self.calls.append((method, {}))
            return httpx.Response(200, json={"ok": True, "result": {}})
        p = json.loads(req.content or b"{}")
        self.calls.append((method, p))
        if method == "getUpdates":
            return httpx.Response(200, json=self.updates.pop(0) if self.updates else {"ok": True, "result": []})
        if method == "getFile":
            return httpx.Response(200, json={"ok": True, "result": {"file_path": p["file_id"]}})
        if method in ("sendMessage", "editMessageText"):
            for row in (p.get("reply_markup") or {}).get("inline_keyboard") or []:
                for bt in row:  # Telegram refuses callback data longer than 64 bytes
                    assert len(bt["callback_data"].encode()) <= 64, bt
            assert len(p["text"]) <= 4096
            if method == "sendMessage":
                self.mid += 1
            return httpx.Response(200, json={"ok": True, "result": {"message_id": p.get("message_id", self.mid)}})
        return httpx.Response(200, json={"ok": True, "result": True})

    def shown(self):
        """Every screen/notice the bot displayed, oldest first: (method, payload)."""
        return [(m, p) for m, p in self.calls if m in ("sendMessage", "editMessageText")]


class FakeCloudflare:
    """Just enough of the v4 API for the bot's flows. State is plain dicts so tests can inspect it."""

    def __init__(self):
        self.log = []          # (method, path, json-or-None)
        self.account = {"id": "a" * 32, "name": "Acme"}
        self.zones = {}        # id -> zone
        self.records = {}      # zone id -> {rec id -> record}
        self.settings = {}     # zone id -> {setting -> value}
        self.rules = {}        # zone id -> {rule id -> access rule}
        self.rulesets = {}     # (zone id, phase) -> ruleset
        self.pagerules = {}    # zone id -> {id -> rule}
        self.routes = {}       # zone id -> {id -> route}
        self.dnssec = {}       # zone id -> status
        self.scripts = [{"id": "my-worker", "created_on": "2026-01-01T00:00:00Z", "modified_on": "2026-02-01T00:00:00Z", "handlers": ["fetch"]}]
        self.projects = [{"name": "site", "subdomain": "site.pages.dev", "domains": ["site.pages.dev"], "production_branch": "main",
                          "latest_deployment": {"id": "dep1", "latest_stage": {"name": "deploy", "status": "success"}}}]
        self.tunnels = [{"id": str(uuid.uuid4()), "name": "home", "status": "healthy", "created_at": "2026-01-01T00:00:00Z",
                         "connections": [{"colo_name": "FRA", "origin_ip": "198.51.100.7", "client_version": "2026.1.0"}]}]
        self.purges, self.retries, self.imports = [], [], []
        self.fail_all = None   # set to (status, body) to make every call fail
        self.add_zone("example.com"); self.add_zone("example.org", status="pending")
        z = self.zid("example.com")
        self.add_rec(z, "A", "example.com", "1.1.1.1", proxied=True)
        self.add_rec(z, "A", "www.example.com", "1.1.1.1")
        self.add_rec(z, "CNAME", "blog.example.com", "example.com")
        self.add_rec(self.zid("example.org"), "A", "example.org", "1.1.1.1")

    # ── state helpers
    def add_zone(self, name, status="active"):
        z = hexid()
        self.zones[z] = {"id": z, "name": name, "status": status, "paused": False, "plan": {"name": "Free Website"},
                         "name_servers": ["ada.ns.cloudflare.com", "bob.ns.cloudflare.com"], "account": dict(self.account)}
        self.records[z] = {}; self.rules[z] = {}; self.pagerules[z] = {}; self.routes[z] = {}; self.dnssec[z] = "disabled"
        self.settings[z] = {"ssl": "full", "security_level": "medium", "development_mode": "off", "always_use_https": "off",
                            "ipv6": "on", "tls_1_3": "zrt", "min_tls_version": "1.0", "cache_level": "aggressive",
                            "security_header": {"strict_transport_security": {"enabled": False, "max_age": 0, "include_subdomains": False, "preload": False, "nosniff": False}}}
        return z

    def zid(self, name):
        return next(k for k, v in self.zones.items() if v["name"] == name)

    def add_rec(self, z, typ, name, content, **kw):
        r = hexid()
        self.records[z][r] = {"id": r, "type": typ, "name": name, "content": content, "ttl": 1, "proxied": False, **kw}
        return r

    def recs(self, zone_name):
        return list(self.records[self.zid(zone_name)].values())

    # ── HTTP
    @staticmethod
    def ok(result=None, **extra):
        return httpx.Response(200, json={"success": True, "errors": [], "messages": [], "result": result, **extra})

    @staticmethod
    def err(status, code, message):
        return httpx.Response(status, json={"success": False, "errors": [{"code": code, "message": message}], "result": None})

    def page(self, items, q):
        per, page = int(q.get("per_page", 20)), int(q.get("page", 1))
        part = items[(page - 1) * per: page * per]
        return self.ok(part, result_info={"page": page, "per_page": per, "count": len(part), "total_count": len(items),
                                          "total_pages": max(1, -(-len(items) // per))})

    def handler(self, req: httpx.Request):
        path = req.url.path.split("/client/v4", 1)[1]; q = dict(req.url.params); m = req.method
        ctype = req.headers.get("content-type", "")
        body = json.loads(req.content) if req.content and "json" in ctype else None
        self.log.append((m, path, body))
        if self.fail_all:
            return httpx.Response(self.fail_all[0], content=self.fail_all[1])
        if not req.headers.get("authorization", "").startswith("Bearer good"):
            return self.err(401, 10000, "Authentication error")
        P = path.strip("/").split("/")
        if P == ["graphql"]:
            day = {"dimensions": {"t": "2026-01-01"}, "uniq": {"uniques": 40},
                   "sum": {"requests": 1500, "cachedRequests": 600, "bytes": 3 << 20, "cachedBytes": 1 << 20, "threats": 7, "pageViews": 900,
                           "countryMap": [{"clientCountryName": "IR", "requests": 1000}, {"clientCountryName": "DE", "requests": 500}]}}
            return httpx.Response(200, json={"data": {"viewer": {"zones": [{"g": [day, day]}]}}, "errors": None})
        if P == ["accounts"]:
            return self.page([self.account], q)
        if P[0] == "accounts":
            return self.accounts(m, P[2:], body)
        if P == ["zones"]:
            if m == "POST":
                if any(z["name"] == body["name"] for z in self.zones.values()):
                    return self.err(400, 1061, f"{body['name']} already exists")
                assert body["account"]["id"] == self.account["id"]
                return self.ok(self.zones[self.add_zone(body["name"], "pending")])
            zs = list(self.zones.values())
            if q.get("name", "").startswith("contains:"):
                zs = [z for z in zs if q["name"][9:] in z["name"]]
            return self.page(zs, q)
        z = P[1]
        if z not in self.zones:
            return self.err(404, 7003, "Could not route to /zones/" + z)
        return self.zone(m, z, P[2:], q, body, req)

    def accounts(self, m, P, body):
        if P == ["workers", "scripts"]:
            return self.ok(self.scripts)
        if P[:2] == ["workers", "scripts"] and m == "DELETE":
            self.scripts = [s for s in self.scripts if s["id"] != P[2]]
            return self.ok(None)
        if P == ["pages", "projects"]:
            return self.ok(self.projects)
        if P[:2] == ["pages", "projects"] and P[-1] == "deployments":
            return self.ok([{"id": "dep1", "created_on": "2026-03-01T10:00:00Z", "environment": "production", "latest_stage": {"name": "deploy", "status": "failure"}}])
        if P[:2] == ["pages", "projects"] and P[-1] == "retry":
            self.retries.append((P[2], P[4]))
            return self.ok({"id": "dep2"})
        if P == ["cfd_tunnel"]:
            return self.ok(self.tunnels)
        return self.err(404, 7003, "no route")

    def zone(self, m, z, P, q, body, req):
        zone = self.zones[z]
        if not P:
            if m == "DELETE":
                del self.zones[z]
                return self.ok({"id": z})
            if m == "PATCH":
                zone.update(body)
            return self.ok(zone)
        if P == ["activation_check"]:
            return self.ok({"id": z})
        if P == ["settings"]:
            return self.ok([{"id": k, "value": v, "editable": True} for k, v in self.settings[z].items()])
        if P[0] == "settings":
            if P[1] not in self.settings[z]:
                return self.err(400, 1006, "Unrecognized zone setting name")
            if m == "PATCH":
                self.settings[z][P[1]] = body["value"]
            return self.ok({"id": P[1], "value": self.settings[z][P[1]]})
        if P == ["dnssec"]:
            if m == "PATCH":
                self.dnssec[z] = "pending" if body["status"] == "active" else "disabled"
            return self.ok({"status": self.dnssec[z], "ds": f"{zone['name']}. 3600 IN DS 2371 13 2 ABCDEF", "key_tag": 2371, "algorithm": "13", "digest_type": "2", "digest": "ABCDEF"})
        if P == ["purge_cache"]:
            self.purges.append(body)
            return self.ok({"id": z})
        if P == ["dns_records", "export"]:
            return httpx.Response(200, text="\n".join(f"{r['name']}. 1 IN {r['type']} {r['content']}" for r in self.records[z].values()))
        if P == ["dns_records", "import"]:
            self.imports.append(req.content)
            return self.ok({"recs_added": 2, "total_records_parsed": 3})
        if P == ["dns_records"]:
            if m == "POST":
                if body["type"] == "MX" and "priority" not in body:
                    return self.err(400, 9100, "priority is required")
                if "content" not in body and "data" not in body:
                    return self.err(400, 9005, "Content for record is invalid")
                r = hexid()
                content = body.get("content") or " ".join(str(v) for v in body["data"].values())
                self.records[z][r] = {"id": r, "proxied": False, **body, "content": content}
                return self.ok(self.records[z][r])
            rs = sorted(self.records[z].values(), key=lambda r: r["type"])
            if q.get("type"): rs = [r for r in rs if r["type"] == q["type"]]
            if q.get("content"): rs = [r for r in rs if r["content"] == q["content"]]
            if q.get("search"): rs = [r for r in rs if q["search"] in r["name"] or q["search"] in r["content"]]
            return self.page(rs, q)
        if P[0] == "dns_records":
            if P[1] not in self.records[z]:
                return self.err(404, 81044, "Record does not exist.")
            if m == "DELETE":
                del self.records[z][P[1]]
                return self.ok({"id": P[1]})
            if m == "PATCH":
                self.records[z][P[1]].update(body)
            return self.ok(self.records[z][P[1]])
        if P[:3] == ["firewall", "access_rules", "rules"]:
            if m == "POST":
                r = hexid(); self.rules[z][r] = {"id": r, **body}
                return self.ok(self.rules[z][r])
            if m == "DELETE":
                self.rules[z].pop(P[3], None)
                return self.ok({"id": P[3]})
            return self.page(list(self.rules[z].values()), q)
        if P[0] == "rulesets":
            return self.ruleset(m, z, P[1:], body)
        if P[0] == "pagerules":
            if m == "POST":
                r = hexid(); self.pagerules[z][r] = {"id": r, **body}
                return self.ok(self.pagerules[z][r])
            if m == "PATCH":
                self.pagerules[z][P[1]].update(body)
                return self.ok(self.pagerules[z][P[1]])
            if m == "DELETE":
                del self.pagerules[z][P[1]]
                return self.ok({"id": P[1]})
            return self.ok(list(self.pagerules[z].values()))
        if P[:2] == ["workers", "routes"]:
            if m == "POST":
                r = hexid(); self.routes[z][r] = {"id": r, **body}
                return self.ok({"id": r})
            if m == "DELETE":
                del self.routes[z][P[2]]
                return self.ok({"id": P[2]})
            return self.ok(list(self.routes[z].values()))
        return self.err(404, 7003, "no route")

    def ruleset(self, m, z, P, body):
        if P[0] == "phases":
            key = (z, P[1])
            if m == "PUT":
                self.rulesets[key] = {"id": hexid(), "phase": P[1], "rules": [{"id": hexid(), **r} for r in body["rules"]]}
            if key not in self.rulesets:
                return self.err(404, 10003, "could not find entrypoint ruleset in the phase")
            return self.ok(self.rulesets[key])
        rs = next(r for r in self.rulesets.values() if r["id"] == P[0])
        if m == "POST":
            rs["rules"].append({"id": hexid(), **body})
        elif m == "PATCH":
            next(r for r in rs["rules"] if r["id"] == P[2]).update(body)
        elif m == "DELETE":
            rs["rules"] = [r for r in rs["rules"] if r["id"] != P[2]]
        return self.ok(rs)


class Driver:
    """Plays a Telegram user: sends texts, taps buttons, reads what the bot showed."""

    def __init__(self, mod, tg, cf):
        self.b, self.tg, self.cf = mod, tg, cf
        self.uid = OWNER; self.n = 0

    def as_user(self, uid):
        self.uid = uid
        return self

    async def text(self, text, **extra):
        self.n += 1
        await self.b.handle({"update_id": self.n, "message": {"message_id": 1000 + self.n, "from": {"id": self.uid},
                                                             "chat": {"id": self.uid}, "text": text, **extra}})
        return self.screen()

    async def doc(self, file_id, size=10):
        self.n += 1
        await self.b.handle({"update_id": self.n, "message": {"message_id": 1000 + self.n, "from": {"id": self.uid}, "chat": {"id": self.uid},
                                                             "document": {"file_id": file_id, "file_size": size}}})
        return self.screen()

    def screen(self):
        """Last message the bot showed to the current user: (text, [buttons])."""
        for m, p in reversed(self.tg.shown()):
            if p.get("chat_id") == self.uid:
                rows = (p.get("reply_markup") or {}).get("inline_keyboard") or []
                return p["text"], [bt for row in rows for bt in row], p.get("message_id") or self.tg.mid
        return "", [], None

    def texts(self, last=3):
        return "\n".join(p["text"] for m, p in self.tg.shown()[-last:] if p.get("chat_id") == self.uid)

    def button(self, what):
        """Find a button on the current screen by callback action (e.g. 'ss:off') or by a label fragment."""
        _, buttons, _ = self.screen()
        for bt in buttons:
            data = bt.get("callback_data", "").partition("|")[0]
            if data == what or data.partition(":")[0] == what or what in bt["text"]:
                return bt
        raise AssertionError(f"no button {what!r} on screen; have {[(b['text'], b.get('callback_data')) for b in buttons]}")

    async def tap(self, what, raw=None):
        data = raw if raw is not None else self.button(what)["callback_data"]
        _, _, mid = self.screen()
        self.n += 1
        await self.b.handle({"update_id": self.n, "callback_query": {"id": str(self.n), "from": {"id": self.uid}, "data": data,
                                                                    "message": {"message_id": mid, "chat": {"id": self.uid}}}})
        return self.screen()

    def alert(self):
        """Text of the last answerCallbackQuery."""
        for m, p in reversed(self.tg.calls):
            if m == "answerCallbackQuery":
                return p.get("text", "")
        return ""

    async def login(self):
        """Add the fake account and open example.com."""
        await self.text("/start"); await self.text("➕ افزودن حساب"); await self.text(GOOD)
        await self.text("🌐 دامنه‌ها")
        return await self.tap("example.com")


@pytest.fixture
def bot(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "1:TESTTOKEN"); monkeypatch.setenv("ADMIN_IDS", str(OWNER))
    monkeypatch.setenv("CFBOT_DIR", str(tmp_path)); monkeypatch.setenv("MONITOR_MINUTES", "0")
    monkeypatch.delenv("DATA_KEY", raising=False)
    sys.path.insert(0, ROOT); sys.modules.pop("cfbot", None)
    mod = importlib.import_module("cfbot")
    tg, cf = FakeTelegram(), FakeCloudflare()
    mod.H = httpx.AsyncClient(transport=httpx.MockTransport(tg.handler))
    mod.HC = httpx.AsyncClient(transport=httpx.MockTransport(cf.handler))
    yield Driver(mod, tg, cf)
    sys.modules.pop("cfbot", None)
