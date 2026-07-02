# Phase 1: Simulator + Dataset v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Learning-first override:** This project follows a mentoring agreement (see memory: learning-first-working-style). Tasks are tagged `[CLAUDE]` (boilerplate — generate freely), `[USER]` (the user writes it with guidance — do NOT write this code for them), or `[PAIR]` (discuss design first, then Claude types the agreed result). **Learning checkpoints** are conversation gates — stop and discuss before proceeding.

**Goal:** A deterministic incident generator that produces dataset v1 — 300 labeled incidents (≈200 train / ≈100 held-out, stratified 2:1 per archetype) in SQLite — where every incident contains an alert, a window of candidate commits/deploys, perturbed metrics, and free ground truth (culprit commit, runbook ID, true impact).

**Architecture:** Each incident is an independently generated mini-world: same fixed 10-service topology, fresh 48-hour window of benign commits/deploys/metrics, with one scenario archetype injecting a known-bad commit and consistent symptoms. Per-incident isolation keeps generation embarrassingly parallel and eval contamination-free. All randomness flows from a single seed via per-incident child seeds.

**Tech stack:** Python 3.12, dataclasses, stdlib `random` + `sqlite3`, pytest. No external services; no LLM in this phase.

**Timebox:** Weeks 1–2, hard stop. Ugly-but-labeled beats beautiful-but-late.

**Phase map (later phases get their own plan at phase start):**
Phase 2 (wk 3): scorer + eval harness → Phase 3 (wk 4): LLM reasoner → Phase 4 (wk 5): runbook retrieval → Phase 5 (wk 6): impact + comms → Phase 6 (wk 7–8): feedback loop + experiments → Phase 7 (wk 9–10): dashboard.

---

## File structure

```
ai-sre-agent/
  pyproject.toml
  src/simworld/
    __init__.py
    models.py        # frozen dataclasses: Commit, Deploy, Alert, GroundTruth, Incident
    topology.py      # fixed 10-service dependency graph + transitive dependents()
    naming.py        # deterministic content pools: authors, messages, per-service file trees
    metrics.py       # baseline time series with daily seasonality + effect application
    gitgen.py        # benign commit stream generator
    deploygen.py     # deploy events for commits
    scenarios.py     # Archetype schema + the 12-archetype library
    generator.py     # assembles one Incident from an archetype (the orchestrator)
    dataset.py       # N incidents, train/holdout split, SQLite writer, CLI entry
  tests/
    test_topology.py
    test_naming.py
    test_metrics.py
    test_gitgen.py
    test_deploygen.py
    test_scenarios.py
    test_generator.py
    test_dataset.py
  data/              # generated artifacts (gitignored)
```

One responsibility per file; `generator.py` is the only module that imports most of the others.

---

### Learning checkpoint 0 — domain modeling (before any code)

**[PAIR — conversation, no code]** Before Task 1, the user answers these out loud; Claude probes and corrects:

1. What *is* an incident, as a data record? What must the agent be allowed to see (evidence) vs. never see (ground truth)? Where is that boundary in the schema?
2. Why per-incident mini-worlds instead of one continuous timeline? What would a shared timeline break in eval? (Answer to reach: cross-incident contamination — case memory could match on world coincidences; also parallelism and determinism.)
3. Why must the culprit's evidence trail be *probabilistic*, not deterministic? (Answer to reach: if stack traces always name the culprit's files, the file-overlap feature alone solves the task and the learning curve has no headroom.)

Record the user's answers in `docs/README.md` (the design spec) under a new "Design Q&A" appendix if they surface anything new.

---

### Task 1: Project scaffolding `[CLAUDE]`

**Files:**
- Create: `pyproject.toml`, `src/simworld/__init__.py`, `tests/test_smoke.py`, `.gitignore`

- [ ] **Step 1: Write pyproject.toml**

```toml
[project]
name = "ai-sre-agent"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=8"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create package + smoke test**

`src/simworld/__init__.py`: empty file.

```python
# tests/test_smoke.py
def test_import():
    import simworld  # noqa: F401
```

`.gitignore`:

```
__pycache__/
*.egg-info/
.venv/
data/
```

- [ ] **Step 3: Install and run**

Run: `python -m venv .venv && .venv/Scripts/pip install -e .[dev] && .venv/Scripts/pytest -q`
Expected: `1 passed`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml src tests .gitignore
git commit -m "chore: scaffold python package with pytest"
```

---

### Task 2: Domain models `[PAIR]`

Discuss the checkpoint-0 evidence/truth boundary first; then Claude types the agreed schema.

