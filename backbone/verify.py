"""Locate model-supplied evidence quotes in the source text.

Returns (start, end, line, match) where match is 'exact', 'normalised', 'approx' or 'missing'.
Normalisation folds dashes/quotes/whitespace/case, so harmless copy differences still anchor to an
exact character span in the original document.
"""
import difflib
import re

_FOLD = {"–": "-", "—": "-", "−": "-", "‘": "'", "’": "'", "“": '"', "”": '"',
         " ": " "}


def _normalise(text: str):
    """Fold text and keep a map from each folded char back to its original index."""
    out, idx, prev_space = [], [], False
    for i, ch in enumerate(text):
        ch = _FOLD.get(ch, ch)
        if ch.isspace():
            if prev_space:
                continue
            ch, prev_space = " ", True
        else:
            prev_space = False
        out.append(ch.lower())
        idx.append(i)
    return "".join(out), idx


def _line(text, pos):
    return text.count("\n", 0, pos) + 1


def locate(text: str, quote: str | None):
    if not quote or not quote.strip():
        return None, None, None, "missing"
    q = quote.strip()
    pos = text.find(q)
    if pos >= 0:
        return pos, pos + len(q), _line(text, pos), "exact"
    nt, idx = _normalise(text)
    nq, _ = _normalise(q)
    nq = nq.strip()
    pos = nt.find(nq)
    if pos >= 0:
        s, e = idx[pos], idx[pos + len(nq) - 1] + 1
        return s, e, _line(text, s), "normalised"
    # fuzzy: longest common block must cover most of the quote
    sm = difflib.SequenceMatcher(None, nt, nq, autojunk=False)
    m = sm.find_longest_match(0, len(nt), 0, len(nq))
    if m.size >= max(12, int(0.75 * len(nq))):
        s = idx[max(0, m.a - m.b)]
        e = idx[min(len(idx) - 1, m.a - m.b + len(nq) - 1)] + 1
        return s, e, _line(text, s), "approx"
    return None, None, None, "missing"


_QUOTE_RE = re.compile(r"“([^”]{4,600})”|\"([^\"\n]{4,600})\"")
_DOCREF_RE = re.compile(r"\b([A-Z]{2,}-[A-Z]?\d{2,}[A-Za-z0-9~]*)\b")


def check_citations(answer: str, docs: dict[str, str]) -> list[dict]:
    """Check every quoted passage in an answer against the source documents.

    A quote passes if all its fragments (split on ellipses) occur, after normalisation, in one document
    cited on the same line (or in any document if the line cites none)."""
    results = []
    for line in answer.split("\n"):
        cited = [d for d in _DOCREF_RE.findall(line) if d in docs]
        for m in _QUOTE_RE.finditer(line):
            q = (m.group(1) or m.group(2)).strip().replace("\\|", "|")  # Markdown-table escapes
            frags = [f.strip(" .,;:[]") for f in re.split(r"…|\.\.\.|\[…\]", q)]
            frags = [f for f in frags if len(f) >= 5]
            if not frags:
                continue
            pool = cited or list(docs)
            found = next((d for d in pool if all(locate(docs[d], f)[3] in ("exact", "normalised") for f in frags)), None)
            results.append({"quote": q, "cited": cited, "verified": found is not None, "found_in": found})
    return results


TIME_RE = re.compile(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)")


def to_minutes(hhmm: str | None):
    """Minutes since midnight. Accepts 'HH:MM' and also forms small models produce, e.g. '2026-01-22T10:30'."""
    if not hhmm:
        return None
    m = list(TIME_RE.finditer(hhmm.strip()))
    return int(m[-1].group(1)) * 60 + int(m[-1].group(2)) if m else None
