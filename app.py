"""
app.py - Bank Merger Regulatory Check (Streamlit).

Run it:   python3 -m streamlit run app.py

This file only does three things:
  1. sets up the page and its look (ui.py);
  2. draws the left-hand panel: the OpenAI API key box and the list of steps;
  3. shows the step you are on. Each step lives in its own file in the steps/ folder.

The rest of the app:
  engine.py   every rule and calculation, and the checks of the AI's work (no AI)
  ai.py       every call to OpenAI                        library.py  the regulation library and its search
  deal.py     the deal on screen and its results          state.py    what the app remembers between clicks
  ui.py       the look, the left-hand panel and the shared display pieces
"""

import streamlit as st

st.set_page_config(page_title="Bank Merger Regulatory Check", page_icon="🏦", layout="wide")

import deal  # noqa: E402  (everything below must come after set_page_config)
import state  # noqa: E402
import ui  # noqa: E402
from steps import analyst, canadian, capital, glance, home, leverage, setup, sizes, summary  # noqa: E402

# The steps of the workflow, in order: (id, name in the left-hand panel, the function that draws the page).
STEPS = [
    ("home", "Home", home.render),
    ("setup", "Getting started", setup.render),
    ("glance", "At a glance", glance.render),
    ("capital", "Capital ratios", capital.render),
    ("leverage", "Leverage & liabilities", leverage.render),
    ("canadian", "Canadian buyer", canadian.render),        # only shown when the buyer is a Canadian bank
    ("analyst", "AI analyst", analyst.render),
    ("summary", "Summary & next steps", summary.render),
]
# Reference pages listed under the steps.
EXTRAS = [("sizes", "📏  Size examples", sizes.render)]

state.register(STEPS, EXTRAS)
state.init()
ui.apply_style()
page = state.current_page()
counter = ui.sidebar()
{pid: draw for pid, _, draw in STEPS + EXTRAS}[page]()
ui.nav_buttons(can_continue=deal.ready())
ui.show_counter(counter)