**Files:**
- Create: `src/simworld/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py
from datetime import datetime, timezone
from simworld.models import Alert, Commit, Deploy, GroundTruth, Incident

T0 = datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc)

def make_incident() -> Incident:
    c = Commit(sha="a" * 8, service="checkout", author="maya",
               message="fix rounding", files=("checkout/src/cart.py",),
               lines_changed=12, touches_config=False,
               touches_migration=False, committed_at=T0)
    d = Deploy(service="checkout", sha=c.sha, deployed_at=T0)
    a = Alert(service="checkout", fired_at=T0, symptom="error rate spike",
              stack_frames=("checkout/src/cart.py",),
              anomalies=("error_rate_spike",))
    gt = GroundTruth(culprit_sha=c.sha, culprit_service="checkout",
                     archetype="bad_config_push", runbook_id="rb-config-rollback",
                     impact_failed_requests=1500)
    return Incident(id="inc-0001", alert=a, commits=(c,), deploys=(d,),
                    metrics={"checkout": {"requests": [100.0], "errors": [1.0],
                                          "latency_ms": [120.0]}},
                    truth=gt)

def test_incident_round_trips_through_json():
    inc = make_incident()
    again = Incident.from_json(inc.to_json())
    assert again == inc

def test_evidence_view_excludes_ground_truth():
    inc = make_incident()
    ev = inc.evidence_json()
    assert "culprit" not in ev and "truth" not in ev and "archetype" not in ev
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/pytest tests/test_models.py -q`
Expected: FAIL — `ModuleNotFoundError` / `ImportError`

- [ ] **Step 3: Implement models.py**

```python
# src/simworld/models.py
from __future__ import annotations
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime

ISO = "%Y-%m-%dT%H:%M:%S%z"

@dataclass(frozen=True)
class Commit:
    sha: str
    service: str
    author: str
    message: str
    files: tuple[str, ...]
    lines_changed: int
    touches_config: bool
    touches_migration: bool
    committed_at: datetime

@dataclass(frozen=True)
class Deploy:
    service: str
    sha: str
    deployed_at: datetime

@dataclass(frozen=True)
class Alert:
    service: str
    fired_at: datetime
    symptom: str
    stack_frames: tuple[str, ...]
    anomalies: tuple[str, ...]

@dataclass(frozen=True)
class GroundTruth:
    culprit_sha: str
    culprit_service: str
    archetype: str
    runbook_id: str
    impact_failed_requests: int

@dataclass(frozen=True)
class Incident:
    id: str
    alert: Alert
    commits: tuple[Commit, ...]
    deploys: tuple[Deploy, ...]
    metrics: dict[str, dict[str, list[float]]] = field(compare=True)
    truth: GroundTruth = field(compare=True)

    def to_json(self) -> str:
        def default(o):
            if isinstance(o, datetime):
                return o.strftime(ISO)
            raise TypeError(type(o))
        return json.dumps(asdict(self), default=default)

    def evidence_json(self) -> str:
        d = json.loads(self.to_json())
        d.pop("truth")
        return json.dumps(d)

    @classmethod
    def from_json(cls, s: str) -> "Incident":
        d = json.loads(s)
        dt = lambda x: datetime.strptime(x, ISO)
        a = d["alert"]
        alert = Alert(a["service"], dt(a["fired_at"]), a["symptom"],
                      tuple(a["stack_frames"]), tuple(a["anomalies"]))
        commits = tuple(Commit(c["sha"], c["service"], c["author"], c["message"],
                               tuple(c["files"]), c["lines_changed"],
                               c["touches_config"], c["touches_migration"],
                               dt(c["committed_at"])) for c in d["commits"])
        deploys = tuple(Deploy(x["service"], x["sha"], dt(x["deployed_at"]))
                        for x in d["deploys"])
        truth = GroundTruth(**d["truth"])
        return cls(d["id"], alert, commits, deploys, d["metrics"], truth)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/pytest tests/test_models.py -q`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add src/simworld/models.py tests/test_models.py
git commit -m "feat: domain models with evidence/truth boundary"
```

---

### Task 3: Topology `[CLAUDE]`

**Files:**
- Create: `src/simworld/topology.py`
- Test: `tests/test_topology.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_topology.py
from simworld.topology import SERVICES, dependents

def test_ten_services_and_deps_resolve():
    assert len(SERVICES) == 10
    for svc, deps in SERVICES.items():
        for d in deps:
            assert d in SERVICES, f"{svc} depends on unknown {d}"

