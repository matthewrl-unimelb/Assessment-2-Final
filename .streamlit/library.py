"""
library.py - the app's "closed world" regulation library.

The AI is only ever shown passages from this library - never the web. The library is:
  * library/chunks.json            1,164 passages from 14 regulations (built once by tools/build_library.py)
  * library/embeddings.npy         each passage turned into a vector by OpenAI's text-embedding-3-large
  * library/embeddings_meta.json   which model built the vectors, and a fingerprint of the passages
                                   (built once by tools/build_embeddings.py)

How a search works ("search by meaning"):
  1. the question is turned into a vector by text-embedding-3-large (one small OpenAI call);
  2. the app compares it with every passage's vector (cosine similarity - plain arithmetic, no AI);
  3. the closest passages are handed to the AI.
If the vectors are missing, or OpenAI cannot be reached, the app falls back to a keyword search (BM25)
and says so - so a search never simply fails.

When the app already knows which section defines something (e.g. 12 CFR 252.5 for the size categories),
it fetches that section directly with section() instead of searching.
"""

import hashlib
import json
import math
import os
import re
from collections import Counter

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
CHUNKS_PATH = os.path.join(ROOT, "library", "chunks.json")
INDEX_PATH = os.path.join(ROOT, "library", "embeddings.npy")
META_PATH = os.path.join(ROOT, "library", "embeddings_meta.json")
EMBED_MODEL = "text-embedding-3-large"

MIN_SIMILARITY = 0.25     # meaning search: below this, the best passage is treated as "not about this"
MIN_KEYWORD_SCORE = 4.0   # keyword search: the same idea on the BM25 scale


def embedding_text(chunk):
    """The text that is turned into a vector for each passage: its citation, title and words."""
    return f"{chunk['cite']} - {chunk['title']}\n{chunk['text']}"


def fingerprint(chunks):
    """A short code that changes if any passage is added, removed or relabelled - so stale vectors are never used."""
    return hashlib.sha256("|".join(c["id"] + ":" + c["cite"] for c in chunks).encode()).hexdigest()[:16]


# --------------------------------------------------------------------------------------
# Keyword search (BM25) - only the fallback
# --------------------------------------------------------------------------------------
TOKEN = re.compile(r"[a-z0-9]+(?:\.[0-9a-z]+)?")
STOP = set("the a an of to and or in for on by with as is are be this that which any such its it at from under shall may".split())


def _tokens(text):
    return [t for t in TOKEN.findall(text.lower()) if t not in STOP]


