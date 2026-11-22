"""
Step 5c: Gradio interface for the F1 regulations RAG bot.

Run from the project root:   python app.py
Then open the local address it prints (usually http://127.0.0.1:7860).

The page is written for people who are not F1 rules experts: plain-language
labels, one-click example questions, readable source cards, and the retrieval
settings tucked away under "Advanced settings" (their defaults are the
best-scoring configuration from the evaluation, eval/results/summary.md).

Look and feel: an original motorsport style (carbon-fibre header, chequered
flag, timing-tower step numbers, flag-coloured source cards). It deliberately
uses no official Formula 1 / FIA logos or fonts; this is an unofficial project.
"""
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
import gradio as gr
from rag import RAG, closed_book
from llm import LLM
from config import DEFAULT_SEASON, PROCESSED

_bots = {}
_llm = None

REFUSAL = "I couldn't find this in the regulations"


def get_bot(collection, k, season_filter, hybrid, entity_mode, rewrite):
    global _llm
    _llm = _llm or LLM()
    key = (collection, int(k), bool(season_filter), bool(hybrid), entity_mode, bool(rewrite))
    if key not in _bots:
        _bots[key] = RAG(collection=collection, k=int(k), season_filter=season_filter, hybrid=hybrid,
                         entity_filter=entity_mode != "off",
                         entity_incident_only=entity_mode == "incident", rewrite=rewrite, llm=_llm)
    return _bots[key]


def covered_races():
    """Races that have stewards' documents in the corpus, in round order.
    Read from the chunk file, so the page updates itself when new races are added."""
    races = {}
    try:
        with open(PROCESSED / "chunks_article.jsonl", encoding="utf-8") as f:
            for line in f:
                if '"stewards"' not in line:
                    continue
                md = json.loads(line)["metadata"]
                if md.get("source_type") == "stewards" and md.get("race"):
                    races.setdefault(md["race"], md.get("round") or 99)
    except (OSError, ValueError):
        return []
    return [r.replace(f"{DEFAULT_SEASON} ", "").replace(" Grand Prix", "")
            for r, _ in sorted(races.items(), key=lambda x: x[1])]


# ---------------- formatting helpers ----------------
def season_note(r, season_filter):
    """One plain-English line saying which rulebook the answer is based on."""
    pill = lambda s: f'<span class="season-pill">{s}</span>'
    if not season_filter:
        return f"{pill('ALL SEASONS')} Searched the rules from 2025 and 2026."
    if r["mode"] == "compare":
        return f"{pill('2025 vs 2026')} Comparing the two seasons' rules."
    if r["mode"] == "named":
        s = ", ".join(map(str, r["seasons"]))
        return f"{pill(s + ' RULES')} Based on the {s} rulebook."
    return (f"{pill(f'{DEFAULT_SEASON} RULES')} Based on the latest rulebook. "
            "Add *“in 2025”* to your question to ask about last season.")


def source_card(h):
    md, e = h["metadata"], html.escape
    if md.get("source_type") == "stewards":
        kind, tag = "stewards", "⚖️ Stewards' decision"
        title = f"{md.get('race', '')} · Document {md.get('document_no', '?')}"
        meta = " · ".join(str(b) for b in (md.get("title"), md.get("driver"), md.get("session"),
                                           md.get("date")) if b)
        outcome = (f'<div class="src-outcome"><b>Outcome:</b> {e(str(md["decision"]))}</div>'
                   if md.get("decision") else "")
    else:
        kind, tag = "rule", "📄 Rulebook"
        title = md.get("doc_name", "F1 Regulations")
        art = (md.get("article_title") or "").title()
        meta = " · ".join(b for b in (f"Rule {md['clause']}" if md.get("clause") else None, art or None,
                                      f"page {md['page']}" if md.get("page") else None) if b)
        outcome = ""
    chip = '<span class="src-chip">Matches the driver / race you named</span>' if h.get("entity") else ""
    snippet = h["text"].split("\n", 2)[-1][:350].replace("\n", " ").strip()
    return (f'<div class="src-card src-{kind}">'
            f'<div class="src-top"><span class="src-code">[{e(h["label"])}]</span>'
            f'<span class="src-tag">{tag}</span>{chip}</div>'
            f'<div class="src-title">{e(title)}</div><div class="src-meta">{e(meta)}</div>{outcome}'
            f'<blockquote>{e(snippet)}…</blockquote></div>')


