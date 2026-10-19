import json
import unittest
from pathlib import Path
from scripts.import_rosters import Page, roster, normalized

ROOT = Path(__file__).resolve().parents[1]


class RosterTests(unittest.TestCase):
    def test_explicit_name_aliases(self):
        for a, b in [('Manchester City FC', 'Manchester City'), ('1 FC Koeln', '1.FC Köln'), ('Real Betis Balompié', 'Betis'), ('Netherlands', 'Holland'), ('Bayern München', 'Bayern Munich')]:
            self.assertEqual(normalized(a), normalized(b))

    def test_parser_marks_departures_and_snapshot_coach(self):
        page = Page()
        page.feed('<h3>Manager: Coach Example [ESP]</h3><table><tr><td>1</td><td>Player One</td><td>ENG</td><td>G</td><td>1.8</td><td>80</td><td>01-01-90</td></tr><tr><td>Players no longer at this club</td></tr><tr><td>9</td><td>Player Two</td><td>ESP</td><td>F</td><td>1.8</td><td>80</td><td>01-01-91</td></tr></table>')
        data = roster(page, 'https://example.com/squad', 'digest')
        self.assertEqual(data['players'][0]['status'], 'listed')
        self.assertEqual(data['players'][1]['status'], 'departed')
        self.assertEqual(data['coaches'][0]['name'], 'Coach Example [ESP]')
        self.assertEqual(data['coaches'][0]['role'], 'Source snapshot coach')

    def test_packaged_roster_integrity(self):
        manifest_path = ROOT / 'dist/rosters/index.json'
        if not manifest_path.exists():
            self.skipTest('Historical roster import has not completed')
        manifest = json.loads(manifest_path.read_text())
        catalog = json.loads((ROOT / 'dist/catalog.json').read_text())
        team_ids = {t['id'] for t in catalog['teams']}
        self.assertEqual(set(manifest['editions']) | set(manifest['missing']), team_ids)
        player_count = 0
        coach_count = 0
        for tid, entry in manifest['editions'].items():
            data = json.loads((ROOT / 'dist' / entry['path']).read_text())
            self.assertTrue(data['source'].startswith('https://www.footballsquads.co.uk/'))
            self.assertEqual(len(data['source_sha256']), 64)
            self.assertEqual(len(data['players']), entry['players'])
            self.assertEqual(len({p['id'] for p in data['players']}), len(data['players']))
            self.assertTrue(all(p['name'] and p['position'] for p in data['players']))
            player_count += len(data['players'])
            coach_count += bool(data['coaches'])
        self.assertEqual(manifest['players'], player_count)
        self.assertEqual(manifest['coaches'], coach_count)

if __name__ == '__main__':
    unittest.main()
