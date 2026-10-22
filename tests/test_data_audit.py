"""Ground-truth audit of the bundled data.

Everything else in this suite checks that the code is self-consistent. This
file checks that the data is *right*: final league tables against the real
seasons, birth dates against the real players, and the documented contracts of
the derived artifacts against the artifacts themselves.

Where a value looks wrong but is real, it is pinned here with a note, so the
next person does not "fix" Essam El-Hadary playing a World Cup at 45.
"""
import json
import re
import unittest
from collections import defaultdict
from pathlib import Path

from scripts.build_scouting import SOURCE_CORRECTIONS, birth_year, accent_fold

ROOT = Path(__file__).resolve().parents[1]

# Final goals for / against, from the real completed seasons.
REAL_TABLES = [
    ('en-2023-manchester-city', 94, 33), ('en-2024-manchester-city', 96, 34),
    ('en-2010-chelsea', 103, 32), ('en-2016-leicester-city', 68, 36),
    ('es-2016-real-madrid', 110, 34), ('es-2015-barcelona', 110, 21),
    ('es-2021-atl-tico-madrid', 67, 25), ('de-2013-bayern-munich', 98, 18),
    ('de-2020-bayern-munich', 100, 32), ('it-2014-juventus', 80, 23),
    ('it-2020-juventus', 76, 43), ('fr-2016-paris-saint-germain', 102, 19),
]
REAL_BIRTH_DATES = {
    'Lamine Yamal': '2007-07-13', 'Erling Haaland': '2000-07-21',
    'Kylian Mbappé': '1998-12-20', 'Jude Bellingham': '2003-06-29',
    'Pedri': '2002-11-25', 'Pau Cubarsí': '2007-01-22',
    'Vinícius Júnior': '2000-07-12', 'Bukayo Saka': '2001-09-05',
}
# Extreme ages that are genuinely correct, not parsing accidents.
VERIFIED_EXTREMES = {
    ('Essam El-Hadary', 'wc-2018-egypt'): 45,   # oldest player in World Cup history
    ('Pietro Pellegri', 'it-2016-genoa-cfc'): 15,  # really did debut for Genoa at 15
    # Augsburg's goalkeeping coach, listed as a goalkeeper wearing 12: clubs do
    # register a coach as the emergency third keeper, and the source says so.
    ('Zdenko Miletić', 'de-2018-fc-augsburg'): 50,
}


def load(path):
    return json.loads((ROOT / path).read_text())


class CatalogGroundTruthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load('dist/catalog.json')
        cls.teams = {t['id']: t for t in cls.catalog['teams']}

    def test_final_tables_match_the_real_seasons(self):
        for edition_id, gf, ga in REAL_TABLES:
            team = self.teams.get(edition_id)
            self.assertIsNotNone(team, f'{edition_id} missing from the catalog')
            self.assertEqual((team['gf'], team['ga']), (gf, ga), f'{edition_id} goal totals')

    def test_goals_scored_and_conceded_balance_within_every_edition(self):
        """In a closed league every goal scored is a goal conceded."""
        totals = defaultdict(lambda: [0, 0, 0])
        for team in self.catalog['teams']:
            if team['kind'] != 'club':
                continue
            key = (team['competition'], team['year'])
            totals[key][0] += team['gf']
            totals[key][1] += team['ga']
            totals[key][2] += team['played']
        for key, (gf, ga, played) in totals.items():
            self.assertEqual(gf, ga, f'{key} scored/conceded do not balance')
            self.assertEqual(played % 2, 0, f'{key} has an odd number of team-matches')

    def test_wins_and_draws_never_exceed_matches_played(self):
        for team in self.catalog['teams']:
            self.assertLessEqual(team['wins'] + team['draws'], team['played'], team['id'])
            self.assertGreaterEqual(min(team['wins'], team['draws'], team['gf'], team['ga']), 0, team['id'])

    def test_coverage_totals_agree_with_the_team_list(self):
        for report in self.catalog['coverage']:
            listed = [t for t in self.catalog['teams']
                      if t['competition'] == report['competition'] and t['year'] == report['year']]
            self.assertEqual(len(listed), report['teams'], f"{report['competition']} {report['year']}")

    def test_only_the_declared_editions_are_incomplete(self):
        partial = {(c['competition'], c['year']) for c in self.catalog['coverage'] if c['complete'] is False}
        self.assertEqual(partial, {('es', 2025), ('it', 2025), ('fr', 2026)})


class SquadGroundTruthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        manifest = load('dist/rosters/index.json')
        cls.catalog = {t['id']: t for t in load('dist/catalog.json')['teams']}
        cls.squads = {tid: load('dist/' + e['path']) for tid, e in manifest['editions'].items()}

    def test_real_players_have_their_real_birth_dates(self):
        found = defaultdict(set)
        for squad in self.squads.values():
            for player in squad['players']:
                if player['name'] in REAL_BIRTH_DATES:
                    day, month, year = player['date_of_birth'].split('-')
                    found[player['name']].add(f'{birth_year(player["date_of_birth"])}-{month}-{day}')
        for name, expected in REAL_BIRTH_DATES.items():
            self.assertEqual(found.get(name), {expected}, f'{name} birth date')

    def test_no_player_is_an_implausible_age_once_corrections_apply(self):
        """A mis-parsed century shows up as a teenager or a pensioner."""
        from scripts.build_scouting import corrected
        unexplained = []
        for edition_id, squad in self.squads.items():
            year = self.catalog[edition_id]['year']
            for player in squad['players']:
                born = birth_year(corrected(edition_id, player))
                if born is None:
                    continue
                age = year - born
                if 15 <= age <= 44:
                    continue
                if VERIFIED_EXTREMES.get((player['name'], edition_id)) == age:
                    continue
                unexplained.append((player['name'], edition_id, age))
        self.assertEqual(unexplained, [], 'unverified extreme ages; confirm or correct each')

    def test_the_verified_extremes_are_still_present(self):
        """If these vanish the exemptions above are silently covering nothing."""
        seen = {}
        for edition_id, squad in self.squads.items():
            year = self.catalog[edition_id]['year']
            for player in squad['players']:
                key = (player['name'], edition_id)
                if key in VERIFIED_EXTREMES:
                    seen[key] = year - birth_year(player['date_of_birth'])
        self.assertEqual(seen, VERIFIED_EXTREMES)

    def test_every_source_correction_still_applies(self):
        for (edition_id, name), fix in SOURCE_CORRECTIONS.items():
            squad = self.squads.get(edition_id)
            self.assertIsNotNone(squad, f'{edition_id} no longer exists')
            matches = [p for p in squad['players'] if p['name'] == name]
            self.assertEqual(len(matches), 1, f'{name} in {edition_id}')
            self.assertEqual(matches[0]['date_of_birth'], fix['was'],
                             'upstream value changed; re-verify this correction rather than keeping it')

    def test_namesakes_stay_separate_people(self):
        """Two real Aaron Ramseys exist. Identity is name plus birth year, and
        collapsing them would invent a transfer between them."""
        norm = lambda n: re.sub(r'[^a-z ]', '', accent_fold(n).lower()).strip()
        years = defaultdict(set)
        for squad in self.squads.values():
            for player in squad['players']:
                born = birth_year(player.get('date_of_birth'))
                if born:
                    years[norm(player['name'])].add(born)
        self.assertEqual(years['aaron ramsey'], {1990, 2003})


class DerivedArtifactContractTests(unittest.TestCase):
    """The scouting files document what their fields mean. Check they mean it."""

    @classmethod
    def setUpClass(cls):
        cls.clubs = {c['id']: c for c in load('dist/scouting/clubs.json')['clubs']}
        cls.pool = load('dist/scouting/prospects.json')
        cls.model = load('dist/scouting/model.json')
        cls.by_club = defaultdict(dict)
        for club in cls.clubs.values():
            cls.by_club[club['club']][club['year']] = club['id']

    def test_a_profile_is_sourced_from_the_prior_season_whenever_one_exists(self):
        for club in self.clubs.values():
            prior = self.by_club[club['club']].get(club['year'] - 1)
            if prior:
                self.assertEqual(club['profile_source'], prior, club['id'])
                self.assertFalse(club['profile_fallback'], club['id'])
            else:
                self.assertEqual(club['profile_source'], club['id'], club['id'])
                self.assertTrue(club['profile_fallback'], club['id'])

    def test_turnover_describes_the_sourced_season_not_this_one(self):
        for club in self.clubs.values():
            source = self.clubs[club['profile_source']]
            expected_total = (source['year'] - 1) not in self.by_club[source['club']]
            self.assertEqual(club['turnover'] == 1.0, expected_total, club['id'])

    def test_club_identity_matches_the_curated_badge_mapping(self):
        badges = load('dist/assets/crests/clubs.json')['names']
        catalog = [t for t in load('dist/catalog.json')['teams'] if t['kind'] == 'club']
        self.assertEqual(len({c['club'] for c in self.clubs.values()}),
                         len({badges[t['name']] for t in catalog}),
                         'club identities must collapse the same name variants the badges do')
        for team in catalog:
            self.assertIn(team['name'], badges, 'every club name needs a badge mapping')

    def test_pool_ages_are_consistent_with_the_birth_dates_shipped_beside_them(self):
        index = {name: i for i, name in enumerate(self.pool['fields'])}
        for row in self.pool['rows']:
            year = self.clubs[self.pool['editions'][row[index['edition']]]]['year']
            self.assertEqual(year - int(row[index['birth_date']][:4]), int(row[index['age']]))

    def test_recorded_outcomes_agree_with_the_peak_edition_and_tier_cuts(self):
        import math
        index = {name: i for i, name in enumerate(self.pool['fields'])}
        cuts = self.model['progression']['tier_cuts']
        catalog = {t['id']: t for t in load('dist/catalog.json')['teams']}
        for row in self.pool['rows']:
            outcome, peak = row[index['outcome']], row[index['peak_edition']]
            if outcome is None:
                continue
            if outcome == 0:
                self.assertIsNone(peak, 'no further season must carry no peak club')
                continue
            edition = catalog[self.pool['editions'][peak]]
            level = math.log(edition['attack'] / edition['defense'])
            # The cuts are quantiles, so they are themselves observed levels, and
            # the published copy is rounded. A level sitting on a cut may fall
            # either side; only a clear misplacement is a failure.
            if any(abs(level - cut) < 1e-5 for cut in cuts):
                continue
            expected = 1 if level < cuts[0] else 2 if level < cuts[1] else 3
            self.assertEqual(outcome, expected, f'tier for {edition["id"]}')

    def test_nationality_counts_total_the_squad_they_describe(self):
        for club in self.clubs.values():
            counts = club['nations']
            self.assertEqual(sum(counts[i + 1] for i in range(0, len(counts), 2)), club['squad_size'], club['id'])
            self.assertEqual(sum(club['positions']), club['squad_size'], club['id'])


if __name__ == '__main__':
    unittest.main()
