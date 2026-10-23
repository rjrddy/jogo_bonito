import assert from 'node:assert/strict';
import fs from 'node:fs';
import { paletteFor, matchColors, readable, contrast } from '../dist/team-colors.js';
const data = JSON.parse(fs.readFileSync('dist/badge-colors.json'));
const catalog = JSON.parse(fs.readFileSync('dist/catalog.json'));
const manifest = JSON.parse(fs.readFileSync('dist/assets/crests/clubs.json'));
assert.equal(Object.keys(data.palettes).length, Object.keys(manifest.clubs).length);
for (const edition of catalog.teams) {
  const palette = paletteFor(edition, data);
  assert.ok(palette.length);
  for (const c of palette) {
    assert.match(c, /^#[a-f\d]{6}$/i);
    for (const dark of [false, true])
      for (const bg of dark ? ['#142019', '#1a2a1f'] : ['#f2f1e9', '#f9f8f1'])
        assert.ok(contrast(readable(c, dark), bg) >= 4.5);
  }
}
const team = name => catalog.teams.find(t => t.name === name);
assert.equal(paletteFor(team('Manchester City'), data)[0], '#6cabdd');
assert.equal(paletteFor(team('Real Madrid'), data)[0], '#ffffff');
const derby = matchColors(team('Liverpool'), team('Arsenal'), data);
assert.ok(contrast(derby.home, derby.away) >= 1.7);
assert.ok(paletteFor(team('Arsenal'), data).includes(derby.away));
console.log('Badge palette coverage, clash handling and theme contrast passed.');
