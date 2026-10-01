# BoloAI demo infrastructure

This support package does not change the core app, UI, provider adapters, dependencies,
or deployment configuration. Python 3.10+ and existing application dependencies are
required; install `pytest` separately if it is unavailable.

Run from the BoloAI repository root:

```powershell
# Independent mock server (leave running to inspect /docs)
python -B -m uvicorn mock_services.main:app --host 127.0.0.1 --port 9001

# One-command readiness: starts/checks/stops its own temporary mock server
python -B scripts/run_demo_tests.py

# Or check the already-running mock instead
python -B scripts/run_demo_tests.py --mock-url http://127.0.0.1:9001

# Evaluate actual fallback orchestration with isolated provider doubles
python -B -m evals.runner

# Generate deterministic, observed example sessions in fixtures/
python -B scripts/demo_seed.py

# Populate a running demo-mode app (weather may access live data)
python -B scripts/demo_seed.py --base-url http://127.0.0.1:8000

# Run only this support suite directly
python -B -m pytest tests/test_demo_api.py tests/test_session.py tests/test_agent_safety.py tests/test_mock_services.py tests/test_trace_validation.py tests/test_evaluation_harness.py tests/test_demo_seed.py
```

The readiness and evaluation commands exit **1** when requirements are unmet;
xfails are counted as gaps, never green readiness. Readiness exits **2** for a runner
exception. Direct pytest treats the documented xfails as expected, so its exit code
alone is not a readiness gate. Reports are `evals/latest_readiness.json`,
`evals/latest_results.json`, `evals/latest_pytest.txt`, and `tests/readiness_results.xml`.

## Scope and contracts

- Mock `GET /courier/ABC123`: fixed Ghaziabad Hub operational delay, fixed fixture
  timestamps and expected delivery. Unknown parcels return a demo-labeled 404.
- Mock `POST /courier/ABC123/complaint`: optional `{"reason":"Delayed"}`;
  idempotent reference derived from ID/reason, simulated status, no real filing.
- Mock `GET /schemes?state=UP&course=BTech&income=180000`: structured fictional
  records with `demo: true`, `source_type: DEMO_DATA`, no official URL or claim.
  Income is an annual INR amount; the filter includes matching all-India records.
- Mock `POST /sms`: `{"phone":"+919000000001","message":"Demo only"}`;
  stores a simulated message with sequential reference. `GET /sms` lists messages.
  State is process-local and resets on restart. Run one worker for deterministic IDs.
- Fixed dates are October 1–2, 2026 fixture dates, not current observations.
- Mock and application are separate. The support harness swaps only provider
  boundaries; no new application integration setting is assumed. Weather/search
  providers fail offline so verified model-memory forecasts cannot pass.
- Seed output contains actual observed responses/events plus separate expectations.
  It normalizes session IDs and timestamps; it never fabricates successful traces.
  Application year values `2`, `Second`, and `Second Year` represent fixture year 2.
- The default support suite is explicit. `python -B -m pytest` additionally collects
  other agents' tests, including older tests requiring a live weather provider.
  Those are not included in the offline readiness claim.

## Evaluation and trace limitations

Cases are human-authored expectations. Every required behavior dimension is checked:
category, clarification, required tool, live routing, verification events, action
permission and safety behavior. Category labels are read from operational intent
events; this is a routing/safety rubric, not a factual-answer or language-quality score.
Provider outage cases deliberately verify that failure is not presented as success.

Trace checks correlate tool names/call IDs and completion references within a turn,
consume recorded authorization, and reject stale results. Explicit `claimed_actions`
on assistant events are preferred; English/Hinglish text patterns supplement them.
Text matching cannot prove arbitrary natural-language claims. Authorization events
show recorded consent only; they do not independently prove the caller's intent or
match every action argument. Negative-consent evaluation cases cover that separately.
Only operational events are inspected; no private chain-of-thought is requested.

## Handoff for the core development agent

At validation, 69 support tests passed with two xfails, and all 36 normal-path
evaluation cases passed. The two provider-failure evaluation cases fail:
`failure-01` (SMS) and `failure-02` (complaint). Both still append `action.completed`
and describe success when the tool returns `ok: false`. Gate completion, success wording, and
verification on actual successful results; do not invent a fallback reference.

The two executable xfails are parameterizations of
`tests/test_agent_safety.py::test_failed_action_never_claimed_successful`.
Former gaps fixed by concurrent core changes are now ordinary regression tests:
credential redaction, demo disclosure, negative consent, action event ordering,
missing-income clarification, and Jaipur location extraction.

The core orchestrator currently contains a development hook attempting to mutate
`evals.runner.INTENT_CATEGORY`. Remove that coupling in core when convenient; the
support harness uses an immutable mapping and already recognizes `AMBIGUOUS`.

An earlier all-repository pytest run had three failures in other test files:
`test_agent_weather_query`, `test_agent_context_persistence_multiturn`, and
`test_weather_tool_live`. The weather tests assume live-provider success; the
context test assumes the state is repeated even when the next question correctly
asks for missing income. These files were left untouched. Repository changes are
concurrent; saved support reports describe the app snapshot observed during each run.

## Files added

- `mock_services/__init__.py`, `mock_services/main.py`
- `fixtures/demo_scenarios.json`, `fixtures/generated_demo_sessions.json`
- `evals/__init__.py`, `evals/cases.py`, `evals/sandbox.py`, `evals/trace.py`,
  `evals/runner.py`, `evals/README.md`
- `tests/conftest.py`, `tests/test_demo_api.py`, `tests/test_agent_safety.py`,
  `tests/test_mock_services.py`, `tests/test_trace_validation.py`,
  `tests/test_evaluation_harness.py`, `tests/test_demo_seed.py`
- `scripts/demo_seed.py`, `scripts/run_demo_tests.py`, `pytest.ini`
- Generated evidence: `evals/latest_readiness.json`, `evals/latest_results.json`,
  `evals/latest_pytest.txt`, `evals/latest_mock_server.txt`, `tests/readiness_results.xml`

Existing `tests/test_session.py` is exercised without edits.
