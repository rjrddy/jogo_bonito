import json
import math
import unittest
from pathlib import Path

from scripts.build_scouting import (
    FLAG_NAMES,
    HORIZON,
    PROSPECT_MAX_AGE,
    REGIONS,
    auc,
    birth_year,
    club_identities,
    club_profiles,
    edition_profiles,
    identity_key,
    level_of,
    load,
    prior_offsets,
    softmax_classifier_train,
)
from scripts.scouting_features import CANDIDATE_FEATURES, CROSS_OFFSET, PLAYER_FEATURES, candidate_vector, player_vector

ROOT = Path(__file__).resolve().parents[1]
SCOUTING = ROOT / 'dist/scouting'
FLAT_SCALE = {k: [0.0, 1.0] for k in ('age', 'level', 'attack', 'defense', 'debut_age', 'youth_rate')}


class FeatureTests(unittest.TestCase):
    def test_birth_year_century(self):
        for dob, expected in [('28-05-90', 1990), ('21-07-00', 2000), ('14-05-97', 1997), ('02-12-05', 2005)]:
            self.assertEqual(birth_year(dob), expected)
        self.assertIsNone(birth_year(''))
        self.assertIsNone(birth_year('1990-05-28'))

    def test_identity_folds_accents_and_case(self):
        self.assertEqual(identity_key('Rúben Dias', 1997), identity_key('RUBEN DIAS', 1997))
        self.assertEqual(identity_key('İlkay Gündoğan', 1990), identity_key('Ilkay Gundogan', 1990))
        self.assertNotEqual(identity_key('Ruben Dias', 1997), identity_key('Ruben Dias', 1998))

    def test_vectors_have_the_declared_width_and_no_stray_values(self):
        spec = dict(scale=FLAT_SCALE, nation_pool={'BRA': 2546}, corridor={'es>en': 0.5})
        prospect = dict(name='Test', age=18.0, position='F', nationality='BRA', number=9,
                        years_at_club=1, seasons_seen=1, debut_age=18.0, foreign=1, status='listed')
        club = dict(club='origin', competition='es', level=0.2, attack=1.1, defense=0.9, squad_size=25,
                    youth_rate=0.2, position_counts={'G': 3, 'D': 8, 'M': 9, 'F': 5}, nation_counts={'BRA': 4},
                    u21_count=5, foreign_share=0.4, turnover=0.3, profile_fallback=False)
        target = dict(club, club='target', competition='en')
        player = player_vector(prospect, club, spec)
        candidate = candidate_vector(prospect, club, target, spec)
        self.assertEqual(len(player), len(PLAYER_FEATURES))
        self.assertEqual(len(candidate), len(CANDIDATE_FEATURES))
        for name, value in list(zip(PLAYER_FEATURES, player)) + list(zip(CANDIDATE_FEATURES, candidate)):
            self.assertTrue(math.isfinite(value), f'{name} is not finite')
        self.assertEqual(candidate[CANDIDATE_FEATURES.index('same_club')], 0.0)
        self.assertEqual(candidate_vector(prospect, club, club, spec)[CANDIDATE_FEATURES.index('same_club')], 1.0)
        self.assertEqual(candidate[CANDIDATE_FEATURES.index('corridor')], 0.5)
        self.assertEqual(candidate_vector(prospect, club, club, spec)[CANDIDATE_FEATURES.index('corridor')], 0.0)

    def test_missing_optional_fields_do_not_break_the_vector(self):
        spec = dict(scale=FLAT_SCALE, nation_pool={}, corridor={})
        prospect = dict(name='Sparse', age=17.0, position='M', nationality=None, number=None, status='listed')
        club = dict(club='c', competition='en', level=0.0, attack=1.0, defense=1.0, squad_size=0,
                    position_counts={}, nation_counts={})
        self.assertTrue(all(math.isfinite(v) for v in player_vector(prospect, club, spec)))
        self.assertTrue(all(math.isfinite(v) for v in candidate_vector(prospect, club, club, spec)))

    def test_an_unknown_position_falls_back_rather_than_raising(self):
        spec = dict(scale=FLAT_SCALE, nation_pool={}, corridor={})
        prospect = dict(name='Odd', age=18.0, position='SW', nationality='ENG', number=5, status='listed')
        club = dict(club='c', competition='en', level=0.0, attack=1.0, defense=1.0, squad_size=20,
                    position_counts={'M': 6}, nation_counts={'ENG': 10})
        vector = player_vector(prospect, club, spec)
        self.assertEqual(vector[PLAYER_FEATURES.index('pos_m')], 1.0)

    def test_excluding_the_player_lowers_their_own_nationality_share(self):
        spec = dict(scale=FLAT_SCALE, nation_pool={}, corridor={})
        prospect = dict(name='T', age=18.0, position='F', nationality='BRA', number=9, status='listed')
        club = dict(club='a', competition='es', level=0.0, attack=1.0, defense=1.0, squad_size=20, youth_rate=0.2,
                    position_counts={'F': 4}, nation_counts={'BRA': 4}, u21_count=4, foreign_share=0.3, turnover=0.2)
        target = dict(club, club='b')
        index = CANDIDATE_FEATURES.index('nation_share')
        self.assertGreater(candidate_vector(prospect, club, target, spec)[index],
                           candidate_vector(prospect, club, target, spec, exclude_self=True)[index])
        need = CANDIDATE_FEATURES.index('position_need')
        self.assertLess(candidate_vector(prospect, club, target, spec)[need],
                        candidate_vector(prospect, club, target, spec, exclude_self=True)[need])


