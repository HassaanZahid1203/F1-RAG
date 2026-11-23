# Step 5b: retrieval + generation.  RAG().answer("...")["answer"]
# Options:
#   hybrid=True                dense + BM25 merged with RRF (better on names, numbers)
#   entity_filter=True         stewards' docs matching named drivers/races/car numbers go first
#   entity_incident_only=True  apply that filter only to incident questions
#   rewrite=True               LLM restates the query in FIA wording (cached); original kept too
#   season_filter=True         named season only; each season for comparisons; else DEFAULT_SEASON
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (DEFAULT_SEASON, EMBED_MODEL, PROCESSED, QUERY_PREFIX, SEASONS,
                    TOP_K, VECTORSTORE)
from llm import LLM

SYSTEM_PROMPT = """You answer questions about the FIA Formula 1 regulations and the FIA stewards' decisions.

Rules:
1. Use ONLY the numbered sources provided. Never add facts from your own knowledge.
2. Cite every claim with the source label in square brackets, for example [B3.5.3] or [Monaco GP Doc 85].
3. If the sources do not contain the answer, reply exactly:
   "I couldn't find this in the regulations and stewards' documents I have."
4. Say which season's regulations your answer is based on.
5. Be concise and precise. Quote numbers (times, distances, penalties) exactly as the sources give them."""

CLOSED_BOOK_PROMPT = """You answer questions about the FIA Formula 1 regulations.
Answer from your own knowledge, concisely. If you are not sure, say so."""

INCIDENT_WORDS = re.compile(
    r"\b(penal\w*|fine[ds]?|stewards?|why|investigat\w*|incident\w*|collision|collid\w*|crash\w*|"
    r"disqualif\w*|reprimand\w*|warning|summon\w*|infringement\w*|decision\w*|happened)\b", re.I)

REWRITE_PROMPT = """Rewrite the user's question about Formula 1 so it uses the formal vocabulary of the
FIA Formula 1 Sporting and Technical Regulations, to help a search engine find the right rule.
- Keep every name, year, race, car number and number from the question.
- Add the formal terms the rulebook would use (e.g. "minimum mass" for weight, "track conditions
  unsuitable" for heavy rain, "Pit Lane", "Safety Car", "Power Unit elements", "parc fermé").
- Do not answer the question. Output only the rewritten search query, at most 40 words."""
REWRITE_CACHE = PROCESSED / "rewrite_cache.json"

COMPARE_WORDS = re.compile(
    r"\b(chang\w*|differ\w*|compar\w*|versus|vs\.?|new (for|in)|previous(ly)?|last year|anymore|no longer)\b",
    re.I)

_embedder = None
_client = None


def _get_embedder():
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer(EMBED_MODEL)
    return _embedder


def _get_client():
    global _client
    if _client is None:
        import chromadb
        _client = chromadb.PersistentClient(path=str(VECTORSTORE))
    return _client


STOPWORDS = set("""a an and are as at be by did do does for from has have how i if in
is it its of on or the to was were what when where which who why will with""".split())
_bm25_cache = {}   # collection name -> {season or None: (BM25Okapi, [records])}


def tokenize(text):
    """Lowercase, strip accents (fermé -> ferme), keep article ids like b3.5.3 intact."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return [t for t in re.findall(r"[a-z0-9]+(?:\.[a-z0-9]+)*", text) if t not in STOPWORDS]


def _get_bm25(col):
    """Build BM25 indexes (one per season + one over everything) the first time they're needed."""
    if col.name not in _bm25_cache:
        from rank_bm25 import BM25Okapi
        data = col.get(include=["documents", "metadatas"])
        records = [{"id": i, "text": d, "metadata": m}
                   for i, d, m in zip(data["ids"], data["documents"], data["metadatas"])]
        groups = {None: records}
        for season in SEASONS:
            groups[season] = [r for r in records if r["metadata"].get("season") == season]
        _bm25_cache[col.name] = {key: (BM25Okapi([tokenize(r["text"]) for r in recs]), recs)
                                 for key, recs in groups.items() if recs}
    return _bm25_cache[col.name]


