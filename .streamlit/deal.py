"""
deal.py - the deal on screen: which two banks, the combined bank, and every result the later steps show.

Everything here is CODE (no AI): it loads the banks' FR Y-9C filings, works out the combined bank, the size
categories, and the results rows that the pages, the issues list and the memo all share. The rules themselves live
in engine.py; this file only puts the user's choices and the rules together.
"""

import datetime
import json
import os

import streamlit as st

import engine as E
import state
from state import S, keep, saved
from ui import nice_name, pct

HERE = os.path.dirname(os.path.abspath(__file__))
TEST = os.path.join(HERE, "test_data")

# The FR Y-9C reports of the Canadian banks' U.S. holding companies (built into the app).
US_ARM_FILES = {"TD": ["TD_US_FRY9C_2026Q1.pdf", "TD_US_FRY9C_2026Q2.pdf"], "BMO": ["BMO_US_FRY9C_2026Q2.pdf"],
                "RBC": ["RBC_US_FRY9C_2026Q2.pdf"], "CIBC": ["CIBC_US_FRY9C_2026Q2.pdf"]}
# Example Pillar 3 / capital disclosures of the Canadian parents.
PILLAR3 = {"RBC": ("RBC_Pillar3_Q3_2026.pdf", "RBC Pillar 3 report (Q3 2026)"),
           "BMO": ("BMO_RegCapital_Q3_2026.pdf", "BMO capital disclosure (Q3 2026)"),
           "TD": ("TD_RegDisclosure_Q3_2023.pdf", "TD disclosure (Q3 2023 — older layout)")}
EXAMPLE_POOL = "EXAMPLE_BANKS_2026Q2.txt"            # fictional banks sized just under the category lines
REGISTER_EXAMPLE = "ILLUSTRATIVE_holdings_register.csv"

with open(os.path.join(HERE, "library", "us_structure.json"), encoding="utf-8") as _fh:
    STRUCTURE = json.load(_fh)     # each Canadian bank's U.S. footprint, from the Fed's ownership data (tools/build_structure.py)
CANADIAN = list(STRUCTURE)         # TD, RBC, BMO, CIBC

EXAMPLE_DEALS = {
    "U.S. deal that crosses $100bn — Great Lakes Financial buys Prairie Trust": ("us", "GREAT LAKES", "PRAIRIE TRUST"),
    "U.S. deal that crosses $250bn — Sun Belt Bancshares buys Atlantic Harbor": ("us", "SUN BELT", "ATLANTIC HARBOR"),
    "U.S. deal that crosses $700bn — Pacific Crest Financial buys Cascade Bancorp": ("us", "PACIFIC CREST", "CASCADE"),
    "Canadian buyer — RBC buys Liberty Square (Category IV → III)": ("ca", "RBC", "LIBERTY SQUARE"),
    "Canadian buyer — CIBC buys Great Lakes Financial (U.S. presence crosses $100bn)": ("ca", "CIBC", "GREAT LAKES"),
    "Canadian buyer — TD buys Keystone National (Category II, and fails Reg K)": ("ca", "TD", "KEYSTONE"),
}


# --------------------------------------------------------------------------------------
# Loading banks
# --------------------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def parse_one(name, data):
    """Read one FR Y-9C file (the Fed's PDF form, or its bulk .txt file). Cached, so re-runs are instant."""
    return E.parse_y9c_pdf(data) if name.lower().endswith(".pdf") else E.parse_y9c_bulk(data)


def read_test(name):
    with open(os.path.join(TEST, name), "rb") as fh:
        return fh.read()


def rebuild_banks():
    """All banks the app knows about: the fictional example banks, the Canadian banks' U.S. arms, and whatever was
    uploaded for the buyer and for the bank being bought."""
    parsed, skipped = [], []
    files = [(EXAMPLE_POOL, read_test(EXAMPLE_POOL))] + [(n, read_test(n)) for v in US_ARM_FILES.values() for n in v]
    for slot in ("acq", "tgt"):
        files += list(S.get(f"files_{slot}", {}).items())
    for name, data in files:
        try:
            q, banks = parse_one(name, data)
        except Exception:            # a damaged or unrelated file: skip it and say so
            q, banks = None, {}
        if banks:
            parsed.append((q, banks))
        else:
            skipped.append(name)
    S["banks"] = E.merge_quarters(parsed)
    S["skipped"] = skipped


