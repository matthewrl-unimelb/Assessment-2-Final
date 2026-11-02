"""
ai.py - every call to OpenAI goes through this file.

Models:
  * gpt-4o-mini              - reads, applies, analyses and drafts (the "chat" model)
  * text-embedding-3-large   - turns text into numbers so the regulation library can be searched by meaning

Design rule for the whole app:  AI ANALYSES, CODE CHECKS.
The AI is only ever given (a) facts the app has already worked out, (b) the bank's own filing, and
(c) passages from the app's own regulation library. It never browses the web. Code then checks what
comes back (engine.py holds most of the checks).

"Closed world" is enforced in four layers:
  1. Retrieve first: only library passages are ever sent to the AI (library.py).
  2. Instructions: answer ONLY from those passages, otherwise say so (CLOSED_WORLD_RULES below).
  3. Code check: every [C#] citation must be one of the passages actually sent (check_citations).
  4. Relevance floor: if the library has nothing relevant, the AI is not called at all.

The techniques used (from Lab 2 and beyond), and where:
  * retrieval (RAG) ......................... explain, explain_multi, ask, every legal step
  * looping + reflection .................... ask (question box), build_memo in steps/summary.py
  * self-correction ......................... reread_filing (the AI re-reads what the app could not confirm)
  * chain of thought in JSON ................ read_rules ("reasoning" before the answer)
  * self-consistency (3 votes) .............. read_rules
  * tool use ................................ analyst_next (the AI calls the app's calculator)
  * parallel calls .......................... parallel (several AI calls at once)

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

# OpenAI's list prices (US$ per million tokens) - only used to show an estimate of what a session has cost.
PRICE_IN, PRICE_OUT, PRICE_EMBED = 0.15, 0.60, 0.13

MAX_LOOPS = 2            # the question box: how many times it may search again after a failed check
VOTE_TEMPERATURE = 0.5   # the three independent rule readings vary a little, so the vote means something

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


# ======================================================================================
# THE CONNECTION: the API key (from the box in the left-hand panel) and the OpenAI client
# ======================================================================================
def key():
    """The key typed into the left-hand panel (it lives in this browser session only)."""
    s = st.session_state
    return (s.get("api_key") or s.get("openai_api_key") or s.get("OPENAI_API_KEY") or "").strip()


def ready():
    """True if a key has been entered and OpenAI has not refused it."""
    return key_status() in ("ok", "unchecked")


def key_status():
    """'none' (no key), 'ok' (OpenAI accepted it), 'bad' (OpenAI refused it), 'unchecked' (not checked yet)."""
    k = key()
    if not k:
        return "none"
    done = st.session_state.get("key_checks", {}).get(_tag(k))
    return "unchecked" if done is None else ("ok" if done[0] else "bad")


def _tag(k):
    return hashlib.sha256(k.encode()).hexdigest()[:16]      # remember a key's check without storing the key twice


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
    done = st.session_state.setdefault("key_checks", {})
    tag = _tag(k)
    if tag not in done:
        try:
            client().with_options(max_retries=0, timeout=20).models.retrieve(MODEL)   # quick: no retries
            done[tag] = (True, "")
        except (openai.APIConnectionError, openai.APITimeoutError) as exc:
            return False, friendly_error(exc)               # a network blip: do not remember, try again next time
        except Exception as exc:
            done[tag] = (False, friendly_error(exc))
    return done[tag]


# ======================================================================================
# THE AUDIT TRAIL AND THE CALL COUNTER (both shown to the user)
# ======================================================================================
_LOCK = threading.Lock()     # several AI calls can finish at the same moment (see parallel)


def _log(step, purpose, prompt, output, passages=None, seconds=0.0, kind="chat", tokens_in=0, tokens_out=0):
    s = st.session_state
    with _LOCK:
        s.setdefault("audit", []).append({
            "time": time.strftime("%Y-%m-%d %H:%M:%S"), "step": step, "purpose": purpose,
            "model": MODEL if kind == "chat" else EMBED_MODEL,
            "passages_sent": [p["id"] + " " + p["cite"] for p in (passages or [])],
            "prompt_chars": len(prompt), "tokens_in": tokens_in, "tokens_out": tokens_out,
            "output": output, "seconds": round(seconds, 1)})
        counter = "ai_calls" if kind == "chat" else "searches"
        s[counter] = s.get(counter, 0) + 1
        price = (tokens_in * PRICE_IN + tokens_out * PRICE_OUT) if kind == "chat" else tokens_in * PRICE_EMBED
        s["cost_usd"] = s.get("cost_usd", 0.0) + price / 1e6


# ======================================================================================
# THE TWO KINDS OF CALL: chat (gpt-4o-mini) and embeddings (text-embedding-3-large)
# ======================================================================================
LABELS_THE_AI_SOMETIMES_CITES = (r"\s?\[(?:APP FACTS|RESULTS|CONTEXT|DEAL BACKGROUND|FACTS|PASSAGES|DEAL FACTS|"
                                 r"WORKFLOW FINDINGS|ISSUES LIST)\]")


def chat(system, user, step, purpose, passages=None, max_tokens=900, want_json=False, temperature=0.2):
    """One call to gpt-4o-mini. Returns the reply as text."""
    started = time.time()
    extra = {}
    if want_json:
        extra["response_format"] = {"type": "json_object"}
        if "json" not in (system + user).lower():        # OpenAI's JSON mode requires the word in the prompt
            system += "\nReturn only valid JSON."
    resp = client().chat.completions.create(
        model=MODEL, temperature=temperature, max_completion_tokens=max_tokens,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}], **extra)
    text = resp.choices[0].message.content or ""
    if not text.strip():
        text = "The AI returned an empty answer. Press the step again."
    text = re.sub(LABELS_THE_AI_SOMETIMES_CITES, "", text)     # the prompt's own headings are not sources
    usage = getattr(resp, "usage", None)
    _log(step, purpose, system + user, text, passages, time.time() - started,
         tokens_in=getattr(usage, "prompt_tokens", 0) or 0, tokens_out=getattr(usage, "completion_tokens", 0) or 0)
    return text


def _parse_json(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        return {}


def json_call(system, user, step, purpose, passages=None, max_tokens=1500, need="", retries=1, temperature=0.2):
    """A call that must return JSON containing the key `need`. If the reply is cut off or malformed, ask once
    more with more room."""
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
    usage = getattr(resp, "usage", None)
    _log(step, purpose, " | ".join(texts)[:2000], f"{len(resp.data)} vector(s)", seconds=time.time() - started,
         kind="embed", tokens_in=getattr(usage, "prompt_tokens", 0) or 0)
    return [d.embedding for d in resp.data]


# ======================================================================================
# RUNNING INDEPENDENT AI CALLS AT THE SAME TIME (a page with three AI tasks takes as long as one)
# ======================================================================================
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


# ======================================================================================
# PASSAGES AND CITATIONS (layer 3 of the closed world: code checks every citation)
# ======================================================================================
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


def _checked(text, passages):
    """Check the citations in an answer and remove any the AI was not given."""
    check = check_citations(text, passages)
    if check["invalid"]:
        text = strip_invalid(text, check["invalid"])
    return {"text": text, "passages": passages, "check": check}


NOT_IN_LIBRARY = "The loaded regulations do not contain material relevant to this step."


# ======================================================================================
# EVERY PAGE (from Stage 2) - RAG: a grounded explanation, and the question box (retrieve -> answer -> reflect -> loop)
# ======================================================================================
def explain(step, task, facts, query, lib, k=6):
    """Search the library, then one AI call that may use only what was found. Code checks the citations."""
    passages = lib.search(query, k=k)
    if not lib.relevant(passages):
        return {"text": NOT_IN_LIBRARY, "passages": [], "check": None}
    user = f"TASK: {task}\n\nAPP FACTS (computed by the app - do not change):\n{facts}\n\nPASSAGES:\n{passages_block(passages)}"
    return _checked(chat(CLOSED_WORLD_RULES, user, step, task[:80], passages), passages)


def explain_multi(step, task, facts, queries, lib, per_query=2):
    """Like explain(), but gathers passages topic by topic, so a guide that covers several terms gets the defining
    text of each one. Each item in `queries` is either a search (a string) or a (citation, phrase) pair that fetches
    the exact section that defines the term."""
    seen, passages = set(), []
    for q in queries:
        found = lib.section(q[0], q[1], limit=1) if isinstance(q, tuple) else lib.search(q, k=per_query)
        for p in found:
            if p["id"] not in seen and lib.relevant([p]):
                seen.add(p["id"])
                passages.append(p)
    if not passages:
        return {"text": NOT_IN_LIBRARY, "passages": [], "check": None}
    user = f"TASK: {task}\n\nAPP FACTS (computed by the app - do not change):\n{facts}\n\nPASSAGES:\n{passages_block(passages)}"
    return _checked(chat(CLOSED_WORLD_RULES, user, step, task[:80], passages, max_tokens=1400), passages)


def reflect(step, answer, passages, question):
    """Reflection: a second AI call checks each sentence of an answer against the passages it cites."""
    user = (
        "You are a strict checker. Compare the ANSWER with the PASSAGES it cites.\n"
        "Return JSON only: {\"supported\": true/false, \"answered\": true/false, \"unsupported\": [\"sentence\", ...], "
        "\"better_search\": \"words likely to appear in the regulation text that would answer the question, "
        "e.g. section topics and defined terms\"}.\n"
        "supported = every statement is backed by its cited passage (saying the regulations do not cover something "
        "counts as supported). answered = the passages actually answered the question asked.\n\n"
        f"QUESTION: {question}\n\nANSWER:\n{answer}\n\nPASSAGES:\n{passages_block(passages)}")
    verdict = _parse_json(chat("Return only valid JSON.", user, step, "Reflection check", passages, max_tokens=800,
                               want_json=True, temperature=0))
    verdict["supported"] = verdict.get("supported") is True
    verdict["answered"] = verdict.get("answered", True) is not False
    verdict.setdefault("unsupported", [])
    verdict.setdefault("better_search", "")
    return verdict


def ask(step, question, facts, lib):
    """The question box: search -> answer -> a second AI checks the answer -> if it fails, search again and retry."""
    query, trail, last = question, [], None
    for attempt in range(1, MAX_LOOPS + 1):
        passages = lib.search(query, k=6)
        how = "by meaning" if passages and passages[0].get("method") == "meaning" else "by keywords"
        if not lib.relevant(passages):
            trail.append(f"Attempt {attempt}: searched {how} for '{query}' - nothing relevant, so the AI was not called.")
            if last:
                break
            return {"text": "I couldn't find that in the regulations loaded into this app.", "passages": [],
                    "trail": trail, "verified": True}
        user = (f"QUESTION: {question}\n\nAPP FACTS about the deal on screen (computed by the app):\n{facts}\n\n"
                f"PASSAGES:\n{passages_block(passages)}")
        answer = chat(CLOSED_WORLD_RULES, user, step, f"Q&A attempt {attempt}", passages)
        cites = check_citations(answer, passages)
        if cites["invalid"]:
            answer = strip_invalid(answer, cites["invalid"])
        verdict = reflect(step, answer, passages, question)
        trail.append(f"Attempt {attempt}: searched {how} for '{query}', cited {', '.join(cites['cited']) or 'nothing'}; "
                     f"the checker says {'SUPPORTED' if verdict['supported'] else 'NOT SUPPORTED'}"
                     f"{'' if verdict['answered'] else ', but the passages did NOT answer the question'}.")
        if verdict["supported"] and not cites["invalid"]:
            if verdict["answered"] or attempt == MAX_LOOPS:
                return {"text": answer, "passages": passages, "trail": trail, "verified": True}
        last = {"text": answer, "passages": passages, "trail": trail,
                "verified": verdict["supported"] and not cites["invalid"], "unsupported": verdict.get("unsupported", [])}
        query = verdict["better_search"] or question + " definition requirement"     # LOOP: search again
    if last and not last["verified"]:
        last["text"] += ("\n\n_⚠️ The checker could not confirm every sentence of this answer against the regulations. "
                         "Treat it as a lead, not a conclusion._")
    return last


# ======================================================================================
# STAGE 1 - GETTING STARTED: the AI reads each bank's FR Y-9C (code checks every figure), re-reads what did not
# match (self-correction), then reviews the checked figures as an analyst would.
# ======================================================================================
def read_filing(step, bank_name, filing_text):
    from engine import READ_TARGETS
    want = "\n".join(f"- {k}: {label}" for k, (label, _codes) in READ_TARGETS.items())
    user = (
        "You are reading a U.S. bank holding company's FR Y-9C regulatory filing, laid out line by line below. Find each "
        "figure listed under WANTED by its meaning. Copy each value EXACTLY as filed (thousands of dollars; percentages as "
        "shown) - never calculate, round or convert. For each figure give the schedule and item where you found it "
        "(e.g. 'HC item 12'). If a figure is not in the filing, use null. For deposit_lines give a LIST of every deposit "
        "line's value - do not add them up.\n"
        "Return JSON only: {\"figures\": {\"total_assets\": {\"value\": 123, \"line\": \"HC item 12\"}, ...}}\n\n"
        f"WANTED:\n{want}\n\n{filing_text}")
    raw = json_call("Return only valid JSON.", user, step, f"Read the filing: {bank_name}", max_tokens=2500, need="figures",
                    temperature=0)
    figs = raw.get("figures") if isinstance(raw.get("figures"), dict) else raw
    return figs if isinstance(figs, dict) else {}


def reread_filing(step, bank_name, filing_text, misses):
    """Self-correction loop: the app tells the AI which of its figures did not match the filing (without giving the
    answer); the AI reads those lines again."""
    from engine import READ_TARGETS
    wanted = "\n".join(f"- {k}: {READ_TARGETS[k][0]} (you gave {v!r}; that does not match the filing)" for k, v in misses.items())
    user = (
        "Some figures you read from this FR Y-9C filing did not match when the app checked them. Read the filing again, "
        "carefully, and find ONLY these figures. Copy each value exactly as filed - never calculate. Give the schedule and "
        "item. For deposit_lines give a LIST of every deposit line's value.\n"
        "Return JSON only: {\"figures\": {\"key\": {\"value\": 123, \"line\": \"HC item 12\"}}}\n\n"
        f"FIGURES TO RE-READ:\n{wanted}\n\n{filing_text}")
    raw = json_call("Return only valid JSON.", user, step, f"Re-read the filing: {bank_name}", max_tokens=1200, need="figures",
                    temperature=0)
    figs = raw.get("figures") if isinstance(raw.get("figures"), dict) else {}
    return {k: v for k, v in figs.items() if k in misses}


def review_bank(step, bank_name, figures_text, checks_text):
    user = (
        "Below are figures from a bank holding company's FR Y-9C filing, read exactly by the app, with some proportions the app "
        "worked out, and the app's checks of the AI's reading of the filing. As an experienced bank analyst, in short bullet "
        "points: (1) the bank's size, funding and capital position in plain English; (2) anything a deal lawyer should "
        "look at more closely - for example a large unrealised securities loss (AOCI) relative to CET1, which matters if the "
        "bank loses its AOCI opt-out; heavy goodwill; thin capital above the buffer; a reliance on wholesale funding; (3) any "
        "balance-sheet lines that may be holdings a bank holding company cannot keep indefinitely - real estate ventures, "
        "investments in unconsolidated companies, equity securities, other real estate owned - with their exact amounts, if "
        "material; (4) any figure the checks could not confirm. At most 6 bullets. Use only the numbers given, exactly as "
        "written. Do not cite law. No preamble.\n\n"
        f"BANK: {bank_name}\nFIGURES:\n{figures_text}\n\nCHECKS:\n{checks_text}")
    return chat("You are a careful bank-regulatory analyst.", user, step, f"Analyst review: {bank_name}", max_tokens=700)


# The Canadian parent's Pillar 3 report: code finds the right pages, the AI reads them, code checks the figures.
PARENT_FIELDS = {
    "bank_name": "Name of the bank",
    "period": "Quarter-end date of the most recent column",
    "total_assets": "Total consolidated assets (balance sheet / LR1 'total consolidated assets as per published financial statements')",
    "cet1": "Common Equity Tier 1 (CET1) capital",
    "tier1": "Tier 1 capital",
    "total_capital": "Total capital",
    "rwa": "Total risk-weighted assets (RWA)",
    "leverage_exposure": "Total leverage ratio exposure measure",
    "cet1_ratio": "CET1 ratio (%)",
    "leverage_ratio": "Leverage ratio (%)",
}
AMOUNT_FIELDS = ("total_assets", "cet1", "tier1", "total_capital", "rwa", "leverage_exposure")


def find_capital_pages(pdf_reader):
    """CODE (not AI) finds the KM1 key-metrics and LR1 leverage pages, skipping the table of contents, so the AI
    reads 2-4 pages instead of 100."""
    keep = []
    for i, page in enumerate(pdf_reader.pages):
        t = page.extract_text() or ""
        head = t[:400].upper()
        if "TABLE OF CONTENTS" in head or "INDEX" in head:
            continue
        is_km1 = re.search(r"KM1", t) and re.search(r"Common Equity Tier 1", t, re.I) and re.search(r"leverage", t, re.I)
        is_lr1 = re.search(r"LR1", t) and re.search(r"[Tt]otal consolidated assets", t)
        if is_km1 or is_lr1:
            keep.append((i, t))
        if len(keep) >= 4:
            break
    if not keep:  # fall back: the pages that mention the key words most
        scored = sorted(((sum(t.lower().count(w) for w in ("cet1", "risk-weighted", "leverage")), i, t)
                         for i, t in ((i, p.extract_text() or "") for i, p in enumerate(pdf_reader.pages))), reverse=True)[:4]
        keep = sorted((i, t) for _, i, t in scored)
    return "\n\n".join(f"--- page {i + 1} ---\n{t}" for i, t in keep), [i + 1 for i, _ in keep]


def extract_parent_figures(step, pages_text):
    """The AI reads the KM1 'key metrics' and LR1 tables. Code then checks the result (verify_parent)."""
    user = (
        "Below are pages from a Canadian bank's Pillar 3 / supplementary regulatory capital disclosure. "
        "Tables have several quarter columns: use ONLY the FIRST (most recent) column. "
        "Amounts are in millions of Canadian dollars - copy them exactly as numbers (no commas). "
        "Ratios as percentages (e.g. 13.5). If a figure is not shown, use null. Never calculate or guess. "
        "For each figure give a short quote of the row you used.\n"
        "Return JSON only, in this shape: {"
        + ", ".join(f'"{k}": {{"value": ..., "found_as": "..."}}' for k in PARENT_FIELDS)
        + "}\n\nFIGURES WANTED:\n" + "\n".join(f"- {k}: {v}" for k, v in PARENT_FIELDS.items())
        + f"\n\nPAGES:\n{pages_text[:40000]}")
    raw = json_call("Return only valid JSON.", user, step, "Read the parent's Pillar 3 report", max_tokens=1500, temperature=0)
    out = {}
    for k in PARENT_FIELDS:
        item = raw.get(k) if isinstance(raw.get(k), dict) else {"value": raw.get(k), "found_as": ""}
        v = item.get("value")
        if k in AMOUNT_FIELDS or k in ("cet1_ratio", "leverage_ratio"):
            try:
                v = float(str(v).replace(",", "").replace("%", "")) if v not in (None, "", "null") else None
            except ValueError:
                v = None
        out[k] = {"value": v, "found_as": str(item.get("found_as") or "")}
    return out


def verify_parent(fig):
    """CODE check of the AI's reading: do the amounts reproduce the bank's own reported ratios?"""
    v = {k: fig.get(k, {}).get("value") for k in fig}
    checks = []
    for label, num, den, reported in (("CET1 ratio", "cet1", "rwa", "cet1_ratio"),
                                      ("Leverage ratio", "tier1", "leverage_exposure", "leverage_ratio")):
        if v.get(num) and v.get(den) and v.get(reported):
            calc = 100 * v[num] / v[den]
            checks.append({"check": label, "ok": abs(calc - v[reported]) < 0.15,
                           "result": f"{calc:.2f}% recomputed vs {v[reported]:.2f}% reported"})
        else:
            checks.append({"check": label, "ok": None, "result": "a figure is missing"})
    if v.get("tier1") and v.get("cet1"):
        checks.append({"check": "Tier 1 ≥ CET1", "ok": v["tier1"] >= v["cet1"],
                       "result": "consistent" if v["tier1"] >= v["cet1"] else "inconsistent"})
    return checks


# ======================================================================================
# STAGE 2 - AT A GLANCE: the AI applies the rules from the regulation text itself, in two rounds, each run as three
# independent readings at once (self-consistency). Code compares the majority answer with the built-in rulebook.
# ======================================================================================
RULE_QUERIES_CATEGORY = [("12 CFR 252.5", None, 3), ("12 CFR 252.2", "Category IV", 1),
                         ("12 CFR 217.2", "Category III Board-regulated institution means", 1),
                         ("12 CFR 217.2", "Advanced approaches Board-regulated institution means", 1),
                         ("12 CFR 217.100", "Category II banking organization", 1)]
RULE_QUERIES_REQUIREMENTS = [("12 CFR 217.10", "supplementary leverage ratio of 3 percent", 1),
                             ("12 CFR 217.11", "countercyclical capital buffer amount", 2),
                             ("12 CFR 217.22", "AOCI opt-out election", 2),
                             ("12 CFR 225.8", "$100 billion asset threshold", 1),
                             ("12 CFR 225.8", "Category IV", 2),
                             ("12 CFR 252.44", None, 2),
                             ("12 CFR 249.1", None, 1), ("12 CFR 249.30", None, 2)]
RULE_VOTES = 3   # independent readings; the app takes the majority on each point


def _vote(values):
    """The majority value and how many readings gave it."""
    vals = [v for v in values if v not in (None, "")]
    if not vals:
        return None, 0
    best = max(sorted(set(vals)), key=vals.count)
    return best, vals.count(best)


def _norm_cat(c):
    c = str(c or "").replace("Category", "").replace("category", "").strip().upper()
    c = {"1": "I", "2": "II", "3": "III", "4": "IV"}.get(c, c)
    return "None" if c in ("NONE", "NO CATEGORY", "N/A", "") or "BELOW" in c else c


def _norm_bool(v):
    v = str(v).strip().lower()
    return {"yes": "true", "no": "false"}.get(v, v)


def _norm_state(v):
    return re.sub(r"\s+", " ", str(v or "").strip().strip(".").lower())


def read_rules(step, facts, requirement_names, lib, votes=RULE_VOTES, questions=None):
    """Returns {"category", "advanced_approaches", "other_triggers", "requirements", "passages", "votes", "citations"}."""
    p_cat = lib.fetch(RULE_QUERIES_CATEGORY)
    u1 = (
        "Apply the regulation PASSAGES to the bank in APP FACTS. Work out which size category (I, II, III, IV, or None if "
        "below $100 billion) the bank is in BEFORE the deal and AFTER it, using the asset size given. Work it out in "
        "'reasoning' FIRST, testing each category from the top (I, then II, III, IV) against the asset figure for each date, "
        "and only then fill in 'before' and 'after' so they match your reasoning. Next, in 'advanced_approaches', decide for "
        "each date whether the bank is an 'advanced approaches Board-regulated institution', testing the definition in 12 CFR "
        "217.2 and the list in 12 CFR 217.100(b)(1)(i) clause by clause against APP FACTS and your category answer. Then list "
        "the OTHER ways the passages say a bank of this size can be placed in a HIGHER category (e.g. cross-jurisdictional "
        "activity, nonbank assets, weighted short-term wholesale funding, off-balance-sheet exposure) - the app does not have "
        "those figures, so state the threshold and what the lawyer must check. Cite passages like [C12].\n"
        "Return JSON only: {\"category\": {\"reasoning\": \"step by step, with citations\", \"before\": \"II|III|IV|None\", "
        "\"after\": \"II|III|IV|None\", \"why\": \"two sentences for the lawyer, with citations\"}, "
        "\"advanced_approaches\": {\"reasoning\": \"clause by clause, with citations\", \"before\": true, \"after\": true}, "
        "\"other_triggers\": [{\"trigger\": \"...\", \"threshold\": \"...\", \"effect\": \"which category it would mean\", "
        "\"check\": \"what to ask the client\", \"cite\": \"[C#]\"}]}\n\n"
        f"APP FACTS:\n{facts}\n\nPASSAGES:\n{passages_block(p_cat)}")
    runs1 = parallel([lambda i=i: json_call(CLOSED_WORLD_RULES + "\nReturn only valid JSON.", u1, step,
                                            f"Rule reading: size category (reading {i + 1} of {votes})", p_cat,
                                            max_tokens=2600, need="category", temperature=VOTE_TEMPERATURE)
                      for i in range(votes)])
    cats = [r.get("category") if isinstance(r.get("category"), dict) else {} for r in runs1]
    before, nb = _vote([_norm_cat(c.get("before")) for c in cats])
    after, na = _vote([_norm_cat(c.get("after")) for c in cats])
    pick = next((i for i, c in enumerate(cats) if _norm_cat(c.get("before")) == before and _norm_cat(c.get("after")) == after), 0)
    c = dict(cats[pick], before=before, after=after)
    trig = [t for t in (runs1[pick].get("other_triggers") or []) if isinstance(t, dict)][:6]
    aas = [r.get("advanced_approaches") if isinstance(r.get("advanced_approaches"), dict) else {} for r in runs1]
    aa_b, _ = _vote([_norm_bool(x.get("before")) for x in aas if x.get("before") is not None])
    aa_a, _ = _vote([_norm_bool(x.get("after")) for x in aas if x.get("after") is not None])
    aa = next((x for x in aas if _norm_bool(x.get("after")) == aa_a), {})
    yn = lambda v: "YES" if v == "true" else ("NO" if v == "false" else "UNCLEAR")

    p_req = lib.fetch(RULE_QUERIES_REQUIREMENTS)
    questions = questions or requirement_names
    names = "\n".join(f"{i}. {q}" for i, q in enumerate(questions, 1))
    u2 = (
        "SETTLED FACTS (from the first round of readings):\n"
        f"- BEFORE the deal: Category {before}; advanced approaches Board-regulated institution: {yn(aa_b)}.\n"
        f"- AFTER the deal: Category {after}; advanced approaches Board-regulated institution: {yn(aa_a)}.\n"
        "A rule that covers 'X or Y' covers the bank on any date where EITHER X or Y is true for it.\n"
        "Answer each numbered QUESTION for the bank, before and after the deal, using ONLY the PASSAGES and those "
        "settled facts. Work like a lawyer, in this order for each question: (1) 'covers' - quote the words in the passage "
        "that say WHO the rule applies to; (2) 'test' - for each date, restate the bank's category and advanced-approaches "
        "status from SETTLED FACTS and check them against those words; (3) only then the answers. Use exactly one of: "
        "\"applies\", \"does not apply\", \"conditional\" (only if another test is met), \"optional\" (the bank may elect) - "
        "never any other words in those fields.\n"
        "Return JSON only: {\"requirements\": [{\"n\": 1, \"covers\": \"quote [C#]\", \"test\": \"...\", "
        "\"before\": \"...\", \"after\": \"...\", \"why\": \"one sentence for the lawyer, with a citation like [C12]\"}]} "
        "(one entry per numbered question)\n\n"
        f"QUESTIONS:\n{names}\n\nAPP FACTS:\n{facts}\n\nPASSAGES:\n{passages_block(p_req)}")
    runs2 = parallel([lambda i=i: json_call(CLOSED_WORLD_RULES + "\nReturn only valid JSON.", u2, step,
                                            f"Rule reading: what applies (reading {i + 1} of {votes})", p_req,
                                            max_tokens=3500, need="requirements", temperature=VOTE_TEMPERATURE)
                      for i in range(votes)])
    by_run = []
    for r in runs2:
        m = {}
        for x in r.get("requirements", []) if isinstance(r.get("requirements"), list) else []:
            try:
                m[int(x.get("n"))] = x
            except (TypeError, ValueError, AttributeError):
                pass
        by_run.append(m)
    reqs, agree_counts = [], {}
    for n, name in enumerate(requirement_names, 1):
        best, k = _vote([_norm_state(m.get(n, {}).get("after")) for m in by_run])
        src = next((m[n] for m in by_run if n in m and _norm_state(m[n].get("after")) == best), {})
        b_best, _ = _vote([_norm_state(m.get(n, {}).get("before")) for m in by_run])
        reqs.append({"n": n, "name": name, "after": best or "", "before": b_best or "", "why": str(src.get("why", "")),
                     "votes": f"{k} of {len(by_run)}"})
        agree_counts[name] = k
    passages = p_cat + p_req
    out = {"category": c, "advanced_approaches": aa, "other_triggers": trig, "requirements": reqs, "passages": passages,
           "votes": {"n": votes, "before": nb, "after": na, "requirements": agree_counts,
                     "unanimous": sum(1 for v in [nb, na] if v == votes) + sum(1 for v in agree_counts.values() if v == len(by_run)),
                     "points": 2 + len(requirement_names)}}
    out["citations"] = check_citations(json.dumps(out["category"]) + json.dumps(trig) + json.dumps(reqs), passages)
    if out["citations"]["invalid"]:                    # remove citations to passages the AI was not given
        bad = out["citations"]["invalid"]
        out["category"]["why"] = strip_invalid(str(c.get("why", "")), bad)
        for r in reqs:
            r["why"] = strip_invalid(r["why"], bad)
        for t in trig:
            t["cite"] = strip_invalid(str(t.get("cite", "")), bad)
    return out


# ======================================================================================
# STAGE 5 - CANADIAN BUYER: the AI reads any holdings register into rows, then gives each holding a reasoned verdict
# under Reg K and Regulation Y. Code checks each verdict (engine.disposal_checks) and works out the timing.
# ======================================================================================
ACTIVITIES = ["Banking", "Holding company", "Lending / finance", "Securities & investment", "Insurance", "Funds & trusts",
              "Real estate", "Other financial", "Non-financial (commercial)", "Not classified"]


def find_subsidiary_pages(pdf_reader, max_pages=6):
    """CODE picks the pages that list subsidiaries, so the AI reads a few pages, not a whole annual report."""
    scored = []
    for i, page in enumerate(pdf_reader.pages):
        t = page.extract_text() or ""
        low = t.lower()
        score = low.count("subsidiar") * 3 + low.count("limited") + low.count("inc.") + low.count("llc")
        if "subsidiar" in low and score >= 8:
            scored.append((score, i, t))
    keep = sorted(sorted(scored, reverse=True)[:max_pages], key=lambda x: x[1])
    return "\n\n".join(f"--- page {i + 1} ---\n{t}" for _, i, t in keep), [i + 1 for _, i, _ in keep]


def extract_register(step, text, parent_name):
    user = (
        f"Below is a holdings register for {parent_name} (a spreadsheet, list or annual-report extract). For EACH company: "
        "name; country (where incorporated or mainly operating); business (a short plain description, as given); activity, "
        f"chosen ONLY from {ACTIVITIES}; ownership_pct (the parent's voting stake as a number, null if not given); "
        "us_activity (what it does in the United States, as given, or \"\"); us_business = true if it does any business in the "
        "United States or a U.S. territory. Copy facts as given - do not invent. Return JSON only: "
        '{"holdings": [{"name": "...", "country": "...", "business": "...", "activity": "...", "ownership_pct": 100, '
        '"us_activity": "", "us_business": false}]}'
        f"\n\nREGISTER:\n{text[:40000]}")
    raw = json_call("Return only valid JSON.", user, step, "Read the holdings register", max_tokens=5000, need="holdings",
                    temperature=0)
    out, seen = [], set()
    for h in raw.get("holdings", []) if isinstance(raw.get("holdings"), list) else []:
        if isinstance(h, dict) and str(h.get("name") or "").strip():
            name = str(h["name"]).strip()
            if name.lower() in seen:
                continue
            seen.add(name.lower())
            pct = h.get("ownership_pct")
            try:
                pct = float(str(pct).replace("%", "")) if pct not in (None, "", "null") else None
            except ValueError:
                pct = None
            us = h.get("us_business")
            out.append({"name": name, "country": str(h.get("country") or "Unknown"),
                        "business": str(h.get("business") or ""), "ownership_pct": pct,
                        "activity": h.get("activity") if h.get("activity") in ACTIVITIES else "Not classified",
                        "us_activity": str(h.get("us_activity") or ""),
                        "us_business": us is True or str(us).strip().lower() in ("true", "yes")})
    return out


DISPOSAL_QUERIES = [("12 CFR 211.23", None, 5), ("12 CFR 225.86", None, 4), ("12 CFR 225.28", "closely related to banking", 2)]


def disposal_passages(holdings, lib):
    passages = lib.fetch(DISPOSAL_QUERIES)
    words = " ".join(sorted({h.get("business", "") + " " + h.get("activity", "") for h in holdings}))[:400]
    for p in lib.search("closely related to banking permissible activities " + words, k=4):
        if p["id"] not in {x["id"] for x in passages} and p["cite"].startswith(("12 CFR 225.28", "12 CFR 225.86", "12 CFR 211")):
            passages.append(p)
    return passages


def _norm_verdict(v):
    v = re.sub(r"[\s\-]+", "_", str(v or "").strip().lower())
    return {"keep_with_conditions": "keep_conditions", "keep_conditional": "keep_conditions", "fed_approval": "approval",
            "needs_approval": "approval", "must_sell": "sell", "sell_or_restructure": "sell"}.get(v, v)


def analyse_holdings(step, holdings, context, passages, batch=8):
    """One AI call per batch of holdings, all run at the same time. Returns {name: verdict dict}."""
    from engine import VERDICTS

    def one(chunk):
        listing = "\n".join(f"{i + 1}. {h['name']} | {h.get('country')} | {h.get('business') or h.get('activity')} | owned "
                            f"{'?' if h.get('ownership_pct') is None else str(round(h['ownership_pct'])) + '%'} | U.S. activity: "
                            f"{h.get('us_activity') or ('yes' if h.get('us_business') else 'none')}" for i, h in enumerate(chunk))
        user = (
            "You are a U.S. bank regulatory lawyer. A Canadian bank is buying a U.S. bank. For EACH holding below, decide what "
            "U.S. law requires of the Canadian parent, using ONLY the PASSAGES: Regulation K's exemptions for qualifying foreign "
            "banking organizations (12 CFR 211.23: the qualifying tests, what a qualifying bank may own outside the U.S., the "
            "limits on foreign companies that also do business in the U.S., loss of eligibility) and Regulation Y's lists of "
            "activities a U.S. bank holding company may do (closely related to banking; financial in nature). Treat U.S. "
            "territories as the United States: a company there is a U.S. company, judged by what a U.S. bank holding company "
            "may own. Use the app's Reg K result in CONTEXT as given - do not redo it.\n"
            "verdict must be one of these keys, used strictly as defined:\n"
            "- \"keep\": the passages allow it whatever happens to the parent's Reg K status (e.g. banking outside the U.S., or an "
            "activity a U.S. bank holding company may itself do). A permission given to a 'qualifying foreign banking "
            "organization' (e.g. 'may engage in activities of any kind outside the United States') DEPENDS on Reg K status, so a "
            "holding allowed only by such a permission is \"at_risk\", never \"keep\".\n"
            "- \"keep_conditions\": allowed only if a condition holds - name it (e.g. more than half of the company's assets and "
            "revenue outside the U.S.).\n"
            "- \"at_risk\": allowed only while the parent keeps Reg K status.\n"
            "- \"approval\": allowed only with the Fed's approval or after notice to the Fed.\n"
            "- \"sell\": ONLY if no provision in the PASSAGES lets the parent keep it even while it keeps Reg K status. Before "
            "choosing \"sell\", test the routes the passages give - the Reg K exemptions and their conditions, the timing rule on "
            "loss of eligibility (which catches activities started after the first failing year), a specific determination of "
            "eligibility, an exemption the Board may grant case by case, holdings in a fiduciary capacity - and say in the reason "
            "why each relevant route fails. If any route might work, use \"at_risk\", \"keep_conditions\" or \"approval\" instead.\n"
            "Return JSON only: {\"verdicts\": [{\"n\": 1, \"verdict\": \"...\", \"reason\": \"one or two sentences with a "
            "citation like [C12]\", \"action\": \"the next step for the lawyer, one sentence\"}]}\n\n"
            f"CONTEXT:\n{context}\n\nHOLDINGS:\n{listing}\n\nPASSAGES:\n{passages_block(passages)}")
        raw = json_call(CLOSED_WORLD_RULES + "\nReturn only valid JSON.", user, step,
                        f"Disposal review ({len(chunk)} holdings)", passages, max_tokens=3000, need="verdicts")
        out = {}
        for v in raw.get("verdicts", []) if isinstance(raw.get("verdicts"), list) else []:
            try:
                h = chunk[int(v.get("n")) - 1]
            except (TypeError, ValueError, IndexError, AttributeError):
                continue
            text = str(v.get("reason", ""))
            chk = check_citations(text, passages)
            if chk["invalid"]:
                text = strip_invalid(text, chk["invalid"])
            verdict = _norm_verdict(v.get("verdict"))
            out[h["name"]] = {"verdict": verdict if verdict in VERDICTS else None,
                              "reason": text, "action": str(v.get("action") or ""), "cited": chk["cited"]}
        return out

    chunks = [holdings[i:i + batch] for i in range(0, len(holdings), batch)]
    merged = {}
    for part in parallel([lambda c=c: one(c) for c in chunks]):
        merged.update(part)
    return merged


# ======================================================================================
# STAGE 6 - THE AI ANALYST (tool use): the AI decides what to investigate and calls the app's calculator; it never
# does the arithmetic itself. Code runs each tool, feeds the result back, and checks every number in the write-up.
# ======================================================================================
ANALYST_MAX_STEPS = 6
ANALYST_MIN_STEPS = 3


def analyst_next(step, facts, tools_doc, history, focus, n):
    hist = "\n\n".join(f"Call {i + 1}: {h['tool']} {json.dumps(h['args'])} - because: {h['why']}\nRESULT: {json.dumps(h['result'])}"
                       for i, h in enumerate(history)) or "(none yet)"
    may_finish = n >= ANALYST_MIN_STEPS
    user = (
        "You are a senior bank-regulatory analyst investigating a proposed merger for a deal partner. You cannot calculate: "
        "you call the app's calculator TOOLS and read their results. Decide the single most useful NEXT call. Good analysts "
        "check how close the deal is to each line, what could tip it over (growth, losses, more debt), when it bites (the "
        "four-quarter average), and capital resilience - and for a Canadian buyer, Reg K. Do not repeat a call with the same "
        "arguments. Use scenario arguments that answer a real question (e.g. a 2% CET1 loss: capital_loss_bn sized from the "
        "facts; or the target growing 10%)."
        + (" You may finish now if you have enough." if may_finish else f" You must make at least {ANALYST_MIN_STEPS - n} more call(s).")
        + "\nReturn JSON only: {\"why\": \"one sentence: the question this call answers\", \"tool\": \"tool name\", \"args\": {}}"
        + (" or {\"done\": true}" if may_finish else "")
        + f"\n\nTOOLS:\n{tools_doc}\n\nDEAL FACTS:\n{facts}\n\nPARTNER'S FOCUS: {focus or 'a general investigation'}\n\nCALLS SO FAR:\n{hist}")
    return json_call("Return only valid JSON.", user, step, f"Analyst: choose call {n + 1}", max_tokens=500)


def analyst_report(step, facts, history, focus):
    hist = "\n\n".join(f"Call {i + 1}: {h['tool']} {json.dumps(h['args'])} - {h['why']}\nRESULT: {json.dumps(h['result'])}"
                       for i, h in enumerate(history))
    user = (
        "Write the findings of your investigation for the deal partner, using ONLY the numbers in the RESULTS and DEAL FACTS, "
        "copied exactly as written (never compute a new number). Format in markdown:\n"
        "**Key findings** - 4 to 6 bullets, most important first; each one sentence with the figure that proves it.\n"
        "**What could change the picture** - 2 or 3 bullets.\n**Questions for the client** - 2 or 3 bullets.\n"
        "Do not put quotation marks around figures. Where a RESULT has a 'summary' line, rely on it. "
        "No legal citations, no preamble, under 300 words.\n\n"
        f"PARTNER'S FOCUS: {focus or 'a general investigation'}\n\nDEAL FACTS:\n{facts}\n\nRESULTS:\n{hist}")
    return chat("You are a senior bank-regulatory analyst.", user, step, "Analyst: findings", max_tokens=900)


# ======================================================================================
# STAGE 7 - SUMMARY: the ranked issues list, the one-page partner memo, and a second AI that checks the memo
# ======================================================================================
MEMO_WORD_LIMIT = 430
MEMO_STYLE = ("Write as a lawyer to a lawyer: state facts directly and confidently. Never mention 'passages', 'the loaded "
              "regulations', 'the findings', 'the app' or what the regulations 'do not cover' - if a point is not supported, "
              "leave it out. Where a result rests on an estimate, say so in one short clause. Do not predict whether the deal "
              "will or will not be approved. Put a citation only after a statement about what the law requires - not after "
              "facts about this deal.")


def issues_list(step, rows_text, extra_text, passages):
    user = (
        "You are the senior associate on a bank merger. Below are the app's numbered results [R#] and other workflow "
        "findings. Write the ISSUES LIST the partner needs: group related results into issues, rank them by how much they "
        "matter to the deal (legal consequence, cost, timing), say which issues interact (e.g. a category crossing that also "
        "breaks Reg K), and give one specific action each. Every result with a status other than Met or Already applies must "
        "be covered by an issue (list its [R#] numbers in covers). Use statuses exactly as given. Cite PASSAGES like [C12] for "
        "legal points. " + MEMO_STYLE + "\n"
        "Return JSON only: {\"issues\": [{\"title\": \"6-10 words\", \"severity\": \"high|medium|low\", \"why\": \"two sentences "
        "with citations\", \"action\": \"one specific next step\", \"interacts_with\": [\"title of another issue\"], "
        "\"covers\": [1, 2]}]}  (3 to 8 issues)\n\n"
        f"RESULTS:\n{rows_text}\n\nOTHER FINDINGS:\n{extra_text}\n\nPASSAGES:\n{passages_block(passages)}")
    raw = json_call(CLOSED_WORLD_RULES + "\nReturn only valid JSON.", user, step, "Issues list", passages,
                    max_tokens=3500, need="issues")
    out = []
    for it in raw.get("issues", []) if isinstance(raw.get("issues"), list) else []:
        if not isinstance(it, dict) or not it.get("title"):
            continue
        why, action = str(it.get("why", "")), str(it.get("action", ""))
        for field in ("why", "action"):
            chk = check_citations(why if field == "why" else action, passages)
            if chk["invalid"]:
                if field == "why":
                    why = strip_invalid(why, chk["invalid"])
                else:
                    action = strip_invalid(action, chk["invalid"])
        covers = []
        for c in it.get("covers", []) or []:
            try:
                covers.append(int(str(c).strip("R[] ")))
            except ValueError:
                pass
        sev = str(it.get("severity", "medium")).lower()
        out.append({"title": str(it["title"]), "severity": sev if sev in ("high", "medium", "low") else "medium", "why": why,
                    "action": action, "interacts_with": [str(x) for x in it.get("interacts_with", []) or []],
                    "covers": covers})
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(out, key=lambda x: order.get(x["severity"], 1))


def check_memo(step, memo_text, facts, passages):
    """A second AI call on the memo: legal statements must follow from their cited passage; facts and figures must come
    from the WORKFLOW FINDINGS (the app's results). Returns {"supported", "unsupported": [...], "minor": [...]}."""
    user = (
        "You are a careful senior reviewer. Check the MEMO sentence by sentence and flag only real problems:\n"
        "- 'error': a statement about what the LAW requires that its cited passage does not support or contradicts, a "
        "statement cited to the wrong passage, or a fact about this deal that the WORKFLOW FINDINGS do not support or "
        "contradict, or a conclusion the findings do not support (e.g. predicting whether the deal will be approved).\n"
        "- 'minor': anything else worth tidying (citation placement, wording).\n"
        "Do NOT flag a sentence that is supported. Do not flag recommendations or next steps.\n"
        "Return JSON only: {\"flags\": [{\"sentence\": \"...\", \"severity\": \"error|minor\", \"problem\": \"...\"}]} "
        "(an empty list if nothing is wrong)\n\n"
        f"MEMO:\n{memo_text}\n\nWORKFLOW FINDINGS:\n{facts}\n\nPASSAGES:\n{passages_block(passages)}")
    v = json_call("Return only valid JSON.", user, step, "Memo check (second AI)", passages, max_tokens=1500, temperature=0)
    flags = [u for u in v.get("flags", []) if isinstance(u, dict) and u.get("sentence")] if isinstance(v.get("flags"), list) else []
    errors = [u for u in flags if str(u.get("severity", "")).lower() == "error"]
    return {"supported": not errors, "unsupported": errors, "minor": [u for u in flags if u not in errors]}


def partner_memo(step, facts, issues_text, passages, shorten_from=None, words=None, fix=None):
    """Returns the memo as parts (subject, bottom line, findings, recommendations, caveat); code assembles the email.
    shorten_from: tighten an over-long draft. fix: revise a draft whose statements the checker could not confirm."""
    if fix:
        problems = "\n".join(f"- \"{u['sentence']}\" - {u.get('problem', '')}" for u in fix["unsupported"])
        task = ("A reviewer could not confirm these statements in your memo:\n" + problems + "\nRevise the memo: correct each "
                "statement so it says only what its cited passage or the WORKFLOW FINDINGS support, or remove it. Keep "
                f"everything else, every figure exactly as written, and the same JSON shape. At most {MEMO_WORD_LIMIT - 60} "
                "words. " + MEMO_STYLE + "\n\nMEMO:\n" + fix["memo"])
    elif shorten_from:
        task = (f"This memo is {words or 'too many'} words - too long for one page. Rewrite it in at most {MEMO_WORD_LIMIT - 80} "
                "words: keep the bottom line, at most 4 findings of 2 sentences each and at most 4 one-sentence recommendations; "
                "keep every figure exactly as written and keep the citations; cut repetition first. Same JSON shape. "
                + MEMO_STYLE + "\n\nMEMO:\n" + shorten_from)
    else:
        task = ("Write a one-page internal memo, ready to email to the supervising partner at a law firm, on the regulatory "
                "screening of this bank merger. Lead with the answer. Plain, precise legal English; no hedging boilerplate. "
                "Use ONLY the facts and figures given, copied exactly (never compute a new number). Cite PASSAGES like [C12] for "
                f"each legal point. Whole memo under {MEMO_WORD_LIMIT - 60} words. " + MEMO_STYLE)
    task += ("\nReturn JSON only: {\"subject\": \"under 12 words\", \"bottom_line\": \"2-3 sentences: the answer\", "
             "\"findings\": [{\"heading\": \"3-6 words\", \"text\": \"2 sentences with figures and citations\"}] (3 or 4), "
             "\"recommendations\": [\"one sentence each\"] (3 or 4), \"caveat\": \"one sentence on what was not checked\"}")
    user = f"{task}\n\nWORKFLOW FINDINGS:\n{facts}\n\nISSUES LIST:\n{issues_text}\n\nPASSAGES:\n{passages_block(passages)}"
    raw = json_call(CLOSED_WORLD_RULES + "\nReturn only valid JSON.", user, step,
                    "Partner memo - revised after check" if fix else ("Partner memo - shortened" if shorten_from else "Partner memo - draft"),
                    passages, max_tokens=3000, need="bottom_line")
    memo = {"subject": str(raw.get("subject") or "Regulatory screen of the proposed merger"),
            "bottom_line": str(raw.get("bottom_line") or ""),
            "findings": [{"heading": str(f.get("heading", "")), "text": str(f.get("text", ""))}
                         for f in (raw.get("findings") or []) if isinstance(f, dict) and f.get("text")][:5],
            "recommendations": [str(r) for r in (raw.get("recommendations") or []) if r][:5],
            "caveat": str(raw.get("caveat") or "")}
    blob = json.dumps(memo)
    chk = check_citations(blob, passages)
    if chk["invalid"]:
        memo = json.loads(strip_invalid(blob, chk["invalid"]))
    memo["citations"] = chk
    return memo
