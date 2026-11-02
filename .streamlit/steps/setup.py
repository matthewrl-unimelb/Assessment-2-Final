"""
Stage 1 - Getting started: choose the two banks, then the AI reads both FR Y-9C filings.

  * Each bank: upload its FR Y-9C (the Fed's PDF, or its bulk .txt file) or pick a fictional example bank -
    or load a ready-made example deal.
  * For a Canadian buyer: pick TD, RBC, BMO or CIBC (its U.S. arm's filing is built in), and its Pillar 3 report,
    which the AI reads (code finds the right pages first, and checks the figures after).
  * AI reads each filing line by line and finds 21 figures by their meaning. CODE checks every figure against the
    exact value filed under its Fed code; the AI re-reads any it got wrong (self-correction); then the AI writes an
    analyst's review of the checked figures.
"""

import datetime
import io

import streamlit as st

import ai
import deal as D
import engine as E
import ui
from state import S, fp, keep, saved
from ui import nice_name, pct

STEP = "Getting started"


def render():
    ui.header("setup")
    D.ensure_banks()
    ui.lede("Choose the buyer and the bank being bought. Upload each one's FR Y-9C report from the Federal Reserve, "
            "or pick an example bank.")

    def on_example():
        if S.get("example_choice"):
            D.load_example_deal(S["example_choice"])

    st.selectbox("Or load a ready-made example deal", list(D.EXAMPLE_DEALS), index=None, key="example_choice",
                 placeholder="Choose an example deal — it loads straight away", on_change=on_example)

    is_can = st.checkbox("The buyer is a Canadian bank (TD, RBC, BMO or CIBC)", value=saved("canadian", False))
    if is_can != saved("canadian", False):
        keep("canadian", is_can)
        st.rerun()
    left, right = st.columns(2, gap="large")
    arm_ids = {D.ihc_rssd(k) for k in D.CANADIAN}
    with left:
        if is_can:
            canadian_buyer()
        else:
            bank_picker("acq", "Buyer", exclude=arm_ids | {saved("tgt")})
            keep("gsib", st.checkbox("The buyer is a U.S. GSIB", value=saved("gsib", False),
                                     help="A global systemically important bank (Category I). The example banks are not GSIBs."))
    with right:
        bank_picker("tgt", "Bank being bought (U.S.)", exclude=arm_ids | ({saved("acq")} if not is_can else set()))

    if not D.ready():
        return
    d = D.deal()
    st.write("")
    arm = f"({saved('parent_key')}'s U.S. arm) " if is_can else ""
    st.markdown(f'<div class="card" style="background:#f7f9fc"><b>{nice_name(d["a"]["name"])}</b> {arm}buying '
                f'<b>{nice_name(d["t"]["name"])}</b> · combined {E.bn(d["pf_avg"])} · {E.cat_label(d["cat_a"][0])} → '
                f'<b>{E.cat_label(d["cat_c"][0])}</b></div>', unsafe_allow_html=True)
    c1, c2 = st.columns([1, 2])
    default_close = D.closing_date() or (datetime.date.today() + datetime.timedelta(days=270))
    when = c1.date_input("Expected closing date", value=default_close, format="DD/MM/YYYY",
                         help="Used for the quarter-by-quarter size timeline, disposal deadlines and the memo.")
    if when.isoformat() != saved("closing"):
        keep("closing", when.isoformat())
    c2.markdown('<div style="padding-top:34px" class="muted">Next: the AI reads both banks\' filings below, and the app '
                'checks every figure it reads against the exact value filed.</div>', unsafe_allow_html=True)
    st.write("")
    filing_read_section(d)


