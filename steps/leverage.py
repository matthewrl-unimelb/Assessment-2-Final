"""
Stage 4 - Leverage & liabilities: the leverage ratios and the 10% liabilities cap.

  * CODE: the 4% Tier 1 leverage ratio (12 CFR 217.10(a)(1)(iv)); from Category III the 3% supplementary leverage
    ratio (217.10(a)(1)(v)); the 10% limit on the combined firm's share of the financial sector's liabilities
    (12 U.S.C. 1852(b); 12 CFR 251), including any debt raised to pay for the deal (a number the user enters).
  * AI (RAG): "what this means" for this deal, and an optional plain-English guide.
"""

import streamlit as st

import ai
import deal as D
import engine as E
import state
import ui
from state import S, fp, keep, saved
from ui import pct

STEP = "Leverage & liabilities"

GUIDE_SECTIONS = [("12 CFR 217.10", "leverage ratio is the ratio"),
                  ("12 CFR 217.10", "total leverage exposure"),
                  ("12 CFR 217.11", "leverage buffer"),
                  ("12 CFR 251.2", "10 percent of the aggregate"),
                  ("12 CFR 251.3", "consolidated liabilities")]


def render():
    ui.header("leverage")
    if not D.ready():
        return ui.need_banks()
    d = D.deal()
    cat = d["cat_c"][0]
    st.markdown("### Leverage")
    ui.lede("The leverage ratio compares Tier 1 capital with total assets, ignoring risk. Every bank needs 4%. From "
            "Category III, a second \"supplementary\" ratio of 3% also applies.")
    rows = []
    for r in E.leverage_tests(d["c"], cat):
        row = {"Ratio": f"<b>{r['test']}</b>", "Needed": f"{r['minimum']:.1f}%"}
        for col, bank in (("Buyer", d["a"]), ("Bank bought", d["t"]), ("Combined", d["c"])):
            v = bank.get(r["key"])
            row[col] = ui.ratio_cell(v, E.judge(v, r["minimum"], r["minimum"])) if v is not None else "<span class='muted'>not reported</span>"
        rows.append(row)
    ui.table(rows, ["Ratio", "Needed", "Buyer", "Bank bought", "Combined"])
    ui.muted("Source: 12 CFR 217.10(a)(1)(iv) and (v). Only banks of Category III and above report the supplementary "
             "leverage ratio, so it can only be combined when both banks report it.")

    # ---- what the leverage measures mean (optional, written by AI on request) ----
    st.markdown("### What these ratios mean")
    guide_key = fp("leverage-explained")
    if guide_key in S["ai_cache"]:
        ui.show_ai(S["ai_cache"][guide_key], "Plain-English guide to leverage and the liabilities limit", "leverage_explained")
    else:
        ui.muted("Not needed if you work with bank capital rules every day. Otherwise, AI can write a short plain-English guide, "
                 "drawn only from the regulations in the app.")
        if st.button("✨ Explain leverage in plain English"):
            facts_now = (f"Tier 1 leverage ratio: buyer {pct(d['a']['leverage_ratio'])}, bank bought {pct(d['t']['leverage_ratio'])}, "
                         f"combined {pct(d['c']['leverage_ratio'])}, minimum 4%. Supplementary leverage ratio (only banks of $250bn+ "
                         f"report it): buyer {ui.reported(d['a'].get('slr'))}, bank bought {ui.reported(d['t'].get('slr'))}, combined "
                         f"{ui.reported(d['c'].get('slr'))}; it applies to the combined bank from Category III. Combined bank: "
                         f"{E.cat_label(cat)}. Liabilities: {d['liab']['detail']}")
            res = ui.run_ai(guide_key, lambda: ai.explain_multi(
                STEP, "Write a short plain-English guide for a transactional lawyer. Use a bold heading for each of: Tier 1 "
                      "leverage ratio; How it differs from the risk-based capital ratios; Supplementary leverage ratio and total "
                      "leverage exposure; The enhanced SLR for the largest banks; The 10% liabilities concentration limit. Under "
                      "each, two or three short sentences: first what it is in everyday words, drawn from the passages, then one "
                      "sentence tying it to this deal's figures in APP FACTS. Cite passages. No preamble.",
                facts_now, GUIDE_SECTIONS, state.lib()), "Writing the guide…")
            if res:
                st.rerun()

    # ---- what each size category must hold ----
    st.markdown("### What each size category must hold")
    ui.lede("Every bank needs a 4% Tier 1 leverage ratio. From Category III, the supplementary leverage ratio adds a second "
            "test that also counts off-balance-sheet exposures; the largest banks hold an extra buffer on top.")
    here = {}
    here.setdefault(d["cat_a"][0], []).append("buyer today")
    here.setdefault(cat, []).append("after the deal")
    lrows = []
    for c_, who, lev, slr, src in E.CATEGORY_LEVERAGE:
        label = f"<b>{'Below $100bn' if c_ == 'None' else 'Category ' + c_}</b>"
        if c_ in here:
            label += "<br>" + " ".join(f'<span class="pill" style="background:#1f3a931a;color:#1f3a93">{x}</span>' for x in here[c_])
        lrows.append({"Size category": label, "Who": who, "Tier 1 leverage ratio": lev, "Supplementary leverage ratio": slr,
                      "Source": src})
    ui.table(lrows, ["Size category", "Who", "Tier 1 leverage ratio", "Supplementary leverage ratio", "Source"], src_col="Source")

    # ---- the liabilities limit ----
    st.markdown("### Liabilities")
    ui.lede("No merger may leave the combined firm with more than 10% of the liabilities of the whole U.S. financial sector. "
            "If the buyer borrows to pay for the deal, that debt adds to the combined liabilities.")
    debt = st.number_input("Debt raised to finance the deal (US$bn)", 0.0, value=float(saved("deal_debt_bn", 0.0)), step=1.0,
                           help="For example, senior notes issued by the buyer's holding company to fund the purchase price.")
    if debt != saved("deal_debt_bn", 0.0):
        keep("deal_debt_bn", debt)
        st.rerun()
    L = d["liab"]
    total_liab = d["c"]["total_liabilities"] + d["deal_debt"]
    share_of_limit = min(1.0, max(0.0, total_liab / L["limit"]))
    c1, c2 = st.columns([3, 1])
    with c1:
        st.progress(share_of_limit, text=(f"Combined liabilities {E.bn(total_liab)}"
                                          + (f" (incl. {E.bn(d['deal_debt'])} of deal debt)" if d["deal_debt"] else "")
                                          + f" — {share_of_limit * 100:.1f}% of the way to the {E.bn(L['limit'])} limit"
                                          ).replace("$", "\\$"))
    c2.markdown(ui.pill(L["status"]), unsafe_allow_html=True)
    ui.muted(f"Room left under the limit: <b>{E.bn(L['limit'] - total_liab)}</b>. Source: 12 U.S.C. 1852(b); 12 CFR 251. "
             f"Sector total {E.bn(E.FIN_SECTOR_LIABILITIES)} — {E.FIN_SECTOR_SOURCE}")

    facts = (f"Leverage ratio: buyer {pct(d['a']['leverage_ratio'])}, bank bought {pct(d['t']['leverage_ratio'])}, combined "
             f"{pct(d['c']['leverage_ratio'])} vs 4% minimum. Combined category {E.cat_label(cat)} (SLR applies from Category III). "
             f"Liabilities: {L['detail']}")
    st.write("")
    res = ui.run_ai(fp("leverage", facts), lambda: ai.explain(
        STEP, "In under 150 words explain the leverage position and the liabilities concentration limit for this deal. "
              "Cite passages.", facts,
        "leverage ratio 4 percent supplementary leverage ratio concentration limit consolidated liabilities 10 percent financial companies",
        state.lib()))
    ui.show_ai(res, "What this means", "leverage")
    ui.chat_box(STEP, facts)
