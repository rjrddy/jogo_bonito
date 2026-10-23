// Pure analytical helpers. These describe the simulator, not measured football forecasts.
import { randomGenerator } from './simulator.js';
export function poissonMass(rate, max = 6) {
  const p = [Math.exp(-rate)];
  for (let k = 1; k < max; k++) p.push((p[k - 1] * rate) / k);
  p.push(Math.max(0, 1 - p.reduce((a, b) => a + b, 0)));
  return p;
}
export function scoreMatrix(rates) {
  const h = poissonMass(rates.home),
    a = poissonMass(rates.away);
  return h.map(p => a.map(q => p * q));
}
function drawPoisson(rate, random) {
  let p = 1,
    n = 0;
  const limit = Math.exp(-rate);
  do {
    n++;
    p *= random();
  } while (p > limit);
  return n - 1;
}
export function runBatch(rates, count, seed) {
  if (!Number.isInteger(count) || count < 1 || count > 10000) throw new Error('Batch size must be 1–10,000.');
  if (!['home', 'away'].every(k => Number.isFinite(rates[k]) && rates[k] > 0 && rates[k] <= 4.5))
    throw new Error('Invalid scoring rates.');
  if (!Number.isInteger(seed) || seed < 0 || seed > 4294967295) throw new Error('Invalid batch seed.');
  const random = randomGenerator(seed),
    wins = [0, 0, 0],
    scores = new Map();
  let hg = 0,
    ag = 0,
    btts = 0,
    over = 0;
  for (let i = 0; i < count; i++) {
    const h = drawPoisson(rates.home, random),
      a = drawPoisson(rates.away, random);
    wins[h > a ? 0 : h === a ? 1 : 2]++;
    hg += h;
    ag += a;
    btts += h > 0 && a > 0;
    over += h + a >= 3;
    const key = h + '–' + a;
    scores.set(key, (scores.get(key) || 0) + 1);
  }
  return {
    count,
    seed,
    wins,
    homeGoals: hg / count,
    awayGoals: ag / count,
    btts: btts / count,
    over25: over / count,
    scores: [...scores].sort((a, b) => b[1] - a[1]).slice(0, 8),
  };
}
export function playerLines(match, minute = 90) {
  const rows = new Map();
  for (const team of ['home', 'away'])
    for (const p of match.lineups[team] || [])
      rows.set(team + ':' + p.id, { ...p, team, goals: 0, shots: 0, xg: 0, passes: 0, completed: 0 });
  for (const e of match.events) {
    if (e.minute > minute || !e.player_id) continue;
    const row = rows.get(e.team + ':' + e.player_id);
    if (!row) continue;
    if (e.type === 'shot') {
      row.shots++;
      row.xg += e.xg;
      row.goals += e.outcome === 'goal';
    } else if (e.type === 'pass') {
      row.passes++;
      row.completed += e.outcome === 'complete';
    }
  }
  return [...rows.values()].sort(
    (a, b) => b.goals - a.goals || b.xg - a.xg || b.completed - a.completed || a.name.localeCompare(b.name),
  );
}
export function compareTeams(home, away) {
  return [
    { label: 'Goals scored / match', home: home.gf / home.played, away: away.gf / away.played },
    {
      label: 'Goals conceded / match ↓',
      home: home.ga / home.played,
      away: away.ga / away.played,
      lower: true,
    },
    {
      label: 'Win rate',
      home: (home.wins / home.played) * 100,
      away: (away.wins / away.played) * 100,
      unit: '%',
    },
    { label: 'Attack vs competition avg', home: home.attack, away: away.attack },
    { label: 'Conceding vs competition avg ↓', home: home.defense, away: away.defense, lower: true },
  ];
}
