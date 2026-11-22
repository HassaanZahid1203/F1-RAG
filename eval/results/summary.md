# Evaluation results

Test set: 92 questions (92 verified by the group). k = 5.

## Retrieval (answerable questions)

| Config | Hit@5 | Recall@5 | MRR | Year confusion |
|---|---|---|---|---|
| fixed_dense | 81% | 76% | 0.61 | 4% |
| article_dense | 80% | 78% | 0.66 | 4% |
| article_no_season | 76% | 75% | 0.54 | 41% |
| article_ent_dense | 82% | 80% | 0.68 | 3% |
| article_entfilter | 81% | 79% | 0.66 | 4% |
| article_hybrid | 91% | 87% | 0.70 | 4% |
| best | 88% | 84% | 0.69 | 4% |
| hybrid_entinc | 91% | 87% | 0.69 | 4% |
| hybrid_rewrite | 91% | 89% | 0.73 | 4% |
| final | 91% | 88% | 0.73 | 4% |

### Hit@5 by category

| Config | compare | fan_language | general_2026 | season_2025 | sporting_2026 | stewards | technical_2026 |
|---|---|---|---|---|---|---|---|
| fixed_dense | 90% | 55% | 100% | 67% | 81% | 94% | 88% |
| article_dense | 70% | 36% | 83% | 83% | 90% | 94% | 88% |
| article_no_season | 60% | 36% | 83% | 75% | 86% | 94% | 88% |
| article_ent_dense | 70% | 36% | 83% | 83% | 100% | 94% | 88% |
| article_entfilter | 70% | 36% | 83% | 83% | 90% | 100% | 88% |
| article_hybrid | 90% | 45% | 100% | 100% | 100% | 100% | 88% |
| best | 90% | 36% | 100% | 100% | 95% | 100% | 88% |
| hybrid_entinc | 90% | 45% | 100% | 100% | 100% | 100% | 88% |
| hybrid_rewrite | 100% | 45% | 100% | 100% | 100% | 100% | 75% |
| final | 100% | 45% | 100% | 100% | 100% | 100% | 75% |

## Answers (graded by the judge model)

| Config | n | Score | Correct | Partial | Incorrect | Refused | Unanswerable handled |
|---|---|---|---|---|---|---|---|
| article_dense | 92 | 76% | 58 | 9 | 5 | 13 | 7/7 |
| article_hybrid | 92 | 79% | 59 | 13 | 10 | 3 | 7/7 |
| closed_book | 92 | 26% | 14 | 12 | 44 | 15 | 4/7 |
| final | 92 | 82% | 61 | 15 | 4 | 5 | 7/7 |

### Answer score by category

| Config | compare | fan_language | general_2026 | season_2025 | sporting_2026 | stewards | technical_2026 | unanswerable |
|---|---|---|---|---|---|---|---|---|
| article_dense | 60% | 36% | 75% | 75% | 88% | 82% | 81% | 100% |
| article_hybrid | 40% | 50% | 100% | 88% | 88% | 85% | 81% | 100% |
| closed_book | 30% | 36% | 25% | 33% | 33% | 0% | 6% | 57% |
| final | 80% | 55% | 83% | 88% | 90% | 82% | 75% | 100% |

Score: correct = 1, partial = 0.5; for unanswerable questions, refusing = 1.

Token usage: article_dense: avg 2009 tokens per answer; article_hybrid: avg 1978 tokens per answer; closed_book: avg 349 tokens per answer; final: avg 2000 tokens per answer