def rrf_merge(ranked_lists, k=60):
    """Reciprocal Rank Fusion: score = sum over lists of 1 / (k + rank)."""
    scores, items = {}, {}
    for ranked in ranked_lists:
        for rank, hit in enumerate(ranked, start=1):
            scores[hit["id"]] = scores.get(hit["id"], 0) + 1 / (k + rank)
            items.setdefault(hit["id"], hit)
    order = sorted(scores, key=scores.get, reverse=True)
    return [{**items[i], "rrf": scores[i]} for i in order]


# Extra names people use for races (circuits / countries), keyed by folder slug.
RACE_ALIASES = {
    "australia": ["melbourne", "albert park"], "china": ["shanghai"], "japan": ["suzuka"],
    "miami": [], "canada": ["montreal"], "monaco": ["monte carlo"],
    "barcelona-catalunya": ["barcelona", "catalunya", "catalonia", "spain", "spanish"],
    "austria": ["red bull ring", "spielberg"], "great-britain": ["silverstone", "britain", "uk"],
}
DRIVER_ALIASES = {"Sergio Perez": ["checo"], "Kimi Antonelli": ["kimi"]}
_entity_cache = {}


def _norm(text):
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def _entity_vocab(col):
    """Map surface forms (e.g. 'perez', 'chinese', 'shanghai') to metadata values."""
    if col.name not in _entity_cache:
        mds = col.get(where={"source_type": "stewards"}, include=["metadatas"])["metadatas"]
        races, drivers = {}, {}
        for md in mds:
            race, slug = md.get("race"), md.get("race_slug", "")
            if race:
                words = [w for w in re.findall(r"[a-z]+", _norm(race)) if w not in ("grand", "prix")]
                for form in words + [slug.replace("-", " ")] + RACE_ALIASES.get(slug, []):
                    races.setdefault(form, set()).add(race)
            if md.get("driver") and md.get("car") is not None:
                full = md["driver"]
                for form in [_norm(full), _norm(full.split()[-1])] + DRIVER_ALIASES.get(full, []):
                    drivers.setdefault(form, set()).add(md["car"])
        _entity_cache[col.name] = (races, drivers)
    return _entity_cache[col.name]


def detect_entities(question, col):
    """Return {'races': [...], 'cars': [...]} found in the question."""
    races_vocab, drivers_vocab = _entity_vocab(col)
    q = _norm(question)
    found = {"races": set(), "cars": set()}
    for form, races in races_vocab.items():
        if re.search(rf"\b{re.escape(form)}\b", q):
            found["races"] |= races
    named_driver = False
    for form, cars in drivers_vocab.items():
        if re.search(rf"\b{re.escape(form)}\b", q):
            found["cars"] |= cars
            named_driver = True
    for num in re.findall(r"\bcar\s*(?:no\.?|number|#)?\s*(\d{1,2})\b", q):
        found["cars"].add(int(num))
    result = {k: sorted(v) for k, v in found.items() if v}
    if named_driver:
        result["named_driver"] = True      # used by the incident-only gate, ignored by the filter
    return result


def entity_where(entities):
    conds = [{"source_type": "stewards"}]
    if entities.get("races"):
        conds.append({"race": {"$in": entities["races"]}})
    if entities.get("cars"):
        conds.append({"car": {"$in": entities["cars"]}})
    return {"$and": conds}


def detect_seasons(question):
    """Return (list_of_seasons, mode) where mode is 'named', 'compare' or 'default'."""
    years = sorted({int(y) for y in re.findall(r"\b(20\d\d)\b", question) if int(y) in SEASONS})
    if len(years) >= 2 or (COMPARE_WORDS.search(question) and len(years) <= 1):
        return list(SEASONS), "compare"
    if years:
        return years, "named"
    return [DEFAULT_SEASON], "default"


