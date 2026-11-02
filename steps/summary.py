"""
Stage 7 - Summary & next steps: a ranked issues list and a one-page memo, ready to email to the partner.

  * AI weighs every result into a ranked ISSUES LIST. CODE checks that every flagged result is covered, and adds any
    the AI dropped.
  * AI drafts a one-page MEMO to the partner from everything the workflow found. Then a bounded loop:
    CODE counts the words (AI tightens an over-long draft) -> a SECOND AI checks every statement against its source
    (reflection) -> AI revises anything flagged as an error -> check again (at most three checks).
  * CODE turns passage IDs into real citations, and checks every figure in the memo against the app's own results.
  * Downloads: the memo as a one-page Word file, as an email draft (.eml), the full report, and the AI audit trail.
"""

import datetime
import io
import json
import re

import streamlit as st

import ai
import deal as D
import engine as E
import state
import ui
from state import S, fp, keep, saved
from ui import nice_name, pct

STEP = "Summary"

NEXT_STEPS = {
    "Size category": "Plan for the new category's requirements to be in place by closing — supervisors expect it.",
    "Annual capital plan (CCAR)": "Start building the capital plan and stress-testing capability (12 CFR 225.8).",
    "Stress capital buffer": "Model the combined bank's stress capital buffer once it is in the capital plan cycle (12 CFR 225.8).",
    "Supervisory stress test": "Prepare for the Fed's supervisory stress test cycle.",
    "Supplementary leverage ratio (3%)": "Model the combined supplementary leverage ratio using both banks' leverage exposure.",
    "Countercyclical capital buffer": "Track the countercyclical buffer the Fed sets and build it into the capital plan (12 CFR 217.11(b)).",
    "Unrealised securities gains/losses": "Model CET1 with unrealised securities losses included, as the AOCI opt-out is lost (12 CFR 217.22).",
    "Liquidity coverage ratio / NSFR": "Check whether the combined bank's funding mix triggers the liquidity coverage ratio.",
    "Hold all U.S. subsidiaries": "Place the bank being bought under the U.S. intermediate holding company.",
    "U.S. companies held outside the IHC": "Confirm each U.S. company outside the IHC falls within an exception, or move it under the IHC.",
    "U.S. risk committee": "Set up the U.S. risk committee and appoint a U.S. chief risk officer (12 CFR 252.155).",
    "Liquidity stress tests": "Build U.S. liquidity stress testing and hold a U.S. liquidity buffer (12 CFR 252.157).",
    "Capital stress testing": "Prepare for capital stress testing of the U.S. operations (12 CFR 252.158).",
    "Certify the parent": "Prepare the certification that the parent meets Basel-consistent home capital standards (12 CFR 252.154).",
    "Reg K exemptions": "Before signing, map which non-banking holdings outside the U.S. rely on the exemptions, and consider asking "
                        "the Fed for a specific determination of eligibility (12 CFR 211.23(e)) or restructuring the deal.",
    "Reg K test": "Confirm the Reg K tests with revenue and net income from the annual report; consider asking the Fed for a "
                  "specific determination (12 CFR 211.23(e)).",
    "Holdings the parent may have to sell": "Run or finish the holdings review; for each holding marked 'likely must sell', confirm "
                                            "the facts and plan the sale or restructuring (12 CFR 211.23).",
    "Parent's": "Load the parent's Pillar 3 report to check its OSFI ratios.",
    "Four-quarter average size": "Upload the other three quarters of FR Y-9C data to confirm the size category.",
    "AI's reading of the rules": "Review the points where the AI's reading of the regulations differs from the built-in rulebook.",
}
FLAGGED = ("not_met", "newly_applies", "warning", "unknown", "review")
RUN_TARGET = {"AI analyst": "analyst", "Holdings review": "canadian", "Rules applied by AI": "glance", "Filings read by AI": "setup"}


