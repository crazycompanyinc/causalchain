# CausalChain

CausalChain v2.0 is a deterministic causal incident analysis and response agent. It rebuilds why an incident happened by combining temporal proximity, service dependencies, change proximity, historical pattern matches, distributed trace topology, cross-system correlation, predictive signals, and business impact into explainable confidence scores.

```text
        Events / Alerts / Webhooks
                 |
                 v
        +-------------------+
        |   CausalGraph     |
        | builder + edges   |
        +---------+---------+
                  |
     +------------+-------------+
     |                          |
     v                          v
+------------+           +--------------+
| Investigator|          |   Learner    |
| roots/chain |          | patterns     |
+-----+------+           +------+-------+
      |                         |
      v                         v
+-------------+          +--------------+
|  Narrator   |          |  Predictor   |
| postmortems |          | next breaks  |
+-------------+          +--------------+
```

## Install

```bash
pip install -e ".[dev]"
```

## CLI

```bash
causalchain init
causalchain ingest --type deploy --source api-gateway --description "Deploy v2.3.1"
causalchain trace-ingest otel.json
causalchain investigate --since 2026-05-08T00:00:00
causalchain predict
causalchain alerts
causalchain whatif --action rollback_deploy --target 2.3.1
causalchain patterns
causalchain install-patterns
causalchain narrative --incident <id>
causalchain postmortem --incident <id>
causalchain timeline --incident <id>
causalchain coordinate --incident <id>
causalchain graph --dot
causalchain graph --html
causalchain graph --ascii
causalchain serve --port 8000
causalchain demo
```

By default the CLI stores data in `causalchain.db` in the current directory. Set `CAUSALCHAIN_DB=/path/to/db.sqlite` to override it.

## API

- `POST /events`
- `POST /traces/otel`
- `GET /graph`
- `GET /graph/ascii`
- `GET /graph/html`
- `POST /investigate`
- `GET /predict`
- `GET /alerts/predictive`
- `POST /whatif`
- `GET /patterns`
- `POST /patterns/builtins`
- `POST /correlate/cross-system`
- `POST /business-metrics`
- `GET /incidents`
- `GET /incidents/{id}/narrative`
- `GET /incidents/{id}/timeline`
- `GET /incidents/{id}/postmortem`
- `GET /incidents/{id}/business-impact`
- `GET /incidents/{id}/root-ranking`
- `POST /incidents/{id}/coordinate`
- `GET /health`
- `POST /webhook/alertmanager`

## v2.0 Modules

- `causalchain.tracing`: ingests OpenTelemetry traces and adds span topology to the graph.
- `causalchain.realtime`: publishes live graph snapshots as events and traces stream in.
- `causalchain.whatif`: simulates mitigation actions such as deploy rollbacks.
- `causalchain.ranking`: ranks root causes by impact, confidence, and fix difficulty.
- `causalchain.timeline`: reconstructs minute-by-minute incident timelines.
- `causalchain.patterns`: installs known patterns such as cascading failures, retry storms, thundering herd, and bad deploys.
- `causalchain.correlation`: infers cross-system causal links.
- `causalchain.alerting`: turns causal trajectory predictions into incident alerts.
- `causalchain.postmortem`: generates blameless postmortems with causal analysis, timelines, playbooks, and impact.
- `causalchain.visualization`: exports DOT, interactive HTML, and ASCII graph views.
- `causalchain.agents`: creates response-agent coordination actions.
- `causalchain.metrics`: correlates incidents with business metrics and estimated lost revenue.

## Causal Scoring

Edges are not created from time order alone. Each candidate edge carries evidence:

- `temporal_score`: source happened before target and close enough to matter
- `dependency_score`: target service depends on source, or the relationship is known
- `change_score`: a deploy/config change happened near the symptom
- `pattern_score`: a learned pattern supports this causal step
- `metric_score`: metadata or anomaly descriptions suggest coupled divergence

The final edge confidence is a weighted deterministic score, so every inference is explainable and testable.
