"""Generate fictional, reproducible fixtures. No external match data is used."""
import json
import math
import random
from pathlib import Path


def shot_xg(distance, angle):
    return round(1 / (1 + math.exp(- (2.1 - .145 * distance - .8 * angle))), 4)


def generate():
    fixtures = [
        ('city', 'Manchester City', 'Arsenal', 'MC', 'AR', ['Haaland', 'Foden', 'De Bruyne', 'Rodri', 'Bernardo Silva'], ['Saka', 'Ødegaard', 'Martinelli', 'Rice', 'Havertz']),
        ('liverpool', 'Liverpool', 'Chelsea', 'LI', 'CH', ['Salah', 'Díaz', 'Mac Allister', 'Szoboszlai', 'Gakpo'], ['Palmer', 'Fernández', 'Caicedo', 'Jackson', 'Madueke']),
        ('barca', 'Barcelona', 'Real Madrid', 'BA', 'RM', ['Yamal', 'Pedri', 'Raphinha', 'Lewandowski', 'Gavi'], ['Mbappé', 'Vinícius Jr.', 'Bellingham', 'Valverde', 'Rodrygo']),
    ]
    result = []
    for seed, (mid, home, away, hc, ac, hp, ap) in enumerate(fixtures, 71):
        rng = random.Random(seed)
        events = []
        for i in range(440):
            minute = round((i + 1) * 90 / 441, 3)
            team = 'home' if rng.random() < .59 else 'away'
            kind = 'shot' if rng.random() < .065 else 'pass'
            x, y = rng.uniform(8, 92), rng.uniform(5, 95)
            event = dict(id=f'{mid}-{i:04}', match_id=mid, minute=minute, team=team, type=kind, player=rng.choice(hp if team == 'home' else ap), x=round(x, 2), y=round(y, 2), xg=0, outcome='complete' if rng.random() < .87 else 'incomplete')
            if kind == 'shot':
                distance = rng.uniform(5, 31)
                angle = rng.uniform(0, 1.4)
                xg = shot_xg(distance, angle)
                event.update(x=round(100-distance if team == 'home' else distance, 2), y=round(50+rng.uniform(-27, 27), 2), xg=xg, outcome='goal' if rng.random() < xg else rng.choice(['saved', 'off target', 'blocked']))
            events.append(event)
        result.append(dict(id=mid, home=home, away=away, home_code=hc, away_code=ac, events=events))
    return result

if __name__ == '__main__':
    Path('dist/matches.json').write_text(json.dumps(generate(), ensure_ascii=False, separators=(',', ':')))
