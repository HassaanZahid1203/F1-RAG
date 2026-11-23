# Step 7: evaluation - retrieval metrics, answer generation + LLM judging, reports.
# Run from the project root; see USAGE below. Questions marked verified=removed are skipped.
import csv
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
RESULTS = ROOT / "eval" / "results"
RESULTS.mkdir(parents=True, exist_ok=True)

USAGE = """\
python eval/evaluate.py retrieval               retrieval metrics for all configs (local, no API)
python eval/evaluate.py answers <config> ...    generate + judge answers (slow; resumes on re-run)
python eval/evaluate.py rejudge <QID> ...       re-grade saved answers without regenerating
python eval/evaluate.py report                  rebuild eval/results/summary.md"""

# ---------------------------------------------------------------------------
# Configurations. Each one is a RAG(...) setup; closed_book uses no retrieval.
# ---------------------------------------------------------------------------
CONFIGS = {
    "closed_book":        None,
    "fixed_dense":        dict(collection="fixed",       hybrid=False, entity_filter=False, season_filter=True),
    "article_dense":      dict(collection="article",     hybrid=False, entity_filter=False, season_filter=True),
    "article_no_season":  dict(collection="article",     hybrid=False, entity_filter=False, season_filter=False),
    "article_ent_dense":  dict(collection="article_ent", hybrid=False, entity_filter=False, season_filter=True),
    "article_entfilter":  dict(collection="article",     hybrid=False, entity_filter=True,  season_filter=True),
    "article_hybrid":     dict(collection="article",     hybrid=True,  entity_filter=False, season_filter=True),
    "best":               dict(collection="article_ent", hybrid=True,  entity_filter=True,  season_filter=True),
    # ---- fixes from the error analysis (Step 7) ----
    # Fix 1: entity filter only for incident questions
    "hybrid_entinc":      dict(collection="article",     hybrid=True,  entity_filter=True,  season_filter=True,
                               entity_incident_only=True),
    # Fix 2: LLM query rewriting into regulation vocabulary
    "hybrid_rewrite":     dict(collection="article",     hybrid=True,  entity_filter=False, season_filter=True,
                               rewrite=True),
    # Both fixes together
    "final":              dict(collection="article",     hybrid=True,  entity_filter=True,  season_filter=True,
                               entity_incident_only=True, rewrite=True),
}
K = 5
PAUSE = 4.0   # seconds between API calls, to stay under free-tier rate limits

JUDGE_SYSTEM = """You are grading answers from a question-answering system about Formula 1 regulations.
You get the question, a reference answer written by a human, and the system's answer.

Grade the system's answer:
- "correct": contains the key facts of the reference answer and nothing that contradicts it.
- "partial": some key facts are right, but something important is missing or slightly wrong.
- "incorrect": wrong, contradicts the reference, or answers a different question.
- "refused": the system said it could not find the answer / does not know.

If the reference answer says the question is NOT answerable from the documents, then
"refused" is the desired behaviour, and any concrete factual answer counts as "incorrect".

Extra detail beyond the reference is fine if it does not contradict it.
Reply with JSON only: {"verdict": "...", "reason": "<one sentence>"}"""


def load_questions():
    rows = list(csv.DictReader(open(ROOT / "eval" / "questions.csv", encoding="utf-8-sig")))
    return [r for r in rows if r.get("verified", "").strip().lower() != "removed"]


def load_chunks():
    chunks = {}
    for name in ("article", "fixed"):
        with open(ROOT / "data" / "processed" / f"chunks_{name}.jsonl", encoding="utf-8") as f:
            for line in f:
                c = json.loads(line)
                chunks[c["id"]] = c
    return chunks


# ---------------------------------------------------------------------------
# Matching retrieved chunks to the gold chunks
# ---------------------------------------------------------------------------
def is_match(hit, gold_id, chunks):
    """Same chunk, or (for the fixed-size collection, whose ids differ) a fixed
    chunk from the same file that contains the gold clause number or starts on its page."""
    if hit["id"] == gold_id:
        return True
    gold = chunks.get(gold_id)
    if not gold or gold["metadata"]["source_type"] != "regulation":
        return False
    hm, gm = hit["metadata"], gold["metadata"]
    if "fixed" not in hit["id"] or hm.get("file") != gm.get("file"):
        return False
    clause = gm.get("clause", "")
    if clause and not clause.startswith("Appendix") and re.search(rf"(?<![\d.]){re.escape(clause)}(?![\d])", hit["text"]):
        return True
    return hm.get("page") == gm.get("page")


