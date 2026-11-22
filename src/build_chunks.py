"""
Step 2: parse every PDF in data/raw and write the chunk files.

Outputs (in data/processed/):
  chunks_article.jsonl  article-based chunks (main approach)
  chunks_article_ent.jsonl  same, with entity summaries on stewards' chunks
  chunks_fixed.jsonl    fixed-size chunks (baseline for comparison)
  chunk_samples.md      random sample of chunks for manual spot-checking

Run from the project root:   python src/build_chunks.py
"""
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pdf_text import extract_pages, clean_lines, PROJECT_ROOT
from parse_regs import parse_regulation
from parse_stewards import parse_stewards_doc

RAW = PROJECT_ROOT / "data" / "raw"
OUT = PROJECT_ROOT / "data" / "processed"
FIXED_SIZE, FIXED_OVERLAP = 1000, 200


def classify(pdf: Path):
    """Work out season, doc_type and a readable name from the file name."""
    name = pdf.name
    season = int(pdf.parent.name)
    if season >= 2026:
        m = re.search(r"Section ([A-F])\s*\[([^\]]+)\]", name)
        letter, label = m.group(1), m.group(2)
        doc_type = {"A": "general", "B": "sporting", "C": "technical"}.get(letter, label.lower())
        return season, doc_type, f"{season} F1 Regulations Section {letter} ({label})"
    doc_type = "technical" if re.search(r"technical", name, re.I) else "sporting"
    return season, doc_type, f"{season} F1 {doc_type.title()} Regulations"


def fixed_chunks(pdf, season, doc_type, doc_name):
    """Baseline: fixed windows of FIXED_SIZE characters, no awareness of structure."""
    lines = clean_lines(extract_pages(pdf))
    text, page_at = "", []
    for page, line in lines:
        page_at.append((len(text), page))
        text += line + "\n"
    chunks, start, n = [], 0, 0
    while start < len(text):
        piece = text[start:start + FIXED_SIZE]
        page = max(p for off, p in page_at if off <= start) if page_at else None
        n += 1
        chunks.append({"id": f"{season}-{doc_type}-fixed-{n}",
                       "text": piece,
                       "metadata": {"source_type": "regulation", "season": season,
                                    "doc_type": doc_type, "doc_name": doc_name,
                                    "file": pdf.name, "page": page}})
        start += FIXED_SIZE - FIXED_OVERLAP
    return chunks


def dedupe_ids(chunks):
    seen = Counter()
    for c in chunks:
        seen[c["id"]] += 1
        if seen[c["id"]] > 1:
            c["id"] = f"{c['id']}-dup{seen[c['id']]}"
    return chunks


def write_jsonl(path, chunks):
    with open(path, "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")


def main(only=None):
    OUT.mkdir(parents=True, exist_ok=True)
    article_chunks, fixed = [], []

    for season_dir in ["2025", "2026"]:
        for pdf in sorted((RAW / season_dir).glob("*.pdf")):
            if only and only.lower() not in pdf.name.lower():
                continue
            season, doc_type, doc_name = classify(pdf)
            print(f"Parsing {pdf.name} ...", flush=True)
            a = parse_regulation(pdf, season, doc_name, doc_type)
            f = fixed_chunks(pdf, season, doc_type, doc_name)
            print(f"   {len(a)} article chunks, {len(f)} fixed chunks")
            article_chunks += a
            fixed += f

    stewards = []
    if not only or only == "stewards":
        pdfs = sorted((RAW / "stewards").rglob("*.pdf"))
        print(f"Parsing {len(pdfs)} stewards' documents ...", flush=True)
        for pdf in pdfs:
            stewards += parse_stewards_doc(pdf)
        print(f"   {len(stewards)} stewards chunks")

    # Stewards' documents are already short: both approaches share them.
    article_chunks = dedupe_ids(article_chunks + stewards)
    fixed = dedupe_ids(fixed + [dict(c) for c in stewards])

    # Option 1 variant: same chunks, but stewards' chunks start with an entity summary.
    enriched = []
    for c in article_chunks:
        c2 = {k: v for k, v in c.items() if k != "summary"}
        if c.get("summary"):
            c2["text"] = c["summary"] + "\n" + c["text"]
        enriched.append(c2)
    for lst in (article_chunks, fixed):
        for c in lst:
            c.pop("summary", None)

    write_jsonl(OUT / "chunks_article.jsonl", article_chunks)
    write_jsonl(OUT / "chunks_article_ent.jsonl", enriched)
    write_jsonl(OUT / "chunks_fixed.jsonl", fixed)

    random.seed(42)
    sample = random.sample(article_chunks, min(15, len(article_chunks)))
    with open(OUT / "chunk_samples.md", "w", encoding="utf-8") as f:
        f.write("# Chunk samples for spot-checking\n\n")
        f.write("Check each one against the PDF: complete rule? correct number? no header/footer junk?\n\n")
        for c in sample:
            md = c["metadata"]
            f.write(f"## {c['id']}  (file: {md['file']}, page {md.get('page', '-')})\n\n")
            f.write("```\n" + c["text"] + "\n```\n\n")

    lengths = [len(c["text"]) for c in article_chunks]
    print("\nDone.")
    print(f"  article-based: {len(article_chunks)} chunks "
          f"(avg {sum(lengths)//max(len(lengths),1)} chars, max {max(lengths, default=0)})")
    print(f"  fixed-size:    {len(fixed)} chunks")
    print(f"  by source: {dict(Counter(c['metadata']['doc_type'] + '-' + str(c['metadata']['season']) for c in article_chunks))}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