def source_label(md):
    """Short citation label for a chunk, e.g. 'B3.5.3' or 'Monaco GP Doc 85'."""
    if md.get("source_type") == "stewards":
        race = md.get("race", "").replace(f"{md.get('season', '')} ", "").replace("Grand Prix", "GP")
        return f"{race} Doc {md.get('document_no', '?')}"
    clause = md.get("clause")
    if clause:
        return f"{clause}" if md.get("season", 0) >= 2026 else f"{md['season']} Art. {clause}"
    return f"{md.get('doc_name', 'regulations')} p.{md.get('page', '?')}"


class RAG:
    def __init__(self, collection="article", k=TOP_K, season_filter=True, hybrid=False,
                 entity_filter=False, entity_incident_only=False, rewrite=False, llm=None):
        self.collection_name = collection
        self.k = k
        self.hybrid = hybrid
        self.entity_filter = entity_filter
        self.entity_incident_only = entity_incident_only
        self.rewrite = rewrite
        self.last_rewrite = None
        self._rewrite_llm = None
        self.season_filter = season_filter
        self.col = _get_client().get_collection(collection)
        self.llm = llm or LLM()

    # ---------------- query rewriting ----------------
    def _get_rewrite_llm(self):
        """REWRITE_PROVIDER / REWRITE_MODEL in .env pick a separate (cheap) model for
        rewriting; otherwise the main answer model is used."""
        if self._rewrite_llm is None:
            import os
            prov, model = os.getenv("REWRITE_PROVIDER"), os.getenv("REWRITE_MODEL")
            self._rewrite_llm = LLM(provider=prov, model=model, fallback=False) if (prov and model) else self.llm
        return self._rewrite_llm

    def rewrite_query(self, question):
        cache = {}
        if REWRITE_CACHE.exists():
            cache = json.loads(REWRITE_CACHE.read_text(encoding="utf-8"))
        rw_llm = self._get_rewrite_llm()
        key = f"{rw_llm.name}||{question}"
        if key not in cache:
            cache[key] = rw_llm.generate(question, system=REWRITE_PROMPT).strip()
            REWRITE_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
            time.sleep(2)          # gentle on free-tier rate limits
        return cache[key]

    # ---------------- retrieval ----------------
    def retrieve(self, question):
        seasons, mode = detect_seasons(question)          # always from the ORIGINAL question
        query = question
        self.last_rewrite = None
        if self.rewrite:
            self.last_rewrite = self.rewrite_query(question)
            query = f"{question}\n{self.last_rewrite}"
        qvec = _get_embedder().encode(QUERY_PREFIX + query, normalize_embeddings=True).tolist()

        if not self.season_filter:
            groups = [None]
        else:
            groups = seasons

        entities = detect_entities(question, self.col) if self.entity_filter else {}
        if entities and self.entity_incident_only:
            # Only filter for incident questions: a named driver, or incident words.
            # A bare race name ("is Monaco different?") or car number ("who may use
            # car number 1?") in a rules question does not count.
            if not (entities.get("named_driver") or INCIDENT_WORDS.search(question)):
                entities = {}
        hits = []
        for season in groups:
            # In hybrid mode, fetch a wider candidate pool from each method before fusing.
            n = self.k * 4 if self.hybrid else self.k
            res = self.col.query(query_embeddings=[qvec], n_results=n,
                                 where={"season": season} if season else None)
            dense = [{"id": cid, "text": doc, "metadata": md, "distance": dist}
                     for doc, md, dist, cid in zip(res["documents"][0], res["metadatas"][0],
                                                   res["distances"][0], res["ids"][0])]
            group_hits = None
            if self.hybrid:
                bm25, recs = _get_bm25(self.col)[season]
                scores = bm25.get_scores(tokenize(query))
                top = sorted(range(len(recs)), key=lambda i: scores[i], reverse=True)[:n]
                keyword = [{**recs[i], "distance": None} for i in top if scores[i] > 0]
                # keep the dense distance for display when a chunk appears in both lists
                dist_by_id = {h["id"]: h["distance"] for h in dense}
                fused = rrf_merge([dense, keyword])[:self.k]
                for h in fused:
                    h["distance"] = dist_by_id.get(h["id"])
                group_hits = fused
            else:
                group_hits = dense[:self.k]

            # Entity-aware filtering: stewards' docs matching the named driver/race/car
            # go first; normal results fill the remaining slots. Stewards' documents
            # exist only for 2026, so only that season (or an unfiltered search) is affected.
            if entities and season in (None, 2026):
                res = self.col.query(query_embeddings=[qvec], n_results=self.k,
                                     where=entity_where(entities))
                ent = [{"id": cid, "text": doc, "metadata": md, "distance": dist, "entity": True}
                       for doc, md, dist, cid in zip(res["documents"][0], res["metadatas"][0],
                                                     res["distances"][0], res["ids"][0])]
                seen = {h["id"] for h in ent}
                group_hits = (ent + [h for h in group_hits if h["id"] not in seen])[:self.k]
            hits.extend(group_hits)

        for h in hits:
            h["label"] = source_label(h["metadata"])
        # Entity matches first, then by relevance score.
        if self.hybrid:
            hits.sort(key=lambda h: (not h.get("entity"), -h.get("rrf", 0)))
        else:
            hits.sort(key=lambda h: (not h.get("entity"), h["distance"] if h["distance"] is not None else 9))
        self.last_entities = entities
        return hits, seasons, mode

    # ---------------- generation ----------------
    def answer(self, question):
        hits, seasons, mode = self.retrieve(question)
        context = "\n\n".join(f"[{h['label']}] ({h['metadata'].get('doc_name') or 'Stewards decision'})\n{h['text']}"
                              for h in hits)
        if self.season_filter and mode == "default":
            note = f"The question names no season; the sources are from the {DEFAULT_SEASON} season."
        elif self.season_filter and mode == "compare":
            note = "The question compares seasons; sources from 2025 and 2026 are both provided."
        else:
            note = ""
        prompt = f"{note}\n\nSources:\n{context}\n\nQuestion: {question}".strip()
        text = self.llm.generate(prompt, system=SYSTEM_PROMPT)
        return {"answer": text, "sources": hits, "seasons": seasons, "mode": mode,
                "model": self.llm.last_model, "entities": self.last_entities,
                "rewrite": self.last_rewrite}


