"""Canonical scouting feature construction, mirrored byte-for-byte in dist/scouting-engine.js.

Two vectors are built here and nowhere else:

* ``player_vector``  — what is knowable about a prospect at scouting time.
* ``candidate_vector`` — a club edition as a destination, plus the explicit
  player x club cross terms that make a fit score explainable.

Both take plain records so the browser can build them for a hand-entered
prospect using exactly the same arithmetic. ``tests/scouting.test.mjs`` replays
the fixtures exported in the model file through the JavaScript port and fails on
any divergence, which is the only thing keeping the two implementations honest.
"""
from math import log1p

POSITIONS = ('G', 'D', 'M', 'F')
COMPETITIONS = ('en', 'es', 'de', 'it', 'fr')
# Expected share of an eleven by position group; used for squad-need scarcity.
POSITION_SHARE = {'G': 1 / 11, 'D': 4 / 11, 'M': 4 / 11, 'F': 2 / 11}

PLAYER_FEATURES = (
    'bias', 'age', 'age_dev', 'pos_g', 'pos_d', 'pos_m', 'pos_f', 'club_level',
    'club_attack', 'club_defense', 'number_low', 'number_norm', 'pos_depth',
    'years_at_club', 'seasons_seen', 'debut_age', 'foreign', 'nation_pool',
    'club_youth_rate', 'listed',
)
CANDIDATE_FEATURES = (
    'bias', 'level', 'attack', 'defense', 'youth_rate', 'foreign_share',
    'turnover', 'u21_count', 'profile_fallback',
    'comp_en', 'comp_es', 'comp_de', 'comp_it', 'comp_fr',
    'level_gap', 'level_gap_sq', 'step_up_young', 'nation_share', 'position_need',
    'youth_fit', 'corridor', 'same_club', 'same_competition', 'foreign_fit',
    'elite_target', 'elite_step',
)
# Cross terms begin here; everything before describes the destination alone.
CROSS_OFFSET = CANDIDATE_FEATURES.index('level_gap')


def _z(value, stats, key):
    mean, sd = stats[key]
    return (value - mean) / sd if sd else 0.0


def player_vector(prospect, club, spec):
    """Features for a prospect, where ``club`` is their club edition profile."""
    stats = spec['scale']
    age = float(prospect['age'])
    position = prospect['position'] if prospect['position'] in POSITIONS else 'M'
    number = prospect.get('number')
    squad = max(1, club.get('squad_size') or 1)
    depth = (club.get('position_counts', {}).get(position, 0)) / squad
    pool = spec['nation_pool'].get(prospect.get('nationality'), 0)
    return [
        1.0,
        _z(age, stats, 'age'),
        ((age - 19.0) / 3.0) ** 2,
        1.0 if position == 'G' else 0.0,
        1.0 if position == 'D' else 0.0,
        1.0 if position == 'M' else 0.0,
        1.0 if position == 'F' else 0.0,
        _z(club['level'], stats, 'level'),
        _z(club['attack'], stats, 'attack'),
        _z(club['defense'], stats, 'defense'),
        1.0 if number is not None and 1 <= number <= 11 else 0.0,
        min(number or 40, 40) / 40.0,
        depth - POSITION_SHARE[position],
        min(float(prospect.get('years_at_club') or 0), 5.0) / 5.0,
        min(float(prospect.get('seasons_seen') or 1), 6.0) / 6.0,
        _z(float(prospect.get('debut_age') or age), stats, 'debut_age'),
        1.0 if prospect.get('foreign') else 0.0,
        log1p(pool) / 10.0,
        _z(club.get('youth_rate') or 0.0, stats, 'youth_rate'),
        0.0 if prospect.get('status') == 'departed' else 1.0,
    ]


def candidate_vector(prospect, origin, target, spec, exclude_self=False):
    """Destination features plus the player x club cross terms.

    ``origin`` is the prospect's club profile, ``target`` the destination club
    profile. ``exclude_self`` removes the prospect from the destination's own
    nationality and position counts, which matters only while training on pairs
    where the move already happened. ``prospect['elite']`` is the progression
    model's elite probability for this player, which is what lets the ranker
    treat a top prospect's options differently from an ordinary mover's.
    """
    stats = spec['scale']
    age = float(prospect['age'])
    elite = float(prospect.get('elite') or 0.0)
    position = prospect['position'] if prospect['position'] in POSITIONS else 'M'
    nationality = prospect.get('nationality')
    squad = max(1, target.get('squad_size') or 1)
    nation_count = target.get('nation_counts', {}).get(nationality, 0)
    position_count = target.get('position_counts', {}).get(position, 0)
    if exclude_self:
        squad = max(1, squad - 1)
        nation_count = max(0, nation_count - 1)
        position_count = max(0, position_count - 1)
    level_gap = target['level'] - origin['level']
    same_club = 1.0 if target.get('club') and target['club'] == origin.get('club') else 0.0
    corridor = spec['corridor'].get(origin.get('competition', '') + '>' + target.get('competition', ''), 0.0)
    youth_rate = target.get('youth_rate') or 0.0
    vector = [
        1.0,
        _z(target['level'], stats, 'level'),
        _z(target['attack'], stats, 'attack'),
        _z(target['defense'], stats, 'defense'),
        _z(youth_rate, stats, 'youth_rate'),
        target.get('foreign_share') or 0.0,
        target.get('turnover') or 0.0,
        log1p(target.get('u21_count') or 0) / 3.0,
        1.0 if target.get('profile_fallback') else 0.0,
    ]
    vector += [1.0 if target.get('competition') == code else 0.0 for code in COMPETITIONS]
    vector += [
        level_gap,
        level_gap * level_gap,
        level_gap * max(0.0, 21.0 - age) / 5.0,
        nation_count / squad,
        max(0.0, POSITION_SHARE[position] - position_count / squad) / POSITION_SHARE[position],
        youth_rate * max(0.0, 21.0 - age) / 5.0,
        corridor,
        same_club,
        1.0 if target.get('competition') == origin.get('competition') else 0.0,
        (target.get('foreign_share') or 0.0) * (1.0 if prospect.get('foreign') else 0.0),
        # How far a prospect can realistically move depends on how good they are.
        # Without these, the fitted level terms come out negative for everyone,
        # because the average move in the training data is lateral or downward.
        elite * _z(target['level'], stats, 'level'),
        elite * level_gap,
    ]
    if len(vector) != len(CANDIDATE_FEATURES):
        raise AssertionError(f'{len(vector)} values for {len(CANDIDATE_FEATURES)} declared features')
    return vector