def ensure_banks():
    if "banks" not in S:
        rebuild_banks()


def ihc_rssd(pk):
    return STRUCTURE[pk]["ihcs"][0]["rssd"] if STRUCTURE[pk]["ihcs"] else None


def example_rssds():
    return list(parse_one(EXAMPLE_POOL, read_test(EXAMPLE_POOL))[1])


def by_name(fragment):
    return next((k for k, v in S["banks"].items() if fragment in v["latest"]["name"]), None)


def reset_parent():
    """Forget everything that belongs to one Canadian parent (its Pillar 3 figures, holdings register and review)."""
    S["parent"], S["disposal"], S["register"] = None, None, None
    S["saved"].pop("parent_src", None)


def load_example_deal(label):
    """Called when an example deal is chosen. It also sets the bank pickers on Getting started, so they show the
    example's banks instead of what was picked before."""
    kind, buyer, target = EXAMPLE_DEALS[label]
    S["files_acq"], S["files_tgt"] = {}, {}
    reset_parent()
    rebuild_banks()
    example = "Choose an example bank"
    keep("tgt", by_name(target))
    keep("tgt_source", example)
    S["src_tgt"], S[f"pick_tgt_{example}"] = example, saved("tgt")          # the pickers on Getting started
    if kind == "ca":
        keep("canadian", True)
        keep("parent_key", buyer)
        keep("acq", ihc_rssd(buyer))
        S["parent_pick"] = buyer
        if buyer in PILLAR3:
            S["pending_pillar3"] = PILLAR3[buyer][0]
    else:
        keep("canadian", False)
        keep("acq", by_name(buyer))
        keep("acq_source", example)
        S["src_acq"], S[f"pick_acq_{example}"] = example, saved("acq")


# --------------------------------------------------------------------------------------
# The deal (everything the later steps need)
# --------------------------------------------------------------------------------------
def ready():
    """Have two different banks been chosen?"""
    B = S.get("banks") or {}
    return bool(B and saved("acq") in B and saved("tgt") in B and saved("acq") != saved("tgt"))


def deal():
    B = S["banks"]
    A, T = B[saved("acq")], B[saved("tgt")]
    a, t = A["latest"], T["latest"]
    c = E.combine(a, t)
    gsib = saved("gsib", False) and not saved("canadian")
    cat_a, cat_t = E.category(A["avg_assets"], gsib), E.category(T["avg_assets"])
    pf_avg = A["avg_assets"] + T["avg_assets"]
    cat_c = E.category(pf_avg, gsib)
    quarters = sorted({b["quarter"] for X in (A, T) for b in X["history"] if b["quarter"]})
    debt = saved("deal_debt_bn", 0.0) * 1e6
    return dict(A=A, T=T, a=a, t=t, c=c, cat_a=cat_a, cat_t=cat_t, cat_c=cat_c, pf_avg=pf_avg, gsib=gsib,
                liab=E.liabilities_test(c["total_liabilities"] + debt), deal_debt=debt,
                quarters=[state.nice_date(q) for q in quarters], min_q=min(A["quarters"], T["quarters"]))


def closing_date():
    try:
        return datetime.date.fromisoformat(saved("closing"))
    except (TypeError, ValueError):
        return None


def deal_key():
    """Which deal is on screen (results that belong to another deal are not shown)."""
    return state.fp(saved("acq"), saved("tgt"), saved("canadian"), saved("parent_key"))


def deal_sig():
    """Everything that changes the analyst's facts - so a changed input means a fresh investigation."""
    return [saved("acq"), saved("tgt"), saved("canadian"), saved("parent_key"), saved("gsib"), saved("deal_debt_bn"),
            saved("branches_bn"), saved("us_rev_share"), saved("us_ni_share"), saved("mostly_banking"), saved("closing"),
            saved("fx"), bool(S.get("parent"))]