def closed_book(question, llm=None):
    """Baseline: the LLM answers with no retrieval at all."""
    return (llm or LLM()).generate(question, system=CLOSED_BOOK_PROMPT)


if __name__ == "__main__":
    # Flags: --hybrid  --entities  --entities-incident  --rewrite  --collection=article|article_ent|fixed
    args = sys.argv[1:]
    flags = {a for a in args if a.startswith("--")}
    collection = next((a.split("=", 1)[1] for a in flags if a.startswith("--collection=")), "article")
    q = " ".join(a for a in args if not a.startswith("--")) or "What happens if a car breaks parc ferme conditions?"
    bot = RAG(collection=collection, hybrid="--hybrid" in flags,
              entity_filter="--entities" in flags or "--entities-incident" in flags,
              entity_incident_only="--entities-incident" in flags, rewrite="--rewrite" in flags)
    r = bot.answer(q)
    print(f"Collection: {collection} | retrieval: {'hybrid' if bot.hybrid else 'dense'}"
          f" | entity filter: {'on ' + str(r['entities']) if bot.entity_filter else 'off'}")
    if r.get("rewrite"):
        print("Rewritten query:", r["rewrite"])
    print("\nQ:", q)
    print(f"Seasons searched: {r['seasons']} ({r['mode']})   Answered by: {r['model']}")
    print("\nA:", r["answer"])
    print("\nSources:")
    for h in r["sources"]:
        d = f"distance={h['distance']:.3f}" if h.get("distance") is not None else "keyword match only"
        tag = " [entity match]" if h.get("entity") else ""
        print(f"  [{h['label']}] {d}{tag}  {h['metadata'].get('doc_name') or h['metadata'].get('title', '')}")
