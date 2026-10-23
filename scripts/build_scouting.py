"""Train the scouting models from the bundled squad snapshots and catalog.

Nothing here reaches the network. Every label comes from the packaged roster
files, so each number the browser shows is reproducible from the repository.

Two supervised models are fitted, both with pure-stdlib SGD and a temporal
train/validation split (earlier seasons train, later seasons validate):

``progression``
    Multinomial logistic regression over four outcome classes for a player
    first seen at 21 or younger: no further observed top-five season, squad
    level, regular level, elite level. The first class is censoring, not
    failure: a move to a league outside the bundled five looks identical to
    dropping out of football.

``fit``
    A sampled-softmax ranker over club editions. Score = dot(player latent,
    club-identity embedding) + weighted destination and cross features. The
    latent part learns transfer corridors; the linear part stays named and
    additive so every recommendation can be decomposed into reasons.

Club profiles for a destination season Y are built from that club's season Y-1
squad and results, so a candidate never carries information from the season the
prospect would be arriving into, including the prospect's own presence.
"""
import json
import math
import random
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

try:
    from .scouting_features import CANDIDATE_FEATURES, CROSS_OFFSET, PLAYER_FEATURES, candidate_vector, player_vector
except ImportError:
    from scouting_features import CANDIDATE_FEATURES, CROSS_OFFSET, PLAYER_FEATURES, candidate_vector, player_vector

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'dist/scouting'
LEAGUE_COUNTRY = {'en': ('ENG', 'WAL', 'SCO', 'NIR'), 'es': ('ESP',), 'de': ('GER',), 'it': ('ITA',), 'fr': ('FRA',)}
PROSPECT_MAX_AGE = 21
HORIZON = 6                 # last season of career followed when labelling an outcome
SETTLE = 1                  # ...and the first, counted from the cohort season.
# SETTLE exists because counting the very next season made an outcome tautological:
# a teenager on an elite squad list who is listed there again a year later would
# "reach elite level" without having progressed at all. Measured on the held-out
# cohorts, SETTLE=0 lifts accuracy 7.7 points over the majority class but keeps
# that artifact; SETTLE=2 removes more but leaves censoring at 59% of the label
# and only 0.9 points of lift. SETTLE=1 keeps 3.9 points of lift with the
# artifact gone.
MIN_HORIZON = 4             # cohorts with less observable future are left unlabelled
FIT_TRAIN_UNTIL = 2020      # fit model: destinations up to this season train, later validate
PROGRESS_TRAIN_UNTIL = 2015   # progression: cohorts up to this season train the weights
PROGRESS_CALIBRATE_UNTIL = 2017  # ...these recalibrate the class priors, later ones validate
NEGATIVES = 8
SEED = 20261021


# Confederation per nationality code as it appears in the squad source. Codes the
# source spells unusually are left unclassified rather than guessed at.
REGIONS = {}
for _confederation, _codes in {
    'UEFA': 'ALB AND ARM AUT AZE BEL BIH BLR BUL CRO CYP CZE DEN ENG ESP EST FIN FRA FRO GEO GER GIB GRE HUN IRL ISL '
            'ISR ITA KAZ KVX LIE LTU LUX LVA MDA MKD MLT MNE NED NIR NOR POL POR ROU RUS SCO SMR SRB SUI SVK SVN SWE '
            'TUR UKR WAL',
    'CONMEBOL': 'ARG BOL BRA CHI COL ECU PAR PER URU VEN',
    'CONCACAF': 'ATG BER BLZ BRB CAN CRC CUB CUW DOM GRN GUY HAI HON JAM LCA MEX MSR PAN PUR SKN SUR TRI USA',
    'CAF': 'ALG ANG BDI BEN BFA CGO CHA CMR COD COM CPV CTA CIV EGY EQG ERI GAB GAM GHA GNB GUI KEN LBR LBY MAD MLI '
           'MOZ MRI MTN MAR NAM NGA NIG RSA RWA SEN SLE STP TAN TOG TUN UGA ZAM ZIM',
    'AFC': 'AFG AUS BAN BRU CHN HKG IDN IRN IRQ JOR JPN KOR KSA LIB OMA PHI PLE PRK QAT SIN SRI THA UAE UZB',
    'OFC': 'FIJ NCL NZL',
}.items():
    for _code in _codes.split():
        REGIONS[_code] = _confederation

# Nationality code to the country name build_flags.py already bundles an SVG for.
FLAG_NAMES = dict(zip(
    ['ALB', 'ALG', 'ARG', 'AUS', 'AUT', 'BEL', 'BOL', 'BIH', 'BRA', 'CMR', 'CAN', 'CPV', 'CHI', 'COL', 'CRC',
     'CRO', 'CUW', 'CZE', 'COD', 'DEN', 'ECU', 'EGY', 'ENG', 'FIN', 'FRA', 'GEO', 'GER', 'GHA', 'GRE', 'HAI',
     'HON', 'HUN', 'ISL', 'IRN', 'IRQ', 'ITA', 'CIV', 'JAM', 'JPN', 'JOR', 'MEX', 'MAR', 'NED', 'NZL', 'NGA',
     'PRK', 'MKD', 'NIR', 'NOR', 'PAN', 'PAR', 'PER', 'POL', 'POR', 'QAT', 'IRL', 'ROU', 'RUS', 'KSA', 'SCO',
     'SEN', 'SRB', 'SVK', 'SVN', 'RSA', 'KOR', 'ESP', 'SWE', 'SUI', 'TUN', 'TUR', 'UKR', 'USA', 'URU', 'UZB',
     'VEN', 'WAL'],
    ['Albania', 'Algeria', 'Argentina', 'Australia', 'Austria', 'Belgium', 'Bolivia', 'Bosnia and Herzegovina',
     'Brazil', 'Cameroon', 'Canada', 'Cape Verde', 'Chile', 'Colombia', 'Costa Rica', 'Croatia', 'Curaçao',
     'Czech Republic', 'DR Congo', 'Denmark', 'Ecuador', 'Egypt', 'England', 'Finland', 'France', 'Georgia', 'Germany',
     'Ghana', 'Greece', 'Haiti', 'Honduras', 'Hungary', 'Iceland', 'Iran', 'Iraq', 'Italy', 'Ivory Coast', 'Jamaica',
     'Japan', 'Jordan', 'Mexico', 'Morocco', 'Netherlands', 'New Zealand', 'Nigeria', 'North Korea',
     'North Macedonia', 'Northern Ireland', 'Norway', 'Panama', 'Paraguay', 'Peru', 'Poland', 'Portugal', 'Qatar',
     'Republic of Ireland', 'Romania', 'Russia', 'Saudi Arabia', 'Scotland', 'Senegal', 'Serbia', 'Slovakia',
     'Slovenia', 'South Africa', 'South Korea', 'Spain', 'Sweden', 'Switzerland', 'Tunisia', 'Turkey', 'Ukraine',
     'United States', 'Uruguay', 'Uzbekistan', 'Venezuela', 'Wales']))