def parse_gold(field):
    """'a|b;c' -> [['a','b'], ['c']]. ';' separates REQUIRED sources (e.g. the 2025 rule AND
    the 2026 rule for a comparison); '|' separates interchangeable ALTERNATIVES for one source."""
    return [[g.strip() for g in grp.split("|") if g.strip()] for grp in field.split(";") if grp.strip()]


def retrieval_metrics(hits, gold_groups, chunks):
    ranks = []
    for group in gold_groups:
        best = None
        for r, h in enumerate(hits, start=1):
            if any(is_match(h, gid, chunks) for gid in group):
                best = r; break
        ranks.append(best)
    found = [r for r in ranks if r]
    return {
        "hit": 1.0 if found else 0.0,
        "recall": len(found) / len(gold_groups),
        "mrr": 1.0 / min(found) if found else 0.0,
    }


def year_confusion(hits, q_seasons):
    """Share of retrieved REGULATION chunks from a season the question isn't about."""
    regs = [h for h in hits if h["metadata"].get("source_type") == "regulation"]
    if not regs or not q_seasons:
        return None
    return sum(h["metadata"].get("season") not in q_seasons for h in regs) / len(regs)


def gold_seasons(gold_groups, chunks):
    return {chunks[g]["metadata"]["season"] for grp in gold_groups for g in grp
            if g in chunks and chunks[g]["metadata"]["source_type"] == "regulation"} or \
           {chunks[g]["metadata"]["season"] for grp in gold_groups for g in grp if g in chunks}


# ---------------------------------------------------------------------------
# 1) Retrieval evaluation
# ---------------------------------------------------------------------------
def run_retrieval():
    from rag import RAG
    questions = load_questions()
    chunks = load_chunks()
    answerable = [q for q in questions if q["answerable"] == "yes" and q["gold_chunk_ids"]]
    per_q, summary = [], {}

    class NoLLM:              # retrieval only: never call an API
        last_model = None

    rewrite_llm = None
    only = set(sys.argv[2:])          # optional: evaluate only the named configs
    for name, cfg in CONFIGS.items():
        if only and name not in only:
            continue
        if cfg is None:
            continue
        print(f"[retrieval] {name} ...", flush=True)
        if cfg.get("rewrite"):
            # Query rewriting needs the LLM (results are cached after the first run).
            from llm import LLM
            rewrite_llm = rewrite_llm or LLM(fallback=False)
            print("   (query rewriting: first run makes one API call per question, then cached)", flush=True)
        bot = RAG(k=K, llm=rewrite_llm if cfg.get("rewrite") else NoLLM(), **cfg)
        agg = defaultdict(list)
        try:
            results_for_config = [(q, bot.retrieve(q["question"])[0]) for q in answerable]
        except Exception as e:
            print(f"   SKIPPED {name}: {str(e)[:200]}", flush=True)
            continue
        for q, hits in results_for_config:
            gold = parse_gold(q["gold_chunk_ids"])
            m = retrieval_metrics(hits, gold, chunks)
            yc = year_confusion(hits, gold_seasons(gold, chunks))
            row = {"config": name, "id": q["id"], "category": q["category"], **m,
                   "year_confusion": yc, "retrieved": ";".join(h["id"] for h in hits)}
            per_q.append(row)
            for key in ("hit", "recall", "mrr"):
                agg[key].append(m[key]); agg[f"{key}|{q['category']}"].append(m[key])
            if yc is not None:
                agg["year_confusion"].append(yc)
        summary[name] = {k: sum(v) / len(v) for k, v in agg.items()}

    if not per_q:
        print("No configuration finished."); return
    pq_path, sum_path = RESULTS / "retrieval_per_question.csv", RESULTS / "retrieval_summary.json"
    # When only some configs were run, keep the saved results of all the others.
    # (Read the old files BEFORE overwriting them.)
    if only:
        if sum_path.exists():
            old = json.load(open(sum_path))
            old.update(summary); summary = old
        if pq_path.exists():
            old_rows = [r for r in csv.DictReader(open(pq_path, encoding="utf-8"))
                        if r["config"] not in only]
            per_q = old_rows + per_q
    with open(pq_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(per_q[0].keys()))
        w.writeheader(); w.writerows(per_q)
    json.dump(summary, open(sum_path, "w"), indent=2)
    print(f"\nEvaluated {len(answerable)} answerable questions.")
    write_report()


