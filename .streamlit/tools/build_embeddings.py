"""
tools/build_embeddings.py - run ONCE to build the search index for the regulation library.

It sends each of the library's 1,164 passages to OpenAI's text-embedding-3-large model, which turns each
passage into a list of 3,072 numbers (a "vector") that captures its meaning. The vectors are saved to
library/embeddings.npy so the app can find the passages closest in meaning to any question.

Cost: about 875,000 tokens - about US$0.11 at OpenAI's price for text-embedding-3-large. Time: 1-2 minutes.

Run it from the top folder of the project:
    python3 tools/build_embeddings.py
It asks for your OpenAI API key (typing is hidden). The key is used for this run only and is not saved.
"""

import datetime
import getpass
import json
import os
import sys
import time

import numpy as np
import openai

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from library import CHUNKS_PATH, EMBED_MODEL, INDEX_PATH, META_PATH, embedding_text, fingerprint  # noqa: E402

BATCH = 64          # passages per request


def main():
    key = os.environ.get("OPENAI_API_KEY") or getpass.getpass("Paste your OpenAI API key (typing is hidden), then press Enter: ")
    client = openai.OpenAI(api_key=key.strip(), max_retries=5, timeout=120)
    with open(CHUNKS_PATH, encoding="utf-8") as fh:
        chunks = json.load(fh)
    texts = [embedding_text(c) for c in chunks]
    vectors = []
    for start in range(0, len(texts), BATCH):
        batch = texts[start:start + BATCH]
        for attempt in range(6):
            try:
                resp = client.embeddings.create(model=EMBED_MODEL, input=batch)
                break
            except openai.RateLimitError as exc:
                if "insufficient_quota" in str(exc):
                    sys.exit("Stopped: this OpenAI account has no credit left. Add credit at platform.openai.com, then run again.")
                wait = 15 * (attempt + 1)
                print(f"  OpenAI is busy - waiting {wait} seconds…")
                time.sleep(wait)
        else:
            sys.exit("Stopped: OpenAI kept refusing (rate limit). Try again in a few minutes.")
        vectors.extend(d.embedding for d in resp.data)
        print(f"  {len(vectors):,} of {len(texts):,} passages done")

    arr = np.asarray(vectors, dtype=np.float32)
    arr /= np.linalg.norm(arr, axis=1, keepdims=True)
    np.save(INDEX_PATH, arr.astype(np.float16))          # float16 halves the file size (about 7 MB)
    meta = {"model": EMBED_MODEL, "count": len(chunks), "dims": int(arr.shape[1]), "fingerprint": fingerprint(chunks),
            "built": datetime.date.today().isoformat()}
    with open(META_PATH, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)
    print(f"Saved {INDEX_PATH} ({arr.shape[0]:,} x {arr.shape[1]:,}) and {META_PATH}")


if __name__ == "__main__":
    try:
        main()
    except openai.AuthenticationError:
        sys.exit("Stopped: OpenAI did not accept that key. Check it was copied in full, then run the command again.")
