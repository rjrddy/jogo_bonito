import json
import tempfile
import unittest
from pathlib import Path
from generate_data import generate
from server import EventStore


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'events.db'
        self.store = EventStore(self.path)
        self.events = generate()[0]['events']

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def test_duplicate_delivery_and_recovery(self):
        self.assertEqual(self.store.ingest(self.events)['accepted'], 440)
        before = self.store.snapshot('city', 90)
        self.assertEqual(self.store.ingest(self.events)['duplicates'], 440)
        self.assertEqual(before, self.store.snapshot('city', 90))
        self.store.db.close()
        self.store = EventStore(self.path)
        self.assertEqual(before, self.store.snapshot('city', 90))

    def test_out_of_order_replay_is_deterministic(self):
        self.store.ingest(list(reversed(self.events)))
        ordered = self.store.events('city')
        self.assertEqual(ordered, self.events)
        state = self.store.snapshot('city', 45)
        self.assertEqual(state['event_count'], sum(e['minute'] <= 45 for e in self.events))
        self.assertEqual(self.store.snapshot('city', 0)['event_count'], 0)

    def test_conflict_rolls_back_entire_batch(self):
        self.store.ingest([self.events[0]])
        conflict = {**self.events[0], 'player': 'Conflicting player'}
        with self.assertRaises(ValueError):
            self.store.ingest([self.events[1], conflict])
        self.assertEqual(len(self.store.events('city')), 1)

    def test_invalid_data_rejected_before_writes(self):
        for invalid in [dict(minute=float('nan')), dict(xg=1.5), dict(team='unknown'), dict(minute=True)]:
            with self.assertRaises(ValueError):
                self.store.ingest([self.events[0], {**self.events[1], **invalid}])
            self.assertEqual(self.store.events('city'), [])

    def test_fixture_generation_reproducible(self):
        self.assertEqual(generate(), generate())
        fixtures = json.loads(Path('dist/matches.json').read_text())
        self.assertEqual(fixtures, generate())

if __name__ == '__main__':
    unittest.main()
