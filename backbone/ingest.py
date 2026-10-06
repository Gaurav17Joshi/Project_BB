"""Read documents, fingerprint them, and register new ones. Exact duplicate copies map to one document."""
import hashlib
import re
import time
from pathlib import Path

DOC_ID_RE = re.compile(r"Document ID:\s*([A-Za-z0-9_.-]+)")


def normalise_text(raw: str) -> str:
    lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(l.rstrip() for l in lines).strip() + "\n"


def fingerprint(text: str) -> str:
    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()


def ingest(con, docs_dir: Path) -> dict:
    """Register every file under docs_dir. Returns {'new': [doc_key], 'duplicates': [(path, doc_key)], 'seen': n}."""
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    new, dups, seen = [], [], 0
    keys_this_run = set()
    paths = sorted(p for p in Path(docs_dir).rglob("*") if p.is_file() and p.suffix.lower() in {".txt", ".md"})
    for p in paths:
        seen += 1
        text = normalise_text(p.read_text(encoding="utf-8-sig"))
        key = fingerprint(text)
        rel = str(p.resolve())
        known = con.execute("SELECT 1 FROM documents WHERE doc_key=?", (key,)).fetchone()
        # A copy is the same text under a second file that exists now. A file that was only moved (another folder,
        # or the project copied to another machine) is the same document, not a duplicate.
        others = [r["path"] for r in con.execute("SELECT path FROM document_files WHERE doc_key=? AND path<>?", (key, rel))]
        is_copy = key in keys_this_run or any(Path(o).exists() for o in others)
        keys_this_run.add(key)
        con.execute("INSERT OR REPLACE INTO document_files(path, doc_key, seen_at) VALUES (?,?,?)", (rel, key, now))
        if known:
            if is_copy:
                dups.append((p.name, key))
            continue
        m = DOC_ID_RE.search(text)
        doc_id = m.group(1) if m else p.stem
        if con.execute("SELECT 1 FROM documents WHERE doc_id=?", (doc_id,)).fetchone():
            doc_id = f"{doc_id}~{key[:6]}"  # same printed ID, different content: keep both, label distinctly
        con.execute("INSERT INTO documents(doc_key, doc_id, filename, text, n_chars, ingested_at) VALUES (?,?,?,?,?,?)",
                    (key, doc_id, p.name, text, len(text), now))
        new.append(key)
    con.commit()
    return {"new": new, "duplicates": dups, "seen": seen}
