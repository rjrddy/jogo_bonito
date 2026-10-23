import assert from 'node:assert/strict';
import fs from 'node:fs';
import { simulate, expectedGoals, outcomeDistribution } from '../dist/simulator.js';
import { snapshot, probabilities } from '../dist/engine.js';
const catalog = JSON.parse(fs.readFileSync('dist/catalog.json', 'utf8'));
const city = catalog.teams.find(t => t.id === 'en-2023-manchester-city');
const madrid = catalog.teams.find(t => t.id === 'es-2016-real-madrid');
assert.ok(city && madrid);
assert.equal(city.gf, 94);
assert.equal(madrid.gf, 110);
assert.equal(new Set(catalog.teams.map(t => t.id)).size, catalog.teams.length);
for (const code of ['en', 'es', 'de', 'it', 'fr'])
  for (let year = 2010; year <= 2026; year++) {
    const teams = catalog.teams.filter(t => t.competition === code && t.year === year);
    assert.equal(
      teams.length,
      code === 'de' || (code === 'fr' && year >= 2024) ? 18 : 20,
      `${code} ${year} team coverage`,
    );
  }
for (const [code, years] of [
  ['wc', [2010, 2014, 2018, 2022, 2026]],
  ['euros', [2012, 2016, 2021, 2024]],
  ['copa', [2011, 2015, 2016, 2019, 2021, 2024]],
]) {
  for (const year of years) {
    const coverage = catalog.coverage.find(c => c.competition === code && c.year === year);
    assert.ok(coverage?.complete, `${code} ${year} source coverage`);
  }
}
const first = simulate(city, madrid, { seed: 123 });
assert.deepEqual(first, simulate(city, madrid, { seed: 123 }));
assert.notDeepEqual(first.events, simulate(city, madrid, { seed: 124 }).events);
assert.equal(snapshot(first, 0).events.length, 0);
assert.equal(
  first.events.filter(e => e.type === 'shot' && e.outcome === 'goal').length,
  snapshot(first, 90).stats.home.goals + snapshot(first, 90).stats.away.goals,
);
assert.ok(
  first.events.every(
    (e, i) =>
      e.minute >= 0 &&
      e.minute <= 90 &&
      (!i || e.minute >= first.events[i - 1].minute) &&
      e.match_id === first.id,
  ),
);
assert.equal(new Set(first.events.map(e => e.id)).size, first.events.length);
for (const team of catalog.teams) {
  const match = simulate(team, city, { seed: 0 });
  assert.ok(match.events.length > 0);
  assert.ok(Object.values(match.rates).every(n => Number.isFinite(n) && n >= 0.15 && n <= 4.5));
}
assert.throws(() => simulate(city, madrid, { seed: -1 }));
assert.throws(() => simulate(city, madrid, { seed: 1.5 }));
assert.throws(() => simulate(city, madrid, { seed: Infinity }));
assert.throws(() => simulate(city, madrid, { venue: 'invalid' }));
const neutral = expectedGoals(city, madrid),
  swapped = expectedGoals(madrid, city);
assert.equal(neutral.home, swapped.away);
assert.equal(neutral.away, swapped.home);
const atHome = expectedGoals(city, madrid, 'home');
assert.ok(atHome.home > neutral.home && atHome.away < neutral.away);
const zero = snapshot(first, 0).stats;
const prior = probabilities(zero, 0, first.rates),
  distribution = outcomeDistribution(first.rates);
assert.ok(prior.every((n, i) => Math.abs(n - distribution[i]) < 1e-10));
const poor = { ...city, attack: 0.6, defense: 1.5 },
  strong = { ...city, attack: 1.6, defense: 0.6 };
assert.ok(outcomeDistribution(expectedGoals(strong, poor))[0] > 0.7);
// Seeded Monte Carlo verifies the generated goals track the declared rates.
let goals = 0;
for (let seed = 0; seed < 1200; seed++) {
  const m = simulate(city, madrid, { seed });
  goals += m.events.filter(e => e.team === 'home' && e.outcome === 'goal').length;
}
assert.ok(Math.abs(goals / 1200 - neutral.home) < 0.12);
console.log(
  `Historical simulator: ${catalog.teams.length} editions, all competition years, deterministic events, strength response, probability and goal-rate checks passed.`,
);
