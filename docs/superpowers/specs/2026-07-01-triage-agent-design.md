# Self-Improving On-Call Triage Agent — Design Spec

**Date:** 2026-07-01
**Status:** Approved design, pre-implementation
**Timeline:** 10 weeks (~2026-07-01 to ~2026-09-09), 10–20 hrs/week (~150 hrs total)

## Purpose

A portfolio project for AI/agent engineering roles. The system is an autonomous on-call triage agent that, when an alert fires, proposes a root cause, impact estimate, relevant runbook, and drafted communications — then learns from whether it was right, measurably improving over time.

The two artifacts that matter most are the **eval harness** and the **learning curve** (accuracy improving as the agent works more incidents). Every other component is scoped to serve them. The target resume line: *"raised root-cause accuracy from X% to Y% across N incidents via an automated feedback loop."*

## Core loop

```
Alert fires
  → agent proposes: root cause + impact + runbook + drafted comms
  → outcome auto-adjudicated against ground truth (was the root cause right?)
  → outcome feeds back into future predictions (scorer weights + case memory)
```

## Success criteria

1. **Headline metric:** top-1 root-cause accuracy on a frozen held-out incident set. Secondaries: MRR, precision@3, runbook recall@1, impact-estimation error.
2. **The self-improvement claim is proven, not asserted:** agent snapshots at 0/50/100/150/200 feedback incidents, each evaluated on the held-out set, plotted as accuracy vs. incidents-learned-from. The curve must go up.
3. **Every claim ships with an ablation:** scorer-only baseline vs. LLM-without-memory vs. full system, run on every eval.
4. **Model comparison:** the same eval run against both LLM backends (Gemini Flash vs. an open-weight HuggingFace model) plus the non-LLM baseline.

## Architecture

Six components with clear boundaries:

```
[Simulator] → incidents + ground truth → SQLite
     ↓
[Triage agent] = Stage-1 scorer → top-5 suspects → Stage-2 LLM reasoner → verdict
     + [Runbook retrieval]  + [Impact estimator]  + [Comms generator]
     ↓
[Adjudicator] compares verdict to ground truth → outcome record
     ↓
[Feedback updater] → scorer weights + case memory
     ↓
[Eval harness] orchestrates all of the above against frozen datasets
     ↓
[Dashboard] reads SQLite via FastAPI, renders feed/detail/metrics
```

### 1. Simulator (incident source)

Generates a fake but internally consistent microservice company:

- **Topology:** ~10 services with a dependency graph (e.g. api-gateway → checkout → payments → db).
- **Git history:** per-service generated commit streams — realistic messages, file trees, authors, timestamps.
- **Deploy log:** ties commits to deploy timestamps per service.
- **Metrics:** per-service request rate, error rate, latency time series with daily seasonality.

A **scenario library** of 12–15 failure archetypes grounded in real public postmortems (bad config push, unbounded retry storm, DB migration lock, dependency version bump, cache stampede, secret expiry, thread-pool exhaustion, ...). Each scenario:

1. Injects a known-bad commit into one service's history.
2. Perturbs metrics of that service and downstream dependents consistently with the failure mode.
3. Emits an alert: stack-trace fragment, anomalous metrics, affected endpoints.
4. Records ground truth: the injected commit ID, the applicable runbook ID, true impact numbers.

**Ground truth is free by construction** — no manual labeling, ever.

**Dataset v1:** ~300 incidents. 200 for feedback-loop training, 100 frozen for eval. Split by scenario variant so held-out incidents are not near-duplicates of training incidents. All generation is seeded and deterministic.

### 2. Root cause identification (two-stage)

**Stage 1 — rule-based scorer.** For every commit deployed within the lookback window (default 48h before the alert, configurable), compute features:

- Deploy recency relative to alert time
- File-path overlap with the stack trace
- Dependency-graph distance from the alerting service
- Commit risk heuristics: diff size, touches config/migrations, off-hours deploy

Weighted linear score ranks candidates; top-5 become suspects. **Weights start uniform** — deliberately uninformed, because tuning them is what the feedback loop demonstrably improves.

**Stage 2 — LLM reasoner.** The LLM receives the alert, the top-5 suspects with their evidence, and up to 3 retrieved case-memory entries. Returns a structured verdict: culprit commit, confidence, reasoning chain (JSON-enforced).

**Failure handling:** on LLM API failure, retry once with backoff; on second failure, fall back to the scorer's top-1 so batch runs never die mid-eval. Rate limiting (throttle + retry-on-429) is built into the LLM client from day one because the Gemini free tier is request-limited.

### 3. Runbook retrieval

- Corpus: ~30–40 short markdown runbooks, authored by hand — one per scenario archetype plus decoys.
- Retrieval: hybrid BM25 (`rank-bm25`) + local embeddings (sentence-transformers), combined with reciprocal rank fusion (RRF).
- Eval: recall@1 against the generator's known correct runbook per incident.

### 4. Impact estimation

Deviation-from-baseline over simulated metrics: expected requests (from seasonality baseline) minus observed, error-rate delta, affected downstream services. No ML. Reported against the generator's true impact numbers as estimation error.

