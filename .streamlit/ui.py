"""
ui.py - the look of the app and the building blocks every page uses: tables, coloured status labels, the purple
"written by AI" box, the question box, and the left-hand panel with the OpenAI API key box and the list of steps.
"""

import re

import streamlit as st

import ai
import state
from engine import STATUS  # icon, word and colour for each result: met, not met, newly applies ...
from state import S


# --------------------------------------------------------------------------------------
# Look and feel
# --------------------------------------------------------------------------------------
def _escape_dollars(fn):
    """Streamlit reads "$...$" as maths. Escape dollar signs in ordinary text (raw HTML blocks are left alone)."""
    def wrapper(body="", *args, **kwargs):
        if isinstance(body, str) and not re.match(r"\s*<(table|div|style|p)[\s>]", body):
            body = re.sub(r"(?<!\\)\$", r"\\$", body)
        return fn(body, *args, **kwargs)
    wrapper._escaped = True
    return wrapper


def apply_style():
    for name in ("markdown", "info", "success", "warning", "error", "caption", "write"):
        if not getattr(getattr(st, name), "_escaped", False):
            setattr(st, name, _escape_dollars(getattr(st, name)))
    st.markdown(CSS, unsafe_allow_html=True)


CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Source+Serif+4:opsz,wght@8..60,600;8..60,700&display=swap');
:root { --ink:#1a1d23; --muted:#6b7280; --line:#e7e9ee; --navy:#1f3a93; --green:#1e7d4f; --ai:#6c4ee0; }
.stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"], [data-testid="stMain"] { background:#ffffff !important; color:var(--ink); }
[data-testid="stSidebar"], [data-testid="stSidebar"] > div { background:#f7f8fa !important; }
.stApp p, .stApp li, .stApp label, .stApp td, .stApp th, .stApp input, .stApp textarea, .stMarkdown {
  font-family:'Inter', system-ui, sans-serif !important; color:var(--ink); }
.stApp button, .stApp button p { font-family:'Inter', system-ui, sans-serif !important; }
.stApp button[kind="primary"], .stApp button[kind="primary"] p, .stApp button[kind="primaryFormSubmit"], .stApp button[kind="primaryFormSubmit"] p { color:#ffffff !important; }
.stApp button[kind="secondary"] p { color:var(--ink); }
.stApp p, .stApp li { font-size:17px; line-height:1.6; }
h1, h2, h3, h4 { font-family:'Source Serif 4', Georgia, serif !important; color:var(--ink) !important; letter-spacing:-0.01em; }
h1 { font-size:2.4rem !important; font-weight:700 !important; }
h2 { font-size:1.75rem !important; font-weight:700 !important; margin-top:0.2rem !important; }
h3 { font-size:1.25rem !important; font-weight:600 !important; }
.block-container { padding-top:2.6rem; max-width:1100px; }
.lede { font-size:19px; color:#3c4250; max-width:760px; line-height:1.55; }
.muted { color:var(--muted) !important; font-size:14.5px; }
.pill { display:inline-block; padding:3px 11px; border-radius:99px; font-weight:600; font-size:13.5px; white-space:nowrap; }
table.nice { width:100%; border-collapse:collapse; margin:4px 0 18px; }
table.nice th { text-align:left; font-weight:600; font-size:13px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted);
  border-bottom:1px solid var(--line); padding:10px 12px; background:#fff; }
table.nice td { padding:12px; border-bottom:1px solid var(--line); vertical-align:top; font-size:15.5px; background:#fff; color:var(--ink); }
table.nice td.src { color:var(--muted); font-size:13.5px; }
.stat { border:1px solid var(--line); border-radius:14px; padding:14px 16px; background:#fff; }
.stat .n { font-size:30px; font-weight:700; font-family:'Inter'; }
.stat .l { font-size:14px; color:var(--muted); }
.card { border:1px solid var(--line); border-radius:16px; padding:18px 20px; background:#fff; }
.step-preview { display:flex; gap:14px; align-items:flex-start; padding:10px 0; border-bottom:1px solid var(--line); }
.step-preview .num { width:30px; height:30px; border-radius:50%; background:#eef2ff; color:var(--navy); font-weight:700;
  display:flex; align-items:center; justify-content:center; flex-shrink:0; }
div.stButton > button { border-radius:10px; font-weight:600; }
/* left-hand step list */
.st-key-nav div.stButton > button > div { justify-content:flex-start; }
.st-key-nav div.stButton > button { justify-content:flex-start; text-align:left; border:1px solid transparent; background:transparent;
  color:var(--ink); padding:.55rem .8rem; font-weight:500; }
.st-key-nav div.stButton > button:hover { background:#eceef3; }
.st-key-nav div.stButton > button[kind="primary"] { background:var(--navy); color:#fff; font-weight:700; }
.arrows { color:var(--green); text-align:center; font-weight:800; line-height:.62; font-size:16px; margin:2px 0 4px; letter-spacing:0; }
.gap { height:6px; border-left:2px solid #dfe3ea; margin-left:26px; }
/* the API key box */
.st-key-keybox { border:1px solid var(--line); border-radius:12px; padding:10px 12px 4px; background:#ffffff; margin-bottom:6px; }
/* AI answers */
[class*="st-key-ai_"] { border-left:4px solid var(--ai); background:#f8f6ff; border-radius:10px; padding:14px 18px 6px; margin:6px 0 14px; }
.ai-tag { display:inline-block; background:#efeafe; color:#5a3fc0; font-size:12.5px; font-weight:600; padding:2px 10px; border-radius:99px; }
.code-tag { display:inline-block; background:#e7f4ec; color:#1e7d4f; font-size:12.5px; font-weight:600; padding:2px 10px; border-radius:99px; }
/* force a light look for every control, whatever theme the browser or server uses */
.stApp button[kind="secondary"], .stApp button[kind="secondaryFormSubmit"], [data-testid="stPopover"] button {
  background:#ffffff !important; color:var(--ink) !important; border:1px solid #d0d5dd !important; }
.stApp button[kind="secondary"]:hover, [data-testid="stPopover"] button:hover { border-color:var(--navy) !important; color:var(--navy) !important; }
.stApp button[kind="secondary"] p, [data-testid="stPopover"] button p { color:inherit !important; }
.stApp button[kind="primary"], .stApp button[kind="primaryFormSubmit"] { background:var(--navy) !important; border:1px solid var(--navy) !important; }
.stApp button:disabled { opacity:.4 !important; cursor:not-allowed !important; }
.stApp button[kind="tertiary"], .stApp button[kind="tertiary"] p { color:var(--navy) !important; background:transparent !important; text-decoration:underline; }
[data-baseweb="select"] > div, [data-testid="stSelectbox"] [data-baseweb="select"] > div:first-child,
[data-baseweb="input"], [data-baseweb="input"] input, [data-baseweb="textarea"], textarea, [data-baseweb="base-input"],
[data-testid="stNumberInputContainer"], [data-testid="stNumberInputContainer"] input, [data-testid="stNumberInputContainer"] button,
[data-testid="stDateInput"] input {
  background:#f5f7fa !important; color:var(--ink) !important; border-color:#d0d5dd !important; }
[data-baseweb="select"] span, [data-baseweb="select"] div, [data-testid="stSelectbox"] * { color:var(--ink) !important; }
[data-baseweb="popover"] ul, [data-baseweb="popover"] li, [data-baseweb="menu"] { background:#ffffff !important; color:var(--ink) !important; }
[data-baseweb="calendar"], [data-baseweb="calendar"] * { background-color:#ffffff; color:var(--ink); }
[data-testid="stFileUploaderDropzone"] { background:#f5f7fa !important; color:var(--ink) !important; }
[data-testid="stFileUploaderDropzone"] * { color:var(--ink) !important; }
/* checkbox ticks and radio dots: navy instead of the default red */
[data-testid="stCheckbox"] div:has(> svg polyline) { background-color:var(--navy) !important; border-color:var(--navy) !important; }
[data-testid="stRadioOption"]:has(input:checked) div:has(> div:only-child:empty) { background-color:var(--navy) !important; border-color:var(--navy) !important; }
/* the left-hand step list stays plain text, not boxes */
.st-key-nav div.stButton > button[kind="secondary"] { background:transparent !important; border:1px solid transparent !important; }
.st-key-nav div.stButton > button[kind="secondary"]:hover { background:#eceef3 !important; }
[data-testid="stExpander"] details, [data-testid="stExpander"] summary { background:#ffffff !important; color:var(--ink) !important; }
[data-testid="stVerticalBlockBorderWrapper"] { background:#ffffff; }
.howto { display:flex; gap:12px; align-items:flex-start; margin:10px 0; }
.howto .ic { font-size:20px; line-height:1.4; }
.howto b { display:block; font-size:16px; }
.howto span { color:var(--muted); font-size:15px; }
</style>
"""


# --------------------------------------------------------------------------------------
# Small display helpers
# --------------------------------------------------------------------------------------
def pill(status):
    icon, label, colour = STATUS[status]
    return f'<span class="pill" style="background:{colour}1a;color:{colour}">{icon}&nbsp; {label}</span>'


def badge(ok, text):
    """ok=True green tick, None amber, False red cross."""
    colour = "#1e7d4f" if ok is True else ("#b26a00" if ok is None else "#b42318")
    icon = "✓" if ok is True else ("!" if ok is None else "✕")
    return f'<span class="pill" style="background:{colour}1a;color:{colour}">{icon}&nbsp; {text}</span>'


def esc(text):
    """Make text safe to put inside HTML (AI text and file contents can contain < or &)."""
    return str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def table(rows, cols, src_col=None):
    """A clean HTML table. rows = list of dicts; values may contain HTML (e.g. pills)."""
    head = "".join(f"<th>{c}</th>" for c in cols)
    body = "".join("<tr>" + "".join(f'<td class="{"src" if c == src_col else ""}">{r.get(c, "")}</td>' for c in cols) + "</tr>"
                   for r in rows)
    st.markdown(f'<table class="nice"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>', unsafe_allow_html=True)


def lede(text):
    st.markdown(f'<p class="lede">{text}</p>', unsafe_allow_html=True)


def muted(text):
    st.markdown(f'<span class="muted">{text}</span>', unsafe_allow_html=True)


ACRONYMS = {"Rbc": "RBC", "Bmo": "BMO", "Td": "TD", "Cibc": "CIBC", "Us": "US", "Usa": "USA", "(Usa)": "(USA)", "Llc": "LLC",
            "Lp": "LP", "N.a.": "N.A.", "Wafd,": "WaFd,", "Of": "of", "The": "the", "And": "and"}


def nice_name(name):
    """'TORONTO-DOMINION BANK, THE' -> 'The Toronto-Dominion Bank'."""
    name = re.sub(r"^(.*?),\s*the$", r"The \1", (name or "").strip(), flags=re.I)
    out = [ACRONYMS.get(w, w) for w in name.title().split()]
    if out:
        out[0] = out[0][0].upper() + out[0][1:]
    return " ".join(out)


def pct(v):
    return "n/a" if v is None else f"{v:.2f}%"


def reported(v):
    """A ratio for the AI's facts: 'not reported' rather than 'n/a', so it isn't read as 'not applicable'."""
    return "not reported in the filings" if v is None else f"{v:.2f}%"


def ratio_cell(value, status):
    icon, _, colour = STATUS[status]
    return f'<span style="color:{colour};font-weight:600">{icon}&nbsp; {pct(value)}</span>'


def law(text, passages):
    """Passage IDs -> real citations, for anything a lawyer will read or copy out."""
    return ai.cites_to_law(text or "", passages or [])


def header(pid):
    order = state.pages()
    n = f"{order.index(pid)} · " if pid in order and pid != "home" else ""
    st.markdown(f"## {n}{state.NAMES[pid]}")


def summary_table(rows):
    table([{"Status": pill(r["status"]), "Check": r["check"], "Detail": r["detail"], "Source": r["src"]} for r in rows],
          ["Status", "Check", "Detail", "Source"], src_col="Source")


def counts(rows):
    """The four coloured tiles above a results table."""
    n = {k: 0 for k in STATUS}
    for r in rows:
        n[r["status"]] += 1
    cols = st.columns(4)
    groups = [("met", ("met",), "Met"), ("not_met", ("not_met",), "Not met"),
              ("newly_applies", ("newly_applies", "warning"), "Newly applies / in buffer"),
              ("unknown", ("unknown", "review"), "Can't tell / review")]
    for col, (k, members, name) in zip(cols, groups):
        icon, _, colour = STATUS[k]
        col.markdown(f'<div class="stat"><div class="n" style="color:{colour}">{sum(n[m] for m in members)}</div>'
                     f'<div class="l">{icon} {name}</div></div>', unsafe_allow_html=True)
    st.write("")


def need_banks():
    st.info("First choose the two banks on the **Getting started** page.")
    st.button("Go to Getting started", on_click=state.go, args=("setup",), type="primary")


# --------------------------------------------------------------------------------------
# Showing AI results, and running AI calls (one at a time, or several at once)
# --------------------------------------------------------------------------------------
def no_key_note(what="the AI's part of this step"):
    if ai.key_status() == "bad":
        st.warning("Your OpenAI key isn't working, so this part can't run yet — check the key in the left-hand panel. "
                   "Everything else works without it.")
    else:
        st.info(f"Add your OpenAI API key in the left-hand panel to see {what}. Everything else works without it.")


def run_ai(cache_key, fn, label="Thinking…"):
    """Run one AI task once and remember the result (so a page does not ask the AI the same thing twice)."""
    if cache_key in S["ai_cache"]:
        return S["ai_cache"][cache_key]
    if not ai.ready():
        no_key_note()
        return None
    with st.spinner(label):
        try:
            out = fn()
        except Exception as exc:
            st.error("The AI step did not work: " + ai.friendly_error(exc))
            return None
    S["ai_cache"][cache_key] = out
    return out


def run_many(jobs, label):
    """jobs = [(cache_key, fn), ...]. Runs the ones not yet done AT THE SAME TIME under one spinner."""
    todo = [(k, f) for k, f in jobs if k not in S["ai_cache"]]
    if todo and not ai.ready():
        no_key_note()
    elif todo:
        def safe(f):
            def run():
                try:
                    return f()
                except Exception as exc:          # one failed call should not lose the others
                    return {"_error": ai.friendly_error(exc)}
            return run
        with st.spinner(label):
            outs = ai.parallel([safe(f) for _, f in todo])
        errors = [o["_error"] for o in outs if isinstance(o, dict) and "_error" in o]
        for (k, _), o in zip(todo, outs):
            if not (isinstance(o, dict) and "_error" in o):
                S["ai_cache"][k] = o
        if errors:
            st.error("An AI step did not work: " + errors[0])
    return [S["ai_cache"].get(k) for k, _ in jobs]


def show_ai(result, title, key):
    """The purple box that marks anything written by AI, with its verified sources underneath."""
    if not result:
        return
    with st.container(key=f"ai_{key}"):
        chk = result.get("check")
        note = ""
        if chk:
            note = (f"cites {len(chk['cited'])} regulation passage(s) — all verified" if chk["has_citations"] and not chk["invalid"]
                    else "⚠️ unverified citations were removed" if chk["invalid"] else "no citations")
        st.markdown(f'<span class="ai-tag">✨ Written by AI</span> <span class="muted">&nbsp;{title}{" · " + note if note else ""}</span>',
                    unsafe_allow_html=True)
        # passage IDs ([C41]) become the real citations ((12 CFR 217.10)); the sources are listed underneath
        st.markdown(law(result["text"], result["passages"]) if result.get("passages") else result["text"])
        if result.get("passages"):
            with st.expander(f"Sources the AI was allowed to use ({len(result['passages'])})"):
                for p in result["passages"]:
                    st.markdown(f"**[{p['id']}] {p['cite']}** — {p['title']}  \n<span class='muted'>{p['status']} · as of {p['as_of']}</span>",
                                unsafe_allow_html=True)
                    st.caption(p["text"][:700] + ("…" if len(p["text"]) > 700 else ""))


# --------------------------------------------------------------------------------------
# The question box (from Stage 2): one running Q&A shared by every page
# --------------------------------------------------------------------------------------
def chat_box(page, facts):
    """Answers come only from the library; a second AI call checks each one. ◀ ▶ step through earlier answers."""
    st.markdown("### Ask a question")
    muted("Answers come only from the regulations loaded into this app, and a second AI call checks each one.")
    with st.form(key=f"chatform_{page}", clear_on_submit=True, border=False):
        c1, c2 = st.columns([5, 1])
        q = c1.text_input("Question", label_visibility="collapsed", placeholder="e.g. What does the stress capital buffer do?")
        sent = c2.form_submit_button("Ask", type="primary", width="stretch")
    if sent and q.strip():
        if not ai.ready():
            no_key_note("an answer")
        else:
            with st.spinner("Searching the regulations, answering, then checking the answer…"):
                try:
                    ans = ai.ask(page, q.strip(), facts, state.lib())
                    S["chat"].append({"q": q.strip(), "a": ans, "page": page})
                    S["chat_i"] = len(S["chat"]) - 1
                except Exception as exc:
                    st.error("The question could not be answered: " + ai.friendly_error(exc))
    if S["chat"]:
        i = min(S["chat_i"], len(S["chat"]) - 1)
        item = S["chat"][i]
        c1, c2, c3 = st.columns([1, 3, 1])
        c1.button("◀  Older", key=f"older_{page}", disabled=i == 0, on_click=lambda: S.update(chat_i=i - 1), width="stretch")
        c2.markdown(f"<div style='text-align:center;padding-top:8px' class='muted'>Question {i + 1} of {len(S['chat'])}</div>",
                    unsafe_allow_html=True)
        c3.button("Newer  ▶", key=f"newer_{page}", disabled=i == len(S["chat"]) - 1, on_click=lambda: S.update(chat_i=i + 1),
                  width="stretch")
        st.markdown(f"**Q: {item['q']}**")
        show_ai(item["a"], "Answer" + ("" if item["a"].get("verified") else " · not fully confirmed by the checker"), f"chat_{page}")
        if item["a"].get("trail"):
            with st.expander("How this answer was checked"):
                for t in item["a"]["trail"]:
                    st.write("• " + t)


# --------------------------------------------------------------------------------------
# The left-hand panel: API key box, then the steps (green arrows show where you are)
# --------------------------------------------------------------------------------------
def key_box():
    with st.container(key="keybox"):
        st.markdown("**🔑 Your OpenAI API key**")
        k = st.text_input("Your OpenAI API key", type="password", key="api_key_box", placeholder="sk-…",
                          label_visibility="collapsed",
                          help="Paste your own OpenAI key. It is used only while this browser tab is open — never saved, "
                               "never shown, never sent anywhere except OpenAI.")
        S["api_key"] = (k or "").strip()
        if S["api_key"]:
            ok, msg = ai.check_key()
            st.markdown(badge(True, f"Key works · {ai.MODEL}") if ok else badge(False, "Key not working"), unsafe_allow_html=True)
            if not ok:
                st.caption(msg)
        else:
            st.caption("Paste your key to switch on the AI. Everything else works without it.")
        st.caption(f"AI model: {ai.MODEL} · search: {ai.EMBED_MODEL}")


def sidebar():
    with st.sidebar:
        st.markdown("### 🏦 Merger check")
        key_box()
        st.write("")
        order = state.pages()
        current = order.index(S["page"]) if S["page"] in order else None
        with st.container(key="nav"):
            for i, p in enumerate(order):
                done = current is not None and 0 < i < current
                label = ("✓  " if done else "") + (f"{i}  " if i else "") + state.NAMES[p]
                st.button(label, key=f"nav_{p}", on_click=state.go, args=(p,), width="stretch",
                          type="primary" if S["page"] == p else "secondary")
                if i < len(order) - 1:
                    st.markdown('<div class="arrows">⌄<br>⌄<br>⌄</div>' if current == i else '<div class="gap"></div>',
                                unsafe_allow_html=True)
            if state.EXTRA_IDS:
                st.markdown('<div style="height:10px"></div>', unsafe_allow_html=True)
            for p in state.EXTRA_IDS:
                st.button(state.NAMES[p], key=f"nav_{p}", on_click=state.go, args=(p,), width="stretch",
                          type="primary" if S["page"] == p else "secondary")
        st.divider()
        return st.empty()     # filled with the AI call counter once the page has run


def show_counter(slot):
    cost = S.get("cost_usd", 0.0)
    slot.markdown(f'<span class="muted">AI calls this session: <b>{S.get("ai_calls", 0)}</b> · '
                  f'library searches: <b>{S.get("searches", 0)}</b><br>'
                  f'OpenAI cost so far: about <b>US${cost:.2f}</b></span>', unsafe_allow_html=True)


def nav_buttons(can_continue=True):
    """Back / Next at the foot of each step."""
    order = state.pages()
    if S["page"] not in order:
        return
    st.write("")
    st.divider()
    i = order.index(S["page"])
    c1, _, c3 = st.columns([1, 2, 1])
    if i > 0:
        c1.button("←  Back", on_click=state.go, args=(order[i - 1],), width="stretch", key="back")
    if i < len(order) - 1:
        nxt = order[i + 1]
        c3.button(f"Next: {state.NAMES[nxt]}  →", on_click=state.go, args=(nxt,), type="primary", width="stretch", key="next",
                  disabled=not can_continue and nxt != "setup")
