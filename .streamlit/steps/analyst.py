"""
Stage 6 - AI analyst (tool use): the AI investigates the deal the way a senior analyst would.

  * AI decides what to test, one call at a time (up to 6): how close the deal is to every line, what would flip each
    result, what-if scenarios, and the quarter-by-quarter timeline after closing.
  * CODE runs each "tool" - the app's own calculator in engine.py - and hands the result back. The AI never does the
    arithmetic.
  * AI writes up its findings; CODE checks that every $ figure and % in the write-up traces to a calculator result
    (engine.verify_numbers).
"""

import json
import re

import streamlit as st

import ai
import deal as D
import engine as E
import ui
from state import S, fp, keep, saved
from ui import nice_name, pct

STEP = "AI analyst"
TOOL_LABEL = {"headroom": "How close is it to every line?", "break_even": "What would it take to flip each result?",
              "scenario": "What if…", "timeline": "When does it bite? Quarter by quarter"}
FOCUS_IDEAS = ["How close is this deal to the next line?", "How much of a capital hit can the combined bank take?",
               "When after closing does the new category apply?", "What if the bank being bought keeps growing?"]


def args_text(args):
    """The AI's scenario inputs in plain words, e.g. 'capital loss $5bn, target size 110%'."""
    out = []
    for k, v in (args or {}).items():
        name = k.replace("_bn", "").replace("_pct", "").replace("_", " ")
        out.append(f"{name} ${v}bn" if k.endswith("_bn") else f"{name} {v}%" if k.endswith("_pct") else f"{name} {v}")
    return ", ".join(out)


def analyst_facts(d):
    f = (f"Buyer: {nice_name(d['a']['name'])}{' (the U.S. arm of ' + saved('parent_key') + ')' if saved('canadian') else ''}, "
         f"average assets {E.bn(d['A']['avg_assets'])}, {E.cat_label(d['cat_a'][0])} today. Bank being bought: "
         f"{nice_name(d['t']['name'])}, {E.bn(d['T']['avg_assets'])}. Combined: {E.bn(d['pf_avg'])}, {E.cat_label(d['cat_c'][0])}. "
         f"Combined CET1 {pct(d['c']['cet1_ratio'])} on risk-weighted assets of {E.bn(d['c']['rwa'])}; CET1 capital "
         f"{E.bn(d['c']['cet1'])}; Tier 1 leverage {pct(d['c']['leverage_ratio'])}. Deal debt {E.bn(d['deal_debt'])}.")
    if D.closing_date():
        f += f" Expected closing {D.closing_date():%d %b %Y}."
    if saved("canadian"):
        cx = D.canadian(d)
        f += (f" Canadian buyer: combined U.S. assets {E.bn(cx['fp']['combined_after'])}; Reg K overall "
              f"{E.STATUS[cx['q']['overall']][1]}.")
    return f