def format_sources(hits):
    if not hits:
        return "<p><i>No sources were found for this question.</i></p>"
    head = ('<p class="src-intro">The answer cites these by the code in [square brackets], '
            'listed from most to least relevant. <span class="key key-rule">Rulebook</span>'
            '<span class="key key-stewards">Stewards\' decision</span></p>')
    return head + "".join(source_card(h) for h in hits)


def format_details(r, season_filter):
    lines = [f"- **AI model that wrote the answer:** {r['model']}"]
    if season_filter:
        lines.append(f"- **Seasons searched:** {', '.join(map(str, r['seasons']))} (mode: {r['mode']})")
    if r.get("rewrite"):
        lines.append(f"- **Question restated in rulebook terms (used for searching):** {r['rewrite']}")
    shown = {k: v for k, v in (r.get("entities") or {}).items() if k != "named_driver"}
    if shown:
        lines.append(f"- **Drivers / races / cars recognised:** {shown}")
    lines.append("- **Retrieval scores** (lower distance = closer match):")
    for i, h in enumerate(r["sources"], 1):
        d = f"distance {h['distance']:.3f}" if h.get("distance") is not None else "keyword match only"
        lines.append(f"    {i}. [{h['label']}] {d}")
    return "\n".join(lines)


# ---------------- main handler ----------------
ASK_LABEL, BUSY_LABEL = "Get answer 🏁", "Working… 🚦"


def ask(question, collection, k, season_filter, hybrid, entity_mode, rewrite, show_closed_book):
    """Generator: first shows a 'working' message, then the result.
    Outputs: answer, sources, sources accordion, details, closed-book text, closed-book accordion, button."""
    question = (question or "").strip()
    if not question:
        yield ("👆 Type a question in the box above, or click one of the example questions.",
               "", gr.update(label="Where this answer comes from"), "", "",
               gr.update(visible=False), gr.update())
        return

    yield ("🚦 **Lights out!** Searching the rulebooks and writing your answer… "
           "This usually takes 5–20 seconds.",
           "", gr.update(), "", "", gr.update(), gr.update(interactive=False, value=BUSY_LABEL))

    try:
        bot = get_bot(collection, k, season_filter, hybrid, entity_mode, rewrite)
        r = bot.answer(question)
    except Exception as e:  # network / API-key / quota problems
        yield ("🚩 **Red flag: something went wrong while getting your answer.** "
               "The AI service may be busy; please try again in a moment.\n\n"
               f"<details><summary>Error details</summary>\n\n`{type(e).__name__}: {e}`\n\n</details>",
               "", gr.update(), "", "", gr.update(visible=False),
               gr.update(interactive=True, value=ASK_LABEL))
        return

    text = r["answer"].replace("【", "[").replace("】", "]")  # some models use CJK brackets
    answer = f"{season_note(r, season_filter)}\n\n---\n\n{text}"
    if REFUSAL in r["answer"]:
        answer += ("\n\n💡 **Tip:** try rephrasing, naming the season (2025 or 2026), "
                   "or naming the race or driver you mean.")
    elif r["sources"]:
        answer += ("\n\n<sub>Codes in [square brackets], like [B3.5.3], point to the exact rule or "
                   "stewards' document. Open **Where this answer comes from** below to read the original text.</sub>")

    cb = ""
    if show_closed_book:
        try:
            cb = closed_book(question, _llm)
        except Exception as e:
            cb = f"_Could not get the answer without sources: {e}_"

    yield (answer,
           format_sources(r["sources"]),
           gr.update(label=f"📚 Where this answer comes from ({len(r['sources'])} sources)"),
           format_details(r, season_filter),
           cb,
           gr.update(visible=bool(show_closed_book)),
           gr.update(interactive=True, value=ASK_LABEL))


def clear():
    return ("", WELCOME, "", gr.update(label="Where this answer comes from", open=False), "", "",
            gr.update(visible=False))


# ---------------- page content ----------------
WELCOME = "_Your answer will appear here, along with the exact rules it is based on._"

EXAMPLES = {
    "🏎️ Race weekend basics": [
        "What is the pit lane speed limit and what is the fine for exceeding it in practice?",
        "What happens if a team breaks parc fermé conditions?",
        "How many power unit elements can a driver use in 2025?",
    ],
    "⚖️ Penalties & stewards": [
        "Why was Sergio Perez penalised at the 2026 Chinese Grand Prix?",
        "What happens if a driver causes a collision?",
    ],
    "🔄 2025 vs 2026": [
        "How did the sprint session rules change from 2025 to 2026?",
        "What happens if it rains really hard during a race?",
    ],
}

