"""Package imported squads into a small manifest and lazy-loaded edition files."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def package():
    candidates=[ROOT/'.local/rosters/normalized.json',ROOT/'dist/rosters.json']
    source=next(p for p in candidates if p.exists())
    data=json.loads(source.read_text())
    directory=ROOT/'dist/rosters';directory.mkdir(exist_ok=True)
    records={}
    for tid,roster in sorted(data['rosters'].items()):
        (directory/(tid+'.json')).write_text(json.dumps(roster,ensure_ascii=False,separators=(',',':')))
        records[tid]=dict(path='rosters/'+tid+'.json',players=len(roster['players']),coaches=len(roster['coaches']),status=roster['status'])
    manifest={k:v for k,v in data.items() if k not in ('rosters','mapping_gaps','errors')}
    manifest.update(version=1,editions=records,players=sum(r['players'] for r in records.values()),coaches=sum(bool(r['coaches']) for r in records.values()),import_errors=len(data['errors']))
    (directory/'index.json').write_text(json.dumps(manifest,ensure_ascii=False,separators=(',',':')))
    if source==ROOT/'dist/rosters.json':
        (ROOT/'.local/rosters/normalized.json').write_text(source.read_text());source.unlink()
    legacy=ROOT/'dist/rosters.json'
    if legacy.exists():legacy.unlink()
    print(f'Packaged {len(records)} roster files; {manifest["players"]} players; {manifest["coaches"]} coach snapshots; {len(manifest["missing"])} missing editions')

if __name__=='__main__':package()
