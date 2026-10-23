import assert from 'node:assert/strict';
import { scoreMatrix, poissonMass, runBatch, playerLines } from '../dist/lab-engine.js';
import { simulate, expectedGoals, outcomeDistribution } from '../dist/simulator.js';
import { suggestedXI, lineupError, FORMATIONS } from '../dist/squads.js';
const team = { id: 'team', name: 'Test', attack: 1.2, defense: 0.9 };
const rates = expectedGoals(team, team);
for (const lambda of [0.15, 1.35, 4.5])
  assert.ok(Math.abs(poissonMass(lambda).reduce((s, n) => s + n, 0) - 1) < 1e-12);
const grid = scoreMatrix(rates);
assert.equal(grid.length, 7);
assert.ok(grid.every(row => row.length === 7));
assert.ok(Math.abs(grid.flat().reduce((s, n) => s + n, 0) - 1) < 1e-12);
const batch = runBatch(rates, 10000, 42);
assert.equal(
  batch.wins.reduce((a, b) => a + b),
  10000,
);
assert.deepEqual(batch, runBatch(rates, 10000, 42));
const exact = outcomeDistribution(rates);
for (let i = 0; i < 3; i++) assert.ok(Math.abs(batch.wins[i] / batch.count - exact[i]) < 0.025);
assert.ok(Math.abs(batch.homeGoals - rates.home) < 0.05);
assert.ok(Math.abs(batch.awayGoals - rates.away) < 0.05);
assert.notDeepEqual(batch, runBatch(rates, 10000, 43));
assert.throws(() => runBatch(rates, 10001, 1));
assert.throws(() => runBatch({ home: 1 }, 100, 1));
assert.throws(() => runBatch(rates, 100, -1));
const press = expectedGoals(team, team, 'neutral', { home: 'press', away: 'balanced' });
assert.ok(press.home > rates.home && press.away > rates.away);
const block = expectedGoals(team, team, 'neutral', { home: 'lowblock', away: 'balanced' });
assert.ok(block.home < rates.home && block.away < rates.away);
assert.throws(() => expectedGoals(team, team, 'neutral', { home: '__proto__' }));
assert.throws(() => suggestedXI([], '__proto__'));
const roster = Array.from({ length: 40 }, (_, i) => ({
  id: 'p' + i,
  name: 'Player ' + i,
  position: i < 3 ? 'G' : i < 15 ? 'D' : i < 28 ? 'M' : 'F',
  status: 'listed',
}));
for (const formation of Object.keys(FORMATIONS))
  assert.equal(lineupError(suggestedXI(roster, formation)), null);
const match = simulate(team, team, {
  seed: 72,
  tactics: { home: 'press' },
  formations: { home: '3-5-2' },
  lineups: { home: suggestedXI(roster), away: suggestedXI(roster) },
});
const rows = playerLines(match, 90);
assert.equal(rows.length, 22);
assert.equal(
  rows.reduce((n, r) => n + r.goals, 0),
  match.events.filter(e => e.outcome === 'goal').length,
);
assert.equal(
  rows.reduce((n, r) => n + r.shots, 0),
  match.events.filter(e => e.type === 'shot').length,
);
assert.equal(
  playerLines(match, 0).reduce((n, r) => n + r.shots + r.passes, 0),
  0,
);
console.log(
  'Match Lab: score-grid mass, seeded 10k experiments vs exact outcomes, tactical effects, formations, player-stat consistency, invalid input checks passed.',
);
