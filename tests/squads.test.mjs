import assert from 'node:assert/strict';
import fs from 'node:fs';
import { suggestedXI, lineupError } from '../dist/squads.js';
import { simulate } from '../dist/simulator.js';
const players = Array.from({ length: 26 }, (_, i) => ({
  id: 'p' + i,
  name: 'Player ' + i,
  position: i < 3 ? 'G' : i < 11 ? 'D' : i < 19 ? 'M' : 'F',
  status: i === 25 ? 'departed' : 'listed',
}));
const xi = suggestedXI(players);
assert.equal(xi.length, 11);
assert.equal(xi.filter(p => p.position === 'G').length, 1);
assert.equal(lineupError(xi), null);
assert.ok(lineupError(xi.slice(1)));
assert.ok(lineupError([...xi.slice(0, 10), xi[0]]));
assert.ok(lineupError([...xi.slice(0, 10), players[25]]));
const edition = { id: 'test-2023', name: 'Test club', attack: 1, defense: 1 };
const a = simulate(edition, edition, { seed: 9, lineups: { home: xi, away: xi } }),
  b = simulate(edition, edition, { seed: 9, lineups: { home: xi, away: xi } });
assert.deepEqual(a, b);
assert.ok(a.events.every(e => xi.some(p => p.id === e.player_id && p.name === e.player)));
assert.ok(
  a.events.filter(e => e.type === 'shot').every(e => xi.find(p => p.id === e.player_id).position !== 'G'),
);
assert.throws(() => simulate(edition, edition, { lineups: { home: xi.slice(1) } }));
const plain = simulate(edition, edition, { seed: 9 });
assert.deepEqual(
  a.events.map(({ player, player_id, ...e }) => e),
  plain.events.map(({ player, player_id, ...e }) => e),
  'Lineup attribution must not silently change numeric team-strength simulation',
);
console.log(
  'Squad selection: valid XI, goalkeeper constraint, no departed/duplicate players, deterministic real-player attribution, unchanged goal model.',
);

const manifest = JSON.parse(fs.readFileSync('dist/rosters/index.json', 'utf8'));
assert.equal(manifest.missing.length, 0);
for (const entry of Object.values(manifest.editions)) {
  const roster = JSON.parse(fs.readFileSync('dist/' + entry.path, 'utf8'));
  assert.equal(lineupError(suggestedXI(roster.players)), null, entry.path);
}
const readSquad = id => JSON.parse(fs.readFileSync('dist/' + manifest.editions[id].path, 'utf8'));
const city = readSquad('en-2023-manchester-city'),
  madrid = readSquad('es-2016-real-madrid');
assert.ok(city.players.some(p => p.name === 'Erling Haaland'));
assert.ok(city.coaches.some(c => c.name.includes('Guardiola')));
assert.ok(madrid.players.some(p => p.name === 'Cristiano Ronaldo'));
assert.ok(madrid.coaches.some(c => c.name.includes('Zidane')));
assert.ok(!madrid.players.some(p => p.name.includes('Mbappé')));
console.log(
  'All packaged squads yield valid XIs; City 2023 and Madrid 2016 player/coach identities verified.',
);
