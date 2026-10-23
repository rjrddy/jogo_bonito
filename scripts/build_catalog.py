"""Build reproducible historical team-edition strengths from cached source archives.

Run download_sources.py first. The generated catalog includes source hashes,
coverage counts, and data cutoffs; incomplete seasons are never called complete.
"""
import csv
import hashlib
import io
import json
import re
import zipfile
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

try:
    from .build_flags import flag_path
except ImportError:
    from build_flags import flag_path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.local/sources'
LEAGUES = {
    'en': ('Premier League', 'eng'), 'es': ('La Liga', 'es'), 'de': ('Bundesliga', 'de'),
    'it': ('Serie A', 'it'), 'fr': ('Ligue 1', 'fr')
}
TOURNAMENTS = {
    'FIFA World Cup': ('wc', 'World Cup'), 'UEFA Euro': ('euros', 'Euros'),
    'Copa América': ('copa', 'Copa América')
}
ALIASES = {
    'Manchester City FC': 'Manchester City', 'Real Madrid CF': 'Real Madrid', 'FC Barcelona': 'Barcelona',
    'Liverpool FC': 'Liverpool', 'Chelsea FC': 'Chelsea', 'Arsenal FC': 'Arsenal',
    'Paris Saint-Germain FC': 'Paris Saint-Germain', 'Paris SG': 'Paris Saint-Germain',
    'Bayern München': 'Bayern Munich', 'FC Bayern München': 'Bayern Munich',
    'FC Internazionale Milano': 'Inter', 'Internazionale': 'Inter', 'Inter Milan': 'Inter',
    'AC Milan': 'Milan', 'Juventus FC': 'Juventus', 'Club Atlético de Madrid': 'Atlético Madrid',
    'Atletico Madrid': 'Atlético Madrid'
}
CRESTS = {
    'Manchester City': 'manchester-city', 'Real Madrid': 'real-madrid', 'Barcelona': 'barcelona',
    'Arsenal': 'arsenal', 'Liverpool': 'liverpool', 'Chelsea': 'chelsea'
}
BADGE_MANIFEST = ROOT / 'dist/assets/crests/clubs.json'
BADGES = json.loads(BADGE_MANIFEST.read_text())['names'] if BADGE_MANIFEST.exists() else {}


def clean(name):
    name = ALIASES.get(name.strip(), name.strip())
    return re.sub(r' FC$', '', name)


def slug(name):
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')


def edition(competition, label, year, season, rows, expected=None):
    stats = defaultdict(lambda: dict(played=0, gf=0, ga=0, wins=0, draws=0))
    for row in rows:
        for team, gf, ga in [(row['home'], row['hg'], row['ag']), (row['away'], row['ag'], row['hg'])]:
            s = stats[team]
            s['played'] += 1
            s['gf'] += gf
            s['ga'] += ga
            s['wins'] += gf > ga
            s['draws'] += gf == ga
    if not rows:
        return [], None
    mean = sum(r['hg'] + r['ag'] for r in rows) / (2 * len(rows))
    prior = 8
    result = []
    for name, s in sorted(stats.items()):
        attack = (s['gf'] + prior * mean) / (s['played'] + prior) / mean
        defense = (s['ga'] + prior * mean) / (s['played'] + prior) / mean
        result.append(dict(
            id=f'{competition}-{year}-{slug(name)}', name=name, year=year, season=season,
            competition=competition, competition_name=label,
            kind='club' if competition in LEAGUES else 'national',
            attack=round(attack, 5), defense=round(defense, 5), **s,
            crest=flag_path(name) if competition not in LEAGUES
            else BADGES.get(name) or (f'assets/crests/{CRESTS[name]}.svg' if name in CRESTS else None),
            last_match=max(r['date'] for r in rows if name in (r['home'], r['away']))))
    coverage = dict(
        competition=competition, label=label, year=year, season=season, teams=len(stats),
        matches=len(rows), expected_matches=expected,
        complete=len(rows) == expected if expected else None,
        last_match=max(r['date'] for r in rows))
    return result, coverage


