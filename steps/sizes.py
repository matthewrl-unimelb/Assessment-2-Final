"""
Size examples - a reference page: made-up deals landing in each size category, and a calculator to try your own.
All CODE (12 CFR 252.5) - no AI.
"""

import streamlit as st

import engine as E
import ui

EXAMPLES = [
    ("Below $100bn — no category", "Harbor Bancorp ($45bn) + Prairie Financial ($30bn)", 75e6, False),
    ("Category IV", "Lakeshore Bancorp ($85bn) + Summit Bank ($40bn)", 125e6, False),
    ("Category III", "Pacific Crest Financial ($190bn) + Gulf Coast Bancshares ($85bn)", 275e6, False),
    ("Category II", "Atlantic National ($480bn) + Continental Trust ($260bn)", 740e6, False),
    ("Category I (GSIB)", "A U.S. GSIB ($2.5tn) + Riverbend Bank ($30bn)", 2530e6, True),
]


def render():
    ui.header("sizes")
    ui.lede("Which category a merger lands in depends mainly on the combined bank's average total assets. These made-up pairs "
            "show each step of the ladder.")
    rows = []
    for label, pair, total, gsib in EXAMPLES:
        cat = E.category(total, gsib)[0]
        switched_on = [r[0].split(" (")[0] for r in E.REQUIREMENTS if r[1][cat] not in ("No", "Optional opt-out")]
        rows.append({"Lands in": f"<b>{label}</b>", "Example deal (fictitious)": pair, "Combined": E.bn(total),
                     "What switches on": ", ".join(switched_on) or "Base rules only"})
    ui.table(rows, ["Lands in", "Example deal (fictitious)", "Combined", "What switches on"])
    ui.muted("There is no \"Category 5\": below $100bn a bank simply has no category. Category I is only for U.S. GSIBs, which "
             "are identified by the Fed's GSIB method, not size alone. Source: 12 CFR 252.5.")
    st.markdown("### Try your own")
    c1, c2, c3 = st.columns(3)
    x = c1.number_input("Buyer ($bn)", 0.0, value=120.0, step=5.0)
    y = c2.number_input("Bank bought ($bn)", 0.0, value=60.0, step=5.0)
    g = c3.checkbox("Buyer is a GSIB")
    cat, why = E.category((x + y) * 1e6, g)
    st.markdown(f"**{E.cat_label(cat)}** — {why}")