def test_dependents_is_transitive():
    # api-gateway -> checkout -> payments, so payments breaking hits both
    assert "checkout" in dependents("payments")
    assert "api-gateway" in dependents("payments")
    assert "payments" not in dependents("payments")

def test_leaf_has_no_dependencies():
    assert SERVICES["payments"] == ()
```

- [ ] **Step 2: Run to verify FAIL** — `.venv/Scripts/pytest tests/test_topology.py -q`

- [ ] **Step 3: Implement**

```python
# src/simworld/topology.py
from functools import cache

SERVICES: dict[str, tuple[str, ...]] = {
    "api-gateway": ("auth", "catalog", "search", "checkout", "user-profile"),
    "checkout": ("payments", "inventory", "notifications"),
    "search": ("catalog",),
    "catalog": ("inventory",),
    "user-profile": ("auth",),
    "auth": (),
    "payments": (),
    "inventory": (),
    "notifications": (),
    "analytics": (),
}

@cache
def dependents(service: str) -> frozenset[str]:
    """Services that (transitively) depend on `service` — its blast radius."""
    direct = {s for s, deps in SERVICES.items() if service in deps}
    out = set(direct)
    for d in direct:
        out |= dependents(d)
    return frozenset(out)
```

- [ ] **Step 4: Run to verify PASS**, then **Step 5: Commit** — `git commit -m "feat: fixed service topology with blast-radius helper"`

---

### Task 4: Naming pools `[CLAUDE]`

**Files:**
- Create: `src/simworld/naming.py`
- Test: `tests/test_naming.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_naming.py
import random
from simworld.naming import AUTHORS, benign_message, service_files

def test_every_service_has_a_file_tree():
    from simworld.topology import SERVICES
    for svc in SERVICES:
        files = service_files(svc)
        assert len(files) >= 8
        assert all(f.startswith(f"{svc}/") for f in files)
        assert any("config" in f for f in files)

def test_benign_message_is_deterministic_per_rng():
    assert benign_message(random.Random(7)) == benign_message(random.Random(7))
    assert len(AUTHORS) >= 8
```

- [ ] **Step 2: Run to verify FAIL**

- [ ] **Step 3: Implement**

```python
# src/simworld/naming.py
import random

AUTHORS = ("maya", "jordan", "priya", "sam", "alex", "chen", "fatima",
           "diego", "nia", "tomás")

_MESSAGES = (
    "fix flaky test in {mod}", "bump minor deps", "refactor {mod} helpers",
    "add logging to {mod}", "handle None in {mod} parser",
    "update docstrings", "tune {mod} timeout", "remove dead code in {mod}",
    "add metrics counter to {mod}", "small cleanup in {mod}",
)
_MODULES = ("handlers", "client", "serializers", "cache", "queue", "auth")

_TREE = ("src/handlers.py", "src/client.py", "src/serializers.py",
         "src/cache.py", "src/queue.py", "src/models.py", "src/app.py",
         "config/settings.yaml", "config/limits.yaml",
         "migrations/0001_init.sql", "requirements.txt")

def service_files(service: str) -> tuple[str, ...]:
    return tuple(f"{service}/{p}" for p in _TREE)

def benign_message(rng: random.Random) -> str:
    return rng.choice(_MESSAGES).format(mod=rng.choice(_MODULES))

def sha(rng: random.Random) -> str:
    return "".join(rng.choices("0123456789abcdef", k=8))
```

- [ ] **Step 4: Run to verify PASS**, then **Step 5: Commit** — `git commit -m "feat: deterministic naming/content pools"`

---

### Task 5: Baseline metrics `[PAIR]`

Learning moment: seasonality + noise, and why the impact estimator (Phase 5) needs a *predictable* baseline. Discuss the shape before typing.

**Files:**
- Create: `src/simworld/metrics.py`
- Test: `tests/test_metrics.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_metrics.py
import random
from simworld.metrics import STEP_MINUTES, apply_effect, baseline

def test_baseline_shape_and_seasonality():
    m = baseline(random.Random(1), base_rps=50, n_points=576)  # 48h at 5-min steps
    assert set(m) == {"requests", "errors", "latency_ms"}
    assert all(len(v) == 576 for v in m.values())
    day1, day2 = m["requests"][:288], m["requests"][288:]
    # same phase of seasonality correlates across days
    assert abs(day1[100] - day2[100]) < day1[100] * 0.35