def render():
    ui.header("analyst")
    if not D.ready():
        return ui.need_banks()
    d = D.deal()
    if not (d["c"]["rwa"] and d["c"]["tier1"] and d["c"]["avg_assets_lev"]):
        st.warning("The analyst needs both banks' capital figures (risk-weighted assets, Tier 1 capital and leverage assets), "
                   "and at least one filing does not report them. Choose banks whose FR Y-9C includes Schedule HC-R.")
        return
    base, timeline = D.analysis_base(d)
    ui.lede("The AI analyst investigates the deal the way a senior analyst would: it decides what to test, runs the app's "
            "calculator, reads the result and decides what to test next. It never does the arithmetic itself — and the app "
            "checks every number in its write-up.")
    pick = st.pills("Suggested focus", FOCUS_IDEAS, key="focus_pick", label_visibility="collapsed")
    focus = st.text_input("What should the analyst focus on? (optional)", value=pick or saved("focus", ""),
                          placeholder="e.g. Could a weak year push the combined bank into its buffer?")
    keep("focus", focus)
    facts = analyst_facts(d)
    key = fp("analyst", D.deal_sig(), focus)
    res = S["ai_cache"].get(key)
    c1, c2 = st.columns([1, 3])
    go = c1.button("✨ Run the investigation" if not res else "↻ Investigate again", type="primary" if not res else "secondary")
    c2.markdown(f'<div class="muted" style="padding-top:8px">Up to {ai.ANALYST_MAX_STEPS} calculator calls, chosen one at a time '
                'by the AI, then a written report.</div>', unsafe_allow_html=True)
    if go:
        if not ai.ready():
            ui.no_key_note("the investigation")
        else:
            res = run_analyst(base, timeline, facts, focus)
            if res:
                S["ai_cache"][key] = res
                S["analyst_last"] = {"deal": D.deal_key(), "report": res["report"]}
    if not res:
        st.markdown("#### What it can use")
        ui.table([{"Tool": f"<b>{TOOL_LABEL[k]}</b>", "What the app calculates": v} for k, v in E.ANALYST_TOOLS.items()],
                 ["Tool", "What the app calculates"])
        return
    nums = res["numbers"]
    st.markdown("### Findings")
    st.markdown(ui.badge(True, f"all {nums['checked']} figures trace to the app's calculations") if not nums["unverified"] else
                ui.badge(None, f"{len(nums['unverified'])} of {nums['checked']} figures could not be traced: "
                               + ", ".join(nums["unverified"][:4]) + " — treat with care"), unsafe_allow_html=True)
    ui.show_ai({"text": res["report"]}, "the analyst's findings", "analyst")
    st.markdown("### How the analyst got there")
    for i, h in enumerate(res["history"], 1):
        with st.container(border=True):
            args = args_text(h["args"])
            st.markdown(f"<b>{i} · {TOOL_LABEL.get(h['tool'], ui.esc(h['tool']))}</b>{' — ' + ui.esc(args) if args else ''}<br>"
                        f"<span class='ai-tag'>✨ AI's reason</span> <span class='muted'>{ui.esc(h['why'])}</span>",
                        unsafe_allow_html=True)
            r = h["result"]
            with st.expander("Result calculated by the app"):
                if isinstance(r, dict) and "rows" in r:
                    st.markdown(f"**{r.get('summary', '')}**")
                    ui.table([{"Quarter-end": x["quarter_end"], "Quarters after closing": x["quarters_since_closing"],
                               "Four-quarter average": x["four_quarter_average"], "Category": x["category"]} for x in r["rows"]],
                             ["Quarter-end", "Quarters after closing", "Four-quarter average", "Category"])
                    st.caption(r["note"])
                elif isinstance(r, dict):
                    flat = []
                    for k, v in r.items():
                        if isinstance(v, dict):
                            flat += [(k2.replace("_", " ").capitalize(), v2) for k2, v2 in v.items()]
                        else:
                            flat.append((k.replace("_", " ").capitalize(), ", ".join(map(str, v)) if isinstance(v, list) else v))
                    ui.table([{"Measure": k, "Result": v} for k, v in flat], ["Measure", "Result"])


def run_analyst(base, timeline, facts, focus):
    tools_doc = "\n".join(f"- {k}: {v}" for k, v in E.ANALYST_TOOLS.items())
    history, seen = [], set()
    try:
        with st.status("The AI analyst is investigating…", expanded=True) as status:
            for n in range(ai.ANALYST_MAX_STEPS):
                status.update(label=f"The AI analyst is choosing call {n + 1}…")
                dec = ai.analyst_next(STEP, facts, tools_doc, history, focus, n)
                if dec.get("done") and n >= ai.ANALYST_MIN_STEPS:
                    break
                tool = str(dec.get("tool", ""))
                args = dec.get("args") if isinstance(dec.get("args"), dict) else {}
                sig = json.dumps([tool, args], sort_keys=True, default=str)
                if tool not in E.ANALYST_TOOLS:
                    result = {"error": f"There is no tool called '{tool}'. Use one of: {', '.join(E.ANALYST_TOOLS)}."}
                elif sig in seen:
                    result = {"note": "Already run with these arguments - choose something new."}
                else:
                    try:
                        result = E.run_tool(tool, args, base, timeline)
                    except Exception as exc:           # a calculator error goes back to the AI, not to the screen
                        result = {"error": f"The calculator could not run this ({exc.__class__.__name__}). Try other arguments."}
                seen.add(sig)
                history.append({"tool": tool, "args": args, "why": str(dec.get("why", "")), "result": result})
                shown = args_text(args)
                status.write(f"**{n + 1} · {TOOL_LABEL.get(tool, tool)}**{' (' + shown + ')' if shown else ''} — {dec.get('why', '')}")
            status.update(label="The AI analyst is writing up its findings…")
            report = ai.analyst_report(STEP, facts, history, focus)
            report = re.sub(r"\s*\n(\*\*[^*\n]+\*\*)", r"\n\n\1", report).strip()     # each heading on its own line
            inputs = " ".join(f"${v}bn" if k.endswith("_bn") else f"{v}%" for h in history for k, v in (h["args"] or {}).items())
            inputs += " " + " ".join(h["why"] for h in history)      # the AI's own scenario design (inputs, not results)
            nums = E.verify_numbers(report, facts + " " + inputs + " " + json.dumps([h["result"] for h in history], default=str))
            status.update(label=f"Investigation complete — {len(history)} calculator calls", state="complete", expanded=False)
        return {"history": history, "report": report, "numbers": nums}
    except Exception as exc:
        st.error("The investigation did not finish: " + ai.friendly_error(exc))
        return None
