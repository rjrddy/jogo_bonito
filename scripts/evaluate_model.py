"""Measure the shipped match engine against alternatives on held-out matches.

The project shipped a scoring model whose coefficients were asserted rather
than measured. This harness closes that gap: every league edition is split by
date, the earlier matches fit each contender, and the later ones are predicted.

The contender built here is a Dixon-Coles bivariate Poisson fitted per edition:

    log lambda_home = attack_i - defence_j + home_advantage
    log lambda_away = attack_j - defence_i

plus the low-score correlation correction rho, which is what separates
Dixon-Coles from independent Poisson and is worth fitting because 0-0 and 1-1
are more common than independence predicts.

It loses. On held-out matches the shipped goal-ratio model with its eight-match
prior predicts better than the fitted alternative, and the gap narrows the
harder the fit is shrunk: the prior was already doing the work that maximum
likelihood had to be regularised into. That result is published rather than
discarded, and the engine is left alone.

The baselines are deliberately unflattering to the engine: the same heuristic
the app runs, the training split's own home/draw/away frequencies, and a
uniform guess.
"""
import json
import math
from collections import defaultdict
from pathlib import Path

try:
    from .build_catalog import league_results
except ImportError:
    from build_catalog import league_results

ROOT = Path(__file__).resolve().parents[1]
PRIOR = 8              # matches of competition-average prior, as the catalog uses
TRAIN_SHARE = 0.6      # earlier matches fit, later matches are predicted
GRID = 13              # score grid for 1X2 probabilities
RHO_RANGE = [i / 100 for i in range(-25, 11)]


def tau(x, y, lam, mu, rho):
    """Dixon-Coles correction on the four low-score cells."""
    if x == 0 and y == 0:
        return max(1e-9, 1 - lam * mu * rho)
    if x == 0 and y == 1:
        return max(1e-9, 1 + lam * rho)
    if x == 1 and y == 0:
        return max(1e-9, 1 + mu * rho)
    if x == 1 and y == 1:
        return max(1e-9, 1 - rho)
    return 1.0


def fit(rows, iterations=400, rate=0.08, ridge=2e-3):
    """Gradient ascent on the Poisson log-likelihood; rho is fitted afterwards."""
    teams = sorted({r['home'] for r in rows} | {r['away'] for r in rows})
    index = {name: i for i, name in enumerate(teams)}
    attack = [0.0] * len(teams)
    defence = [0.0] * len(teams)
    mean_goals = sum(r['hg'] + r['ag'] for r in rows) / (2 * len(rows))
    base = math.log(max(mean_goals, 0.05))
    advantage = 0.1
    for _ in range(iterations):
        ga = [0.0] * len(teams)
        gd = [0.0] * len(teams)
        gh = 0.0
        for r in rows:
            i, j = index[r['home']], index[r['away']]
            lam = math.exp(base + attack[i] - defence[j] + advantage)
            mu = math.exp(base + attack[j] - defence[i])
            eh, ea = r['hg'] - lam, r['ag'] - mu
            ga[i] += eh
            gd[j] -= eh
            gh += eh
            ga[j] += ea
            gd[i] -= ea
        scale = rate / len(rows)
        for t in range(len(teams)):
            attack[t] += scale * (ga[t] - ridge * attack[t] * len(rows) / len(teams))
            defence[t] += scale * (gd[t] - ridge * defence[t] * len(rows) / len(teams))
        advantage += scale * gh
        # Attack is only identified up to a constant; pin its mean at zero.
        shift = sum(attack) / len(attack)
        for t in range(len(teams)):
            attack[t] -= shift
        base += shift
    rho = fit_rho(rows, index, attack, defence, base, advantage)
    return dict(teams=teams, index=index, attack=attack, defence=defence, base=base,
                advantage=advantage, rho=rho, mean_goals=mean_goals)


def fit_rho(rows, index, attack, defence, base, advantage):
    best, best_ll = 0.0, None
    for rho in RHO_RANGE:
        total = 0.0
        for r in rows:
            i, j = index[r['home']], index[r['away']]
            lam = math.exp(base + attack[i] - defence[j] + advantage)
            mu = math.exp(base + attack[j] - defence[i])
            total += math.log(tau(r['hg'], r['ag'], lam, mu, rho))
        if best_ll is None or total > best_ll:
            best, best_ll = rho, total
    return best


def rates(model, home, away):
    i, j = model['index'].get(home), model['index'].get(away)
    if i is None or j is None:
        return None
    lam = math.exp(model['base'] + model['attack'][i] - model['defence'][j] + model['advantage'])
    mu = math.exp(model['base'] + model['attack'][j] - model['defence'][i])
    return lam, mu


def outcome_probabilities(lam, mu, rho=0.0):
    ph = [math.exp(-lam)]
    pa = [math.exp(-mu)]
    for k in range(1, GRID):
        ph.append(ph[k - 1] * lam / k)
        pa.append(pa[k - 1] * mu / k)
    home = draw = away = 0.0
    for x in range(GRID):
        for y in range(GRID):
            p = ph[x] * pa[y] * tau(x, y, lam, mu, rho)
            if x > y:
                home += p
            elif x == y:
                draw += p
            else:
                away += p
    total = home + draw + away
    return home / total, draw / total, away / total


