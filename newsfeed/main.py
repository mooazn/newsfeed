import os
import yaml
from datetime import datetime, timezone
from dotenv import load_dotenv

from .utils import compute_html_hash, file_hash
from .db import get_conn
from .fetch import fetch_feeds
from .summarize import summarize_three_sentences
from .render import render_email
from .send_email import send_via_gmail
from .logging_setup import setup_logger


logger = setup_logger()

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "out")
os.makedirs(OUT_DIR, exist_ok=True)


# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------
def load_config():
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    with open(cfg_path, "r") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------
# SCORING
# ---------------------------------------------------------
def score(title, source, published_at, topic, cfg, text):
    import math

    # Recency half-life ~1 day
    try:
        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        age_hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
        recency = math.exp(-max(age_hours, 0) / 24)
    except Exception:
        recency = 0.1

    # Source weight
    sweight = 0.0
    for k, v in (cfg.get("source_weights") or {}).items():
        if k.lower() in (source or "").lower():
            sweight = max(sweight, float(v))

    # Keyword relevance
    kw_hits = sum(
        0.4 for w in (cfg.get("topic_keywords", {}).get(topic, []))
        if w.lower() in title.lower()
    )

    # Long-form bonus
    length_boost = min(len(text) / 5000, 0.4)

    # Headline action words
    hot = ["breakthrough", "crisis", "warns", "reveals", "new", "major"]
    hot_score = sum(0.15 for w in hot if w in title.lower())

    return recency + sweight + kw_hits + length_boost + hot_score


