#!/usr/bin/env python3
"""
build_manifest.py — Auto-discover the start page of every chapter so you
don't have to read 150 page numbers by hand.

Two modes, tried in order:

  1. BOOKMARKS  — read the PDF's embedded outline / table of contents.
                  If your PDF has a bookmarks sidebar in any reader, this
                  works and is exact.
  2. TITLE SCAN — if bookmarks are missing or incomplete, take your list
                  of chapter titles and scan the PDF text page by page,
                  matching each title to the page it first appears on as
                  a heading.

Usage
─────
    # If bookmarks exist (preferred):
    python scripts/build_manifest.py path/to/IAP_STG_2022.pdf \\
        --mode bookmarks

    # If bookmarks are missing:
    python scripts/build_manifest.py path/to/IAP_STG_2022.pdf \\
        --mode titles \\
        --titles scripts/chapter_titles.csv

The chapter_titles.csv only needs three columns — no page numbers:

    chapter_no,title,section
    1,Neonatal Hypoglycemia,Neonatology
    2,Atopic Dermatitis,Dermatology
    ...

Output
──────
    scripts/manifest.csv  — same shape that split_pdf.py consumes, with
                            start_page filled in. The keywords column
                            is left blank for you to fill (5–10 synonyms
                            per chapter is the sweet spot).

A "confidence" column is appended in TITLE SCAN mode so you can see
which entries the script is sure about and which need a quick eyeball.

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
    from pypdf.generic import Destination
except ImportError:
    sys.exit("pypdf is not installed. Run:\n\n    pip install pypdf\n")


# ── Helpers ────────────────────────────────────────────────────────────────
def normalise(s: str) -> str:
    """Lowercase, collapse whitespace, drop punctuation — for fuzzy match."""
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def write_manifest(rows: list[dict], out_path: Path, with_confidence: bool):
    fieldnames = ["chapter_no", "title", "section", "start_page", "keywords"]
    if with_confidence:
        fieldnames.append("confidence")
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


# ── Mode 1: bookmarks ──────────────────────────────────────────────────────
def from_bookmarks(reader: PdfReader) -> list[dict]:
    """Walk the PDF outline and return one row per top-level entry."""
    outline = reader.outline
    if not outline:
        sys.exit(
            "This PDF has no embedded bookmarks. Try --mode titles instead."
        )

    rows: list[dict] = []
    counter = 1

    def walk(items, depth=0):
        nonlocal counter
        for item in items:
            if isinstance(item, list):
                # Nested children — only descend one level so we don't pick
                # up sub-headings as separate "chapters".
                if depth == 0:
                    walk(item, depth + 1)
                continue
            if not isinstance(item, Destination):
                continue
            try:
                page_idx = reader.get_destination_page_number(item)
            except Exception:
                continue
            title = str(item.title or "").strip()
            if not title:
                continue
            rows.append(
                {
                    "chapter_no": counter,
                    "title": title,
                    "section": "",
                    "start_page": page_idx + 1,  # CSV is 1-indexed
                    "keywords": "",
                }
            )
            counter += 1

    walk(outline)

    if not rows:
        sys.exit("Outline existed but no usable entries found.")
    return rows


# ── Mode 2: title scan ─────────────────────────────────────────────────────
def from_titles(reader: PdfReader, titles_csv: Path) -> list[dict]:
    """Match each title to the page where it first appears as a heading."""
    with titles_csv.open(newline="", encoding="utf-8-sig") as f:
        wanted = []
        for raw in csv.DictReader(f):
            row = {k.strip(): (v or "").strip() for k, v in raw.items()}
            if not row.get("title"):
                continue
            wanted.append(row)
    if not wanted:
        sys.exit(f"No usable rows in {titles_csv}")

    print(f"Indexing {len(reader.pages)} pages of text…")
    pages_text = []
    for i, page in enumerate(reader.pages):
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        pages_text.append(normalise(t))
        if (i + 1) % 50 == 0:
            print(f"  {i + 1} pages indexed")

    rows: list[dict] = []
    for w in wanted:
        target = normalise(w["title"])
        # Score: prefer pages where the title appears near the top.
        # Scan top 400 chars of each page to favour heading position.
        best_page = None
        best_score = 0
        for i, txt in enumerate(pages_text):
            head = txt[:400]
            full_hit = target in head
            partial_hit = target in txt
            if full_hit:
                score = 100 - (txt[:400].find(target) // 10)
            elif partial_hit:
                score = 40
            else:
                # token overlap fallback
                tw = set(target.split())
                ph = set(head.split())
                overlap = len(tw & ph)
                score = overlap * 5 if overlap >= max(2, len(tw) // 2) else 0
            if score > best_score:
                best_score = score
                best_page = i + 1
        rows.append(
            {
                "chapter_no": w.get("chapter_no") or len(rows) + 1,
                "title": w["title"],
                "section": w.get("section", ""),
                "start_page": best_page or "",
                "keywords": "",
                "confidence": (
                    "high" if best_score >= 80
                    else "medium" if best_score >= 40
                    else "LOW — verify manually"
                ),
            }
        )

    return rows


# ── CLI ────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(
        description="Build manifest.csv with start_page auto-detected."
    )
    ap.add_argument("pdf", type=Path, help="Path to the master PDF")
    ap.add_argument(
        "--mode",
        choices=["bookmarks", "titles"],
        required=True,
        help="bookmarks: read PDF outline. titles: scan text against a titles CSV.",
    )
    ap.add_argument(
        "--titles",
        type=Path,
        help="(titles mode only) CSV with columns: chapter_no,title,section",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent / "manifest.csv",
        help="Output manifest CSV (default: scripts/manifest.csv)",
    )
    args = ap.parse_args()

    if not args.pdf.exists():
        sys.exit(f"PDF not found: {args.pdf}")

    reader = PdfReader(str(args.pdf))
    print(f"Loaded PDF: {args.pdf} ({len(reader.pages)} pages)\n")

    if args.mode == "bookmarks":
        rows = from_bookmarks(reader)
        with_conf = False
    else:
        if not args.titles or not args.titles.exists():
            sys.exit("--titles /path/to/chapter_titles.csv is required for --mode titles")
        rows = from_titles(reader, args.titles)
        with_conf = True

    write_manifest(rows, args.out, with_confidence=with_conf)

    print(f"\nWrote {len(rows)} rows to {args.out}")
    if with_conf:
        lows = [r for r in rows if r.get("confidence", "").startswith("LOW")]
        if lows:
            print(f"\n⚠  {len(lows)} entries flagged LOW confidence — review these:")
            for r in lows[:10]:
                print(f"     {r['chapter_no']}  {r['title']}  → page {r['start_page']}")
            if len(lows) > 10:
                print(f"     … and {len(lows) - 10} more in the CSV.")
    print(
        "\nNext: open the CSV, fill in the keywords column (5–10 synonyms\n"
        "      per chapter), then run:\n\n"
        f"      python scripts/split_pdf.py \"{args.pdf}\" {args.out}\n"
    )


if __name__ == "__main__":
    main()
