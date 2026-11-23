# Parser for FIA stewards' decisions: labelled fields (Driver, Fact, Decision,
# Reason, ...) become metadata; long-form docs without them are split into
# ~WINDOW-character windows.
import re
from pathlib import Path

from pdf_text import extract_pages

WINDOW = 1500

LABELS = ["No / Driver", "Competitor", "Time", "Session", "Fact",
          "Infringement", "Decision", "Reasons", "Reason", "Note"]
LABEL_RE = re.compile(r"^(" + "|".join(re.escape(l) for l in LABELS) + r")\s*(.*)$")
BODY_START = re.compile(r"(The Stewards, having|^1\.\s+The Stewards)", re.M)
BOILERPLATE = re.compile(r"Competitors are reminded|Decisions of the Stewards are taken independently")
ARTICLE_REF = re.compile(r"\b([A-F]\d+(?:\.\d+)+[a-z]?)\b")
DATE_RE = re.compile(r"Date\s+(\d{1,2}\s+[A-Z][a-z]+\s+20\d\d)")
DOCNO_RE = re.compile(r"Document\s+(\d+)")


def _meta_from_path(pdf_path: Path):
    """Round, race and document type from folder + file name."""
    folder = pdf_path.parent.name                     # e.g. "02-china"
    m = re.match(r"(\d+)-(.+)", folder)
    rnd = int(m.group(1)) if m else None
    slug = m.group(2) if m else folder
    stem = pdf_path.stem.replace("_", " ")
    stem = re.sub(r"^doc \d+ - ", "", stem, flags=re.I)
    stem = re.sub(r"\s*\(\d\)$", "", stem)            # browser duplicate-name suffix
    parts = [p.strip() for p in re.split(r"\s+-\s+", stem)]
    race = parts[0] if parts else folder               # "2026 Chinese Grand Prix"
    kind = parts[1].lower() if len(parts) > 1 else "decision"
    title = " - ".join(parts[2:]) if len(parts) > 2 else ""
    doc_kind = "infringement" if "infringement" in kind else "decision"
    return rnd, race.title().replace("Gp", "GP"), doc_kind, title, slug


def parse_stewards_doc(pdf_path):
    pdf_path = Path(pdf_path)
    pages = extract_pages(pdf_path)
    full = "\n".join(pages)
    rnd, race, doc_kind, title, slug = _meta_from_path(pdf_path)

    # Skip the cover page: the ruling starts at the LAST "From The Stewards" block.
    m = BODY_START.search(full)
    header_zone = full[:m.start()] if m else full[:600]
    # Use the last Document/Date in the header zone (the ruling, not the cover).
    docnos = DOCNO_RE.findall(header_zone)
    dates = DATE_RE.findall(header_zone)
    doc_no = int(docnos[-1]) if docnos else None
    date = dates[-1] if dates else ""
    body = full[m.start():] if m else full
    cut = BOILERPLATE.search(body)
    if cut:
        body = body[:cut.start()]
    body = re.sub(r"\n?Note\s*$", "", body.strip())

    # ---- extract labelled fields (only after "determine the following") ----
    fields, current = {}, None
    after = re.split(r"determine\s+the\s+following", body, maxsplit=1)
    field_zone = after[1] if len(after) > 1 else ""
    for line in field_zone.split("\n"):
        lm = LABEL_RE.match(line.strip())
        if lm and lm.group(1) not in fields:
            current = "Reason" if lm.group(1) == "Reasons" else lm.group(1)
            fields[current] = lm.group(2).strip()
        elif current:
            fields[current] += "\n" + line.strip()
    fields = {k: v.strip(" :\n") for k, v in fields.items() if v.strip()}

    driver = fields.get("No / Driver", "")
    car = re.match(r"(\d+)", driver) or re.search(r"\bCar\s+0?(\d+)", title, re.I)
    base_meta = {
        "source_type": "stewards",
        "season": 2026,
        "doc_type": "stewards",
        "doc_kind": doc_kind,                 # infringement | decision
        "file": pdf_path.name,
        "round": rnd,
        "race": race,
        "race_slug": slug,
        "document_no": doc_no,
        "date": date,
        "title": title,
        "car": int(car.group(1)) if car else None,
        "driver": re.sub(r"^\d+\s*-\s*", "", driver).strip(),
        "team": fields.get("Competitor", ""),
        "session": fields.get("Session", ""),
        "decision": fields.get("Decision", ""),
        "articles_cited": sorted(set(ARTICLE_REF.findall(body))),
    }
    header = (f"Stewards' {doc_kind} | {race} (Round {rnd}) | Document {doc_no}, {date}"
              f"\nTitle: {title}")
    summary = entity_summary(base_meta)

    # ---- standard ruling: one chunk ----
    if "Fact" in fields and "Decision" in fields:
        order = ["No / Driver", "Competitor", "Session", "Fact", "Infringement", "Decision", "Reason"]
        lines = [f"{k}: {fields[k]}" for k in order if k in fields]
        return [{
            "id": f"stewards-r{rnd:02d}-doc{doc_no}",
            "text": header + "\n" + "\n".join(lines),
            "metadata": base_meta,
            "summary": summary,
        }]

    # ---- long-form document: windows ----
    chunks, cur, n = [], "", 0
    for para in re.split(r"\n(?=\d+\.\s)", body):
        if len(cur) + len(para) > WINDOW and cur:
            n += 1
            chunks.append({"id": f"stewards-r{rnd:02d}-doc{doc_no}-w{n}",
                           "text": header + f" (part {n})\n" + cur.strip(),
                           "metadata": base_meta, "summary": summary})
            cur = ""
        cur += para + "\n"
    if cur.strip():
        n += 1
        chunks.append({"id": f"stewards-r{rnd:02d}-doc{doc_no}-w{n}",
                       "text": header + f" (part {n})\n" + cur.strip(),
                       "metadata": base_meta, "summary": summary})
    return chunks


def entity_summary(md):
    """
    One sentence naming the key entities (driver, car, team, race, session, outcome).
    Prepended to the chunk text in the 'article_ent' collection, so the embedding
    of the chunk is dominated by WHO, WHERE and WHAT rather than boilerplate.
    """
    who = []
    if md.get("driver"):
        who.append(md["driver"])
    if md.get("car") is not None:
        who.append(f"Car {md['car']}")
    if md.get("team"):
        who.append(re.sub(r"\s*Formula\s*(1|One)\s*Team", "", md["team"], flags=re.I).strip())
    subject = (f"{who[0]} ({', '.join(who[1:])})" if len(who) > 1 else who[0]) if who else "multiple cars"
    session = f", {md['session']}" if md.get("session") else ""
    outcome = re.sub(r"\s+", " ", md.get("decision", "")).strip().rstrip(".")
    s = f"Stewards' {md['doc_kind']} about {subject} at the {md['race']}{session}: {md.get('title', '')}."
    if outcome:
        s += f" Outcome: {outcome}."
    return s
