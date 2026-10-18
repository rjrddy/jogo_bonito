# Jogo Bonito

A historical football matchup simulator. Play **2023 Manchester City vs 2016 Real Madrid**, **2012 Spain vs 2022 Argentina**, or any pair of supported team editions, including club-versus-country experiments.

## Run

Requires Python 3.10+. No runtime dependencies, API keys, or paid feeds.

```sh
python3 server.py
# Open http://127.0.0.1:8000
```

The simulator also runs on static hosting: serve `dist/` over HTTP. Its catalog and match engine are bundled, with no third-party data requests at runtime. Google Fonts is optional; local font fallbacks are defined.

## Choose your matchup

Each side has independent competition, edition, team, and search controls. Select neutral ground or home advantage, enter a seed, and click **Simulate match**. Use replay/pause, restart, seek, speed controls or **Skip to full time**. **New seed** reruns the matchup with a fresh possible outcome. URLs store both editions, venue and seed, so reopening the URL reproduces the scenario. CSV exports include simulation metadata and events up to the current replay minute.

**Year convention:** club editions use the season-ending year. City 2023 = 2022/23; Madrid 2016 = 2015/16. National editions use tournament years; Euro 2020 appears as `2020 / played 2021`, with internal year 2021. These are men's senior teams.

## Actual coverage

The bundled catalog contains **2,002 team editions**, **100 competition editions**, and **31,412 historical source results**, with a cutoff of **2026-10-18**:

| Competition | Editions |
| --- | --- |
| Premier League, La Liga, Bundesliga, Serie A, Ligue 1 | Every team, each season ending 2010–2026 |
| World Cup | 2010, 2014, 2018, 2022, 2026 |
| Euros | 2012, 2016, 2020 (played 2021), 2024 |
| Copa América | 2011, 2015, 2016, 2019, 2021, 2024 |

All team memberships are present. Three club editions have partial results in the source: La Liga 2024/25 (370/380), Serie A 2024/25 (370/380), Ligue 1 2025/26 (305/306). The builder labels these editions and the Methodology view exposes every competition's team count, match count and completeness. Ligue 1 2019/20 uses its officially curtailed 279-match season. The ongoing 2026/27 club season is not included; it has not finished.

## Simulation model

Real goals scored/conceded are normalized by each edition's competition scoring average. An eight-match prior pulls small samples toward the competition mean. Expected 90-minute goals use:

```text
home = clamp(1.35 × home.attack × away.defense × venue_factor, 0.15, 4.5)
away = clamp(1.35 × away.attack × home.defense × venue_factor, 0.15, 4.5)
```

Neutral venue factors are 1.0; home advantage uses 1.12 for home and 0.92 for away. These coefficients are explicit heuristic assumptions, not fitted or calibrated results. Cross-league and club/national comparisons assume equal baseline competition strength; no measured cross-competition adjustment is claimed.

A seeded generator samples shot counts, shot quality, outcomes, pass events and event times. The generated goal rate matches the declared expected-goal rate in Monte Carlo tests. Match outcome estimates sum independent Poisson distributions for remaining goals, conditioned on score and time. The engine ends at 90 minutes: no extra time or shootouts. International input scores can include extra time, so tournament-derived rates are approximations.

**These are hypothetical matches, not historical replays or calibrated forecasts.** No historical player rosters, lineups, injuries, formations or tactical styles are included. Anonymous event units avoid attributing invented events to real players. Possession remains a completed-pass-share proxy. Momentum reflects generated attacking events.

The original six club crests are bundled locally. Other team editions use readable initials when a crest asset is not available; no incorrect badge is substituted.

## Data provenance and refresh

Sources are [OpenFootball](https://github.com/openfootball/football.json), [FootballCSV / Soccerverse](https://github.com/footballcsv/cache.soccerverse), and [Mart Jürisoo's international results](https://github.com/martj42/international_results), published under CC0. The catalog includes source URLs, SHA-256 hashes, per-edition match counts, cutoffs, team counts, and completeness.

Rebuild the current catalog from the downloaded source snapshots:

```sh
python3 scripts/build_catalog.py --as-of 2026-10-18
```

To download refreshed sources first (requires network access):

```sh
python3 scripts/download_sources.py
python3 scripts/build_catalog.py --as-of YYYY-MM-DD
```

Raw downloads live in ignored `.local/sources/`. The default builder cutoff stays fixed for reproducibility; explicitly update it when refreshing. Source hashes detect changed upstream snapshots. Refreshing data or changing model code can change outputs; preserve the catalog and model version when comparing experiments.

## Verify

Python 3.10+ and Node.js 20+:

```sh
npm test
```

Tests verify all 85 club season/league memberships, every supported international tournament edition, model bounds, venue behavior, deterministic generation, score/event agreement, probability normalization, Monte Carlo goal rates, and legacy SQLite ingestion reliability. The UI also passed a DOM smoke check of presets, selectors, search, replay, deterministic scores, filters, invalid seeds, crests, and partial-data labels.

## Local API and legacy ingestion demo

The Python server serves the simulator and provides a separate SQLite ingestion demo for the original three synthetic fixtures. Those routes do not store the new browser-generated simulations. Current scenarios are encoded in the URL; simulation events can be exported as CSV.

```sh
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/matches
curl 'http://127.0.0.1:8000/api/matches/city/state?minute=58.25'
curl 'http://127.0.0.1:8000/api/matches/city/events?minute=45'
# POST /api/events accepts normalized event batches for those legacy fixtures.
```

This unauthenticated API binds only to loopback and is intended for local development. It validates events, deduplicates IDs, rejects conflicting duplicates atomically, sorts by event time, and persists through restarts. The hosted site is static and does not deploy Python or SQLite. `generate_data.py` rebuilds only the three legacy fixtures, not the historical catalog or simulator.

## Remaining platform work

Historical rosters/player models; calibrated cross-era and cross-competition strengths; training/evaluation with chronological splits; real event feeds; FastAPI/PostgreSQL/Redis Streams/WebSockets; distributed recovery; observability; Docker/CI; load and failure benchmarks. Original performance and model-quality targets remain unverified.
