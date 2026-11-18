"""Newspaper headlines from RSS/Atom feeds: headline, link, time, source and section only."""
from __future__ import annotations

import html
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Callable

DAILY_STAR = "The Daily Star"
TBS = "The Business Standard"
PROTHOM_ALO = "Prothom Alo English"

FEEDS = [
    (DAILY_STAR, "Daily Star stock market", "https://www.thedailystar.net/business/economy/stock/rss.xml"),
    (DAILY_STAR, "Daily Star business", "https://www.thedailystar.net/business/rss.xml"),
    (DAILY_STAR, "Daily Star organisation news",
     "https://www.thedailystar.net/business/organisation-news/rss.xml"),
    (TBS, "TBS stocks", "https://www.tbsnews.net/economy/stocks/rss.xml"),
    (TBS, "TBS corporates", "https://www.tbsnews.net/economy/corporates/rss.xml"),
    (TBS, "TBS economy", "https://www.tbsnews.net/economy/rss.xml"),
    (PROTHOM_ALO, "Prothom Alo all news", "https://en.prothomalo.com/feed/"),
]

USER_AGENT = "dse-report/0.1"
MAX_FEED_BYTES = 5_000_000
MAX_TITLE = 200
MAX_LINK = 2048
FEED_DEADLINE_S = 30          # whole download, not per socket read
READ_CHUNK = 65_536
MAX_REDIRECTS = 3
DHAKA = timezone(timedelta(hours=6))
ATOM_NS = "{http://www.w3.org/2005/Atom}"
FORBIDDEN = ("<!doctype", "<!entity")
BOMS = (b"\xff\xfe", b"\xfe\xff", b"\x00\x00\xfe\xff", b"\xff\xfe\x00\x00")

Getter = Callable[[str], bytes]


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(el: ET.Element, *names: str) -> str | None:
    for child in el:
        if _local(child.tag) in names and child.text and child.text.strip():
            return child.text.strip()
    return None


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(DHAKA).replace(microsecond=0).isoformat()


def _published(raw: str | None) -> str | None:
    """RFC 822 (RSS) or ISO 8601 (Atom) -> ISO datetime in Dhaka time, or None."""
    if not raw:
        return None
    try:
        return _iso(parsedate_to_datetime(raw))
    except (TypeError, ValueError, IndexError):
        pass
    try:
        return _iso(datetime.fromisoformat(raw.replace("Z", "+00:00")))
    except ValueError:
        return None


def _link(el: ET.Element) -> str | None:
    for child in el:
        if _local(child.tag) != "link":
            continue
        href = child.get("href") if child.get("rel", "alternate") == "alternate" else None
        value = (href or child.text or "").strip()
        if value:
            return value
    return None


def _plain(text: str) -> str:
    """Plain text only: markup, angle brackets, control and bidi characters removed; spaces collapsed; capped."""
    text = unicodedata.normalize("NFC", html.unescape(text))
    text = re.sub(r"<[^>]*>", "", text).replace("<", "").replace(">", "")
    text = "".join(ch for ch in text if unicodedata.category(ch) not in ("Cc", "Cf") or ch in " \t\n")
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= MAX_TITLE else text[: MAX_TITLE - 1].rstrip() + "…"


def _title(el: ET.Element) -> str:
    """Headline text, also when a feed wraps it in markup (<a>) or escaped tags."""
    node = next((c for c in el if _local(c.tag) == "title"), None)
    return _plain("".join(node.itertext()) if node is not None else "")


def _safe_link(link: str | None) -> str | None:
    """Only a clean https URL with a host and no credentials, spaces, quotes or control characters."""
    if not link or len(link) > MAX_LINK or re.search(r'[\s"\'<>\\\x00-\x1f\x7f]', link):
        return None
    parts = urllib.parse.urlsplit(link)
    if parts.scheme != "https" or not parts.hostname or "@" in parts.netloc:
        return None
    return link


def _item(el: ET.Element, source: str, section: str) -> dict | None:
    title = _title(el)
    link = _safe_link(_link(el))
    if not title or not link:
        return None
    when = _child_text(el, "pubDate", "published", "updated", "date")
    return {"source": source, "section": section, "title": title, "link": link,
            "published": _published(when)}