def flag_assets(codes):
    """Only codes whose SVG is actually bundled get a flag; the rest show a chip."""
    try:
        from .build_flags import flag_path
    except ImportError:
        from build_flags import flag_path
    assets = {}
    for code in codes:
        name = FLAG_NAMES.get(code)
        if name and (ROOT / 'dist' / flag_path(name)).exists():
            assets[code] = flag_path(name)
    return assets


def accent_fold(name):
    folded = unicodedata.normalize('NFKD', name)
    return ''.join(c for c in folded if not unicodedata.combining(c))


def identity_key(name, birth_year):
    return re.sub(r'[^a-z ]', '', accent_fold(name).lower()).strip() + '|' + str(birth_year)


def birth_year(dob):
    """FootballSquads dates are DD-MM-YY. Nobody in a 2010-2026 snapshot was
    born after 2011 or before 1960, which makes the century unambiguous."""
    match = re.fullmatch(r'(\d{2})-(\d{2})-(\d{2})', dob or '')
    if not match:
        return None
    year = int(match.group(3))
    return 1900 + year if year >= 40 else 2000 + year


# Records where the upstream squad page is demonstrably wrong and the correct
# value is externally verifiable. Kept deliberately tiny and explicit: the
# source value is preserved in the output so the edit is auditable, and
# tests/test_data_audit.py fails if an entry ever stops applying, so a silent
# upstream fix cannot leave a stale override behind.
SOURCE_CORRECTIONS = {
    ('fr-2025-as-saint-tienne', 'Benjamin Bouchouari'): dict(
        date_of_birth='13-11-01', was='13-11-11',
        why='Source reads 2011, which would make a squad-number-6 Ligue 1 midfielder 14. Born 13 Nov 2001.'),
}
corrections_applied = Counter()


def corrected(edition_id, player):
    """Apply a verified correction, recording that it fired."""
    fix = SOURCE_CORRECTIONS.get((edition_id, player.get('name')))
    if not fix or player.get('date_of_birth') != fix['was']:
        return player.get('date_of_birth')
    corrections_applied[(edition_id, player['name'])] += 1
    return fix['date_of_birth']


def birth_date(dob):
    """DD-MM-YY to ISO, so a prospect's age can be taken as of today rather than
    as of the season they were listed in."""
    match = re.fullmatch(r'(\d{2})-(\d{2})-(\d{2})', dob or '')
    if not match:
        return None
    day, month = int(match.group(1)), int(match.group(2))
    if not (1 <= day <= 31 and 1 <= month <= 12):
        return None
    return f'{birth_year(dob):04d}-{month:02d}-{day:02d}'


def slug(name):
    return re.sub(r'[^a-z0-9]+', '-', accent_fold(name).lower()).strip('-')


def load():
    catalog = json.loads((ROOT / 'dist/catalog.json').read_text())
    manifest = json.loads((ROOT / 'dist/rosters/index.json').read_text())
    editions = {t['id']: t for t in catalog['teams']}
    squads = {}
    for edition_id, entry in manifest['editions'].items():
        squads[edition_id] = json.loads((ROOT / 'dist' / entry['path']).read_text())
    return catalog, editions, squads


def club_identities(editions):
    """Resolve a club edition to the club itself.

    The catalog spells 249 club names across these seasons, but the bundled
    badge manifest already maps them onto 192 real clubs: 'Athletic Bilbao' and
    'Athletic Club' are one team, and treating them as two would turn a rename
    into a transfer and split that club's embedding in half. Reuse the mapping
    the repository already curates rather than inventing a second one.
    """
    badges = json.loads((ROOT / 'dist/assets/crests/clubs.json').read_text())['names']
    identity, by_club = {}, defaultdict(dict)
    for edition_id, edition in editions.items():
        if edition['kind'] != 'club':
            continue
        badge = badges.get(edition['name'])
        key = badge.rsplit('/', 1)[-1].removesuffix('.svg') if badge else slug(edition['name'])
        identity[edition_id] = key
        by_club[key][edition['year']] = edition_id
    return identity, by_club


def level_of(edition):
    """A single strength axis. Cross-era and cross-league scales are not
    calibrated anywhere in this project, and that applies here too."""
    return math.log(edition['attack'] / edition['defense'])


def build_records(editions, squads, identity):
    """One record per player-edition, with the career each player is part of."""
    records = []
    careers = defaultdict(list)
    for edition_id, squad in squads.items():
        edition = editions[edition_id]
        for player in squad['players']:
            dob = corrected(edition_id, player)
            born = birth_year(dob)
            if born is None:
                continue
            key = identity_key(player['name'], born)
            number = None
            if str(player.get('number') or '').strip().isdigit():
                number = int(player['number'])
            record = dict(key=key, name=player['name'], edition=edition_id, year=edition['year'],
                          kind=edition['kind'], club=identity.get(edition_id),
                          competition=edition['competition'], position=player.get('position') or 'M',
                          nationality=(player.get('nationality') or '').upper() or None,
                          number=number, status=player.get('status') or 'listed', born=born,
                          birth_date=birth_date(dob),
                          age=edition['year'] - born)
            records.append(record)
            careers[key].append(record)
    for timeline in careers.values():
        timeline.sort(key=lambda r: (r['year'], r['edition']))
    return records, careers


