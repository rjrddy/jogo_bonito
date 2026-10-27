# Training an event model

**Status: none of this is built yet.** This is the setup guide and the design
decisions behind it. Scripts named below do not exist until you write them;
each section says what the script has to do.

## What you are replacing

`dist/simulator.js` invents events from a seeded RNG. Four things are wrong
with them, and all four are visible in the UI:

| Current behaviour | Where | Why it shows |
| --- | --- | --- |
| Shot minutes uniform on 0–90 | `simulator.js` `simulate()` | No build-up, no late-game push, no injury time. The momentum chart is noise. |
| xG uniform on 0.05–0.25 | same | Real shot xG is heavily right-skewed. A tap-in and a 30-yard shot score alike. |
| Shot location derived *from* xG | same | Backwards. Location should determine xG, not the reverse. |
| Pass coordinates uniform on the pitch | same | No possession chains, no territory, no structure. |

A model trained on real event streams fixes all four. The team-strength layer
(`expectedGoals`) stays as it is — it is measured and it wins its benchmark.
You are replacing the event generator underneath it, not the ratings.

## The blocker: this repo has no event data

The 31,412 bundled results are final scores. The squad files have no match
events. The three fixtures in `dist/matches.json` are synthetic. You have to
bring event data in.

| Source | Size | Licence | Notes |
| --- | --- | --- | --- |
| [StatsBomb Open Data](https://github.com/statsbomb/open-data) | ~3,000 matches | CC BY-NC-SA 4.0 | Richest. Shot freeze frames give defender positions. World Cups, Messi's La Liga years, FAWSL. |
| [Wyscout public dataset](https://figshare.com/collections/Soccer_match_event_dataset/4415000) | 1,941 matches, ~3.25M events | CC BY 4.0 | Big-five 2017/18 plus WC 2018 and Euro 2016. Flatter schema, easier to parse. |
| [SkillCorner open data](https://github.com/SkillCorner/opendata) | 9 matches | CC BY-NC 4.0 | Tracking, not events. Too small to train on. |

Start with StatsBomb. Its non-commercial clause matches the posture this
project already has with FootballSquads, so note it in the README the same way.

Roughly 5,000 matches is a modest corpus for a generative model. That ceiling,
not the GPU, is what limits how large a model is worth training.

## Do it in two stages

Stage one is small, fast and independently useful. Do not skip to stage two.

### Stage 1 — an xG model

One shot in, one probability out. Trains in minutes, has a crisp evaluation,
and drops straight into the `xg` field the whole dashboard already sums.

Features from a StatsBomb shot: `x`, `y`, distance and angle to goal, body
part, assist type, under-pressure flag, and the defender count from the freeze
frame. Fit logistic regression first, then gradient boosting, and keep whichever
wins on held-out log loss.

Export the coefficients to JSON and write the forward pass by hand in JS. This
is exactly what `dist/scouting-engine.js` already does: the Python builder is
the specification, the JS is a port, and parity fixtures in the model file fail
the test suite on any divergence beyond 1e-9. Follow that pattern rather than
inventing a second one. A logistic model needs no runtime dependency at all.

### Stage 2 — an event sequence model

A decoder-only transformer over tokenised events, conditioned on the two team
strengths, venue and tactics so it slots in behind `expectedGoals`.

**Tokenisation.** Discretise the pitch into a 16×12 grid (192 zones). A token
is `(event type, zone, outcome, time-delta bucket)`. Keep the type vocabulary
small — the app only renders `shot` and `pass`, so collapse carries and duels
into the pass stream or drop them. Prefix each sequence with conditioning
tokens for home attack, home defence, away attack, away defence, venue and the
two tactical approaches, bucketed.

**Size.** With ~5,000 matches you are data-bound, not VRAM-bound. Start small
and only grow if held-out loss is still falling.

| Config | Layers | d_model | Params | VRAM at batch 32 | Use |
| --- | ---: | ---: | ---: | ---: | --- |
| small | 6 | 256 | ~6M | ~3 GB | start here |
| medium | 12 | 512 | ~40M | ~8 GB | only if small underfits |
| large | 24 | 768 | ~170M | ~14 GB | will overfit this corpus |

## Environment

The 5070 Ti is Blackwell, compute capability **12.0 (sm_120)**. PyTorch wheels
built before Blackwell support only go up to sm_90 and fail at the first kernel
launch with `no kernel image is available for execution on the device`. You
need a CUDA 12.8 build.

```sh
# Driver: 570+ on Linux, 572+ on Windows.
nvidia-smi

python3 -m venv .venv-train
./.venv-train/bin/pip install torch --index-url https://download.pytorch.org/whl/cu128
./.venv-train/bin/pip install numpy pandas scikit-learn onnx onnxruntime tqdm
```

Verify before you train anything:

```sh
./.venv-train/bin/python -c "import torch; print(torch.__version__, torch.cuda.get_device_capability())"
# expect (12, 0)
```

Keep this separate from the project venv. The app has no runtime dependencies
and that property is worth protecting — training deps never ship.

Use bf16 autocast rather than fp16; Blackwell handles it natively and you avoid
loss scaling. `torch.compile` is worth the first-run compile cost here.

## Pipeline

Four scripts to write, under `scripts/events/`:

1. **`download.py`** — fetch the open data into `.local/events/`, record SHA-256
   hashes the way `build_catalog.py` does. Gitignored; never commit the corpus.
2. **`build_dataset.py`** — parse into a flat Parquet table of events, one row
   per event with match id, period, timestamp, type, x, y, outcome, player.
   Hold out whole matches, never individual events, and split by date so the
   validation set is later than training. This repo validates forward in time
   everywhere else; stay consistent.
3. **`train_xg.py`** — stage one. Writes `dist/models/xg.json` plus parity
   fixtures.
4. **`train_events.py`** — stage two. Writes a checkpoint and exports ONNX.

Add `.local/events/`, `.venv-train/` and `checkpoints/` to `.gitignore`.

## Evaluation

Nothing ships without a held-out number next to a baseline, same as the match
engine in [methodology.md](methodology.md).

**xG model:** log loss and Brier on held-out shots, against two baselines — the
overall conversion rate, and distance-only logistic regression. Plot calibration
in deciles. StatsBomb publish their own xG per shot; treat it as a reference
point, not ground truth.

**Sequence model:** held-out negative log-likelihood per event, plus
distributional checks against real matches — shots per match, shot-location
heatmap divergence, time to first shot, possession chain length, pass completion
by zone.

## Integration constraints

Three things the trained model must not break.

**The event contract.** `dist/engine.js` and the dashboard read exactly
`{id, match_id, minute, team, type, player, player_id, x, y, xg, outcome}`.
`type` is `shot` or `pass`. Shot outcomes are `goal | saved | blocked | off
target`; pass outcomes are `complete | incomplete`. Coordinates are 0–100 with
home attacking right. Emit that shape or the UI breaks.

**The goal-rate invariant.** `tests/simulator.test.mjs` runs 1,200 seeds and
asserts the generated home-goal rate tracks the rate `expectedGoals` declares,
within 0.12. The Forecast lab reads the declared Poisson rates while the
Matchroom reads generated events, so if the generator drifts the two views start
disagreeing. A learned generator needs calibrating back onto the declared rate —
the cleanest way is to sample conditioned on the target rate and reject or
rescale until it holds.

**Determinism.** Same seed, same match. Share links and the notebook depend on
it. Seed the sampler explicitly and avoid non-deterministic GPU kernels in
export; browser inference should be fp32 and reproducible.

**No runtime dependency.** A logistic xG model is a dot product — hand-roll it.
A transformer needs `onnxruntime-web`, which is roughly 10 MB of WASM. If you go
that way, vendor it into `dist/` rather than hotlinking a CDN, and bump the
model-version string so cached share links stay reproducible.

## Risks worth knowing before you start

- **Corpus size caps quality.** 5,000 matches is small for sequence generation.
  Expect plausible local structure and weak long-range coherence.
- **Competition mismatch.** The open data skews to World Cups and specific
  league-seasons. The app covers five leagues, 2010–2026. The model will be
  extrapolating for most editions, which is the same uncalibrated cross-era
  problem the README already declares.
- **Licensing.** StatsBomb is non-commercial with attribution. Credit it next to
  FootballSquads and keep the deployment non-commercial.
- **It may not beat the current generator on the things that are measured.**
  The Dixon-Coles attempt lost to the heuristic; publish the result either way.
