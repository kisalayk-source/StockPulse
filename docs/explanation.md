# Prediction explanations (MVP-7)

Human-readable explanations for hybrid BUY/HOLD/SELL stances.

## Behavior

1. **Template (always):** `ml.explanation.explain_prediction` formats only fields
   already present in the structured quantitative payload (probability, model
   members, risk gate, institutional/fundamental/government scores, …).
2. **Optional LLM narration:** when `llm.enabled` is true in
   `ml/config/prediction.yaml` **and** research LLM is active for the user
   (`RESEARCH_LLM_ENABLED` + OpenAI key + user “Use AI summaries”), the API
   calls the shared `openai_client` with the structured JSON and may replace
   the displayed text.
3. **Fallback:** any LLM miss/failure keeps the template. Provider is never
   labeled `"llm"` unless narration actually succeeded.

When present, `government_score` is listed as a driver alongside institutional and
fundamental scores. Government scores themselves remain deterministic config-driven
values — the LLM never computes them.

## Rules

- Never invent prices, probabilities, filings, fundamentals, or government contract stats
- LLM must not contradict the JSON context
- Template disclaimer is retained when missing from the narrative

## Code

| Piece | Role |
|---|---|
| `ml/explanation/` | Template + merge helpers |
| `backend/app/services/prediction_explanation.py` | Async enrichment |
| `backend/app/api/prediction.py` | Runs enrichment after predict/explanation |

Plain-language overview: [mvp-roadmap.md](./mvp-roadmap.md#mvp-7--plain-explanations).