### 5. Comms generation

One LLM call per artifact — Slack brief, status-page update, postmortem draft — templated, taking the structured triage result as input. A critique/refine pass is a stretch goal only if week 6 has slack.

### 6. Feedback loop

After each training incident, the adjudicator auto-compares the verdict to ground truth and records hit/miss. Two updates fire:

1. **Scorer weights** — multiplicative-weights update: features that pointed at the true culprit are boosted; features that pointed elsewhere are dampened.
2. **Case memory** — store the resolved incident (symptom embedding, true cause, which signals mattered). Future incidents retrieve the 3 most similar solved cases as few-shot context for the LLM.

**Headline experiment:** freeze agent snapshots at 0, 50, 100, 150, 200 feedback incidents; evaluate each snapshot on the held-out 100; plot top-1 accuracy vs. incidents-learned-from.

### 7. Eval harness (built in week 3, before anything is polished)

- Runs any agent configuration against the frozen held-out set.
- Reports: top-1 accuracy, MRR, precision@3, runbook recall@1, impact error.
- Always runs three configurations: scorer-only, LLM-without-memory, full system.
- Supports backend swap for the model-comparison table.
- Deterministic seeds; all results logged to SQLite so the learning curve is queryable.

### 8. Dashboard (weeks 9–10)

React + Vite + Tailwind + Recharts over FastAPI, reading the same SQLite stores. Three views:

1. **Incident feed** — list of incidents with status.
2. **Incident detail** — ranked suspects, LLM reasoning trace, retrieved runbook, impact estimate, drafted comms.
3. **Metrics** — learning curve front and center, plus ablation and model comparisons.

## Tech stack

| Layer | Tech | Role |
|---|---|---|
| Core language | Python 3.12 | Simulator, agent, scorer, eval harness, feedback loop |
| LLM — primary | Gemini API (Flash, free tier) | Reasoning + comms; workhorse for development, the learning experiment, and demos |
| LLM — secondary | HuggingFace open-weight model (e.g. Qwen 2.5 7B via Ollama or HF Inference API) | Second backend; eval-time model comparison + open-weight serving credibility |
| LLM abstraction | Thin provider interface | One `triage(evidence) → verdict` contract; backends swappable by config |
| Embeddings | sentence-transformers (HuggingFace, local) | Runbook retrieval + case-memory similarity |
| Keyword search | rank-bm25 | Lexical half of hybrid retrieval |
| Storage | SQLite | All persistence: incidents, labels, predictions, outcomes, weights, case memory, eval results |
| API | FastAPI | Dashboard backend |
| Frontend | React + Vite + Tailwind + Recharts | Feed, detail, metrics views |
| Testing | pytest | Simulator determinism, scorer, feedback updates, golden eval tests |

API cost target: $0 (Gemini free tier + local everything else).

## Ten-week schedule

| Weeks | Deliverable |
|---|---|
| 1–2 | Simulated world + scenario library + dataset v1 with labels (hard timebox) |
| 3 | Scorer + eval harness → first baseline numbers |
| 4 | LLM reasoner (Gemini backend + provider abstraction) → baseline-vs-agent comparison |
| 5 | Runbooks + hybrid retrieval + retrieval eval |
| 6 | Impact estimation + comms generation |
| 7 | Feedback loop (weights + case memory) + learning-curve experiment |
| 8 | Eval hardening, ablations, HF-backend model comparison, results write-up |
| 9–10 | Dashboard, README, demo script, buffer |

## Testing strategy

- **Simulator:** unit tests for determinism (same seed → identical dataset) and internal consistency (injected commit exists in history, metric perturbation matches scenario, ground-truth references resolve).
- **Scorer:** unit tests for each feature extractor and the ranking function.
- **Feedback updater:** unit tests that weight updates move in the correct direction on synthetic hit/miss cases.
- **Eval harness:** golden tests — a tiny fixed dataset with known expected metrics.
- **LLM layers:** tested via the eval harness with recorded/mocked responses in CI; live calls only in real runs.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Simulator realism eats unlimited time | Hard timebox weeks 1–2; ugly-but-labeled beats beautiful-but-late |
| Learning curve plateaus early (weak self-improvement story) | Starting weights deliberately uniform; scenarios diverse for headroom; week 7 reserved for tuning the update rule |
| Gemini free-tier rate limits stall batch runs | Throttling + retry-on-429 in the client from day one; spread big experiments across a day or overnight |
| Open-weight model too weak / hardware too slow | HF backend is comparison-only, a handful of eval runs; can use HF Inference API instead of local if needed |
| Dashboard overruns | It is last in the schedule with a buffer week; CLI output of the same data is the fallback demo |

## Out of scope

- Real alert-source integrations (PagerDuty, Grafana, Slack apps)
- Multi-incident correlation / concurrent incidents
- Auto-remediation (the agent proposes; it never acts)
- Fine-tuning any model
- Auth, multi-user support, or deployment infrastructure for the dashboard
