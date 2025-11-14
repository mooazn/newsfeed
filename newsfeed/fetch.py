import time
import os
import json
import feedparser
import requests
from bs4 import BeautifulSoup
from readability import Document
import trafilatura
from urllib.parse import urlparse

from .utils import canonicalize_url, url_hash, content_fingerprint
from .db import upsert_article
from .logging_setup import setup_logger

logger = setup_logger()

COOLDOWN_SECONDS = 24 * 3600
BLOCKED_PATH = os.path.join(os.path.dirname(__file__), "..", "blocked_feeds.json")


# ---------------------------------------------------------
# Blocklist checking
# ---------------------------------------------------------
def is_feed_blocked_recently(feed_url):
    if not os.path.exists(BLOCKED_PATH):
        return False

    try:
        with open(BLOCKED_PATH, "r") as f:
            data = json.load(f)
    except Exception:
        return False

    for entry in data.get("blocked", []):
        if entry.get("url") == feed_url:
            last_seen = entry.get("last_seen") or entry.get("timestamp")
            if last_seen and (time.time() - last_seen < COOLDOWN_SECONDS):
                return True
    return False


def log_blocked_feed(url, reason):
    entry = {
        "url": url,
        "last_reason": reason,
        "first_seen": int(time.time()),
        "last_seen": int(time.time()),
        "count": 1
    }

    try:
        if os.path.exists(BLOCKED_PATH):
            with open(BLOCKED_PATH, "r") as f:
                data = json.load(f)
        else:
            data = {"blocked": []}

        for ex in data["blocked"]:
            if ex["url"] == url:
                ex["last_reason"] = reason
                ex["last_seen"] = int(time.time())
                ex["count"] += 1
                break
        else:
            data["blocked"].append(entry)

        with open(BLOCKED_PATH, "w") as f:
            json.dump(data, f, indent=2)

        logger.warning(f"Feed marked as blocked: {url} ({reason})")

    except Exception as e:
        logger.error(f"Failed writing blocked_feeds.json: {e}")


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------
def _parse_date_struct(d):
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", d)
    except Exception:
        return None


def _infer_source(feed_url, entry):
    if "source" in entry and getattr(entry.source, "title", None):
        return entry.source.title
    try:
        return urlparse(feed_url).netloc.replace("www.", "")
    except Exception:
        return "Unknown"


def discover_rss(feed_url):
    try:
        base = urlparse(feed_url)
        homepage = f"{base.scheme}://{base.netloc}"
        html = requests.get(homepage, timeout=5).text
        soup = BeautifulSoup(html, "lxml")

        found = []
        for link in soup.find_all("link", type="application/rss+xml"):
            href = link.get("href")
            if href:
                found.append(href if href.startswith("http")
                             else homepage.rstrip("/") + "/" + href.lstrip("/"))
        return found
    except Exception:
        return []


COMMON_RSS_PATTERNS = [
    "/rss", "/rss.xml", "/feed", "/feed.xml",
    "/feeds", "/feeds/all", "/index.xml",
]


def generate_candidate_feeds(feed_url):
    base = f"{urlparse(feed_url).scheme}://{urlparse(feed_url).netloc}"
    return [base + p for p in COMMON_RSS_PATTERNS]


# ---------------------------------------------------------
# Text extraction
# ---------------------------------------------------------
def extract_full_text(url: str) -> str:
    try:
        downloaded = trafilatura.fetch_url(url, no_ssl=True, timeout=5)
        if downloaded:
            extracted = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=False
            )
            if extracted and len(extracted) > 200:
                return extracted.strip()
    except Exception:
        pass

    try:
        html = requests.get(url, timeout=5).text
        doc = Document(html)
        return BeautifulSoup(doc.summary(), "lxml").get_text(" ", strip=True)
    except Exception:
        return ""


# ---------------------------------------------------------
# MAIN FETCHER
# ---------------------------------------------------------
def fetch_feeds(conn, topic: str, feeds: list):
    total_inserted_topic = 0

    for feed_url in feeds:
        logger.info(f"Fetching feed: {feed_url}")

        if is_feed_blocked_recently(feed_url):
            logger.info(f"Skipped (recent failure): {feed_url}")
            continue

        fp = feedparser.parse(feed_url)
        status = getattr(fp, "status", None)

        feed_ok = (
            fp and not fp.bozo and fp.entries and
            status not in (403, 404, 429, 500, 502, 503)
        )

        if not feed_ok:
            logger.info(f"Trying alternate discovery for feed: {feed_url}")
            for alt in discover_rss(feed_url):
                fp_alt = feedparser.parse(alt)
                if not fp_alt.bozo and fp_alt.entries:
                    fp = fp_alt
                    feed_ok = True
                    logger.info(f"Found working alternate feed: {alt}")
                    break

        if not feed_ok:
            for alt in generate_candidate_feeds(feed_url):
                fp_alt = feedparser.parse(alt)
                if not fp_alt.bozo and fp_alt.entries:
                    fp = fp_alt
                    feed_ok = True
                    logger.info(f"Found working fallback pattern: {alt}")
                    break

        if not feed_ok or not fp.entries:
            logger.error(f"Feed failed: {feed_url}")
            log_blocked_feed(feed_url, f"http_status_{status}")
            continue

        inserted_count = 0
        skipped_count = 0

        for e in fp.entries[:50]:
            url = canonicalize_url(e.get("link") or e.get("id") or "")
            if not url:
                skipped_count += 1
                continue

            title = e.get("title", "").strip()
            published = _parse_date_struct(
                e.get("published_parsed") or e.get("updated_parsed")
            ) or ""
            source = _infer_source(feed_url, e)

            full_text = extract_full_text(url) or (e.get("summary") or "")
            content_hash = content_fingerprint(full_text)

            cur = conn.execute(
                "SELECT 1 FROM articles WHERE content_hash=? OR title=?",
                (content_hash, title),
            )
            if cur.fetchone():
                skipped_count += 1
                continue

            rec = {
                "url_hash": url_hash(url),
                "url": url,
                "source": source,
                "title": title,
                "published_at": published,
                "topic": topic,
                "text": full_text,
                "score": 0.0,
                "chosen": 0,
                "content_hash": content_hash,
            }

            upsert_article(conn, rec)
            inserted_count += 1

        conn.commit()

        total_seen = inserted_count + skipped_count
        logger.info(
            f"Feed processed: {feed_url} — "
            f"{total_seen} items (inserted {inserted_count}, skipped {skipped_count})"
        )

        total_inserted_topic += inserted_count

    logger.info(f"Total new articles added for topic '{topic}': {total_inserted_topic}\n")
