"""
tools/build_library.py - how library/chunks.json was made (run once; the regulation PDFs are not in this repository).

It reads 14 regulation PDFs and splits them into passages ("chunks"):
  * the U.S. regulations (12 CFR Parts 211, 217, 225, 249, 251, 252): one passage per section (e.g. "12 CFR 217.10"),
    long sections split into parts of about 3,500 characters;
  * the statutes, OSFI guidelines, Bank Act and the Fed memo: passages of two pages, cited by page.
Page headers, footers and website clutter are removed. Each passage keeps its citation, the document it came from,
whether it is in force or only proposed, and the date of the version used.

Usage:  python3 tools/build_library.py <folder containing the regulation PDFs>
After rebuilding, rebuild the search index too:  python3 tools/build_embeddings.py
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from library import CHUNKS_PATH  # noqa: E402

# "match" is a piece of text in the PDF's file name. "status" is shown to the user (in force, or only proposed).
SOURCES = [
    {"match": "Part_217", "name": "12 CFR Part 217 (Regulation Q - capital)", "cite": "12 CFR", "kind": "cfr", "status": "In force", "as_of": "2026-10-27"},
    {"match": "Part_252", "name": "12 CFR Part 252 (Regulation YY - enhanced prudential standards)", "cite": "12 CFR", "kind": "cfr", "status": "In force", "as_of": "2026-10-27"},
    {"match": "Part_249", "name": "12 CFR Part 249 (Regulation WW - LCR / NSFR)", "cite": "12 CFR", "kind": "cfr", "status": "In force", "as_of": "2026-10-27"},
    {"match": "Part_225", "name": "12 CFR Part 225 (Regulation Y - bank holding companies)", "cite": "12 CFR", "kind": "cfr", "status": "In force", "as_of": "2026-10-27"},
    {"match": "Part_211", "name": "12 CFR Part 211 (Regulation K - international banking / foreign banks)", "cite": "12 CFR", "kind": "cfr", "status": "In force", "as_of": "2026-10-27"},
    {"match": "Part_251", "name": "12 CFR Part 251 (Regulation XX - concentration limit)", "cite": "12 CFR", "kind": "cfr", "status": "In force", "as_of": "2026-10-27"},
    {"match": "1828", "name": "12 U.S.C. 1828 (incl. Bank Merger Act, s.1828(c))", "cite": "12 U.S.C. 1828", "kind": "page", "status": "In force", "as_of": "2026-10-29"},
    {"match": "1842", "name": "12 U.S.C. 1842 (BHC Act s.3 - acquisitions)", "cite": "12 U.S.C. 1842", "kind": "page", "status": "In force", "as_of": "2026-10-29"},
    {"match": "1852", "name": "12 U.S.C. 1852 (concentration limits)", "cite": "12 U.S.C. 1852", "kind": "page", "status": "In force", "as_of": "2026-10-29"},
    {"match": "car-nfp-ch1", "name": "OSFI CAR Guideline (2027) - Chapter 1", "cite": "OSFI CAR (2027) Ch.1", "kind": "page", "status": "In force from 1 Nov 2026", "as_of": "2026-09"},
    {"match": "car-nfp-ch2", "name": "OSFI CAR Guideline (2027) - Chapter 2", "cite": "OSFI CAR (2027) Ch.2", "kind": "page", "status": "In force from 1 Nov 2026", "as_of": "2026-09"},
    {"match": "Leverage_Requirements", "name": "OSFI Leverage Requirements Guideline (2023)", "cite": "OSFI LR Guideline", "kind": "page", "status": "In force", "as_of": "2023"},
    {"match": "B-1.01", "name": "Bank Act (Canada) - Parts IX-X (pp. 397-429)", "cite": "Bank Act (Can.)", "kind": "page", "status": "In force", "as_of": "2026-09-30", "pages": (396, 429)},
    {"match": "board-memo-basel", "name": "Fed Board memo on the March 2026 capital proposals", "cite": "Fed Board memo (19 Mar 2026)", "kind": "page", "status": "PROPOSED rules - not in force", "as_of": "2026-03-19"},
]

NOISE = re.compile(
    r"^(12 CFR Part \d+ \(up to date as of .*\)|.*Legal Information Institute.*|https?://\S+.*|"
    r"\d+/\d+/\d{4}, \d+:\d+.*|Page \d+ of \d+|.*\(enhanced display\) page \d+ of \d+|.*Protected B - External.*|.*Unclassified / Non classifi.*)$")
SECTION_HEADING = re.compile(r"^§\s?(\d{3})\.\s?([0-9a-z\-]+)\s+(.{3,160})$")
APPENDIX_HEADING = re.compile(r"^(Appendix [A-Z]+ to Part (\d{3}))\b\s*(.{0,160})$")
MAX_CHARS = 3500


def _clean(text):
    return "\n".join(ln for ln in (l.strip() for l in text.splitlines()) if ln and not NOISE.match(ln))


def _split_long(text, max_chars=MAX_CHARS):
    if len(text) <= max_chars:
        return [text]
    parts, current = [], ""
    for line in text.split("\n"):
        if len(current) + len(line) > max_chars and current:
            parts.append(current)
            current = ""
        current += line + "\n"
    if current.strip():
        parts.append(current)
    return parts


def _chunks_from_cfr(pages):
    """One passage per § section. The table of contents makes tiny 'sections' with no body; those are dropped."""
    text = _clean("\n".join(pages))
    chunks, heading, body = [], None, []

    def flush():
        if heading and len("\n".join(body)) > 300:
            sec_id, title = heading
            for i, part in enumerate(_split_long("\n".join(body))):
                chunks.append({"cite": f"12 CFR {sec_id}" + (f" (part {i + 1})" if i else ""), "title": title, "text": part.strip()})

    for line in text.split("\n"):
        m, a = SECTION_HEADING.match(line), APPENDIX_HEADING.match(line)
        if m:
            flush()
            heading, body = (f"{m.group(1)}.{m.group(2)}", m.group(3).strip()), []
        elif a:
            flush()
            heading, body = (f"Part {a.group(2)}, {a.group(1)}", a.group(3).strip() or a.group(1)), []
        elif heading:
            body.append(line)
    flush()
    return chunks


def _chunks_from_pages(pages, src, first_page=1):
    chunks = []
    for i in range(0, len(pages), 2):
        text = _clean("\n".join(pages[i:i + 2]))
        if len(text) < 200:
            continue
        for part in _split_long(text):
            chunks.append({"cite": f"{src['cite']}, p.{first_page + i}", "title": src["name"], "text": part.strip()})
    return chunks


def _fix_known_misfiles(chunks):
    """The PDF prints the next section's heading before the last lines of 12 CFR 252.5, so the Category IV definition
    (252.5(e)) lands under 252.11. Put it back where it belongs."""
    title = next((c["title"] for c in chunks if c["cite"] == "12 CFR 252.5"), "Applicability")
    for c in chunks:
        if c["cite"] == "12 CFR 252.11" and "(e) Category IV." in c["text"]:
            c["cite"], c["title"] = "12 CFR 252.5 (part 3)", title
            c["text"] = c["text"].split("(a) Authority.")[0].rstrip()
    return chunks


def build(pdf_folder):
    from pypdf import PdfReader
    all_chunks, files = [], sorted(os.listdir(pdf_folder))
    for src in SOURCES:
        match = [f for f in files if src["match"] in f and f.lower().endswith(".pdf")]
        if not match:
            print(f"  MISSING: {src['name']}")
            continue
        reader = PdfReader(os.path.join(pdf_folder, match[0]))
        start, end = src.get("pages", (0, len(reader.pages)))
        pages = [(reader.pages[i].extract_text() or "") for i in range(start, end)]
        chunks = _chunks_from_cfr(pages) if src["kind"] == "cfr" else _chunks_from_pages(pages, src, first_page=start + 1)
        for c in chunks:
            c.update({"source": src["name"], "status": src["status"], "as_of": src["as_of"]})
        print(f"  {src['name']}: {len(chunks)} passages")
        all_chunks.extend(chunks)
    all_chunks = _fix_known_misfiles(all_chunks)
    for n, c in enumerate(all_chunks):
        c["id"] = f"C{n}"
    with open(CHUNKS_PATH, "w", encoding="utf-8") as fh:
        json.dump(all_chunks, fh, ensure_ascii=False)
    print(f"Saved {len(all_chunks)} passages to {CHUNKS_PATH}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: python3 tools/build_library.py <folder containing the regulation PDFs>")
    build(sys.argv[1])
