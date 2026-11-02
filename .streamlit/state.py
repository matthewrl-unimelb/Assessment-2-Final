"""
state.py - what the app remembers while you use it.

Streamlit re-runs the whole script every time you click something, so anything that must survive a
click is kept in st.session_state ("S" here). Nothing is ever written to disk or sent anywhere else.
"""

import datetime
import hashlib
import json

import streamlit as st

import ai
from library import Library

S = st.session_state

STEP_IDS, EXTRA_IDS, NAMES = [], [], {}


def register(steps, extras):
    """app.py tells this file which steps exist, in order, and their names."""
    STEP_IDS[:] = [pid for pid, _, _ in steps]
    EXTRA_IDS[:] = [pid for pid, _, _ in extras]
    NAMES.clear()
    NAMES.update({pid: name for pid, name, _ in steps + extras})


def init():
    S.setdefault("page", "home")
    S.setdefault("saved", {})        # the user's choices (banks, dates, ...)
    S.setdefault("ai_cache", {})     # AI results, so a page does not ask the AI the same thing twice
    S.setdefault("audit", [])        # every AI call, for the downloadable audit trail
    S.setdefault("ai_calls", 0)
    S.setdefault("searches", 0)
    S.setdefault("cost_usd", 0.0)
    S.setdefault("chat", [])         # the question box: every question and answer this session
    S.setdefault("chat_i", 0)


def saved(name, default=None):
    return S["saved"].get(name, default)


def keep(name, value):
    S["saved"][name] = value
    return value


def go(page):
    S["page"] = page


def fp(*parts):
    """A short fingerprint of some inputs - used to know when an AI result must be redone."""
    return hashlib.md5(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:12]


def pages():
    """The steps shown in the left-hand panel, in order. 'Canadian buyer' only appears for a Canadian buyer."""
    return [p for p in STEP_IDS if p != "canadian" or saved("canadian")]


def current_page():
    """The page to show. If it is no longer offered (e.g. 'Canadian buyer' after unticking it), go back to Home."""
    if S["page"] not in pages() and S["page"] not in EXTRA_IDS:
        S["page"] = "home"
    return S["page"]


def nice_date(yyyymmdd):
    try:
        return datetime.datetime.strptime(yyyymmdd, "%Y%m%d").strftime("%d %b %Y")
    except (TypeError, ValueError):
        return str(yyyymmdd)


@st.cache_resource(show_spinner=False)
def _library():
    lib = Library()
    lib.embed_fn = ai.embed          # searches use the key of whoever is searching, at the moment they search
    return lib


def lib():
    return _library()
