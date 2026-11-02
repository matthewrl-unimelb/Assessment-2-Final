"""
app.py - Bank Merger Regulatory Check (Streamlit).

Run it:   python3 -m streamlit run app.py

This file only does three things:
  1. sets up the page and its look (ui.py);
  2. draws the left-hand panel: the OpenAI API key box and the list of steps;
  3. shows the step you are on. Each step lives in its own file in the steps/ folder.

The rest of the app:
  ai.py       every call to OpenAI                        library.py  the regulation library and its search
  state.py    what the app remembers between clicks       ui.py       the look and the left-hand panel
"""

import streamlit as st

st.set_page_config(page_title="Bank Merger Regulatory Check", page_icon="🏦", layout="wide")

import state  # noqa: E402  (must come after set_page_config)
import ui  # noqa: E402
from steps import home  # noqa: E402

# The steps of the workflow, in order: (id, name in the left-hand panel, the function that draws the page).
STEPS = [
    ("home", "Home", home.render),
]
# Reference pages listed under the steps.
EXTRAS = []

state.register(STEPS, EXTRAS)
state.init()
ui.apply_style()
counter = ui.sidebar()
page = state.current_page()
{pid: draw for pid, _, draw in STEPS + EXTRAS}[page]()
ui.nav_buttons()
ui.show_counter(counter)