def league_results(as_of='2026-10-18'):
    """Yield (code, label, year, season, rows) for every league edition.

    Shared with scripts/build_ratings.py so the fitted ratings and the catalog
    can never drift onto different parses of the same archives.
    """
    cutoff = date.fromisoformat(as_of)
    football = zipfile.ZipFile(CACHE / 'football.zip')
    legacy = zipfile.ZipFile(CACHE / 'france.zip')  # upstream redirects to cache.soccerverse
    for year in range(2010, cutoff.year + 1):
        season = f'{year-1}-{str(year)[2:]}'
        for code, (label, old_code) in LEAGUES.items():
            modern_path = f'football.json-master/{season}/{code}.1.json'
            old_path = f'cache.soccerverse-master/{season}/{old_code}.csv'
            rows = []
            if modern_path in football.namelist():
                data = json.loads(football.read(modern_path))
                matches = data.get('matches', [m for r in data.get('rounds', []) for m in r.get('matches', [])])
                for m in matches:
                    score = m.get('score', {})
                    ft = score.get('ft') if isinstance(score, dict) else score
                    if ft is None and m.get('score1') is not None:
                        ft = [m['score1'], m['score2']]
                    if not ft or len(ft) != 2 or any(not isinstance(v, int) for v in ft):
                        continue
                    day = m.get('date', '')[:10]
                    if not day or day > as_of:
                        continue
                    names = [m['team1'], m['team2']]
                    names = [n.get('name') if isinstance(n, dict) else n for n in names]
                    rows.append(dict(date=day, home=clean(names[0]), away=clean(names[1]), hg=ft[0], ag=ft[1]))
            elif old_path in legacy.namelist():
                for m in csv.DictReader(io.StringIO(legacy.read(old_path).decode('utf-8-sig'))):
                    if not re.fullmatch(r'\d+-\d+', m['FT']):
                        continue
                    day = datetime.strptime(m['Date'], '%a %b %d %Y').date().isoformat()
                    if day > as_of:
                        continue
                    hg, ag = map(int, m['FT'].split('-'))
                    rows.append(dict(date=day, home=clean(m['Team 1']), away=clean(m['Team 2']), hg=hg, ag=ag))
            yield code, label, year, season, rows


def build(as_of='2026-10-18'):
    teams, coverage = [], []
    for code, label, year, season, rows in league_results(as_of):
        count = 18 if code == 'de' or (code == 'fr' and year >= 2024) else 20
        expected = count*(count-1)
        if code == 'fr' and year == 2020:
            expected = 279  # COVID-curtailed official season
        batch, report = edition(code, label, year, season, rows, expected)
        teams.extend(batch)
        if report:
            coverage.append(report)
        else:
            coverage.append(dict(
                competition=code, label=label, year=year, season=season, teams=0,
                matches=0, expected_matches=expected, complete=False, last_match=None))
    groups = defaultdict(list)
    for m in csv.DictReader((CACHE / 'international.csv').open()):
        if (m['tournament'] not in TOURNAMENTS or not '2010-01-01' <= m['date'] <= as_of
                or not m['home_score'] or not m['away_score']):
            continue
        groups[(m['tournament'], int(m['date'][:4]))].append(dict(
            date=m['date'], home=clean(m['home_team']), away=clean(m['away_team']),
            hg=int(m['home_score']), ag=int(m['away_score'])))
    for (tournament, year), rows in sorted(groups.items()):
        code, label = TOURNAMENTS[tournament]
        counts = {
            'wc': 104 if year >= 2026 else 64,
            'euros': 31 if year < 2016 else 51,
            'copa': 32 if year in (2016, 2024) else 26 if year == 2019 else 28 if year == 2021 else 26,
        }
        season = '2020 (played 2021)' if code == 'euros' and year == 2021 else str(year)
        batch, report = edition(code, label, year, season, rows, counts[code])
        teams.extend(batch)
        coverage.append(report)
    hashes = {name: hashlib.sha256((CACHE / name).read_bytes()).hexdigest()
              for name in ('football.zip', 'france.zip', 'international.csv')}
    result = dict(
        version=1, as_of=as_of, club_year_convention='season-ending year',
        sources=[
            dict(url='https://github.com/openfootball/football.json', license='CC0-1.0'),
            dict(url='https://github.com/footballcsv/cache.soccerverse', license='CC0-1.0'),
            dict(url='https://github.com/martj42/international_results', license='CC0-1.0'),
        ],
        source_sha256=hashes,
        model=('Eight-match-prior, competition-normalized scoring and conceding rates. '
               'No calibrated cross-league or club/national adjustment.'),
        coverage=coverage, teams=teams)
    out = ROOT / 'dist/catalog.json'
    out.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')))
    print(f'{len(teams)} team editions, {len(coverage)} competition editions, '
          f'{sum(c["matches"] for c in coverage)} source results')
    gaps = [c for c in coverage if c['complete'] is False]
    print('Incomplete editions:', json.dumps(gaps, ensure_ascii=False))
    return result

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--as-of', default='2026-10-18')
    build(parser.parse_args().as_of)
