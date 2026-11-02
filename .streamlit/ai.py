"""
ai.py - every call to OpenAI goes through this file.

Models:
  * gpt-4o-mini              - reads, explains, analyses and drafts (the "chat" model)
  * text-embedding-3-large   - turns text into numbers so the regulation library can be searched by meaning

Design rule for the whole app:  AI ANALYSES, CODE CHECKS.
The AI is only ever given (a) facts the app has already worked out and (b) passages from the app's own
regulation library. It never browses the web. Code then checks what comes back - for example, every
citation the AI makes must be one of the passages it was actually given.

The API key comes from the box in the left-hand panel. It is held in this browser session only.
"""

import functools
import hashlib
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import openai
import streamlit as st

MODEL = "gpt-4o-mini"
EMBED_MODEL = "text-embedding-3-large"

CLOSED_WORLD_RULES = (
    "You are an assistant to a U.S./Canadian banking M&A lawyer. Rules you must follow:\n"
    "1. Use ONLY the numbered passages and the APP FACTS provided in this message. Do not use outside "
    "knowledge, and do not mention cases, rules or numbers that are not in them.\n"
    "2. After every sentence that relies on a passage, cite it in square brackets with its ID, e.g. [C41]. "
    "Do not cite the app facts.\n"
    "3. Never do arithmetic and never decide pass/fail yourself - the APP FACTS already contain the computed "
    "numbers and results; repeat them, do not change them.\n"
    "4. If the passages cannot answer the question you were asked, say so once: 'The loaded regulations do not "
    "cover this.' Do not add such remarks about side points - simply leave them out.\n"
    "5. Plain English for a busy senior lawyer. No preamble."
)


# --------------------------------------------------------------------------------------
# The API key (from the box in the left-hand panel) and the OpenAI connection
# --------------------------------------------------------------------------------------
def key():
    return (st.session_state.get("api_key") or "").strip()


def ready():
    """True once a key has been entered (the key box checks that OpenAI accepts it)."""
    return bool(key())


@functools.lru_cache(maxsize=4)
def _client_for(api_key):
    # max_retries: the library waits and retries by itself if OpenAI is busy (rate limits, brief outages).
    return openai.OpenAI(api_key=api_key, max_retries=3, timeout=120)


def client():
    if not key():
        raise RuntimeError("Add your OpenAI API key in the left-hand panel first.")
    return _client_for(key())


def friendly_error(exc):
    """Turn an OpenAI error into one plain sentence for the user."""
    text = str(exc)
    if isinstance(exc, openai.AuthenticationError):
        return "OpenAI did not accept this key - check it was copied in full (it starts with sk-)."
    if isinstance(exc, openai.PermissionDeniedError):
        return f"This key is not allowed to use {MODEL} - check the key's project settings at platform.openai.com."
    if isinstance(exc, openai.RateLimitError):
        if "insufficient_quota" in text or "quota" in text.lower():
            return "This OpenAI account has no credit left - add credit at platform.openai.com, then try again."
        return "OpenAI is busy right now (rate limit) - wait a minute and try again."
    if isinstance(exc, (openai.APIConnectionError, openai.APITimeoutError)):
        return "Could not reach OpenAI - check the internet connection and try again."
    if isinstance(exc, openai.NotFoundError):
        return f"OpenAI says the model is not available to this key ({MODEL} / {EMBED_MODEL})."
    if isinstance(exc, openai.BadRequestError):
        return "OpenAI rejected the request: " + text[:200]
    return text[:300] or exc.__class__.__name__


def check_key():
    """Is the key in the box accepted by OpenAI? Asks OpenAI once per key (a free call). Returns (ok, message)."""
    k = key()
    if not k:
        return False, "No key entered."
    tag = hashlib.sha256(k.encode()).hexdigest()[:16]          # remember the answer without storing the key twice
    done = st.session_state.setdefault("key_checks", {})
    if tag not in done:
        try:
            client().with_options(max_retries=0, timeout=20).models.retrieve(MODEL)   # quick: no retries
            done[tag] = (True, "")
        except (openai.APIConnectionError, openai.APITimeoutError) as exc:
            return False, friendly_error(exc)               # a network blip: do not remember, try again next time
        except Exception as exc:
            done[tag] = (False, friendly_error(exc))
    return done[tag]


# --------------------------------------------------------------------------------------
# The audit trail and the call counter (both shown to the user)
# --------------------------------------------------------------------------------------
def _log(step, purpose, prompt, output, passages=None, seconds=0.0, kind="chat"):
    st.session_state.setdefault("audit", []).append({
        "time": time.strftime("%Y-%m-%d %H:%M:%S"), "step": step, "purpose": purpose,
        "model": MODEL if kind == "chat" else EMBED_MODEL,
        "passages_sent": [p["id"] + " " + p["cite"] for p in (passages or [])],
        "prompt_chars": len(prompt), "output": output, "seconds": round(seconds, 1)})
    counter = "ai_calls" if kind == "chat" else "searches"
    st.session_state[counter] = st.session_state.get(counter, 0) + 1