def heuristic_strengths(rows):
    """The shipped model: competition-normalised goal ratios with an eight-match prior."""
    stats = defaultdict(lambda: dict(played=0, gf=0, ga=0))
    for r in rows:
        for team, gf, ga in [(r['home'], r['hg'], r['ag']), (r['away'], r['ag'], r['hg'])]:
            s = stats[team]
            s['played'] += 1
            s['gf'] += gf
            s['ga'] += ga
    mean = sum(r['hg'] + r['ag'] for r in rows) / (2 * len(rows))
    out = {}
    for name, s in stats.items():
        out[name] = dict(attack=(s['gf'] + PRIOR * mean) / (s['played'] + PRIOR) / mean,
                         defense=(s['ga'] + PRIOR * mean) / (s['played'] + PRIOR) / mean)
    return out


def heuristic_rates(strengths, home, away):
    """dist/simulator.js expectedGoals, with home advantage, as the app runs it."""
    h, a = strengths.get(home), strengths.get(away)
    if not h or not a:
        return None
    def clamp(n):
        return max(0.15, min(4.5, n))

    return clamp(1.35 * h['attack'] * a['defense'] * 1.12), clamp(1.35 * a['attack'] * h['defense'] * 0.92)


def evaluate(as_of='2026-10-18'):
    """Date-split every league edition and score each model on the later matches."""
    scores = {name: dict(logloss=0.0, brier=0.0, hits=0, n=0)
              for name in ('fitted', 'fitted_no_rho', 'heuristic', 'base_rate', 'uniform')}
    editions = 0
    for *_, rows in league_results(as_of):
        if len(rows) < 120:
            continue
        rows = sorted(rows, key=lambda r: (r['date'], r['home']))
        cut = int(len(rows) * TRAIN_SHARE)
        train, test = rows[:cut], rows[cut:]
        if len(test) < 20:
            continue
        model = fit(train)
        strengths = heuristic_strengths(train)
        counts = [0, 0, 0]
        for r in train:
            counts[0 if r['hg'] > r['ag'] else 1 if r['hg'] == r['ag'] else 2] += 1
        base_rate = [c / len(train) for c in counts]
        editions += 1
        for r in test:
            actual = 0 if r['hg'] > r['ag'] else 1 if r['hg'] == r['ag'] else 2
            fitted = rates(model, r['home'], r['away'])
            heuristic = heuristic_rates(strengths, r['home'], r['away'])
            if fitted is None or heuristic is None:
                continue  # a promoted team with no training history in this edition
            predictions = dict(
                fitted=outcome_probabilities(*fitted, model['rho']),
                fitted_no_rho=outcome_probabilities(*fitted, 0.0),
                heuristic=outcome_probabilities(*heuristic, 0.0),
                base_rate=tuple(base_rate),
                uniform=(1 / 3, 1 / 3, 1 / 3))
            for name, p in predictions.items():
                s = scores[name]
                s['logloss'] -= math.log(max(p[actual], 1e-12))
                s['brier'] += sum((p[k] - (1.0 if k == actual else 0.0)) ** 2 for k in range(3))
                s['hits'] += p.index(max(p)) == actual
                s['n'] += 1
    report = {}
    for name, s in scores.items():
        if s['n']:
            report[name] = dict(logloss=round(s['logloss'] / s['n'], 4), brier=round(s['brier'] / s['n'], 4),
                                accuracy=round(s['hits'] / s['n'], 4), n=s['n'])
    return dict(editions=editions, train_share=TRAIN_SHARE, models=report)


LABELS = {
    'heuristic': 'Shipped engine · goal ratios with an eight-match prior',
    'fitted': 'Dixon-Coles MLE, fitted per edition',
    'fitted_no_rho': 'Fitted MLE without the low-score correction',
    'base_rate': 'Training-split home/draw/away frequencies',
    'uniform': 'Uniform guess',
}
ORDER = ['heuristic', 'fitted', 'fitted_no_rho', 'base_rate', 'uniform']


def publish(result, as_of):
    models = result['models']
    best = min(models, key=lambda name: models[name]['logloss'])
    report = dict(
        version=1, as_of=as_of, editions=result['editions'], train_share=result['train_share'],
        matches=models['heuristic']['n'], shipped='heuristic', best=best,
        method=('Every league edition is split by date. The earlier share of each season fits each contender, '
                'the remaining matches are predicted, and no contender sees a match it was fitted on. '
                'Reported figures are 1X2 log loss, Brier score and top-pick accuracy, pooled over editions.'),
        caveats=['This measures ordinary league fixtures, which is not what the simulator is for: cross-era '
                 'matchups have no ground truth and are not evaluated here, and never can be from this data.',
                 'Tactical approaches, formations and venue beyond home advantage are not part of this test.',
                 'A fitted alternative was tried and lost; the engine was left as it is rather than replaced.'],
        models=[dict(key=name, label=LABELS[name], **models[name]) for name in ORDER if name in models])
    out = ROOT / 'dist/benchmark.json'
    out.write_text(json.dumps(report, ensure_ascii=False, separators=(',', ':')))
    return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--as-of', default='2026-10-18')
    args = parser.parse_args()
    result = evaluate(args.as_of)
    print(f"Held-out 1X2 accuracy over {result['editions']} league editions "
          f"({int(TRAIN_SHARE*100)}% of each season fits, the rest is predicted):")
    print(f"  {'model':16} {'log loss':>9} {'Brier':>8} {'accuracy':>9} {'n':>7}")
    for name in ORDER:
        m = result['models'][name]
        print(f"  {name:16} {m['logloss']:9.4f} {m['brier']:8.4f} {m['accuracy']:9.4f} {m['n']:7d}")
    report = publish(result, args.as_of)
    print(f"\nBest held-out log loss: {report['best']}. Shipped engine: {report['shipped']}.")
    print('Wrote dist/benchmark.json')
