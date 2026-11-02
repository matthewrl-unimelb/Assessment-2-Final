# Bank Merger Regulatory Check

An AI-powered Streamlit app for a banking M&A lawyer. Pick a proposed bank merger: either two U.S. banks, or a Canadian bank (TD, RBC, BMO or CIBC) buying a U.S. bank. The app then works out:
- which U.S. capital rules each bank meets, and what the merger changes;
- for a Canadian buyer, what U.S. regulation it takes on, whether it can keep its businesses outside the U.S. under Regulation K, and which of its holdings it may have to sell.

It ends in a ranked issues list and a one-page memo to the partner, ready to email.

**Deployed app:** _add the Streamlit Cloud URL here_

**To use it:** paste your own OpenAI API key into the box at the top of the left-hand panel. The key is used only while the browser tab is open; it is never saved. Everything that isn't AI (the numbers, the rules, the results) also works without a key.

---

## The legal task, in steps

_Draft text below: rewrite in your own words._

The task is a **regulatory screen of a bank merger**: what a deal lawyer checks first, before the detailed work starts. It breaks into seven steps, one per tab of the app:

| Step | Question it answers |
|---|---|
| 1. Getting started | Who are the two banks, and what do their Fed filings say? |
| 2. At a glance | Which size category is the combined bank in, and what newly applies? |
| 3. Capital ratios | Do the buyer, the target and the combined bank meet the risk-based capital minimums and buffers? |
| 4. Leverage & liabilities | Do they meet the leverage ratios, and the 10% cap on a firm's share of the financial sector's liabilities? |
| 5. Canadian buyer | _(Canadian buyers only)_ Which U.S. rules does the Canadian bank take on? Does it still qualify under Reg K? Which holdings may it have to sell? |
| 6. AI analyst | How close is the deal to each line, what could tip it over, and when does it bite? |
| 7. Summary & next steps | What are the issues, ranked, and what does the partner need to know? |

**The design rule: "AI analyses, code checks."**
- Every threshold, ratio and test is written into the code (`engine.py`), with its citation beside it. The numbers are never left to the AI, so the same deal always gets the same results.
- The AI does the reading, applying, investigating and drafting:
  - it reads the filings;
  - it applies the regulations from their text;
  - it reviews each holding;
  - it runs the analysis;
  - it drafts the issues list and the memo.
- The code checks everything the AI produces:
  - every figure against the filing;
  - every rule against the built-in rulebook;
  - every citation against the library;
  - every number in the analyst's write-up and the memo against the app's own results.

---

## How I built it — stage by stage

_Each stage is one tab of the app. For each one I record what it does, what the AI does, what the code checks, the class technique it uses, and the decisions and problems along the way. Draft text: rewrite in your own words._

### Stage 0 — Foundations
**What it does.** The Home page; the OpenAI API key box in the left-hand panel; the regulation library the AI is allowed to use.

**The closed world.** The AI never browses the web. It only ever sees passages from the app's own library (`library/chunks.json`): **14 regulations in 1,164 passages.**
- 12 CFR Parts 211 (Regulation K), 217 (Regulation Q, capital), 225 (Regulation Y), 249 (liquidity), 251 (concentration limit) and 252 (Regulation YY);
- 12 U.S.C. 1828, 1842 and 1852;
- OSFI's Capital Adequacy Requirements (2027) and Leverage Requirements guidelines;
- the Bank Act (Canada), Parts IX–X;
- the Fed's March 2026 capital proposals (marked "proposed, not in force").

The passages were cut once by `tools/build_library.py`: one per CFR section (long sections split into parts), or two pages at a time for the other documents.

**How the AI finds the right passages (retrieval).**
- **The index.** Every passage was turned into a vector once, with OpenAI's **text-embedding-3-large** (`tools/build_embeddings.py`, about US$0.11).
- **Searching.** A question is turned into a vector the same way, and the app picks the passages closest in meaning (cosine similarity, which is plain arithmetic).
- **Fetching a known section.** When the app already knows which section defines something (for example 12 CFR 252.5 for the size categories), it fetches that section directly.
- **The relevance floor.** If nothing in the library is close enough to the question, the AI is not called at all.

