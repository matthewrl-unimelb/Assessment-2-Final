"""
Stage 5 - Canadian buyer (only shown when the buyer is TD, RBC, BMO or CIBC).

  A. CODE: its U.S. presence before and after the deal (its U.S. arm's FR Y-9C + the Fed's ownership records).
  B. CODE: the U.S. rules it becomes subject to - the intermediate holding company (12 CFR 252.153) and
     Subpart O of Regulation YY for foreign banks with $100bn+ of combined U.S. assets.
  C. CODE: the Reg K tests (12 CFR 211.23(a)) - may it keep its businesses outside the U.S.?
  D. AI: the holdings review. The AI reads any holdings register (spreadsheet, PDF, Word, text) and gives each
     holding a reasoned verdict under Reg K and Regulation Y. CODE checks every verdict against its own Reg K
     result and works out the disposal timing (12 CFR 211.23(d)).
  E. CODE: the parent's Canadian capital ratios under OSFI, from the Pillar 3 figures the AI read on Getting started.
"""

import io

import pandas as pd
import streamlit as st

import ai
import deal as D
import engine as E
import state
import ui
from state import S, fp, keep, saved
from ui import nice_name

STEP = "Canadian buyer"


def render():
    ui.header("canadian")
    if not D.ready():
        return ui.need_banks()
    if not saved("canadian"):
        ui.lede('This step is for a Canadian bank buying a U.S. bank. Tick <b>"The buyer is a Canadian bank"</b> on the '
                'Getting started page to use it.')
        st.button("Go to Getting started", on_click=state.go, args=("setup",))
        return
    d = D.deal()
    cx = D.canadian(d)
    G, fp_ = cx["G"], cx["fp"]
    parent_name = nice_name(G["parent"])
    ihc_name = nice_name(G["ihcs"][0]["name"]) if G["ihcs"] else "its U.S. holding company"
    ui.lede(f"Once a foreign bank's U.S. presence is big enough, the U.S. regulates it much like a U.S. bank — and that reaches "
            f"back to the businesses it owns at home. Here: <b>{parent_name}</b> buying <b>{nice_name(d['t']['name'])}</b>.")

    # ---- A. U.S. footprint ----
    st.markdown("### A. Its U.S. presence, before and after")
    ui.muted(f"From {ihc_name}'s FR Y-9C and the Fed's ownership records.")
    c1, c2, c3 = st.columns(3)
    for col, lbl, before, after in ((c1, "U.S. subsidiaries (non-branch)", fp_["nonbranch_before"], fp_["nonbranch_after"]),
                                    (c2, "All U.S. operations incl. branches", fp_["combined_before"], fp_["combined_after"])):
        col.markdown(f'<div class="stat"><div class="l">{lbl}</div><div class="n" style="font-size:22px">{E.bn(before)} → '
                     f'{E.bn(after)}</div></div>', unsafe_allow_html=True)
    c3.markdown(f'<div class="stat"><div class="l">Today in the U.S.</div><div class="n" style="font-size:22px">{G["under_ihc"]:,} '
                f'companies</div><div class="l">under the IHC · {len(G["branches"])} branches/offices</div></div>',
                unsafe_allow_html=True)
    st.write("")
    branches = st.number_input("Assets in its U.S. branches and agencies (US$bn, optional)", 0.0,
                               value=float(saved("branches_bn", 0.0)), step=1.0,
                               help="From the branches' FFIEC 002 reports (available from the Fed on request). Branches count "
                                    "toward 'all U.S. operations' but not toward the $50bn IHC trigger.")
    if branches != saved("branches_bn", 0.0):
        keep("branches_bn", branches)
        st.rerun()

    # ---- B. U.S. rules ----
    st.markdown("### B. The U.S. rules it is now subject to")
    ui.muted(E.SUBPART_O_NOTE)
    ui.summary_table(cx["us_rows"])
    new_ihc = E.newly_applying(cx["ihc_before"], cx["ihc_after"])
    if new_ihc:
        st.markdown(f"**What {ihc_name} newly has to do** ({E.cat_label(cx['ihc_before'])} → {E.cat_label(cx['ihc_after'])}):")
        ui.table([{"Requirement": r["Requirement"], "Before": r["Before"], "After": r["After"], "Source": r["Source"]}
                  for r in new_ihc], ["Requirement", "Before", "After", "Source"], src_col="Source")

    # ---- C. Reg K ----
    st.markdown("### C. Reg K — can it keep its businesses at home?")
    ui.lede("A foreign bank may run <b>any</b> business outside the U.S. — and own foreign companies that also do some U.S. "
            "business — only while it is a <b>qualifying foreign banking organization</b>. It must stay mostly a bank, and mostly "
            "outside the U.S. A big U.S. acquisition pushes on the second test.")
    c1, c2, c3 = st.columns(3)
    mostly = c1.radio("Is more than half its worldwide business banking?", ["Yes", "No", "Not sure"],
                      index=["Yes", "No", "Not sure"].index(saved("mostly_banking", "Yes")), horizontal=True,
                      help="Test 1. True for the big Canadian banks; confirm from its annual FR Y-7 report to the Fed.")
    rev = c2.number_input("Share of its banking revenue earned in the U.S. after the deal (%)", 0.0, 100.0,
                          value=saved("us_rev_share"), step=1.0, help="From its annual report's U.S. segment, plus the target.")
    ni = c3.number_input("Share of its banking net income earned in the U.S. after the deal (%)", 0.0, 100.0,
                         value=saved("us_ni_share"), step=1.0, help="From its annual report's U.S. segment, plus the target.")
    if (mostly, rev, ni) != (saved("mostly_banking", "Yes"), saved("us_rev_share"), saved("us_ni_share")):
        keep("mostly_banking", mostly)
        keep("us_rev_share", rev)
        keep("us_ni_share", ni)
        st.rerun()
    q = cx["q"]
    ui.table([{"Measure": l["measure"], "Share in the U.S.": "n/a" if l["us_share"] is None else f"{l['us_share']:.1f}%",
               "Result": ui.pill({True: "met", False: "not_met", None: "unknown"}[l["pass"]]), "Detail": l["detail"]}
              for l in q["legs"]], ["Measure", "Share in the U.S.", "Result", "Detail"])
    room = ""
    if q["headroom"] is not None:
        room = (f" &nbsp; · &nbsp; Room for more U.S. banking assets before the assets measure fails: <b>{E.bn(q['headroom'])}</b>"
                if q["headroom"] > 0 else
                f" &nbsp; · &nbsp; U.S. banking assets are already <b>{E.bn(-q['headroom'])}</b> past the point where the assets "
                "measure fails")
    st.markdown(f"**Overall: {ui.pill(q['overall'])}** &nbsp; Test 1 {ui.pill(q['test1'])} &nbsp; Test 2 {ui.pill(q['test2'])}"
                + room, unsafe_allow_html=True)
    ui.muted("Each test needs 2 of 3 measures. Assets come from the Pillar 3 report and FR Y-9Cs (U.S. assets include branches "
             "entered above); Puerto Rico, Guam and other territories count as the U.S. The parent's total assets are used as "
             "\"outside the U.S.\" after removing U.S. assets — a simplification. Source: 12 CFR 211.23(a)–(b).")
    with st.expander("What happens if it stops qualifying"):
        for title, body, cite in E.REG_K_CONSEQUENCES:
            st.markdown(f"**{title}.** {body} <span class='muted'>({cite})</span>", unsafe_allow_html=True)

    # ---- D. Holdings: what it may have to sell ----
    holdings_section(d, cx, parent_name)
    us_holdings_table(d, G)

    # ---- E. OSFI ----
    st.markdown("### E. Its Canadian capital (OSFI)")
    P = S.get("parent")
    if P:
        fig = P["fig"]
        st.markdown(f'<span class="ai-tag">✨ Read by AI</span>&nbsp; from page(s) {", ".join(map(str, P["pages"]))} of the Pillar 3 '
                    'report. You can correct any figure below (hover over the ⓘ to see the row the AI read).', unsafe_allow_html=True)
        keys = ai.AMOUNT_FIELDS + ("cet1_ratio", "leverage_ratio")
        changed = False
        cols = st.columns(4)
        for i, k in enumerate(keys):
            ratio = k in ("cet1_ratio", "leverage_ratio")
            label = ai.PARENT_FIELDS[k].split(" (")[0] + (" (%)" if ratio else " (C$m)")
            val = cols[i % 4].number_input(label, min_value=0.0, value=fig[k]["value"], step=0.01 if ratio else 1.0,
                                           format="%.2f" if ratio else "%.0f", key=f"p3_{k}_{saved('parent_src')}",
                                           help=("The AI read: " + fig[k]["found_as"]) if fig[k]["found_as"] else "Not found by the AI.")
            if val != fig[k]["value"]:
                fig[k]["value"], changed = val, True
        if changed:
            st.rerun()
        st.markdown('<span class="code-tag">✓ Checked without AI</span>&nbsp; ' + " · ".join(
            f"{'✓' if c['ok'] else '?' if c['ok'] is None else '✕'} {c['check']} ({c['result']})" for c in ai.verify_parent(fig)),
            unsafe_allow_html=True)
    else:
        ui.muted("No Pillar 3 figures yet — load the parent's report on Getting started.")
    c1, c2, c3 = st.columns(3)
    fx = c1.number_input("C\\$ per US\\$1", 0.5, 3.0, float(saved("fx", 1.40)), 0.01, help="Enter today's exchange rate.")
    dsib = c2.checkbox("It is a Canadian D-SIB", value=saved("dsib", True), help="TD, RBC, BMO and CIBC all are.")
    dsb = c3.number_input("OSFI Domestic Stability Buffer (%)", 0.0, 4.0, float(saved("dsb", 3.0)), 0.25,
                          help="Set by OSFI; not in this app's library. Check OSFI's latest announcement.")
    if (fx, dsib, dsb) != (saved("fx", 1.40), saved("dsib", True), saved("dsb", 3.0)):
        keep("fx", fx)
        keep("dsib", dsib)
        keep("dsb", dsb)
        st.rerun()
    ui.summary_table(cx["osfi_rows"])
    ui.muted("Simplified: it pays cash at book value, so its capital is unchanged and the target's risk-weighted assets are added "
             "at their U.S. amount (OSFI's weights may differ).")

    facts = D.facts_text(cx["rows"]) + f"\nParent: {G['parent']}; U.S. holding company: {ihc_name}."
    res = ui.run_ai(fp("canadian", facts), lambda: ai.explain(
        STEP, "In under 200 words, explain to the deal lawyer: which U.S. rules the Canadian bank is (newly) subject to after the "
              "deal; whether it still qualifies under Reg K to keep its non-U.S. businesses, and what happens if not; and which "
              "holdings need review. Use the statuses exactly as given. Cite passages.",
        facts, "qualifying foreign banking organization more than half banking outside United States nonbanking activities "
               "exemptions U.S. intermediate holding company combined U.S. assets $100 billion risk committee", state.lib(), k=8))
    ui.show_ai(res, "What this means", "canadian")
    ui.chat_box(STEP, facts)


