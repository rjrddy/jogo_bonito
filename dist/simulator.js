import { assignPlayer, lineupError, FORMATIONS } from './squads.js';
// Historical team-edition baseline. All generated events are hypothetical.
export const MODEL_VERSION = 'historical-v3';
export const TACTICS = {
  balanced: { name: 'Balanced', attack: 1, exposure: 1 },
  possession: { name: 'Keep the ball', attack: 1.04, exposure: 0.96 },
  press: { name: 'High press', attack: 1.12, exposure: 1.1 },
  counter: { name: 'Counterattack', attack: 1.06, exposure: 1.02 },
  lowblock: { name: 'Low block', attack: 0.84, exposure: 0.86 },
};
const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));
export function randomGenerator(seed) {
  let state = Number(seed) >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t ^= t + Math.imul(t ^ (t >>> 7), 61 | t);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
export function expectedGoals(home, away, venue = 'neutral', tactics = {}) {
  const hk = tactics.home || 'balanced',
    ak = tactics.away || 'balanced';
  if (!Object.hasOwn(TACTICS, hk) || !Object.hasOwn(TACTICS, ak))
    throw new Error('Unknown tactical approach');
  const h = TACTICS[hk],
    a = TACTICS[ak];
  if (
    !home ||
    !away ||
    ![home.attack, home.defense, away.attack, away.defense].every(n => Number.isFinite(n) && n > 0)
  )
    throw new Error('Invalid team strengths');
  if (!['neutral', 'home'].includes(venue)) throw new Error('Invalid venue');
  // Equal competition baselines are an explicit simplifying assumption.
  const base = 1.35;
  return {
    home: clamp(
      base * home.attack * away.defense * h.attack * a.exposure * (venue === 'home' ? 1.12 : 1),
      0.15,
      4.5,
    ),
    away: clamp(
      base * away.attack * home.defense * a.attack * h.exposure * (venue === 'home' ? 0.92 : 1),
      0.15,
      4.5,
    ),
  };
}
function poisson(lambda, random) {
  let p = 1,
    k = 0;
  const limit = Math.exp(-lambda);
  do {
    k++;
    p *= random();
  } while (p > limit);
  return k - 1;
}
export function simulate(
  home,
  away,
  { seed = 202316, venue = 'neutral', lineups = {}, tactics = {}, formations = {} } = {},
) {
  if (!Number.isInteger(Number(seed)) || Number(seed) < 0 || Number(seed) > 4294967295)
    throw new Error('Seed must be an integer from 0 to 4294967295');
  for (const side of ['home', 'away']) {
    if (lineups[side]?.length) {
      const error = lineupError(lineups[side]);
      if (error) throw new Error(side + ': ' + error);
    }
  }
  for (const side of ['home', 'away'])
    if (formations[side] && !Object.hasOwn(FORMATIONS, formations[side]))
      throw new Error('Unknown formation');
  tactics = { home: tactics.home || 'balanced', away: tactics.away || 'balanced' };
  formations = { home: formations.home || '4-3-3', away: formations.away || '4-3-3' };
  const rates = expectedGoals(home, away, venue, tactics),
    random = randomGenerator(seed);
  const id = `sim-${home.id}-${away.id}-${venue}-${tactics.home}-${tactics.away}-${Number(seed)}`;
  const events = [];
  for (const team of ['home', 'away']) {
    const count = poisson(rates[team] / 0.15, random);
    for (let i = 0; i < count; i++) {
      const xg = 0.05 + 0.2 * random(),
        angle = random() * 0.9;
      const distance = clamp((2.1 - 0.8 * angle - Math.log(xg / (1 - xg))) / 0.145, 4, 35);
      const outcome =
        random() < xg ? 'goal' : random() < 0.5 ? 'saved' : random() < 0.5 ? 'blocked' : 'off target';
      events.push({
        minute: Math.round((0.05 + random() * 89.9) * 1000) / 1000,
        team,
        type: 'shot',
        player: 'Attacking unit',
        x: team === 'home' ? 100 - distance : distance,
        y: 50 + (random() - 0.5) * 48,
        xg,
        outcome,
      });
    }
  }
  const share = clamp(0.5 + 0.12 * Math.log(rates.home / rates.away), 0.32, 0.68);
  const passes = 560 + Math.floor(random() * 220);
  for (let i = 0; i < passes; i++) {
    const team = random() < share ? 'home' : 'away';
    events.push({
      minute: Math.round((0.05 + random() * 89.9) * 1000) / 1000,
      team,
      type: 'pass',
      player: 'Team build-up',
      x: 5 + random() * 90,
      y: 5 + random() * 90,
      xg: 0,
      outcome: random() < 0.86 ? 'complete' : 'incomplete',
    });
  }
  events.sort((a, b) => a.minute - b.minute);
  for (const [i, team] of ['home', 'away'].entries()) {
    if (lineups[team]?.length)
      assignPlayer(
        events.filter(e => e.team === team),
        lineups[team],
        randomGenerator((Number(seed) ^ (i ? 0xabcd1234 : 0x1234abcd)) >>> 0),
      );
  }
  events.forEach((e, i) => {
    e.id = `${id}-${i}`;
    e.match_id = id;
    e.x = +e.x.toFixed(3);
    e.y = +e.y.toFixed(3);
    e.xg = +e.xg.toFixed(4);
  });
  return {
    id,
    home: home.name,
    away: away.name,
    home_edition: home,
    away_edition: away,
    rates,
    seed: Number(seed),
    venue,
    model: MODEL_VERSION,
    lineups,
    tactics,
    formations,
    events,
  };
}
export function outcomeDistribution(rates) {
  const mass = lambda => {
    const p = [Math.exp(-lambda)];
    for (let i = 1; i < 40; i++) p.push((p[i - 1] * lambda) / i);
    return p;
  };
  const h = mass(rates.home),
    a = mass(rates.away);
  const result = [0, 0, 0];
  h.forEach((p, i) => a.forEach((q, j) => (result[i > j ? 0 : i === j ? 1 : 2] += p * q)));
  return result;
}