def test_apply_effect_multiplies_with_ramp():
    m = baseline(random.Random(2), base_rps=50, n_points=576)
    before = m["errors"][:]
    apply_effect(m, metric="errors", multiplier=10.0, start_idx=500,
                 ramp_points=6)
    assert m["errors"][490] == before[490]          # untouched before start
    assert m["errors"][560] > before[560] * 5       # fully ramped after
    assert before[503] < m["errors"][503] < before[503] * 10  # mid-ramp
```

- [ ] **Step 2: Run to verify FAIL**

- [ ] **Step 3: Implement**

```python
# src/simworld/metrics.py
import math
import random

STEP_MINUTES = 5

def baseline(rng: random.Random, base_rps: float, n_points: int
             ) -> dict[str, list[float]]:
    """Per-service series at 5-min resolution with daily seasonality."""
    requests, errors, latency = [], [], []
    for i in range(n_points):
        hour = (i * STEP_MINUTES / 60) % 24
        season = 1 + 0.4 * math.sin(2 * math.pi * (hour - 14) / 24)
        r = base_rps * 60 * STEP_MINUTES * season * rng.uniform(0.92, 1.08)
        requests.append(round(r, 1))
        errors.append(round(r * rng.uniform(0.001, 0.004), 1))
        latency.append(round(rng.gauss(120, 12), 1))
    return {"requests": requests, "errors": errors, "latency_ms": latency}

def apply_effect(m: dict[str, list[float]], *, metric: str, multiplier: float,
                 start_idx: int, ramp_points: int) -> None:
    """Linearly ramp `metric` toward baseline*multiplier from start_idx on."""
    series = m[metric]
    for i in range(start_idx, len(series)):
        frac = min(1.0, (i - start_idx + 1) / max(ramp_points, 1))
        series[i] = round(series[i] * (1 + (multiplier - 1) * frac), 1)
```

- [ ] **Step 4: Run to verify PASS**, then **Step 5: Commit** — `git commit -m "feat: baseline metrics with seasonality and effect ramps"`

---

### Task 6: Commit stream generator `[CLAUDE]`

**Files:**
- Create: `src/simworld/gitgen.py`
- Test: `tests/test_gitgen.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gitgen.py
import random
from datetime import datetime, timedelta, timezone
from simworld.gitgen import generate_commits

T0 = datetime(2026, 1, 5, tzinfo=timezone.utc)

def test_commits_are_in_window_and_plausible():
    cs = generate_commits(random.Random(3), "checkout", T0, T0 + timedelta(hours=48))
    assert 6 <= len(cs) <= 30
    for c in cs:
        assert c.service == "checkout"
        assert T0 <= c.committed_at <= T0 + timedelta(hours=48)
        assert all(f.startswith("checkout/") for f in c.files)
        assert len(c.sha) == 8

def test_deterministic_for_same_seed():
    a = generate_commits(random.Random(9), "auth", T0, T0 + timedelta(hours=48))
    b = generate_commits(random.Random(9), "auth", T0, T0 + timedelta(hours=48))
    assert a == b
```

- [ ] **Step 2: Run to verify FAIL**

- [ ] **Step 3: Implement**

```python
# src/simworld/gitgen.py
import random
from datetime import datetime, timedelta

from .models import Commit
from .naming import AUTHORS, benign_message, service_files, sha

def generate_commits(rng: random.Random, service: str,
                     start: datetime, end: datetime,
                     rate_per_day: float = 6.0) -> list[Commit]:
    hours = (end - start).total_seconds() / 3600
    n = max(1, int(rng.gauss(rate_per_day * hours / 24, 2)))
    files = service_files(service)
    out = []
    for _ in range(n):
        # business-hours bias: 3 draws, keep the one closest to 14:00 UTC
        ts = min((start + timedelta(hours=rng.uniform(0, hours))
                  for _ in range(3)),
                 key=lambda t: abs(t.hour - 14))
        picked = tuple(sorted(rng.sample(files, k=rng.randint(1, 3))))
        out.append(Commit(
            sha=sha(rng), service=service, author=rng.choice(AUTHORS),
            message=benign_message(rng), files=picked,
            lines_changed=max(1, int(rng.gauss(40, 30))),
            touches_config=any("config/" in f for f in picked),
            touches_migration=any("migrations/" in f for f in picked),
            committed_at=ts))
    return sorted(out, key=lambda c: c.committed_at)
```

- [ ] **Step 4: Run to verify PASS**, then **Step 5: Commit** — `git commit -m "feat: benign commit stream generator"`

---

### Task 7: Deploy generator `[CLAUDE]`

**Files:**
- Create: `src/simworld/deploygen.py`
- Test: `tests/test_deploygen.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_deploygen.py
import random
from datetime import datetime, timedelta, timezone
from simworld.deploygen import generate_deploys
from simworld.gitgen import generate_commits

