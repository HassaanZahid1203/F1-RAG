# Step 5a: embed all chunks into a local Chroma DB (rebuilds from scratch).
# Run: python src/index.py [collection]
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import COLLECTIONS, EMBED_MODEL, VECTORSTORE

import chromadb
from sentence_transformers import SentenceTransformer

BATCH = 500


def load_chunks(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def clean_metadata(md):
    """Chroma only accepts str/int/float/bool values and no None."""
    out = {}
    for k, v in md.items():
        if v is None:
            continue
        if isinstance(v, list):
            v = ", ".join(map(str, v))
        if isinstance(v, (str, int, float, bool)):
            out[k] = v
    return out


def build(name, model, client):
    chunks = load_chunks(COLLECTIONS[name])
    print(f"\n[{name}] embedding {len(chunks)} chunks with {EMBED_MODEL} ...")
    t0 = time.time()
    vectors = model.encode([c["text"] for c in chunks], batch_size=32,
                           normalize_embeddings=True, show_progress_bar=True)
    try:
        client.delete_collection(name)
    except Exception:
        pass
    col = client.create_collection(name)
    for i in range(0, len(chunks), BATCH):
        part = chunks[i:i + BATCH]
        col.add(ids=[c["id"] for c in part],
                documents=[c["text"] for c in part],
                embeddings=[v.tolist() for v in vectors[i:i + BATCH]],
                metadatas=[clean_metadata(c["metadata"]) for c in part])
    print(f"[{name}] stored {col.count()} chunks in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    names = sys.argv[1:] or list(COLLECTIONS)
    model = SentenceTransformer(EMBED_MODEL)
    client = chromadb.PersistentClient(path=str(VECTORSTORE))
    for n in names:
        build(n, model, client)
    print("\nDone. Vector database saved in vectorstore/")
