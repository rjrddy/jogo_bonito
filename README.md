# Jogo Bonito

A football intelligence prototype with deterministic match replay, interactive shot maps, cumulative expected goals, attacking momentum, baseline outcome estimates, and event inspection.

## Run

Requires Python 3.10+. No runtime dependencies or API keys.

```sh
python3 server.py
# Open http://127.0.0.1:8000
```

The dashboard also works on static hosting: serve `dist/` with an HTTP server. All fixture names, players, and results are illustrative; the events are synthetic and do not represent real matches. Nothing here is a live sports feed.

## Features implemented

- Three reproducible synthetic fixtures, replay/pause/restart, seek, playback speed, and CSV export of events up to the selected time.
- Shot filters and keyboard-accessible shot details; xG, pass completion, completed-pass share, and shot statistics.
- Synchronized momentum, xG progression, score, event table, and outcome probabilities.
- Local SQLite event API with schema validation, atomic batches, duplicate detection, conflict rejection, chronological reconstruction, and persistence across restart.
- Unit tests for retries, rollback, out-of-order delivery, persistence, deterministic fixtures, scoring, and outcome probability invariants.

## Local API

```sh
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/matches
curl 'http://127.0.0.1:8000/api/matches/city/state?minute=58.25'
curl 'http://127.0.0.1:8000/api/matches/city/events?minute=45'
# POST /api/events accepts a JSON array of normalized events.
```

`server.py` binds to loopback. This unauthenticated API is intended for local development. It is not deployed with the static dashboard. The browser loads the bundled event stream and reconstructs snapshots locally; POSTed API events are inspectable through API queries but do not automatically appear in the static browser replay.

The server seeds the database idempotently. Changing an existing event payload under the same ID intentionally causes a conflict: use a different database with `--db` for regenerated fixtures. Regenerate fixture JSON with `python3 generate_data.py`.

## Verify

Python 3.10+ and Node.js 20+:

```sh
npm test
```

## Model status

Shot xG uses an illustrative logistic function of distance and angle. The outcome model sums independent Poisson distributions for remaining goals, with neutral pre-match rates adjusted by accumulated xG. These are untrained, uncalibrated baselines. The synthetic generator samples outcomes from its own xG formula; evaluating against that same data would not establish real-world predictive quality. Possession is a completed-pass-share proxy. Momentum is a visualization of recent passes and shot quality, not an independently validated model.

## Planned, not implemented

FastAPI, PostgreSQL, Redis Streams, consumer checkpoints/retries, WebSockets, imported licensed/open match datasets, chronological model training/evaluation, PyTorch/XGBoost, Prometheus/Grafana, Docker, CI/CD, load/fault testing, and production deployment of the API. No throughput, latency, model-quality, or fault-tolerance targets from the proposal are claimed as achieved.

See [architecture](docs/architecture.md) for the implementation boundary and next steps.