# --------------------------------------------------------------------------------------
# Everything the workflow found, as text for the issues list and the memo
# --------------------------------------------------------------------------------------
def workflow_findings(d, rows):
    """Returns (findings text, {part of the workflow: included?})."""
    a, t = d["a"], d["t"]
    who = f"{saved('parent_key')} (through its U.S. arm {nice_name(a['name'])})" if saved("canadian") else nice_name(a["name"])
    deal_line = f"DEAL: {who} buying {nice_name(t['name'])}. Data as of {', '.join(d['quarters'])}."
    if D.closing_date():
        deal_line += f" Expected closing {D.closing_date():%d %B %Y}."
    parts, included = [deal_line], {}
    from steps.setup import filing_key
    reads = [S["ai_cache"].get(filing_key(b)) for b in (a, t)]
    if all(reads):
        m = sum(r["check"]["counts"]["match"] for r in reads)
        c = sum(r["check"]["checked"] for r in reads)
        parts.append(f"FILINGS: the AI read both FR Y-9C filings; the app confirmed {m} of {c} figures exactly against the filed values.")
    included["Filings read by AI"] = all(reads)
    for b in (a, t):
        prof, sh = E.bank_profile(b)
        bits = [f"total assets {E.bn(b['total_assets'])}", f"CET1 ratio {pct(b['cet1_ratio'])}"]
        if "AOCI as % of CET1" in sh:
            bits.append(f"AOCI {E.bn(prof['AOCI'])} = {sh['AOCI as % of CET1']:.1f}% of CET1"
                        + (" (AOCI opt-out elected)" if prof.get("AOCI opt-out election (1 = opted out)") == 1 else ""))
        if "Goodwill as % of equity" in sh:
            bits.append(f"goodwill {sh['Goodwill as % of equity']:.1f}% of equity")
        parts.append(f"BANK - {nice_name(b['name'])}: " + "; ".join(bits) + ".")
    sig = E.holding_signals(t)
    if sig:
        parts.append("BANK BEING BOUGHT - balance-sheet lines a U.S. holding company may need to sell or conform (exact, from its "
                     "FR Y-9C): " + "; ".join(f"{s['label']} {E.money(s['value'])}" for s in sig) + ".")
    parts.append("RESULTS (status | check | detail | source):\n" + "\n".join(
        f"- {E.STATUS[r['status']][1]} | {r['check']} | {r['detail']} | {r['src']}" for r in rows))
    cmp_, rules = D.rule_cmp(d), S["ai_cache"].get(D.rule_facts(d)[1])
    if cmp_:
        parts.append(f"RULES: the AI applied 12 CFR 252.5 and the requirement sections itself and agreed with the built-in rulebook "
                     f"on {cmp_['agree']} of {cmp_['total']} points. Other triggers the app cannot test: "
                     + "; ".join(f"{x.get('trigger')} ({x.get('threshold')})" for x in (rules.get("other_triggers") or [])[:4]) + ".")
    included["Rules applied by AI"] = bool(cmp_)
    if saved("canadian"):
        parts.append("REG K CHOICE: " + re.sub(r"<[^>]+>", "", D.two_ways_out(D.canadian(d)["q"])[1]))
        disp = D.disposal_current()
        if disp:
            groups = {k: [nice_name(r["name"]) for r in disp["rows"] if r["verdict"] == k] for k in E.VERDICTS}
            parts.append("HOLDINGS DISPOSAL REVIEW (AI verdicts checked by the app): " + "; ".join(
                f"{E.VERDICTS[k][0]}: {', '.join(v[:6])}" for k, v in groups.items() if v) + ".")
        included["Holdings review"] = bool(disp)
    an = S.get("analyst_last")
    has_analyst = bool(an and an["deal"] == D.deal_key())
    if has_analyst:
        parts.append("AI ANALYST FINDINGS (numbers from the app's calculator):\n" + an["report"])
    included["AI analyst"] = has_analyst
    return "\n\n".join(p for p in parts if p), included


def memo_passages(rows):
    q = [("12 CFR 252.5", None, 2), ("12 CFR 225.8", "$100 billion asset threshold", 1),
         ("12 CFR 217.10", "supplementary leverage ratio of 3 percent", 1), ("12 CFR 217.11", "capital conservation buffer", 1),
         ("12 CFR 217.22", "AOCI opt-out election", 1), ("12 CFR 251.3", "consolidated liabilities", 1)]
    if saved("canadian"):
        q += [("12 CFR 211.23", None, 4), ("12 CFR 252.153", "intermediate holding company", 1),
              ("12 CFR 252.154", "combined U.S. assets of $100 billion", 1)]
    lib = state.lib()
    passages = lib.fetch(q)
    flagged = " ".join(r["check"] for r in rows if r["status"] in FLAGGED)[:300]
    if flagged:
        for p in lib.search(flagged, k=3):
            if p["id"] not in {x["id"] for x in passages} and lib.relevant([p]):
                passages.append(p)
    return passages


