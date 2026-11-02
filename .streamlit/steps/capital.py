"""
Stage 3 - Capital ratios: each bank, and the two combined, against what each size category needs.

  * CODE: the three risk-based ratios (CET1, Tier 1, Total capital) against the minimums in 12 CFR 217.10(a) and the
    2.5% buffer in 217.11(a); what each size category must hold; where each figure comes from in the FR Y-9C.
  * AI (RAG): "what this means" for this deal, from the library passages; and an optional plain-English guide,
    built from the exact sections that define each term (explain_multi).
"""

import streamlit as st

import ai
import deal as D
import engine as E
import state
import ui
from state import S, fp, saved
from ui import nice_name, pct

STEP = "Capital ratios"
nb = lambda x: x.replace("≥ ", "≥&nbsp;")      # keep "≥ 7.0%" on one line in a narrow column

GUIDE_SECTIONS = [("12 CFR 217.2", "Standardized total risk-weighted assets means"),
                  ("12 CFR 217.20", "Common equity tier 1 capital is the sum"),
                  ("12 CFR 217.20", "Additional tier 1 capital is the sum"),
                  ("12 CFR 217.20", "Tier 2 capital is the sum"),
                  ("12 CFR 217.10", "minimum capital requirements"),
                  ("12 CFR 217.11", "maximum payout ratio"),
                  ("12 CFR 217.11", "Stress capital buffer requirement"),
                  ("12 CFR 217.11", "must calculate a countercyclical capital buffer amount"),
                  ("12 CFR 217.403", "surcharge")]