# ---------------------------------------------------------
# ARCHIVE
# ---------------------------------------------------------
def archive_html(html: str):
    history_dir = os.path.join(OUT_DIR, "history")
    os.makedirs(history_dir, exist_ok=True)

    filename = datetime.now().strftime("%Y-%m-%d") + ".html"
    path = os.path.join(history_dir, filename)

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info(f"Archived: {path}")


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
def main():
    print("Daily Brief started.")

    load_dotenv()
    cfg = load_config()
    conn = get_conn()

    FAST_TEST = os.getenv("FAST_TEST", "false").lower() == "true"
    if FAST_TEST:
        logger.info("FAST_TEST active — trimming feeds, skipping email.")
        cfg["per_topic"] = 1
        for spec in cfg["topics"].values():
            spec["feeds"] = spec["feeds"][:1]

    # =====================================================
    # FETCH PHASE
    # =====================================================
    print("Fetching feeds…")
    for topic, spec in cfg["topics"].items():
        logger.info(f"[FETCH] {topic}")
        fetch_feeds(conn, topic, spec.get("feeds", []))
    conn.commit()

    # =====================================================
    # CLEANUP PHASE
    # =====================================================
    print("Cleaning up old articles…")
    logger.info("Running cleanup rules.")

    # 48h absolute cutoff
    conn.execute("""
        DELETE FROM articles
        WHERE published_at < datetime('now','-48 hours');
    """)

    # 24h grace for unsent items
    conn.execute("""
        DELETE FROM articles
        WHERE sent = 0
        AND published_at < datetime('now','-24 hours');
    """)

    # Cap backlog
    for topic in cfg["topics"]:
        conn.execute(f"""
            DELETE FROM articles
            WHERE sent = 0
            AND topic = '{topic}'
            AND url_hash NOT IN (
                SELECT url_hash FROM articles
                WHERE topic = '{topic}' AND sent = 0
                ORDER BY datetime(published_at) DESC
                LIMIT 30
            );
        """)

    conn.commit()
    logger.info("Cleanup done.")

    # =====================================================
    # PROCESS PHASE
    # =====================================================
    print("Scoring & selecting articles…")

    grouped = {}
    per_topic = int(os.getenv("MAX_PER_TOPIC") or cfg.get("per_topic", 3))

    anti_scraper_markers = [
        "access denied",
        "you don't have permission",
        "forbidden",
        "error 403",
        "request blocked",
        "unusual traffic",
        "captcha",
        "permission denied",
    ]

    for topic in cfg["topics"]:
        logger.info(f"[PROCESS] {topic}")

        # Load unsent
        cur = conn.execute("""
            SELECT url, source, title, published_at, topic, text, score, content_hash
            FROM articles
            WHERE topic=? AND sent=0
            ORDER BY datetime(published_at) DESC
        """, (topic,))
        candidates = [dict(zip([col[0] for col in cur.description], row)) for row in cur.fetchall()]

        if not candidates:
            logger.info(f"No unsent content for {topic}.")
            continue

        logger.info(f"Loaded {len(candidates)} candidates.")

        # Keyword filtering
        kw = [k.lower() for k in cfg.get("topic_keywords", {}).get(topic, [])]
        filtered = [
            c for c in candidates
            if any(k in (c["title"] + c["text"]).lower() for k in kw)
        ]

        if not filtered:
            filtered = candidates[:10]
            logger.info("No keyword hits; using fallback set.")
        else:
            logger.info(f"Keyword matches: {len(filtered)}")

        # Score
        for c in filtered:
            c["score"] = score(
                c["title"], c["source"], c["published_at"],
                topic, cfg, c["text"]
            )

        chosen = sorted(filtered, key=lambda x: x["score"], reverse=True)[:per_topic]
        logger.info(f"Selected {len(chosen)} articles.")

        out_items = []

        # Expand summaries
        for it in chosen:
            text_lower = it["text"].lower() if it["text"] else ""
            summary_failed = False

            if any(m in text_lower for m in anti_scraper_markers) or len(it["text"]) < 150:
                logger.warning(f"Blocked or short article: {it['url']}")
                s1, s2, s3 = it["title"], "", ""
                summary_failed = True
            else:
                try:
                    s1, s2, s3 = summarize_three_sentences(it["title"], it["text"])
                except Exception as e:
                    logger.error(f"Summary error for '{it['title']}': {e}")
                    s1, s2, s3 = it["title"], "", ""
                    summary_failed = True

            # Mark sent
            conn.execute(
                "UPDATE articles SET sent=1 WHERE content_hash=?",
                (it["content_hash"],)
            )

            out_items.append({
                "url": it["url"],
                "title": it["title"],
                "source": it["source"],
                "s1": s1,
                "s2": s2,
                "s3": s3,
                "summary_failed": summary_failed,
            })

        conn.commit()
        grouped[topic] = out_items

    # =====================================================
    # NOTHING SELECTED?
    # =====================================================
    total_items = sum(len(v) for v in grouped.values())
    if total_items == 0:
        logger.info("No new content. Nothing to email.")
        print("Daily Brief finished.")
        return

    # =====================================================
    # RENDER HTML
    # =====================================================
    html = render_email(grouped, os.getenv("TIMEZONE") or cfg["run_time"].split()[-1])

    out_path = os.path.join(OUT_DIR, "latest.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info(f"Newsletter written to: {out_path}")
    archive_html(html)

    # =====================================================
    # DUPLICATE DETECTION
    # =====================================================
    html_hash = compute_html_hash(html)
    hash_path = os.path.join(OUT_DIR, "latest.hash")
    prev_hash = file_hash(hash_path)

    if prev_hash == html_hash:
        logger.info("Newsletter unchanged — suppressing email.")
        print("Daily Brief finished.")
        return

    with open(hash_path, "w") as f:
        f.write(html_hash)

    # =====================================================
    # EMAIL
    # =====================================================
    if FAST_TEST:
        logger.info("FAST_TEST — skipping email.")
        print("Daily Brief finished.")
        return

    mail_from = os.getenv("MAIL_FROM")
    mail_to = os.getenv("MAIL_TO")

    if mail_from and mail_to:
        logger.info(f"Sending email to {mail_to}...")
        send_via_gmail(html, "Daily Brief", mail_from, mail_to)
    else:
        logger.warning("MAIL_FROM or MAIL_TO missing — email disabled.")

    print("Daily Brief finished.")


if __name__ == "__main__":
    main()
