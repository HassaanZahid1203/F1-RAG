# PDF text extraction with per-page disk cache (data/processed/cache/)
# and header/footer cleaning.
import json
import re
import hashlib
from pathlib import Path

import pdfplumber

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / "data" / "processed" / "cache"


def extract_pages(pdf_path: Path) -> list[str]:
    """Return a list with the raw text of each page (cached on disk)."""
    pdf_path = Path(pdf_path)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = hashlib.md5(f"{pdf_path.name}-{pdf_path.stat().st_size}".encode()).hexdigest()[:12]
    cache_file = CACHE_DIR / f"{key}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))

    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    cache_file.write_text(json.dumps(pages, ensure_ascii=False), encoding="utf-8")
    return pages


# ---------------------------------------------------------------------------
# Header / footer removal for the regulation PDFs
# ---------------------------------------------------------------------------
# Footers look like:
#   "2026 Form ula 1 Regulations - Section B [Sporting] 01 October 2026"
#   "2025 Formula 1 Sporting Regulations 3/119 30 April 2025"
#   "©2026 Fédération Internationale de l'Automobile Issue 09"
# Headers look like: "B", "0", "SECTION B: SPORTING REGULATIONS"
# Page markers look like: "B 1", "A 4", "C2 1"
_FORMULA_1 = r"20\d\d\s*F\s*o\s*r\s*m\s*u\s*l\s*a\s*1"
NOISE_PATTERNS = [
    re.compile(rf"^{_FORMULA_1}\b.*\d{{1,2}}\s+[A-Z][a-z]+\s+20\d\d"),  # footer with date
    re.compile(r"^©\s*20\d\d\s+F[ée]d[ée]ration"),                      # copyright line
    re.compile(r"^SECTION [A-F]\s*:\s*[A-Z ]+$"),                       # running header
    re.compile(r"^[A-F0]$"),                                            # lone letters / "0"
    re.compile(r"^[A-F]\s?\d{0,2}\s?\d{1,3}$"),                         # page markers "B 1", "C2 1"
    re.compile(r"^(Advisory Committee|Governance)\s*:"),                # governance annotations
]


def is_noise(line: str) -> bool:
    s = line.strip()
    return not s or any(p.search(s) for p in NOISE_PATTERNS)


def clean_lines(pages: list[str]) -> list[tuple[int, str]]:
    """Flatten pages into (page_number, line) pairs with headers/footers removed."""
    out = []
    for page_no, text in enumerate(pages, start=1):
        for line in text.split("\n"):
            if not is_noise(line):
                out.append((page_no, line.rstrip()))
    return out