class CurrentCropTests(unittest.TestCase):
    """The lab is for scouting now, so the newest season has to be usable and
    has to be honestly unlabelled."""

    @classmethod
    def setUpClass(cls):
        cls.pool = json.loads((ROOT / 'dist/scouting/prospects.json').read_text())
        cls.clubs = {c['id']: c for c in json.loads((ROOT / 'dist/scouting/clubs.json').read_text())['clubs']}
        cls.index = {name: i for i, name in enumerate(cls.pool['fields'])}

    def year_of(self, row):
        return self.clubs[self.pool['editions'][row[self.index['edition']]]]['year']

    def test_current_year_is_the_newest_season_present(self):
        self.assertEqual(self.pool['current_year'], max(c['year'] for c in self.clubs.values()))

    def test_the_current_crop_is_large_enough_to_scout(self):
        current = [r for r in self.pool['rows'] if self.year_of(r) == self.pool['current_year']]
        self.assertGreater(len(current), 500, 'the newest season must carry a usable prospect pool')
        nations = {r[self.index['nationality']] for r in current if r[self.index['nationality']] is not None}
        self.assertGreater(len(nations), 50, 'the current crop should still be a global one')

    def test_current_prospects_carry_no_outcome(self):
        """Their six-season window runs past the cutoff, so a label would be a lie."""
        for row in self.pool['rows']:
            if self.year_of(row) == self.pool['current_year']:
                self.assertIsNone(row[self.index['outcome']])
                self.assertIsNone(row[self.index['peak_edition']])

    def test_every_prospect_has_a_birth_date_so_it_can_be_aged_to_today(self):
        for row in self.pool['rows']:
            born = row[self.index['birth_date']]
            self.assertRegex(born or '', r'^\d{4}-\d{2}-\d{2}$')
            # The season age must agree with the birth year it was derived from.
            self.assertEqual(self.year_of(row) - int(born[:4]), int(row[self.index['age']]))


