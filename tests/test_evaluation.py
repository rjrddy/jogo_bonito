"""Tests for the maximum-likelihood match ratings.

The central one is parameter recovery: generate matches from known strengths
and check the fitter finds them again. A fitter that cannot do that has no
business producing numbers the interface presents as measured.
"""
import json
import math
import random
import re
import unittest
from pathlib import Path

from scripts.evaluate_model import PRIOR, fit, heuristic_rates, heuristic_strengths, outcome_probabilities, rates, tau

ROOT = Path(__file__).resolve().parents[1]


def synthetic(attack, defence, advantage, base, seed=7, rounds=30):
    """Round-robin fixtures drawn from a known Poisson process."""
    rng = random.Random(seed)
    teams = list(attack)

    def draw(mean):
        # Knuth's method; adequate for the small means in football.
        limit, k, p = math.exp(-mean), 0, 1.0
        while True:
            p *= rng.random()
            if p <= limit:
                return k
            k += 1

    rows = []
    for _ in range(rounds):
        for home in teams:
            for away in teams:
                if home == away:
                    continue
                lam = math.exp(base + attack[home] - defence[away] + advantage)
                mu = math.exp(base + attack[away] - defence[home])
                rows.append(dict(date='2020-01-01', home=home, away=away, hg=draw(lam), ag=draw(mu)))
    return rows


class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.attack = {'A': 0.45, 'B': 0.15, 'C': 0.0, 'D': -0.2, 'E': -0.4}
        cls.defence = {'A': 0.35, 'B': 0.1, 'C': 0.0, 'D': -0.15, 'E': -0.3}
        cls.advantage = 0.26
        cls.base = math.log(1.35)
        cls.rows = synthetic(cls.attack, cls.defence, cls.advantage, cls.base)
        cls.model = fit(cls.rows)

    def test_attack_is_identified_only_up_to_its_mean(self):
        self.assertAlmostEqual(sum(self.model['attack']) / len(self.model['attack']), 0.0, places=6)

    def test_recovers_the_attack_ordering_and_magnitude(self):
        centred = {name: self.attack[name] - sum(self.attack.values()) / len(self.attack)
                   for name in self.attack}
        for name, index in self.model['index'].items():
            self.assertAlmostEqual(self.model['attack'][index], centred[name], delta=0.08,
                                   msg=f'attack for {name}')

    def test_recovers_defence_differences(self):
        index = self.model['index']
        for a, b in [('A', 'E'), ('A', 'C'), ('C', 'E')]:
            truth = self.defence[a] - self.defence[b]
            found = self.model['defence'][index[a]] - self.model['defence'][index[b]]
            self.assertAlmostEqual(found, truth, delta=0.1, msg=f'defence gap {a}-{b}')

    def test_recovers_home_advantage(self):
        self.assertAlmostEqual(self.model['advantage'], self.advantage, delta=0.06)

    def test_recovers_the_scoring_rates_it_was_generated_from(self):
        lam, mu = rates(self.model, 'A', 'E')
        truth_lam = math.exp(self.base + self.attack['A'] - self.defence['E'] + self.advantage)
        truth_mu = math.exp(self.base + self.attack['E'] - self.defence['A'])
        self.assertAlmostEqual(lam, truth_lam, delta=0.22)
        self.assertAlmostEqual(mu, truth_mu, delta=0.22)

    def test_independent_data_yields_no_low_score_correction(self):
        """The generator is independent Poisson, so rho should sit near zero."""
        self.assertAlmostEqual(self.model['rho'], 0.0, delta=0.06)


class ProbabilityTests(unittest.TestCase):
    def test_outcome_probabilities_normalise(self):
        for lam, mu, rho in [(1.5, 1.1, 0.0), (0.3, 2.7, -0.1), (2.2, 2.2, 0.08), (4.4, 0.2, -0.2)]:
            p = outcome_probabilities(lam, mu, rho)
            self.assertAlmostEqual(sum(p), 1.0, places=9)
            self.assertTrue(all(0 <= v <= 1 for v in p))

    def test_a_stronger_side_is_never_given_a_worse_chance(self):
        weak = outcome_probabilities(1.0, 1.4)[0]
        strong = outcome_probabilities(2.0, 1.4)[0]
        self.assertGreater(strong, weak)

    def test_the_correction_only_touches_low_scores(self):
        for x, y in [(0, 0), (0, 1), (1, 0), (1, 1)]:
            self.assertNotAlmostEqual(tau(x, y, 1.3, 1.1, -0.1), 1.0, places=6)
        for x, y in [(2, 0), (1, 2), (3, 3), (0, 4)]:
            self.assertEqual(tau(x, y, 1.3, 1.1, -0.1), 1.0)

    def test_the_correction_stays_positive_at_the_fitted_extremes(self):
        for rho in (-0.25, 0.1):
            for lam in (0.15, 4.5):
                for mu in (0.15, 4.5):
                    for x in range(2):
                        for y in range(2):
                            self.assertGreater(tau(x, y, lam, mu, rho), 0.0)


