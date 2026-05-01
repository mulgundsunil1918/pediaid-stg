# PediAid STG

Hosting + index for the **IAP Standard Treatment Guidelines 2022 (IAP-STG 2022)** chapters used by the PediAid app.

**Live URL:** https://mulgundsunil1918.github.io/pediaid-stg/
**Chapter base URL:** https://mulgundsunil1918.github.io/pediaid-stg/chapters/{chapter}.pdf

## What this repo holds

```
pediaid-stg/
├── chapters/                    ← per-chapter PDFs (you generate these)
│   ├── 001-neonatal-hypoglycemia.pdf
│   ├── 002-atopic-dermatitis.pdf
│   └── ...
├── stg_index.json               ← machine-readable chapter index (auto-generated)
├── index.html                   ← human-browseable chapter list
├── scripts/
│   ├── split_pdf.py             ← splits the master PDF + builds stg_index.json
│   └── manifest.example.csv     ← example chapter map (you edit a copy)
└── .github/workflows/deploy.yml ← GitHub Pages deploy
```

The master IAP-STG 2022 PDF is **not** committed here. The repo only holds the per-chapter splits + the index, so the Flutter app can fetch one chapter at a time on demand.

## How to add / regenerate chapters

You only need Python 3.9+ and one library.

```bash
pip install pypdf
```

The IAP-STG 2022 index page lists chapter titles but **not** start pages, so we have a helper that auto-discovers them. Two-step flow:

### Step 1 — auto-detect every chapter's start_page

You don't have to scroll the PDF. The helper script handles it two ways:

**A. Bookmarks mode (preferred — instant + exact)**

If your PDF has an embedded outline / bookmarks sidebar (most modern medical PDFs do — open in Adobe Reader and check the left bookmarks panel):

```bash
python scripts/build_manifest.py /path/to/IAP_STG_2022.pdf --mode bookmarks
```

This reads the PDF's table of contents directly and writes `scripts/manifest.csv` with start pages already filled in for every chapter.

**B. Titles mode (fallback — works when bookmarks are missing)**

If the PDF has no bookmarks, transcribe the chapter list (titles only — no page numbers needed) into a CSV using `scripts/chapter_titles.example.csv` as the template:

```csv
chapter_no,title,section
1,Neonatal Hypoglycemia,Neonatology
2,Atopic Dermatitis,Dermatology
...
```

Then:

```bash
python scripts/build_manifest.py /path/to/IAP_STG_2022.pdf \
    --mode titles --titles scripts/chapter_titles.csv
```

The script scans the PDF text page by page, matches each title to the page where it first appears as a heading, and writes `scripts/manifest.csv` with start pages filled in. A `confidence` column is appended — anything flagged `LOW` is worth a 5-second eyeball before you proceed.

### Step 2 — add keywords + run the splitter

Open `scripts/manifest.csv` in Excel and fill in the `keywords` column (semicolon-separated). **This is the make-or-break field for search quality** — add 5–10 synonyms per chapter (clinical names, abbreviations, lay terms, common misspellings).

| Column        | Required | Example                               | Notes |
|---------------|----------|---------------------------------------|-------|
| `chapter_no`  | yes      | `1`                                   | The script zero-pads to `001` |
| `title`       | yes      | `Neonatal Hypoglycemia`               | Used for filename slug + display |
| `section`     | no       | `Neonatology`                         | Free-text grouping for the app |
| `start_page`  | yes      | `15`                                  | Auto-filled by `build_manifest.py` |
| `keywords`    | no       | `hypoglycemia;low blood sugar;BSL`    | You fill this. 5–10 synonyms per chapter is the sweet spot. |

The script computes `end_page` automatically as `(next chapter's start_page − 1)`. The last chapter runs to the final page.

Then run the splitter:

```bash
python scripts/split_pdf.py /path/to/IAP_STG_2022.pdf scripts/manifest.csv
```

Output:
- 150 PDFs written to `chapters/`
- `stg_index.json` written at the repo root, with absolute URLs already wired to this Pages site.

### Step 3 — push

```bash
git add chapters/ stg_index.json
git commit -m "Add IAP STG 2022 chapter splits"
git push
```

GitHub Actions deploys to Pages automatically (`.github/workflows/deploy.yml`).

## Output `stg_index.json` shape

```json
{
  "source": "IAP Standard Treatment Guidelines 2022 (IAP-STG 2022)",
  "version": "2022",
  "base_url": "https://mulgundsunil1918.github.io/pediaid-stg/chapters/",
  "generated_at": "2026-04-29T...",
  "total_chapters": 150,
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
      "keywords": ["hypoglycemia", "low blood sugar", "neonate", "BSL", "dextrose"]
    }
  ]
}
```

## How the Flutter app uses this

1. App ships with **only** a small copy of `stg_index.json` (or fetches it on first launch and caches it).
2. User searches by typing — title + keywords + section are scored locally.
3. Tap a result → the app downloads `chapter.url`, caches to disk via `path_provider`, and opens it in the in-app PDF viewer (Syncfusion).
4. Subsequent opens of the same chapter are offline.

## Limits to be aware of

- GitHub repo soft cap: **1 GB**. The split set should be ~200 MB, well under.
- Per-file hard cap: **100 MB**. No single STG chapter is anywhere near that.
- GitHub Pages bandwidth: **100 GB/month soft**. ~80,000 chapter views/month before throttling kicks in.
- Per-file rate limit on GitHub Pages: none documented (unlike Drive's silent quota lockouts).

## Copyright note

The IAP STG 2022 is a copyrighted publication. Hosting per-chapter PDFs publicly counts as redistribution. Make sure you have written permission from IAP or appropriate licensing before you push the `chapters/` folder. If you do not have permission, keep the splits in a private fork or change to a "link out to IAP's official PDF" model.

## Local preview

```bash
python -m http.server 8090
```

Then open http://127.0.0.1:8090/.