class ModelTrainingTests(unittest.TestCase):
    def test_classifier_separates_a_linearly_separable_problem(self):
        rows = [([1.0, i / 400], 1 if i / 400 > 0.5 else 0) for i in range(400)]
        weights = softmax_classifier_train(rows, 2, 2, epochs=60)
        correct = sum(1 for features, label in rows
                      if max(range(2), key=lambda k: sum(w * f for w, f in zip(weights[k], features))) == label)
        self.assertGreater(correct / len(rows), 0.95)

    def test_prior_offsets_move_predictions_towards_the_observed_base_rate(self):
        weights = [[0.0, 0.0], [0.0, 0.0]]
        rows = [([1.0, 0.0], 1) for _ in range(90)] + [([1.0, 0.0], 0) for _ in range(10)]
        offsets = prior_offsets(weights, rows, 2, steps=600)
        shifted = [offsets[k] for k in range(2)]
        exponent = [math.exp(s - max(shifted)) for s in shifted]
        self.assertAlmostEqual(exponent[1] / sum(exponent), 0.9, places=2)
        self.assertEqual(prior_offsets(weights, [], 2), [0.0, 0.0])

    def test_auc_is_a_rank_statistic_with_tie_handling(self):
        self.assertEqual(auc([(0.9, 1), (0.1, 0)]), 1.0)
        self.assertEqual(auc([(0.1, 1), (0.9, 0)]), 0.0)
        self.assertEqual(auc([(0.5, 1), (0.5, 0)]), 0.5)
        self.assertIsNone(auc([(0.5, 1), (0.9, 1)]))


class LeakageTests(unittest.TestCase):
    """The published metrics only mean something if a candidate club cannot see
    the season the prospect would be arriving into."""

    @classmethod
    def setUpClass(cls):
        if not (ROOT / 'dist/rosters/index.json').exists():
            raise unittest.SkipTest('Historical roster import has not completed')
        cls.catalog, cls.editions, cls.squads = load()
        cls.identity, cls.by_club = club_identities(cls.editions)
        cls.profiles = edition_profiles(cls.editions, cls.squads, cls.identity, cls.by_club)
        cls.clubs = club_profiles(cls.editions, cls.profiles, cls.identity, cls.by_club)

    def test_a_club_profile_describes_the_previous_season(self):
        checked = 0
        for edition_id, profile in self.clubs.items():
            previous = self.by_club[self.identity[edition_id]].get(self.editions[edition_id]['year'] - 1)
            if previous:
                self.assertFalse(profile['profile_fallback'], edition_id)
                self.assertEqual(profile['profile_source'], previous)
                self.assertAlmostEqual(profile['level'], level_of(self.editions[previous]), places=9)
                checked += 1
            else:
                self.assertTrue(profile['profile_fallback'], edition_id)
                self.assertEqual(profile['profile_source'], edition_id)
        # The rest are 2010 or newly promoted, and carry the profile_fallback flag.
        self.assertGreater(checked, 1300, 'most editions should have a prior season to describe them')
        self.assertLess(sum(1 for p in self.clubs.values() if p['profile_fallback']) / len(self.clubs), 0.25)

    def test_a_joining_player_is_absent_from_the_profile_that_scores_them(self):
        """Whoever arrived at a club for season Y is, by construction, missing
        from the season Y-1 squad that the candidate profile is built from."""
        arrivals = checked = 0
        for edition_id, profile in self.clubs.items():
            if profile['profile_fallback'] or edition_id not in self.profiles or checked >= 300:
                continue
            source_keys = self.profiles[profile['profile_source']]['keys']
            for key in self.profiles[edition_id]['keys'] - source_keys:
                self.assertNotIn(key, source_keys)
                arrivals += 1
            checked += 1
        self.assertGreater(checked, 100)
        self.assertGreater(arrivals, 500, 'the snapshot should contain plenty of real arrivals')

    def test_profile_strengths_differ_from_the_arrival_season(self):
        moved = sum(1 for edition_id, profile in self.clubs.items()
                    if not profile['profile_fallback']
                    and abs(profile['level'] - level_of(self.editions[edition_id])) > 1e-9)
        self.assertGreater(moved, 1200, 'a profile reusing the arrival season would leak the outcome')

    def test_name_variants_resolve_to_one_club(self):
        """A rename must not read as a transfer."""
        for names in [('Athletic Bilbao', 'Athletic Club'), ('Malaga CF', 'Málaga CF'),
                      ('Deportivo La Coruna', 'Deportivo La Coruña')]:
            keys = {self.identity[edition_id] for edition_id, edition in self.editions.items()
                    if edition['kind'] == 'club' and edition['name'] in names}
            self.assertEqual(len(keys), 1, names)
        self.assertEqual(len(set(self.identity.values())), 192, 'the badge manifest resolves 192 clubs')
        for key, years in self.by_club.items():
            self.assertEqual(len(years), len(set(years.values())), key)

    def test_strengths_come_from_results_not_from_the_squad_file(self):
        sample = self.editions['en-2023-manchester-city']
        self.assertAlmostEqual(level_of(sample), math.log(sample['attack'] / sample['defense']), places=12)


class ArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (SCOUTING / 'model.json').exists():
            raise unittest.SkipTest('Run scripts/build_scouting.py to produce the scouting artifacts')
        cls.model = json.loads((SCOUTING / 'model.json').read_text())
        cls.clubs = json.loads((SCOUTING / 'clubs.json').read_text())
        cls.prospects = json.loads((SCOUTING / 'prospects.json').read_text())

    def test_artifacts_agree_with_the_catalog_and_each_other(self):
        catalog = json.loads((ROOT / 'dist/catalog.json').read_text())
        club_ids = {t['id'] for t in catalog['teams'] if t['kind'] == 'club'}
        self.assertEqual({c['id'] for c in self.clubs['clubs']}, club_ids)
        self.assertEqual(self.model['as_of'], catalog['as_of'])
        self.assertEqual(self.clubs['as_of'], catalog['as_of'])
        self.assertEqual(set(self.prospects['editions']) - club_ids, set())
        self.assertEqual(len(self.prospects['rows']), self.model['pool']['size'])
        self.assertEqual(self.clubs['nation_codes'], self.prospects['nation_codes'])
        for club in self.clubs['clubs']:
            self.assertEqual(sum(club['nations'][1::2]), club['squad_size'], club['id'])
            self.assertEqual(sum(club['positions']), club['squad_size'], club['id'])

    def test_shapes_match_the_declared_feature_spec(self):
        self.assertEqual(self.model['player_features'], list(PLAYER_FEATURES))
        self.assertEqual(self.model['candidate_features'], list(CANDIDATE_FEATURES))
        self.assertEqual(self.model['cross_offset'], CROSS_OFFSET)
        self.assertEqual(len(self.model['fit']['weights']), len(CANDIDATE_FEATURES))
        self.assertEqual(len(self.model['fit']['club_bias']), len(self.model['fit']['clubs']))
        self.assertEqual(len(self.model['fit']['embed']), len(self.model['fit']['clubs']))
        for row in self.model['fit']['tower']:
            self.assertEqual(len(row), len(PLAYER_FEATURES))
        for row in self.model['fit']['embed']:
            self.assertEqual(len(row), len(self.model['fit']['tower']))
        for row in self.model['progression']['weights']:
            self.assertEqual(len(row), len(PLAYER_FEATURES))
        self.assertEqual(len(self.model['progression']['weights']), len(self.model['progression']['outcomes']))
        self.assertEqual(len(self.model['progression']['prior_offsets']), len(self.model['progression']['outcomes']))
        for archetype in self.model['archetypes']:
            self.assertEqual(len(archetype['centre']), len(self.model['fit']['tower']))
        self.assertEqual(len({a['label'] for a in self.model['archetypes']}), len(self.model['archetypes']))

    def test_the_model_has_no_fitted_opinion_on_staying_put(self):
        """It only ever saw moves, so claiming otherwise in the interface would
        be wrong."""
        self.assertEqual(self.model['fit']['weights'][CANDIDATE_FEATURES.index('same_club')], 0.0)

    def test_pool_rows_are_within_the_declared_bounds(self):
        index = {name: i for i, name in enumerate(self.prospects['fields'])}
        outcomes = len(self.model['progression']['outcomes'])
        for row in self.prospects['rows']:
            self.assertLessEqual(row[index['age']], PROSPECT_MAX_AGE)
            self.assertGreaterEqual(row[index['age']], 13)
            self.assertIn(row[index['position']], ('G', 'D', 'M', 'F'))
            self.assertLess(row[index['edition']], len(self.prospects['editions']))
            self.assertLessEqual(row[index['debut_age']], row[index['age']])
            if row[index['nationality']] is not None:
                self.assertLess(row[index['nationality']], len(self.prospects['nation_codes']))
            if row[index['outcome']] is not None:
                self.assertIn(row[index['outcome']], range(outcomes))

    def test_recent_cohorts_are_left_unlabelled_rather_than_guessed(self):
        index = {name: i for i, name in enumerate(self.prospects['fields'])}
        years = {c['id']: c['year'] for c in self.clubs['clubs']}
        cutoff = int(self.model['as_of'][:4])
        labelled_recent = [row for row in self.prospects['rows']
                           if years[self.prospects['editions'][row[index['edition']]]] > cutoff - 4
                           and row[index['outcome']] is not None]
        self.assertEqual(labelled_recent, [], 'cohorts without an observable window must stay unlabelled')
        self.assertLess(self.model['pool']['labelled'], self.model['pool']['size'])

    def test_published_metrics_beat_the_baselines_they_are_shown_against(self):
        fit = self.model['fit']['metrics']
        for key in ('recall_1', 'recall_5', 'recall_10', 'recall_25', 'mrr'):
            self.assertGreater(fit['model'][key], fit['popularity'][key], key)
            self.assertGreater(fit['model'][key], fit['closest_level'][key], key)
        self.assertLess(fit['model']['median_rank'], fit['closest_level']['median_rank'])
        self.assertEqual(fit['model']['n'], fit['popularity']['n'])
        self.assertEqual(fit['model']['n'], fit['closest_level']['n'])
        progression = self.model['progression']['metrics']
        self.assertGreater(progression['accuracy'], progression['majority_accuracy'])
        self.assertLess(progression['brier'], progression['base_rate_brier'])
        for row in progression['calibration']:
            self.assertLess(abs(row['predicted'] - row['observed']), 0.05, row['outcome'])
        self.assertEqual(progression['horizon'], HORIZON)
        self.assertGreater(progression['validation_from'], 2015)

    def test_the_loss_curve_shows_the_ranker_actually_trained(self):
        curve = self.model['fit']['metrics']['loss_curve']
        self.assertGreater(len(curve), 10)
        self.assertLess(curve[-1], curve[0])
        self.assertLess(curve[-1], math.log(self.model['fit']['metrics']['negatives'] + 1),
                        'final loss must beat guessing uniformly among the sampled candidates')

    def test_every_served_flag_and_region_resolves(self):
        for code, path in self.model['flags'].items():
            self.assertIn(code, FLAG_NAMES)
            self.assertTrue((ROOT / 'dist' / path).exists(), path)
        for code, region in self.model['regions'].items():
            self.assertEqual(REGIONS[code], region)
        pooled = {self.prospects['nation_codes'][row[4]] for row in self.prospects['rows'] if row[4] is not None}
        self.assertGreater(len(pooled & set(self.model['regions'])), 100)
        self.assertGreater(len({self.model['regions'][c] for c in pooled if c in self.model['regions']}), 4)

    def test_the_limits_are_published_with_the_model(self):
        self.assertGreater(len(self.model['limits']), 3)
        self.assertTrue(any('academy' in limit.lower() or 'minutes' in limit.lower()
                            for limit in self.model['limits']))
        self.assertIn('seed', self.model)
        self.assertIn('method', self.model)


if __name__ == '__main__':

    unittest.main()