# --------------------------------------------------------------------------------------
# D. The holdings register and the disposal review
# --------------------------------------------------------------------------------------
def register_text(name, data):
    """Turn an uploaded register into text the AI can read: spreadsheet rows, PDF pages, Word paragraphs or plain text."""
    low = name.lower()
    if low.endswith((".csv", ".xlsx")):
        df = pd.read_csv(io.BytesIO(data)) if low.endswith(".csv") else pd.read_excel(io.BytesIO(data))
        return df.to_csv(index=False)
    if low.endswith(".pdf"):
        from pypdf import PdfReader
        text, _pages = ai.find_subsidiary_pages(PdfReader(io.BytesIO(data)))
        return text or "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages[:12])
    if low.endswith(".docx"):
        from docx import Document
        doc = Document(io.BytesIO(data))
        rows = ["\t".join(c.text for c in r.cells) for t in doc.tables for r in t.rows]
        return "\n".join([p.text for p in doc.paragraphs if p.text.strip()] + rows)
    return data.decode("utf-8", errors="ignore")


def holdings_section(d, cx, parent_name):
    st.markdown("### D. Holdings — what it may have to sell")
    q, G = cx["q"], cx["G"]
    tone, line = D.two_ways_out(q)
    colour = E.STATUS[tone][2]
    st.markdown(f'<div class="card" style="border-left:4px solid {colour}">{line}</div>', unsafe_allow_html=True)
    sig = E.holding_signals(d["t"])
    if sig:
        ui.muted(f"On <b>{nice_name(d['t']['name'])}</b>'s own balance sheet (its FR Y-9C): "
                 + " · ".join(f"{s['label'].split(' (')[0].lower()} <b>{E.money(s['value'])}</b>" for s in sig)
                 + " — a U.S. holding company may need to sell or conform these. The AI's review on Getting started looks at them.")
    st.write("")
    ui.lede(f"Upload {parent_name}'s holdings register — a spreadsheet, PDF, Word file or plain list. The AI reviews every holding "
            "under Reg K and Regulation Y; the app checks each verdict against its own Reg K result and works out the timing.")
    c1, c2 = st.columns([3, 1.2])
    up = c1.file_uploader("Holdings register", type=["csv", "xlsx", "pdf", "docx", "txt"], key="register_upload",
                          help="Columns or lines with: company, country, business, ownership %, U.S. activities. Any layout works.")
    if c2.button("Use the example register", width="stretch", help="Fictional companies, for demonstration"):
        S["register"] = (D.REGISTER_EXAMPLE, D.read_test(D.REGISTER_EXAMPLE))
    if up is not None:
        S["register"] = (up.name, up.getvalue())
    known = [dict(h, source="Fed records") for h in G.get("foreign_all", []) + G.get("territory_holdings", [])]
    if known:
        c1.caption(f"The review also includes the {len(known)} companies the Fed's records list for {cx['pk']}.")
    reg = S.get("register")
    if reg:
        c2.markdown(f'<span class="muted">Loaded: <b>{ui.esc(reg[0])}</b></span>', unsafe_allow_html=True)
    if st.button("✨ Review the holdings", type="primary", disabled=not (reg or known)):
        if not ai.ready():
            ui.no_key_note("the holdings review")
        else:
            run_review(d, q, parent_name, reg, known)
    res = D.disposal_current()
    if not res:
        return
    if res["regk"] != q["overall"]:
        st.info("The Reg K result above has changed since this review was run — press **Review the holdings** again to update it.")
    rows, P = res["rows"], res["passages"]
    n = {k: sum(1 for r in rows if r["verdict"] == k) for k in E.VERDICTS}
    cols = st.columns(4)
    for col, k in zip(cols, ("sell", "at_risk", "approval", "keep")):
        label, status_ = E.VERDICTS[k]
        colour = E.STATUS[status_][2]
        count = n[k] + (n["keep_conditions"] if k == "keep" else 0)
        col.markdown(f'<div class="stat"><div class="n" style="color:{colour}">{count}</div><div class="l">'
                     f'{label if k != "keep" else "Can keep (incl. with conditions)"}</div></div>', unsafe_allow_html=True)
    st.write("")
    flagged = sum(1 for r in rows if r["notes"])
    st.markdown('<span class="ai-tag">✨ Verdicts by AI</span> <span class="code-tag">checked by the app</span>&nbsp; '
                + ui.badge(flagged == 0, "every verdict is consistent with the app's Reg K result" if flagged == 0 else
                           f"{flagged} verdict(s) flagged for a second look")
                + f' &nbsp;<span class="muted">· {len(rows)} holdings from {ui.esc(res["source"])}</span>', unsafe_allow_html=True)
    stake = lambda r: "" if r.get("ownership_pct") is None else f" · {r['ownership_pct']:.0f}% owned"

    def verdict_pill(r):
        if not r["verdict"]:
            return ui.pill("unknown")
        label, status_ = E.VERDICTS[r["verdict"]]
        return ui.pill(status_).replace(E.STATUS[status_][1], label)

    ui.table([{"Verdict": verdict_pill(r) + "".join(f"<br><span style='color:#b26a00;font-size:13px'>⚠️ App check: {x}</span>"
                                                     for x in r["notes"]),
               "Company": f"<b>{ui.esc(nice_name(r['name']))}</b><br><span class='muted'>{ui.esc(r.get('country', ''))}{stake(r)}</span>",
               "Business": ui.esc(r.get("business") or r.get("activity", ""))
               + (f"<br><span class='muted'>U.S.: {ui.esc(r['us_activity'])}</span>"
                  if r.get("us_activity") and r["us_activity"].lower() != "none" else ""),
               "Why (AI)": ui.esc(ui.law(r["reason"], P)),
               "Next step": ui.esc(r["action"] or "—") + (f"<br><span class='muted'>⏱ {r['timing']}</span>" if r["timing"] else "")}
              for r in rows],
             ["Verdict", "Company", "Business", "Why (AI)", "Next step"])
    out = pd.DataFrame([{"Company": r["name"], "Country": r.get("country"), "Ownership %": r.get("ownership_pct"),
                         "Business": r.get("business") or r.get("activity"), "U.S. activities": r.get("us_activity"),
                         "Verdict": E.VERDICTS[r["verdict"]][0] if r["verdict"] else "No verdict",
                         "Why": ui.law(r["reason"], P), "Next step": r["action"], "Timing": r["timing"],
                         "App check": " ".join(r["notes"])} for r in rows])
    st.download_button("Download the disposal schedule (CSV)", out.to_csv(index=False), file_name="disposal_schedule.csv")
    ui.muted("Covers only the holdings listed — the register uploaded plus the Fed's records. Screening view, not a legal opinion; "
             "timing is a rough guide from the expected closing date on Getting started (the two-year clock under 12 CFR 211.23(d) "
             "runs from the annual reports to the Fed).")