class HeuristicBaselineTests(unittest.TestCase):
    """The baseline must stay the model the app actually ships, or the
    comparison in the interface is against a straw man."""

    def setUp(self):
        self.rows = [dict(date='2020-01-01', home='A', away='B', hg=3, ag=0),
                     dict(date='2020-01-08', home='B', away='A', hg=1, ag=1),
                     dict(date='2020-01-15', home='A', away='C', hg=2, ag=1),
                     dict(date='2020-01-22', home='C', away='B', hg=0, ag=0)]

    def test_strengths_use_the_eight_match_prior_and_competition_mean(self):
        s = heuristic_strengths(self.rows)
        mean = sum(r['hg'] + r['ag'] for r in self.rows) / (2 * len(self.rows))
        self.assertAlmostEqual(s['A']['attack'], (6 + 8 * mean) / (3 + 8) / mean)
        self.assertAlmostEqual(s['A']['defense'], (2 + 8 * mean) / (3 + 8) / mean)

    def test_rates_match_the_shipped_formula_including_venue_and_clamp(self):
        s = heuristic_strengths(self.rows)
        lam, mu = heuristic_rates(s, 'A', 'B')
        self.assertAlmostEqual(lam, 1.35 * s['A']['attack'] * s['B']['defense'] * 1.12)
        self.assertAlmostEqual(mu, 1.35 * s['B']['attack'] * s['A']['defense'] * 0.92)
        self.assertTrue(all(0.15 <= v <= 4.5 for v in (lam, mu)))

    def test_an_unknown_team_is_reported_rather_than_guessed(self):
        self.assertIsNone(heuristic_rates(heuristic_strengths(self.rows), 'A', 'Newly promoted'))


class EngineParityTests(unittest.TestCase):
    """The harness reimplements the engine in Python to score it. If the two
    ever disagree, the published benchmark is measuring the wrong thing."""

    @classmethod
    def setUpClass(cls):
        cls.simulator = (ROOT / 'dist/simulator.js').read_text()
        cls.catalog_builder = (ROOT / 'scripts/build_catalog.py').read_text()

    def test_the_shipped_expected_goals_constants_are_the_ones_scored(self):
        """Compare the numbers, not how they are spelled: a formatter rewriting
        .92 as 0.92 must not look like a change to the model."""
        source = re.sub(r'\s+', '', self.simulator)
        base = re.search(r'constbase=([\d.]+);', source)
        self.assertIsNotNone(base, 'could not find the base scoring rate in dist/simulator.js')
        self.assertEqual(float(base.group(1)), 1.35)
        venue = [float(v) for v in re.findall(r"venue==='home'\?([\d.]+):1", source)]
        self.assertEqual(venue, [1.12, 0.92], 'home and away venue factors')
        bounds = {(float(lo), float(hi)) for lo, hi in re.findall(r',([\d.]+),([\d.]+),?\)', source)}
        self.assertIn((0.15, 4.5), bounds, 'expected-goal clamp bounds')

    def test_the_prior_matches_the_catalog_builder(self):
        self.assertIn(f'prior = {PRIOR}', self.catalog_builder)


class PublishedBenchmarkTests(unittest.TestCase):
    """Whatever the interface shows has to be what the harness actually found."""

    @classmethod
    def setUpClass(cls):
        path = ROOT / 'dist/benchmark.json'
        if not path.exists():
            raise unittest.SkipTest('run npm run data:benchmark first')
        cls.report = json.loads(path.read_text())
        cls.models = {m['key']: m for m in cls.report['models']}

    def test_the_shipped_engine_is_identified_and_present(self):
        self.assertEqual(self.report['shipped'], 'heuristic')
        self.assertIn('heuristic', self.models)

    def test_every_contender_saw_the_same_matches(self):
        counts = {m['n'] for m in self.report['models']}
        self.assertEqual(len(counts), 1, 'contenders were scored on different match sets')
        self.assertEqual(self.report['matches'], self.models['heuristic']['n'])
        self.assertGreater(self.report['matches'], 5000)

    def test_the_engine_beats_both_naive_baselines(self):
        for name in ('base_rate', 'uniform'):
            self.assertLess(self.models['heuristic']['logloss'], self.models[name]['logloss'])
            self.assertLess(self.models['heuristic']['brier'], self.models[name]['brier'])

    def test_a_uniform_guess_scores_exactly_what_theory_says(self):
        self.assertAlmostEqual(self.models['uniform']['logloss'], math.log(3), places=3)
        self.assertAlmostEqual(self.models['uniform']['brier'], 2 / 3, places=3)

    def test_the_published_best_is_the_lowest_log_loss_present(self):
        best = min(self.report['models'], key=lambda m: m['logloss'])['key']
        self.assertEqual(self.report['best'], best)

    def test_the_negative_result_is_published_rather_than_hidden(self):
        """A fitted alternative was tried; the interface must still list it."""
        self.assertIn('fitted', self.models)
        self.assertTrue(any('lost' in c or 'fitted' in c for c in self.report['caveats']))

    def test_scores_are_in_range(self):
        for model in self.report['models']:
            self.assertTrue(0 < model['logloss'] < 3, model['key'])
            self.assertTrue(0 < model['brier'] <= 2, model['key'])
            self.assertTrue(0 <= model['accuracy'] <= 1, model['key'])


if __name__ == '__main__':
    unittest.main()