# --------------------------------------------------------------------------------------
# Choosing the banks
# --------------------------------------------------------------------------------------
def bank_picker(slot, label, exclude=()):
    """One bank: either an example bank or the user's own FR Y-9C upload (PDF or the Fed's bulk .txt)."""
    st.markdown(f"#### {label}")
    choices = ["Upload its FR Y-9C", "Choose an example bank"]
    # The widgets on this page are controlled through session state (set here, or by an example deal), so they always
    # show the bank the app is actually using - even after visiting another page.
    S.setdefault(f"src_{slot}", saved(f"{slot}_source", "Upload its FR Y-9C"))
    src = st.radio("Source", choices, horizontal=True, label_visibility="collapsed", key=f"src_{slot}")
    keep(f"{slot}_source", src)
    B = S["banks"]
    lab = lambda k: f"{nice_name(B[k]['latest']['name'])}  ·  {E.bn(B[k]['latest']['total_assets'])}"
    if src == "Choose an example bank":
        options = [k for k in sorted(D.example_rssds(), key=lambda k: -B[k]["latest"]["total_assets"]) if k not in exclude]
        ui.muted("Fictional banks, sized just below the category lines so deals cross them.")
    else:
        files = st.file_uploader("FR Y-9C (PDF from the Fed's National Information Center, or the bulk .txt) — up to four quarters",
                                 type=["pdf", "txt"], accept_multiple_files=True, key=f"upload_{slot}")
        if files:
            new = {f.name: f.getvalue() for f in files}
            if new != S.get(f"files_{slot}"):
                S[f"files_{slot}"] = new
                D.rebuild_banks()
                B = S["banks"]
        uploaded = set()
        for name, data in S.get(f"files_{slot}", {}).items():
            try:
                uploaded |= set(D.parse_one(name, data)[1])
            except Exception:
                pass
        options = [k for k in sorted(uploaded, key=lambda k: -B[k]["latest"]["total_assets"]) if k in B and k not in exclude]
        bad = [n for n in S.get("skipped", []) if n in S.get(f"files_{slot}", {})]
        if bad:
            st.warning("Not an FR Y-9C report, so skipped: " + ", ".join(bad))
        if not options:
            ui.muted("Find the bank at [ffiec.gov/npw](https://www.ffiec.gov/npw) → Financial Reports → FR Y-9C. "
                     "The test files are in the app's test_data folder.")
            return None
    if not options:
        return None
    if len(options) == 1:
        keep(slot, options[0])
        b = B[options[0]]
        st.markdown(f"**{nice_name(b['latest']['name'])}** · {E.bn(b['latest']['total_assets'])} · {b['quarters']} quarter(s)")
        return options[0]
    key = f"pick_{slot}_{src}"
    if S.get(key) not in options:
        S[key] = saved(slot) if saved(slot) in options else options[0]
    pick = st.selectbox(label, options, format_func=lab, label_visibility="collapsed", key=key)
    keep(slot, pick)
    return pick


def canadian_buyer():
    st.markdown("#### Buyer (Canadian bank)")
    if S.get("parent_pick") not in D.CANADIAN:
        S["parent_pick"] = saved("parent_key") if saved("parent_key") in D.CANADIAN else D.CANADIAN[0]
    pk = st.selectbox("Canadian bank", D.CANADIAN, format_func=lambda k: f"{nice_name(D.STRUCTURE[k]['parent'])} ({k})",
                      label_visibility="collapsed", key="parent_pick")
    if pk != saved("parent_key"):
        D.reset_parent()
    keep("parent_key", pk)
    keep("acq", D.ihc_rssd(pk))
    arm = S["banks"][D.ihc_rssd(pk)]
    st.markdown(f'Its U.S. arm: **{nice_name(arm["latest"]["name"])}** · {E.bn(arm["latest"]["total_assets"])} '
                f'<span class="muted">(FR Y-9C, built into the app)</span>', unsafe_allow_html=True)
    st.markdown("**Its Pillar 3 report** — for its Canadian capital and total assets")
    c1, c2 = st.columns([1, 1.4])
    if S.get("pending_pillar3"):
        name = S.pop("pending_pillar3")
        read_pillar3(D.read_test(name), name)
    if pk in D.PILLAR3 and c1.button("Use example", width="stretch", help=D.PILLAR3[pk][1]):
        read_pillar3(D.read_test(D.PILLAR3[pk][0]), D.PILLAR3[pk][0])
    pdf = c2.file_uploader("Pillar 3 PDF", type=["pdf"], label_visibility="collapsed", key="p3_upload")
    if pdf is not None:
        read_pillar3(pdf.getvalue(), pdf.name)
    if pk not in D.PILLAR3 and not S.get("parent"):
        ui.muted(f"No example report is built in for {pk} — upload its Pillar 3 PDF, or carry on without it "
                 "(Reg K and the OSFI ratios will show \"can't tell\").")
    v = D.parent_values()
    if v:
        chk = ai.verify_parent(S["parent"]["fig"])
        ok = all(c["ok"] is True for c in chk)
        verdict = ('<span class="code-tag">✓ double-checked against the bank\'s own ratios</span>' if ok else
                   ui.badge(None, "some figures are missing or don't match — check them on the Canadian buyer page"))
        money = lambda x: f"C${x:,.0f}m" if x else "not found"
        st.markdown(f'<span class="ai-tag">✨ Read by AI</span>&nbsp; {ui.esc(v.get("period") or "Latest quarter")}: CET1 '
                    f'{money(v.get("cet1"))}, total assets {money(v.get("total_assets"))} · {verdict}', unsafe_allow_html=True)


def read_pillar3(src_bytes, src_name):
    """Code finds the key-metrics pages; the AI reads them; the result is kept for the Canadian buyer page."""
    if saved("parent_src") == fp(src_name, len(src_bytes)):
        return
    from pypdf import PdfReader
    try:
        text, page_nums = ai.find_capital_pages(PdfReader(io.BytesIO(src_bytes)))
    except Exception:
        st.warning(f"Could not read {src_name} as a PDF.")
        return
    out = ui.run_ai(fp("extract", src_name, len(src_bytes)),
                    lambda: {"fig": ai.extract_parent_figures(STEP, text), "pages": page_nums},
                    "The AI is reading the report's key-metrics table…")
    if out:
        keep("parent_src", fp(src_name, len(src_bytes)))
        S["parent"] = out