# --------------------------------------------------------------------------------------
# The issues list and the memo (AI drafts, code and a second AI check)
# --------------------------------------------------------------------------------------
def build_issues(rows, facts, passages):
    rows_text = "\n".join(f"[R{i}] {E.STATUS[r['status']][1]} | {r['check']} | {r['detail']} | {r['src']}"
                          for i, r in enumerate(rows, 1))
    issues = ai.issues_list(STEP, rows_text, facts, passages)
    need = {i for i, r in enumerate(rows, 1) if r["status"] in FLAGGED}
    covered = {c for it in issues for c in it["covers"]}
    missing = sorted(need - covered)
    if missing:   # code's safety net: nothing flagged may be dropped
        acts = []
        for i in missing:
            r = rows[i - 1]
            text = next((t for k, t in NEXT_STEPS.items() if r["check"].startswith(k)), f"Review: {r['detail']}.")
            acts.append(f"{r['check']}: {text}")
        issues.append({"title": "Also flagged — added by the app", "severity": "medium",
                       "why": "The AI's list did not cover these results.", "action": " ".join(acts), "interacts_with": [],
                       "covers": missing, "added_by_app": True})
    return {"issues": issues, "missing": missing, "need": len(need)}


def issues_text(issues):
    return "\n".join(f"{i}. [{it['severity']}] {it['title']} - {it['why']} Action: {it['action']}" for i, it in enumerate(issues, 1))


def memo_body(m, passages):
    """The memo's words with real citations (no greeting or sign-off) - for the word count and the number check."""
    L = lambda x: ui.law(x, passages)
    lines = [L(m["bottom_line"])] + [f"{f.get('heading', '')}. {L(f.get('text', ''))}" for f in m["findings"]]
    return "\n".join(lines + [L(r) for r in m["recommendations"]] + [L(m["caveat"])])


def build_memo(facts, issues, passages):
    """Draft -> (tighten until it fits one page) -> second-AI check -> revise what it flags -> repeat, a bounded number of times."""
    it_text = issues_text(issues)
    m = ai.partner_memo(STEP, facts, it_text, passages)
    count = lambda mm: len(memo_body(mm, passages).split())
    strip = lambda mm: json.dumps({k: mm[k] for k in mm if k != "citations"})
    raw = lambda mm: "\n".join([mm["bottom_line"]] + [f"{f.get('heading', '')}. {f.get('text', '')}" for f in mm["findings"]]
                               + mm["recommendations"] + [mm["caveat"]])
    shortened, revised, verdict = False, 0, None

    def tighten(mm):
        nonlocal shortened
        for _ in range(2):
            if count(mm) <= ai.MEMO_WORD_LIMIT:
                break
            m2 = ai.partner_memo(STEP, facts, it_text, passages, shorten_from=strip(mm), words=count(mm))
            if m2["bottom_line"] and m2["findings"]:
                mm, shortened = m2, True
        return mm

    m = tighten(m)
    for round_ in range(3):
        verdict = ai.check_memo(STEP, raw(m), facts, passages)
        if verdict["supported"] or round_ == 2:
            break
        m2 = ai.partner_memo(STEP, facts, it_text, passages, fix={"unsupported": verdict["unsupported"], "memo": strip(m)})
        if not (m2["bottom_line"] and m2["findings"]):
            break
        m, revised = tighten(m2), revised + 1
    nums = E.verify_numbers(memo_body(m, passages), facts + it_text)
    return {"memo": m, "words": count(m), "shortened": shortened, "revised": revised, "verdict": verdict, "numbers": nums}


