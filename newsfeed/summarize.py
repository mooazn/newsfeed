from .utils import split_sentences

def summarize_three_sentences(title: str, text: str) -> list[str]:
    """Return exactly three sentences trying to cover:
    1) What happened
    2) Why it matters
    3) What's next / impact
    Heuristic: take first 6-8 sentences, prefer those containing named entities like dates/numbers/verbs.
    """
    if not text:
        return [title, "", ""]

    sents = split_sentences(text)
    head = sents[:8] if len(sents) >= 8 else sents
    if len(head) >= 3:
        candidates = _rank_sentences(head, title)
        chosen = [s for _, s in sorted(candidates)[:3]]
    else:
        chosen = head + [""] * (3 - len(head))
    # Normalize: strip and ensure sentence end punctuation
    cleaned = [ _ensure_period(s) for s in chosen ]
    return cleaned

def _rank_sentences(sents, title):
    scores = []
    for i, s in enumerate(sents):
        score = i  # lead bias
        # simple boosts: digits/dates/verbs-as-proxy
        if any(ch.isdigit() for ch in s):
            score -= 0.3
        if any(w in s.lower() for w in ("will", "expected", "plan", "could", "may")):
            score -= 0.1
        # prefer sentences that contain title tokens
        for t in title.split()[:5]:
            if t and t.lower() in s.lower():
                score -= 0.05
        scores.append((score, s))
    return scores

def _ensure_period(s: str) -> str:
    s = s.strip()
    return s if s.endswith(('.', '!', '?')) else s + '.'
