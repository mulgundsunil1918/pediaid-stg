#!/usr/bin/env python3
"""
split_pdf.py — Split the IAP STG 2022 master PDF into per-chapter PDFs and
generate stg_index.json for the PediAid app.

Usage
─────
    python scripts/split_pdf.py path/to/IAP_STG_2022.pdf scripts/manifest.csv

Inputs
──────
    1. The master PDF (you keep this file private — never commit it).
    2. A manifest CSV describing where each chapter starts. See
       scripts/manifest.example.csv for the exact format. You only need to
       fill in start_page for each chapter — the script computes end_page
       automatically as (next_chapter.start_page - 1), and the last chapter
       runs to the final page of the PDF.

Outputs
───────
    chapters/001-neonatal-hypoglycemia.pdf
    chapters/002-atopic-dermatitis.pdf
    ...
    stg_index.json

What stg_index.json looks like
──────────────────────────────
    {
      "source": "IAP Standard Treatment Guidelines 2022 (IAP-STG 2022)",
      "version": "2022",
      "base_url": "https://mulgundsunil1918.github.io/pediaid-stg/chapters/",
      "generated_at": "2026-04-29T...",
      "chapters": [
        {
          "no": "001",
          "title": "Neonatal Hypoglycemia",
          "section": "Neonatology",
          "slug": "neonatal-hypoglycemia",
          "file": "001-neonatal-hypoglycemia.pdf",
          "url":  "https://mulgundsunil1918.github.io/pediaid-stg/chapters/001-neonatal-hypoglycemia.pdf",
          "pages": 14,
          "size_kb": 1842,
          "keywords": ["hypoglycemia","low blood sugar","neonate","BSL","dextrose"]
        },
        ...
      ]
    }

Dependencies
────────────
    pip install pypdf
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    sys.exit(
        "pypdf is not installed. Run:\n\n    pip install pypdf\n\nthen retry."
    )

BASE_URL_DEFAULT = "https://mulgundsunil1918.github.io/pediaid-stg/chapters/"


def slugify(text: str) -> str:
    """Lowercase, alnum + hyphens only — safe for URLs and filenames."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def read_manifest(manifest_path: Path) -> list[dict]:
    """Parse the CSV manifest. Required columns: chapter_no, title, start_page.
    Optional: section, keywords (semicolon-separated)."""
    with manifest_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = []
        for raw in reader:
            row = {k.strip(): (v or "").strip() for k, v in raw.items()}
            if not row.get("chapter_no") or not row.get("title"):
                # Skip blank rows silently.
                continue
            try:
                row["start_page"] = int(row["start_page"])
            except (KeyError, ValueError):
                sys.exit(
                    f"Row {row.get('chapter_no')!r} ({row.get('title')!r}) "
                    "is missing a numeric start_page."
                )
            row["section"] = row.get("section", "")
            kw = row.get("keywords", "") or ""
            row["keywords"] = [k.strip() for k in kw.split(";") if k.strip()]
            rows.append(row)
    if not rows:
        sys.exit("Manifest had no usable rows.")
    rows.sort(key=lambda r: r["start_page"])
    return rows


def split(
    src_pdf: Path,
    manifest: list[dict],
    out_dir: Path,
    base_url: str,
) -> dict:
    """Split src_pdf into per-chapter PDFs. Return the index dict."""
    reader = PdfReader(str(src_pdf))
    total_pages = len(reader.pages)

    # Compute end pages (next.start - 1, last chapter -> total_pages).
    for i, ch in enumerate(manifest):
        if i + 1 < len(manifest):
            ch["end_page"] = manifest[i + 1]["start_page"] - 1
        else:
            ch["end_page"] = total_pages
        if ch["end_page"] < ch["start_page"]:
            sys.exit(
                f"Chapter {ch['chapter_no']} ({ch['title']!r}) has "
                f"start_page={ch['start_page']} > end_page={ch['end_page']}. "
                "Check the manifest order."
            )

    out_dir.mkdir(parents=True, exist_ok=True)

    chapter_records = []
    for ch in manifest:
        no = str(ch["chapter_no"]).zfill(3)
        slug = slugify(ch["title"])
        filename = f"{no}-{slug}.pdf"
        out_path = out_dir / filename

        writer = PdfWriter()
        # PdfReader pages are 0-indexed; manifest uses 1-indexed.
        for p in range(ch["start_page"] - 1, ch["end_page"]):
            writer.add_page(reader.pages[p])
        with out_path.open("wb") as f:
            writer.write(f)

        size_kb = round(out_path.stat().st_size / 1024)
        pages = ch["end_page"] - ch["start_page"] + 1
        url = base_url.rstrip("/") + "/" + filename

        chapter_records.append(
            {
                "no": no,
                "title": ch["title"],
                "section": ch["section"],
                "slug": slug,
                "file": filename,
                "url": url,
                "pages": pages,
                "size_kb": size_kb,
                "keywords": ch["keywords"],
            }
        )

        print(f"  {no}  {ch['title']:<48}  pp.{ch['start_page']:>4}-{ch['end_page']:<4}  {size_kb:>5} KB")

    return {
        "source": "IAP Standard Treatment Guidelines 2022 (IAP-STG 2022)",
        "version": "2022",
        "base_url": base_url,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_chapters": len(chapter_records),
        "chapters": chapter_records,
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Split the IAP STG 2022 PDF into per-chapter PDFs and "
        "build stg_index.json."
    )
    ap.add_argument("pdf", type=Path, help="Path to the master IAP STG PDF")
    ap.add_argument("manifest", type=Path, help="Path to the chapter manifest CSV")
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "chapters",
        help="Output directory for per-chapter PDFs (default: ./chapters)",
    )
    ap.add_argument(
        "--index",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "stg_index.json",
        help="Output path for stg_index.json (default: ./stg_index.json)",
    )
    ap.add_argument(
        "--base-url",
        default=BASE_URL_DEFAULT,
        help=f"Public base URL where chapters/ will be hosted "
        f"(default: {BASE_URL_DEFAULT})",
    )
    args = ap.parse_args()

    if not args.pdf.exists():
        sys.exit(f"PDF not found: {args.pdf}")
    if not args.manifest.exists():
        sys.exit(f"Manifest not found: {args.manifest}")

    print(f"Reading manifest:   {args.manifest}")
    manifest = read_manifest(args.manifest)
    print(f"Splitting PDF:      {args.pdf}")
    print(f"Output dir:         {args.out}")
    print(f"Base URL:           {args.base_url}\n")

    index = split(args.pdf, manifest, args.out, args.base_url)

    args.index.write_text(json.dumps(index, indent=2, ensure_ascii=False))

    total_kb = sum(c["size_kb"] for c in index["chapters"])
    print(
        f"\nDone. {index['total_chapters']} chapters, "
        f"{total_kb / 1024:.1f} MB total."
    )
    print(f"Index written to:   {args.index}")
    print(
        f"\nNext: stage chapters/ and stg_index.json, then\n"
        f"    git add chapters/ stg_index.json\n"
        f'    git commit -m "Add IAP STG 2022 chapters"\n'
        f"    git push\n"
    )


if __name__ == "__main__":
    main()
