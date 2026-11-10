"""Pure input parsers: what the user types -> what is sent to Cloudflare."""
import re

import pytest


def test_txt_keeps_spaces(bot):
    r = bot.b.parse_rec("TXT @ v=spf1 include:_spf.google.com ~all", "example.com")
    assert r == {"type": "TXT", "name": "example.com", "ttl": 1, "content": '"v=spf1 include:_spf.google.com ~all"'}


def test_txt_long_value_is_split_into_255_char_strings(bot):
    r = bot.b.parse_rec("TXT dkim._domainkey v=DKIM1; p=" + "A" * 400, "example.com")
    parts = re.findall(r'"([^"]*)"', r["content"])
    assert len(parts) == 2 and all(len(p) <= 255 for p in parts) and "".join(parts).endswith("A" * 400)


def test_txt_already_quoted_is_untouched(bot):
    assert bot.b.parse_rec('TXT @ "a b"', "example.com")["content"] == '"a b"'


@pytest.mark.parametrize("line", ["MX @ 10 mail.example.com", "MX @ mail.example.com 10"])
def test_mx_has_priority(bot, line):
    r = bot.b.parse_rec(line, "example.com")
    assert (r["content"], r["priority"], r["name"]) == ("mail.example.com", 10, "example.com")


def test_srv_and_caa_use_data(bot):
    srv = bot.b.parse_rec("SRV _sip._tcp 10 5 5060 sip.example.com", "example.com")
    assert srv["name"] == "_sip._tcp.example.com"
    assert srv["data"] == {"priority": 10, "weight": 5, "port": 5060, "target": "sip.example.com"}
    caa = bot.b.parse_rec("CAA @ 0 issue letsencrypt.org", "example.com")
    assert caa["data"] == {"flags": 0, "tag": "issue", "value": "letsencrypt.org"}


def test_a_record_and_proxy_flag(bot):
    assert bot.b.parse_rec("a sub 1.2.3.4 1", "example.com") == {"type": "A", "name": "sub.example.com", "ttl": 1, "content": "1.2.3.4", "proxied": True}
    assert bot.b.parse_rec("A sub.example.com 1.2.3.4", "example.com")["proxied"] is False
    assert bot.b.parse_rec("AAAA v6 2001:db8::1 on", "example.com")["content"] == "2001:db8::1"


@pytest.mark.parametrize("line,err", [
    ("A sub", "fmt"), ("A sub 2001:db8::1", "ip"), ("AAAA sub 1.2.3.4", "ip"), ("A sub 1.2.3.4 maybe", "fmt"),
    ("MX @ mail.example.com", "mx"), ("SRV _a._tcp 1 2 host", "srv"), ("CAA @ issue le.org", "caa"), ("?? a b", "fmt")])
def test_bad_records_name_the_problem(bot, line, err):
    with pytest.raises(ValueError, match=f"^{err}$"):
        bot.b.parse_rec(line, "example.com")
    assert "x_" + err in bot.b.T["fa"] and "x_" + err in bot.b.T["en"]


def test_fqdn(bot):
    f = bot.b.fqdn
    assert f("@", "example.com") == "example.com" and f("www", "example.com") == "www.example.com"
    assert f("WWW.Example.com.", "example.com") == "www.example.com" and f("*.dev", "example.com") == "*.dev.example.com"
    assert f("notexample.com", "example.com") == "notexample.com.example.com"


def test_edit_values(bot):
    pe = bot.b.parse_edit
    assert pe("A", "ttl", "auto") == {"ttl": 1} and pe("A", "ttl", "300") == {"ttl": 300}
    assert pe("MX", "priority", "20") == {"priority": 20}
    assert pe("TXT", "content", "hello world") == {"content": '"hello world"'}
    assert pe("SRV", "content", "1 2 443 t.example.com") == {"data": {"priority": 1, "weight": 2, "port": 443, "target": "t.example.com"}}
    assert pe("A", "name", "new", "example.com") == {"name": "new.example.com"}
    for typ, field, bad, err in [("A", "ttl", "5", "ttl"), ("A", "ttl", "abc", "ttl"), ("MX", "priority", "-1", "prio"), ("A", "content", "nope", "ip")]:
        with pytest.raises(ValueError, match=err):
            pe(typ, field, bad)


