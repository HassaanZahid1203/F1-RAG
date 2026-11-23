# Article-based chunking of FIA regulations: one chunk per numbered clause,
# prefixed with a document > article > subsection breadcrumb.
# Formats: 2026 "ARTICLE B3:" / "B3.5.3"; 2025 sporting "40)" / "40.3", technical "ARTICLE 3:" / "3.2.2".
# A numbered line starts a clause only if numbering advances plausibly, so wrapped
# cross-references ("...Article\n54.3 the stewards...") aren't mistaken for clauses.
import re
from pathlib import Path

from pdf_text import extract_pages, clean_lines

MAX_CHARS = 2500        # clauses longer than this are split into parts
APPENDIX_WINDOW = 1500  # appendices are split into windows of about this size

# Appendices describing rules for FUTURE seasons are excluded,
# otherwise they would contaminate answers about the current season.
EXCLUDED_APPENDIX = re.compile(r"SUBSEQUENT YEARS|FUTURE", re.I)

#  heading patterns 
NEW_ARTICLE = re.compile(r"^ARTICLE\s+([A-F])(\d+)\s*:\s*(.+?)\s*$")
NEW_CLAUSE = re.compile(r"^([A-F])(\d+(?:\.\d+){1,4})([a-z])?\s+(\S.*)$")
OLD_ARTICLE_TECH = re.compile(r"^ARTICLE\s+(\d+)\s*:\s*(.+?)\s*$")
OLD_ARTICLE_SPORT = re.compile(r"^(\d+)\)\s+([A-Z][A-Z0-9 ,&’'\-–/()É]+)$")
OLD_CLAUSE = re.compile(r"^(\d+(?:\.\d+){1,4})\s+(\S.*)$")
# 2026: "APPENDIX B2: TITLE"   2025: "APPENDIX 1" (no title)
APPENDIX = re.compile(r"^APPENDIX\s+([A-F]?\d+)\s*(?::\s*(.+?))?\s*$")
TOC_TRAILING_PAGE = re.compile(r"\s\d{1,3}$")
TABLE_ROW = re.compile(r"\b(Yes|No|N/A)\b(\s+\S+){0,2}\s+\b(Yes|No|N/A)\b")


def _plausible_next(prev, new):
    """Is clause number `new` a believable successor of `prev`?"""
    if prev is None:
        return all(n <= 3 for n in new[1:])
    for i in range(min(len(prev), len(new))):
        if new[i] != prev[i]:
            if new[i] < prev[i] or new[i] - prev[i] > 3:
                return False
            return all(n <= 3 for n in new[i + 1:])
    if len(new) > len(prev):                 # going one level deeper
        return all(n <= 3 for n in new[len(prev):])
    return False                             # identical number


def _looks_like_title(text):
    t = text.strip()
    return len(t) <= 80 and not t.endswith((".", ",", ";", ":")) and not t[:1].islower()


class _Unit:
    def __init__(self, cid, article, page, first_text):
        self.cid, self.article, self.page = cid, article, page
        self.title = None
        self.lines = []
        if first_text:
            self.lines.append(first_text)