**What the code checks.**
- **The index matches the library.** The search index carries a fingerprint of the library and the model that built it. If they don't match, the app refuses the stale index, falls back to keyword search (BM25), and says so on the Home page.
- **The key works.** The key box asks OpenAI once whether the key works. If it doesn't, the box shows a plain-English reason (wrong key, no credit, no connection).

**Models.**
- **gpt-4o-mini** does all the reading and writing. A full run costs a few cents, and the left-hand panel shows a running estimate.
- **text-embedding-3-large** does the search.

**Technique.** Lab 2: an evidence database with retrieval (RAG).

**Decisions and problems.**
- **OpenAI only, with the key in the front end.** The key is typed into the left-hand panel and held in the browser session only. It is never in the code, in a file or on GitHub.
- **A misfiled section.** While testing, I found the PDF layout had filed the definition of Category IV (12 CFR 252.5(e)) under 12 CFR 252.11. The AI then cited the wrong section, so I corrected it in the build tool.

### Stage 1 — Getting started
**What it does.** You choose the two banks in one of three ways:
- upload each bank's **FR Y-9C** (the Fed's PDF, or its bulk .txt file);
- pick a fictional example bank;
- load a ready-made example deal.

For a Canadian buyer, you pick TD, RBC, BMO or CIBC (its U.S. arm's FR Y-9C is built in), plus its **Pillar 3** capital report. You also enter the expected closing date.

**What the AI does.**
- **It reads both filings line by line** and finds 21 figures (total assets, deposits, AOCI, goodwill, CET1, risk-weighted assets, the reported ratios…) by their meaning, the way an analyst would.
- **It writes an analyst's review of each bank**, for example:
  - an unrealised securities loss that is large against CET1;
  - heavy goodwill;
  - balance-sheet lines a holding company may not be allowed to keep.
- **For a Canadian buyer, it reads the key-metrics table in the Pillar 3 report.**

**What the code checks.**
- **The filing figures.** Every figure the AI read is compared with the exact value filed under its Fed code (MDRM). The AI's figures must also reproduce the ratios the bank reported.
- **The re-read.** Anything that doesn't match goes back to the AI to read again, without being told the answer. Wherever the AI and the filing still disagree, the app uses the filed value.
- **The Pillar 3 pages.** Code finds the right 2–4 pages of the report before the AI reads them.
- **The Pillar 3 figures.** The AI's figures must reproduce the bank's own reported CET1 and leverage ratios.

**Technique.** Self-correction (a loop): the code checks the reading, and the AI re-reads what failed. The filing reads for both banks run at the same time.

**Decisions and problems.**
- **Why the AI reads the whole filing.** The app could read the figures from the Fed codes alone. Instead, the AI reads the filing as a person would, and the codes become the answer key that checks it.
- **Why there are example banks.** The real banks in the test data don't cross the category lines, so I built fictional banks sized just below each line (`tools/make_example_banks.py`). Their filings are complete and internally consistent.

### Stage 2 — At a glance
**What it does.** Every result in one table:
- the size category before and after the deal;
- what newly applies;
- capital, leverage and liabilities;
- for a Canadian buyer, the U.S. rules, Reg K and OSFI.

Each result carries its citation.

**What the AI does.**
- **It writes a short headline** from the library passages.
- **It applies the rules from the regulation text itself, in two rounds:**
  - first, the size category and whether the bank is an "advanced approaches" bank (12 CFR 252.5, 217.2, 217.100);
  - then the seven requirements (capital plan, stress capital buffer, stress test, supplementary leverage ratio, countercyclical buffer, AOCI, LCR/NSFR). For each, it quotes who the rule covers and tests the bank against it.
- **It lists the other ways the bank could land in a higher category** (cross-jurisdictional activity, wholesale funding…). The app has no figures for these, so they become questions for the client.

**What the code checks.**
- **The vote.** Each round runs as **three independent readings at the same time**, and the app takes the majority answer on each point.
- **The rulebook comparison.** The AI's answers are compared, point by point, with the rulebook built into the app (for example "agree on 9 of 9 points"). The page shows how many of the three readings agreed on each point.
- **The question box.** From this stage on, every page has a question box (`ai.ask`) that works in a loop:
  1. it searches the library;
  2. the AI answers;
  3. **a second AI call checks every sentence against the passages it cites**;
  4. if the check fails, the app searches again with better words and retries.

  Off-topic questions ("Who won the World Series?") are declined.

**Technique.**
- Lab 1: if-then rules (the rulebook).
- Lab 2: RAG with looping and reflection (the question box).
- Beyond the labs: chain of thought in JSON (the AI writes its reasoning before its answer) and self-consistency (three votes).

**Decisions and problems.**
- **The AI contradicted itself.** Asked everything in one call, it sometimes put the bank in Category III and then said a Category II-only rule applied. I split the reading into two rounds. The second round is told the settled facts from the first, plus "a rule that covers 'X or Y' covers the bank if either is true".
- **The answers varied from run to run.** I added the three-reading vote.
- **Long answers were cut off.** I added a retry with more room (`ai.json_call`).

### Stage 3 — Capital ratios
**What it does.** The three risk-based ratios (CET1, Tier 1, Total capital) for the buyer, the target and the combined bank, against:
- the minimums in 12 CFR 217.10(a);
- the 2.5% buffer in 217.11(a).

It also shows a table of what each size category must hold, and where each figure comes from in the FR Y-9C.

**What the AI does.**
- A short "what this means" for this deal.
- On request, a plain-English guide to each ratio, built from the exact sections that define each term (`ai.explain_multi`).

**What the code checks.** Every ratio and every met / not met. Each bank's reported ratios are recomputed from their parts.

**Technique.** Lab 1: if-then rules. Lab 2: RAG.

### Stage 4 — Leverage & liabilities
**What it does.**
- **The Tier 1 leverage ratio** of 4% (12 CFR 217.10(a)(1)(iv)).
- **The supplementary leverage ratio** of 3%, which applies from Category III (217.10(a)(1)(v)).
- **The 10% liabilities cap.** No merger may leave the firm with more than 10% of the financial sector's liabilities (12 U.S.C. 1852(b); 12 CFR 251). You can enter the debt raised to pay for the deal, and it counts toward the limit.

**What the AI does.** "What this means", plus an optional plain-English guide.

**What the code checks.** Every ratio and the share of the liabilities limit.

**Technique.** Lab 1: if-then rules. Lab 2: RAG.

### Stage 5 — Canadian buyer _(only when the buyer is a Canadian bank)_
**What it does.**
- **A. Its U.S. presence before and after the deal**, from its U.S. arm's FR Y-9C and the Fed's ownership records (`tools/build_structure.py`).
- **B. The U.S. rules it becomes subject to:** the intermediate holding company (12 CFR 252.153), and Subpart O of Regulation YY for foreign banks with $100bn or more of combined U.S. assets.
- **C. The Reg K tests** (12 CFR 211.23(a)). A foreign bank may run any business outside the U.S. only while it is "mostly a bank" and "mostly outside the U.S.". The app also shows how far past the line the deal pushes it.
- **D. The holdings review:** what it may have to sell.
- **E. Its Canadian capital under OSFI**, from the Pillar 3 figures (which you can correct).

**What the AI does.**
- **It reads the holdings register**, in any layout: spreadsheet, PDF, Word or a plain list.
- **It gives each holding a reasoned verdict** under Reg K and Regulation Y: can keep / keep with conditions / at risk if Reg K status is lost / needs Fed approval / likely must sell. "Must sell" is allowed only if no route in the text lets the parent keep the holding, and the AI must say why each route fails. Holdings are reviewed in batches, at the same time.

**What the code checks.**
- **Consistency.** Every verdict is checked against the app's own Reg K result. For example, "can keep" for a non-banking business abroad is flagged when the parent fails Reg K.
- **Timing.** The disposal deadline comes from the closing date (12 CFR 211.23(d)).
- **The "two ways out" line, from the app's own numbers:** keep Reg K status by shedding $X of U.S. banking assets, or let it go and sell the holdings that depend on it.
- **The target's own holdings.** It lists the bank being bought's own real-estate ventures, minority investments, equity securities and foreclosed property, exact from its FR Y-9C.

**Technique.** Lab 1: if-then rules (Reg K tests, OSFI ratios). Lab 2: RAG. Parallel AI calls.

**Decisions and problems.**
- **"Keep" was misused.** The AI first said "keep" for holdings allowed only by the qualifying-foreign-bank permission. I rewrote the verdict definitions: a permission that depends on Reg K status means "at risk", never "keep".
- **U.S. territories.** I added the rule that territories count as the U.S. (Puerto Rico, Guam…).

### Stage 6 — AI analyst
**What it does.** The AI investigates the deal like a senior analyst: it decides what to test, one step at a time (up to six steps), choosing from four tools:
- **headroom:** how close the deal is to every line;
- **break_even:** what would flip each result;
- **scenario:** what-if tests (growth, a capital loss, more debt);
- **timeline:** the four-quarter average, quarter by quarter after closing.

It then writes up its findings and questions for the client. You can give it a focus.

**What the code checks.** The tools are the app's own calculator (`engine.py`): the AI never does the arithmetic. Every $ figure and % in the write-up must trace to a calculator result; any that don't are listed.

**Technique.** Tool use: the AI chooses, the code calculates, and the result goes back to the AI.

**Decisions and problems.**
- **It misread the timeline table.** The timeline tool now also returns a one-sentence summary.
- **Inputs looked untraceable.** The number check now counts the AI's own scenario inputs (e.g. "a $5bn loss") as traceable.

### Stage 7 — Summary & next steps
**What it does.** All results, a ranked issues list, and a one-page memo to the partner. Downloads:
- the memo as a one-page Word file;
- the memo as an email draft (.eml, opens in Outlook) or text to copy;
- the full report;
- the AI audit trail (every AI call, what it was for and which passages it was given).

**What the AI does.**
- Ranks the issues and says which ones interact.
- Drafts the memo.
- A **second AI call checks every statement in the memo** against its source.

**What the code checks.**
- **Nothing dropped.** Every flagged result must be covered by an issue; the app adds any the AI missed.
- **The memo loop.** Draft → tighten if over one page (430 words) → check → revise anything flagged as an error → check again (at most three checks).
- **Real citations.** Passage IDs become real citations ("12 CFR 211.23").
- **The figures.** Every figure in the memo must match the app's results.

**Technique.** Lab 2: looping and reflection (the second AI checks the first), with code checks around both.

**Decisions and problems.**
- **It predicted approval.** The first memos said the "deal cannot be approved". The memo style now forbids predicting approval and puts citations only after statements of law.
- **The checker flagged everything.** Its flags are now graded "error" or "minor", and only errors send the memo back.

### Size examples _(reference page)_
Made-up deals that land in each size category, and a calculator to try your own. Code only (12 CFR 252.5).

### What I left out
An earlier version had a "Deal options" step, where the AI proposed ways to restructure the deal to stay under a line. I dropped it to keep the task narrow, as the assignment notes recommend.

---

## AI calls in one run

The assignment needs at least 5 AI calls per run. A run through every step makes **about 30–40**:

| Step | AI calls |
|---|---|
| Getting started | 4–6 (read and review each filing, plus re-reads), +1 for a Pillar 3 report |
| At a glance | 7 (headline, plus 3 + 3 rule readings) |
| Capital ratios, Leverage & liabilities | 1 each, +1 each for the optional guide |
| Canadian buyer | 1, plus 1 to read the register and 1 per 8 holdings reviewed |
| AI analyst | 4–7 |
| Summary | 3–7 (issues list, memo draft, tightening, checks, revisions) |
| Each question asked | 2–4 (answer and check, looping if needed) |

---

## Test cases

The files are in `test_data/`. The example banks (`EXAMPLE_BANKS_2026Q2.txt`) and the holdings register (`ILLUSTRATIVE_holdings_register.csv`) are **fictional**. The figures in "Expected" below are worked out by the app's code, so they are the same every run; the AI's wording varies from run to run.

### Test 1 — A U.S. deal that crosses the $250bn line (works well)
1. Paste an OpenAI key in the left-hand panel. **Getting started** → *Or load a ready-made example deal* → **"U.S. deal that crosses $250bn — Sun Belt Bancshares buys Atlantic Harbor"**.
2. Go through each step with **Next**.

**Expected**
- **The deal.** Sun Belt ($228.0bn) + Atlantic Harbor ($41.0bn) = **$269.0bn: Category IV → Category III**.
- **Getting started.** The AI reads both filings and the app checks 40 figures. It should report "40 of 40 figures match the filing exactly"; any figure the AI misreads is sent back for a re-read. Its review should notice Sun Belt's large unrealised securities loss against CET1 and Atlantic Harbor's heavy goodwill.
- **At a glance.**
  - Newly applies: the supervisory stress test, the supplementary leverage ratio, the countercyclical buffer and the LCR/NSFR.
  - The AI's own reading of the rules should agree with the rulebook on 9 of 9 points, with the votes shown.
- **Capital ratios.** Combined CET1 9.69% against 7.0% needed: met.
- **Summary.** A ranked issues list covering every flagged result, and a one-page memo whose checks read "all figures match the app's results" and "every citation is a regulation in the library".

### Test 2 — A Canadian buyer that fails Reg K, with a holdings register (works well)
1. **Getting started** → load **"Canadian buyer — TD buys Keystone National (Category II, and fails Reg K)"**.
2. **Canadian buyer** → **Use the example register** → **Review the holdings** (the upload artefact is `test_data/ILLUSTRATIVE_holdings_register.csv`).
3. **AI analyst** → **Run the investigation**, then **Summary & next steps**.

**Expected**
- **Size.** TD's U.S. arm ($509.3bn) + Keystone ($470.0bn) = **$979.3bn: Category III → Category II**. AOCI now counts in CET1, and the full LCR/NSFR applies.
- **Reg K.**
  - The U.S. share of TD's banking assets becomes **53.8%**, so test 2 is **not met**.
  - The "two ways out" line: keep Reg K status by shedding more than **$137.6bn** of U.S. banking assets, or let it go and sell the holdings that depend on it.
  - Keystone's own balance sheet shows $705m of real-estate ventures, $1.65bn of investments in unconsolidated companies, $282m of equity securities and $94m of foreclosed property.
- **Holdings.** About 21 holdings get verdicts (the 14 in the register plus the 7 the Fed's records list for TD). Each verdict is checked against the Reg K result, with timing (about Oct 2029 for a closing in mid-2027), and the schedule downloads as CSV.
- **AI analyst.** It typically checks headroom, then break-even, then the timeline (Category II from the second quarter-end after closing), then a capital stress scenario. Every figure is traced.
- **Summary.** The memo should lead with the Reg K failure and the move to Category II, citing 12 CFR 211.23 and 252.5.

### Test 3 — Real Fed data, and where the app struggles
1. **Getting started.** For both banks choose *Upload its FR Y-9C* and upload `test_data/BHCF20260930.txt` (the Fed's real bulk file for smaller U.S. bank holding companies). Pick **Associated Banc-Corp** as the buyer and any other bank as the target.
2. Ask in any question box: **"Who won the World Series?"**
3. Load **"Canadian buyer — CIBC buys Great Lakes Financial"** and open **Canadian buyer**.
4. Load **"Canadian buyer — TD buys Keystone National"** and look at the Pillar 3 line on Getting started.

**Expected**
- **(1)** Real banks are read and checked like the examples. Both are below $100bn, so the deal lands in no category, and most rules don't apply. Only one quarter is loaded, so "Four-quarter average size" shows **can't tell**. The app says so rather than guessing.
- **(2)** The question is declined: there is nothing about it in the library.
- **(3)** No Pillar 3 report is built in for CIBC, so its total assets are unknown. Reg K and the OSFI ratios show **can't tell** until a report is uploaded, and the holdings section says Reg K status can't be confirmed yet.
- **(4)** TD's example report uses an older (2023) layout. The AI may not find CET1 ("not found"), and the code check flags it. The OSFI ratios stay "can't tell" until the figure is typed into the table on the Canadian buyer page.
- **Also expect** (gpt-4o-mini, run to run):
  - On the hardest rule question (when a holding company becomes an "advanced approaches" bank), one of the three readings sometimes disagrees. The vote and the rulebook comparison catch it, and the page shows how many readings agreed.
  - The memo checker sometimes still flags a subtle statement after two revisions. The page then quotes it under "Before sending, verify".

### Other test files
| File | What it is |
|---|---|
| `BHCF20260930.txt` | The Fed's real bulk FR Y-9C file (smaller U.S. bank holding companies) |
| `EXAMPLE_BANKS_2026Q2.txt` | Fictional banks, sized just below each category line (built by `tools/make_example_banks.py`) |
| `TD_/RBC_/BMO_/CIBC_US_FRY9C_*.pdf` | Real FR Y-9C filings of the Canadian banks' U.S. holding companies (built into the app) |
| `RBC_Pillar3_Q3_2026.pdf`, `BMO_RegCapital_Q3_2026.pdf`, `TD_RegDisclosure_Q3_2023.pdf` | The Canadian parents' capital disclosures |
| `ILLUSTRATIVE_holdings_register.csv` | A fictional holdings register for the Reg K review |
| `TD_illustrative_subsidiaries.txt` | A fictional list of subsidiaries in plain text (also works as a register upload) |

---

## Run it yourself
```
pip install -r requirements.txt
python3 -m streamlit run app.py
```
Then paste an OpenAI API key into the left-hand panel.

**Build the search index (once).** Without it the app searches by keywords (and says so on the Home page). Run this in the project folder; it asks for your key with the typing hidden:
```
python3 tools/build_embeddings.py
git add library/embeddings.npy library/embeddings_meta.json
git commit -m "Add the search index"
git push
```

**Deploy.** On [share.streamlit.io](https://share.streamlit.io):
1. Create app.
2. Choose this repository, branch `main`, main file `app.py`.
3. Under Advanced settings, set Python to 3.13.

No secrets are needed, because each user pastes their own key.

**Rebuild the data (not needed to run the app):**
- `python3 tools/build_library.py <folder of regulation PDFs>`
- `python3 tools/build_structure.py <folder of the Fed's NIC XML files>`
- `python3 tools/build_y9c_template.py`
- `python3 tools/make_example_banks.py`

## Files
| File | What it is |
|---|---|
| `app.py` | Sets up the page and shows the step you are on |
| `steps/` | One file per step: `home`, `setup`, `glance`, `capital`, `leverage`, `canadian`, `analyst`, `summary`, `sizes` |
| `engine.py` | Every rule and calculation, and the checks of the AI's work (no AI) |
| `ai.py` | Every call to OpenAI |
| `deal.py` | The deal on screen and its results |
| `library.py` | The regulation library and its search |
| `state.py` | What the app remembers between clicks |
| `ui.py` | The look, the left-hand panel (API key box and steps), shared display pieces |
| `library/` | The library's passages, the search index, the FR Y-9C line template, the Canadian banks' U.S. structure |
| `tools/` | One-off build scripts (not run by the app) |
| `test_data/` | The test files |

## Limitations
- **The combined bank is a simple sum.** It is the two banks added together: no purchase premium or goodwill.
- **Size categories use asset size only.** The app lists the other triggers (cross-jurisdictional activity, wholesale funding…) as questions for the client.
- **The Reg K test is partly estimated.** It uses assets from the filings and the Pillar 3 report; revenue and net income are estimated from the asset split unless you enter them.
- **Disposal timing is a rough guide.**
- **It is a screening tool, not legal advice.** Verify against the filings and the rules cited.