# --------------------------------------------------------------------------------------
# The memo as an email, an .eml draft and a one-page Word file
# --------------------------------------------------------------------------------------
def memo_email(m, passages, to, frm, client):
    """The memo as an email: (subject, plain text, html)."""
    subj = (f"{client} — " if client else "") + m["subject"]
    first = (to or "").split()[0] if (to or "").strip() else ""
    L = lambda x: ui.law(x, passages)
    plain = [f"Hi {first}," if first else "Hi,", "", f"Bottom line: {L(m['bottom_line'])}", "", "Key findings"]
    plain += [f"{i}. {f.get('heading', '')}. {L(f.get('text', ''))}" for i, f in enumerate(m["findings"], 1)]
    plain += ["", "Recommended next steps"] + [f"- {L(r)}" for r in m["recommendations"]]
    plain += ["", L(m["caveat"]), "", "Best,", frm or ""]
    e = ui.esc
    html = (f"<p>{'Hi ' + e(first) + ',' if first else 'Hi,'}</p><p><b>Bottom line:</b> {e(L(m['bottom_line']))}</p>"
            "<p style='margin-bottom:4px'><b>Key findings</b></p><ol style='margin-top:0'>"
            + "".join(f"<li><b>{e(f.get('heading', ''))}.</b> {e(L(f.get('text', '')))}</li>" for f in m["findings"]) + "</ol>"
            "<p style='margin-bottom:4px'><b>Recommended next steps</b></p><ul style='margin-top:0'>"
            + "".join(f"<li>{e(L(r))}</li>" for r in m["recommendations"]) + "</ul>"
            f"<p style='color:#6b7280'><i>{e(L(m['caveat']))}</i></p><p>Best,<br>{e(frm)}</p>")
    return subj, "\n".join(plain), html


def make_eml(subj, plain, html, to_addr=""):
    from email.message import EmailMessage
    msg = EmailMessage()
    msg["Subject"] = subj
    msg["To"] = to_addr or ""
    msg["X-Unsent"] = "1"          # opens as a draft ready to send in Outlook
    msg.set_content(plain)
    msg.add_alternative(f"<html><body style='font-family:Calibri,Arial,sans-serif;font-size:11pt'>{html}</body></html>", subtype="html")
    return msg.as_bytes()


def make_memo_docx(m, passages, to, frm, client, d):
    """One-page memorandum in Word."""
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Inches, Pt, RGBColor
    doc = Document()
    for sec in doc.sections:
        sec.top_margin = sec.bottom_margin = Inches(0.75)
        sec.left_margin = sec.right_margin = Inches(0.95)
    st_ = doc.styles["Normal"]
    st_.font.name, st_.font.size = "Calibri", Pt(10.5)
    st_.paragraph_format.space_after, st_.paragraph_format.space_before = Pt(4), Pt(0)
    st_.paragraph_format.line_spacing = 1.05
    L = lambda x: ui.law(x, passages)

    def para(text="", bold_lead=None, size=None, italic=False, color=None, align=None, after=None):
        p = doc.add_paragraph()
        if bold_lead:
            r = p.add_run(bold_lead)
            r.bold = True
        r = p.add_run(text)
        r.italic = italic
        if size:
            for run in p.runs:
                run.font.size = Pt(size)
        if color:
            for run in p.runs:
                run.font.color.rgb = RGBColor(*color)
        if align is not None:
            p.alignment = align
        if after is not None:
            p.paragraph_format.space_after = Pt(after)
        return p

    para("PRIVILEGED & CONFIDENTIAL — ATTORNEY WORK PRODUCT", size=8, color=(107, 114, 128), align=WD_ALIGN_PARAGRAPH.RIGHT, after=2)
    t = para("MEMORANDUM", size=15, after=4)
    t.runs[0].bold = True
    for lead, val in (("TO:\t", to or "Supervising partner"), ("FROM:\t", frm or ""),
                      ("DATE:\t", datetime.date.today().strftime("%d %B %Y")),
                      ("RE:\t", (f"{client} — " if client else "") + m["subject"])):
        para(val, bold_lead=lead, after=0)
    rule = para(after=6)
    pPr = rule._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    for k, v in (("w:val", "single"), ("w:sz", "6"), ("w:space", "1"), ("w:color", "1F3A93")):
        bottom.set(qn(k), v)
    bdr.append(bottom)
    pPr.append(bdr)
    para(L(m["bottom_line"]), bold_lead="Bottom line. ", after=5)
    h = para("Key findings", after=2)
    h.runs[0].bold = True
    for i, f in enumerate(m["findings"], 1):
        para(L(f.get("text", "")), bold_lead=f"{i}. {f.get('heading', '')}. ", after=3)
    h = para("Recommended next steps", after=2)
    h.runs[0].bold = True
    for r in m["recommendations"]:
        p = doc.add_paragraph(L(r), style="List Bullet")
        p.paragraph_format.space_after = Pt(1)
    para(L(m["caveat"]), italic=True, size=8.5, color=(107, 114, 128), after=0)
    para(f"Prepared with the Bank Merger Regulatory Check app from FR Y-9C data as of {', '.join(d['quarters'])}. "
         "Figures calculated by the app; drafting by AI and checked by the app — verify before relying on it.",
         italic=True, size=8, color=(107, 114, 128))
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def make_report_docx(d, rows, issues, memo_plain, passages):
    """The full report: every result, the issues list and the memo."""
    from docx import Document
    doc = Document()
    doc.add_heading("Bank merger regulatory check", 0)
    doc.add_paragraph(f"{nice_name(d['a']['name'])} buying {nice_name(d['t']['name'])}. Data as of {', '.join(d['quarters'])}.")
    doc.add_heading("Results", 1)
    tbl = doc.add_table(rows=1, cols=4)
    tbl.style = "Light Grid Accent 1"
    for i, h in enumerate(["Status", "Check", "Detail", "Source"]):
        tbl.rows[0].cells[i].text = h
    for r in rows:
        cells = tbl.add_row().cells
        for i, val in enumerate([E.STATUS[r["status"]][1], r["check"], r["detail"], r["src"]]):
            cells[i].text = val
    doc.add_heading("Issues and next steps (ranked by AI, checked by the app)", 1)
    for it in issues:
        p = doc.add_paragraph(style="List Number")
        p.add_run(f"{it['title']} [{it['severity']}]. ").bold = True
        p.add_run(f"{ui.law(it['why'], passages)} Next step: {ui.law(it['action'], passages)}")
    doc.add_heading("Memo to the partner (AI-drafted, checked by the app)", 1)
    for line in memo_plain.split("\n"):
        if line.strip():
            doc.add_paragraph(line.strip())
    doc.add_paragraph("Screening tool, not legal advice. The combined bank is a simple sum of the two banks; verify against the "
                      "filings and rules cited.")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------------------
