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
    # Preserve the source publication's chapter number for reference if
    # any row has it (titles mode emits this column; bookmarks mode does not).
    has_orig = any(r.get("orig_chapter_no") for r in rows)
    if has_orig:
        fieldnames.append("orig_chapter_no")
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
    """v3: trust the PDF, not the index.

    For each title in titles_csv, find the page where it appears as a
    heading in the PDF body. Then sort matches by PDF page order and
    re-number chapters 1..N in that order. Titles whose chapter doesn't
    appear in the PDF are reported and dropped.

    The chapter_no column from titles_csv is preserved as `orig_chapter_no`
    for reference but is NOT used as the chapter number — the source
    publication's index numbering is treated as unreliable.
    """
    with titles_csv.open(newline="", encoding="utf-8-sig") as f:
        wanted = []
        for raw in csv.DictReader(f):
            row = {k.strip(): (v or "").strip() for k, v in raw.items()}
            if not row.get("title"):
                continue
            wanted.append(row)
    if not wanted:
        sys.exit(f"No usable rows in {titles_csv}")

    n_pages = len(reader.pages)
    print(f"Indexing {n_pages} pages of text…")
    pages_text = []
    for i, page in enumerate(reader.pages):
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        pages_text.append(normalise(t))
        if (i + 1) % 50 == 0:
            print(f"  {i + 1} pages indexed")

    # ── Detect TOC / index pages and exclude them from the search pool ──
    all_titles = [normalise(w["title"]) for w in wanted]
    toc_pages: set[int] = set()
    for i, txt in enumerate(pages_text):
        hits = sum(1 for t in all_titles if t and t in txt)
        if hits >= 4:
            toc_pages.add(i)
    if toc_pages:
        print(
            f"  excluded {len(toc_pages)} table-of-contents page(s): "
            f"{sorted(p + 1 for p in toc_pages)[:10]}"
            f"{' …' if len(toc_pages) > 10 else ''}"
        )

    # The publication uses '<title> 1 NN <body>' at the top of every
    # chapter start page (where NN is the chapter number). When that
    # pattern is present the page is unambiguously a chapter start and
    # we score it very high — this kills tie-collisions where two
    # chapters' titles both substring-match the same page text.
    chapter_marker_re = re.compile(r"^1\s+\d{1,3}\s")

    def score_page(target: str, page_idx: int) -> int:
        """Score how strongly `target` appears as a heading on this page."""
        if page_idx in toc_pages:
            return 0
        txt = pages_text[page_idx]
        head = txt[:600]
        if target in head:
            pos = head.find(target)
            # What follows the title? If it's the publication's chapter
            # marker ('1 94', '1 147' etc.) this is the real chapter start.
            after = head[pos + len(target):pos + len(target) + 40].lstrip()
            is_heading = bool(chapter_marker_re.match(after))
            base = 200 - (pos // 10)
            return base + 400 if is_heading else base
        if target in txt:
            return 60
        return 0

    # ── For each title, find its best-matching page anywhere in the PDF ──
    matches = []
    for w in wanted:
        target = normalise(w["title"])
        best_page = None
        best_score = 0
        for i in range(n_pages):
            s = score_page(target, i)
            # Tie-break: prefer earlier page (a chapter heading is typically
            # the first occurrence; later mentions are cross-references).
            if s > best_score:
                best_score = s
                best_page = i + 1
        matches.append(
            {
                "orig_chapter_no": w.get("chapter_no", ""),
                "title": w["title"],
                "section": w.get("section", ""),
                "best_page": best_page,
                "score": best_score,
            }
        )

    # Drop titles that don't appear meaningfully in the PDF body.
    SCORE_FLOOR = 60
    matched = [m for m in matches if m["score"] >= SCORE_FLOOR and m["best_page"]]
    dropped = [m for m in matches if m["score"] < SCORE_FLOOR or not m["best_page"]]

    if dropped:
        print(
            f"\n  ⚠  {len(dropped)} title(s) had no match in the PDF body — "
            "dropped:"
        )
        for d in dropped:
            print(f"     orig #{d['orig_chapter_no']:>3}  {d['title']}")

    # ── Sort by PDF page order, then renumber 1..N ──
    matched.sort(key=lambda m: (m["best_page"], -m["score"]))

    # Some titles might collide on the same page (rare). Keep the higher
    # scorer and drop the others.
    used_pages: set[int] = set()
    deduped = []
    collisions = []
    for m in matched:
        if m["best_page"] in used_pages:
            collisions.append(m)
            continue
        used_pages.add(m["best_page"])
        deduped.append(m)
    if collisions:
        print(
            f"\n  ⚠  {len(collisions)} title(s) collided on a page already "
            "claimed by another chapter — dropped:"
        )
        for c in collisions:
            print(f"     orig #{c['orig_chapter_no']:>3}  {c['title']}  → page {c['best_page']}")

    rows = []
    for new_no, m in enumerate(deduped, start=1):
        if m["score"] >= 150:
            confidence = "high"
        elif m["score"] >= 60:
            confidence = "medium"
        else:
            confidence = "LOW — verify manually"
        rows.append(
            {
                "chapter_no": new_no,
                "orig_chapter_no": m["orig_chapter_no"],
                "title": m["title"],
                "section": m["section"],
                "start_page": m["best_page"],
                "keywords": "",
                "confidence": confidence,
            }
        )

    print(
        f"\n  matched {len(rows)} chapters in PDF order "
        f"(of {len(wanted)} titles in the input)."
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