def parse_regulation(pdf_path, season, doc_name, doc_type):
    """
    Parse one regulation PDF into chunks.

    season    e.g. 2026
    doc_name  human label, e.g. "2026 Sporting Regulations (Section B)"
    doc_type  "sporting" | "technical" | "general"
    """
    pdf_path = Path(pdf_path)
    lines = clean_lines(extract_pages(pdf_path))
    is_new = season >= 2026

    article_titles = {}   # article id -> title, e.g. "B3" -> "PROCEDURES DURING A COMPETITION"
    clause_titles = {}    # clause id -> title, e.g. "B3.5" -> "Pre-Sprint & Pre-Race Parc Fermé"
    units = []

    current_article = None   # e.g. "B3" or "40"
    current_art_num = None   # integer part, used for sequence checks
    last_tuple = None
    in_appendix = None       # (id, title) when inside an appendix
    appendix_lines = []
    started = False
    unit = None
    excluded_skip = False

    def close_unit():
        nonlocal unit
        if unit is not None:
            units.append(unit)
        unit = None

    def flush_appendix():
        nonlocal appendix_lines
        if in_appendix and appendix_lines and not excluded_skip:
            units.append(("APPENDIX", in_appendix, appendix_lines))
        appendix_lines = []

    for page, line in lines:
        s = line.strip()

        # Future-season appendices come at the end of the document and contain
        # their own ARTICLE/APPENDIX headings, so once one starts, skip the rest.
        if excluded_skip:
            continue

        #  article headings 
        m_art = NEW_ARTICLE.match(s) if is_new else (OLD_ARTICLE_TECH.match(s) or OLD_ARTICLE_SPORT.match(s))
        if m_art:
            title = m_art.groups()[-1]
            if TOC_TRAILING_PAGE.search(title):          # table-of-contents line
                continue
            close_unit(); flush_appendix()
            in_appendix = None; excluded_skip = False
            if is_new:
                current_article = f"{m_art.group(1)}{m_art.group(2)}"
                current_art_num = int(m_art.group(2))
            else:
                current_article = m_art.group(1)
                current_art_num = int(m_art.group(1))
            article_titles.setdefault(current_article, title.strip())
            last_tuple = None
            started = True
            continue

        #  appendix headings 
        m_app = APPENDIX.match(s)
        app_title = (m_app.group(2) or "").strip() if m_app else ""
        if m_app and started and not TOC_TRAILING_PAGE.search(app_title):
            close_unit(); flush_appendix()
            in_appendix = (f"Appendix {m_app.group(1)}", app_title, page)
            excluded_skip = bool(EXCLUDED_APPENDIX.search(app_title))
            current_article = None
            continue

        if not started:
            continue
        if in_appendix:
            if not excluded_skip:
                appendix_lines.append((page, s))
            continue

        #  numbered clauses 
        m_cl = NEW_CLAUSE.match(s) if is_new else OLD_CLAUSE.match(s)
        if m_cl and current_article:
            if is_new:
                letter, nums, suffix, rest = m_cl.groups()
                cid = f"{letter}{nums}"
                ok_prefix = letter == current_article[0]
            else:
                nums, rest = m_cl.groups()
                cid = nums
                ok_prefix = True
            tup = tuple(int(n) for n in nums.split("."))
            starts_ok = rest[:1].isupper() or rest[:1].isdigit() or rest[:1] in "“\"'("
            # Table rows that begin with a clause number (e.g. a test matrix row
            # "C13.5.4 SIS Squeeze Yes Yes Yes No") are not clause headings.
            if TABLE_ROW.search(rest):
                starts_ok = False
            if ok_prefix and tup[0] == current_art_num and starts_ok and _plausible_next(last_tuple, tup):
                close_unit()
                last_tuple = tup
                unit = _Unit(cid, current_article, page, None)
                if _looks_like_title(rest):
                    unit.title = rest.strip()
                    clause_titles[cid] = unit.title
                else:
                    unit.lines.append(rest)
                continue

        #  ordinary text line 
        if unit is not None:
            unit.lines.append(s)
    close_unit(); flush_appendix()

    #  turn units into chunks 
    chunks = []
    for u in units:
        if isinstance(u, tuple):                       # appendix
            _, (app_id, app_title, app_page), app_lines = u
            chunks.extend(_window_chunks(app_lines, season, doc_name, doc_type, pdf_path,
                                         app_id, app_title))
            continue
        body = "\n".join(u.lines).strip()
        if not body:
            continue                                   # pure heading, already stored as a title
        art_title = article_titles.get(u.article, "")
        crumbs = [f"Article {u.article}: {art_title.title()}"]
        parts = u.cid.split(".")
        for depth in range(2, len(parts)):             # ancestors like B3.5
            anc = ".".join(parts[:depth])
            if anc in clause_titles:
                crumbs.append(f"{anc} {clause_titles[anc]}")
        heading = f"{u.cid} {u.title}" if u.title else u.cid
        for i, piece in enumerate(_split_long(body)):
            label = heading if i == 0 else f"{heading} (continued)"
            text = f"{doc_name} | {' > '.join(crumbs)}\n{label}\n{piece}"
            chunks.append({
                "id": f"{season}-{doc_type}-{u.cid}" + (f"-p{i+1}" if i else ""),
                "text": text,
                "metadata": {
                    "source_type": "regulation",
                    "season": season,
                    "doc_type": doc_type,
                    "doc_name": doc_name,
                    "file": pdf_path.name,
                    "article": u.article,
                    "article_title": art_title,
                    "clause": u.cid,
                    "clause_title": u.title or "",
                    "page": u.page,
                },
            })
    return chunks


def _split_long(body):
    if len(body) <= MAX_CHARS:
        return [body]
    pieces, cur = [], ""
    for line in body.split("\n"):
        if len(cur) + len(line) > MAX_CHARS and cur:
            pieces.append(cur.strip()); cur = ""
        cur += line + "\n"
    if cur.strip():
        pieces.append(cur.strip())
    return pieces


def _window_chunks(app_lines, season, doc_name, doc_type, pdf_path, app_id, app_title):
    chunks, cur, start_page, n = [], [], None, 0
    def emit():
        nonlocal cur, n
        if not cur:
            return
        n += 1
        chunks.append({
            "id": f"{season}-{doc_type}-{app_id.replace(' ', '')}-w{n}",
            "text": f"{doc_name} | {app_id}" + (f": {app_title.title()}" if app_title else "") + "\n" + "\n".join(cur),
            "metadata": {
                "source_type": "regulation", "season": season, "doc_type": doc_type,
                "doc_name": doc_name, "file": pdf_path.name, "article": app_id,
                "article_title": app_title, "clause": f"{app_id} (part {n})",
                "clause_title": "", "page": start_page,
            },
        })
        cur = []
    for page, line in app_lines:
        if start_page is None or not cur:
            start_page = page
        cur.append(line)
        if sum(len(l) for l in cur) >= APPENDIX_WINDOW:
            emit()
    emit()
    return chunks
