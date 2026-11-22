"""Shared settings for indexing, retrieval and the app."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED = PROJECT_ROOT / "data" / "processed"
VECTORSTORE = PROJECT_ROOT / "vectorstore"

# Embedding model (runs locally on CPU, downloads ~130 MB on first use).
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
# BGE models work best when QUERIES (not documents) get this instruction prefix.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

# Chunk sets built in Step 2 -> one Chroma collection each.
COLLECTIONS = {
    "article": PROCESSED / "chunks_article.jsonl",   # article-based chunking (main)
    "article_ent": PROCESSED / "chunks_article_ent.jsonl",  # + entity summaries on stewards' chunks
    "fixed": PROCESSED / "chunks_fixed.jsonl",       # fixed-size chunking (baseline)
}

TOP_K = 5                 # chunks retrieved per question (per season for comparisons)
DEFAULT_SEASON = 2026     # used when a question names no season
SEASONS = (2025, 2026)