# --------------------------------------------------------------------------------------
# A Canadian buyer
# --------------------------------------------------------------------------------------
def parent_values():
    P = S.get("parent")
    return {k: P["fig"][k]["value"] for k in P["fig"]} if P else {}


def disposal_current():
    """The holdings review for the deal on screen, if it has been run."""
    res = S.get("disposal")
    return res if res and res.get("deal") == deal_key() else None


def canadian(d):
    """Everything the Canadian-buyer analysis needs. Pure calls to engine.py - no AI here."""
    pk = saved("parent_key")
    G = STRUCTURE[pk]
    v = parent_values()
    fx = saved("fx", 1.40)
    branches = saved("branches_bn", 0.0) * 1e6
    fp_ = E.us_footprint(d["a"]["total_assets"], branches, d["t"]["total_assets"])
    us_rows, (ihc_before, ihc_after) = E.us_rules_for_foreign_buyer(fp_)
    parent_total_usd = (v["total_assets"] * 1e3 / fx + d["t"]["total_assets"]) if v.get("total_assets") else None
    q = E.qfbo_test(parent_total_usd, fp_["combined_after"], saved("us_rev_share"), saved("us_ni_share"),
                    {"Yes": True, "No": False}.get(saved("mostly_banking", "Yes")))
    regk_rows = [
        {"status": q["test1"], "check": "Reg K test 1 — more than half its worldwide business is banking",
         "detail": "Confirmed by the user." if q["test1"] == "met" else "Not confirmed.", "src": "12 CFR 211.23(a)(1)"},
        {"status": q["test2"], "check": "Reg K test 2 — more than half its banking is outside the U.S. (after the deal)",
         "detail": "; ".join(f"{l['measure']}: {l['detail']}" for l in q["legs"]), "src": "12 CFR 211.23(a)(2)"}]
    if q["overall"] == "not_met":
        regk_rows.append({"status": "not_met", "check": "Reg K exemptions for its businesses outside the U.S.",
                          "detail": "If it fails for two years in a row, the exemptions end; anything acquired after the first "
                                    "failing year must be sold or wound down within three months, unless the Fed agrees otherwise.",
                          "src": "12 CFR 211.23(d)"})
    hold_rows = []
    disp = disposal_current()
    if disp:
        n = {k: sum(1 for r in disp["rows"] if r["verdict"] == k) for k in E.VERDICTS}
        status = "not_met" if n["sell"] else ("review" if n["at_risk"] or n["approval"] else "met")
        detail = (f"Of {len(disp['rows'])} holdings reviewed: {n['sell']} likely must sell or restructure; {n['at_risk']} at risk "
                  f"if Reg K status is lost; {n['approval']} need Fed approval or notice.")
    else:
        status = "not_met" if q["overall"] == "not_met" else "review"
        detail = ("Not reviewed yet. Because it fails the Reg K tests, its non-banking holdings outside the U.S. are at risk — "
                  "run the holdings review on the Canadian buyer page." if q["overall"] == "not_met" else
                  "Not reviewed yet — run the holdings review on the Canadian buyer page.")
    hold_rows.append({"status": status, "check": "Holdings the parent may have to sell (AI review, checked by the app)",
                      "detail": detail, "src": "12 CFR 211.23; 12 CFR 225.28, 225.86"})
    hold_rows.append({"status": "review" if G["outside_ihc"] else "met", "check": "U.S. companies held outside the IHC",
                      "detail": (", ".join(nice_name(x["name"]) for x in G["outside_ihc"][:3])
                                 + " — confirm an exception applies or move under the IHC.")
                      if G["outside_ihc"] else "None — every U.S. company is under the IHC.", "src": "12 CFR 252.153"})
    osfi_rows = []
    if v.get("cet1") and v.get("rwa"):
        to_cad = lambda usd_k: usd_k / 1e3 * fx           # thousands of US$ -> millions of C$
        parent = {k: v.get(k) for k in ("cet1", "tier1", "total_capital", "rwa", "leverage_exposure")}
        for r in E.parent_tests(parent, to_cad(d["t"]["rwa"] or 0), to_cad(d["t"]["total_assets"] or 0),
                                saved("dsib", True), saved("dsb", 3.0)):
            osfi_rows.append({"status": r["status"], "check": f"Parent's {r['test']} (OSFI)",
                              "detail": f"{pct(r['before'])} → {pct(r['after'])} vs target {r['target']:.2f}%", "src": r["cite"]})
    else:
        osfi_rows.append({"status": "unknown", "check": "Parent's capital ratios (OSFI)",
                          "detail": "Load the parent's Pillar 3 report on Getting started.", "src": "OSFI CAR (2027) Ch.1"})
    return dict(pk=pk, G=G, v=v, fp=fp_, us_rows=us_rows, ihc_before=ihc_before, ihc_after=ihc_after, q=q,
                regk_rows=regk_rows, hold_rows=hold_rows, osfi_rows=osfi_rows, parent_total_usd=parent_total_usd,
                rows=us_rows + regk_rows + hold_rows + osfi_rows)


