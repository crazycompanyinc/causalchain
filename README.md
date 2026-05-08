# CausalChain

CausalChain is a deterministic causal incident analysis agent. It rebuilds why an incident happened by combining temporal proximity, service dependencies, change proximity, historical pattern matches, and metric-like correlation signals into explainable confidence scores.

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
causalchain investigate --since 2026-05-08T00:00:00
causalchain predict
causalchain patterns
causalchain narrative --incident <id>
causalchain graph --dot
causalchain serve --port 8000
causalchain demo
```

By default the CLI stores data in `causalchain.db` in the current directory. Set `CAUSALCHAIN_DB=/path/to/db.sqlite` to override it.

## API

- `POST /events`
- `GET /graph`
- `POST /investigate`
- `GET /predict`
- `GET /patterns`
- `GET /incidents`
- `GET /incidents/{id}/narrative`
- `GET /health`
- `POST /webhook/alertmanager`

## Causal Scoring

Edges are not created from time order alone. Each candidate edge carries evidence:

- `temporal_score`: source happened before target and close enough to matter
- `dependency_score`: target service depends on source, or the relationship is known
- `change_score`: a deploy/config change happened near the symptom
- `pattern_score`: a learned pattern supports this causal step
- `metric_score`: metadata or anomaly descriptions suggest coupled divergence

The final edge confidence is a weighted deterministic score, so every inference is explainable and testable.

