import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "news.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)

    # Enable WAL for faster writes & parallel reads
    conn.execute("PRAGMA journal_mode=WAL;")

    conn.execute("""
    CREATE TABLE IF NOT EXISTS articles(
        url_hash TEXT PRIMARY KEY,
        url TEXT,
        source TEXT,
        title TEXT,
        published_at TEXT,
        topic TEXT,
        text TEXT,
        score REAL DEFAULT 0.0,
        chosen INTEGER DEFAULT 0,
        content_hash TEXT,
        sent INTEGER DEFAULT 0
    )
    """)

    # Important index for speed
    conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_topic_sent
    ON articles(topic, sent);
    """)

    return conn


def upsert_article(conn, rec):
    """
    Important: We DO NOT update `sent`.
    Once sent=1, it stays 1 forever.
    """
    conn.execute(
        """
        INSERT INTO articles(
            url_hash, url, source, title, published_at,
            topic, text, score, chosen, content_hash
        )
        VALUES(
            :url_hash, :url, :source, :title, :published_at,
            :topic, :text, :score, :chosen, :content_hash
        )
        ON CONFLICT(url_hash) DO UPDATE SET
            source=excluded.source,
            title=excluded.title,
            published_at=excluded.published_at,
            topic=excluded.topic,
            text=excluded.text,
            score=excluded.score,
            content_hash=excluded.content_hash
            -- NOTE: sent is intentionally NOT updated!
        """,
        rec
    )


def fetch_candidates(conn, topic, limit=20):
    """
    Still useful for debugging or alternate flows.
    But now includes `sent` so we can reason about it.
    """
    cur = conn.execute(
        """
        SELECT url, source, title, published_at,
               topic, text, score, sent
        FROM articles
        WHERE topic=?
        ORDER BY score DESC
        LIMIT ?
        """,
        (topic, limit),
    )
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]