def two_ways_out(q):
    """One line framing the real choice, from numbers the app already has (no AI)."""
    h = q.get("headroom")
    if q["overall"] == "not_met" and q["test2"] == "not_met" and h is not None and h < 0:
        return ("not_met", f"<b>Two ways out.</b> Keep Reg K status by shedding more than <b>{E.bn(-h)}</b> of U.S. banking assets "
                           "(the assets measure; revenue and income move with it until real figures are entered) — or let Reg K "
                           "status go, and in time sell or wind down the non-banking holdings abroad that depend on it, reviewed below.")
    if q["overall"] == "not_met":
        return ("not_met", "<b>It fails a Reg K test</b>, so the holdings that depend on Reg K status are at risk — reviewed below.")
    if q["overall"] == "met" and h is not None:
        return ("met", f"<b>Reg K is met</b>, with room for {E.bn(h)} more U.S. banking assets. The review below checks each "
                       "holding's own conditions.")
    return ("unknown", "<b>Reg K status can't be confirmed yet</b> — load the parent's Pillar 3 report on Getting started. The "
                       "review below still shows what depends on it.")


# --------------------------------------------------------------------------------------
# The AI's reading of the rules (Stage 2) - its facts, and the comparison with the rulebook
# --------------------------------------------------------------------------------------
def rule_facts(d):
    who = ("the U.S. intermediate holding company of a Canadian bank. It is itself a top-tier bank holding company domiciled in "
           "the United States, and it is not a consolidated subsidiary of any other U.S. bank holding company or savings and loan "
           "holding company" if saved("canadian") else
           "a top-tier U.S. bank holding company domiciled in the United States, not a consolidated subsidiary of any other bank "
           "holding company or savings and loan holding company")
    facts = (f"Entity: {who}. Average total consolidated assets: {E.bn(d['A']['avg_assets'])} before the deal, "
             f"{E.bn(d['pf_avg'])} after it (the two banks added together). It is {'' if d['gsib'] else 'not '}a U.S. GSIB. "
             "Cross-jurisdictional activity, total nonbank assets, weighted short-term wholesale funding and off-balance-sheet "
             "exposure are NOT available to the app.")
    return facts, state.fp("rules", facts)


def rule_cmp(d, rules=None):
    rules = rules or S["ai_cache"].get(rule_facts(d)[1])
    return E.compare_rule_reading(rules, d["cat_a"][0], d["cat_c"][0]) if rules else None