def run_review(d, q, parent_name, reg, known):
    with st.status("Reviewing the holdings…", expanded=True) as status:
        try:
            holdings = []
            if reg:
                status.write(f"✨ AI is reading **{reg[0]}**…")
                holdings = [dict(h, source=reg[0]) for h in ai.extract_register(STEP, register_text(*reg), parent_name)]
                status.write(f"Found {len(holdings)} companies in the register.")
            names = {h["name"].lower() for h in holdings}
            holdings += [dict(h, business=h.get("activity", ""), ownership_pct=None, us_activity="")
                         for h in known if h["name"].lower() not in names]
            if not holdings:
                status.update(label="No holdings found in the register", state="error")
                return
            passages = ai.disposal_passages(holdings, state.lib())
            context = (f"Parent: {parent_name}, a Canadian bank, buying {nice_name(d['t']['name'])}. The app's Reg K result after "
                       f"the deal: test 1 {E.STATUS[q['test1']][1]}, test 2 {E.STATUS[q['test2']][1]}, overall "
                       f"{E.STATUS[q['overall']][1]} (U.S. share of its banking assets "
                       f"{'unknown' if q['legs'][0]['us_share'] is None else format(q['legs'][0]['us_share'], '.1f') + '%'}). "
                       "So: if overall is Not met, its Reg K exemptions are at risk; if Met, it qualifies.")
            status.write(f"✨ AI is reviewing {len(holdings)} holdings against {len(passages)} passages of Reg K and Regulation Y, "
                         "several at once…")
            verdicts = ai.analyse_holdings(STEP, holdings, context, passages)
            status.write("The app is checking every verdict and working out the timing…")
            rows = []
            for h in holdings:
                v = verdicts.get(h["name"]) or {}
                key = v.get("verdict")
                rows.append(dict(h, verdict=key, reason=v.get("reason", ""), action=v.get("action", ""),
                                 timing=E.disposal_timing(key, q["overall"], D.closing_date()),
                                 notes=E.disposal_checks(h, key, q["overall"]) if key else
                                 ["The AI gave no verdict for this holding — review it by hand."]))
            rows.sort(key=lambda r: (E.VERDICT_ORDER.index(r["verdict"]) if r["verdict"] in E.VERDICT_ORDER else -1, r["name"]))
            S["disposal"] = {"deal": D.deal_key(), "rows": rows, "passages": passages, "regk": q["overall"],
                             "source": reg[0] if reg else "the Fed's records"}
            status.update(label="Holdings reviewed", state="complete", expanded=False)
        except Exception as exc:
            status.update(label="The review did not finish", state="error")
            st.error("Something went wrong: " + ai.friendly_error(exc))