def render():
    ui.header("capital")
    if not D.ready():
        return ui.need_banks()
    d = D.deal()
    ui.lede("Every bank must keep three ratios of capital to risk-weighted assets above a minimum, plus a 2.5% buffer. "
            "Below the buffer, dividends and bonuses are restricted; below the minimum, the bank is under-capitalised.")
    rows = []
    for k, name, m in E.CAPITAL_RATIOS:
        r = {"Ratio": f"<b>{name}</b>", "Needed": f"{m:.1f}% minimum<br><span class='muted'>{m + E.BUFFER:.1f}% with buffer</span>"}
        for col, bank in (("Buyer", d["a"]), ("Bank bought", d["t"]), ("Combined", d["c"])):
            r[col] = ui.ratio_cell(bank[k], E.judge(bank[k], m, m + E.BUFFER))
        rows.append(r)
    ui.table(rows, ["Ratio", "Needed", "Buyer", "Bank bought", "Combined"])
    arm = f" ({saved('parent_key')}'s U.S. arm)" if saved("canadian") else ""
    ui.muted(f"Buyer: {nice_name(d['a']['name'])}{arm} · Bank bought: {nice_name(d['t']['name'])} · Source: 12 CFR 217.10(a) "
             "(minimums), 217.11(a) (buffer). For Category IV and above, the buffer is the bank's stress capital buffer, which "
             "is at least 2.5% (12 CFR 225.8).")

    # ---- what the ratios mean (optional, written by AI on request) ----
    st.markdown("### What these ratios mean")
    guide_key = fp("ratios-explained")
    if guide_key in S["ai_cache"]:
        ui.show_ai(S["ai_cache"][guide_key], "Plain-English guide to the capital ratios", "ratios_explained")
    else:
        ui.muted("Not needed if you work with bank capital rules every day. Otherwise, AI can write a short plain-English "
                 "guide to each ratio, drawn only from the regulations in the app.")
        if st.button("✨ Explain these ratios in plain English"):
            facts_now = "\n".join(f"{name}: buyer {pct(d['a'][k])}, bank bought {pct(d['t'][k])}, combined {pct(d['c'][k])}; "
                                  f"minimum {m}%, with buffer {m + E.BUFFER}%" for k, name, m in E.CAPITAL_RATIOS)
            res = ui.run_ai(guide_key, lambda: ai.explain_multi(
                STEP, "Write a short plain-English guide for a transactional lawyer. Use a bold heading for each of: "
                      "Risk-weighted assets; CET1 capital and the CET1 ratio; Tier 1 capital (including additional Tier 1); "
                      "Total capital (including Tier 2); The buffers on top of the minimums (conservation buffer, stress capital "
                      "buffer, countercyclical buffer, GSIB surcharge); What happens below the buffer or the minimum. Under each, "
                      "two or three short sentences: first what it is in everyday words, drawn from the passages, then one "
                      "sentence tying it to this deal's figures in APP FACTS. Cite passages. No preamble.",
                facts_now, GUIDE_SECTIONS, state.lib()), "Writing the guide…")
            if res:
                st.rerun()

    # ---- what each size category must hold ----
    st.markdown("### What each size category must hold")
    ui.lede("The minimums are the same for every bank. What grows with size is the buffer on top — and below the buffer, "
            "dividends and bonuses are restricted.")
    here = {}
    here.setdefault(d["cat_a"][0], []).append("buyer today")
    here.setdefault(d["cat_c"][0], []).append("after the deal")
    crow = []
    for cat, who, c1, t1, tot, buffer, src in E.CATEGORY_CAPITAL:
        label = f"<b>{'Below $100bn' if cat == 'None' else 'Category ' + cat}</b>"
        if cat in here:
            label += "<br>" + " ".join(f'<span class="pill" style="background:#1f3a931a;color:#1f3a93">{x}</span>' for x in here[cat])
        crow.append({"Size category": label, "Who": who if cat != "None" else "No category",
                     "CET1": nb(c1), "Tier 1": nb(t1), "Total capital": nb(tot), "The buffer on top of the minimum": buffer,
                     "Source": src})
    ui.table(crow, ["Size category", "Who", "CET1", "Tier 1", "Total capital", "The buffer on top of the minimum", "Source"],
             src_col="Source")
    ui.muted("Minimums for every bank: CET1 4.5%, Tier 1 6%, Total capital 8% (12 CFR 217.10(a)). Figures shown are minimum "
             "plus the lowest possible buffer; a bank's actual stress capital buffer, countercyclical buffer and GSIB surcharge "
             "are set by the Fed and can be higher.")

    with st.expander("Where these numbers come from"):
        st.markdown('<span class="code-tag">✓ Calculated without AI</span>&nbsp; Read straight from the Fed filings and '
                    'double-checked.', unsafe_allow_html=True)
        frows = []
        for k in ("cet1", "tier1", "total_capital", "rwa"):
            codes, lbl, loc = E.FIELDS[k]
            frows.append({"Figure": lbl, "Buyer": E.bn(d["a"][k]), "Bank bought": E.bn(d["t"][k]), "Combined": E.bn(d["c"][k]),
                          "FR Y-9C line": f"{' + '.join(codes)} · {loc}"})
        ui.table(frows, ["Figure", "Buyer", "Bank bought", "Combined", "FR Y-9C line"], src_col="FR Y-9C line")
        for b in (d["a"], d["t"]):
            st.markdown(f"**{nice_name(b['name'])}** — " + " · ".join(
                f"{'✓' if c['ok'] else '?' if c['ok'] is None else '✕'} {c['check']}" for c in E.cross_checks(b)))

    facts = ("\n".join(f"{name}: buyer {pct(d['a'][k])}, bank bought {pct(d['t'][k])}, combined {pct(d['c'][k])}; needed {m}% "
                       f"min / {m + E.BUFFER}% with buffer" for k, name, m in E.CAPITAL_RATIOS)
             + f"\nCombined category: {E.cat_label(d['cat_c'][0])}")
    res = ui.run_ai(fp("capital", facts), lambda: ai.explain(
        STEP, "In under 150 words, explain how the buyer, the bank bought, and the combined bank meet the capital ratio "
              "requirements, and which ratio has the least room. Cite passages.", facts,
        "minimum capital requirements common equity tier 1 capital ratio tier 1 total capital capital conservation buffer",
        state.lib()))
    ui.show_ai(res, "What this means", "capital")
    ui.chat_box(STEP, facts)
