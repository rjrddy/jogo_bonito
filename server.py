"""Jogo Bonito local API and dashboard. Python 3.10+, standard library only."""
import argparse
import json
import math
import sqlite3
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent


class EventStore:
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.RLock()
        with self.db:
            self.db.execute('PRAGMA journal_mode=WAL')
            self.db.execute('CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, match_id TEXT NOT NULL, minute REAL NOT NULL, payload TEXT NOT NULL)')
            self.db.execute('CREATE INDEX IF NOT EXISTS match_time ON events(match_id, minute, id)')

    def ingest(self, events):
        """Atomic batch: same-ID retries are harmless; conflicting IDs reject the batch."""
        normalized = []
        for e in events:
            if not isinstance(e, dict):
                raise ValueError('Each event must be an object')
            if not all(isinstance(e.get(k), str) and e[k] for k in ('id', 'match_id', 'player')):
                raise ValueError('id, match_id, and player must be nonempty strings')
            if e.get('team') not in ('home', 'away') or e.get('type') not in ('shot', 'pass'):
                raise ValueError('Unsupported team or event type')
            for key, low, high in [('minute', 0, 90), ('x', 0, 100), ('y', 0, 100), ('xg', 0, 1)]:
                value = e.get(key)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
                    raise ValueError(f'Invalid {key}')
            outcomes = ('goal', 'saved', 'off target', 'blocked') if e['type'] == 'shot' else ('complete', 'incomplete')
            if e.get('outcome') not in outcomes or (e['type'] == 'pass' and e['xg'] != 0):
                raise ValueError('Invalid outcome or pass xG')
            normalized.append((e, json.dumps(e, sort_keys=True, ensure_ascii=False, separators=(',', ':'))))
        accepted = 0
        with self.lock, self.db:
            for e, payload in normalized:
                existing = self.db.execute('SELECT payload FROM events WHERE id=?', (e['id'],)).fetchone()
                if existing:
                    if existing[0] != payload:
                        raise ValueError(f'Conflicting duplicate ID: {e["id"]}')
                    continue
                self.db.execute('INSERT INTO events VALUES (?, ?, ?, ?)', (e['id'], e['match_id'], e['minute'], payload))
                accepted += 1
        return {'accepted': accepted, 'duplicates': len(events) - accepted}

    def events(self, match_id, minute=90):
        with self.lock:
            rows = self.db.execute('SELECT payload FROM events WHERE match_id=? AND minute<=? ORDER BY minute,id', (match_id, minute)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def snapshot(self, match_id, minute):
        stats = {t: dict(goals=0, xg=0, shots=0, target=0, passes=0, complete=0) for t in ('home', 'away')}
        events = self.events(match_id, minute)
        for e in events:
            s = stats[e['team']]
            if e['type'] == 'shot':
                s['shots'] += 1
                s['xg'] += e['xg']
                s['goals'] += e['outcome'] == 'goal'
                s['target'] += e['outcome'] in ('goal', 'saved')
            else:
                s['passes'] += 1
                s['complete'] += e['outcome'] == 'complete'
        return dict(match_id=match_id, minute=minute, event_count=len(events), stats=stats)


def handler(store, fixtures):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(ROOT / 'dist'), **kwargs)

        def send_json(self, data, status=200):
            body = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            url = urlparse(self.path)
            parts = url.path.strip('/').split('/')
            if url.path == '/api/health':
                return self.send_json({'status': 'ok', 'storage': 'sqlite', 'data': 'synthetic'})
            if url.path == '/api/matches':
                return self.send_json([{k: v for k, v in f.items() if k != 'events'} for f in fixtures])
            if len(parts) == 4 and parts[:2] == ['api', 'matches'] and parts[3] in ('events', 'state'):
                mid = parts[2]
                if mid not in {f['id'] for f in fixtures}:
                    return self.send_json({'error': 'Unknown match'}, 404)
                try:
                    minute = float(parse_qs(url.query).get('minute', ['90'])[0])
                    if not math.isfinite(minute) or not 0 <= minute <= 90:
                        raise ValueError()
                except ValueError:
                    return self.send_json({'error': 'minute must be between 0 and 90'}, 400)
                return self.send_json(store.events(mid, minute) if parts[3] == 'events' else store.snapshot(mid, minute))
            if url.path.startswith('/api/'):
                return self.send_json({'error': 'Not found'}, 404)
            return super().do_GET()

        def do_POST(self):
            if urlparse(self.path).path != '/api/events':
                return self.send_json({'error': 'Not found'}, 404)
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 1_000_000:
                    return self.send_json({'error': 'Body must be 1–1,000,000 bytes'}, 413)
                events = json.loads(self.rfile.read(length))
                if not isinstance(events, list) or len(events) > 2000:
                    raise ValueError('Expected an array of at most 2000 events')
                if any(not isinstance(e, dict) or e.get('match_id') not in {f['id'] for f in fixtures} for e in events):
                    raise ValueError('Unknown match')
                result = store.ingest(events)
                return self.send_json(result, 200)
            except (ValueError, TypeError) as error:
                return self.send_json({'error': str(error)}, 400)
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--db', default=str(ROOT / '.local' / 'events.db'))
    args = parser.parse_args()
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    fixtures = json.loads((ROOT / 'dist' / 'matches.json').read_text())
    store = EventStore(args.db)
    for fixture in fixtures:
        store.ingest(fixture['events'])
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler(store, fixtures))
    print(f'Jogo Bonito running at http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        store.db.close()

if __name__ == '__main__':
    main()