# --------------------------------------------------------------------------------------
# The results rows shared by At a glance, the issues list and the memo
# --------------------------------------------------------------------------------------
def summary_rows(d):
    rows = []
    before, after = d["cat_a"][0], d["cat_c"][0]
    rows.append({"status": "newly_applies" if E.rank(after) > E.rank(before) else "met",
                 "check": "Size category of the combined U.S. bank",
                 "detail": f"{E.cat_label(before)} → {E.cat_label(after)} (combined {E.bn(d['pf_avg'])})", "src": E.CATEGORY_CITE})
    for r in E.newly_applying(before, after):
        rows.append({"status": "newly_applies", "check": r["Requirement"], "detail": f"{r['Before']} → {r['After']}",
                     "src": r["Source"]})
    for r in E.capital_tests(d["c"]) + E.leverage_tests(d["c"], after):
        rows.append({"status": r["status"], "check": f"{r['test']} (combined)",
                     "detail": f"{pct(r['value'])} vs {r['with_buffer']:.1f}% needed" if r["value"] is not None else
                     "Not reported by both banks — can't combine", "src": r["cite"]})
    rows.append({"status": d["liab"]["status"], "check": "10% liabilities concentration limit", "detail": d["liab"]["detail"],
                 "src": "12 U.S.C. 1852(b); 12 CFR 251"})
    if saved("canadian"):
        cx = canadian(d)
        rows += ([r for r in cx["us_rows"] if not r["check"].startswith("The IHC's own")]
                 + cx["regk_rows"] + cx["hold_rows"] + cx["osfi_rows"])
    cmp_ = rule_cmp(d)
    if cmp_:
        rows.append({"status": "met" if cmp_["differ"] == 0 else "review", "check": "AI's reading of the rules vs the built-in rulebook",
                     "detail": f"Agree on {cmp_['agree']} of {cmp_['total']} points"
                               + (f"; {cmp_['differ']} to review" if cmp_["differ"] else ""),
                     "src": "12 CFR 252.5; 217.10–11; 225.8; 252.44; Part 249"})
    if d["min_q"] < 4:
        rows.append({"status": "unknown", "check": "Four-quarter average size",
                     "detail": f"Only {d['min_q']} quarter(s) loaded for at least one bank; size uses what is available.",
                     "src": "12 CFR 252.5"})
    return rows


def facts_text(rows):
    return "\n".join(f"- {E.STATUS[r['status']][1]} | {r['check']} | {r['detail']}" for r in rows)


# --------------------------------------------------------------------------------------
# The combined bank as plain numbers, for the AI analyst's calculator (Stage 6)
# --------------------------------------------------------------------------------------
def quarter_ends_after(day, n=6):
    """The n calendar quarter-ends on or after a date (the first one includes the combined balance sheet)."""
    out, y, m = [], day.year, ((day.month - 1) // 3 + 1) * 3
    while len(out) < n:
        last = datetime.date(y + (m // 12), m % 12 + 1, 1) - datetime.timedelta(days=1)
        if last >= day:
            out.append(last)
        m += 3
        if m > 12:
            m, y = m - 12, y + 1
    return out


def analysis_base(d):
    """Returns (base, timeline inputs): the combined bank in thousands of US$, with each bank's own contribution."""
    c = d["c"]
    base = dict(avg_assets=d["pf_avg"], total_assets=c["total_assets"], rwa=c["rwa"], cet1=c["cet1"], tier1=c["tier1"],
                total_capital=c["total_capital"], lev_assets=c["avg_assets_lev"],
                slr_exposure=c["tier1"] / (c["slr"] / 100) if c.get("slr") else None,
                liabilities=c["total_liabilities"] + d["deal_debt"], gsib=d["gsib"])
    if saved("canadian"):
        cx = canadian(d)
        base.update(us_combined=cx["fp"]["combined_after"], parent_total=cx["parent_total_usd"],
                    us_rev_share=saved("us_rev_share"), us_ni_share=saved("us_ni_share"),
                    mostly_banking={"Yes": True, "No": False}.get(saved("mostly_banking", "Yes")))
    part = lambda b, avg: {"avg_assets": avg, "total_assets": b["total_assets"] or 0, "lev_assets": b["avg_assets_lev"] or 0,
                           "liabilities": b["total_liabilities"] or 0, "rwa": b["rwa"] or 0, "cet1": b["cet1"] or 0,
                           "tier1": b["tier1"] or 0, "total_capital": b["total_capital"] or 0}
    base.update(buyer=part(d["a"], d["A"]["avg_assets"]), target=part(d["t"], d["T"]["avg_assets"]), buyer_cat=d["cat_a"][0])
    day = closing_date() or datetime.date.today()
    labels = [q.strftime("%d %b %Y") for q in quarter_ends_after(day)]
    timeline = ([b["total_assets"] for b in d["A"]["history"]], [b["total_assets"] for b in d["T"]["history"]], labels)
    return base, timeline