T0 = datetime(2026, 1, 5, tzinfo=timezone.utc)

def test_every_commit_deploys_after_commit_time():
    cs = generate_commits(random.Random(4), "search", T0, T0 + timedelta(hours=48))
    ds = generate_deploys(random.Random(4), cs)
    assert {d.sha for d in ds} == {c.sha for c in cs}
    by_sha = {c.sha: c for c in cs}
    for d in ds:
        assert d.deployed_at > by_sha[d.sha].committed_at
        assert d.service == by_sha[d.sha].service
```

- [ ] **Step 2: Run to verify FAIL**

- [ ] **Step 3: Implement**

```python
# src/simworld/deploygen.py
import random
from datetime import timedelta

from .models import Commit, Deploy

def generate_deploys(rng: random.Random, commits: list[Commit]) -> list[Deploy]:
    """Each commit ships 0.5–6h after it lands (CI + rollout delay)."""
    out = [Deploy(service=c.service, sha=c.sha,
                  deployed_at=c.committed_at + timedelta(hours=rng.uniform(0.5, 6)))
           for c in commits]
    return sorted(out, key=lambda d: d.deployed_at)
```

- [ ] **Step 4: Run to verify PASS**, then **Step 5: Commit** — `git commit -m "feat: deploy events for commit streams"`

---

### Learning checkpoint 1 — scenario design (before Task 8)

**[USER — research + design, ~2–3 hrs]** This is the highest-learning-value work in Phase 1.

1. Read 4–6 real public postmortems (good sources: danluu/post-mortems list on GitHub, the Cloudflare and GitLab incident blogs, k8s.af).
2. For each, answer in writing (a short markdown note in `docs/notes/postmortems.md`): what changed, how long until symptoms, what did the trail look like (did the stack trace point at the change? did metrics or logs?), what made diagnosis hard?
3. Draft the 12-archetype table: name, real-world inspiration, which service kinds it can hit, deploy→alert delay range, how *discoverable* the culprit is (strong trace overlap vs. weak).
4. Review the table with Claude before Task 9 — the key property to check: **archetypes must vary in difficulty**, or the learning curve will have no headroom.

---

### Task 8: Archetype schema + injection engine `[PAIR]`

Discuss: what knobs must an archetype expose so that *one* engine function can express all 12 failure modes? Then Claude types the agreed schema.

**Files:**
- Create: `src/simworld/scenarios.py` (schema + 3 seed archetypes)
- Test: `tests/test_scenarios.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scenarios.py
from simworld.scenarios import ARCHETYPES, Archetype

def test_seed_archetypes_present_and_valid():
    names = {a.name for a in ARCHETYPES}
    assert {"bad_config_push", "retry_storm", "migration_lock"} <= names
    for a in ARCHETYPES:
        assert a.runbook_id.startswith("rb-")
        lo, hi = a.deploy_to_alert_minutes
        assert 0 < lo <= hi
        assert 0.0 <= a.trace_overlap <= 1.0
        assert a.effect.metric in ("errors", "latency_ms", "requests")
```

- [ ] **Step 2: Run to verify FAIL**

- [ ] **Step 3: Implement schema + 3 seed archetypes**

```python
# src/simworld/scenarios.py
from dataclasses import dataclass

@dataclass(frozen=True)
class MetricEffect:
    metric: str          # "errors" | "latency_ms" | "requests"
    multiplier: float    # target-service multiplier at full ramp
    ramp_points: int     # 5-min steps to reach full effect

@dataclass(frozen=True)
class Archetype:
    name: str
    runbook_id: str
    eligible_services: tuple[str, ...]      # () = any service
    commit_messages: tuple[str, ...]        # may use {service}
    files: tuple[str, ...]                  # may use {service}
    touches_config: bool
    touches_migration: bool
    lines_changed: tuple[int, int]
    deploy_to_alert_minutes: tuple[int, int]
    trace_overlap: float          # P(each stack frame comes from culprit files)
    symptom: str                  # may use {service}
    effect: MetricEffect
    downstream_factor: float      # 0..1 scaling of effect on dependents

