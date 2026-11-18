"""papers.py: RSS headlines. Sample feeds below are our own text; no test touches the network."""
from __future__ import annotations

import json

import pytest

from dsereport import papers

RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Sample</title>
<item><title>  BATBC shares rise on dividend  </title><link>https://example.com/a</link>
<description>Long text we must not keep</description>
<pubDate>Tue, 17 Nov 2026 10:30:00 +0600</pubDate></item>
<item><title>Banks lead the market &amp;#039;s turnover</title><link>https://example.com/b</link>
<pubDate>Mon, 16 Nov 2026 20:00:00 GMT</pubDate></item>
<item><title>No date here</title><link>https://example.com/c</link></item>
<item><title>Bad date</title><link>https://example.com/d</link><pubDate>yesterday</pubDate></item>
<item><title></title><link>https://example.com/e</link></item>
<item><title>No link</title></item>
<item><title>Script link</title><link>javascript:alert(1)</link></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Atom sample</title>
<entry><title>IT stocks gain as GP climbs</title><link rel="alternate" href="https://example.com/x"/>
<updated>2026-11-15T08:00:00Z</updated></entry>
<entry><title>Older story</title><link href="https://example.com/y"/>
<published>2026-11-01T08:00:00+06:00</published></entry>
</feed>"""

RSS_DUP = b"""<?xml version="1.0"?><rss><channel>
<item><title>BATBC shares rise on dividend</title><link>https://example.com/a</link>
<pubDate>Tue, 17 Nov 2026 10:30:00 +0600</pubDate></item>
<item><title>Newest story</title><link>https://example.com/n</link>
<pubDate>Wed, 18 Nov 2026 09:00:00 +0600</pubDate></item>
</channel></rss>"""


def test_feeds_list_names_the_seven_sections():
    assert len(papers.FEEDS) == 7
    sources = {s for s, _, _ in papers.FEEDS}
    assert sources == {"The Daily Star", "The Business Standard", "Prothom Alo English"}
    assert len({sec for _, sec, _ in papers.FEEDS}) == 7      # section names identify a feed in `failed`
    assert all(u.startswith("https://") for _, _, u in papers.FEEDS)


def test_parse_rss_keeps_only_headline_fields():
    items = papers.parse_rss(RSS, "Src", "Sec")
    assert [i["link"] for i in items] == ["https://example.com/a", "https://example.com/b",
                                          "https://example.com/c", "https://example.com/d"]
    first = items[0]
    assert first == {"source": "Src", "section": "Sec", "title": "BATBC shares rise on dividend",
                     "link": "https://example.com/a", "published": "2026-11-17T10:30:00+06:00"}
    assert items[1]["published"] == "2026-11-17T02:00:00+06:00"     # GMT shown in Dhaka time
    assert items[1]["title"] == "Banks lead the market 's turnover"
    assert items[2]["published"] is None and items[3]["published"] is None


def test_parse_atom_entries():
    items = papers.parse_rss(ATOM, "A", "B")
    assert [i["link"] for i in items] == ["https://example.com/x", "https://example.com/y"]
    assert items[0]["published"] == "2026-11-15T14:00:00+06:00"
    assert items[1]["published"] == "2026-11-01T08:00:00+06:00"


@pytest.mark.parametrize("bad", [
    b'<?xml version="1.0"?><!DOCTYPE rss [<!ENTITY x "y">]><rss/>',
    b'<rss><!ENTITY x "y"></rss>',
])
def test_parse_rss_rejects_dtds_and_entities(bad):
    with pytest.raises(ValueError):
        papers.parse_rss(bad, "S", "s")


def test_parse_rss_rejects_broken_xml():
    with pytest.raises(ValueError):
        papers.parse_rss(b"<rss><channel><item>", "S", "s")


def test_tag_codes_whole_words_in_capitals_and_sectors():
    codes = ["GP", "BATBC", "SQURPHARMA", "BEST"]
    sectors = ["Bank", "IT", "Telecom"]
    assert papers.tag("BATBC and GP up; banks steady", codes, sectors) == ["GP", "BATBC", "Bank"]   # in the order of `codes`
    assert papers.tag("Batbc slips; the best day for gp", codes, sectors) == []   # codes only in capitals: words are not codes
    assert papers.tag("GPH Ispat falls", codes, sectors) == []           # no partial-word match
    assert papers.tag("IT stocks gain", codes, sectors) == ["IT"]
    assert papers.tag("It was a quiet day", codes, sectors) == []        # acronym sectors keep their case
    assert papers.tag("Telecom shares", codes, sectors) == ["Telecom"]
    assert papers.tag("", codes, sectors) == []


def _getter(mapping):
    def get(url):
        value = mapping[url]
        if isinstance(value, Exception):
            raise value
        return value
    return get


def test_fetch_survives_bad_feeds_dedupes_and_sorts_newest_first():
    urls = [u for _, _, u in papers.FEEDS]
    mapping = {u: b"<rss><channel></channel></rss>" for u in urls}
    mapping[urls[0]] = RSS
    mapping[urls[1]] = RSS_DUP
    mapping[urls[2]] = OSError("timed out")
    mapping[urls[3]] = b"<!DOCTYPE x><rss/>"
    mapping[urls[4]] = ATOM
    out = papers.fetch(getter=_getter(mapping))
    assert set(out) == {"fetched_at", "items", "failed"}
    assert out["failed"] == [papers.FEEDS[2][1], papers.FEEDS[3][1]]
    links = [i["link"] for i in out["items"]]
    assert len(links) == len(set(links))
    assert links[:3] == ["https://example.com/n", "https://example.com/a", "https://example.com/b"]
    assert links[-2:] in (["https://example.com/c", "https://example.com/d"],
                          ["https://example.com/d", "https://example.com/c"])   # undated last
    a = next(i for i in out["items"] if i["link"] == "https://example.com/a")
    assert a["section"] == papers.FEEDS[0][1]                       # first feed wins a duplicate
    assert out["fetched_at"].endswith("+00:00")
    json.dumps(out)


def test_fetch_default_getter_is_used_when_none(monkeypatch):
    seen = []

    def fake_default(timeout):
        def get(url):
            seen.append((url, timeout))
            raise OSError("offline")
        return get

    monkeypatch.setattr(papers, "_default_getter", fake_default)
    out = papers.fetch(timeout=3)
    assert len(seen) == 7 and seen[0][1] == 3
    assert out["items"] == [] and len(out["failed"]) == 7


class _Resp:
    def __init__(self, body):
        self.body, self.pos = body, 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n):
        chunk = self.body[self.pos:self.pos + n]
        self.pos += len(chunk)
        return chunk


def _fake_opener(monkeypatch, body, captured):
    class Opener:
        def open(self, req, timeout):
            captured["ua"] = req.get_header("User-agent")
            captured["timeout"] = timeout
            return _Resp(body)

    def build_opener(*handlers):
        captured["handlers"] = [type(h).__name__ for h in handlers]
        return Opener()
    monkeypatch.setattr(papers.urllib.request, "build_opener", build_opener)


def test_default_getter_sends_user_agent_and_checks_redirects(monkeypatch):
    captured = {}
    _fake_opener(monkeypatch, b"<rss/>", captured)
    assert papers._default_getter(7)("https://example.com/feed") == b"<rss/>"
    assert captured["ua"] == "dse-report/0.1" and captured["timeout"] == 7
    assert captured["handlers"] == ["_HttpsOnlyRedirect"]


def test_default_getter_rejects_oversize_and_non_https(monkeypatch):
    _fake_opener(monkeypatch, b"x" * (papers.MAX_FEED_BYTES + 10), {})
    with pytest.raises(ValueError):
        papers._default_getter(1)("https://example.com/big")
    with pytest.raises(ValueError):
        papers._default_getter(1)("file:///etc/passwd")


def test_select_filters_by_date_tags_and_limits():
    mapping = {u: b"<rss><channel></channel></rss>" for _, _, u in papers.FEEDS}
    mapping[papers.FEEDS[0][2]] = RSS
    mapping[papers.FEEDS[4][2]] = ATOM
    fetched = papers.fetch(getter=_getter(mapping))
    got = papers.select(fetched, "2026-11-15", "2026-11-17", ["BATBC", "GP"], ["Bank", "IT"])
    assert [i["link"] for i in got] == ["https://example.com/a", "https://example.com/b",
                                        "https://example.com/x"]
    assert got[0]["tags"] == ["BATBC"]
    assert got[1]["tags"] == ["Bank"]
    assert got[2]["tags"] == ["GP", "IT"]
    assert "tags" not in fetched["items"][0]                          # input not mutated
    assert len(papers.select(fetched, "2026-11-01", "2026-11-30", [], [], limit=2)) == 2
    assert papers.select(fetched["items"], "2026-11-17", "2026-11-17", [], [])[0]["tags"] == []
    assert papers.select({}, "2026-11-01", "2026-11-30", [], []) == []


def test_tag_with_real_fixture_codes_and_sectors():
    with open("tests/fixtures/inputs_2026-11-17.json") as f:
        inputs = json.load(f)
    codes = sorted(inputs["stocks"])
    sectors = sorted({s["sector"] for s in inputs["stocks"].values()})
    tags = papers.tag("Bank shares and BATBC lead the telecom rally", codes, sectors)
    assert "BATBC" in tags and "Bank" in tags and "Telecom" in tags
    assert all(isinstance(t, str) for t in tags)


def test_parse_rss_reads_titles_wrapped_in_markup():
    data = b"""<?xml version="1.0"?><rss><channel>