def test_firewall_targets(bot):
    p = bot.b.parse_fw
    assert p("1.2.3.4")["configuration"] == {"target": "ip", "value": "1.2.3.4"} and p("1.2.3.4")["mode"] == "block"
    assert p("2001:DB8::1")["configuration"] == {"target": "ip6", "value": "2001:db8::1"}
    assert p("1.2.3.9/24")["configuration"] == {"target": "ip_range", "value": "1.2.3.0/24"}
    assert p("as13335")["configuration"] == {"target": "asn", "value": "AS13335"}
    assert p("challenge ru")["configuration"] == {"target": "country", "value": "RU"} and p("challenge ru")["mode"] == "challenge"
    r = p("allow 10.0.0.1 office vpn")
    assert (r["mode"], r["notes"]) == ("whitelist", "office vpn")
    for bad in ["", "hello", "1.2.3", "allow"]:
        with pytest.raises(ValueError):
            p(bad)


def test_bulk_ip_pair(bot):
    assert bot.b.parse_bulk("1.1.1.1 2.2.2.2") == ("1.1.1.1", "2.2.2.2", "A")
    assert bot.b.parse_bulk("2001:db8::1 2001:db8::2")[2] == "AAAA"
    for bad in ["1.1.1.1", "1.1.1.1 2001:db8::1", "1.1.1.1 1.1.1.1", "a b", "1.1.1.1 2.2.2.2 3.3.3.3"]:
        with pytest.raises(ValueError):
            bot.b.parse_bulk(bad)


def test_rule_parsers(bot):
    w = bot.b.parse_waf('block (ip.src.country eq "RU")')
    assert (w["action"], w["expression"], w["enabled"]) == ("block", '(ip.src.country eq "RU")', True)
    rl = bot.b.parse_rl('50 10 10 (http.request.uri.path contains "/login")')
    assert rl["ratelimit"] == {"characteristics": ["ip.src", "cf.colo.id"], "period": 10, "requests_per_period": 50, "mitigation_timeout": 10}
    d = bot.b.parse_redirect("old.example.com/blog https://new.example.com 302")
    assert d["expression"] == '(http.host eq "old.example.com" and http.request.uri.path eq "/blog")'
    assert d["action_parameters"]["from_value"] == {"status_code": 302, "target_url": {"value": "https://new.example.com"}, "preserve_query_string": True}
    assert bot.b.parse_redirect("old.example.com https://x.example.com")["action_parameters"]["from_value"]["status_code"] == 301
    pr = bot.b.parse_pagerule("example.com/old/* https://example.com/new/$1")
    assert pr["actions"][0]["value"] == {"url": "https://example.com/new/$1", "status_code": 301}
    for f, bad in [(bot.b.parse_waf, "allow x"), (bot.b.parse_waf, "block"), (bot.b.parse_rl, "a b c d"), (bot.b.parse_rl, "50 10"),
                   (bot.b.parse_redirect, 'a".com https://x.com'), (bot.b.parse_redirect, "a.com ftp://x"), (bot.b.parse_redirect, "a.com https://x.com 999"),
                   (bot.b.parse_pagerule, "a.com/x")]:
        with pytest.raises(ValueError):
            f(bad)


def test_purge_targets(bot):
    g = bot.b.parse_purge("https://example.com/a.css\nexample.com/blog/\nwww.example.com")
    assert g == {"files": ["https://example.com/a.css"], "prefixes": ["example.com/blog/"], "hosts": ["www.example.com"]}
    with pytest.raises(ValueError):
        bot.b.parse_purge("???")


def test_both_languages_have_the_same_texts(bot):
    assert set(bot.b.T["fa"]) == set(bot.b.T["en"])
    src = open(bot.b.__file__, encoding="utf-8").read()
    used = set(re.findall(r"""\bt\((?:uid|c\.uid),\s*["']([a-z_0-9]+)["']\)""", src))
    assert not used - set(bot.b.T["fa"])


def test_human_numbers(bot):
    assert bot.b.hn(999) == "999" and bot.b.hn(1500) == "1.5K" and bot.b.hb(3 << 20) == "3.0 MB"
    assert bot.b.spark([0, 5, 10]) == "▁▅█" and bot.b.spark([0, 0]) == ""