ARCHETYPES: tuple[Archetype, ...] = (
    Archetype(
        name="bad_config_push", runbook_id="rb-config-rollback",
        eligible_services=(),
        commit_messages=("raise {service} connection pool limits",
                         "tune {service} timeouts in settings"),
        files=("{service}/config/settings.yaml", "{service}/config/limits.yaml"),
        touches_config=True, touches_migration=False, lines_changed=(2, 15),
        deploy_to_alert_minutes=(5, 45), trace_overlap=0.7,
        symptom="{service} error rate spiked shortly after a deploy",
        effect=MetricEffect("errors", 12.0, 3), downstream_factor=0.4),
    Archetype(
        name="retry_storm", runbook_id="rb-retry-storm",
        eligible_services=("checkout", "search", "user-profile", "api-gateway"),
        commit_messages=("add retry wrapper to {service} client",
                         "make {service} http client more resilient"),
        files=("{service}/src/client.py",),
        touches_config=False, touches_migration=False, lines_changed=(20, 80),
        deploy_to_alert_minutes=(60, 360), trace_overlap=0.3,
        symptom="{service} latency climbing; downstream request volume anomalous",
        effect=MetricEffect("latency_ms", 6.0, 24), downstream_factor=0.8),
    Archetype(
        name="migration_lock", runbook_id="rb-migration-lock",
        eligible_services=("payments", "inventory", "auth", "catalog"),
        commit_messages=("add index to {service} orders table",
                         "backfill column in {service} schema"),
        files=("{service}/migrations/0001_init.sql", "{service}/src/models.py"),
        touches_config=False, touches_migration=True, lines_changed=(10, 60),
        deploy_to_alert_minutes=(10, 90), trace_overlap=0.5,
        symptom="{service} requests timing out; DB connections saturated",
        effect=MetricEffect("errors", 8.0, 6), downstream_factor=0.6),
)
```

- [ ] **Step 4: Run to verify PASS**, then **Step 5: Commit** — `git commit -m "feat: archetype schema with three seed scenarios"`

---

### Task 9: Author the remaining 9+ archetypes `[USER]`

**Files:**
- Modify: `src/simworld/scenarios.py` (append entries to `ARCHETYPES`)
- Test: `tests/test_scenarios.py` (extend)

The user writes each archetype as a data entry following the Task 8 schema, grounded in their checkpoint-1 postmortem notes. Claude reviews for: schema validity, difficulty spread (trace_overlap should range ~0.1–0.9 across the library; delays from minutes to hours), and metric-effect plausibility. Candidate list from the spec: dependency version bump, cache stampede, secret expiry, thread-pool exhaustion, memory leak (slow ramp), bad feature flag, N+1 query regression, timezone/DST bug, log-volume explosion, connection-pool misconfig.

- [ ] **Step 1: Extend the test first**

```python
# append to tests/test_scenarios.py
def test_library_size_and_difficulty_spread():
    assert len(ARCHETYPES) >= 12
    overlaps = sorted(a.trace_overlap for a in ARCHETYPES)
    assert overlaps[0] <= 0.2 and overlaps[-1] >= 0.7  # easy AND hard exist
    assert len({a.runbook_id for a in ARCHETYPES}) == len(ARCHETYPES)
```

- [ ] **Step 2: Run to verify FAIL** (only 3 archetypes exist)
- [ ] **Step 3: USER authors the entries** — Claude reviews, does not write
- [ ] **Step 4: Run to verify PASS**
- [ ] **Step 5: Commit** — `git commit -m "feat: full 12-archetype scenario library"`

---

### Task 10: Incident assembly `[PAIR]`

The orchestrator — walk through the assembly sequence together before typing; the user should be able to narrate it from memory afterward.

**Files:**
- Create: `src/simworld/generator.py`
- Test: `tests/test_generator.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_generator.py
import json
import random
from simworld.generator import build_incident
from simworld.scenarios import ARCHETYPES
from simworld.topology import SERVICES, dependents

ARCH = {a.name: a for a in ARCHETYPES}

def test_incident_is_internally_consistent():
    inc = build_incident(random.Random(11), "inc-0001", ARCH["bad_config_push"])
    shas = {c.sha for c in inc.commits}
    assert inc.truth.culprit_sha in shas
    dep = {d.sha: d for d in inc.deploys}
    assert dep[inc.truth.culprit_sha].deployed_at < inc.alert.fired_at
    assert set(inc.metrics) == set(SERVICES)
    assert inc.alert.service in ({inc.truth.culprit_service}
                                 | dependents(inc.truth.culprit_service))
    assert inc.truth.impact_failed_requests > 0

def test_decoys_exist_and_evidence_hides_truth():
    inc = build_incident(random.Random(12), "inc-0002", ARCH["retry_storm"])
    assert len(inc.commits) >= 10          # real candidate noise
    ev = json.loads(inc.evidence_json())
    assert "truth" not in ev

