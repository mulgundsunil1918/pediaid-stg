#!/usr/bin/env python3
"""
find_missing.py — for chapters that build_manifest.py couldn't locate,
search the PDF for distinctive partial terms and show candidate pages
with the surrounding text, so you can identify the actual heading wording
without scrolling the PDF by hand.

Compares scripts/chapter_titles.csv (the input list) against
scripts/manifest.csv (what build_manifest.py actually matched), and runs
a partial-term search against the PDF for everything that's missing.

Usage
─────
    python scripts/find_missing.py path/to/IAP_STG_2022.pdf

For each missing chapter it prints up to 5 candidate pages, e.g.:

    ── orig # 18  Acute Tonsillo-pharyngitis ──
       searching: 'tonsill'
       p.110  "ACUTE TONSILLOPHARYNGITIS Definition Tonsillopharyngitis is an…"
       p.522  "…antibiotic for tonsillitis…"

You eyeball the list, identify the chapter heading and its page, then
tell me. I patch scripts/chapter_titles.csv and you re-run
build_manifest.py — should pick everything up cleanly.

Dependencies
────────────
    pip install pypdf
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError:
    sys.exit("pypdf is not installed. Run:\n\n    pip install pypdf\n")


# Hand-tuned distinctive search terms for the 11 chapters this PDF most
# commonly mis-matches. Anything not in this map falls back to a generic
# rule (longest word from the title that isn't a stopword).
SEARCH_TERMS = {
    "Difficulties in Breathing":
        ["breathing difficult", "respiratory distress", "approach to breathing"],
    "Acute Tonsillo-pharyngitis":
        ["tonsill"],
    "Acute GI Bleed":
        ["gi bleed", "gastrointestinal bleed", "upper gi", "lower gi"],
    "JIA / JRA":
        ["juvenile idiopathic arthritis", "juvenile arthritis", "jia"],
    "AKI in Children":
        ["acute kidney injury", "aki"],
    "Respiratory Distress in Term Newborn":
        ["term newborn", "term neonate", "term nb", "respiratory distress in term"],
    "Cow Milk Protein Allergy":
        ["cow milk", "cow's milk", "milk protein allergy", "cmpa"],
    "Specific Learning Disorders":
        ["specific learning", "learning disorder"],
    "Nipah, Zika and Monkey Pox":
        ["nipah", "monkeypox", "monkey pox", "zika"],
    "Autism Spectrum Disorders":
        ["autism spectrum", "autism"],
    "Measles":
        ["measles"],
}

STOPWORDS = {
    "the", "of", "in", "and", "for", "to", "a", "an", "with", "by", "on",
    "from", "as", "at", "is", "or", "approach", "acute", "chronic",
    "children", "child", "neonatal", "neonate",
}


def normalise(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def fallback_terms(title: str) -> list[str]:
    """Pick the longest non-stopword as a fallback search term."""
    words = [w for w in normalise(title).split() if w not in STOPWORDS and len(w) > 3]
    if not words:
        return [normalise(title)]
    words.sort(key=len, reverse=True)
    return words[:2]


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Find candidate pages for chapters that build_manifest.py "
        "could not match."
    )
    ap.add_argument("pdf", type=Path, help="Path to the master PDF")
    ap.add_argument(
        "--titles",
        type=Path,
        default=Path(__file__).resolve().parent / "chapter_titles.csv",
        help="Input chapter titles CSV (default: scripts/chapter_titles.csv)",
    )
    ap.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).resolve().parent / "manifest.csv",
        help="Manifest produced by build_manifest.py (default: scripts/manifest.csv)",
    )
    args = ap.parse_args()

    if not args.pdf.exists():
        sys.exit(f"PDF not found: {args.pdf}")
    if not args.titles.exists():
        sys.exit(f"Titles CSV not found: {args.titles}")
    if not args.manifest.exists():
        sys.exit(f"Manifest CSV not found: {args.manifest}")

    # Load titles + manifest, compute the missing set.
    with args.titles.open(newline="", encoding="utf-8-sig") as f:
        wanted = [{k.strip(): (v or "").strip() for k, v in r.items()}
                  for r in csv.DictReader(f) if (r or {}).get("title")]
    with args.manifest.open(newline="", encoding="utf-8-sig") as f:
        matched_titles = {(r.get("title") or "").strip()
                          for r in csv.DictReader(f)}

    missing = [w for w in wanted if w["title"] not in matched_titles]
    if not missing:
        print("No missing chapters. Nothing to do.")
        return

    print(f"Loading PDF: {args.pdf}")
    reader = PdfReader(str(args.pdf))
    n_pages = len(reader.pages)
    print(f"Indexing {n_pages} pages of text…")

    pages_text = []
    for i, page in enumerate(reader.pages):
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        pages_text.append(normalise(t))
        if (i + 1) % 100 == 0:
            print(f"  {i + 1} pages indexed")

    print(f"\nMissing {len(missing)} chapter(s) — searching for each:\n")

    for w in missing:
        title = w["title"]
        terms = SEARCH_TERMS.get(title) or fallback_terms(title)
        print(f"── orig #{w.get('chapter_no', '?'):>3}  {title} ──")

        any_hits = False
        for term in terms:
            term_n = normalise(term)
            print(f"   searching: {term_n!r}")
            hits = []
            for i, txt in enumerate(pages_text):
                head = txt[:600]
                if term_n in head:
                    pos = head.find(term_n)
                    hits.append((200 - pos // 5, i + 1, head))
                elif term_n in txt:
                    hits.append((50, i + 1, txt[:200]))
            hits.sort(key=lambda h: -h[0])
            for score, page_no, snippet in hits[:5]:
                snip = re.sub(r"\s+", " ", snippet)[:160]
                print(f"      p.{page_no:>4}  \"{snip}…\"")
                any_hits = True
            if hits:
                # First good term that hit something — stop trying more.
                break

        if not any_hits:
            print(f"      (no matches found)")
        print()

    print(
        "Pick the right page for each chapter and tell Claude — paste the "
        "list back. Format:\n\n"
        "    chapter X → page YYY  (heading: 'EXACT TEXT')\n"
    )


if __name__ == "__main__":
    main()
