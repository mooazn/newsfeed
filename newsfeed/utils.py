import re
import hashlib
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
import os

def file_hash(path: str):
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()

def compute_html_hash(html: str):
    return hashlib.sha256(html.encode("utf-8")).hexdigest()


def canonicalize_url(url: str) -> str:
    if not url:
        return ""

    try:
        parsed = urlparse(url)

        # Remove tracking parameters
        query = dict(parse_qsl(parsed.query))
        bad_params = {"utm_source", "utm_medium", "utm_campaign", "utm_term",
                      "utm_content", "cmpid", "fbclid", "gclid", "mc_cid",
                      "mc_eid", "ref"}
        cleaned_query = {k: v for k, v in query.items() if k not in bad_params}

        # Force https
        scheme = "https"

        # Remove mobile prefixes e.g. m., mobile.
        netloc = parsed.netloc.replace("m.", "").replace("mobile.", "")

        # Drop fragments (#comments)
        fragment = ""

        normalized = urlunparse((
            scheme,
            netloc,
            parsed.path,
            parsed.params,
            urlencode(cleaned_query),
            fragment
        ))
        return normalized

    except Exception:
        return url


def content_fingerprint(text: str) -> str:
    if not text:
        return ""
    first = text[:300].strip().lower()
    return hashlib.sha256(first.encode("utf-8")).hexdigest()


def url_hash(url: str) -> str:
    return hashlib.sha256(canonicalize_url(url).encode("utf-8")).hexdigest()

def safe_get(d: dict, *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur

_sentence_splitter = re.compile(r'(?<=[.!?])\s+(?=[A-Z0-9\"])')

def split_sentences(text: str):
    # Simple sentence splitter; avoids external heavy deps
    return [s.strip() for s in _sentence_splitter.split(text) if s.strip()]