def edition_profiles(editions, squads, identity, by_club):
    """Squad composition per club edition, used to describe a destination."""
    profiles = {}
    for edition_id, squad in squads.items():
        edition = editions[edition_id]
        if edition['kind'] != 'club':
            continue
        listed = [p for p in squad['players'] if (p.get('status') or 'listed') != 'departed']
        ages = []
        nations, positions = Counter(), Counter()
        for player in listed:
            born = birth_year(corrected(edition_id, player))
            if born is not None:
                ages.append(edition['year'] - born)
            nations[(player.get('nationality') or '').upper()] += 1
            positions[(player.get('position') or 'M')[:1].upper()] += 1
        home = LEAGUE_COUNTRY[edition['competition']]
        profiles[edition_id] = dict(
            squad_size=len(listed), nation_counts=dict(nations), position_counts=dict(positions),
            u21_count=sum(1 for a in ages if a <= PROSPECT_MAX_AGE),
            youth_rate=(sum(1 for a in ages if a <= PROSPECT_MAX_AGE) / len(ages)) if ages else 0.0,
            mean_age=(sum(ages) / len(ages)) if ages else 0.0,
            foreign_share=(sum(n for code, n in nations.items() if code not in home) / len(listed)) if listed else 0.0,
            ids={p['id'] for p in listed},
            keys={identity_key(p['name'], birth_year(corrected(edition_id, p)))
                  for p in listed if birth_year(corrected(edition_id, p))})
    for edition_id, profile in profiles.items():
        previous = by_club[identity[edition_id]].get(editions[edition_id]['year'] - 1)
        before = profiles.get(previous)
        profile['turnover'] = (len(profile['keys'] - before['keys']) / max(1, len(profile['keys']))) if before else 1.0
    return profiles


def club_profiles(editions, profiles, identity, by_club):
    """Destination profile for joining club C in season Y: C's season Y-1 squad
    and results. No feature can see the season the prospect would play in."""
    result = {}
    for club, years in by_club.items():
        for year, edition_id in years.items():
            source_id = years.get(year - 1)
            fallback = source_id is None
            source = editions[years[year]] if fallback else editions[source_id]
            profile = profiles.get(source['id']) or profiles.get(edition_id) or {}
            edition = editions[edition_id]
            result[edition_id] = dict(
                id=edition_id, club=club, name=edition['name'], year=year,
                competition=edition['competition'], competition_name=edition['competition_name'],
                season=edition['season'], crest=edition.get('crest'),
                level=level_of(source), attack=source['attack'], defense=source['defense'],
                squad_size=profile.get('squad_size', 0), nation_counts=profile.get('nation_counts', {}),
                position_counts=profile.get('position_counts', {}), u21_count=profile.get('u21_count', 0),
                youth_rate=profile.get('youth_rate', 0.0), mean_age=profile.get('mean_age', 0.0),
                foreign_share=profile.get('foreign_share', 0.0), turnover=profile.get('turnover', 1.0),
                profile_fallback=fallback, profile_source=source['id'])
    return result


def prospect_of(record, careers):
    """The prospect record the browser also builds, from knowable facts only."""
    timeline = careers[record['key']]
    history = [r for r in timeline if (r['year'], r['edition']) <= (record['year'], record['edition'])]
    club_years = {r['year'] for r in history if r['club'] == record['club']}
    home = LEAGUE_COUNTRY.get(record['competition'], ())
    return dict(name=record['name'], edition=record['edition'], age=float(record['age']),
                position=(record['position'] or 'M')[:1].upper(), nationality=record['nationality'],
                number=record['number'], status=record['status'],
                years_at_club=len([y for y in club_years if y <= record['year']]),
                seasons_seen=len({r['year'] for r in history}),
                debut_age=float(min(r['age'] for r in history)),
                foreign=1 if record['nationality'] not in home else 0)


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def softmax_rank_train(examples, player_dim, candidate_dim, clubs_count, latent=12, epochs=30,
                       rate=0.25, decay=2e-6, seed=SEED):
    """Sampled softmax over one true destination and sampled alternatives.

    Adagrad rather than plain SGD: the named cross features are deliberately
    left on their natural scales (a level gap is a level gap), and per-parameter
    rates keep that from destabilising training.
    """
    rng = random.Random(seed)
    tower = [[rng.uniform(-.05, .05) for _ in range(player_dim)] for _ in range(latent)]
    embed = [[rng.uniform(-.05, .05) for _ in range(latent)] for _ in range(clubs_count)]
    club_bias = [0.0] * clubs_count
    weights = [0.0] * candidate_dim
    acc_tower = [[1e-8] * player_dim for _ in range(latent)]
    acc_embed = [[1e-8] * latent for _ in range(clubs_count)]
    acc_bias = [1e-8] * clubs_count
    acc_weights = [1e-8] * candidate_dim
    order = list(range(len(examples)))
    history = []
    for epoch in range(epochs):
        rng.shuffle(order)
        loss = 0.0
        for index in order:
            player, candidates = examples[index]
            latent_player = [dot(row, player) for row in tower]
            scores = [dot(latent_player, embed[club]) + club_bias[club] + dot(weights, features)
                      for club, features in candidates]
            top = max(scores)
            exponent = [math.exp(s - top) for s in scores]
            total = sum(exponent)
            loss -= math.log(max(exponent[0] / total, 1e-12))
            grad_latent = [0.0] * latent
            for position, (club, features) in enumerate(candidates):
                error = exponent[position] / total - (1.0 if position == 0 else 0.0)
                if abs(error) < 1e-7:
                    continue
                vector, accumulator = embed[club], acc_embed[club]
                for d in range(latent):
                    grad_latent[d] += error * vector[d]
                    gradient = error * latent_player[d] + decay * vector[d]
                    accumulator[d] += gradient * gradient
                    vector[d] -= rate * gradient / math.sqrt(accumulator[d])
                acc_bias[club] += error * error
                club_bias[club] -= rate * error / math.sqrt(acc_bias[club])
                for d, value in enumerate(features):
                    if value:
                        gradient = error * value
                        acc_weights[d] += gradient * gradient
                        weights[d] -= rate * gradient / math.sqrt(acc_weights[d])
            for d in range(latent):
                if not grad_latent[d]:
                    continue
                row, accumulator = tower[d], acc_tower[d]
                for j, value in enumerate(player):
                    if value:
                        gradient = grad_latent[d] * value + decay * row[j]
                        accumulator[j] += gradient * gradient
                        row[j] -= rate * gradient / math.sqrt(accumulator[j])
        history.append(round(loss / len(examples), 4))
        if epoch % 5 == 0 or epoch == epochs - 1:
            print(f'  fit epoch {epoch:>3} mean loss {history[-1]:.4f}')
    return dict(tower=tower, embed=embed, club_bias=club_bias, weights=weights, loss_curve=history)