RACES = covered_races()
RACE_TEXT = (", ".join(RACES[:-1]) + " and " + RACES[-1]) if len(RACES) > 1 else "".join(RACES)

HERO = f"""
<div id="hero">
  <div class="hero-checker"></div>
  <div class="hero-body">
    <div class="hero-kicker">Rulebook assistant · 2025–2026 seasons</div>
    <h1>F1 Rules <span>Explained</span></h1>
    <div class="hero-speed"><i></i><i></i><i></i></div>
    <p>Ask about the rules of Formula 1 in everyday words. Every answer is looked up in the
       official FIA documents and shows the exact rule it comes from.</p>
    <div class="hero-chips">
      <span>📄 2025 &amp; 2026 rulebooks</span>
      <span>⚖️ Stewards' decisions · {len(RACES)} races</span>
      <span>🏁 Every answer cited</span>
    </div>
  </div>
</div>
"""

COVERAGE = f"""
**What I can answer from**
- 📄 The official **2025 and 2026** F1 rulebooks: sporting rules (races, penalties, pit stops, qualifying…), technical rules (car design, engines…) and general provisions
- ⚖️ **{DEFAULT_SEASON} stewards' decisions** (who was penalised and why) from the {RACE_TEXT} Grands Prix

**What I can't answer:** race results, standings, news or opinions. If the documents don't cover it, I'll say so instead of guessing.
"""

FOOTER = """
<div id="footer">
  <div class="footer-checker"></div>
  Unofficial fan project, not affiliated with Formula 1, the FIA or any team.
  Answers are AI-generated from the official documents; check the cited rule for anything important.
</div>
"""


def step(num, text):
    return gr.HTML(f'<div class="sec-head"><span class="pos">{num}</span>{text}</div>')


