# F1 Rules Explained: a RAG assistant for the FIA Formula 1 regulations

Ask a question about the Formula 1 rules in everyday words ("What happens if a team breaks
parc fermé?", "Why was Perez penalised in China?") and get an answer that is looked up in the
official FIA documents, with every claim cited to the exact rule or stewards' decision.

The project is a **retrieval-augmented generation (RAG)** pipeline: the regulations are split
into rule-sized chunks, embedded into a local vector database, and the most relevant chunks are
passed to an LLM that must answer *only* from them. On a 92-question test set it scores
**82%**, against **26%** for the same LLM answering from memory (see [Results](#results)).

## What it knows

| Source | Coverage |
|---|---|
| 2025 F1 Sporting and Technical Regulations | full documents |
| 2026 F1 Regulations, Sections A (General), B (Sporting), C (Technical) | full documents |
| 2026 stewards' decisions | 167 documents from 9 races: Australia → Great Britain |

It does not know race results, standings or news. If the documents don't contain the answer,
it says so instead of guessing.

## Quick start

Requires **Python 3.11** and free API keys for [Google Gemini](https://aistudio.google.com/apikey)
and/or [Groq](https://console.groq.com/keys). Commands are for Windows PowerShell, run from the
project folder.

```powershell
# 1. Create a virtual environment and install the dependencies
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Add your API keys
copy .env.example .env
#    then open .env and fill in GEMINI_API_KEY / GROQ_API_KEY and the model names

# 3. Check the keys work (lists the models your keys can use)
python src/check_llm.py

# 4. Build the search index (a few minutes, runs locally, no API calls)
python src/index.py

# 5. Start the website
python app.py
```

Then open **http://127.0.0.1:7860**.

The first run of steps 4 and 5 downloads the embedding model (about 130 MB), so it needs
internet. On macOS/Linux, activate with `source venv/bin/activate` and use `cp` instead of `copy`.

> **Never commit or share `.env`.** It holds your API keys and is excluded by `.gitignore`.

### Configuration (`.env`)

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER`, `LLM_MODEL` | Main model that writes answers (`gemini` or `groq`) |
| `FALLBACK_PROVIDER`, `FALLBACK_MODEL` | Used automatically if the main model stays unavailable |
| `REWRITE_PROVIDER`, `REWRITE_MODEL` | *Optional:* a cheaper model for query rewriting (defaults to the main model) |
| `JUDGE_PROVIDER`, `JUDGE_MODEL` | Model that grades answers during evaluation, ideally a different provider |
| `GEMINI_API_KEY`, `GROQ_API_KEY` | Your API keys |

## Using the website

1. Type a question, or click one of the example questions.
2. The answer shows which season's rules it is based on (2026 unless you name another season)
   and cites its sources in square brackets, e.g. `[B3.5.3]` or `[Chinese GP Doc 49]`.
3. Open **Where this answer comes from** to read the original text of each source.
4. **Advanced settings** exposes the retrieval options used in the evaluation. The defaults
   are the best-scoring configuration.

## How it works

```
PDFs ──► parse & chunk ──► embed (bge-small) ──► Chroma vector DB
                                                     │
question ──► season detection ──► query rewrite ──► hybrid search (embeddings + BM25)
                                                     │
                          entity filter (driver / race / car) ──► top-5 chunks ──► LLM ──► cited answer
```

- **Article-based chunking:** each chunk is one numbered clause (e.g. `B3.5.3`), prefixed with
  its document › article › subsection breadcrumb so it makes sense on its own. Stewards'
  decisions are parsed into structured fields (driver, car, session, infringement, decision).
- **Season-aware retrieval:** "in 2025" searches only the 2025 rules; comparison questions
  ("what changed from 2025 to 2026") search both seasons; otherwise the 2026 rules are used.
  This cut the share of retrieved chunks from the wrong season ("year confusion") from 41% to 4%.
- **Hybrid search:** dense embeddings (`BAAI/bge-small-en-v1.5`) plus BM25 keyword search,
  merged with Reciprocal Rank Fusion. BM25 catches exact names and rule numbers.
- **Entity-aware filtering:** driver names, races (including nicknames like "Silverstone") and
  car numbers are matched against the stewards' metadata; matching decisions are ranked first,
  but only for incident-type questions.
- **Query rewriting:** one LLM call restates everyday wording in FIA vocabulary
  ("pouring rain" → "wet-weather start behind the Safety Car"). Rewrites are cached.
- **Grounded generation:** the LLM must use only the retrieved sources, cite every claim and
  refuse when the answer isn't there. Temperature is 0 for repeatable answers.

## Results

Test set: 92 hand-verified questions across 8 categories, including 7 deliberately
unanswerable ones. Answers are graded by a separate judge LLM (correct = 1, partial = 0.5).

| Configuration | Hit@5 | MRR | Answer score | Unanswerable handled |
|---|---|---|---|---|
| Closed book (LLM only, no retrieval) | – | – | 26% | 4/7 |
| Article chunks, dense search | 80% | 0.66 | 76% | 7/7 |
| + hybrid search | 91% | 0.70 | 79% | 7/7 |
| **Final** (+ incident-only entity filter, query rewriting) | **91%** | **0.73** | **82%** | **7/7** |

Full tables, including per-category scores and all retrieval variants, are in
[eval/results/summary.md](eval/results/summary.md).

**Known weakness:** questions in casual fan language are the hardest category (55%), because
their wording is furthest from the regulations' vocabulary.

### Reproducing the evaluation

```powershell
python eval/evaluate.py retrieval              # retrieval metrics, local, a few minutes
python eval/evaluate.py answers final          # generate + grade answers (slow: API rate limits; resumes if stopped)
python eval/evaluate.py report                 # rebuild eval/results/summary.md
```

## Project structure

```
app.py                     Gradio website
src/
  config.py                Shared settings (paths, embedding model, k, default season)
  pdf_text.py              PDF text extraction with page cache and header/footer cleaning
  parse_regs.py            Article-based chunking of the regulations (2025 and 2026 formats)
  parse_stewards.py        Parser for stewards' decision documents
  build_chunks.py          Parses every PDF in data/raw → data/processed/chunks_*.jsonl
  index.py                 Embeds the chunks into the Chroma vector store
  rag.py                   Retrieval (season, hybrid, entity filter, rewrite) + answer generation
  llm.py                   Gemini / Groq wrapper with retries and fallback
  check_llm.py, test_llm.py  API key checks
eval/
  make_questions.py        Builds the test set with gold source labels
  questions.csv            The 92-question test set
  evaluate.py              Retrieval and answer evaluation
  results/                 Saved answers, per-question scores and summary.md
data/
  raw/                     Source PDFs (2025, 2026, stewards/2026/<round>-<race>/)
  processed/               Chunk files, rewrite cache, and a page-text cache
vectorstore/               Chroma database (generated by index.py, not in git)
```

## Adding new races or documents

1. Put the stewards' PDFs in a new folder `data/raw/stewards/2026/<round>-<race>/`, e.g.
   `10-belgium`, keeping the FIA's file names (`2026 Belgian Grand Prix - Decision - Car 16 - ….pdf`).
   The parser reads the race and title from the file name.
2. Optionally add circuit nicknames for the race to `RACE_ALIASES` in `src/rag.py`.
3. Rebuild: `python src/build_chunks.py`, then `python src/index.py`.
   Run `build_chunks.py` **without arguments**: `build_chunks.py stewards` rewrites the chunk
   files without the regulations.

The website's coverage list updates itself from the data.

## Disclaimer

Unofficial academic project, not affiliated with Formula 1, the FIA or any team. The regulation
and stewards' documents are © FIA and are included for study purposes. Answers are generated
by an AI from those documents and can contain mistakes, so check the cited rule for anything important.