def test_determinism():
    a = build_incident(random.Random(5), "inc-x", ARCH["migration_lock"])
    b = build_incident(random.Random(5), "inc-x", ARCH["migration_lock"])
    assert a == b
```

- [ ] **Step 2: Run to verify FAIL**

- [ ] **Step 3: Implement**

```python
# src/simworld/generator.py
import random
from datetime import datetime, timedelta, timezone

from .deploygen import generate_deploys
from .gitgen import generate_commits
from .metrics import STEP_MINUTES, apply_effect, baseline
from .models import Alert, Commit, Deploy, GroundTruth, Incident
from .naming import service_files, sha
from .scenarios import Archetype
from .topology import SERVICES, dependents

WINDOW_HOURS = 48
N_POINTS = WINDOW_HOURS * 60 // STEP_MINUTES
BASE_TIME = datetime(2026, 1, 5, tzinfo=timezone.utc)
BASE_RPS = {"api-gateway": 120, "checkout": 40, "payments": 35, "auth": 90,
            "catalog": 70, "search": 60, "inventory": 45, "user-profile": 50,
            "notifications": 20, "analytics": 25}

def build_incident(rng: random.Random, incident_id: str,
                   arch: Archetype) -> Incident:
    start = BASE_TIME + timedelta(minutes=rng.randint(0, 7 * 24 * 60))
    # alert lands in the final quarter of the window so history precedes it
    alert_at = start + timedelta(hours=rng.uniform(WINDOW_HOURS * .75,
                                                   WINDOW_HOURS * .95))
    end = start + timedelta(hours=WINDOW_HOURS)

    commits: list[Commit] = []
    for svc in SERVICES:
        commits += generate_commits(rng, svc, start, alert_at)

    target = rng.choice(arch.eligible_services or tuple(SERVICES))
    gap = timedelta(minutes=rng.uniform(*arch.deploy_to_alert_minutes))
    deployed_at = alert_at - gap
    bad = Commit(
        sha=sha(rng), service=target, author=rng.choice(
            tuple(c.author for c in commits)),
        message=rng.choice(arch.commit_messages).format(service=target),
        files=tuple(f.format(service=target) for f in arch.files),
        lines_changed=rng.randint(*arch.lines_changed),
        touches_config=arch.touches_config,
        touches_migration=arch.touches_migration,
        committed_at=deployed_at - timedelta(hours=rng.uniform(0.5, 4)))
    commits.append(bad)

    deploys = generate_deploys(rng, [c for c in commits if c is not bad])
    deploys.append(Deploy(target, bad.sha, deployed_at))
    deploys.sort(key=lambda d: d.deployed_at)

    metrics = {svc: baseline(rng, BASE_RPS[svc], N_POINTS) for svc in SERVICES}
    start_idx = int((deployed_at - start).total_seconds() // (STEP_MINUTES * 60))
    hit = {target: 1.0} | {d: arch.downstream_factor for d in dependents(target)}
    base_err = {svc: sum(metrics[svc]["errors"]) for svc in hit}
    for svc, factor in hit.items():
        mult = 1 + (arch.effect.multiplier - 1) * factor
        apply_effect(metrics[svc], metric=arch.effect.metric, multiplier=mult,
                     start_idx=start_idx, ramp_points=arch.effect.ramp_points)

    impact = int(sum(sum(metrics[s]["errors"]) - base_err[s] for s in hit)) or 1

    alerting = rng.choice(sorted({target} | dependents(target)))
    frames = tuple(
        rng.choice(bad.files) if rng.random() < arch.trace_overlap
        else rng.choice(service_files(alerting))
        for _ in range(4))
    alert = Alert(service=alerting, fired_at=alert_at,
                  symptom=arch.symptom.format(service=alerting),
                  stack_frames=frames,
                  anomalies=(f"{arch.effect.metric}_anomaly",))
    truth = GroundTruth(culprit_sha=bad.sha, culprit_service=target,
                        archetype=arch.name, runbook_id=arch.runbook_id,
                        impact_failed_requests=impact)
    return Incident(id=incident_id, alert=alert, commits=tuple(commits),
                    deploys=tuple(deploys), metrics=metrics, truth=truth)
```

- [ ] **Step 4: Run to verify PASS** — `.venv/Scripts/pytest tests/test_generator.py -q`
- [ ] **Step 5: Commit** — `git commit -m "feat: incident assembly with consistent evidence and ground truth"`

---

### Task 11: Dataset builder + SQLite + CLI `[CLAUDE]`

**Files:**
- Create: `src/simworld/dataset.py`
- Test: `tests/test_dataset.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dataset.py
import sqlite3
from simworld.dataset import generate_dataset

def test_dataset_generation_and_split(tmp_path):
    db = tmp_path / "incidents.db"
    generate_dataset(seed=42, n=30, db_path=str(db))
    con = sqlite3.connect(db)
    rows = con.execute(
        "select split, count(*) from incidents group by split").fetchall()
    counts = dict(rows)
    assert counts["train"] + counts["holdout"] == 30
    assert 6 <= counts["holdout"] <= 14  # ~1/3
    # archetypes appear in both splits (stratified)
    both = con.execute("""select archetype from incidents where split='train'
        intersect select archetype from incidents where split='holdout'"""
    ).fetchall()
    assert len(both) >= 3

def test_regeneration_is_identical(tmp_path):
    a, b = tmp_path / "a.db", tmp_path / "b.db"
    generate_dataset(seed=7, n=12, db_path=str(a))
    generate_dataset(seed=7, n=12, db_path=str(b))
    pa = sqlite3.connect(a).execute(
        "select payload from incidents order by id").fetchall()
    pb = sqlite3.connect(b).execute(
        "select payload from incidents order by id").fetchall()
    assert pa == pb
```

- [ ] **Step 2: Run to verify FAIL**

- [ ] **Step 3: Implement**

```python
# src/simworld/dataset.py
import argparse
import random
import sqlite3

from .generator import build_incident
from .scenarios import ARCHETYPES

SCHEMA = """
create table if not exists incidents (
  id text primary key,
  split text not null,
  archetype text not null,
  culprit_sha text not null,
  runbook_id text not null,
  payload text not null
);
"""

def generate_dataset(seed: int, n: int, db_path: str) -> None:
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)
    con.execute("delete from incidents")
    per_arch_counter: dict[str, int] = {}
    for i in range(n):
        rng = random.Random(f"{seed}:{i}")
        arch = ARCHETYPES[i % len(ARCHETYPES)]
        k = per_arch_counter.get(arch.name, 0)
        per_arch_counter[arch.name] = k + 1
        split = "holdout" if k % 3 == 2 else "train"  # stratified 2:1
        inc = build_incident(rng, f"inc-{i:04d}", arch)
        con.execute("insert into incidents values (?,?,?,?,?,?)",
                    (inc.id, split, inc.truth.archetype,
                     inc.truth.culprit_sha, inc.truth.runbook_id,
                     inc.to_json()))
    con.commit()
    con.close()