# --------------------------------------------------------------------------------------
# The AI reads both filings; code checks every figure
# --------------------------------------------------------------------------------------
def filing_key(b):
    return fp("read-filing", b["rssd"], b["quarter"], len(b.get("raw") or {}))


def read_one_filing(b):
    """AI reads one bank's filing, code checks every figure, the AI re-reads what did not match, then the AI writes
    an analyst's review of the checked figures."""
    text = E.filing_extract(b)
    read = ai.read_filing(STEP, nice_name(b["name"]), text)
    chk = E.check_ai_read(read, b)
    corrected = 0
    misses = {r["key"]: (read.get(r["key"]) or {}).get("value") if isinstance(read.get(r["key"]), dict) else read.get(r["key"])
              for r in chk["rows"] if r["status"] in ("differs", "missed")}
    if misses:                      # the loop: the AI re-reads only what the app could not confirm
        again = ai.reread_filing(STEP, nice_name(b["name"]), text, misses)
        if again:
            before = chk["counts"]["match"]
            read = dict(read, **again)
            chk = E.check_ai_read(read, b)
            corrected = max(0, chk["counts"]["match"] - before)
    chk["corrected"] = corrected
    prof, shares = E.bank_profile(b)
    figs = "\n".join(f"- {k}: {E.bn(v, 2) if isinstance(v, (int, float)) and 'election' not in k else v}"
                     for k, v in prof.items() if v is not None)
    figs += "\n" + "\n".join(f"- {k}: {v:.1f}%" for k, v in shares.items())
    figs += "\n" + "\n".join(f"- {E.FIELDS[k][1]}: {pct(b[k])}" for k in sorted(E.RATIO_FIELDS) if b.get(k) is not None)
    checks = (f"- The AI read {chk['checked']} figures; {chk['counts']['match']} match the filed values exactly, "
              f"{chk['counts']['differs']} differ, {chk['counts']['missed']} were missed.\n"
              + "\n".join(f"- {c['check']}: {c['result']}" for c in E.cross_checks(b)))
    review = ai.review_bank(STEP, nice_name(b["name"]), figs, checks)
    return {"read": read, "check": chk, "review": review}


def filing_read_section(d):
    banks = [d["a"], d["t"]]
    if not ai.ready():
        ui.no_key_note("the AI read both filings")
        return
    results = ui.run_many([(filing_key(b), lambda b=b: read_one_filing(b)) for b in banks],
                          "The AI is reading both filings line by line, and the app is checking every figure…")
    if not all(results):
        return
    checked = sum(r["check"]["checked"] for r in results)
    matched = sum(r["check"]["counts"]["match"] for r in results)
    fixed = sum(r["check"].get("corrected", 0) for r in results)
    ok = True if all(r["check"]["all_ok"] for r in results) else (None if matched >= 0.9 * checked else False)
    label = f"{matched} of {checked} figures match the filing exactly"
    if fixed:
        label += f" — {fixed} corrected by the AI on a second read"
    if ok is not True:
        label += "; the app uses the filed value for the rest"
    st.markdown(f'<div class="card"><span class="ai-tag">✨ Read by AI</span> <span class="code-tag">checked by the app</span>&nbsp; '
                f'<b>The AI read both FR Y-9C filings.</b> {ui.badge(ok, label)}'
                f'<br><span class="muted">The AI found each figure by its meaning, line by line, as an analyst would. The app then '
                f'compared each one with the exact value filed under its Fed code, and recomputed the reported ratios from the AI\'s '
                f'figures. Wherever they disagree, the app uses the filed value.</span></div>', unsafe_allow_html=True)
    st.write("")
    tabs = st.tabs([nice_name(b["name"]) for b in banks])
    fmt = lambda v, is_pct: "—" if v is None else (f"{v:.2f}%" if is_pct else E.bn(v, 2))
    icon = {"match": ui.badge(True, "match"), "differs": ui.badge(False, "differs — app uses the filed value"),
            "missed": ui.badge(None, "AI missed it"), "not_reported": '<span class="muted">not in this filing</span>'}
    for tab, b, r in zip(tabs, banks, results):
        with tab:
            ui.show_ai({"text": r["review"]}, "analyst's review of the filing — figures only, no law", f"review_{b['rssd']}")
            with st.expander(f"Figure by figure — {r['check']['counts']['match']} of {r['check']['checked']} match"):
                ui.table([{"Figure": x["label"], "AI read": fmt(x["ai"], x["pct"]),
                           "Where the AI found it": ui.esc(x["where"]) or "—", "Filed value": fmt(x["exact"], x["pct"]),
                           "Check": icon[x["status"]]} for x in r["check"]["rows"]],
                         ["Figure", "AI read", "Where the AI found it", "Filed value", "Check"])
                st.markdown('<span class="code-tag">Checked without AI</span>&nbsp; ' + " · ".join(
                    f"{'✓' if c['ok'] else '?' if c['ok'] is None else '✕'} {c['check']} from the AI's figures ({c['result']})"
                    for c in r["check"]["internal"]), unsafe_allow_html=True)
