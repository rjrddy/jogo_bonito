# Jogo Bonito · The Match Lab

A historical football matchup simulator. Play **2023 Manchester City vs 2016 Real Madrid**, **2012 Spain vs 2022 Argentina**, or any pair of supported team editions, including club-versus-country experiments.

## Run

Requires Python 3.10+. No runtime dependencies, API keys, or paid feeds.

```sh
python3 server.py
# Open http://127.0.0.1:8000
```

The simulator also runs on static hosting: serve `dist/` over HTTP. Its catalog and match engine are bundled, with no third-party data requests at runtime. Google Fonts is optional; local font fallbacks are defined.

## The Match Lab

The interface now has dedicated workspaces:

| Workspace | Features |
| --- | --- |
| Matchroom | Badge-led fixture cards, independent eras, side swapping, random fixtures, venue settings, seed controls, replay, shot maps, xG and momentum |
| Team sheets | Six formation boards, selectable real XIs, recorded coaches, and historical team comparisons |
| Scout lab | The current crop of under-21 players, aged to today, projected and matched to club editions by two offline-trained models; scope switches to past cohorts to check the track record, plus a form for prospects the data has never seen |
| Forecast lab | Exact 7×7 scoreline probability grid, both-teams-score/over-2.5 estimates, and seeded batches of 100, 1,000 or 10,000 scorelines |
| Match report | Player goals, shots, xG, passes and completion; search, side filters and sorting; key moments and event rows that seek the replay |
| Notebook | Up to 20 named saved fixtures and the last 10 completed results, stored only in this browser |
| Data & method | Result/squad provenance, coverage and model assumptions |

**Match setup:** choose the competition, edition and team for each side. Choose formations and approaches, inspect or edit each XI, select the venue and seed, then **Simulate match**. A visible pending-changes label distinguishes edited setup from the running simulation. **Swap sides** preserves each XI and game plan while swapping the teams. **Shuffle fixture** samples another pair of historical editions. The setup can be collapsed during analysis.

**Replay:** play/pause, restart, seek, change speed, skip to full time or jump to the previous/next chance. Space toggles playback and left/right arrows seek five match minutes when focus is outside a control. Player ledgers, highlights and event tables reflect the current replay prefix. Charts and tables refresh at a capped cadence during playback.