def main() -> None:
    p = argparse.ArgumentParser(description="Generate incident dataset")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--n", type=int, default=300)
    p.add_argument("--db", default="data/incidents.db")
    a = p.parse_args()
    generate_dataset(a.seed, a.n, a.db)
    print(f"wrote {a.n} incidents to {a.db}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run to verify PASS** — `.venv/Scripts/pytest tests/test_dataset.py -q`
- [ ] **Step 5: Commit** — `git commit -m "feat: dataset builder with stratified split and sqlite storage"`

---

### Task 12: Generate dataset v1 + sanity review `[PAIR]`

**Files:**
- Create: `data/incidents.db` (gitignored — the *recipe* is committed, not the data)
- Create: `docs/notes/dataset-v1-stats.md`

- [ ] **Step 1: Run the full test suite**

Run: `.venv/Scripts/pytest -q`
Expected: all pass

- [ ] **Step 2: Generate**

Run: `mkdir data && .venv/Scripts/python -m simworld.dataset --seed 42 --n 300 --db data/incidents.db`
Expected: `wrote 300 incidents to data/incidents.db`

- [ ] **Step 3: USER sanity-reads 5 incidents** — pull 5 random payloads out of SQLite, read them like an on-call engineer: is the culprit findable but not trivially so? Does anything look absurd? Write findings (3–10 bullet points, including per-archetype counts and train/holdout ratio) to `docs/notes/dataset-v1-stats.md`. Fix generator bugs found, regenerate, re-note.

- [ ] **Step 4: Commit**

```bash
git add docs/notes/dataset-v1-stats.md
git commit -m "docs: dataset v1 sanity review"
```

---

## Phase 1 exit criteria

- `python -m simworld.dataset --seed 42 --n 300` reproduces dataset v1 byte-for-byte
- 12+ archetypes with difficulty spread (trace_overlap 0.1–0.9, delays minutes→hours)
- All tests green; evidence/truth boundary enforced by test
- User can explain, unprompted: the evidence/truth boundary, why per-incident worlds, why probabilistic trails, and how any archetype maps to its real postmortem inspiration