def us_holdings_table(d, G):
    st.markdown("**In the U.S.** — everything must sit under the IHC, except branches and narrow exceptions.")
    rows = [{"Item": f"<b>{nice_name(d['t']['name'])}</b> (being bought)", "What to do": "Place under the IHC.", "Source": "12 CFR 252.153"}]
    for x in G["outside_ihc"]:
        rows.append({"Item": nice_name(x["name"]) + f" <span class='muted'>({x['type']}, {x['where']})</span>",
                     "What to do": "Held outside the IHC today — confirm it is a section 2(h)(2) company or DPC branch subsidiary, "
                                   "or move it.", "Source": "12 CFR 252.153"})
    rows.append({"Item": f"{len(G['branches'])} U.S. branches, agencies and representative offices",
                 "What to do": "Stay outside the IHC (part of the parent itself). Branch vs subsidiary is a structuring choice.",
                 "Source": "12 CFR 252.153"})
    ui.table(rows, ["Item", "What to do", "Source"], src_col="Source")
    if G["branches"]:
        with st.expander(f"Its U.S. branches and offices ({len(G['branches'])})"):
            ui.table([{"Office": nice_name(b["name"]), "Type": b["type"], "Where": b["where"]} for b in G["branches"]],
                     ["Office", "Type", "Where"])