class Library:
    def __init__(self, path=CHUNKS_PATH):
        with open(path, encoding="utf-8") as fh:
            self.chunks = json.load(fh)
        self.by_id = {c["id"]: c for c in self.chunks}
        self.embed_fn = None          # set by the app: a function that turns texts into vectors (ai.embed)
        self._query_cache = {}
        self.last_note = ""
        self._load_index()
        # keyword index (fallback): citation and title counted twice so "217.10" finds its section
        self.docs = [_tokens(c["cite"] + " " + c["title"] + " " + c["cite"] + " " + c["title"] + " " + c["text"]) for c in self.chunks]
        self.lengths = [len(d) for d in self.docs]
        self.avg_len = sum(self.lengths) / max(len(self.lengths), 1)
        self.tf = [Counter(d) for d in self.docs]
        df = Counter()
        for d in self.docs:
            df.update(set(d))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.pairs = [Counter(zip(d, d[1:])) for d in self.docs]

    # ---- the meaning index ----
    def _load_index(self):
        self.index, self.index_problem = None, ""
        if not (os.path.exists(INDEX_PATH) and os.path.exists(META_PATH)):
            self.index_problem = "The search index has not been built yet (run tools/build_embeddings.py)."
            return
        with open(META_PATH, encoding="utf-8") as fh:
            meta = json.load(fh)
        vectors = np.load(INDEX_PATH).astype(np.float32)
        if meta.get("model") != EMBED_MODEL or meta.get("fingerprint") != fingerprint(self.chunks) \
                or vectors.shape[0] != len(self.chunks):
            self.index_problem = "The search index does not match the library - rebuild it with tools/build_embeddings.py."
            return
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
        self.index, self.meta = vectors, meta

    @property
    def by_meaning(self):
        return self.index is not None

    def status(self):
        docs = sorted({c["source"] for c in self.chunks})
        return {"documents": len(docs), "passages": len(self.chunks), "by_meaning": self.by_meaning,
                "problem": self.index_problem}

    def sources(self):
        seen = {}
        for c in self.chunks:
            seen.setdefault(c["source"], {"source": c["source"], "status": c["status"], "as_of": c["as_of"], "passages": 0})
            seen[c["source"]]["passages"] += 1
        return list(seen.values())

    # ---- searching ----
    def _query_vector(self, query):
        if query not in self._query_cache:
            vec = np.asarray(self.embed_fn([query])[0], dtype=np.float32)
            self._query_cache[query] = vec / np.linalg.norm(vec)
        return self._query_cache[query]

    def search(self, query, k=6):
        """The k passages closest in meaning to the query, best first. Each gets a 'score' and the 'method' used."""
        if self.by_meaning and self.embed_fn is not None:
            try:
                sims = self.index @ self._query_vector(query)
                best = np.argsort(-sims)[:k]
                self.last_note = ""
                return [dict(self.chunks[i], score=round(float(sims[i]), 3), method="meaning") for i in best]
            except Exception as exc:          # e.g. no key yet, or OpenAI unreachable: fall back, and say so
                self.last_note = f"Searched by keywords instead of meaning ({exc.__class__.__name__})."
        else:
            self.last_note = "Searched by keywords: " + (self.index_problem or "no OpenAI key yet.")
        return self.keyword_search(query, k)

    def keyword_search(self, query, k=6, k1=1.5, b=0.75):
        q = _tokens(query)
        q_pairs = list(zip(q, q[1:]))
        scores = []
        for i, tf in enumerate(self.tf):
            s = 0.0
            for t in q:
                if t in tf:
                    f = tf[t]
                    s += self.idf[t] * f * (k1 + 1) / (f + k1 * (1 - b + b * self.lengths[i] / self.avg_len))
            if s > 0:
                for pair in q_pairs:
                    hits = self.pairs[i].get(pair, 0)
                    if hits:
                        s += min(hits, 3) * 0.5 * (self.idf.get(pair[0], 0) + self.idf.get(pair[1], 0))
                scores.append((s, i))
        scores.sort(reverse=True)
        return [dict(self.chunks[i], score=round(s, 2), method="keywords") for s, i in scores[:k]]

    def relevant(self, passages):
        """Is the best passage close enough to be about the question at all? (If not, the AI is not called.)"""
        if not passages:
            return False
        best = passages[0]
        if best.get("method") == "section":
            return True
        floor = MIN_SIMILARITY if best.get("method") == "meaning" else MIN_KEYWORD_SCORE
        return best["score"] >= floor

    def section(self, cite_prefix, containing=None, limit=2):
        """Fetch passages by citation (e.g. '12 CFR 217.20'), optionally only those containing a phrase."""
        out = []
        for c in self.chunks:
            base = c["cite"].split(" (part")[0]
            if base == cite_prefix and (containing is None or containing.lower() in c["text"].lower()):
                out.append(dict(c, score=1.0, method="section"))
                if len(out) >= limit:
                    break
        return out

    def fetch(self, queries):
        """Several exact sections at once: each item is (cite, phrase or None, how many). Duplicates are dropped."""
        seen, out = set(), []
        for cite, phrase, limit in queries:
            for p in self.section(cite, phrase, limit):
                if p["id"] not in seen:
                    seen.add(p["id"])
                    out.append(p)
        return out