def render():
    ui.header("summary")
    if not D.ready():
        return ui.need_banks()
    d = D.deal()
    rows = D.summary_rows(d)
    ui.lede(f"<b>{nice_name(d['a']['name'])}</b> buying <b>{nice_name(d['t']['name'])}</b> · data as of {', '.join(d['quarters'])}")
    ui.counts(rows)
    ui.summary_table(rows)
    facts, included = workflow_findings(d, rows)

    # ---- what feeds the memo ----
    missing_parts = [k for k, v in included.items() if not v]
    not_run = lambda k: f'<span class="pill" style="background:#6b72801a;color:#6b7280">○&nbsp; {k} — not run</span>'
    st.markdown("**In this summary:** " + " ".join(ui.badge(True, k) if v else not_run(k) for k, v in included.items()),
                unsafe_allow_html=True)
    if missing_parts:
        cols = st.columns(len(missing_parts) + 1)
        for col, k in zip(cols, missing_parts):
            col.button(f"Run: {k} →", key=f"run_{k}", on_click=state.go, args=(RUN_TARGET[k],), width="stretch")
        st.caption("Optional — run them and this page updates to include their findings.")

    # ---- next steps: the issues list ----
    st.markdown("### Next steps")
    if not ai.ready():
        ui.no_key_note("the AI's issues list and the partner memo")
        return
    passages = memo_passages(rows)
    ikey = fp("issues", facts)
    (iss,) = ui.run_many([(ikey, lambda: build_issues(rows, facts, passages))],
                         "The AI is weighing every result into a ranked issues list, and the app is checking nothing was dropped…")
    if not iss:
        return
    st.markdown('<span class="ai-tag">✨ Ranked by AI</span> <span class="code-tag">checked by the app</span>&nbsp; '
                + ui.badge(True if not iss["missing"] else None, f"all {iss['need']} flagged results are covered" if not iss["missing"] else
                           f"the app added {len(iss['missing'])} result(s) the AI missed"), unsafe_allow_html=True)
    sev_col = {"high": "#b42318", "medium": "#b26a00", "low": "#6b7280"}
    for i, it in enumerate(iss["issues"], 1):
        colour = sev_col.get(it["severity"], "#6b7280")
        links = (f"<br><span class='muted'>Interacts with: {ui.esc('; '.join(it['interacts_with']))}</span>"
                 if it["interacts_with"] else "")
        covers = ", ".join(rows[c - 1]["check"] for c in it["covers"] if 0 < c <= len(rows))
        st.markdown(f'<div class="card" style="margin-bottom:10px;border-left:4px solid {colour}">'
                    f'<b>{i}. {ui.esc(it["title"])}</b> &nbsp;<span class="pill" style="background:{colour}1a;color:{colour}">'
                    f'{it["severity"].capitalize()}</span>{" &nbsp;" + ui.badge(None, "added by the app") if it.get("added_by_app") else ""}'
                    f'<br>{ui.esc(ui.law(it["why"], passages))}<br><b>Next step:</b> {ui.esc(ui.law(it["action"], passages))}{links}'
                    f'<br><span class="muted" style="font-size:13px">Covers: {ui.esc(covers) or "—"}</span></div>',
                    unsafe_allow_html=True)

    # ---- the partner memo ----
    st.markdown("### Memo to the partner")
    ui.lede("One page, ready to email: the AI drafts it from everything above; the app converts its citations to the real "
            "regulations, keeps it to one page, checks every figure against the app's results, and a second AI call checks "
            "every legal statement against its source.")
    c1, c2, c3 = st.columns(3)
    to = c1.text_input("To", value=saved("memo_to", ""), placeholder="e.g. Jane Smith")
    frm = c2.text_input("From", value=saved("memo_from", ""), placeholder="Your name")
    client = c3.text_input("Client / matter", value=saved("memo_client", ""), placeholder="e.g. Project Maple")
    keep("memo_to", to)
    keep("memo_from", frm)
    keep("memo_client", client)
    mkey = fp("memo", facts, issues_text(iss["issues"]))
    (memo,) = ui.run_many([(mkey, lambda: build_memo(facts, iss["issues"], passages))],
                          "The AI is drafting the partner memo; then the app and a second AI call are checking it…")
    if not memo:
        return
    m, v, nums = memo["memo"], memo["verdict"], memo["numbers"]
    checks = [ui.badge(memo["words"] <= ai.MEMO_WORD_LIMIT,
                       f"one page — {memo['words']} words" + (" (tightened by AI)" if memo["shortened"] else "")),
              ui.badge(not nums["unverified"], f"all {nums['checked']} figures match the app's results" if not nums["unverified"]
                       else f"check: {', '.join(nums['unverified'][:3])}"),
              ui.badge(not m["citations"]["invalid"], "every citation is a regulation in the library"),
              ui.badge(True if v.get("supported") else None,
                       ("second AI check: every statement supported"
                        + (f" (after {memo['revised']} revision{'s' if memo['revised'] > 1 else ''})" if memo.get("revised") else ""))
                       if v.get("supported") else f"second AI check: {len(v.get('unsupported', []))} statement(s) to verify — see below")]
    st.markdown(" ".join(checks), unsafe_allow_html=True)
    subj, plain, html = memo_email(m, passages, to, frm, client)
    st.markdown(f'<div class="card" style="margin-top:10px"><div class="muted" style="border-bottom:1px solid var(--line);'
                f'padding-bottom:8px;margin-bottom:10px"><b>To:</b> {ui.esc(to) or "—"} &nbsp;·&nbsp; <b>Subject:</b> {ui.esc(subj)}</div>'
                f'<div style="font-size:15.5px;line-height:1.55">{html}</div></div>', unsafe_allow_html=True)
    if not v.get("supported") and v.get("unsupported"):
        st.warning("Before sending, verify: " + " ".join(f"“{u['sentence']}” — {u.get('problem', '')}" for u in v["unsupported"][:3]))
    st.write("")
    c1, c2, c3 = st.columns(3)
    c1.download_button("⬇ Memo as Word (1 page)", make_memo_docx(m, passages, to, frm, client, d), file_name="memo_to_partner.docx",
                       type="primary", width="stretch")
    c2.download_button("✉ Open as email draft", make_eml(subj, plain, html), file_name="memo_to_partner.eml",
                       width="stretch", help="Opens in Outlook or Mail as a draft, ready to address and send.")
    if c3.button("↻ Redraft the memo", width="stretch"):
        S["ai_cache"].pop(mkey, None)
        st.rerun()
    with st.expander("Copy the email text"):
        st.code(f"Subject: {subj}\n\n{plain}", language=None, wrap_lines=True)

    st.markdown("### Full report")
    c1, c2 = st.columns(2)
    c1.download_button("Download the full report (Word)", make_report_docx(d, rows, iss["issues"], plain, passages),
                       file_name="merger_regulatory_report.docx", width="stretch")
    c2.download_button("Download the AI audit trail", json.dumps(S.get("audit", []), indent=2), file_name="ai_audit_trail.json",
                       width="stretch", help="Every AI call this session: what it was for, which passages it was given, what it said.")
    ui.chat_box(STEP, facts)
