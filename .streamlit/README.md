# Bank Merger Regulatory Check

An AI-powered Streamlit app for a banking M&A lawyer. For a proposed merger (two U.S. banks, or a Canadian bank buying a U.S. bank) it works out:
- which U.S. capital rules each bank meets;
- what the merger changes;
- for a Canadian buyer, what U.S. regulation it takes on and what it may have to sell.

It ends in a ranked issues list and a one-page memo to the partner.

**Deployed app:** _add the Streamlit Cloud URL here_

To use it, paste your own OpenAI API key into the box at the top of the left-hand panel. The key is used only while the browser tab is open; it is never saved.

---

## How I built it — stage by stage

_Each stage is one step of the workflow (one tab in the app). For each I record what it does, what the AI does, what the code checks, the class technique it uses, and the decisions I made._

### Stage 0 — Foundations
_Draft: rewrite in your own words._

**What it does.** Home page; the OpenAI API key box in the left-hand panel; the regulation library the AI is allowed to use.

**The design rule: "AI analyses, code checks".**
- Every threshold, ratio and test is written into the code (`engine.py`, from Stage 1), with its citation. The numbers are never left to the AI.
- The AI reads, applies, investigates and drafts, and the code checks what it produces.

**The closed world.** The AI never browses the web. It is only ever shown passages from the app's own library (`library/chunks.json`):
- **14 regulations in 1,164 passages:**
  - 12 CFR Parts 211, 217, 225, 249, 251 and 252;
  - 12 U.S.C. 1828, 1842 and 1852;
  - OSFI's capital and leverage guidelines;
  - the Bank Act;
  - the Fed's March 2026 capital proposals.
- **How the passages were cut:** one per CFR section (long sections split into parts), or two pages at a time for the other documents (`tools/build_library.py`).

**How the AI finds the right passages (retrieval).**
- Every passage was turned into a vector once, with OpenAI's **text-embedding-3-large** (`tools/build_embeddings.py`; about US$0.11).
- A question is turned into a vector the same way, and the app picks the passages closest in meaning (cosine similarity, plain arithmetic).
- When the app already knows which section defines something (e.g. 12 CFR 252.5 for the size categories), it fetches that section directly.

**What the code checks.**
- The search index carries a fingerprint of the library and the model that built it. If they don't match, the app refuses the stale index and falls back to keyword search, and says so.
- The key box asks OpenAI once whether the key works, and reports a plain-English error if not (wrong key, no credit, no connection).

**Models.** gpt-4o-mini for all reading and writing (cheap enough that a full run costs a few cents); text-embedding-3-large for search (better retrieval than the small model).

**Technique.** Retrieval-augmented generation (RAG) over a closed evidence base. _(Add which class covered this.)_

**Decisions and problems.**
- The API key lives in the browser session only (the left-hand box), not in the code or on GitHub.
- While testing, I found the PDF layout had filed the definition of Category IV (12 CFR 252.5(e)) under 12 CFR 252.11. I corrected it in the build tool, so the AI cites the right section.

### Stage 1 — Getting started
_To come._

### Stage 2 — At a glance
_To come._

### Stage 3 — Questions about the regulations
_To come._

### Stage 4 — Capital ratios
_To come._

### Stage 5 — Leverage & liabilities
_To come._

### Stage 6 — Canadian buyer
_To come._

### Stage 7 — AI analyst
_To come._

### Stage 8 — Summary & next steps
_To come._

---

## Test cases
_To come: three test cases, with the files they use in `test_data/`._

## Run it yourself
```
pip install -r requirements.txt
python3 -m streamlit run app.py
```
Then paste an OpenAI API key into the left-hand panel.

## Files
| File | What it is |
|---|---|
| `app.py` | Sets up the page and shows the step you are on |
| `ui.py` | The look, the left-hand panel (API key box and steps), shared display pieces |
| `state.py` | What the app remembers between clicks |
| `ai.py` | Every call to OpenAI |
| `library.py` | The regulation library and its search |
| `steps/` | One file per step of the workflow |
| `library/` | The library's passages and search index |
| `tools/` | One-off build scripts (not run by the app) |

_Screening tool, not legal advice._