def softmax_classifier_train(rows, dim, classes, epochs=140, rate=0.12, decay=1e-5, seed=SEED):
    rng = random.Random(seed)
    weights = [[0.0] * dim for _ in range(classes)]
    order = list(range(len(rows)))
    for epoch in range(epochs):
        rng.shuffle(order)
        step = rate / (1 + epoch * 0.05)
        loss = 0.0
        for index in order:
            features, label = rows[index]
            scores = [dot(row, features) for row in weights]
            top = max(scores)
            exponent = [math.exp(s - top) for s in scores]
            total = sum(exponent)
            loss -= math.log(max(exponent[label] / total, 1e-12))
            for k in range(classes):
                error = exponent[k] / total - (1.0 if k == label else 0.0)
                if abs(error) < 1e-7:
                    continue
                row = weights[k]
                for j, value in enumerate(features):
                    if value:
                        row[j] -= step * (error * value + decay * row[j])
        if epoch % 40 == 0 or epoch == epochs - 1:
            print(f'  progression epoch {epoch:>3} mean loss {loss / len(rows):.4f}')
    return weights


def class_probabilities(weights, features, offsets=None):
    scores = [dot(row, features) for row in weights]
    if offsets:
        scores = [s + o for s, o in zip(scores, offsets)]
    top = max(scores)
    exponent = [math.exp(s - top) for s in scores]
    total = sum(exponent)
    return [e / total for e in exponent]


def prior_offsets(weights, rows, classes, steps=400, rate=0.3):
    """Per-class log-prior shifts fitted on a held-out slice of the training era.

    Outcome base rates drift across cohorts, so the raw softmax is systematically
    off even when its ranking is good. These offsets are fitted on cohorts the
    weights never saw and the validation set never touches.
    """
    offsets = [0.0] * classes
    if not rows:
        return offsets
    logits = [[dot(row, features) for row in weights] for features, _ in rows]
    labels = [label for _, label in rows]
    accumulator = [1e-8] * classes
    for _ in range(steps):
        gradient = [0.0] * classes
        for scores, label in zip(logits, labels):
            shifted = [s + o for s, o in zip(scores, offsets)]
            top = max(shifted)
            exponent = [math.exp(s - top) for s in shifted]
            total = sum(exponent)
            for k in range(classes):
                gradient[k] += exponent[k] / total - (1.0 if k == label else 0.0)
        for k in range(classes):
            step = gradient[k] / len(rows)
            accumulator[k] += step * step
            offsets[k] -= rate * step / math.sqrt(accumulator[k])
    return offsets


def auc(pairs):
    """Rank-based AUC over (score, label) pairs with tie handling."""
    positives = sum(1 for _, label in pairs if label)
    negatives = len(pairs) - positives
    if not positives or not negatives:
        return None
    ranked = sorted(pairs, key=lambda p: p[0])
    index, rank_sum = 0, 0.0
    while index < len(ranked):
        stop = index
        while stop + 1 < len(ranked) and ranked[stop + 1][0] == ranked[index][0]:
            stop += 1
        average = (index + stop) / 2 + 1
        for position in range(index, stop + 1):
            if ranked[position][1]:
                rank_sum += average
        index = stop + 1
    return (rank_sum - positives * (positives + 1) / 2) / (positives * negatives)


def standardise(values):
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return [round(mean, 6), round(math.sqrt(variance) or 1.0, 6)]