# ---------------------------------------------------------------------------
# 2) Answer evaluation (generation + LLM judge)
# ---------------------------------------------------------------------------
def parse_verdict(text):
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = re.search(r"\{[^{}]*\"verdict\"[^{}]*\}", text, re.S) or re.search(r"\{.*\}", text, re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        d = {}
    v = str(d.get("verdict", "")).lower().strip()
    if v not in ("correct", "partial", "incorrect", "refused"):
        v = next((x for x in ("incorrect", "partial", "correct", "refused") if x in text.lower()), "unparsed")
    return v, d.get("reason", text[:200])


def score(verdict, answerable):
    if answerable == "no":
        # The desired behaviour is to decline. The judge may call that "refused", or "correct"
        # (e.g. "no such penalty exists" for a false-premise question). Both count.
        return 1.0 if verdict in ("refused", "correct") else 0.0
    return {"correct": 1.0, "partial": 0.5}.get(verdict, 0.0)


def run_answers(config_names):
    import os
    from llm import LLM
    from rag import RAG, closed_book
    questions = load_questions()
    gen_llm = LLM(fallback=False)       # every answer from the same model
    judge = LLM(provider=os.getenv("JUDGE_PROVIDER"), model=os.getenv("JUDGE_MODEL"), fallback=False)
    print(f"Answer model: {gen_llm.name} | judge: {judge.name}")

    for name in config_names:
        if name not in CONFIGS:
            print(f"Unknown config '{name}'. Options: {', '.join(CONFIGS)}"); continue
        out = RESULTS / f"answers_{name}.jsonl"
        done = set()
        if out.exists():
            done = {json.loads(l)["id"] for l in open(out, encoding="utf-8")}
        bot = RAG(k=K, llm=gen_llm, **CONFIGS[name]) if CONFIGS[name] else None
        todo = [q for q in questions if q["id"] not in done]
        print(f"\n[{name}] {len(done)} already done, {len(todo)} to go", flush=True)

        for i, q in enumerate(todo, 1):
            t0 = time.time()
            if bot:
                r = bot.answer(q["question"])
                answer, sources = r["answer"], [h["id"] for h in r["sources"]]
            else:
                answer, sources = closed_book(q["question"], gen_llm), []
            answer_tokens = gen_llm.last_tokens
            time.sleep(PAUSE)
            verdict_text = judge.generate(
                f"Question: {q['question']}\n\nReference answer: {q['expected_answer']}\n\n"
                f"System answer: {answer}", system=JUDGE_SYSTEM)
            verdict, reason = parse_verdict(verdict_text)
            rec = {"id": q["id"], "category": q["category"], "answerable": q["answerable"],
                   "question": q["question"], "answer": answer, "sources": sources,
                   "verdict": verdict, "reason": reason, "score": score(verdict, q["answerable"]),
                   "answer_model": gen_llm.name, "judge_model": judge.name,
                   "answer_tokens": answer_tokens, "judge_tokens": judge.last_tokens}
            with open(out, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"  {i}/{len(todo)} {q['id']} {verdict:9} ({time.time() - t0:.0f}s, "
                  f"tokens: answer {answer_tokens}, judge {judge.last_tokens})", flush=True)
            time.sleep(PAUSE)
    write_report()


def run_rejudge(question_ids):
    """Re-grade SAVED answers for the given questions (e.g. after fixing a reference
    answer). Uses only the judge model; answers are not regenerated."""
    import os
    from llm import LLM
    questions = {q["id"]: q for q in load_questions()}
    judge = LLM(provider=os.getenv("JUDGE_PROVIDER"), model=os.getenv("JUDGE_MODEL"), fallback=False)
    for path in sorted(RESULTS.glob("answers_*.jsonl")):
        recs = [json.loads(l) for l in open(path, encoding="utf-8")]
        changed = False
        for r in recs:
            if r["id"] not in question_ids or r["id"] not in questions:
                continue
            q = questions[r["id"]]
            text = judge.generate(
                f"Question: {q['question']}\n\nReference answer: {q['expected_answer']}\n\n"
                f"System answer: {r['answer']}", system=JUDGE_SYSTEM)
            old = r["verdict"]
            r["verdict"], r["reason"] = parse_verdict(text)
            r["score"] = score(r["verdict"], q["answerable"])
            r["judge_tokens"] = judge.last_tokens
            r["rejudged"] = True
            changed = True
            print(f"  {path.stem}: {r['id']} {old} -> {r['verdict']}", flush=True)
            time.sleep(PAUSE)
        if changed:
            with open(path, "w", encoding="utf-8") as f:
                for r in recs:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
    write_report()


# ---------------------------------------------------------------------------
# 3) Report
# ---------------------------------------------------------------------------
def pct(x):
    return "–" if x is None else f"{100 * x:.0f}%"


def write_report():
    questions = load_questions()
    n_verified = sum(q.get("verified", "").strip().lower() in ("yes", "fixed") for q in questions)
    lines = ["# Evaluation results", "",
             f"Test set: {len(questions)} questions ({n_verified} verified by the group). k = {K}.", ""]

    rs_path = RESULTS / "retrieval_summary.json"
    if rs_path.exists():
        rs = json.load(open(rs_path))
        cats = sorted({k.split("|")[1] for s in rs.values() for k in s if "|" in k})
        lines += ["## Retrieval (answerable questions)", "",
                  "| Config | Hit@5 | Recall@5 | MRR | Year confusion |", "|---|---|---|---|---|"]
        for name, s in rs.items():
            lines.append(f"| {name} | {pct(s.get('hit'))} | {pct(s.get('recall'))} | "
                         f"{s.get('mrr', 0):.2f} | {pct(s.get('year_confusion'))} |")
        lines += ["", "### Hit@5 by category", "",
                  "| Config | " + " | ".join(cats) + " |", "|---|" + "---|" * len(cats)]
        for name, s in rs.items():
            lines.append(f"| {name} | " + " | ".join(pct(s.get(f"hit|{c}")) for c in cats) + " |")
        lines.append("")

    answer_files = sorted(RESULTS.glob("answers_*.jsonl"))
    if answer_files:
        lines += ["## Answers (graded by the judge model)", "",
                  "| Config | n | Score | Correct | Partial | Incorrect | Refused | Unanswerable handled |",
                  "|---|---|---|---|---|---|---|---|"]
        by_cat = {}
        token_notes = []
        for p in answer_files:
            name = p.stem.replace("answers_", "")
            active = {q["id"] for q in questions}          # skips questions marked "removed"
            recs = [r for r in (json.loads(l) for l in open(p, encoding="utf-8")) if r["id"] in active]
            for r in recs:
                r["score"] = score(r["verdict"], r["answerable"])
            ans = [r for r in recs if r["answerable"] == "yes"]
            un = [r for r in recs if r["answerable"] == "no"]
            cnt = lambda v: sum(r["verdict"] == v for r in ans)
            toks = [r.get("answer_tokens") for r in recs if r.get("answer_tokens")]
            if toks:
                token_notes.append(f"{name}: avg {sum(toks)//len(toks)} tokens per answer")
            lines.append(f"| {name} | {len(recs)} | {pct(sum(r['score'] for r in recs) / len(recs))} | "
                         f"{cnt('correct')} | {cnt('partial')} | {cnt('incorrect')} | {cnt('refused')} | "
                         f"{sum(r['score'] == 1.0 for r in un)}/{len(un)} |")
            cat_scores = defaultdict(list)
            for r in recs:
                cat_scores[r["category"]].append(r["score"])
            by_cat[name] = {c: sum(v) / len(v) for c, v in cat_scores.items()}
        cats = sorted({c for d in by_cat.values() for c in d})
        lines += ["", "### Answer score by category", "",
                  "| Config | " + " | ".join(cats) + " |", "|---|" + "---|" * len(cats)]
        for name, d in by_cat.items():
            lines.append(f"| {name} | " + " | ".join(pct(d.get(c)) for c in cats) + " |")
        lines += ["", "Score: correct = 1, partial = 0.5; for unanswerable questions, refusing = 1.", ""]
        if token_notes:
            lines += ["Token usage: " + "; ".join(token_notes), ""]

    (RESULTS / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "retrieval":
        run_retrieval()
    elif cmd == "answers":
        run_answers(sys.argv[2:] or ["closed_book", "article_dense", "article_hybrid", "final"])
    elif cmd == "rejudge":
        run_rejudge(set(sys.argv[2:]))
    elif cmd == "report":
        write_report()
    else:
        print(USAGE)
