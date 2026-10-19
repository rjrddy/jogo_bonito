import hashlib
import json
import unittest
from pathlib import Path
from scripts.build_badges import validate_asset

ROOT=Path(__file__).resolve().parents[1]

class BadgeTests(unittest.TestCase):
    def test_every_club_edition_has_real_bundled_badge(self):
        catalog=json.loads((ROOT/'dist/catalog.json').read_text())
        manifest=json.loads((ROOT/'dist/assets/crests/clubs.json').read_text())
        clubs=[t for t in catalog['teams'] if t['kind']=='club']
        self.assertEqual(set(manifest['editions']),{t['id'] for t in clubs})
        for t in clubs:
            record=manifest['clubs'][manifest['editions'][t['id']]]
            self.assertEqual(t['crest'],record['path'])
            self.assertEqual(manifest['names'][t['name']],t['crest'])
            self.assertIn(t['name'],record['aliases'])
            self.assertTrue((ROOT/'dist'/t['crest']).is_file())
        for record in manifest['clubs'].values():
            path=ROOT/'dist'/record['path'];body=path.read_bytes()
            validate_asset(body,path.suffix)
            self.assertEqual(hashlib.sha256(body).hexdigest(),record['sha256'])
            self.assertTrue(record['source'].startswith('https://'))

    def test_archived_clubs_are_not_silently_replaced_by_successors(self):
        manifest=json.loads((ROOT/'dist/assets/crests/clubs.json').read_text())
        for key in ['fr-arlesavignon','fr-evianthonongaillard']:
            record=manifest['clubs'][key]
            self.assertIn('commons.wikimedia.org',record['source'])
        evian=manifest['clubs']['fr-evianthonongaillard']
        self.assertIn('2009',evian['source'])

if __name__=='__main__':unittest.main()

class NationalFlagTests(unittest.TestCase):
    def test_all_national_editions_have_verified_local_flags(self):
        from scripts.build_flags import flag_path
        catalog=json.loads((ROOT/'dist/catalog.json').read_text())
        manifest=json.loads((ROOT/'dist/assets/flags/index.json').read_text())
        editions=[t for t in catalog['teams'] if t['kind']=='national']
        self.assertEqual(set(manifest['teams']),{t['name'] for t in editions})
        for t in editions:
            record=manifest['teams'][t['name']]
            self.assertEqual(t['crest'],flag_path(t['name']))
            self.assertEqual(t['crest'],record['path'])
            body=(ROOT/'dist'/t['crest']).read_bytes()
            validate_asset(body,'.svg')
            self.assertEqual(hashlib.sha256(body).hexdigest(),record['sha256'])
        self.assertEqual(manifest['teams']['England']['code'],'gb-eng')
        self.assertEqual(manifest['teams']['Scotland']['code'],'gb-sct')
        self.assertEqual(manifest['teams']['Wales']['code'],'gb-wls')
        self.assertEqual(manifest['teams']['Northern Ireland']['code'],'gb-nir')
