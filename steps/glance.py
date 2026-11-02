"""
Stage 2 - At a glance: every result in one table, and the AI's own reading of the rules.

  * CODE works out every result (size category, what newly applies, capital, leverage, liabilities - and for a
    Canadian buyer, the U.S. rules, Reg K and OSFI), each with its citation.
  * AI writes a short headline (RAG: it may use only the passages the library search returns).
  * AI applies the rules from the regulation text itself, in two rounds: the size category and the "advanced
    approaches" (12 CFR 252.5, 217.2, 217.100), then the seven requirements. Each round is run as THREE independent
    readings at once, and the app takes the majority answer (self-consistency).
  * CODE compares that reading, point by point, with the rulebook built into the app.
"""

import streamlit as st

import ai
import deal as D
import engine as E
import state
import ui
from state import fp

STEP = "At a glance"


def render():
    ui.header("glance")
    if not D.ready():
        return ui.need_banks()
    d = D.deal()
    ui.lede(f"<b>{ui.nice_name(d['a']['name'])}</b> buying <b>{ui.nice_name(d['t']['name'])}</b> — "
            f"combined average assets {E.bn(d['pf_avg'])}.")
    rows = D.summary_rows(d)
    ui.counts(rows)
    ui.summary_table(rows)
    ui.muted("Combined bank = the two banks added together (no purchase premium or goodwill). Size categories use asset size only.")
    facts = D.facts_text(rows)
    st.write("")
    rf, rule_key = D.rule_facts(d)
    lib = state.lib()
    headline, rules = ui.run_many([
        (fp("glance", facts), lambda: ai.explain(
            STEP, "In 3-4 sentences, give the deal lawyer the headline: what the merger changes in regulatory terms and the "
                  "single most important item to watch. Cite passages.", facts,
            "Category IV $100 billion average total consolidated assets capital plan stress capital buffer minimum capital ratios",
            lib)),
        (rule_key, lambda: ai.read_rules(STEP, rf, [r[0] for r in E.REQUIREMENTS], lib, questions=E.REQUIREMENT_QUESTIONS))],
        "AI is writing the headline and, at the same time, reading the regulations to apply the rules itself…")
    ui.show_ai(headline, "Headline", "glance")
    rule_section(d, rules)
    ui.chat_box(STEP, facts)


def rule_section(d, rules):
    st.markdown("### The rules, applied by AI — checked against the built-in rulebook")
    if not rules:
        return
    cmp_ = D.rule_cmp(d, rules)
    ok = cmp_["differ"] == 0
    P = rules["passages"]
    ui.lede("The AI read the regulations themselves — 12 CFR 252.5 for the size category, 217.2 and 217.100 for whether the "
            "bank uses the advanced approaches, then 217.10, 217.11, 217.22, 225.8, 252.44 and Part 249 for what each brings — "
            "and applied them to this deal. The app compared its answer, point by point, with the rulebook built into the app.")
    st.markdown(ui.badge(ok if cmp_["close"] == 0 else (None if ok else False),
                         f"AI and rulebook agree on {cmp_['agree']} of {cmp_['total']} points"
                         + (f", close on {cmp_['close']}" if cmp_["close"] else "")
                         + (f" — {cmp_['differ']} to review" if cmp_["differ"] else "")), unsafe_allow_html=True)
    V = rules.get("votes") or {}
    if V:
        ui.muted(f"The AI read the rules <b>{V['n']} times independently</b>, at the same time, and the app took the majority "
                 f"answer on each point — the readings were unanimous on {V['unanimous']} of {V['points']} points.")
    vote_of = {f"{n} — after the deal": v for n, v in (V.get("requirements") or {}).items()}
    vote_of.update({"Size category before the deal": V.get("before"), "Size category after the deal": V.get("after")})
    mark = {True: ui.badge(True, "agree"), "close": ui.badge(None, "close"), False: ui.badge(False, "differ — review")}
    ui.table([{"Point": r["point"], "AI, from the regulation text": f"<b>{ui.esc(r['ai'])}</b>"
               + (f" <span class='muted'>({vote_of[r['point']]} of {V['n']} readings)</span>" if vote_of.get(r["point"]) else "")
               + f"<br><span class='muted'>{ui.esc(ui.law(r['why'], P))}</span>",
               "Built-in rulebook": r["rulebook"], "": mark[r["agree"]]} for r in cmp_["rows"]],
             ["Point", "AI, from the regulation text", "Built-in rulebook", ""])
    trig = rules.get("other_triggers") or []
    if trig:
        st.markdown("**Other ways this bank could land in a higher category** — found by the AI in the regulation; the app has "
                    "no figures for these, so ask the client.")
        ui.table([{"Trigger": f"<b>{ui.esc(t.get('trigger', ''))}</b>", "Threshold": ui.esc(t.get("threshold", "")),
                   "Effect": ui.esc(t.get("effect", "")), "Ask the client": ui.esc(t.get("check", "")),
                   "Source": ui.esc(ui.law(str(t.get("cite", "")), P).strip(" ()"))} for t in trig],
                 ["Trigger", "Threshold", "Effect", "Ask the client", "Source"], src_col="Source")
    if rules.get("citations", {}).get("invalid"):
        st.caption("⚙️ Citations the AI made to passages it was not given were removed.")
    with st.expander(f"Sources the AI applied ({len(P)})"):
        for p in P:
            st.markdown(f"**[{p['id']}] {p['cite']}** — {p['title']}")
            st.caption(p["text"][:600] + "…")