**Keep and share:** share links include both editions, selected XIs, formations, tactical choices, venue and seed. A `?view=` parameter opens a specific workspace directly, so `?view=scout` links straight to the Scout lab. CSV exports include the current event prefix and configuration metadata. JSON exports contain the full simulated match, event list, XIs and configuration. Reproduction assumes the same model version and data snapshot. Notebook storage is local to the browser; it is not a cloud account. Storage failure is handled with a visible message and sharing/export remains available.

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
home = clamp(1.35 × home.attack × away.defense × home_approach.attack × away_approach.exposure × venue_factor, 0.15, 4.5)
away = clamp(1.35 × away.attack × home.defense × away_approach.attack × home_approach.exposure × venue_factor, 0.15, 4.5)
```

Neutral venue factors are 1.0; home advantage uses 1.12 for home and 0.92 for away. These coefficients are explicit heuristic assumptions, not fitted or calibrated results. Cross-league and club/national comparisons assume equal baseline competition strength; no measured cross-competition adjustment is claimed.

Approach multipliers are explicit experimental assumptions:

| Approach | Own attacking multiplier | Exposure to opponent |
| --- | --- | --- |
| Balanced | 1.00 | 1.00 |
| Keep the ball | 1.04 | 0.96 |
| High press | 1.12 | 1.10 |
| Counterattack | 1.06 | 1.02 |
| Low block | 0.84 | 0.86 |

Formations affect the suggested selection and pitch layout, not player ability or an additional scoring adjustment. Tactical choices are not fitted coach styles. The scoreline grid sums its 6+ tail buckets to retain all probability mass. Batch experiments sample the same independent Poisson pre-match score distribution without generating full event streams. Sampling frequencies are not held-out model evaluation or measured predictive accuracy.

A seeded generator samples shot counts, shot quality, outcomes, pass events and event times. The generated goal rate matches the declared expected-goal rate in Monte Carlo tests. Match outcome estimates sum independent Poisson distributions for remaining goals, conditioned on score and time. The engine ends at 90 minutes: no extra time or shootouts. International input scores can include extra time, so tournament-derived rates are approximations.

**These are hypothetical matches, not historical replays or calibrated forecasts.** Historical squads and recorded coaches are available in the builder. Suggested XIs are based on listed positions and source order, not verified historical starters. Actions are attributed to selected players with positional heuristic weights; their abilities and coaches do not alter the team-level outcome model. Injuries and tactical styles are not modeled. Possession remains a completed-pass-share proxy. Momentum reflects generated attacking events.

Every club edition now has a locally bundled real badge: **192 club identities**, covering **249 historical name variants** across **all 1,660 club editions**. National teams retain their separate fallback behavior. Badges identify the club; a complete year-specific badge design history is not claimed. The badge manifest records each source, asset hash, alias, and edition mapping, and tests reject missing badge coverage.

## Scout lab

Two supervised models, fitted offline by `scripts/build_scouting.py` from this repository's own data. No network access, no API key, no third-party model: the browser downloads the weights and runs inference itself.

Both are named for what the squad data can actually witness, which is narrower than the word "scouting" suggests. Read the limits below before trusting a number.

**Destination ranking** predicts which club a player moves to next. The snapshots record **8,412 club-to-club moves**; 5,327 of them train the weights and the 3,085 later ones are held back. Training is a sampled softmax over one true destination against 8 sampled alternatives. The score is a learned club embedding dotted with a player tower, plus named additive player×club terms, so every recommendation decomposes into reasons rather than arriving as a bare number.

**Scope.** The board opens on the newest squads in the snapshot — the players who are under-21 *now*, aged to today rather than to the season they were listed in. Those prospects carry no recorded outcome by construction: their six-season window runs past the cutoff, which is precisely what makes them the ones worth scouting. Switching the scope to past cohorts shows the players whose careers the snapshot can already score, which is where the model's track record is visible rather than its predictions. When a prospect's own outcome is still open, the comparables are drawn only from past players whose careers are resolved, so every neighbour shows what actually happened.

**Progression** projects which calibre of squad list a player first seen at 21 or younger appears on 2 to 6 seasons later, across four classes: no further top-five squad, squad-level club, regular-level club, elite club. Class priors are recalibrated on cohorts the weights never saw. Its output feeds the destination ranker as a feature, which is what lets the ranker treat a highly-rated prospect's options differently from an ordinary mover's.

### Held-out results

Validation is a forward split in time, never a random shuffle. For destinations, every observed move from **2021** onwards; for progression, cohorts from **2018** onwards. Baselines face the identical task on the identical rows.

Ranking the true destination among the ~96 club editions available that season (n = 3,085):

| | Top 1 | Top 5 | Top 10 | Top 25 | MRR | Median rank |
| --- | --- | --- | --- | --- | --- | --- |
| **This model** | **4.3%** | **21.0%** | **38.1%** | **65.9%** | **0.146** | **15** |
| Most-active clubs | 1.5% | 5.8% | 12.1% | 28.6% | 0.060 | 46 |
| Closest club level | 1.4% | 6.4% | 11.7% | 31.1% | 0.062 | 44 |

Progression, on 3,285 held-out cohorts: accuracy **50.7%** against 46.8% for always predicting the most common class, and a Brier score of **0.6432** against 0.687 for the base rate (0.6454 before recalibration). Per-class AUC: no further top-five squad 0.667, squad-level club 0.549, regular-level club 0.581, elite club 0.777 — the middle classes are barely separable and the model card prints that rather than hiding it. Every class lands within 2.5 points of its observed rate.

### Why the numbers mean what they say

* A club's profile for a destination season describes that club **the season before**, so no candidate feature sees the season the prospect would be arriving into — including the prospect's own presence in that squad.
* Club identity comes from the bundled badge manifest, which resolves the catalog's 249 club spellings to **192 real clubs**. Without it a rename such as *Athletic Bilbao* to *Athletic Club* reads as a transfer; fixing it removed 646 spurious moves from the training data and the metrics above are the lower, honest ones that resulted.
* Cohorts whose window runs past the 2026-10-18 cutoff are left **unlabelled**, not guessed at: 7,974 of 19,076 pool entries have an observable outcome.
* The progression window deliberately skips the season immediately after the cohort season. Counting it made the target tautological — a teenager on an elite squad list who is listed there again a year later would "reach elite" without progressing. Measured on held-out cohorts, including that season buys 7.7 points of accuracy lift over the majority class but keeps the artifact; skipping two seasons leaves censoring at 59% of the label and only 0.9 points of lift. Skipping one keeps 3.9% of lift with the artifact gone.
* The ranker is trained on moves only, so it has no fitted opinion on a player staying put; that term keeps a weight of exactly zero and the interface says so.
* `tests/scouting.test.mjs` replays 40 prospects and 120 candidate pairs from the Python pipeline through the JavaScript port and fails on any divergence beyond 1e-9. The feature builders exist twice and must agree exactly; a width mismatch raises rather than silently truncating.

### What the ranker learned

Fitted weights on the named cross terms, largest first:

| Term | Weight |
| --- | --- |
| position_need | +6.244 |
| nation_share | +3.148 |
| same_competition | +1.738 |
| corridor | +1.205 |
| youth_fit | +0.933 |
| step_up_young | +0.622 |
| elite_step | -0.517 |
| level_gap_sq | -0.366 |

A gap at the prospect's position dominates everything else, then compatriots already in the squad, then staying in the same league. The level terms are negative for everyone, including the two that interact with the progression score: in this data the average move by a young player is lateral or **downward**, because a teenager at a strong club most often goes out on loan. That is a real pattern, and it is why the output is labelled "where players like this go next" rather than "best fit".

### Honest limits

* **There is no academy data in this project.** The pool is the 19,076 under-21 player-seasons inside the bundled senior-squad snapshots, covering 142 nationalities across all six confederations. That is the youngest cohort these sources can observe — not a youth-team intake. A player who never reached a senior squad list is invisible here. The *Enter a prospect* form exists for players the snapshot has never seen; it scores the attributes you supply and cannot verify them.
* **A squad list records who a club registered, never who played.** So the progression target is which calibre of list a career later appears on, not how good it became. A teenager who stays registered at an elite club for years without playing reaches the top class exactly like one who starred there, and the model cannot tell them apart.
* **Consequently the highest projections cluster on big-club academy intakes.** Being at an elite club at 18 is itself the strongest evidence of being on an elite club's list at 21. Nine of the ten highest 2019 projections are Manchester City academy names. The model is right about the label and the label is not ability.
* **The ranker predicts recorded destinations, loans included**, which this source cannot separate from permanent transfers. It reports the market; it does not name who ought to sign a player.
* Squad lists carry **no minutes, fees, transfer values, injuries or scouting grades**. None of those inform the models, because none exist in this data.
* "No further top-five squad" is **censoring, not failure**. A move to a league outside these five is indistinguishable from leaving football.
* Cross-era and cross-league strength is uncalibrated here, exactly as everywhere else in this project.
* Archetypes are k-means clusters over the ranker's latent space, named from their own members' averages.

Rebuild the models (a few minutes, pure standard library, seed 20261021):

```sh
npm run data:scouting
```

This writes `dist/scouting/model.json` (98 KB of weights, metrics and parity fixtures), `clubs.json` (793 KB of club profiles) and `prospects.json` (1241 KB of pool rows). The Scout lab fetches all three the first time it is opened, so the Matchroom pays nothing for them.

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

Scouting models are rebuilt separately with `npm run data:scouting`, which reads only `dist/catalog.json` and `dist/rosters/`; rerun it after any catalog or roster refresh so the pool and the held-out metrics match the snapshot.

Raw downloads live in ignored `.local/sources/`. The default builder cutoff stays fixed for reproducibility; explicitly update it when refreshing. Source hashes detect changed upstream snapshots. Refreshing data or changing model code can change outputs; preserve the catalog and model version when comparing experiments.

## Historical squads and coaches

The bundled archive covers **all 2,002 supported team editions**, with **75,844 player-edition records** and **2,002 recorded coach snapshots**. These are repeated historical player records, not 75,844 unique people.

Expand **Squad & coach** under either team to browse the source roster, search players, inspect positions and squad numbers, and select an XI. Suggested XIs support 4-3-3, 4-2-3-1, 4-4-2, 3-5-2, 5-3-2 and 3-4-3 where positions allow. Changing formation resets that side’s suggested XI; users can then edit it. Exactly 11 players with one goalkeeper are required. Players marked as departed in the source remain visible in the season archive and cannot enter the snapshot XI. Squad lists can include academy and reserve players: they are source snapshots, not official registration certificates or dated match eligibility lists.

Coaches are shown as **recorded in the source snapshot**. A season with multiple managers is not reduced to a claim that the displayed coach managed every match; complete managerial tenure histories are not included.

Squad pages are bundled in separate edition files and loaded only when selected. Player selections are independent on both sides, included in scenario URLs and CSV exports, and produce reproducible attribution. A separate random stream assigns actions, preserving the existing numeric team-strength simulation. Goalkeepers are excluded from shot attribution.

The squad source is [FootballSquads](https://www.footballsquads.co.uk/), whose [terms](https://www.footballsquads.co.uk/tou.htm) allow non-commercial use with attribution. **These roster data are not CC0 and are not licensed for commercial reuse by this project.** The required attribution appears in the application and every roster retains its source URL and SHA-256 snapshot hash.

> Source of Material is http://www.footballsquads.com. Material: © FootballSquads.com, 1999 - , All Rights Reserved

Refresh squad data (network required; cached pages are reused):

```sh
npm run data:rosters
# Parse cached pages without network:
python3 scripts/import_rosters.py --offline
python3 scripts/package_rosters.py
```

The import records missing editions, name mapping gaps and download errors in `.local/rosters/import-report.json`. Names are joined through explicit audited aliases within the same competition and year; fuzzy matches are not silently accepted. `dist/rosters/index.json` exposes actual coverage counts and missing editions. Empty or unverified squads are not invented.

## System light and dark mode

The site follows `prefers-color-scheme`, including changes while the page is open. CSS and SVG chart colours use shared theme variables, and the browser chrome uses matching theme-colour metadata. There is no saved override to conflict with your device preference. The pitch and broadcast scoreboard retain their football colours in both themes.

## Verify

Python 3.10+ and Node.js 20+:

```sh
npm test
```

Tests verify all 85 club season/league memberships, every supported international tournament edition, model bounds, venue behavior, deterministic generation, score/event agreement, probability normalization, Monte Carlo goal rates, and legacy SQLite ingestion reliability. Browser checks cover formations, tactical rate changes, team sheets, reproducible 10,000-match experiments, player totals and filters, highlight seeking, notebook persistence/removal, URL reloads, swapping, random fixtures, JSON export, system themes and mobile overflow. Pure model tests compare sampled outcomes with the exact distribution and check player-stat totals against events. Scouting tests cover cross-language feature parity, no-leakage club profiling, club-identity resolution, pool bounds, unlabelled recent cohorts, additive fit explanations, probability normalization, and that every published metric still beats the baseline it is shown against. A DOM shim drives the real Scout lab controller against the real markup, so a missing control or a broken render path fails the suite.

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

Player ability ratings from match data; full transfer dates and manager tenures; real academy and youth-team rosters; minutes, fees and valuations to replace squad-list proxies; calibrated cross-era and cross-competition strengths; training/evaluation with chronological splits; real event feeds; FastAPI/PostgreSQL/Redis Streams/WebSockets; distributed recovery; observability; Docker/CI; load and failure benchmarks. Original performance and model-quality targets remain unverified.


## Club badge assets

Badge provenance and exact mappings are in `dist/assets/crests/clubs.json`. Most additional vectors come from [JoseArroyave/football-logos](https://github.com/JoseArroyave/football-logos); the existing six crests are retained from football-data.org, and the original historical Arles-Avignon and Évian crests are sourced from Wikimedia. Club trademarks and artwork belong to their respective owners.

`python3 scripts/build_badges.py` regenerates the bundled assets and mappings from cached source assets in `.local/sources/`. Normal catalog refreshes reuse the manifest, preserving all resolved badges. Any newly introduced club must be assigned an actual crest before the coverage tests pass.

Match colours follow the bundled club badges across shot maps, momentum, xG, scoreline heat maps, team statistics, formations and reports. `dist/badge-colors.json` stores dominant chromatic clusters sampled from all 192 club crests; `dist/team-colors.js` reviews major-club primaries, selects badge-secondary colours for clashes and adjusts text contrast with the system theme. Monochrome crests use black and white; international sides use national colours where defined and a neutral fallback otherwise. Away xG lines are dashed as a second visual cue.

All 77 national teams have locally bundled SVG flags in `dist/assets/flags`, sourced from [flag-icons v7.2.3](https://github.com/lipis/flag-icons/tree/v7.2.3) under its included MIT licence. The fixture picker and scoreboard display flags for national teams and crests for clubs. `scripts/build_flags.py` imports the pinned upstream ZIP; `scripts/build_catalog.py` retains those mappings during data refreshes. Flags represent the current national identity, rather than reconstructing historical flag changes.

Vercel deployment: the repository includes `vercel.json` configured to serve the static `dist` directory with no install or build step. Deploy from the repository root with `npx vercel@latest --prod`, or import `rjrddy/jogo_bonito` in Vercel for Git-based deployments. `.vercelignore` restricts uploads to the application assets and deployment configuration; local source caches are excluded.

Public Vercel URL: https://jogo-bonito-gamma.vercel.app. The Vercel project is connected to `rjrddy/jogo_bonito` for Git deployments.