<item><title><a href="/business/news/x" hreflang="en">Square Pharma  director buys</a></title>
<link>https://example.com/sq</link><pubDate>Tue, 10 Nov 26 15:54:07 +0600</pubDate></item>
<item><title>&lt;b&gt;Escaped&lt;/b&gt; tags removed</title><link>https://example.com/esc</link></item>
</channel></rss>"""
    items = papers.parse_rss(data, "S", "s")
    assert [i["title"] for i in items] == ["Square Pharma director buys", "Escaped tags removed"]
    assert items[0]["published"] == "2026-11-10T15:54:07+06:00"      # two-digit year


# ---- security hardening (review 2026-11-18) ----

def _rss(title, link="https://www.tbsnews.net/a"):
    return (f'<?xml version="1.0" encoding="utf-8"?><rss><channel><item><title>{title}</title>'
            f'<link>{link}</link><pubDate>Tue, 17 Nov 2026 10:00:00 +0600</pubDate></item></channel></rss>').encode()


def test_utf16_and_nul_bytes_are_rejected_before_parsing():
    import pytest as _pt
    doc = '<?xml version="1.0" encoding="utf-16"?><!DOCTYPE x [<!ENTITY a "b">]><rss/>'
    with _pt.raises(ValueError):
        papers.parse_rss(doc.encode("utf-16"), "S", "s")
    with _pt.raises(ValueError):
        papers.parse_rss(b"<rss>\x00</rss>", "S", "s")


def test_doctype_check_ignores_case():
    import pytest as _pt
    with _pt.raises(ValueError):
        papers.parse_rss(b'<?xml version="1.0"?><!doctype rss><rss/>', "S", "s")


def test_titles_are_plain_text_without_markup_controls_or_excess_length():
    items = papers.parse_rss(_rss("&amp;lt;img src=x onerror=alert(1) y \u202eevil"), "S", "s")
    assert papers._plain("bell\u0007 and\u200b zero-width") == "bell and zero-width"
    t = items[0]["title"]
    assert "<" not in t and ">" not in t and "‮" not in t and "\u0007" not in t
    long = papers.parse_rss(_rss("A" * 500), "S", "s")[0]["title"]
    assert len(long) <= papers.MAX_TITLE


def test_links_must_be_clean_https_urls():
    bad = ["http://www.tbsnews.net/a", 'https://a.b/"onmouseover=x', "https://user:pw@tbsnews.net/a",
           "https:///nohost", "javascript:alert(1)", "https://tbsnews.net/" + "a" * 3000]
    for link in bad:
        assert papers.parse_rss(_rss("Headline", link.replace("&", "&amp;")), "S", "s") == []
    assert papers.parse_rss(_rss("Headline", "https://www.tbsnews.net/economy/a"), "S", "s")[0]["link"]


def test_redirects_to_plain_http_are_refused():
    import urllib.request as ur
    h = papers._HttpsOnlyRedirect()
    req = ur.Request("https://www.tbsnews.net/feed")
    import pytest as _pt
    with _pt.raises(ValueError):
        h.redirect_request(req, None, 301, "Moved", {}, "http://www.tbsnews.net/feed")
    assert h.redirect_request(req, None, 301, "Moved", {}, "https://www.tbsnews.net/feed2") is not None


def test_read_stops_at_the_deadline_and_size():
    import io
    import pytest as _pt
    with _pt.raises(ValueError):
        papers._read_capped(io.BytesIO(b"x" * 100), max_bytes=10, deadline=float("inf"))
    with _pt.raises(TimeoutError):
        papers._read_capped(io.BytesIO(b"x" * 100), max_bytes=1000, deadline=0.0)
    assert papers._read_capped(io.BytesIO(b"abc"), max_bytes=10, deadline=float("inf")) == b"abc"


def test_a_failed_feed_names_the_error_class(capsys):
    def get(url):
        raise TimeoutError("slow")
    out = papers.fetch(getter=get)
    assert len(out["failed"]) == len(papers.FEEDS)
    assert "TimeoutError" in capsys.readouterr().err