CSS = """
:root { --racing-red: #d7140f; --racing-red-dark: #a90f0b; --flag-yellow: #f2c200; --carbon: #14161b; }
.gradio-container { max-width: 1050px !important; margin: auto; }

/* ---- Readability ---- */
.prose, .prose p, .prose li { line-height: 1.65 !important; }
#answer .prose { font-size: 1.08rem !important; max-width: 72ch; }
.prose blockquote { font-size: 0.95rem; line-height: 1.6; opacity: .9; }
.prose sub { font-size: 0.85rem; vertical-align: baseline; opacity: .8; }
textarea { font-size: 1.05rem !important; line-height: 1.5 !important; }

/* ---- Carbon-fibre header with chequered flag ---- */
#hero { position: relative; overflow: hidden; border-radius: 12px; color: #f2f3f5;
  background-color: var(--carbon);
  background-image:
    linear-gradient(45deg, rgba(255,255,255,.04) 25%, transparent 25%, transparent 75%, rgba(255,255,255,.04) 75%),
    linear-gradient(45deg, rgba(255,255,255,.04) 25%, transparent 25%, transparent 75%, rgba(255,255,255,.04) 75%);
  background-size: 10px 10px; background-position: 0 0, 5px 5px;
  border-bottom: 5px solid var(--racing-red); padding: 26px 28px 20px; }
.hero-checker { position: absolute; inset: 0 0 0 auto; width: 220px;
  background: repeating-conic-gradient(#f2f3f5 0 25%, transparent 0 50%) 0 0 / 24px 24px;
  opacity: .18; -webkit-mask-image: linear-gradient(to left, #000 20%, transparent);
  mask-image: linear-gradient(to left, #000 20%, transparent); }
.hero-body { position: relative; }
.hero-kicker { font-size: .78rem; letter-spacing: .24em; text-transform: uppercase;
  font-weight: 700; color: #ff7a72; }
#hero h1 { color: #fff !important; font-size: 2.7rem !important; font-style: italic; font-weight: 700;
  margin: .1em 0 .15em !important; letter-spacing: -.01em; line-height: 1.1; }
#hero h1 span { color: var(--racing-red); }
.hero-speed { display: flex; gap: 6px; margin: 2px 0 12px; }
.hero-speed i { display: block; height: 5px; transform: skewX(-30deg); background: var(--racing-red); }
.hero-speed i:nth-child(1) { width: 90px; } .hero-speed i:nth-child(2) { width: 50px; background: #f2f3f5; }
.hero-speed i:nth-child(3) { width: 24px; }
#hero p { color: #d5d8de !important; max-width: 62ch; font-size: 1.1rem; margin: 0 0 14px; }
.hero-chips span { display: inline-block; margin: 0 6px 6px 0; padding: 3px 12px; font-size: .92rem;
  border: 1px solid rgba(255,255,255,.2); background: rgba(255,255,255,.07); border-radius: 999px; }

/* ---- Timing-tower step headings ---- */
.sec-head { display: flex; align-items: center; gap: 12px; margin: 16px 0 0; font-weight: 700;
  text-transform: uppercase; letter-spacing: .1em; font-size: .95rem; }
.sec-head .pos { display: inline-block; min-width: 2.4em; text-align: center; padding: 2px 8px;
  background: var(--racing-red); color: #fff; font-style: italic; transform: skewX(-12deg);
  font-family: var(--font-mono); }
.sec-head::after { content: ""; flex: 1; height: 2px;
  background: linear-gradient(90deg, var(--racing-red), transparent); }

/* ---- Buttons ---- */
#ask-btn { font-style: italic; text-transform: uppercase; letter-spacing: .08em; font-weight: 700; }
.example-btn { text-align: left !important; justify-content: flex-start !important;
  white-space: normal !important; height: auto !important; border-left: 3px solid transparent !important; }
.example-btn:hover { border-left-color: var(--racing-red) !important; }
.group-label p { margin: 6px 0 0 0 !important; font-weight: 700; }

/* ---- Answer panel ---- */
#answer { min-height: 90px; border: 1px solid var(--border-color-primary);
  border-left: 6px solid var(--racing-red); border-radius: 8px; padding: 8px 18px; }
.season-pill { display: inline-block; background: var(--racing-red); color: #fff; font-weight: 700;
  font-style: italic; font-size: .78rem; letter-spacing: .12em; padding: 2px 10px; border-radius: 3px;
  margin-right: 6px; }
#coverage { border: 1px solid var(--border-color-primary); border-radius: 10px;
  padding: 4px 16px; background: var(--background-fill-secondary); }

/* ---- Source cards: red edge = rulebook, yellow-flag edge = stewards ---- */
.src-intro { opacity: .85; }
.key { display: inline-block; margin-left: 8px; padding-left: 8px; font-size: .85rem; }
.key-rule { border-left: 4px solid var(--racing-red); } .key-stewards { border-left: 4px solid var(--flag-yellow); }
.src-card { border: 1px solid var(--border-color-primary); border-left: 6px solid var(--racing-red);
  border-radius: 8px; padding: 10px 14px; margin: 10px 0; background: var(--background-fill-secondary); }
.src-stewards { border-left-color: var(--flag-yellow); }
.src-top { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; font-size: .85rem; }
.src-code { font-family: var(--font-mono); font-weight: 700; }
.src-tag { text-transform: uppercase; letter-spacing: .1em; font-weight: 700; font-size: .75rem; opacity: .75; }
.src-chip { background: var(--flag-yellow); color: #111; border-radius: 999px; padding: 1px 9px;
  font-size: .75rem; font-weight: 700; }
.src-title { font-weight: 700; font-size: 1.06rem; margin-top: 4px; }
.src-meta { opacity: .8; font-size: .95rem; }
.src-outcome { margin-top: 4px; }
.src-card blockquote { margin: 8px 0 0; padding-left: 10px; border-left: 2px solid var(--border-color-primary);
  font-size: .95rem; line-height: 1.55; opacity: .9; }

/* ---- Footer ---- */
#footer { text-align: center; font-size: .85rem; opacity: .7; margin-top: 18px; }
.footer-checker { height: 10px; margin-bottom: 10px; opacity: .5;
  background: repeating-conic-gradient(currentColor 0 25%, transparent 0 50%) 0 0 / 10px 10px; }

@media (max-width: 640px) {
  #hero { padding: 20px 16px 16px; } #hero h1 { font-size: 2rem !important; }
  .hero-checker { width: 100px; }
}
"""