def parse_rss(data: bytes, source: str, section: str) -> list[dict]:
    """Items of an RSS 2.0 or Atom feed. UTF-8 only; rejects DTDs and entity declarations (no defusedxml)."""
    if data.startswith(BOMS) or b"\x00" in data:
        raise ValueError("feed is not UTF-8")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("feed is not UTF-8") from exc
    if any(mark in text.lower() for mark in FORBIDDEN):
        raise ValueError("feed declares a DTD or entities")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError(f"feed is not valid XML: {exc}") from exc
    nodes = [el for el in root.iter() if _local(el.tag) in ("item", "entry")]
    items = (_item(el, source, section) for el in nodes)
    return [i for i in items if i is not None]


def _word_pattern(name: str, case_sensitive: bool) -> re.Pattern:
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(r"(?<![\w&])" + re.escape(name) + r"s?(?![\w&])", flags)


def tag(title: str, codes: list[str], sectors: list[str]) -> list[str]:
    """Trading codes (whole words, in capitals as they are written) and sector names named in a headline.

    A sector name in capitals (e.g. "IT") must match its case, so "It was" does not tag it."""
    if not title:
        return []
    found = [c for c in codes if c and _word_pattern(c, True).search(title)]
    found += [s for s in sectors if s and _word_pattern(s, s.isupper()).search(title)]
    return list(dict.fromkeys(found))


class _HttpsOnlyRedirect(urllib.request.HTTPRedirectHandler):
    """Follow at most MAX_REDIRECTS redirects, and only to https."""
    max_redirections = MAX_REDIRECTS

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != "https":
            raise ValueError("redirect away from https refused")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _read_capped(resp, max_bytes: int, deadline: float) -> bytes:
    """Read in chunks until done, failing past ``max_bytes`` or the monotonic ``deadline``."""
    chunks, size = [], 0
    while True:
        if time.monotonic() > deadline:
            raise TimeoutError("feed download took too long")
        chunk = resp.read(READ_CHUNK)
        if not chunk:
            return b"".join(chunks)
        size += len(chunk)
        if size > max_bytes:
            raise ValueError("feed is too large")
        chunks.append(chunk)


def _default_getter(timeout: float) -> Getter:
    opener = urllib.request.build_opener(_HttpsOnlyRedirect())

    def get(url: str) -> bytes:
        if not url.startswith("https://"):
            raise ValueError("only https feeds are fetched")
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with opener.open(req, timeout=timeout) as resp:   # noqa: S310 (https only, redirects checked)
            return _read_capped(resp, MAX_FEED_BYTES, time.monotonic() + FEED_DEADLINE_S)
    return get


def _newest_first(items: list[dict]) -> list[dict]:
    dated = sorted((i for i in items if i["published"]), key=lambda i: i["published"], reverse=True)
    return dated + [i for i in items if not i["published"]]


def fetch(getter: Getter | None = None, timeout: float = 15) -> dict:
    """All feeds: {fetched_at, items (deduplicated by link, newest first), failed [section names]}."""
    get = getter or _default_getter(timeout)
    items: list[dict] = []
    failed: list[str] = []
    seen: set[str] = set()
    for source, section, url in FEEDS:
        try:
            parsed = parse_rss(get(url), source, section)
        except Exception as exc:   # one bad feed (network, XML, size) must not stop the others
            print(f"papers: {section} failed: {type(exc).__name__}", file=sys.stderr)
            failed.append(section)
            continue
        fresh = [i for i in parsed if i["link"] not in seen]
        seen.update(i["link"] for i in fresh)
        items.extend(fresh)
    return {"fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "items": _newest_first(items), "failed": failed}


def select(papers: dict | list, start: str, end: str, codes: list[str], sectors: list[str],
           limit: int = 12) -> list[dict]:
    """Items published on Dhaka dates start..end (inclusive, 'YYYY-MM-DD'), each with its tags."""
    items = papers.get("items", []) if isinstance(papers, dict) else papers
    inside = [i for i in items if i.get("published") and start <= i["published"][:10] <= end]
    return [{**i, "tags": tag(i["title"], codes, sectors)} for i in inside[:limit]]