# --------------------------------------------------------------------------------------
# The two kinds of call: chat (gpt-4o-mini) and embeddings (text-embedding-3-large)
# --------------------------------------------------------------------------------------
LABELS_THE_AI_SOMETIMES_CITES = r"\s?\[(?:APP FACTS|RESULTS|CONTEXT|DEAL BACKGROUND|FACTS|PASSAGES|DEAL FACTS|WORKFLOW FINDINGS|ISSUES LIST)\]"


def chat(system, user, step, purpose, passages=None, max_tokens=900, want_json=False, temperature=0.2):
    """One call to gpt-4o-mini. Returns the reply as text."""
    started = time.time()
    extra = {"response_format": {"type": "json_object"}} if want_json else {}
    resp = client().chat.completions.create(
        model=MODEL, temperature=temperature, max_completion_tokens=max_tokens,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}], **extra)
    text = resp.choices[0].message.content or ""
    if not text.strip():
        text = "The AI returned an empty answer. Press the step again."
    text = re.sub(LABELS_THE_AI_SOMETIMES_CITES, "", text)     # the prompt's own headings are not sources
    _log(step, purpose, system + user, text, passages, time.time() - started)
    return text


def _parse_json(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        return {}


def json_call(system, user, step, purpose, passages=None, max_tokens=1500, need="", retries=1, temperature=0.2):
    """A call that must return JSON containing the key `need`. If the reply is cut off or malformed, ask once more
    with more room."""
    data = {}
    for attempt in range(retries + 1):
        data = _parse_json(chat(system, user, step, purpose + ("" if attempt == 0 else " (retry)"), passages,
                                max_tokens=int(max_tokens * (1 + 0.6 * attempt)), want_json=True, temperature=temperature))
        if not need or data.get(need):
            return data
    return data


def embed(texts, step="Search", purpose="Search the regulations"):
    """Turn a list of texts into vectors with text-embedding-3-large (used to search the library by meaning)."""
    started = time.time()
    resp = client().embeddings.create(model=EMBED_MODEL, input=list(texts))
    _log(step, purpose, " | ".join(texts)[:2000], f"{len(resp.data)} vector(s)", seconds=time.time() - started, kind="embed")
    return [d.embedding for d in resp.data]


# --------------------------------------------------------------------------------------
# Running independent AI calls at the same time (a page with three AI tasks takes as long as one)
# --------------------------------------------------------------------------------------
def parallel(fns, workers=6):
    """Run callables at once and return their results in order. Each thread is attached to this Streamlit
    session, so the calls still use this session's key, count in the panel and land in the audit trail."""
    if len(fns) <= 1:
        return [f() for f in fns]
    from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
    ctx = get_script_run_ctx()

    def attach(fn):
        def run():
            if ctx is not None:
                add_script_run_ctx(threading.current_thread(), ctx)
            return fn()
        return run

    with ThreadPoolExecutor(max_workers=min(workers, len(fns))) as pool:
        futures = [pool.submit(attach(f)) for f in fns]
        return [f.result() for f in futures]


# --------------------------------------------------------------------------------------
# Passages and citations (layer 3 of the closed world: code checks every citation)
# --------------------------------------------------------------------------------------
def passages_block(passages):
    return "\n\n".join(f"[{p['id']}] {p['cite']} - {p['title']} (status: {p['status']})\n{p['text']}" for p in passages)


def check_citations(text, passages):
    """Every passage ID the AI cites - e.g. [C41] or [C41, C63] - must be one we actually sent."""
    sent = {p["id"] for p in passages}
    cited = set()
    for group in re.findall(r"\[([^\]]*C\d+[^\]]*)\]", text or ""):
        cited.update(re.findall(r"C\d+", group))
    return {"cited": sorted(cited), "invalid": sorted(cited - sent), "has_citations": bool(cited)}


def strip_invalid(text, invalid):
    for cid in invalid:
        text = re.sub(rf"\b{cid}\b", "citation removed - not in sources", text)
    return text


def cites_to_law(text, passages):
    """For anything a lawyer will copy out: passage IDs ([C914][C915]) become real citations ((12 CFR 211.23))."""
    by_id = {p["id"]: re.sub(r"\s*\(part \d+\)$", "", p["cite"]) for p in passages}

    def repl(m):
        ids = re.findall(r"C\d+", m.group(0))
        cites = list(dict.fromkeys(by_id[i] for i in ids if i in by_id))
        return f" ({'; '.join(cites)})" if cites else ""
    text = re.sub(r"(?:\s*\[[^\]]*C\d+[^\]]*\])+", repl, text or "")
    text = re.sub(r"(\([^()]*\))(?:\s*\1)+", r"\1", text)          # "(12 CFR 211.23) (12 CFR 211.23)" -> once
    return re.sub(r"\s+([.,;])", r"\1", text)