# analytics_enabled=False: no usage data sent to Gradio, and it skips Gradio's buggy
# theme-comparison check that crashes launch() with custom fonts.
with gr.Blocks(title="F1 Rules Explained", analytics_enabled=False) as demo:
    gr.HTML(HERO)
    with gr.Accordion("ℹ️ What can I ask about?", open=False):
        gr.Markdown(COVERAGE, elem_id="coverage")

    step("01", "Ask your question")
    question = gr.Textbox(show_label=False, lines=2, max_lines=6, autofocus=True,
                          placeholder="e.g. Can a driver be penalised for going too slow? "
                                      "(press Enter to ask, Shift+Enter for a new line)")
    with gr.Row():
        ask_btn = gr.Button(ASK_LABEL, variant="primary", scale=3, elem_id="ask-btn")
        clear_btn = gr.Button("Clear", variant="secondary", scale=1)

    step("02", "Or click a question to try it")
    example_buttons = []
    with gr.Row(equal_height=False):
        for group, qs in EXAMPLES.items():
            with gr.Column(min_width=220):
                gr.Markdown(group, elem_classes="group-label")
                for q in qs:
                    example_buttons.append((gr.Button(q, size="sm", elem_classes="example-btn"), q))

    step("03", "Answer")
    answer = gr.Markdown(WELCOME, elem_id="answer")
    with gr.Accordion("Where this answer comes from", open=False) as sources_acc:
        sources = gr.HTML()
    with gr.Accordion("🤖 Same question answered WITHOUT the rulebooks (for comparison)",
                      open=True, visible=False) as cb_acc:
        gr.Markdown("_This is what the AI says from memory alone. It is often wrong or out of date, "
                    "which is why the main answer looks things up first._")
        cb_answer = gr.Markdown()

    with gr.Accordion("⚙️ Advanced settings (optional; the defaults give the best results)", open=False):
        gr.Markdown("These options are for testing how the assistant finds information. "
                    "Most people never need to change them.")
        with gr.Row():
            with gr.Column():
                collection = gr.Radio([("Whole rules (recommended)", "article"),
                                       ("Whole rules + incident summaries", "article_ent"),
                                       ("Fixed-length text pieces", "fixed")],
                                      value="article", label="How the rulebooks are split up",
                                      info="How the documents are cut into pieces for searching.")
                k = gr.Slider(3, 10, value=5, step=1, label="How many passages to read",
                              info="More passages = more context, but slower and sometimes less focused.")
                entity_mode = gr.Radio([("Off", "off"), ("Always", "always"),
                                        ("Only for incident questions (recommended)", "incident")],
                                       value="incident", label="Prioritise named drivers / races / cars",
                                       info="Puts stewards' decisions about the driver or race you name first.")
            with gr.Column():
                season_filter = gr.Checkbox(value=True, label="Use the right season's rulebook",
                                            info="Picks 2025 or 2026 rules based on your question "
                                                 "(2026 if you don't say).")
                hybrid = gr.Checkbox(value=True, label="Also match exact words",
                                     info="Combines meaning-based search with keyword search "
                                          "(helps with names and rule numbers).")
                rewrite = gr.Checkbox(value=True, label="Translate my question into rulebook language",
                                      info="Rephrases everyday words into official terms before "
                                           "searching. Slightly slower.")
                show_cb = gr.Checkbox(value=False, label="Also show an answer WITHOUT the rulebooks",
                                      info="For comparison: what the AI says from memory alone.")
        with gr.Accordion("Technical details of the last answer", open=False):
            details = gr.Markdown("_Ask a question first._")

    gr.HTML(FOOTER)

    inputs = [question, collection, k, season_filter, hybrid, entity_mode, rewrite, show_cb]
    outputs = [answer, sources, sources_acc, details, cb_answer, cb_acc, ask_btn]
    ask_btn.click(ask, inputs, outputs)
    question.submit(ask, inputs, outputs)
    for btn, q in example_buttons:
        btn.click(lambda q=q: q, None, question).then(ask, inputs, outputs)
    clear_btn.click(clear, None, [question, answer, sources, sources_acc, details, cb_answer, cb_acc])

if __name__ == "__main__":
    theme = gr.themes.Soft(
        primary_hue="red", secondary_hue="slate", neutral_hue="slate",
        text_size=gr.themes.sizes.text_lg,           # larger base text
        radius_size=gr.themes.sizes.radius_sm,       # sharper corners suit the racing look
        # Times New Roman (built into Windows/macOS, so nothing to download).
        # Every entry is a Font object: Gradio 6 crashes comparing a Font with a plain string.
        font=[gr.themes.Font(f) for f in ("Times New Roman", "Times", "Liberation Serif", "serif")],
        font_mono=[gr.themes.GoogleFont("JetBrains Mono"), gr.themes.Font("Consolas"),
                   gr.themes.Font("monospace")],
    ).set(body_text_color="*neutral_900", body_text_color_dark="*neutral_100",
          body_text_color_subdued="*neutral_600",  # stronger contrast than the theme default
          button_primary_background_fill="#d7140f", button_primary_background_fill_dark="#d7140f",
          button_primary_background_fill_hover="#a90f0b",
          button_primary_background_fill_hover_dark="#a90f0b",
          button_primary_text_color="white", button_primary_text_color_dark="white")
    demo.launch(theme=theme, css=CSS)
