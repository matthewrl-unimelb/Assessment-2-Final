"""
Home - what the app does, how it works, and what is in its regulation library.
"""

import streamlit as st

import ai
import state
import ui

STEPS_PREVIEW = [
    ("Getting started", "Choose the two banks — upload their Fed filings or pick an example. AI reads both filings."),
    ("At a glance", "Every requirement — met, not met, newly applies — and the AI's own reading of the rules."),
    ("Capital ratios", "Each bank, and the two combined, against what each size category needs."),
    ("Leverage & liabilities", "The leverage ratios and the 10% liabilities cap."),
    ("Canadian buyer", "Only for a Canadian buyer: the U.S. rules it takes on, Reg K, and what it may have to sell."),
    ("AI analyst", "AI investigates the deal — choosing what to test, running the app's calculator, reporting back."),
    ("Summary & next steps", "A ranked issues list and a one-page memo, ready to email to the partner."),
]


def render():
    st.markdown("# Bank merger regulatory check")
    ui.lede("For a proposed bank merger, see which U.S. capital rules each bank meets, what the deal changes — and, if the "
            "buyer is a Canadian bank, what U.S. regulation it takes on and what that means for the businesses it owns at home.")
    st.write("")
    left, right = st.columns([1.2, 1], gap="large")
    with left:
        st.markdown("### What you'll see")
        for n, (title, body) in enumerate(STEPS_PREVIEW, 1):
            st.markdown(f'<div class="step-preview"><div class="num">{n}</div><div><b style="font-size:17.5px">{title}</b><br>'
                        f'<span class="muted" style="font-size:15.5px">{body}</span></div></div>', unsafe_allow_html=True)
    with right:
        st.markdown("### How it works")
        st.markdown(
            '<div class="howto"><div class="ic">📖</div><div><b>The rules are built into the app</b>'
            '<span>Every threshold and ratio — the $100bn, $250bn and $700bn lines, the 4.5% CET1 minimum, the 10% liabilities '
            'cap, the Reg K tests — is written into the app from the regulation itself, with the section cited beside it.</span>'
            '</div></div>'
            '<div class="howto"><div class="ic">🧮</div><div><b>The numbers are calculated without AI</b>'
            '<span>Every figure and every met / not met result follows those fixed rules — the same answer every time.</span>'
            '</div></div>'
            '<div class="howto"><div class="ic">✨</div><div><b>The analysis is done by AI — and checked</b>'
            '<span>AI reads the filings, applies the regulations, reviews holdings, investigates the deal and drafts the memo — '
            'using only the regulations in the app. The app checks every figure it reads and writes.</span></div></div>',
            unsafe_allow_html=True)
        st.markdown('<div class="card" style="background:#f7f9fc;margin-top:6px"><b>Why build the rules in?</b><br>'
                    '<span class="muted" style="font-size:15.5px">An AI asked to "apply the capital rules" can misremember a '
                    'threshold or a percentage. Here, the rules are fixed and every one carries its citation — '
                    '<b>so you only have to double-check the work, not triple-check it.</b></span></div>', unsafe_allow_html=True)
        st.write("")
        if "setup" in state.pages():
            st.button("Get started  →", type="primary", on_click=state.go, args=("setup",), width="stretch")
        elif not ai.ready():
            st.info("Start by pasting your OpenAI API key in the left-hand panel.")

    # ---- the closed-world library ----
    st.write("")
    st.markdown("### The regulation library")
    lib = state.lib()
    info = lib.status()
    how = (f"searched by meaning with OpenAI's <b>{ai.EMBED_MODEL}</b>" if info["by_meaning"]
           else f"searched by keywords for now — {info['problem']}")
    st.markdown(f'<div class="card">The AI only ever sees passages from this library — never the web. '
                f'<b>{info["documents"]} documents</b>, split into <b>{info["passages"]:,} passages</b>, {how}</div>',
                unsafe_allow_html=True)
    with st.expander("What's in the library"):
        ui.table([{"Document": s["source"], "Status": s["status"], "As of": s["as_of"], "Passages": s["passages"]}
                  for s in lib.sources()], ["Document", "Status", "As of", "Passages"])