def kmeans(vectors, k, seed=SEED, rounds=25):
    rng = random.Random(seed)
    centres = [list(vectors[rng.randrange(len(vectors))]) for _ in range(k)]
    assignment = [0] * len(vectors)
    for _ in range(rounds):
        moved = False
        for index, vector in enumerate(vectors):
            best, best_distance = 0, None
            for position, centre in enumerate(centres):
                distance = sum((a - b) ** 2 for a, b in zip(vector, centre))
                if best_distance is None or distance < best_distance:
                    best, best_distance = position, distance
            if assignment[index] != best:
                assignment[index] = best
                moved = True
        for position in range(k):
            members = [v for i, v in enumerate(vectors) if assignment[i] == position]
            if members:
                centres[position] = [sum(column) / len(members) for column in zip(*members)]
        if not moved:
            break
    return centres, assignment


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    catalog, editions, squads = load()
    identity, by_club = club_identities(editions)
    records, careers = build_records(editions, squads, identity)
    profiles = edition_profiles(editions, squads, identity, by_club)
    clubs = club_profiles(editions, profiles, identity, by_club)
    club_names = sorted({c['club'] for c in clubs.values()})
    club_index = {name: i for i, name in enumerate(club_names)}
    latest_year = max(e['year'] for e in editions.values())
    club_records = [r for r in records if r['kind'] == 'club']
    print(f'{len(records)} player-editions, {len(careers)} identities, '
          f'{len(clubs)} club editions, {len(club_names)} club identities')

    nation_pool = Counter(r['nationality'] for r in club_records if r['nationality'])
    spec = dict(scale={
        'age': standardise([float(r['age']) for r in club_records]),
        'level': standardise([c['level'] for c in clubs.values()]),
        'attack': standardise([c['attack'] for c in clubs.values()]),
        'defense': standardise([c['defense'] for c in clubs.values()]),
        'debut_age': standardise([float(min(r['age'] for r in timeline))
                                  for timeline in careers.values()
                                  if any(r['kind'] == 'club' for r in timeline)]),
        'youth_rate': standardise([c['youth_rate'] for c in clubs.values()]),
    }, nation_pool=dict(nation_pool), corridor={})

    # Observed club-to-club moves: consecutive club seasons at a different club.
    moves = []
    for timeline in careers.values():
        seasons = defaultdict(list)
        for record in timeline:
            if record['kind'] == 'club':
                seasons[record['year']].append(record)
        years = sorted(seasons)
        for before, after in zip(years, years[1:]):
            if after - before > 2:
                continue
            origin = seasons[before][0]
            destinations = [r for r in seasons[after] if r['club'] != origin['club']]
            if destinations and not any(r['club'] == origin['club'] for r in seasons[after]):
                moves.append((origin, destinations[0]))
    by_year = defaultdict(list)
    for edition_id, club in clubs.items():
        by_year[club['year']].append(edition_id)
    print(f'{len(moves)} observed club-to-club moves')

    corridor_counts = Counter()
    for origin, destination in moves:
        if destination['year'] <= FIT_TRAIN_UNTIL:
            corridor_counts[origin['competition'] + '>' + destination['competition']] += 1
    busiest = max(corridor_counts.values()) if corridor_counts else 1
    spec['corridor'] = {key: round(math.log1p(value) / math.log1p(busiest), 6)
                        for key, value in corridor_counts.items()}

    # ---- Progression: where does a player first seen at 21 or younger end up?
    cohort = []
    for timeline in careers.values():
        club_seasons = [r for r in timeline if r['kind'] == 'club' and r['edition'] in clubs]
        if not club_seasons:
            continue
        first = club_seasons[0]
        if first['age'] > PROSPECT_MAX_AGE:
            continue
        # Seasons SETTLE..HORIZON ahead, not 1..HORIZON. Being listed again next
        # season at the club they are already at says nothing about progression,
        # and counting it made every teenager on an elite squad list an elite
        # outcome by construction.
        window = [r for r in club_seasons
                  if first['year'] + SETTLE < r['year'] <= first['year'] + HORIZON]
        peak = max((level_of(editions[r['edition']]) for r in window), default=None)
        best = max(window, key=lambda r: level_of(editions[r['edition']])) if window else None
        cohort.append(dict(record=first, peak=peak, peak_edition=best['edition'] if best else None,
                           labelled=first['year'] + MIN_HORIZON <= latest_year))
    labelled = [c for c in cohort if c['labelled']]
    observed_peaks = sorted(c['peak'] for c in labelled
                            if c['peak'] is not None and c['record']['year'] <= PROGRESS_TRAIN_UNTIL)
    cuts = [observed_peaks[len(observed_peaks) // 3], observed_peaks[2 * len(observed_peaks) // 3]]
    # Named for what the data can actually witness. A squad list records who a
    # club registered, not who played, so the only honest reading of this target
    # is which calibre of squad list a player appears on later. Calling the top
    # class "elite player" would be a claim this data cannot support: a teenager
    # who stays on an elite club's list for years without ever playing lands in
    # it just the same.
    OUTCOMES = ('No further top-five squad', 'Squad-level club', 'Regular-level club', 'Elite club')

    def outcome_class(peak):
        if peak is None:
            return 0
        return 1 if peak < cuts[0] else 2 if peak < cuts[1] else 3

    progression_rows, calibration_rows, progression_validation = [], [], []
    for entry in labelled:
        record = entry['record']
        prospect = prospect_of(record, careers)
        features = player_vector(prospect, clubs[record['edition']], spec)
        label = outcome_class(entry['peak'])
        entry['outcome'] = label
        bucket = (progression_rows if record['year'] <= PROGRESS_TRAIN_UNTIL else
                  calibration_rows if record['year'] <= PROGRESS_CALIBRATE_UNTIL else progression_validation)
        bucket.append((features, label))
    print(f'progression: {len(progression_rows)} training, {len(calibration_rows)} calibration, '
          f'{len(progression_validation)} validation cohorts, {len(cohort) - len(labelled)} too recent to label')
    progression = softmax_classifier_train(progression_rows, len(PLAYER_FEATURES), len(OUTCOMES))
    offsets = prior_offsets(progression, calibration_rows, len(OUTCOMES))
    print(f'  class prior offsets from {PROGRESS_TRAIN_UNTIL + 1}-{PROGRESS_CALIBRATE_UNTIL} cohorts: '
          + ', '.join(f'{OUTCOMES[k]} {offsets[k]:+.3f}' for k in range(len(OUTCOMES))))

    predictions = [(class_probabilities(progression, f, offsets), label) for f, label in progression_validation]
    actual = Counter(label for _, label in progression_validation)
    majority = Counter(label for _, label in progression_rows).most_common(1)[0][0]
    accuracy = sum(1 for p, label in predictions if p.index(max(p)) == label) / len(predictions)
    brier = sum(sum((p[k] - (1.0 if k == label else 0.0)) ** 2 for k in range(len(OUTCOMES)))
                for p, label in predictions) / len(predictions)
    base_rate = [Counter(label for _, label in progression_rows)[k] / len(progression_rows)
                 for k in range(len(OUTCOMES))]
    base_brier = sum(sum((base_rate[k] - (1.0 if k == label else 0.0)) ** 2 for k in range(len(OUTCOMES)))
                     for _, label in predictions) / len(predictions)
    progression_metrics = dict(
        classes=list(OUTCOMES), train=len(progression_rows), calibration_cohorts=len(calibration_rows),
        validation=len(progression_validation), validation_from=PROGRESS_CALIBRATE_UNTIL + 1,
        horizon=HORIZON, settle=SETTLE, tier_cuts=[round(c, 4) for c in cuts],
        prior_offsets=[round(o, 4) for o in offsets],
        uncalibrated_brier=round(
            sum(sum((p[k] - (1.0 if k == label else 0.0)) ** 2 for k in range(len(OUTCOMES)))
                for p, label in [(class_probabilities(progression, f), l)
                                 for f, l in progression_validation]) / len(progression_validation), 4),
        accuracy=round(accuracy, 4),
        majority_accuracy=round(sum(1 for _, label in predictions if label == majority) / len(predictions), 4),
        brier=round(brier, 4), base_rate_brier=round(base_brier, 4),
        auc={OUTCOMES[k]: round(auc([(p[k], 1 if label == k else 0) for p, label in predictions]) or 0, 4)
             for k in range(len(OUTCOMES))},
        calibration=[dict(outcome=OUTCOMES[k], predicted=round(sum(p[k] for p, _ in predictions) / len(predictions), 4),
                          observed=round(actual[k] / len(predictions), 4)) for k in range(len(OUTCOMES))])
    print('progression validation:', json.dumps(progression_metrics, indent=1))

    rng = random.Random(SEED)
    train_examples, validation = [], []
    elite_index = len(OUTCOMES) - 1
    for origin, destination in moves:
        if origin['edition'] not in clubs or destination['edition'] not in clubs:
            continue
        prospect = prospect_of(origin, careers)
        origin_profile = clubs[origin['edition']]
        player = player_vector(prospect, origin_profile, spec)
        # Two-stage: the progression model scores the player, then the ranker uses
        # that score to judge how far up a move is plausible.
        prospect['elite'] = class_probabilities(progression, player, offsets)[elite_index]
        pool = [e for e in by_year[destination['year']] if clubs[e]['club'] != origin['club']]
        if destination['edition'] not in pool or len(pool) <= NEGATIVES:
            continue
        true_vector = candidate_vector(prospect, origin_profile, clubs[destination['edition']], spec, exclude_self=True)
        row = (prospect, origin_profile, player, destination['edition'], pool, destination['year'])
        if destination['year'] <= FIT_TRAIN_UNTIL:
            others = [e for e in pool if e != destination['edition']]
            sample = rng.sample(others, NEGATIVES)
            candidates = [(club_index[clubs[destination['edition']]['club']], true_vector)]
            candidates += [(club_index[clubs[e]['club']], candidate_vector(prospect, origin_profile, clubs[e], spec))
                           for e in sample]
            train_examples.append((player, candidates))
        else:
            validation.append(row)
    print(f'fit model: {len(train_examples)} training moves, {len(validation)} validation moves')

    fit = softmax_rank_train(train_examples, len(PLAYER_FEATURES), len(CANDIDATE_FEATURES), len(club_names))
    tower, embed, club_bias, weights = fit['tower'], fit['embed'], fit['club_bias'], fit['weights']

    def fit_score(prospect, origin_profile, player, target_id):
        target = clubs[target_id]
        features = candidate_vector(prospect, origin_profile, target, spec)
        latent = [dot(row, player) for row in tower]
        index = club_index[target['club']]
        return dot(latent, embed[index]) + club_bias[index] + dot(weights, features)

    popularity = Counter()
    for _, destination in moves:
        if destination['year'] <= FIT_TRAIN_UNTIL:
            popularity[clubs[destination['edition']]['club']] += 1
    ranks = {'model': [], 'popularity': [], 'level': []}
    for prospect, origin_profile, player, truth, pool, _ in validation:
        scored = sorted(pool, key=lambda e: -fit_score(prospect, origin_profile, player, e))
        ranks['model'].append(scored.index(truth) + 1)
        ranked = sorted(pool, key=lambda e: (-popularity[clubs[e]['club']], clubs[e]['club']))
        ranks['popularity'].append(ranked.index(truth) + 1)
        ranked = sorted(pool, key=lambda e: abs(clubs[e]['level'] - origin_profile['level']))
        ranks['level'].append(ranked.index(truth) + 1)
    candidate_mean = sum(len(p) for *_, p, _ in validation) / max(1, len(validation))

    def rank_report(values):
        return dict(n=len(values),
                    recall_1=round(sum(1 for r in values if r <= 1) / len(values), 4),
                    recall_5=round(sum(1 for r in values if r <= 5) / len(values), 4),
                    recall_10=round(sum(1 for r in values if r <= 10) / len(values), 4),
                    recall_25=round(sum(1 for r in values if r <= 25) / len(values), 4),
                    mrr=round(sum(1 / r for r in values) / len(values), 4),
                    median_rank=sorted(values)[len(values) // 2])
    fit_metrics = dict(candidates_mean=round(candidate_mean, 1), latent=len(tower),
                       train_moves=len(train_examples), negatives=NEGATIVES,
                       validation_from=FIT_TRAIN_UNTIL + 1, loss_curve=fit['loss_curve'],
                       model=rank_report(ranks['model']), popularity=rank_report(ranks['popularity']),
                       closest_level=rank_report(ranks['level']))
    print('fit validation:', json.dumps(fit_metrics['model']))
    print('  popularity baseline:', json.dumps(fit_metrics['popularity']))
    print('  closest-level baseline:', json.dumps(fit_metrics['closest_level']))

    # ---- Prospect pool: every under-21 club season in the snapshot.
    outcomes_by_key = {c['record']['key'] + '|' + c['record']['edition']: c for c in cohort}
    edition_list = sorted(clubs)
    edition_lookup = {edition_id: i for i, edition_id in enumerate(edition_list)}
    identities, identity_lookup = [], {}
    pool = []
    for record in club_records:
        if record['age'] > PROSPECT_MAX_AGE or record['edition'] not in clubs:
            continue
        prospect = prospect_of(record, careers)
        if record['key'] not in identity_lookup:
            identity_lookup[record['key']] = len(identities)
            identities.append(record['key'])
        entry = outcomes_by_key.get(record['key'] + '|' + record['edition'])
        pool.append([
            record['name'], edition_lookup[record['edition']], round(prospect['age'], 1), prospect['position'],
            prospect['nationality'] or '', record['number'], prospect['years_at_club'], prospect['seasons_seen'],
            round(prospect['debut_age'], 1), prospect['foreign'], 1 if record['status'] == 'departed' else 0,
            identity_lookup[record['key']],
            entry['outcome'] if entry and entry.get('outcome') is not None else None,
            edition_lookup.get(entry['peak_edition']) if entry and entry.get('peak_edition') else None,
            record['birth_date'],
        ])
    print(f'prospect pool: {len(pool)} under-{PROSPECT_MAX_AGE} club seasons, {len(identities)} identities')

    # ---- Archetypes: k-means over the learned player latent space.
    sample = [pool[i] for i in range(0, len(pool), max(1, len(pool) // 4000))]
    vectors, sampled = [], []
    for row in sample:
        prospect = dict(name=row[0], age=row[2], position=row[3], nationality=row[4], number=row[5],
                        years_at_club=row[6], seasons_seen=row[7], debut_age=row[8], foreign=row[9],
                        status='departed' if row[10] else 'listed')
        club = clubs[edition_list[row[1]]]
        vectors.append([dot(weights_row, player_vector(prospect, club, spec)) for weights_row in tower])
        sampled.append((prospect, club))
    centres, assignment = kmeans(vectors, 8)
    groups = []
    for index, centre in enumerate(centres):
        members = [sampled[i] for i, a in enumerate(assignment) if a == index]
        if members:
            groups.append((index, centre, members))
    # Level bands are relative to the other clusters, so the labels actually separate.
    ordered = sorted(groups, key=lambda g: sum(c['level'] for _, c in g[2]) / len(g[2]))
    bands = {}
    for position, (index, _, _) in enumerate(ordered):
        bands[index] = ('lower-table', 'mid-table', 'top-level')[min(2, position * 3 // max(1, len(ordered)))]
    archetypes = []
    for index, centre, members in groups:
        positions = Counter(p['position'] for p, _ in members)
        mean_age = sum(p['age'] for p, _ in members) / len(members)
        mean_level = sum(c['level'] for _, c in members) / len(members)
        mean_youth = sum(c['youth_rate'] for _, c in members) / len(members)
        roles = {'G': 'goalkeepers', 'D': 'defenders', 'M': 'midfielders', 'F': 'forwards'}
        role = roles[positions.most_common(1)[0][0]]
        age_band = 'Teenage' if mean_age < 19.3 else 'Late-teen' if mean_age < 20.3 else 'Age-21'
        label = f'{age_band} {role} at {bands[index]} clubs'
        archetypes.append(dict(index=index, centre=[round(v, 5) for v in centre], members=len(members),
                               label=label, mean_age=round(mean_age, 1), mean_level=round(mean_level, 3),
                               mean_youth_rate=round(mean_youth, 3),
                               positions=dict(positions.most_common())))
    typical_youth = sum(a['mean_youth_rate'] for a in archetypes) / len(archetypes)
    seen = Counter(a['label'] for a in archetypes)
    for archetype in archetypes:
        if seen[archetype['label']] > 1:
            archetype['label'] += (' · youth-heavy squads' if archetype['mean_youth_rate'] > typical_youth
                                   else ' · senior-heavy squads')

    # Nationality codes are interned once and shared by both data files; the
    # browser rehydrates them before building any feature vector.
    nation_codes = sorted({code for club in clubs.values() for code in club['nation_counts']}
                          | {r[4] for r in pool if r[4]})
    nation_index = {code: i for i, code in enumerate(nation_codes)}
    serve_clubs = []
    for edition_id in edition_list:
        club = clubs[edition_id]
        serve_clubs.append(dict(
            id=club['id'], club=club['club'], name=club['name'], year=club['year'],
            competition=club['competition'], crest=club['crest'], club_index=club_index[club['club']],
            level=round(club['level'], 5), attack=round(club['attack'], 5), defense=round(club['defense'], 5),
            squad_size=club['squad_size'], u21_count=club['u21_count'],
            youth_rate=round(club['youth_rate'], 5), mean_age=round(club['mean_age'], 3),
            foreign_share=round(club['foreign_share'], 5), turnover=round(club['turnover'], 5),
            profile_fallback=club['profile_fallback'], profile_source=club['profile_source'],
            positions=[club['position_counts'].get(group, 0) for group in ('G', 'D', 'M', 'F')],
            nations=[v for code, count in sorted(club['nation_counts'].items()) if code in nation_index
                     for v in (nation_index[code], count)]))

    # ---- Everything the browser is handed, rebuilt exactly as it will arrive.
    # Rounding happens before the parity fixtures are generated, so the fixtures
    # specify the served artifacts rather than the full-precision training state.
    def served_profile(record):
        nations = {}
        packed = record['nations']
        for i in range(0, len(packed), 2):
            nations[nation_codes[packed[i]]] = packed[i + 1]
        profile = {k: v for k, v in record.items() if k not in ('nations', 'positions')}
        profile['nation_counts'] = nations
        profile['position_counts'] = dict(zip(('G', 'D', 'M', 'F'), record['positions']))
        return profile

    served = {record['id']: served_profile(record) for record in serve_clubs}
    def round6(rows):
        return [[round(v, 6) for v in row] for row in rows]

    tower_out, embed_out = round6(tower), round6(embed)
    bias_out = [round(v, 6) for v in club_bias]
    weights_out = [round(v, 6) for v in weights]
    progression_out = round6(progression)
    offsets_out = [round(o, 6) for o in offsets]

    def served_fit_score(prospect, origin, player, target_id):
        target = served[target_id]
        latent = [dot(row, player) for row in tower_out]
        index = target['club_index']
        return (dot(latent, embed_out[index]) + bias_out[index]
                + dot(weights_out, candidate_vector(prospect, origin, target, spec)))

    picker = random.Random(SEED)
    fixtures = []
    for row in picker.sample(pool, 40):
        prospect = dict(name=row[0], age=row[2], position=row[3], nationality=row[4], number=row[5],
                        years_at_club=row[6], seasons_seen=row[7], debut_age=row[8], foreign=row[9],
                        status='departed' if row[10] else 'listed')
        origin_id = edition_list[row[1]]
        origin = served[origin_id]
        vector = player_vector(prospect, origin, spec)
        prospect['elite'] = class_probabilities(progression_out, vector, offsets_out)[len(OUTCOMES) - 1]
        fixtures.append(dict(
            prospect=prospect, origin=origin_id, player_vector=[round(v, 12) for v in vector],
            progression=[round(v, 12) for v in class_probabilities(progression_out, vector, offsets_out)],
            candidates=[dict(edition=target,
                             vector=[round(v, 12) for v in candidate_vector(prospect, origin, served[target], spec)],
                             score=round(served_fit_score(prospect, origin, vector, target), 12))
                        for target in picker.sample(edition_list, 3)]))

    # Interning the pool's nationalities happens last: the fixtures above and the
    # archetype pass both read the plain codes.
    for row in pool:
        row[4] = nation_index[row[4]] if row[4] else None

    model = dict(
        version=1, as_of=catalog['as_of'], seed=SEED, source='dist/catalog.json + dist/rosters/*.json',
        method=('Supervised models fitted offline from the bundled snapshot. Club profiles for a destination season '
                'use that club the season before, so no candidate feature sees the season the prospect would join. '
                'Validation is a forward split in time, never a random shuffle.'),
        limits=['Squad lists carry no minutes, fees, transfer values, injuries or scouting grades.',
                'The progression target is which calibre of squad list a player later appears on, not how good they '
                'became. A player who stays registered at an elite club for years without playing reaches the top '
                'class exactly like a player who starred there, and the model cannot tell them apart.',
                'Because of that, the highest projections cluster on big-club academy intakes: being at an elite '
                'club at 18 is itself the strongest evidence of being on an elite list at 21.',
                'The ranker predicts observed next destinations, loans included, which the source cannot separate '
                'from permanent transfers. For a teenager at a strong club the likeliest next club is often a '
                'smaller one, and the model reproduces that rather than naming who ought to sign them.',
                'A player leaving the bundled five leagues is unobservable and is reported as censoring, not failure.',
                'Cross-era and cross-league strength is uncalibrated, here as everywhere else in this project.',
                'Fit is learned from where players actually moved, which encodes the recruitment market, not merit.'],
        spec=spec, player_features=list(PLAYER_FEATURES), candidate_features=list(CANDIDATE_FEATURES),
        cross_offset=CROSS_OFFSET, position_share_source='scripts/scouting_features.py',
        fit=dict(tower=tower_out, embed=embed_out, club_bias=bias_out, weights=weights_out,
                 clubs=club_names, metrics=fit_metrics),
        progression=dict(weights=progression_out, prior_offsets=offsets_out, outcomes=list(OUTCOMES),
                         tier_cuts=[round(c, 6) for c in cuts], metrics=progression_metrics),
        archetypes=archetypes, fixtures=fixtures,
        nations=dict(sorted(nation_pool.items())),
        source_corrections=[dict(edition=edition, player=name, **dict(fix.items()))
                            for (edition, name), fix in sorted(SOURCE_CORRECTIONS.items())],
        regions={code: REGIONS[code] for code in sorted(nation_pool) if code in REGIONS},
        flags=flag_assets(sorted(nation_pool)),
        pool=dict(size=len(pool), identities=len(identities), max_age=PROSPECT_MAX_AGE,
                  labelled=sum(1 for row in pool if row[12] is not None)))
    (OUT / 'model.json').write_text(json.dumps(model, ensure_ascii=False, separators=(',', ':')))
    (OUT / 'clubs.json').write_text(json.dumps(dict(
        version=1, as_of=catalog['as_of'], nation_codes=nation_codes,
        note='nations is a flat [code index, count, ...] list; positions is [G, D, M, F]. A club profile for '
             'season Y describes that club in season Y-1, named in profile_source.',
        clubs=serve_clubs), ensure_ascii=False, separators=(',', ':')))
    (OUT / 'prospects.json').write_text(json.dumps(dict(
        version=1, as_of=catalog['as_of'], max_age=PROSPECT_MAX_AGE,
        fields=['name', 'edition', 'age', 'position', 'nationality', 'number', 'years_at_club', 'seasons_seen',
                'debut_age', 'foreign', 'departed', 'identity', 'outcome', 'peak_edition', 'birth_date'],
        current_year=latest_year,
        note='current_year is the most recent season in the snapshot; its prospects have no recorded outcome '
             'because their window runs past the cutoff. Ages in rows are ages during that season, not today.',
        editions=edition_list, nation_codes=nation_codes, rows=pool), ensure_ascii=False, separators=(',', ':')))
    for name in ('model.json', 'clubs.json', 'prospects.json'):
        print(f'  dist/scouting/{name}: {(OUT / name).stat().st_size / 1024:.0f} KB')
    return model


if __name__ == '__main__':
    build()
